# Voice STT WebSocket

## Mục đích

Endpoint push-to-talk chuyển audio tiếng Việt thành văn bản. Nó không gửi câu
hỏi tới Gemini. Người dùng được xem và sửa transcript trước khi gọi REST chat.

```text
ws://127.0.0.1:8005/v1/characters/{character_id}/voice
```

OpenAPI 3.1 không mô hình hóa WebSocket nên endpoint này được mô tả riêng.

## Cấu hình server

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_REALTIME_MODEL=gpt-realtime-whisper
OPENAI_REALTIME_URL=wss://api.openai.com/v1/realtime?intent=transcription
```

`gpt-realtime-whisper` là mặc định tương thích với LLM_v4 cũ. Có thể chuyển sang
`gpt-live-transcribe` bằng biến môi trường; adapter sẽ tự dùng đúng schema ngôn
ngữ (`language` hoặc `languages`) theo model.

`OPENAI_API_KEY` chỉ được dùng ở backend. Không gửi key này xuống browser và
không dùng nó làm `APP_API_KEYS`.

## Protocol

Ngay sau khi mở WebSocket, client gửi:

```json
{
  "type": "session.start",
  "session_id": "demo-session-001",
  "api_key": null
}
```

`api_key` là application key tùy chọn khi `API_AUTH_ENABLED=true`, không phải
OpenAI key. Sau khi kết nối upstream thành công, server trả:

```json
{
  "type": "session.ready",
  "request_id": "uuid",
  "character_id": "to_vinh_dien",
  "sample_rate": 24000,
  "audio_format": "pcm16_mono"
}
```

Client gửi các binary frame PCM16 mono 24 kHz. Khi người dùng nhả nút micro:

```json
{"type": "input_audio.commit"}
```

Server có thể trả nhiều delta:

```json
{
  "type": "transcript.delta",
  "request_id": "uuid",
  "item_id": "item-id",
  "delta": "Chú sinh"
}
```

Và một kết quả cuối:

```json
{
  "type": "transcript.final",
  "request_id": "uuid",
  "item_id": "item-id",
  "transcript": "Chú sinh năm bao nhiêu?",
  "stt_latency_ms": 820
}
```

Client có thể dùng `input_audio.clear` để bỏ audio hoặc `session.close` để đóng
phiên. Lỗi luôn có `type=error`, `code`, `message`, `request_id` và `retryable`.

Các mã thường gặp:

- `stt_not_configured`: chưa đặt `OPENAI_API_KEY`.
- `invalid_api_key`: application key không hợp lệ.
- `character_not_found`: `character_id` không tồn tại.
- `empty_transcript`: không nhận được lời nói.
- `realtime_unavailable`: không kết nối được OpenAI Realtime.

## Kiểm tra thủ công

1. Điền `OPENAI_API_KEY` vào `.env`.
2. Chạy `docker compose up -d --build --force-recreate api`.
3. Kiểm tra `curl http://127.0.0.1:8005/health`; trường `stt_configured` phải là `true`.
4. Mở `http://127.0.0.1:8005`, cho phép microphone.
5. Giữ nút **Giữ để nói**, nói một câu tiếng Việt rồi nhả nút.
6. Kiểm tra transcript xuất hiện trong ô nhập và chỉ gọi chat sau khi bấm gửi.
