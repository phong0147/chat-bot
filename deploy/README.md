# Chạy job trên VPS

Project nằm tại `/opt/script-chat-bot`. Docker chạy một lần rồi thoát; cron gọi lại lúc **02:00 hằng ngày, Asia/Ho_Chi_Minh**. Job chỉ cần kết nối Internet ra ngoài.

## Các file

- `run-daily.sh`: khóa bằng `flock`, chạy Docker, ghi log và báo cáo chung. Giới hạn container: 1 CPU, 512 MB RAM.
- `helpcenter-ingest.cron`: lịch trong `/etc/cron.d/helpcenter-ingest`.
- `helpcenter-ingest.logrotate`: xoay log, giữ 14 bản; cài tại `/etc/logrotate.d/helpcenter-ingest`.
- `/opt/script-chat-bot/.env`: key Gemini; quyền `600`, không nằm trong image hay Git.
- `/opt/script-chat-bot/data`: volume giữ Markdown và trạng thái upload. Sao lưu cả thư mục này để tiếp tục dùng đúng kho.

## Xem kết quả trên VPS

```bash
cat /opt/script-chat-bot/data/daily-last-run.json
tail -n 50 /opt/script-chat-bot/logs/daily.log
cat /etc/cron.d/helpcenter-ingest
```

`status: success` và `exit_code: 0` nghĩa là lần chạy đã hoàn tất. `scrape` là bước lấy bài; `upload` là bước gửi phần thay đổi. Nếu một bước chưa chạy trong lần đó, báo cáo ghi `null`, không lấy nhầm báo cáo cũ. Trường `embedded_chunks` chưa có số thực tế vì API Gemini Document không cung cấp số chunk.

## Chạy ngay hoặc cập nhật code

```bash
cd /opt/script-chat-bot
# Chạy ngay, cùng cách cron sẽ gọi:
./deploy/run-daily.sh
# Sau khi chuyển code mới lên VPS, build lại:
docker build -t helpcenter-ingest:latest .
```

Script ghi vào `logs/daily.log`, vì vậy terminal có thể không hiển thị tiến độ. Xem ở cửa sổ SSH khác bằng `tail -f /opt/script-chat-bot/logs/daily.log`. Khi thành công container tự xóa; không thấy trong `docker ps` giữa hai lần chạy là bình thường.

## Cài lại lịch trên một VPS đã có project

```bash
cd /opt/script-chat-bot
chmod 600 .env
chmod 750 deploy/run-daily.sh
# Kiểm tra timezone của VPS trước khi cài lịch:
timedatectl show -p Timezone --value
sudo install -o root -g root -m 644 deploy/helpcenter-ingest.cron /etc/cron.d/helpcenter-ingest
sudo install -o root -g root -m 644 deploy/helpcenter-ingest.logrotate /etc/logrotate.d/helpcenter-ingest
```

Cron sử dụng timezone của hệ điều hành. Cấu hình hiện tại dành cho VPS ở `Asia/Ho_Chi_Minh`.

## Khi gặp lỗi

- Key mới vẫn thuộc cùng Google project: cập nhật `.env`, chạy lại job.
- Đổi Google project: cần kho/trạng thái upload riêng; không trỏ key mới vào kho của project cũ.
- Lỗi mạng hoặc quota: xem log, xử lý nguyên nhân rồi chạy lại. Upload tiếp tục từ trạng thái đã lưu, không có vòng retry vô hạn.
- Nếu máy/container bị tắt đột ngột và còn `data/.scrape.lock`: kiểm tra `docker ps` và tiến trình job trước khi xử lý khóa cũ.
- Chỉ vận hành lịch tự động trên VPS này; tránh chạy đồng thời một bản local dùng cùng kho. Khóa chỉ bảo vệ các job cùng máy/volume.

Báo cáo trong `evidence/` là bản chụp kết quả, không tự cập nhật từ VPS. Có thể tải bản mới bằng SCP; không đưa `.env`, private key hoặc toàn bộ Docker inspect vào evidence.
