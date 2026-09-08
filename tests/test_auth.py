import pytest
from fastapi import HTTPException

from app.auth import resolve_client_scope
from app.config import Settings


def test_auth_can_be_disabled_for_local_development() -> None:
    settings = Settings(_env_file=None, api_auth_enabled=False)
    assert resolve_client_scope(None, settings) == "local-development"


def test_auth_rejects_missing_key_and_hashes_valid_scope() -> None:
    settings = Settings(
        _env_file=None,
        api_auth_enabled=True,
        app_api_keys="portfolio-test-key",
    )
    with pytest.raises(HTTPException) as error:
        resolve_client_scope(None, settings)
    assert error.value.status_code == 401

    scope = resolve_client_scope("portfolio-test-key", settings)
    assert scope != "portfolio-test-key"
    assert len(scope) == 24
