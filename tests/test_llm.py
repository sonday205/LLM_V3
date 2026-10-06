from __future__ import annotations

import json
import logging

import httpx
import pytest

from app.config import Settings
from app.container import build_container
from app.llm import LLMUnavailableError, MockGateway, OpenRouterProvider, build_gateway


def settings(**overrides) -> Settings:
    return Settings(
        _env_file=None,
        **{
            "llm_provider": "openrouter",
            "openrouter_api_key": "test-key",
            "openrouter_models": "primary:free, fallback:free, last:free",
            **overrides,
        },
    )


def completion(**overrides) -> dict:
    return {
        "model": "fallback:free",
        "choices": [{"message": {"content": "  Câu trả lời nguyên bản.\n"}}],
        "usage": {"prompt_tokens": 12, "completion_tokens": 8},
        **overrides,
    }


def test_model_order_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_MODELS", " third:free, , first:free,, second:free ")
    configured = Settings(_env_file=None, llm_provider="openrouter")
    assert configured.llm_models == ["third:free", "first:free", "second:free"]
    assert configured.llm_model == "third:free"


@pytest.mark.parametrize(
    ("overrides", "expected"),
    [
        ({"openrouter_api_key": None}, "OPENROUTER_API_KEY"),
        ({"openrouter_api_key": "  "}, "OPENROUTER_API_KEY"),
        ({"openrouter_models": " , , "}, "OPENROUTER_MODELS"),
        ({"llm_provider": "gemini"}, "Unsupported LLM_PROVIDER"),
    ],
)
def test_invalid_config_fails_before_building_resources(overrides, expected) -> None:
    with pytest.raises(ValueError, match=expected):
        build_container(settings(**overrides))


def test_secret_hidden_in_settings_representation() -> None:
    assert "test-key" not in repr(settings())


def test_mock_needs_no_openrouter_config() -> None:
    configured = settings(llm_provider="mock", openrouter_api_key=None, openrouter_models="")
    assert isinstance(build_gateway(configured), MockGateway)
    assert configured.llm_model == "mock"


async def test_request_preserves_prompt_fallback_timeout_and_served_model(caplog) -> None:
    requests = []
    prompt = (
        "Persona\n<MEMORY>previous turn</MEMORY>\n"
        "<CONTEXT>source</CONTEXT>\n<QUESTION>hi</QUESTION>"
    )

    def handle(request):
        requests.append(request)
        body = json.loads(request.content)
        assert body["models"] == ["primary:free", "fallback:free", "last:free"]
        assert "model" not in body
        assert body["messages"] == [{"role": "user", "content": prompt}]
        assert body["stream"] is False
        assert body["max_tokens"] == 700
        assert body["reasoning"] == {"enabled": False, "exclude": True}
        assert request.headers["Authorization"] == "Bearer test-key"
        assert request.headers["HTTP-Referer"] == "https://example.com"
        assert request.headers["X-OpenRouter-Title"] == "History demo"
        assert request.extensions["timeout"]["read"] == 30
        assert str(request.url) == "https://openrouter.ai/api/v1/chat/completions"
        return httpx.Response(200, json=completion())

    caplog.set_level(logging.INFO, logger="app.llm")
    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        gateway = OpenRouterProvider(
            settings(
                openrouter_http_referer="https://example.com", openrouter_app_name="History demo"
            ),
            client,
        )
        result = await gateway.generate(prompt)
        await gateway.close()
        assert not client.is_closed  # Client do caller truyền vào không bị gateway đóng.
    assert len(requests) == 1
    assert result.text == "  Câu trả lời nguyên bản.\n"
    assert result.provider == "openrouter"
    assert result.model == "fallback:free"
    assert result.input_tokens == 12
    assert result.output_tokens == 8
    assert result.provider_call_count == 1
    assert "served_model=fallback:free" in caplog.text
    assert "requested_models=" in caplog.text
    assert "test-key" not in caplog.text
    assert prompt not in caplog.text


