from __future__ import annotations

import asyncio
import logging
import time
import uuid
from contextlib import asynccontextmanager, suppress
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from app.auth import ClientScope, resolve_client_scope
from app.config import Settings, get_settings
from app.container import AppContainer, build_container
from app.llm import LLMUnavailableError
from app.logging_config import configure_logging, safe_http_path
from app.schemas import (
    CharacterSummary,
    ChatRequest,
    ChatResponse,
    ErrorResponse,
    HealthResponse,
    SessionResetResponse,
)
from app.service import CharacterNotFoundError

logger = logging.getLogger(__name__)


def create_app(settings: Settings | None = None, container: AppContainer | None = None) -> FastAPI:
    resolved = settings or get_settings()
    log_path = configure_logging(resolved)

    @asynccontextmanager
    async def lifespan(application: FastAPI):
        try:
            resolved_container = container or build_container(resolved)
        except Exception:
            logger.exception("application_startup_failed")
            raise
        application.state.container = resolved_container
        logger.info(
            "application_started environment=%s model=%s embedding_provider=%s log_file=%s",
            resolved.rag_app_env,
            resolved.gemini_model,
            resolved.embedding_provider,
            log_path,
        )

        async def cleanup_memory() -> None:
            while True:
                await asyncio.sleep(3600)
                await resolved_container.database.purge_expired_sessions()

        cleanup_task = asyncio.create_task(cleanup_memory(), name="memory-ttl-cleanup")
        try:
            yield
        finally:
            cleanup_task.cancel()
            with suppress(asyncio.CancelledError):
                await cleanup_task
            await resolved_container.close()
            logger.info("application_stopped")

    application = FastAPI(
        title="Historical Character Hybrid RAG API",
        version="1.1.0",
        summary="API nhân vật lịch sử với một lần gọi Gemini và memory an toàn",
        description=(
            "Hybrid RAG bằng PostgreSQL/pgvector, memory bền vững 7 ngày, hai precheck cục bộ "
            "và đúng một generation call cho mỗi chat hợp lệ."
        ),
        openapi_version="3.1.0",
        lifespan=lifespan,
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=resolved.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "X-API-Key", "X-Request-ID"],
        expose_headers=["X-Request-ID"],
    )

    @application.middleware("http")
    async def request_logging(request: Request, call_next):
        request_id = request.headers.get("X-Request-ID") or str(uuid.uuid4())
        started = time.perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            path = safe_http_path(request.scope, request.url.path)
            logger.exception(
                "request_failed http_request_id=%s method=%s path=%s duration_ms=%d",
                request_id,
                request.method,
                path,
                int((time.perf_counter() - started) * 1000),
            )
            raise

        duration_ms = int((time.perf_counter() - started) * 1000)
        path = safe_http_path(request.scope, request.url.path)
        log_method = logger.debug if path in {"/health", "/ready"} else logger.info
        log_method(
            "request_completed http_request_id=%s method=%s path=%s status_code=%d duration_ms=%d",
            request_id,
            request.method,
            path,
            response.status_code,
            duration_ms,
        )
        response.headers["X-Request-ID"] = request_id
        return response

    @application.get(
        "/health", response_model=HealthResponse, tags=["system"], operation_id="getHealth"
    )
    async def health(request: Request) -> HealthResponse:
        database_ready = await request.app.state.container.database.health()
        corpus_ready = (
            await request.app.state.container.database.ready() if database_ready else False
        )
        return HealthResponse(
            status="ok" if database_ready and corpus_ready else "degraded",
            service=resolved.app_name,
            database_ready=database_ready,
            corpus_ready=corpus_ready,
            llm_model=resolved.gemini_model,
            embedding_provider=resolved.embedding_provider,
        )

    @application.get(
        "/ready",
        response_model=HealthResponse,
        tags=["system"],
        operation_id="getReadiness",
        responses={503: {"model": ErrorResponse}},
    )
    async def ready(request: Request) -> HealthResponse:
        response = await health(request)
        if not response.database_ready or not response.corpus_ready:
            raise HTTPException(
                status.HTTP_503_SERVICE_UNAVAILABLE, "Database or corpus is not ready"
            )
        return response

    @application.get(
        "/v1/characters",
        response_model=list[CharacterSummary],
        tags=["characters"],
        operation_id="listCharacters",
        dependencies=[Depends(resolve_client_scope)],
    )
    async def list_characters(request: Request) -> list[CharacterSummary]:
        return [
            CharacterSummary(**item)
            for item in await request.app.state.container.database.list_characters()
        ]

    @application.post(
        "/v1/characters/{character_id}/chat",
        response_model=ChatResponse,
        tags=["chat"],
        operation_id="chatWithCharacter",
        responses={
            404: {"model": ErrorResponse},
            502: {"model": ErrorResponse},
            503: {"model": ErrorResponse},
        },
    )
    async def chat(
        character_id: str, payload: ChatRequest, request: Request, client_scope: ClientScope
    ) -> ChatResponse:
        return await request.app.state.container.chat_service.chat(
            character_id, payload, client_scope
        )

    @application.delete(
        "/v1/characters/{character_id}/sessions/{session_id}",
        response_model=SessionResetResponse,
        tags=["chat"],
        operation_id="resetCharacterSession",
        responses={404: {"model": ErrorResponse}},
    )
    async def reset_session(
        character_id: str,
        session_id: str,
        request: Request,
        client_scope: ClientScope,
    ) -> SessionResetResponse:
        deleted = await request.app.state.container.chat_service.reset_session(
            character_id,
            session_id,
            client_scope,
        )
        return SessionResetResponse(session_id=session_id, deleted=deleted)

    @application.exception_handler(CharacterNotFoundError)
    async def character_not_found(_: Request, exc: CharacterNotFoundError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"Character not found: {exc}"})

    @application.exception_handler(LLMUnavailableError)
    async def llm_unavailable(request: Request, exc: LLMUnavailableError) -> JSONResponse:
        logger.error(
            "llm_unavailable path=%s error=%s cause=%s",
            request.url.path,
            exc,
            type(exc.__cause__).__name__ if exc.__cause__ else "unknown",
        )
        return JSONResponse(status_code=503, content={"detail": f"LLM unavailable: {exc}"})

    frontend_dir = Path(__file__).resolve().parents[1] / "frontend"

    @application.get("/", include_in_schema=False)
    async def root() -> FileResponse:
        return FileResponse(frontend_dir / "index.html")

    application.mount("/static", StaticFiles(directory=frontend_dir), name="static")
    return application


app = create_app()
