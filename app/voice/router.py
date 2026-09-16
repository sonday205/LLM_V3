from __future__ import annotations

import asyncio
import base64
import json
import logging
import time
import uuid
from typing import Any, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import BaseModel, Field, ValidationError

from app.auth import application_api_key_valid
from app.voice.normalizer import normalize_transcript
from app.voice.realtime_client import (
    OpenAIRealtimeTranscriptionClient,
    RealtimeConfigurationError,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/v1/characters/{character_id}", tags=["voice"])


class VoiceSessionStart(BaseModel):
    type: Literal["session.start"]
    session_id: str = Field(min_length=8, max_length=120)
    debug: bool = False
    api_key: str | None = None


@router.websocket("/voice")
async def voice(character_id: str, websocket: WebSocket) -> None:
    """Chuyển tiếp PCM16 24 kHz tới OpenAI và chỉ trả transcript về browser."""

    request_id = str(uuid.uuid4())
    await websocket.accept()
    container = websocket.app.state.container

    try:
        start = VoiceSessionStart.model_validate(await websocket.receive_json())
    except (ValidationError, ValueError, json.JSONDecodeError):
        await _send_error(
            websocket, "invalid_session", "Dữ liệu mở phiên không hợp lệ.", request_id
        )
        await websocket.close(code=1008)
        return

    supplied_key = websocket.headers.get("X-API-Key") or start.api_key
    if not application_api_key_valid(supplied_key, container.settings):
        await _send_error(
            websocket, "invalid_api_key", "API key ứng dụng không hợp lệ.", request_id
        )
        await websocket.close(code=1008)
        return

    profile = await container.database.get_character(character_id)
    if profile is None:
        await _send_error(websocket, "character_not_found", "Không tìm thấy nhân vật.", request_id)
        await websocket.close(code=1008)
        return

    try:
        realtime = OpenAIRealtimeTranscriptionClient(container.settings)
    except RealtimeConfigurationError:
        await _send_error(
            websocket,
            "stt_not_configured",
            "STT chưa được cấu hình OPENAI_API_KEY.",
            request_id,
        )
        await websocket.close(code=1011)
        return

    commit_state: dict[str, float | None] = {"started_at": None}
    try:
        async with realtime.connect() as upstream:
            await websocket.send_json(
                {
                    "type": "session.ready",
                    "request_id": request_id,
                    "character_id": profile.id,
                    "sample_rate": realtime.SAMPLE_RATE,
                    "audio_format": "pcm16_mono",
                }
            )
            producer = asyncio.create_task(
                _browser_to_openai(websocket, upstream, realtime, commit_state),
                name=f"voice-producer-{request_id}",
            )
            consumer = asyncio.create_task(
                _openai_to_browser(websocket, upstream, request_id, commit_state),
                name=f"voice-consumer-{request_id}",
            )
            done, pending = await asyncio.wait(
                {producer, consumer}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            await asyncio.gather(*pending, return_exceptions=True)
            for task in done:
                task.result()
    except WebSocketDisconnect:
        return
    except Exception as exc:
        logger.warning(
            "voice_unavailable request_id=%s character_id=%s error_type=%s",
            request_id,
            character_id,
            type(exc).__name__,
        )
        try:
            await _send_error(
                websocket,
                "realtime_unavailable",
                "Dịch vụ nhận dạng giọng nói chưa sẵn sàng.",
                request_id,
                retryable=True,
            )
            await websocket.close(code=1011)
        except Exception:
            return


async def _browser_to_openai(
    browser: WebSocket,
    upstream: Any,
    realtime: OpenAIRealtimeTranscriptionClient,
    commit_state: dict[str, float | None],
) -> None:
    while True:
        event = await browser.receive()
        if event["type"] == "websocket.disconnect":
            raise WebSocketDisconnect(event.get("code", 1000))
        if audio := event.get("bytes"):
            encoded = base64.b64encode(audio).decode("ascii")
            await upstream.send(realtime.append_event(encoded))
            continue
        raw_text = event.get("text")
        if not raw_text:
            continue
        control = json.loads(raw_text)
        control_type = control.get("type")
        if control_type == "input_audio.commit":
            commit_state["started_at"] = time.perf_counter()
            await upstream.send(realtime.commit_event())
        elif control_type == "input_audio.clear":
            commit_state["started_at"] = None
            await upstream.send(realtime.clear_event())
        elif control_type == "session.close":
            return
        else:
            await _send_error(
                browser,
                "unknown_control_event",
                "Sự kiện điều khiển không được hỗ trợ.",
                None,
            )


async def _openai_to_browser(
    browser: WebSocket,
    upstream: Any,
    request_id: str,
    commit_state: dict[str, float | None],
) -> None:
    async for raw_message in upstream:
        event = json.loads(raw_message)
        event_type = event.get("type")
        if event_type == "conversation.item.input_audio_transcription.delta":
            await browser.send_json(
                {
                    "type": "transcript.delta",
                    "request_id": request_id,
                    "item_id": event.get("item_id"),
                    "delta": event.get("delta", ""),
                }
            )
        elif event_type == "conversation.item.input_audio_transcription.completed":
            transcript = normalize_transcript(str(event.get("transcript", "")))
            started = commit_state.get("started_at")
            latency_ms = (
                int((time.perf_counter() - started) * 1000) if started is not None else None
            )
            commit_state["started_at"] = None
            await browser.send_json(
                {
                    "type": "transcript.final",
                    "request_id": request_id,
                    "item_id": event.get("item_id"),
                    "transcript": transcript,
                    "stt_latency_ms": latency_ms,
                }
            )
            if not transcript:
                await _send_error(
                    browser,
                    "empty_transcript",
                    "Không nhận được lời nói.",
                    request_id,
                    retryable=True,
                )
        elif event_type == "error":
            error = event.get("error") or {}
            await _send_error(
                browser,
                str(error.get("code") or "openai_error"),
                "OpenAI không thể xử lý đoạn ghi âm.",
                request_id,
                retryable=True,
            )


async def _send_error(
    websocket: WebSocket,
    code: str,
    message: str,
    request_id: str | None,
    *,
    retryable: bool = False,
) -> None:
    await websocket.send_json(
        {
            "type": "error",
            "code": code,
            "message": message,
            "request_id": request_id,
            "retryable": retryable,
        }
    )
