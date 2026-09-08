# Historical Character Hybrid RAG API

API độc lập để thử nghiệm chất lượng hội thoại nhân vật lịch sử với:

- 14 nhân vật và corpus có nguồn.
- PostgreSQL + pgvector hybrid RAG, không dùng Neo4j/GraphRAG.
- Memory bền vững, TTL 7 ngày, truy hồi theo gần đây và ngữ nghĩa.
- Hai precheck local: safety và privacy.
- Một request Gemini `gemini-3.5-flash-lite` cho mỗi chat hợp lệ.
- Output Gemini được trả nguyên; storage guard chỉ quyết định có lưu memory.
- FastAPI, OpenAPI 3.1, API-key auth tùy môi trường và frontend demo.

## Chạy bằng Docker

File `.env` local đã được ignore. Để cấu hình mới từ đầu:

```bash
cp .env.example .env
```

Điền `GEMINI_API_KEY`, sau đó chạy:

```bash
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8010/ready
```

Địa chỉ:

- Frontend: http://127.0.0.1:8010
- Swagger: http://127.0.0.1:8010/docs
- ReDoc: http://127.0.0.1:8010/redoc
- OpenAPI JSON: http://127.0.0.1:8010/openapi.json

Danh sách 14 nhân vật và ID: [CHARACTERS.md](CHARACTERS.md).

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
```

Ví dụ:

```bash
curl -X POST http://127.0.0.1:8010/v1/characters/to_vinh_dien/chat \
  -H 'Content-Type: application/json' \
  -d '{
    "session_id": "demo-session-001",
    "message": "Chú sinh năm nào và quê ở đâu?",
    "debug": true
  }'
```

Khi `API_AUTH_ENABLED=true`, thêm header `X-API-Key`. Frontend chỉ giữ key trong
`sessionStorage` của tab hiện tại.

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

Chạy baseline cũ ở port `8005` và project này ở `8010`, rồi:

```bash
python -m scripts.evaluate \
  --old-url http://127.0.0.1:8005 \
  --new-url http://127.0.0.1:8010 \
  --delay-seconds 10

python -m scripts.report_evaluation evaluation/results/paired.jsonl \
  --output evaluation/results/REPORT.md
```

Runner checkpoint từng lượt vào JSONL và dừng an toàn khi gặp lỗi quyền, quota,
HTTP `503` hoặc fallback provider của baseline; chạy lại cùng lệnh sẽ tiếp tục
phần còn thiếu.

Xem thêm [kiến trúc](docs/ARCHITECTURE.md) và [OpenAPI](docs/openapi.yaml).
