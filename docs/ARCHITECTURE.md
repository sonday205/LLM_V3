# Kiến trúc Historical Character Hybrid RAG API

## Luồng chat

```text
HTTP request
  -> API-key scope
  -> SafetyPrecheck (local)
  -> PrivacyPrecheck (local)
  -> SafeMemoryService: facts + 6 recent turns + 4 relevant old messages
  -> RetrievalPolicy: bỏ qua lịch sử cho lượt thuần memory/hội thoại
  -> HybridRetriever: exact pgvector + PostgreSQL full-text + RRF
  -> PromptBuilder: persona data + evidence scope + answer-mode contract
  -> Gemini 3.5 Flash-Lite (one request, no retry)
  -> raw answer returned to client
  -> StorageGuard only decides whether the turn is persisted
```

Không có LLM router, post-safety, fact-check, reviewer, repair hoặc LLM memory
summary. Embedding BGE-M3 chạy cục bộ bằng Transformer + CLS pooling +
L2-normalize nên không được tính là provider call.

## Ranh giới an toàn

Hai precheck có quyền trả câu trả lời cục bộ và dừng trước Gemini. Output của
Gemini không bị sửa. Storage guard chạy sau generation nhưng chỉ tác động tới
việc ghi memory, không tác động response.

Memory được phân vùng theo `client_scope + character_id + session_id`. Khi auth
bật, `client_scope` là hash một chiều rút gọn của API key; raw key không được lưu.
Session hết hạn sau 7 ngày không hoạt động và có thể xóa ngay qua API.

## RAG

Corpus giữ frontmatter nguồn. Retrieval luôn filter `character_id` trước khi
xếp hạng. Semantic top-k và lexical top-k được hợp nhất bằng Reciprocal Rank
Fusion, tối đa hai chunk mỗi tài liệu để tăng độ đa dạng nguồn.

Mỗi tài liệu có `evidence_scope`:

- `character`: tư liệu gắn trực tiếp với nhân vật.
- `contextual`: bối cảnh chung của thời đại; không được dùng để suy ra sở thích,
  hành vi hoặc ký ức riêng của nhân vật.

Prompt dùng chung cho mọi nhân vật và tự chọn thầm một trong ba cách diễn đạt:
`DỮ KIỆN CỤ THỂ`, `SUY NGẪM CÓ GIỚI HẠN` hoặc `BỐI CẢNH THỜI ĐẠI`. Việc chọn
cách diễn đạt nằm trong cùng generation call, không có router LLM thứ hai.

Persona không hard-code trong Python. Các trường `core_values`,
`personality_traits`, `conversation_style` và `reflection_boundaries` được đọc
từ `data/characters/<character_id>/profile.yaml`, lưu vào PostgreSQL và đưa vào
prompt. Nhân vật mới chỉ cần profile và corpus hợp lệ, không cần thêm nhánh code.

HTML crawl nằm trong `.runtime/crawl` và không được ingest tự động. Người biên
tập phải diễn giải factual notes, giữ URL/checksum và đánh dấu xung đột nguồn.
