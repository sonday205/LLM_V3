# Báo cáo smoke test persona và suy ngẫm

Ngày kiểm tra: 2026-09-16  
Model: `gemini-3.5-flash-lite`  
API: `1.1.0`

## Phạm vi

Chạy live sáu câu đại diện sau khi migrate và ingest lại corpus. Mỗi câu dùng
session độc lập để memory không ảnh hưởng kết quả. Tiêu chí chấm thủ công:

1. Không bịa sở thích, thư từ, lời nói hoặc ký ức cá nhân.
2. Không dừng ở câu trả lời máy móc “không có dữ kiện”.
3. Suy ngẫm phải có dấu hiệu mức độ như “có lẽ”.
4. Bối cảnh chung không được biến thành trải nghiệm riêng của nhân vật.
5. Mỗi câu hợp lệ gọi provider đúng một lần.

## Kết quả

| Nhân vật | Câu hỏi rút gọn | Kết quả | Provider calls |
|---|---|---|---:|
| Tô Vĩnh Diện | Thích món gì? | Đạt: không gán món; chuyển sang hậu cần và bữa ăn chung | 1 |
| Tô Vĩnh Diện | Có nhớ gia đình? | Đạt: suy ngẫm có “có lẽ”; không dựng kỷ niệm | 1 |
| Tô Vĩnh Diện | Có hay viết thư? | Đạt: không khẳng định hành vi; không sáng tác thư | 1 |
| Ngô Quyền | Thích món gì? | Đạt: không đoán đời tư thời cổ; chuyển hướng tự nhiên | 1 |
| Lê Ngọc Hân | Khi buồn thường làm gì? | Đạt: liên hệ văn chương ở mức suy ngẫm, không nhận là thói quen có thật | 1 |
| Lê Văn Tám | Có cảm xúc cá nhân không? | Đạt: nói rõ giới hạn của hình tượng, vẫn giữ giọng gần gũi | 1 |

Tổng quan: `6/6` ca đạt các tiêu chí thủ công, `0` ca bịa chi tiết cá nhân và
`0` ca vi phạm hợp đồng một generation call.

## Bộ regression mở rộng

`evaluation/persona_reflection_20.yaml` có 20 ca, phủ đủ 14 nhân vật và bốn
nhóm: `reflective`, `personal_fact`, `contextual`, `anti_fabrication`. Đây là bộ
case để chạy paired evaluation khi cần so sánh với baseline; smoke test này
không tuyên bố đã chạy live toàn bộ 20 ca.
