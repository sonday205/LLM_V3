from __future__ import annotations

import logging
import time
from dataclasses import dataclass

import httpx

from app.config import Settings

logger = logging.getLogger(__name__)


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


class OpenRouterProvider:
    """Một HTTP request; OpenRouter xử lý fallback theo thứ tự models."""

    def __init__(self, settings: Settings, client: httpx.AsyncClient | None = None) -> None:
        settings.validate_llm()
        self.settings = settings
        self.models = settings.llm_models
        self._owns_client = client is None
        self.client = client or httpx.AsyncClient(timeout=settings.openrouter_timeout_seconds)
        logger.info("ai_provider=openrouter requested_models=%s", self.models)

    @staticmethod
    def _error_for_status(status_code: int) -> str:
        if status_code in {401, 403}:
            return "openrouter_authentication_error"
        if status_code == 402:
            return "openrouter_insufficient_credits"
        if status_code == 429:
            return "openrouter_rate_limit"
        if status_code in {502, 503}:
            return "openrouter_models_unavailable"
        if status_code in {408, 504}:
            return "openrouter_timeout"
        return f"openrouter_http_{status_code}"

    async def generate(self, prompt: str) -> LLMResult:
        started = time.perf_counter()
        key = self.settings.openrouter_api_key
        assert key is not None  # Đã kiểm tra bởi validate_llm khi khởi tạo provider.
        headers = {"Authorization": f"Bearer {key.get_secret_value().strip()}"}
        if self.settings.openrouter_http_referer:
            headers["HTTP-Referer"] = self.settings.openrouter_http_referer
        if self.settings.openrouter_app_name:
            headers["X-OpenRouter-Title"] = self.settings.openrouter_app_name
        effort = self.settings.openrouter_reasoning_effort
        reasoning: dict[str, str | bool] = (
            {"enabled": False, "exclude": True}
            if effort == "none"
            else {"effort": effort, "exclude": True}
        )
        try:
            response = await self.client.post(
                f"{self.settings.openrouter_base_url.rstrip('/')}/chat/completions",
                headers=headers,
                timeout=self.settings.openrouter_timeout_seconds,
                json={
                    "models": self.models,
                    # Giữ nguyên prompt gồm persona, memory, context và question.
                    "messages": [{"role": "user", "content": prompt}],
                    "stream": False,
                    "max_tokens": self.settings.openrouter_max_tokens,
                    "reasoning": reasoning,
                },
            )
            response.raise_for_status()
            payload = response.json()
            if "error" in payload:
                code = payload["error"].get("code")
                error = (
                    self._error_for_status(code)
                    if isinstance(code, int)
                    else "openrouter_provider_error"
                )
                raise LLMUnavailableError(error)
            choice = payload["choices"][0]
            answer = choice["message"]["content"]
            if not isinstance(answer, str):
                raise LLMUnavailableError("openrouter_malformed_response")
            if not answer.strip():
                error = (
                    "openrouter_output_limit"
                    if choice.get("finish_reason") == "length"
                    else "openrouter_empty_text"
                )
                raise LLMUnavailableError(error)
            model = payload["model"]
            if not isinstance(model, str) or not model.strip():
                raise LLMUnavailableError("openrouter_malformed_response")
            usage = payload.get("usage") or {}
            for name in ("prompt_tokens", "completion_tokens"):
                count = usage.get(name)
                if count is not None and (type(count) is not int or count < 0):
                    raise LLMUnavailableError("openrouter_malformed_response")
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info("ai_provider=openrouter served_model=%s latency_ms=%d", model, latency_ms)
            return LLMResult(
                text=answer,
                provider="openrouter",
                model=model,
                latency_ms=latency_ms,
                input_tokens=usage.get("prompt_tokens"),
                output_tokens=usage.get("completion_tokens"),
            )
        except httpx.HTTPStatusError as exc:
            error = self._error_for_status(exc.response.status_code)
        except httpx.TimeoutException:
            error = "openrouter_timeout"
        except httpx.HTTPError:
            error = "openrouter_network_error"
        except LLMUnavailableError as exc:
            error = str(exc)
        except (KeyError, IndexError, TypeError, ValueError, AttributeError):
            error = "openrouter_malformed_response"
        logger.warning(
            "ai_provider=openrouter error=%s latency_ms=%d",
            error,
            int((time.perf_counter() - started) * 1000),
        )
        # Không nối exception upstream có thể chứa URL, credential hoặc body.
        raise LLMUnavailableError(error) from None

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
    if settings.llm_provider == "openrouter":
        return OpenRouterProvider(settings)
    raise ValueError("Unsupported LLM_PROVIDER; use openrouter or mock")
