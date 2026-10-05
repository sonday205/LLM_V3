# Bổ sung nhân vật theo danh sách Word

Nguồn yêu cầu: `Làm các dữ liệu nhân vật lịch sử.docx`, đối chiếu ngày 05/10/2026.

Danh sách Word có 44 mục. Corpus trước đó có 14 mục, gồm 11 mục trong Word và
3 mục ngoài Word (Nguyễn Văn Trỗi, Lê Hồng Phong, Nguyễn Bỉnh Khiêm). Bổ sung
33 mục còn thiếu, giữ nguyên 14 ID và thứ tự ban đầu, tổng cộng 47 mục.
Xem [danh sách và ID](../CHARACTERS.md); manifest đối chiếu nằm tại
`data/docx_character_manifest.yaml`.

## Dữ liệu tái sử dụng

Tiểu sử được tái sử dụng từ `STT_LLM_V1/data/characters`, không cần gọi LLM để
sinh lại. Mỗi mục mới gồm `profile.yaml` và `biography.md` với nguồn dẫn.
Các trường `expression` của bản thử nghiệm được chuyển sang `core_values`,
`personality_traits`, `conversation_style` và `reflection_boundaries` theo
schema của Historical RAG API. Loader/ingest hiện có tự phát hiện các mục mới;
không thêm nhánh xử lý riêng trong code cho từng nhân vật.

Không sao chép README hoặc câu hỏi evaluation vào corpus retrieval. 165 câu
hỏi đánh giá được đặt riêng tại `evaluation/docx_expansion_165.yaml`. Đây là
fixture, chưa phải kết quả đánh giá câu trả lời LLM.

## Danh tính và độ chắc chắn

- Mục “Thiếu tướng Lê Đức Thúy — Điệp viên giữa sa mạc lửa” được đối chiếu thành
  Đại tá Lê Hữu Thúy, bút danh Nhị Hồ, theo
  [Báo Quân đội nhân dân](https://ct.qdnd.vn/van-hoa-xa-hoi/pham-gia-4-dac-biet-530938).
- Quang Trung giữ ID `quang_trung_nguyen_hue`; không tạo mục trùng `quang_trung`.
- Hùng Vương là danh xưng nhiều đời vua; Hai Bà Trưng gồm hai chị em, giữ một
  mục chung theo cách nhóm trong Word.
- Trần Thị Dung giữ danh hiệu Linh Từ quốc mẫu theo nguồn, không tự gán danh
  hiệu từ bản Word. Thần tích, tiểu thuyết, truyền thuyết và các chi tiết còn
  tranh luận được đánh dấu ngay trong dữ liệu retrieval.

Tiểu sử mới là dữ liệu nền ngắn, phần lớn dùng nguồn tổng hợp Wikipedia với
`confidence: medium`; không nâng thành tư liệu gốc hoặc coi là tiểu sử đầy đủ.
Nguồn đã được ghi trong bản thử nghiệm; lần chuyển này không tái xác minh toàn
bộ nguồn trực tuyến. Độ phủ đủ nhân vật không đồng nghĩa đủ mọi chi tiết đời tư.

## Nạp dữ liệu để API phục vụ nhân vật mới

API đọc danh sách từ PostgreSQL, nên cần ingest sau khi bổ sung file.
Tại thư mục repo trên server:

```bash
docker compose build
docker compose run --rm ingest
docker compose up -d api
curl --fail http://127.0.0.1:8005/v1/characters
```

Nếu bật API auth, gửi thêm `X-API-Key` khi kiểm tra danh sách.
Ingest dùng embedding provider đang cấu hình; giữ nguyên BGE-M3 khi cập nhật
database đã có dữ liệu BGE-M3, tránh trộn vector của các provider khác nhau.

Các nhân vật mới chưa tự có giọng TTS/ảnh LipSync: orchestrator có registry
media riêng, cần cấu hình riêng khi đưa các nhân vật này vào sản phẩm có avatar.
