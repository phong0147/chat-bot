# Sửa lỗi upload ảnh base64 — 2026-10-02

## Lỗi đã tái hiện

Job dừng sau 250 bài. Bài tiếp theo là `8899727608083` (How to use the QR Scan-to-Interact (Touchless QR) app). Kiểm tra trên VPS xác nhận `httpx.ReadTimeout` trong bước SDK upload file, trước khi nhận operation để index. Log cũ che loại lỗi bằng thông báo mạng chung.

Markdown của bài có 134.479 byte, gồm một dòng ảnh `data:image/png;base64,...` dài 125.695 ký tự. Đây là dữ liệu ảnh nhị phân mã hóa, không phải nội dung văn bản để tìm kiếm.

## Thay đổi

- Bộ chuyển HTML thay ảnh nhúng data URI bằng chú thích (giữ alt/title nếu có) và chỉ người đọc về bài gốc. Link ảnh thông thường, relative link, nội dung hướng dẫn và code block vẫn được giữ.
- File của bài trên còn 8.836 byte. Upload lại chính bài đó thành công, có document đã index.
- Log upload ghi ID và kích thước bài trước khi gửi; báo cáo lỗi ghi `failed_article_id` và loại lỗi như `ReadTimeout`, không ghi key hay request.
- 33 test đạt trên local và trong Docker trên VPS, gồm các test ảnh base64, ảnh chỉ có hình, bảo toàn link và lỗi timeout không lộ key.

Bằng chứng thử riêng bài lỗi: [base64-regression.json](../evidence/base64-regression.json). Kết quả chạy lại toàn bộ job đã lưu trong `evidence/vps-daily-last-run.json`; đây là snapshot, không phải log trực tiếp.

## Lỗi HTTP 503 trong lần đồng bộ tiếp theo

Sau khi vượt qua bài base64, Gemini trả HTTP 503 ở bài `14502378549907`. Đã bổ sung phân loại lỗi tạm thời, retry có giới hạn và đối chiếu kho trước khi gửi lại. Kiểm thử bao gồm mất phản hồi sau khi server nhận file, lỗi xác thực không retry, timeout hết số lượt và lỗi cleanup vẫn đếm đúng số file cập nhật.

Các tài liệu đã active và trùng hash trong danh sách mới lấy không cần thêm một GET riêng. Bản kiểm thử cuối có 33 test đạt trên local và trong Docker; xem `evidence/vps-tests.txt`.

## Kết quả cuối đã kiểm chứng trên VPS

- Lần hoàn tất: thêm 150 bài còn thiếu, bỏ qua 266 bài; status success, exit 0.
- Chạy lại trên image cuối cùng: thêm 0, cập nhật 0, bỏ qua 416; status success, exit 0.
- Đọc trực tiếp Gemini: 416/416 tài liệu STATE_ACTIVE, hash và URL nguồn đúng; không có ID bài trùng, không còn operation chờ.
- Cron vẫn active: 02:00 mỗi ngày, Asia/Ho_Chi_Minh. Các container website/database hiện có vẫn chạy.
- Bằng chứng: `evidence/vps-completion-run.json`, `evidence/vps-daily-last-run.json`, `evidence/store-verification.json`, `evidence/vps-tests.txt`.
