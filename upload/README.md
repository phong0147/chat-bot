# Upload Gemini File Search

## Trách nhiệm từng file

- `config.py`: đọc `.env` và kiểm tra cấu hình. API key không có trong repr/log.
- `client.py`: tạo/dùng lại store, upload, chờ index và xóa phiên bản cũ. Các lỗi SDK được rút gọn để không lộ chi tiết request.
- `state.py`: ghi JSON qua file tạm rồi thay thế; trạng thái độc lập với scrape.
- `pipeline.py`: đọc manifest, đối chiếu hash, tiếp tục operation đang chờ, thay phiên bản và báo cáo.

## Cách chạy

Từ thư mục project: `.venv/Scripts/python.exe main.py --mode upload`. Dùng `--upload-limit 1` để thử một bài đầu tiên; bỏ tùy chọn để kiểm tra tất cả bài đã lưu. `--mode sync` thực hiện scrape trước rồi upload.

`.env.sample` chỉ chứa tên biến. Key thật được đọc từ `.env` hoặc biến môi trường `GEMINI_API_KEY`. `GEMINI_FILE_SEARCH_STORE` có thể để trống: code tạo store, lưu tên trong `data/upload-state.json`, dùng lại ở lần sau. Nếu tên cấu hình khác tên đã lưu, chương trình dừng để tránh trộn trạng thái hai kho.

## Tại sao phải lưu trạng thái riêng?

Scrape thành công không có nghĩa là upload thành công. Uploader so sánh hash của tất cả bài trong manifest với `uploaded_hash`, không dựa vào `changed_files` của scrape. Chỉ ghi `uploaded_hash` sau khi document ở trạng thái `STATE_ACTIVE`. Mỗi operation đang chờ được lưu để có thể tiếp tục sau timeout.

Metadata trên Gemini chứa owner riêng của project dữ liệu, ID bài, hash và URL. Nếu mất kết nối sau khi server nhận file nhưng trước khi lưu operation, lần chạy sau dò tài liệu có metadata trùng để tiếp tục. Việc này giảm bản trùng; API và file cục bộ không tạo thành một giao dịch nguyên tử nên không cam kết exactly-once khi dịch vụ trả danh sách chậm. Bản trùng cùng owner/ID được dọn sau khi đã có một bản mới active. Không xóa tài liệu của nguồn khác.

Bản cũ chỉ bị xóa sau khi bản mới được index và lưu thành công. Trong khoảng thay thế có thể đồng thời tồn tại hai phiên bản. Nếu cleanup lỗi, lần sau dọn lại. Nếu operation lỗi xử lý, giữ hash cũ để lần sau thử lại. File bị sửa tay hoặc hash không khớp manifest sẽ bị từ chối; chạy scrape trước để khôi phục.

## Chia đoạn và báo cáo

Dùng cấu hình `white_space_config`: tối đa 512 token/chunk, overlap 64. Ở API này token của bộ chia đoạn được tính theo khoảng trắng; overlap giữ ngữ cảnh giữa hai đoạn. Gemini thực hiện embedding và indexing.

`upload-last-run.json` có `added`, `updated`, `skipped`, `failed`, `files_embedded` và cấu hình chia đoạn. `files_embedded` là số file đã xác nhận active mới/cập nhật trong lần chạy, có thể gồm operation được tiếp tục từ lần trước. `embedded_chunks` để `null`: [Document API](https://ai.google.dev/api/file-search/documents) không cung cấp số chunk thực tế. Đây là giới hạn cần ghi rõ nếu đối chiếu yêu cầu đếm chunk trong đề; chưa thể khẳng định đã đáp ứng mục đó.

## Giới hạn

Giữ cả thư mục `data/` khi chuyển lên VPS. Không tự xóa bài bị xóa ở website; quota/billing hết sẽ báo lỗi để xử lý rồi chạy lại. Cron đã triển khai trên VPS lúc 02:00 Asia/Ho_Chi_Minh; hướng dẫn hỏi đáp có trong playground/README.md. Khi hỏi Gemini, cần gắn File Search đúng store và system prompt của đề.

## Thử lại khi dịch vụ tạm thời lỗi

HTTP 408/429/500/502/503/504 và lỗi transport/timeout được phân loại là lỗi tạm thời. Mỗi bài được thử tối đa 3 lượt; trước lượt tiếp theo, uploader đọc lại danh sách tài liệu của chính owner và khôi phục operation đang chờ. Không gọi lại upload một cách mù quáng khi server có thể đã nhận file.

Các request chỉ đọc được thử tối đa 3 lần. Tài liệu có hash trùng và STATE_ACTIVE trong danh sách mới lấy được bỏ qua, không cần GET riêng từng tài liệu. Lỗi xác thực hoặc lỗi nội dung không được retry vô hạn; hết số lượt thì job thoát 1 và giữ trạng thái để lần sau tiếp tục.

Báo cáo có `retries` (số lượt thử lại ở mức bài viết), `failed_article_id` khi lỗi, và loại lỗi như `ReadTimeout`. Những lần retry request chỉ đọc được ghi riêng trong log. Log không ghi API key hay toàn bộ request.

## Chunk-count estimate

Run `python -m upload.chunk_report --output data --report evidence/chunk-report.json` to audit the saved manifest without uploading. With N whitespace-separated tokens in raw Markdown, the estimate is 0 for empty input, otherwise `1 + ceil(max(0, N - 512) / 448)`. It includes repeated overlap.

`estimated_chunks_embedded` counts estimates only for files newly confirmed during that run; unchanged files contribute zero. `embedded_chunks` remains null. Google may parse Markdown and split differently, so neither field is presented as a verified internal chunk count. The assignment's actual chunk-count requirement remains partially fulfilled.

Official references: https://ai.google.dev/api/file-search/documents and https://ai.google.dev/gemini-api/docs/file-search#chunking-configuration .
