# Deploy VPS demo

Runbook này ghi lại cấu hình đang chạy cho demo Zalo AI Service Navigator.

## Mục tiêu và địa chỉ

- Domain: `https://zah-19.123c.vn`
- Swagger: `https://zah-19.123c.vn/docs`
- Readiness: `https://zah-19.123c.vn/health/ready`
- SSH: dùng port `2222`, không phải port mặc định `22`.
- Mã nguồn: branch `data/oa-catalog-research`.

API, PostgreSQL và Redis không mở trực tiếp ra Internet. Nginx là điểm vào HTTPS
duy nhất và proxy API tới `127.0.0.1:8001`.

## Chuẩn bị VPS lần đầu

Đăng nhập SSH bằng user do BTC cấp, rồi cài Docker Engine cùng Compose plugin:

```bash
sudo dnf install -y dnf-plugins-core
sudo dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
sudo dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo systemctl enable --now docker
docker compose version
```

Clone đúng branch vào thư mục cố định:

```bash
sudo git clone --branch data/oa-catalog-research --single-branch \
  https://github.com/bitanut07/thefource-hackathon.git /opt/zalo-service-navigator
sudo chown -R "${USER}:${USER}" /opt/zalo-service-navigator
cd /opt/zalo-service-navigator
```

## Cấu hình production

Tạo `/opt/zalo-service-navigator/.env` trực tiếp trên VPS, không commit file này.
Tối thiểu cần có:

```env
APP_ENV=production
ENABLE_DOCS=true
API_PORT=8001
PUBLIC_BASE_URL=https://zah-19.123c.vn
ALLOWED_LAUNCH_HOSTS=zalo.me
GEMINI_API_KEY=<Gemini key>
NAVIGATOR_API_KEY=<API key mạnh, riêng tư>
STT_PROVIDER=disabled
TTS_PROVIDER=disabled
```

Khóa quyền file:

```bash
chmod 600 .env
```

Không in, gửi chat, commit hoặc thêm vào log các giá trị key/token.

## Nginx

Nginx của VPS đã có wildcard certificate cho `*.123c.vn`. Tạo
`/etc/nginx/conf.d/zah-19-navigator.conf`:

```nginx
server {
    listen 80;
    server_name zah-19.123c.vn;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl http2;
    server_name zah-19.123c.vn;

    ssl_certificate /etc/nginx/certs/123c.vn.pem;
    ssl_certificate_key /etc/nginx/certs/123c.vn.key;
    ssl_dhparam /etc/nginx/certs/dhparams.pem;
    ssl_protocols TLSv1.2 TLSv1.3;

    location / {
        proxy_pass http://127.0.0.1:8001;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

Trên SELinux/Rocky Linux, cho phép Nginx kết nối upstream rồi reload:

```bash
sudo setsebool -P httpd_can_network_connect 1
sudo nginx -t
sudo systemctl reload nginx
```

## Chạy hoặc cập nhật ứng dụng

Lần đầu hoặc sau khi database schema/catalog thay đổi:

```bash
cd /opt/zalo-service-navigator
sudo docker compose up --build --detach
sudo docker compose exec --no-TTY api python scripts/migrate_postgres.py
sudo docker compose exec --no-TTY api python scripts/seed_postgres.py --include-candidates
sudo docker compose ps
```

Catalog hiện có 66 OA active. Lệnh seed là idempotent: có thể chạy lại sau khi
thay manifest duyệt OA.

Cập nhật version thường ngày:

```bash
cd /opt/zalo-service-navigator
sudo git fetch origin data/oa-catalog-research
sudo git reset --hard origin/data/oa-catalog-research
sudo docker compose up --build --detach
```

Nếu chỉ cập nhật data/cấu hình, vẫn chạy seed lại để PostgreSQL nhận catalog mới.

## Kiểm tra

```bash
curl -fsS https://zah-19.123c.vn/health/live
curl -fsS https://zah-19.123c.vn/health/ready
curl -I https://zah-19.123c.vn/docs
sudo docker compose ps
```

Swagger cần `X-API-Key`: dùng giá trị `NAVIGATOR_API_KEY` trong `.env`.
Các endpoint không phải health/docs đều yêu cầu key này.

## Bật STT/TTS theo từng bước

Deploy code lần đầu với `STT_PROVIDER=disabled` và `TTS_PROVIDER=disabled`, rồi
kiểm tra health và Swagger. Khi credential/model Gemini đã được xác nhận, đổi
hai biến tương ứng sang `gemini` trong `.env` và restart:

```bash
cd /opt/zalo-service-navigator
sudo docker compose up --build --detach
```

Smoke test TTS trước, sau đó dùng chính WAV vừa sinh để kiểm tra STT. Nhập API
key ở prompt để không ghi key vào shell history:

```bash
read -rsp "NAVIGATOR_API_KEY: " NAVIGATOR_API_KEY && echo
curl --fail \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"message":"FOne đã sẵn sàng hỗ trợ bạn.","choice_names":["ZaloPay"]}' \
  --output /tmp/fone-response.wav \
  https://zah-19.123c.vn/api/v1/tts
curl --fail \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -H "Content-Type: audio/wav" \
  --data-binary @/tmp/fone-response.wav \
  https://zah-19.123c.vn/api/v1/stt
```

Không lưu file smoke test trong repo. Nếu model Preview chưa được cấp hoặc voice
API lỗi, đặt lại provider tương ứng thành `disabled` rồi chạy lại `docker
compose up --detach`; `/navigate` và health vẫn hoạt động độc lập.

## Rollback

Xem lịch sử và quay về một commit đã biết tốt:

```bash
cd /opt/zalo-service-navigator
sudo git log --oneline -10
sudo git reset --hard <commit_sha>
sudo docker compose up --build --detach
```

Không xóa Docker volume PostgreSQL khi rollback code. Nếu cần rollback catalog,
sửa `data/registry/approved-candidate-ids.json` ở một commit mới rồi chạy
`scripts/seed_postgres.py --include-candidates`.

Riêng STT/TTS có thể rollback tức thời mà không đổi code hoặc database: đặt
`STT_PROVIDER=disabled`, `TTS_PROVIDER=disabled` trong `.env` rồi restart stack.

## Zalo OA webhook

Callback dự kiến là `https://zah-19.123c.vn/webhooks/zalo`, nhưng endpoint hiện
cố ý trả `501` cho tới khi contract webhook, xác thực chữ ký và OA credentials
được triển khai. Không đăng ký callback tại Zalo trước bước đó.
