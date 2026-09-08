from __future__ import annotations

import time
import uuid
from dataclasses import asdict

from app.config import Settings
from app.database import Database
from app.llm import LLMUnavailableError
from app.memory import SafeMemoryService
from app.prompt import PromptBuilder
from app.domain import RetrievalResult
from app.retrieval import HybridRetriever, RetrievalPolicy
from app.safety import PrivacyPrecheck, SafetyPrecheck, StorageGuard
from app.schemas import ChatRequest, ChatResponse, SourceResponse


class CharacterNotFoundError(LookupError):
    pass


class ChatService:
    def __init__(
        self,
        settings: Settings,
        database: Database,
        retriever: HybridRetriever,
        memory: SafeMemoryService,
        prompt_builder: PromptBuilder,
        gateway,
        safety: SafetyPrecheck,
        privacy: PrivacyPrecheck,
        storage_guard: StorageGuard,
    ) -> None:
        self.settings = settings
        self.database = database
        self.retriever = retriever
        self.memory = memory
        self.prompt_builder = prompt_builder
        self.gateway = gateway
        self.safety = safety
        self.privacy = privacy
        self.storage_guard = storage_guard

    async def chat(self, character_id: str, payload: ChatRequest, client_scope: str) -> ChatResponse:
        started = time.perf_counter()
        request_id = str(uuid.uuid4())
        profile = await self.database.get_character(character_id)
        if profile is None:
            raise CharacterNotFoundError(character_id)

        safety_started = time.perf_counter()
        safety_result = self.safety.check(payload.message)
        safety_ms = self._elapsed(safety_started)
        if not safety_result.allowed:
            return self._blocked(request_id, character_id, safety_result, safety_ms, started)

        privacy_started = time.perf_counter()
        privacy_result = self.privacy.check(payload.message)
        privacy_ms = self._elapsed(privacy_started)
        if not privacy_result.allowed:
            return self._blocked(
                request_id,
                character_id,
                privacy_result,
                safety_ms,
                started,
                privacy_ms,
            )

        memory_started = time.perf_counter()
        session_pk, memory_context = await self.memory.context(
            client_scope,
            character_id,
            payload.session_id,
            payload.message,
        )
        memory_ms = self._elapsed(memory_started)

        retrieval_started = time.perf_counter()
        if RetrievalPolicy.should_retrieve_history(payload.message):
            retrieval = await self.retriever.retrieve(character_id, payload.message)
        else:
            retrieval = RetrievalResult(status="not_used")
        retrieval_ms = self._elapsed(retrieval_started)

        prompt = self.prompt_builder.build(profile, payload.message, memory_context, retrieval)
        llm_started = time.perf_counter()
        result = await self.gateway.generate(prompt)
        llm_ms = self._elapsed(llm_started)

        storage_started = time.perf_counter()
        stored = self.storage_guard.can_store(payload.message, result.text)
        if stored:
            await self.memory.store(session_pk, payload.message, result.text)
        storage_ms = self._elapsed(storage_started)

        timings = {
            "safety_precheck": safety_ms,
            "privacy_precheck": privacy_ms,
            "memory_read": memory_ms,
            "retrieval": retrieval_ms,
            "llm": llm_ms,
            "memory_write": storage_ms,
            "total": self._elapsed(started),
        }
        debug = None
        if payload.debug and self.settings.rag_debug_response:
            debug = {
                "retrieval_status": retrieval.status,
                "retrieved_chunk_ids": [chunk.id for chunk in retrieval.chunks],
                "memory_stored": stored,
                "input_tokens": result.input_tokens,
                "output_tokens": result.output_tokens,
            }
        return ChatResponse(
            request_id=request_id,
            character_id=character_id,
            answer=result.text,
            sources=[SourceResponse(**asdict(source)) for source in retrieval.sources()],
            memory_used=memory_context.used,
            provider=result.provider,
            model=result.model,
            provider_call_count=result.provider_call_count,
            degraded=result.provider == "mock",
            timings_ms=timings,
            usage={"input_tokens": result.input_tokens, "output_tokens": result.output_tokens},
            debug=debug,
        )

    async def reset_session(self, character_id: str, session_id: str, client_scope: str) -> bool:
        if await self.database.get_character(character_id) is None:
            raise CharacterNotFoundError(character_id)
        return await self.database.delete_session(client_scope, character_id, session_id)

    def _blocked(self, request_id, character_id, result, safety_ms, started, privacy_ms=0) -> ChatResponse:
        return ChatResponse(
            request_id=request_id,
            character_id=character_id,
            answer=result.response or "Yêu cầu không thể được xử lý an toàn.",
            provider_call_count=0,
            blocked_category=result.category,
            timings_ms={
                "safety_precheck": safety_ms,
                "privacy_precheck": privacy_ms,
                "total": self._elapsed(started),
            },
        )

    @staticmethod
    def _elapsed(started: float) -> int:
        return int((time.perf_counter() - started) * 1000)
