# Historical Character Hybrid RAG API

API độc lập để thử nghiệm chất lượng hội thoại nhân vật lịch sử với:

- 48 mục nhân vật và corpus có nguồn, đủ 44 mục trong danh sách Word yêu cầu.
- PostgreSQL + pgvector hybrid RAG, không dùng Neo4j/GraphRAG.
- Memory bền vững, TTL 7 ngày, truy hồi theo gần đây và ngữ nghĩa.
- Hai precheck local: safety và privacy.
- Một HTTP request OpenRouter với explicit model fallback cho mỗi chat hợp lệ.
- Output LLM được trả nguyên; storage guard chỉ quyết định có lưu memory.
- Persona và ranh giới suy ngẫm được cấu hình bằng data, không hard-code nhân vật.
- Phân biệt tư liệu trực tiếp với bối cảnh chung để trả lời gần gũi mà không bịa đời tư.
- Push-to-talk STT tiếng Việt qua OpenAI Realtime WebSocket, transcript được kiểm tra trước khi gửi chat.
- FastAPI, OpenAPI 3.1, API-key auth tùy môi trường và frontend demo.

## Chạy bằng Docker

File `.env` local đã được ignore. Để cấu hình mới từ đầu:

```bash
cp .env.example .env
```

Điền `OPENROUTER_API_KEY` và đặt `LLM_PROVIDER=openrouter`. Nếu dùng microphone,
điền thêm `OPENAI_API_KEY`, sau đó chạy:

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8005/ready
```

## Cấu hình OpenRouter

Luồng: `ChatService -> gateway.generate(prompt) -> OpenRouterProvider -> OpenRouter`.
Model chỉ nằm trong cấu hình, không nằm trong business logic. Không dùng
`openrouter/free`, không retry hoặc gọi tuần tự từng model trong ứng dụng.

### Dùng model miễn phí

```dotenv
LLM_PROVIDER=openrouter
OPENROUTER_API_KEY=YOUR_OPENROUTER_KEY
OPENROUTER_BASE_URL=https://openrouter.ai/api/v1
OPENROUTER_MODELS=nvidia/nemotron-3-ultra-550b-a55b:free,google/gemma-4-31b-it:free,google/gemma-4-26b-a4b-it:free
OPENROUTER_TIMEOUT_SECONDS=30
OPENROUTER_MAX_TOKENS=700
OPENROUTER_REASONING_EFFORT=none
OPENROUTER_HTTP_REFERER=
OPENROUTER_APP_NAME=
```

Cả ba model có text input/output và giá token bằng 0 trong catalog kiểm tra ngày
2026-10-06. Thứ tự giữ theo lựa chọn ban đầu: Nemotron Ultra, Gemma 31B, Gemma
26B. Đây chưa phải xếp hạng chất lượng tiếng Việt đã benchmark. Model free vẫn
có giới hạn quota và có thể thay đổi khả dụng; kiểm tra lại
[catalog OpenRouter](https://openrouter.ai/api/v1/models) khi cấu hình.

`.env` cũ: thay `LLM_PROVIDER=gemini` bằng `openrouter`, thêm các biến trên và bỏ
`GEMINI_API_KEY`, `GEMINI_MODEL`, `GEMINI_TIMEOUT_SECONDS`. Không ghi key vào Git.
Thiếu key hoặc danh sách model rỗng sẽ khiến API dừng ngay khi startup, trước khi
khởi tạo database/embedding. Migration và ingest dữ liệu không cần key LLM.
`LLM_PROVIDER=mock` vẫn được giữ để demo/test offline.

### Chuyển sang model trả phí

Chỉ thay danh sách bằng model ID hợp lệ trong catalog, ví dụ:

```dotenv
OPENROUTER_MODELS=deepseek/deepseek-v3.2,openai/gpt-6-luna
```

Thứ tự ưu tiên chính là thứ tự sau khi tách dấu phẩy và bỏ khoảng trắng/mục rỗng.
Restart API hoặc chạy `docker compose up -d --build --force-recreate api` để nạp
cấu hình mới. Không sửa business logic. Nếu model cần reasoning, có thể chỉnh
`OPENROUTER_REASONING_EFFORT` và `OPENROUTER_MAX_TOKENS` bằng env.

### Fallback hoạt động thế nào

Một request chứa `models: [primary, fallback_1, fallback_2]`. OpenRouter thử model
đầu, rồi model tiếp theo nếu không phục vụ được do lỗi/khả dụng, chẳng hạn rate
limit, downtime hoặc moderation. Fallback không phải retry vô hạn và không sửa
câu trả lời sai hoặc bị cắt ngắn nhưng đã trả thành công. Xem
[tài liệu fallback](https://openrouter.ai/docs/guides/routing/model-fallbacks).

`provider_call_count=1` đếm HTTP generation call từ ứng dụng tới OpenRouter;
không đếm số lần thử nội bộ của OpenRouter. Response chat và log ghi model thực
sự phục vụ từ trường `model`; `/health.llm_model` là model ưu tiên cấu hình.
Lỗi upstream vẫn trả HTTP 503 theo hợp đồng cũ, với mã an toàn phân biệt auth,
credits, rate limit, model unavailable, timeout, network và response không hợp lệ.

### Khác biệt với Gemini trực tiếp

Prompt, memory, RAG và output text được giữ nguyên; không có streaming LLM,
structured output, tool calling hay image input trong luồng chat hiện tại.
STT OpenAI Realtime độc lập và giữ nguyên.

Gemini cũ dùng `thinkingLevel=minimal`. Nemotron free chỉ công bố effort
`medium/high`; mặc định mới dùng `reasoning.enabled=false`, `exclude=true` để
phù hợp trả lời ngắn và không trả reasoning cho người dùng. Có thể chọn
`minimal/low/medium/high` qua env nếu model hỗ trợ. Model bắt buộc reasoning có
thể không tắt được. `max_tokens=700` có thể tính cả reasoning trên OpenRouter;
nếu bật reasoning cần tăng ngân sách. Xem
[tài liệu reasoning](https://openrouter.ai/docs/guides/best-practices/reasoning-tokens).
Chất lượng nhập vai, tiếng Việt và độ trễ cần đo live với key của bạn; unit test
mock không chứng minh chất lượng của model.

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

Danh sách 48 mục nhân vật và ID: [CHARACTERS.md](CHARACTERS.md).
Đối chiếu file Word và cách nạp dữ liệu mới: [docs/CHARACTER_EXPANSION.md](docs/CHARACTER_EXPANSION.md).

Lần chạy đầu cần tải model embedding `BAAI/bge-m3`, vì vậy service `ingest` có
thể mất vài phút. Muốn smoke test nhẹ, đặt `EMBEDDING_PROVIDER=hash`; không dùng
hash embedding để kết luận chất lượng production.

Nếu chạy trực tiếp ngoài Docker, cài thêm gói embedding CPU (tách riêng để tránh
vô tình kéo CUDA runtime):

```bash
python -m pip install -r requirements.txt -r requirements-embedding-cpu.txt
```

## Nạp bổ sung nhân vật

Để chỉ nạp nhân vật chưa có trong PostgreSQL, giữ nguyên dữ liệu của các nhân vật
đã tồn tại:

```bash
docker compose run --rm --no-deps ingest python -m scripts.ingest --missing-only
```

Bỏ `--missing-only` nếu muốn cập nhật lại toàn bộ corpus từ file hiện tại.
Sau khi thêm profile hoặc đổi code, rebuild/recreate API để nạp danh sách mới.
Readiness kiểm tra các ID profile trong corpus hiện tại có trong database và mỗi
nhân vật đã đăng ký có ít nhất một chunk; không còn phụ thuộc số lượng cố định.

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
vì vậy STT không tự gọi LLM và không làm tăng `provider_call_count` của chat.

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

## Cập nhật mapping 015–019 (2026-10-07)

Giữ nguyên 001–014. Mapping mới:
`pham_ngoc_thao → 015`, `vu_ngoc_nha → 016`, `dang_tran_duc → 017`,
`pham_xuan_an → 018`, `le_duc_thuy → 019`.
019 là Lê Đức Thúy, nguyên Thống đốc Ngân hàng Nhà nước, theo
[Wikipedia người dùng cung cấp](https://vi.wikipedia.org/wiki/L%C3%AA_%C4%90%E1%BB%A9c_Th%C3%BAy).
Không gán quân hàm Thiếu tướng; không dùng hồ sơ Lê Hữu Thúy cho 019. Lê Hữu Thúy giữ mã 020; Lý Tự Trọng
chuyển sang 048 để không trùng 015. Các mã 021–047 giữ nguyên.
ID API vẫn là slug; mã ba chữ số dùng cho voice/image.

Orchestrator hỗ trợ các biến `<CHARACTER_ID>_VOICE_ID`, `_IMAGE_ID`, `_IMAGE_PATH`
cho năm nhân vật trên, gồm `LE_DUC_THUY_*` cho 019.
Trên SSH, đặt ảnh thật trong LipSync và `voice_data/<id>/ref.txt` cùng audio mẫu
trong TTS theo mapping này. Có thể dùng `<CHARACTER_ID>_IMAGE_HOST_PATH` để mount
ảnh vào orchestrator; kiểm tra `CHARACTER_OVERRIDES_JSON` tránh override cũ.

Sau khi cập nhật source, trong repo LLM chạy:

```bash
docker compose build
docker compose run --rm ingest
docker compose up -d api
```

Phải ingest lại, không dùng `--missing-only`, để cập nhật nhân vật đã có trong DB.
Sau đó trong repo orchestrator:

```bash
docker compose up -d --build orchestrator
curl --fail http://127.0.0.1:8991/api/v1/characters
```
