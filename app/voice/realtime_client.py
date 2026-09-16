from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

from app.config import Settings


class RealtimeConfigurationError(RuntimeError):
    pass


class OpenAIRealtimeTranscriptionClient:
    """Adapter nhỏ cho OpenAI Realtime transcription, không gọi chat LLM."""

    SAMPLE_RATE = 24_000

    def __init__(self, settings: Settings) -> None:
        if not settings.stt_configured:
            raise RealtimeConfigurationError("OPENAI_API_KEY is missing")
        self.settings = settings

    @asynccontextmanager
    async def connect(self) -> AsyncIterator[Any]:
        from websockets.asyncio.client import connect

        async with connect(
            self.settings.openai_realtime_url,
            additional_headers={"Authorization": f"Bearer {self.settings.openai_api_key}"},
            max_size=2 * 1024 * 1024,
            ping_interval=20,
            ping_timeout=20,
        ) as websocket:
            await websocket.send(json.dumps(self.session_update_event()))
            yield websocket

    def session_update_event(self) -> dict[str, object]:
        transcription: dict[str, object] = {
            "model": self.settings.openai_realtime_model,
        }
        # gpt-live-transcribe uses the newer plural field. Keep the legacy
        # schema for gpt-realtime-whisper so existing LLM_v4 deployments work.
        if self.settings.openai_realtime_model.startswith("gpt-live-transcribe"):
            transcription["languages"] = ["vi"]
        else:
            transcription["language"] = "vi"

        return {
            "type": "session.update",
            "session": {
                "type": "transcription",
                "audio": {
                    "input": {
                        "format": {"type": "audio/pcm", "rate": self.SAMPLE_RATE},
                        "noise_reduction": {"type": "near_field"},
                        "transcription": transcription,
                        "turn_detection": None,
                    }
                },
            },
        }

    @staticmethod
    def append_event(base64_audio: str) -> str:
        return json.dumps({"type": "input_audio_buffer.append", "audio": base64_audio})

    @staticmethod
    def commit_event() -> str:
        return json.dumps({"type": "input_audio_buffer.commit"})

    @staticmethod
    def clear_event() -> str:
        return json.dumps({"type": "input_audio_buffer.clear"})
