# Đối chiếu gói nộp

## Phần 1 — Coding

| Yêu cầu | Bằng chứng / trạng thái |
|---|---|
| Tối thiểu 30 bài Markdown sạch | Đã xử lý 416 bài; kiểm thử giữ heading, code block và relative link. Dữ liệu runtime không commit, reviewer có thể chạy scraper để tạo lại. |
| Upload qua Python API | upload/; 416 tài liệu đã được xác nhận STATE_ACTIVE trong evidence/store-verification.json. |
| Tạo trợ lý và chat trong AI Studio | result.png hiển thị câu hỏi YouTube, 5 bước trả lời và Article URL; cấu hình ở playground/. |
| System prompt nguyên văn | playground/system-prompt.txt. |
| Log số file và chunk | Số file được xác nhận; số chunk chỉ có ước tính ghi rõ phương pháp. Số chunk thực tế của Gemini chưa xác minh được, đây là mục chỉ đáp ứng một phần. |
| Docker chạy một lần, exit 0 | evidence/vps-completion-run.json và evidence/vps-daily-last-run.json. |
| Chạy hằng ngày và chỉ upload delta | Cron 02:00 Asia/Ho_Chi_Minh; script deploy/run-daily.sh. Chạy lại bỏ qua đủ 416 bài. |
| README ngắn, ảnh và log | README.md dẫn tới ảnh, snapshot báo cáo và hướng dẫn vận hành. |
| Kiểm thử | evidence/local-tests.txt và evidence/vps-tests.txt. |

Các báo cáo là snapshot có timestamp, không phải trang log trực tiếp. Lịch cron đã cài; bằng chứng kiểm tra hiện tại được tạo bằng cách chạy cùng script thủ công, không giả nhận đã chờ một lượt kích hoạt 02:00.

Cần người nộp xác nhận phần warm-up: đã tự dùng tài khoản trial OptiSigns và chat với OptiBot thật. Công việc đó không được suy ra từ ảnh chatbot tự dựng.

## Phần 2 — Planning

Chưa nằm trong gói này. Đề yêu cầu gửi cả hai phần cùng nhau. Cần trải nghiệm app.optisigns.com thật, chốt phạm vi/đội ngũ/nền tảng, lập thứ tự và ước lượng có lý do; nêu một phát hiện bất ngờ trong sản phẩm và điều nó làm thay đổi kế hoạch. Không điền trải nghiệm giả hoặc ước lượng không thể giải thích khi phỏng vấn.