async def test_paid_models_reasoning_and_custom_endpoint_are_config_only() -> None:
    def handle(request):
        body = json.loads(request.content)
        assert body["models"] == ["paid-primary", "paid-fallback"]
        assert body["reasoning"] == {"effort": "minimal", "exclude": True}
        assert body["max_tokens"] == 2000
        assert str(request.url) == "https://example.com/api/v1/chat/completions"
        assert "HTTP-Referer" not in request.headers
        assert "X-OpenRouter-Title" not in request.headers
        return httpx.Response(200, json=completion(model="paid-fallback", usage=None))

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        result = await OpenRouterProvider(
            settings(
                openrouter_models="paid-primary,paid-fallback",
                openrouter_base_url="https://example.com/api/v1/",
                openrouter_reasoning_effort="minimal",
                openrouter_max_tokens=2000,
            ),
            client,
        ).generate("prompt")
    assert result.model == "paid-fallback"
    assert result.input_tokens is None


@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, "authentication_error"),
        (403, "authentication_error"),
        (402, "insufficient_credits"),
        (429, "rate_limit"),
        (502, "models_unavailable"),
        (503, "models_unavailable"),
        (504, "timeout"),
        (400, "http_400"),
    ],
)
async def test_http_errors_are_safe_and_do_not_retry(status, error, caplog) -> None:
    requests = []

    def handle(request):
        requests.append(request)
        return httpx.Response(status, json={"error": {"message": "sensitive-upstream-body"}})

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMUnavailableError, match=f"openrouter_{error}") as caught:
            await OpenRouterProvider(settings(), client).generate("sensitive-user-prompt")
    assert len(requests) == 1
    assert caught.value.__cause__ is None
    assert "sensitive-upstream-body" not in caplog.text
    assert "sensitive-user-prompt" not in caplog.text
    assert "test-key" not in caplog.text


@pytest.mark.parametrize(
    ("payload", "error"),
    [
        ({}, "malformed_response"),
        ({"choices": []}, "malformed_response"),
        ([], "malformed_response"),
        (completion(choices=[{"message": {"content": None}}]), "malformed_response"),
        (completion(choices=[{"message": {"content": " "}}]), "empty_text"),
        (completion(model=None), "malformed_response"),
        (completion(usage={"prompt_tokens": "12"}), "malformed_response"),
        (
            completion(
                choices=[
                    {"message": {"content": "", "reasoning": "secret"}, "finish_reason": "length"}
                ]
            ),
            "output_limit",
        ),
        ({"error": {"code": 503, "message": "private"}}, "models_unavailable"),
    ],
)
async def test_invalid_and_error_responses(payload, error) -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(LLMUnavailableError, match=f"openrouter_{error}"):
            await OpenRouterProvider(settings(), client).generate("prompt")


async def test_reasoning_is_never_used_as_answer() -> None:
    payload = completion(choices=[{"message": {"content": "Answer", "reasoning": "private"}}])
    transport = httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    async with httpx.AsyncClient(transport=transport) as client:
        result = await OpenRouterProvider(settings(), client).generate("prompt")
    assert result.text == "Answer"


@pytest.mark.parametrize(
    ("exception", "error"),
    [(httpx.ReadTimeout, "timeout"), (httpx.ConnectError, "network_error")],
)
async def test_network_failures(exception, error) -> None:
    def handle(request):
        raise exception("sensitive detail", request=request)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handle)) as client:
        with pytest.raises(LLMUnavailableError, match=f"openrouter_{error}"):
            await OpenRouterProvider(settings(), client).generate("prompt")


async def test_invalid_json_response() -> None:
    transport = httpx.MockTransport(lambda _: httpx.Response(200, text="not json"))
    async with httpx.AsyncClient(transport=transport) as client:
        with pytest.raises(LLMUnavailableError, match="openrouter_malformed_response"):
            await OpenRouterProvider(settings(), client).generate("prompt")


async def test_owned_client_is_closed() -> None:
    gateway = build_gateway(settings())
    await gateway.close()
    assert gateway.client.is_closed
