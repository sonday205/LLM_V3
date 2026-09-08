from __future__ import annotations

import time
from dataclasses import dataclass

import httpx

from app.config import Settings


class LLMUnavailableError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class LLMResult:
    text: str
    provider: str
    model: str
    latency_ms: int
    input_tokens: int | None = None
    output_tokens: int | None = None
    provider_call_count: int = 1


class GeminiGateway:
    """Một request provider cho mỗi lần generate; không router/reviewer/retry."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        if not settings.gemini_api_key:
            raise ValueError("GEMINI_API_KEY is required for LLM_PROVIDER=gemini")
        self.settings = settings
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=settings.gemini_timeout_seconds)

    async def generate(self, prompt: str) -> LLMResult:
        started = time.perf_counter()
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{self.settings.gemini_model}:generateContent"
        try:
            response = await self.client.post(
                url,
                headers={"x-goog-api-key": self.settings.gemini_api_key},
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {
                        "maxOutputTokens": 700,
                        "thinkingConfig": {"thinkingLevel": "minimal"},
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
            parts = payload["candidates"][0]["content"]["parts"]
            answer = "\n".join(str(part.get("text", "")) for part in parts)
            if not answer.strip():
                raise LLMUnavailableError("gemini_empty_text")
            usage = payload.get("usageMetadata") or {}
            return LLMResult(
                text=answer,
                provider="gemini",
                model=self.settings.gemini_model,
                latency_ms=int((time.perf_counter() - started) * 1000),
                input_tokens=usage.get("promptTokenCount"),
                output_tokens=usage.get("candidatesTokenCount"),
            )
        except (httpx.HTTPError, KeyError, IndexError, TypeError, ValueError) as exc:
            raise LLMUnavailableError(type(exc).__name__) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self.client.aclose()


class MockGateway:
    async def generate(self, prompt: str) -> LLMResult:
        question = prompt.rsplit("<QUESTION>", 1)[-1].split("</QUESTION>", 1)[0].strip()
        return LLMResult(
            text=f"Đây là câu trả lời thử nghiệm cho câu hỏi: {question}",
            provider="mock",
            model="mock",
            latency_ms=0,
        )

    async def close(self) -> None:
        return None


def build_gateway(settings: Settings):
    if settings.llm_provider == "mock":
        return MockGateway()
    if settings.llm_provider == "gemini":
        return GeminiGateway(settings)
    raise ValueError(f"Unsupported LLM_PROVIDER: {settings.llm_provider}")
