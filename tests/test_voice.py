from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.domain import CharacterProfile
from app.main import create_app
from app.voice.normalizer import normalize_transcript
from app.voice.realtime_client import (
    OpenAIRealtimeTranscriptionClient,
    RealtimeConfigurationError,
)


class FakeDatabase:
    async def get_character(self, character_id: str) -> CharacterProfile | None:
        if character_id != "to_vinh_dien":
            return None
        return CharacterProfile(
            id=character_id,
            sort_order=1,
            display_name="Tô Vĩnh Diện",
            self_pronoun="chú",
            student_pronoun="cháu",
            audience="học sinh",
            tone="gần gũi",
            short_description="Nhân vật lịch sử.",
        )

    async def purge_expired_sessions(self) -> int:
        return 0


class FakeContainer:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.database = FakeDatabase()

    async def close(self) -> None:
        return None


def test_realtime_client_requires_key_and_builds_vietnamese_session() -> None:
    with pytest.raises(RealtimeConfigurationError):
        OpenAIRealtimeTranscriptionClient(Settings(_env_file=None, openai_api_key=None))

    client = OpenAIRealtimeTranscriptionClient(
        Settings(
            _env_file=None,
            openai_api_key="test-openai-key",
            openai_realtime_model="test-transcription-model",
        )
    )
    event = client.session_update_event()
    audio_input = event["session"]["audio"]["input"]

    assert event["type"] == "session.update"
    assert audio_input["format"] == {"type": "audio/pcm", "rate": 24_000}
    assert audio_input["transcription"] == {
        "model": "test-transcription-model",
        "language": "vi",
    }
    assert audio_input["turn_detection"] is None
    assert json.loads(client.commit_event())["type"] == "input_audio_buffer.commit"


def test_realtime_client_supports_current_live_transcribe_language_schema() -> None:
    client = OpenAIRealtimeTranscriptionClient(
        Settings(
            _env_file=None,
            openai_api_key="test-openai-key",
            openai_realtime_model="gpt-live-transcribe",
        )
    )

    transcription = client.session_update_event()["session"]["audio"]["input"]["transcription"]

    assert transcription == {
        "model": "gpt-live-transcribe",
        "languages": ["vi"],
    }


def test_transcript_normalizer_is_generic() -> None:
    assert normalize_transcript("  Xin   chào\nViệt Nam  ") == "Xin chào Việt Nam"


def test_voice_websocket_reports_missing_openai_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        embedding_provider="hash",
        openai_api_key=None,
    )
    application = create_app(settings, FakeContainer(settings))

    with (
        TestClient(application) as client,
        client.websocket_connect("/v1/characters/to_vinh_dien/voice") as websocket,
    ):
        websocket.send_json(
            {
                "type": "session.start",
                "session_id": "voice-test-session",
            }
        )
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "stt_not_configured"
    assert "OPENAI_API_KEY" in event["message"]


def test_voice_websocket_enforces_application_api_key() -> None:
    settings = Settings(
        _env_file=None,
        llm_provider="mock",
        embedding_provider="hash",
        api_auth_enabled=True,
        app_api_keys="expected-application-key",
        openai_api_key="test-openai-key",
    )
    application = create_app(settings, FakeContainer(settings))

    with (
        TestClient(application) as client,
        client.websocket_connect("/v1/characters/to_vinh_dien/voice") as websocket,
    ):
        websocket.send_json(
            {
                "type": "session.start",
                "session_id": "voice-test-session",
                "api_key": "wrong-key",
            }
        )
        event = websocket.receive_json()

    assert event["type"] == "error"
    assert event["code"] == "invalid_api_key"
