from __future__ import annotations

import hashlib
import secrets
from typing import Annotated

from fastapi import Depends, HTTPException, status
from fastapi.security import APIKeyHeader

from app.config import Settings, get_settings

api_key_header = APIKeyHeader(
    name="X-API-Key",
    scheme_name="ApplicationApiKey",
    description="API key của ứng dụng gọi Historical Character RAG API.",
    auto_error=False,
)


def application_api_key_valid(supplied_key: str | None, settings: Settings) -> bool:
    """Kiểm tra API key cho WebSocket, nơi browser không dùng được Depends như REST."""

    if not settings.api_auth_enabled:
        return True
    if supplied_key is None or not settings.api_keys:
        return False
    return any(secrets.compare_digest(supplied_key, configured) for configured in settings.api_keys)


def resolve_client_scope(
    supplied_key: Annotated[str | None, Depends(api_key_header)],
    settings: Annotated[Settings, Depends(get_settings)],
) -> str:
    if not settings.api_auth_enabled:
        return "local-development"
    if not settings.api_keys:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "API auth is enabled but no key is configured"
        )
    if not application_api_key_valid(supplied_key, settings):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or missing X-API-Key")
    return hashlib.sha256(supplied_key.encode("utf-8")).hexdigest()[:24]


ClientScope = Annotated[str, Depends(resolve_client_scope)]
