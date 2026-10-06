# OpenRouter: 20 request so sánh DeepSeek V3.2 và GPT-6 Luna — 2026-10-07

## Cấu hình và phương pháp

Đã thay hai vị trí đầu trong `.env` local và recreate API. Không thay business logic, prompt, SDK hoặc thư viện. API chính cổng 8005 có thứ tự:

```dotenv
OPENROUTER_MODELS=deepseek/deepseek-v3.2,openai/gpt-6-luna,qwen/qwen3.8-27b:free
```

Model thứ ba được giữ theo `.env` người dùng đang cấu hình, nhưng **không tìm thấy `qwen/qwen3.8-27b:free` trong catalog tại lần kiểm tra này**. Vì vậy không coi vị trí thứ ba là fallback hợp lệ đã kiểm chứng; nên chọn ID có trong catalog trước deployment. Hai model đầu đều có trong catalog.

[DeepSeek V3.2](https://openrouter.ai/deepseek/deepseek-v3.2), [GPT-6 Luna](https://openrouter.ai/openai/gpt-6-luna), [catalog](https://openrouter.ai/api/v1/models). Hai model đầu là model trả phí; key được đọc từ `.env`, không ghi vào báo cáo.

- Cùng 10 câu hỏi, mỗi câu chạy một lần với DeepSeek ưu tiên và một lần với GPT ưu tiên: tổng đúng 20 POST chat/20 generation HTTP call từ ứng dụng, không phải 20 câu hỏi độc lập.
- DeepSeek group: API chính cổng 8005, model order như trên.
- GPT group: API test riêng cổng 8007, thứ tự GPT-6 Luna → DeepSeek V3.2 → model thứ ba cũ.
- Mỗi request vẫn gửi ordered `models` array và dùng native fallback. Không ép một model duy nhất hoặc retry thủ công.
- Đảo thứ tự thực hiện mỗi cặp theo câu hỏi để giảm thiên lệch thời điểm. Test tuần tự, nghỉ 1 giây giữa request.
- Cả hai dùng cùng database PostgreSQL/pgvector: 47 nhân vật, 128 tài liệu, 556 chunk; BGE-M3 CPU; reasoning tắt; max_tokens 700; timeout cấu hình 30 giây.
- Wall time là latency HTTP gồm precheck, memory, retrieval, generation và lưu memory; không phải TTFT vì chat không streaming.
- Session riêng từng câu; riêng Q05/Q06 dùng chung session theo nhóm để kiểm tra memory. User data tổng hợp, không dùng dữ liệu cá nhân thật.
- Các request đầu của hai API có thể chịu cold embedding/connection. Test không đo tải đồng thời, production SLA hoặc chất lượng trên toàn bộ corpus.

## Kết quả

- HTTP 200: **20/20**. Tất cả provider_call_count=1 và degraded=false.
- Served model: **DeepSeek V3.2: 3 lượt; GPT-6 Luna: 17 lượt**.
- Trong 10 lượt ưu tiên DeepSeek, 3 served DeepSeek và 7 native fallback sang GPT. Trong 10 lượt ưu tiên GPT, cả 10 served GPT.
- Response hiện tại không cung cấp nguyên nhân thất bại từng model trong chuỗi; không thể quy 7 lần fallback này cho quota/overload/auth khi chưa có thông tin upstream.
- Không có lượt phục vụ bởi Qwen.

| Nhóm cấu hình | Request thành công | Mean wall (s) | Median wall (s) | Min–max (s) |
|---|---:|---:|---:|---:|
| deepseek-primary | 10/10 | 5.067 | 2.925 | 2.006–17.144 |
| gpt-luna-primary | 10/10 | 2.821 | 2.843 | 2.157–3.954 |

Bảng nhóm cấu hình DeepSeek bao gồm 7 kết quả do GPT trả, không phải tốc độ riêng của DeepSeek.

| Model thực sự phục vụ | Số mẫu | Mean wall (s) | Median wall (s) | Min–max wall (s) | Mean LLM (s) |
|---|---:|---:|---:|---:|---:|
| deepseek/deepseek-v3.2 | 3 | 10.925 | 8.751 | 6.879–17.144 | 9.934 |
| openai/gpt-6-luna | 17 | 2.713 | 2.789 | 2.006–3.954 | 2.145 |

Trung bình toàn bộ 20 request: 3.944s. Mẫu DeepSeek chỉ có 3 request và thuộc các câu hỏi khác nhau, nên chưa đủ để kết luận tốc độ tổng quát của model. Trong lượt test này, các response served GPT nhanh hơn và ít dao động hơn.

## Nhận xét nội dung

- Q01: cả hai nêu 1924 và địa danh theo corpus; GPT diễn đạt địa danh hiện nay thận trọng hơn bằng “thường được ghi”. Chưa xác minh độc lập địa giới hành chính mới.
- Q02: hai response đều do GPT trả, nêu ngày 1/2/1954 và hoàn cảnh kéo pháo. Không coi đây là đối chiếu chất lượng DeepSeek với GPT.
- Q03: cả hai response đều do GPT trả. Không bịa món yêu thích hoặc suy ra bữa ăn riêng từ tư liệu hậu cần chung như lượt free trước. Response nhóm GPT có thêm một ý chung về nhu cầu ăn uống của trẻ em, hơi lệch trọng tâm.
- Q04: lời khuyên cụ thể (chia nhỏ bài, nhờ giúp, nghỉ ngắn), không tự chèn tiểu sử hoặc giả ký ức. Cả hai do GPT trả.
- Q05/Q06: cả hai nhóm lưu và gọi lại đúng tên Minh Anh/lớp 8; Q06 memory_used=true. Các lượt này đều do GPT trả.
- Q07: DeepSeek và GPT đều giữ hai mốc 1933/1935. GPT giải thích sự khác nhau giữa nguồn rõ hơn; DeepSeek chuyển sang ý “điều quan trọng nhất không phải con số”, nên kém sát yêu cầu giải thích nguồn.
- Q08: cả hai response do GPT trả, giải thích ý nghĩa độc lập/tự chủ và chuẩn bị/mưu lược, không dùng yếu tố thần kỳ.
- Q09: DeepSeek và GPT đều giới thiệu Lê Hữu Thúy gắn với A.22, phù hợp profile/corpus; GPT ngắn gọn hơn.
- Q10: cả hai do GPT trả, phân biệt truyền thuyết nỏ thần với dữ kiện có thể xác nhận.
- Review nội dung là kiểm tra thủ công theo corpus/prompt của các case này, không phải điểm accuracy chung hoặc xác minh mọi sự kiện lịch sử từ nguồn ngoài.

## Từng request

| Câu | Primary | Served model | HTTP | Wall (s) | LLM (s) | Sources | Memory used |
|---|---|---|---:|---:|---:|---:|---|
| Q01 | deepseek-primary | deepseek/deepseek-v3.2 | 200 | 8.751 | 6.926 | 6 | False |
| Q01 | gpt-luna-primary | openai/gpt-6-luna | 200 | 3.144 | 2.541 | 6 | False |
| Q02 | gpt-luna-primary | openai/gpt-6-luna | 200 | 3.044 | 2.290 | 6 | False |
| Q02 | deepseek-primary | openai/gpt-6-luna | 200 | 2.687 | 1.902 | 6 | False |
| Q03 | deepseek-primary | openai/gpt-6-luna | 200 | 2.255 | 1.638 | 6 | False |
| Q03 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.679 | 1.976 | 6 | False |
| Q04 | gpt-luna-primary | openai/gpt-6-luna | 200 | 3.954 | 3.237 | 0 | False |
| Q04 | deepseek-primary | openai/gpt-6-luna | 200 | 3.033 | 2.371 | 0 | False |
| Q05 | deepseek-primary | openai/gpt-6-luna | 200 | 2.050 | 1.728 | 0 | False |
| Q05 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.395 | 2.179 | 0 | False |
| Q06 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.220 | 1.800 | 0 | True |
| Q06 | deepseek-primary | openai/gpt-6-luna | 200 | 2.006 | 1.630 | 0 | True |
| Q07 | deepseek-primary | deepseek/deepseek-v3.2 | 200 | 17.144 | 16.593 | 6 | False |
| Q07 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.935 | 2.351 | 6 | False |
| Q08 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.789 | 2.132 | 6 | False |
| Q08 | deepseek-primary | openai/gpt-6-luna | 200 | 3.050 | 2.257 | 6 | False |
| Q09 | deepseek-primary | deepseek/deepseek-v3.2 | 200 | 6.879 | 6.283 | 2 | False |
| Q09 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.157 | 1.803 | 2 | False |
| Q10 | gpt-luna-primary | openai/gpt-6-luna | 200 | 2.897 | 2.307 | 2 | False |
| Q10 | deepseek-primary | openai/gpt-6-luna | 200 | 2.818 | 2.317 | 2 | False |

## Toàn bộ câu trả lời

### Q01: Chú sinh năm nào và quê ở đâu?

**deepseek-primary — served deepseek/deepseek-v3.2 — 8.751s**

Chú sinh năm 1924, quê ở thôn Dược Khê, xã Nông Trường, huyện Nông Cống, tỉnh Thanh Hóa. Bây giờ địa danh ấy thuộc huyện Triệu Sơn, tỉnh Thanh Hóa đó cháu.

**gpt-luna-primary — served openai/gpt-6-luna — 3.144s**

Chú Tô Vĩnh Diện sinh năm 1924, quê ở thôn Dược Khê, xã Nông Trường, huyện Nông Cống, tỉnh Thanh Hóa. Địa danh này hiện nay thường được ghi thuộc huyện Triệu Sơn, tỉnh Thanh Hóa.

### Q02: Chú hy sinh ngày nào, trong hoàn cảnh nào?

**deepseek-primary — served openai/gpt-6-luna — 2.687s**

Chú hy sinh ngày 1 tháng 2 năm 1954, khi cùng đồng đội kéo pháo ra ở Điện Biên Phủ. Trên một đoạn dốc trơn và nguy hiểm, dây tời bị đứt khiến khẩu pháo lao xuống; chú đã lấy thân mình chèn bánh để bảo vệ pháo, rồi hy sinh.

**gpt-luna-primary — served openai/gpt-6-luna — 3.044s**

Chú hy sinh ngày 1 tháng 2 năm 1954, khi cùng đồng đội kéo pháo ra ở Điện Biên Phủ. Trên một đoạn dốc trơn, nguy hiểm, dây tời đứt khiến khẩu pháo lao xuống; chú đã lấy thân mình chèn bánh để bảo vệ pháo.

### Q03: Chú thích ăn món gì nhất khi còn nhỏ?

**deepseek-primary — served openai/gpt-6-luna — 2.255s**

Những tư liệu còn lại không cho biết chú thích ăn món gì nhất khi còn nhỏ, nên chú không thể khẳng định. Điều đáng nhớ hơn là dù tuổi thơ khó khăn, chú Tô Vĩnh Diện vẫn nỗ lực và sống có trách nhiệm.

**gpt-luna-primary — served openai/gpt-6-luna — 2.679s**

Những tư liệu hiện có không cho biết hồi nhỏ chú thích ăn món gì nhất, nên chú không thể khẳng định. Điều đáng nhớ hơn là chú sinh ra trong hoàn cảnh khó khăn; dù vậy, trẻ em khi ấy vẫn cần được ăn uống đủ đầy để lớn lên khỏe mạnh.

### Q04: Cháu học lớp 8, gần đây học khó quá nên muốn bỏ cuộc. Chú khuyên cháu thế nào?

**deepseek-primary — served openai/gpt-6-luna — 3.033s**

Cháu đừng vội kết luận rằng mình không thể học được; gặp bài khó là chuyện nhiều bạn trải qua. Hãy chia việc học thành từng phần nhỏ, chọn một việc cần làm trước, rồi hỏi thầy cô, bạn bè hoặc người thân khi chưa hiểu. Nghỉ ngắn để lấy lại sức cũng được—bền bỉ không có nghĩa là phải tự mình gánh hết.

**gpt-luna-primary — served openai/gpt-6-luna — 3.954s**

Cháu đừng vội bỏ cuộc; gặp bài khó không có nghĩa là cháu không học được, mà có thể cháu cần thêm thời gian hoặc một cách học khác. Hãy chọn một phần nhỏ để làm trước, nghỉ ngắn khi mệt, rồi nhờ thầy cô, cha mẹ hoặc bạn bè giải thích chỗ chưa hiểu. Chú nghĩ bền bỉ không phải là cố chịu một mình—biết tìm người giúp cũng là một cách có trách nhiệm với việc học của mình.

### Q05: Cháu tên Minh Anh, đang học lớp 8. Chú nhớ tên cháu nhé.

**deepseek-primary — served openai/gpt-6-luna — 2.050s**

Chú sẽ gọi cháu là Minh Anh trong cuộc trò chuyện này nhé.

**gpt-luna-primary — served openai/gpt-6-luna — 2.395s**

Chú sẽ nhớ trong cuộc trò chuyện này: cháu tên Minh Anh và đang học lớp 8.

### Q06: Cháu vừa nói tên cháu là gì, học lớp mấy?

**deepseek-primary — served openai/gpt-6-luna — 2.006s**

Cháu tên Minh Anh, học lớp 8.

**gpt-luna-primary — served openai/gpt-6-luna — 2.220s**

Cháu tên Minh Anh, đang học lớp 8.

### Q07: Chị sinh năm bao nhiêu? Nếu các nguồn ghi khác nhau thì chị giải thích giúp cháu.

**deepseek-primary — served deepseek/deepseek-v3.2 — 17.144s**

Theo nhiều tư liệu chính thống hiện nay thì chị sinh năm 1933, em ạ. Nhưng cũng có tài liệu ghi năm 1935. Sự khác nhau này là do lịch sử để lại. Điều quan trọng nhất không phải là con số cụ thể, mà là chị đã tham gia kháng chiến và hy sinh khi tuổi đời còn rất trẻ.

**gpt-luna-primary — served openai/gpt-6-luna — 2.935s**

Nhiều nguồn chính thống ghi chị sinh năm 1933, nhưng Bảo tàng Lịch sử Quốc gia cũng lưu ý có tài liệu ghi năm 1935. Vì vậy, năm sinh của chị chưa được các nguồn ghi thống nhất; khi cần nói thận trọng, em có thể nêu cả hai mốc và cho biết 1933 là mốc được nhiều nguồn chính thống hiện nay sử dụng.

### Q08: Vì sao chiến thắng Bạch Đằng năm 938 có ý nghĩa quan trọng?

**deepseek-primary — served openai/gpt-6-luna — 3.050s**

Chiến thắng Bạch Đằng năm 938 đã đánh bại cuộc xâm lược của quân Nam Hán, ngăn họ tái chiếm nước ta. Nhờ đó, chiến thắng mở ra thời kỳ độc lập, tự chủ lâu dài; sau đó, ta xưng vương, chọn Cổ Loa làm kinh đô và xây dựng chính quyền tự chủ. Đây là kết quả của sự chuẩn bị và mưu lược, chứ không phải do phép màu.

**gpt-luna-primary — served openai/gpt-6-luna — 2.789s**

Chiến thắng Bạch Đằng năm 938 đánh bại cuộc xâm lược của quân Nam Hán, ngăn họ áp đặt lại ách cai trị. Chiến thắng ấy mở ra thời kỳ đất nước độc lập, tự chủ lâu dài; sau đó, Ngô Quyền xưng vương và chọn Cổ Loa làm kinh đô. Điều đáng nhớ là thắng lợi không chỉ nhờ địa thế, mà còn nhờ sự chuẩn bị và mưu lược của quân dân ta.

### Q09: Ông Lê Hữu Thúy là ai?

**deepseek-primary — served deepseek/deepseek-v3.2 — 6.879s**

Ông Lê Hữu Thúy là nhà tình báo chiến lược của Việt Nam, và công việc của ông gắn liền với cụm tình báo có tên mã là A.22 đó, cháu à.

**gpt-luna-primary — served openai/gpt-6-luna — 2.157s**

Ông Lê Hữu Thúy là một nhà tình báo chiến lược Việt Nam, gắn với cụm tình báo A.22.

### Q10: Câu chuyện nỏ thần là sự thật lịch sử hay truyền thuyết?

**deepseek-primary — served openai/gpt-6-luna — 2.818s**

Câu chuyện nỏ thần được xem là truyền thuyết có yếu tố giải thích lịch sử, chứ không phải sự kiện đã được xác nhận đầy đủ. Vì vậy, cháu nên phân biệt câu chuyện ấy với những điều có tư liệu lịch sử xác nhận về nước Âu Lạc và thành Cổ Loa.

**gpt-luna-primary — served openai/gpt-6-luna — 2.897s**

Câu chuyện nỏ thần được xem là truyền thuyết có yếu tố giải thích lịch sử, chứ không thể khẳng định mọi chi tiết là sự thật đã được kiểm chứng. Ông gắn với thành Cổ Loa, còn chuyện nỏ thần, Mỵ Châu và Trọng Thủy cần được phân biệt với tư liệu lịch sử.

## Validation và trạng thái

- Existing automated tests: 79 passed; warning Starlette/httpx có sẵn.
- `ruff check app tests scripts`: pass; `git diff --check`: pass. Không sửa code AI nên không cần rebuild image cho việc đổi env.
- `.env` được Git ignore; key không xuất hiện trong source hoặc report/log đã kiểm tra.
- Đã xóa các session test; container GPT comparison sẽ được dừng và dọn. API chính cổng 8005 giữ DeepSeek → GPT theo yêu cầu.
- Không commit/push/deploy server công ty. `.env` không đi theo Git, cần cấu hình model/key riêng trên server.
- Raw responses: `.runtime/openrouter-20-20261007/results.jsonl`; catalog snapshot: `models.json`, đều nằm trong thư mục Git ignore.
