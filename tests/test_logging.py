from __future__ import annotations

import logging
from types import SimpleNamespace

from app.config import Settings
from app.logging_config import RedactingFormatter, configure_logging, safe_http_path


def test_file_logging_redacts_credentials(tmp_path) -> None:
    log_path = tmp_path / "app.log"
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        embedding_provider="hash",
        rag_log_file=log_path,
        rag_log_max_bytes=1024,
        rag_log_backup_count=2,
    )
    configure_logging(settings)

    logger = logging.getLogger("tests.logging")
    logger.warning("GEMINI_API_KEY=secret-value 'x-goog-api-key': 'another-secret'")
    for handler in logging.getLogger().handlers:
        handler.flush()

    contents = log_path.read_text(encoding="utf-8")
    assert "secret-value" not in contents
    assert "another-secret" not in contents
    assert contents.count("[REDACTED]") == 2


def test_formatter_redacts_bearer_and_gemini_key() -> None:
    formatter = RedactingFormatter("%(message)s")
    record = logging.LogRecord(
        "test",
        logging.INFO,
        __file__,
        1,
        "Authorization=Bearer token-123 AIza123456789012345678901234567890",
        (),
        None,
    )
    rendered = formatter.format(record)
    assert "token-123" not in rendered
    assert "AIza" not in rendered


def test_safe_http_path_hides_session_id() -> None:
    route = SimpleNamespace(path="/v1/characters/{character_id}/sessions/{session_id}")
    raw_path = "/v1/characters/to_vinh_dien/sessions/private-session-123"

    assert safe_http_path({"route": route}, raw_path) == route.path
    assert safe_http_path({}, raw_path).endswith("/sessions/{session_id}")
    assert "private-session-123" not in safe_http_path({}, raw_path)
