from __future__ import annotations

from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_name: str = "historical-character-rag-api"
    rag_app_env: str = "development"
    rag_app_host: str = "0.0.0.0"
    rag_app_port: int = 8005
    rag_log_level: str = "INFO"
    rag_log_file: Path = PROJECT_ROOT / "logs" / "app.log"
    rag_log_max_bytes: int = Field(default=10 * 1024 * 1024, ge=1024)
    rag_log_backup_count: int = Field(default=5, ge=1, le=20)
    rag_debug_response: bool = False

    database_url: str = "postgresql+psycopg://historical:historical@localhost:5433/historical_rag"
    data_dir: Path = PROJECT_ROOT / "data" / "characters"

    llm_provider: str = "gemini"
    gemini_api_key: str | None = None
    gemini_model: str = "gemini-3.5-flash-lite"
    gemini_timeout_seconds: float = 30.0

    openai_api_key: str | None = None
    openai_realtime_model: str = "gpt-realtime-whisper"
    openai_realtime_url: str = "wss://api.openai.com/v1/realtime?intent=transcription"

    embedding_provider: str = "bge_m3"
    embedding_model: str = "BAAI/bge-m3"
    embedding_device: str = "auto"
    retrieval_limit: int = Field(default=6, ge=1, le=12)

    memory_ttl_seconds: int = Field(default=604800, ge=60)
    memory_recent_turns: int = Field(default=6, ge=1, le=20)
    memory_relevant_turns: int = Field(default=4, ge=0, le=10)

    api_auth_enabled: bool = False
    app_api_keys: str = ""
    cors_origins: str = "http://127.0.0.1:8005,http://localhost:8005"

    @field_validator("llm_provider", "embedding_provider", mode="before")
    @classmethod
    def normalize_provider(cls, value: object) -> str:
        return str(value).strip().lower()

    @property
    def api_keys(self) -> tuple[str, ...]:
        return tuple(
            dict.fromkeys(item.strip() for item in self.app_api_keys.split(",") if item.strip())
        )

    @property
    def allowed_origins(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]

    @property
    def is_production(self) -> bool:
        return self.rag_app_env.casefold() == "production"

    @property
    def stt_configured(self) -> bool:
        return bool(self.openai_api_key and self.openai_api_key.strip())


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
