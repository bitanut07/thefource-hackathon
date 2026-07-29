# Chạy toàn bộ hệ thống ở local

Ba thành phần: backend (repo này), review console
([FOne-Admin](https://github.com/Keruedu/FOne-Admin)) và landing page
([FOne-Frontend](https://github.com/Keruedu/FOne-Frontend)).

| Thành phần | Cách chạy local | Cổng |
| --- | --- | --- |
| Backend + worker + Redis + PostgreSQL | Docker Compose | API `8001` (theo `API_PORT` trong `.env`) |
| FOne-Admin | `npm run dev` | `3000` |
| FOne-Frontend | `npm run dev` | `3001` |

Hai app Next.js **không cần Docker để phát triển**. `npm run dev` cho hot reload và
vòng lặp nhanh hơn nhiều; container hóa chúng chỉ có ý nghĩa khi deploy. Backend thì
vẫn nên chạy bằng Compose vì nó cần PostgreSQL và Redis đi kèm.

## 1. Backend

Thêm mật khẩu review console vào `.env` (không commit file này):

```dotenv
ADMIN_PASSWORD=<mật khẩu riêng, tối thiểu 12 ký tự>
```

Mật khẩu ngắn hơn 12 ký tự bị coi như **chưa cấu hình**: mọi route admin trả `503`
thay vì chấp nhận một secret yếu.

Rebuild và khởi động. Cần `--build` vì `scripts/` và `db/` được COPY vào image lúc
build, không bind-mount như `src/` — bỏ `--build` thì migration mới và seeder mới
không có trong container:

```powershell
docker compose up --build -d
docker compose exec api python scripts/migrate_postgres.py
docker compose exec api python scripts/seed_postgres.py --include-candidates
```

Migration và seeder đều idempotent, chạy lại được. Seeder nạp cả evidence cho
review console.

Kiểm tra:

```powershell
curl.exe --fail http://localhost:8001/health/ready
```

## 2. Review console (FOne-Admin)

```powershell
cd D:\FOne-Admin
npm install
npm run dev
```

`.env.local` cần trỏ đúng cổng backend:

```dotenv
NAVIGATOR_API_BASE_URL=http://localhost:8001
```

Mở http://localhost:3000, đăng nhập bằng `ADMIN_PASSWORD` vừa đặt.

## 3. Landing page (FOne-Frontend)

```powershell
cd D:\FOne-Frontend
npm install
npm run dev
```

Mở http://localhost:3001. Trang không phụ thuộc backend.

Nút "Quan tâm OA" và mã QR sẽ hiện trạng thái *chưa cấu hình* cho tới khi đặt:

```dotenv
NEXT_PUBLIC_ZALO_OA_URL=https://zalo.me/<oa_id_dạng_số>
```

`NEXT_PUBLIC_*` được Next nội suy lúc build, nên sau khi đổi phải restart dev server
(hoặc build lại nếu đang chạy production build).

## Kiểm thử không cần giao diện

Test tự động của backend không cần PostgreSQL, Redis hay credential thật:

```powershell
make check PYTHON=.venv/Scripts/python.exe
```

Gọi API admin bằng curl:

```bash
# Lấy session
TOKEN=$(curl -s -X POST http://localhost:8001/api/v1/admin/session \
  -H "Content-Type: application/json" \
  -d '{"password":"<ADMIN_PASSWORD>"}' \
  | python -c "import json,sys;print(json.load(sys.stdin)['token'])")

# Số liệu catalog
curl -s -H "Authorization: Bearer $TOKEN" http://localhost:8001/api/v1/admin/stats

# Danh sách candidate chờ duyệt
curl -s -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8001/api/v1/admin/services?review_status=candidate"
```

Swagger tại http://localhost:8001/docs có cả hai scheme: `NavigatorApiKey` cho API
đọc và `AdminSession` cho API quản trị.

## Thử luồng duyệt mà không làm bẩn catalog

Catalog local hiện đã có 66 dịch vụ đang phục vụ và **không còn candidate nào chờ
duyệt**, nên hàng đợi review sẽ trống. Muốn thử luồng duyệt, tạo một record nháp rồi
xóa sau:

```bash
# Tạo record mới; luôn ở trạng thái chưa publish
curl -s -X POST http://localhost:8001/api/v1/admin/services \
  -H "Authorization: Bearer $TOKEN" -H "Content-Type: application/json" \
  -d '{"name":"NHAP - xoa sau khi thu","provider":"Thu nghiem",
       "service_type":"oa","category":"utilities",
       "description":"Record tam de thu luong duyet.",
       "launch_url":"https://zalo.me/1234567890123456789"}'
```

Record mới có `source_type=console`, nên dọn sạch bằng:

```powershell
docker compose exec postgres psql -U navigator -d navigator `
  -c "DELETE FROM services WHERE source_type='console';"
```

Thử guardrail: sửa `launch_url` của record nháp thành `https://example.com/x` rồi bấm
duyệt — API phải trả `409` kèm danh sách lý do, và console khóa nút duyệt.

## Thử webhook Zalo ở local

Webhook cần URL HTTPS công khai để Zalo gọi tới, nên **không test được thuần local**.
Có thể gửi payload giả để kiểm tra phần xác thực, nhưng chữ ký phải khớp
`sha256(app_id + raw_body + timestamp + ZALO_WEBHOOK_SECRET)`; payload không có chữ ký
đúng sẽ bị trả `401 INVALID_SIGNATURE` — đó là hành vi đúng, không phải lỗi cấu hình.

Nếu cần thử end-to-end với OA thật, dùng môi trường VPS đã có HTTPS
([vps-deployment.md](./vps-deployment.md)) thay vì mở tunnel từ máy cá nhân.

## Cổng đang dùng

| Cổng | Dịch vụ |
| --- | --- |
| 3000 | FOne-Admin (dev) |
| 3001 | FOne-Frontend (dev) |
| 8001 | Backend API (map từ 8000 trong container) |
| 5432 | PostgreSQL (chỉ bind vào 127.0.0.1) |

Redis không publish cổng ra host; truy cập qua `docker compose exec redis redis-cli`.
