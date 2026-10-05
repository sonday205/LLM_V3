# Historical Character Hybrid RAG API

API độc lập để thử nghiệm chất lượng hội thoại nhân vật lịch sử với:

- 47 mục nhân vật và corpus có nguồn, đủ 44 mục trong danh sách Word yêu cầu.
- PostgreSQL + pgvector hybrid RAG, không dùng Neo4j/GraphRAG.
- Memory bền vững, TTL 7 ngày, truy hồi theo gần đây và ngữ nghĩa.
- Hai precheck local: safety và privacy.
- Một request Gemini `gemini-3.5-flash-lite` cho mỗi chat hợp lệ.
- Output Gemini được trả nguyên; storage guard chỉ quyết định có lưu memory.
- Persona và ranh giới suy ngẫm được cấu hình bằng data, không hard-code nhân vật.
- Phân biệt tư liệu trực tiếp với bối cảnh chung để trả lời gần gũi mà không bịa đời tư.
- Push-to-talk STT tiếng Việt qua OpenAI Realtime WebSocket, transcript được kiểm tra trước khi gửi chat.
- FastAPI, OpenAPI 3.1, API-key auth tùy môi trường và frontend demo.

## Chạy bằng Docker

File `.env` local đã được ignore. Để cấu hình mới từ đầu:

```bash
cp .env.example .env
```

Điền `GEMINI_API_KEY`. Nếu dùng microphone, điền thêm `OPENAI_API_KEY`, sau đó chạy:

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8005/ready
```

## Log và debug

Ứng dụng ghi log dạng xoay vòng: mỗi file tối đa 10 MB và giữ 5 bản cũ.
Log không chứa nội dung câu hỏi, prompt, session ID hay API key.

Khi chạy trực tiếp, xem log tại:

```bash
tail -f logs/app.log
```

Khi chạy Docker, log nằm trong volume `app_logs` tại `/app/logs/app.log`:

```bash
docker compose exec api tail -f /app/logs/app.log
```

Tra một request theo ID trả về trong response hoặc header `X-Request-ID`:

```bash
docker compose exec api grep "REQUEST_ID_CAN_TIM" /app/logs/app.log
```

Các biến cấu hình là `RAG_LOG_LEVEL`, `RAG_LOG_FILE`, `RAG_LOG_MAX_BYTES` và
`RAG_LOG_BACKUP_COUNT`. Đặt `RAG_LOG_LEVEL=DEBUG` trong `.env` rồi recreate API
nếu cần log health/readiness chi tiết:

```bash
docker compose up -d --build --force-recreate api
```

Địa chỉ:

- Frontend: http://127.0.0.1:8005
- Swagger: http://127.0.0.1:8005/docs
- ReDoc: http://127.0.0.1:8005/redoc
- OpenAPI JSON: http://127.0.0.1:8005/openapi.json

Danh sách 47 mục nhân vật và ID: [CHARACTERS.md](CHARACTERS.md).
Đối chiếu file Word và cách nạp dữ liệu mới: [docs/CHARACTER_EXPANSION.md](docs/CHARACTER_EXPANSION.md).

Lần chạy đầu cần tải model embedding `BAAI/bge-m3`, vì vậy service `ingest` có
thể mất vài phút. Muốn smoke test nhẹ, đặt `EMBEDDING_PROVIDER=hash`; không dùng
hash embedding để kết luận chất lượng production.

Nếu chạy trực tiếp ngoài Docker, cài thêm gói embedding CPU (tách riêng để tránh
vô tình kéo CUDA runtime):

```bash
python -m pip install -r requirements.txt -r requirements-embedding-cpu.txt
```

## API chính

```http
GET /health
GET /ready
GET /v1/characters
POST /v1/characters/{character_id}/chat
DELETE /v1/characters/{character_id}/sessions/{session_id}
WS /v1/characters/{character_id}/voice
```

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8005/v1/characters/to_vinh_dien/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "demo-session-001",
    "message": "Chú sinh năm nào và quê ở đâu?",
    "debug": true
  }'
```

Khi `API_AUTH_ENABLED=true`, thêm header `X-API-Key`. Frontend chỉ giữ key trong
`sessionStorage` của tab hiện tại.

## Speech-to-text push-to-talk

STT giữ nguyên cách hoạt động của bản LLM_v4 trước: browser gửi audio PCM16 mono
24 kHz qua WebSocket tới API; API chuyển tiếp tới OpenAI Realtime transcription.
Transcript được đặt vào ô nhập để người dùng kiểm tra hoặc sửa trước khi bấm gửi,
vì vậy STT không tự gọi Gemini và không làm tăng `provider_call_count` của chat.

Cấu hình trong `.env`:

```dotenv
OPENAI_API_KEY=sk-...
OPENAI_REALTIME_MODEL=gpt-realtime-whisper
OPENAI_REALTIME_URL=wss://api.openai.com/v1/realtime?intent=transcription
```

Mặc định `gpt-realtime-whisper` được giữ để tương thích với LLM_v4 cũ. Adapter
cũng hỗ trợ `gpt-live-transcribe`; chỉ cần đổi `OPENAI_REALTIME_MODEL` khi muốn
chuyển sang model transcription hiện tại, không phải sửa code.

Không đưa `OPENAI_API_KEY` vào frontend. Docker chỉ truyền key vào container API.
Khi `API_AUTH_ENABLED=true`, browser gửi application key riêng trong event
`session.start`; application key này không phải OpenAI key.

Mở frontend bằng `http://127.0.0.1:8005`, `http://localhost:8005` hoặc HTTPS.
Không dùng `http://0.0.0.0:8005` vì browser không cho origin này truy cập mic.
Contract WebSocket chi tiết nằm tại [docs/VOICE_STT.md](docs/VOICE_STT.md).

## Corpus và crawl

Audit/crawl các URL bổ sung:

```bash
python -m scripts.crawl_sources --delay-seconds 2
```

Kết quả thô nằm ở `.runtime/crawl/`, không tự động được ingest. Sau khi biên tập
và đối chiếu thành Markdown có frontmatter trong `data/characters`, chạy:

```bash
python -m scripts.ingest
```

## Test

```bash
python -m pytest
python -m compileall -q app scripts tests
docker compose config
```

## Paired evaluation 50 ca

Chạy tạm baseline cũ ở port `8006` và project này ở port tương thích production
`8005`, rồi:

```bash
python -m scripts.evaluate \
  --old-url http://127.0.0.1:8006 \
  --new-url http://127.0.0.1:8005 \
  --delay-seconds 10

python -m scripts.report_evaluation evaluation/results/paired.jsonl \
  --output evaluation/results/REPORT.md
```

Runner checkpoint từng lượt vào JSONL và dừng an toàn khi gặp lỗi quyền, quota,
HTTP `503` hoặc fallback provider của baseline; chạy lại cùng lệnh sẽ tiếp tục
phần còn thiếu.

Đánh giá riêng 20 câu về cảm xúc, đời sống và chống bịa ký ức:

```bash
python -m scripts.evaluate \
  --cases evaluation/persona_reflection_20.yaml \
  --old-url http://127.0.0.1:8006 \
  --new-url http://127.0.0.1:8005 \
  --output evaluation/results/persona_reflection.jsonl
```

Xem thêm [kiến trúc](docs/ARCHITECTURE.md) và [OpenAPI](docs/openapi.yaml).
