from __future__ import annotations

import logging
import re
from collections.abc import Mapping
from logging.handlers import RotatingFileHandler
from pathlib import Path
from typing import Any

from app.config import Settings

_SENSITIVE_PATTERNS = (
    (
        re.compile(
            r"(?i)((?:GEMINI_API_KEY|OPENROUTER_API_KEY|OPENAI_API_KEY|APP_API_KEYS|x-goog-api-key)[\"']?"
            r"\s*[=:]\s*[\"']?)[^\s,;\"'}]+"
        ),
        r"\1[REDACTED]",
    ),
    (
        re.compile(r"(?i)(authorization[\"']?\s*[=:]\s*[\"']?bearer\s+)[^\s,;\"'}]+"),
        r"\1[REDACTED]",
    ),
    (re.compile(r"\bAIza[0-9A-Za-z_-]{20,}\b"), "[REDACTED]"),
    (re.compile(r"\bsk-or-v1-[0-9A-Za-z_-]+\b"), "[REDACTED]"),
)
_SESSION_PATH = re.compile(r"(/sessions/)[^/?#]+")


def safe_http_path(scope: Mapping[str, Any], raw_path: str) -> str:
    """Ưu tiên route template và che session ID nếu request chưa match route."""

    route = scope.get("route")
    route_template = getattr(route, "path", None)
    if isinstance(route_template, str):
        return route_template
    return _SESSION_PATH.sub(r"\1{session_id}", raw_path)


class RedactingFormatter(logging.Formatter):
    """Ẩn credential nếu một exception vô tình chứa chúng trong log."""

    def format(self, record: logging.LogRecord) -> str:
        rendered = super().format(record)
        for pattern, replacement in _SENSITIVE_PATTERNS:
            rendered = pattern.sub(replacement, rendered)
        return rendered


def configure_logging(settings: Settings) -> Path:
    """Ghi log ứng dụng vào file xoay vòng và trả về đường dẫn đã resolve."""

    log_path = Path(settings.rag_log_file).expanduser()
    if not log_path.is_absolute():
        log_path = (Path.cwd() / log_path).resolve()
    log_path.parent.mkdir(parents=True, exist_ok=True)

    root_logger = logging.getLogger()
    root_logger.setLevel(settings.rag_log_level.upper())

    # create_app có thể được gọi nhiều lần trong test; không gắn trùng handler.
    for handler in root_logger.handlers:
        if getattr(handler, "_historical_rag_log_path", None) == str(log_path):
            handler.setLevel(settings.rag_log_level.upper())
            return log_path

    file_handler = RotatingFileHandler(
        log_path,
        maxBytes=settings.rag_log_max_bytes,
        backupCount=settings.rag_log_backup_count,
        encoding="utf-8",
    )
    file_handler._historical_rag_log_path = str(log_path)  # type: ignore[attr-defined]
    file_handler.setLevel(settings.rag_log_level.upper())
    file_handler.setFormatter(
        RedactingFormatter(
            "%(asctime)s %(levelname)s %(name)s %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S%z",
        )
    )
    root_logger.addHandler(file_handler)
    return log_path
