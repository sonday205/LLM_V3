from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class CharacterSummary(BaseModel):
    id: str
    sort_order: int
    display_name: str
    self_pronoun: str
    student_pronoun: str
    short_description: str


class ChatRequest(BaseModel):
    model_config = ConfigDict(
        json_schema_extra={
            "examples": [
                {
                    "session_id": "demo-session-001",
                    "message": "Chú sinh năm bao nhiêu?",
                    "debug": False,
                }
            ]
        }
    )

    session_id: str = Field(min_length=8, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    debug: bool = False


class SourceResponse(BaseModel):
    chunk_id: str
    document_id: str
    title: str
    source_name: str | None
    source_url: str | None
    evidence_scope: Literal["character", "contextual"] = "character"
    score: float


class ChatResponse(BaseModel):
    request_id: str
    character_id: str
    answer: str
    sources: list[SourceResponse] = Field(default_factory=list)
    memory_used: bool = False
    provider: str | None = None
    model: str | None = None
    provider_call_count: int = Field(ge=0, le=1)
    degraded: bool = False
    blocked_category: str | None = None
    timings_ms: dict[str, int] = Field(default_factory=dict)
    usage: dict[str, int | None] | None = None
    debug: dict[str, Any] | None = None


class SessionResetResponse(BaseModel):
    session_id: str
    deleted: bool


class HealthResponse(BaseModel):
    status: Literal["ok", "degraded"]
    service: str
    database_ready: bool
    corpus_ready: bool
    llm_model: str
    embedding_provider: str
    stt_configured: bool


class ErrorResponse(BaseModel):
    detail: str
    request_id: str | None = None
