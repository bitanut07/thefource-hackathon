# Review Console API

API quản trị catalog cho app FOne-Admin. Đây là bề mặt duy nhất được phép **ghi**
vào Service Catalog; toàn bộ luồng runtime (`/api/v1/navigate`, webhook OA) vẫn chỉ
đọc.

## Vì sao tách khỏi `NAVIGATOR_API_KEY`

`NAVIGATOR_API_KEY` cấp quyền đọc cho máy gọi API. Console thì đổi được thứ người
dùng cuối nhìn thấy, nên dùng credential riêng (`ADMIN_PASSWORD`) và session riêng.
Test `test_console_rejects_missing_wrong_and_navigator_credentials` giữ ràng buộc
này: navigator key không mở được route admin nào.

## Cấu hình

Thêm vào `.env` (file này không được commit):

```dotenv
ADMIN_PASSWORD=mat-khau-review-console-toi-thieu-12-ky-tu
# Tùy chọn:
ADMIN_SESSION_TTL_SECONDS=43200
ADMIN_LOGIN_MAX_ATTEMPTS=10
ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS=900
ADMIN_ALLOWED_ORIGINS=
```

`ADMIN_PASSWORD` ngắn hơn 12 ký tự bị coi như **chưa cấu hình**: mọi route admin
trả `503` thay vì chấp nhận một secret yếu.

Console cần `SEARCH_BACKEND=postgres` và `DATABASE_URL`. Với backend `json`,
`app.state.admin_catalog` là `None` và route admin trả `503` — registry JSON được
nạp một lần vào bộ nhớ nên không thể ghi.

Áp dụng migration audit log (init script của Postgres chỉ chạy trên volume rỗng):

```powershell
make catalog-migrate
```

## Session

| API | Mô tả |
| --- | --- |
| `POST /api/v1/admin/session` | Đổi `ADMIN_PASSWORD` lấy token; trả `expires_at` |
| `DELETE /api/v1/admin/session` | Thu hồi token ngay tại server |

Token là chuỗi random đối xứng lưu trong Redis dưới dạng `sha256(token)`, TTL bằng
`ADMIN_SESSION_TTL_SECONDS`. Chọn cách này thay vì JWT tự ký để có thu hồi thật và
để một Redis dump bị lộ không thể replay thành session sống.

Gửi kèm mọi request admin: `Authorization: Bearer <token>`.

**Nên giữ token ở phía server của FOne-Admin** (httpOnly cookie do Next.js route
handler quản lý, rồi server gọi backend), không lưu `localStorage`. Khi làm vậy
không cần `ADMIN_ALLOWED_ORIGINS`; chỉ đặt biến này nếu trình duyệt gọi backend
trực tiếp và cần CORS.

Đăng nhập sai bị đếm theo IP trong `ADMIN_LOGIN_ATTEMPT_WINDOW_SECONDS`; vượt
`ADMIN_LOGIN_MAX_ATTEMPTS` trả `429` kèm `Retry-After`. Sau reverse proxy, mọi
request chung một IP nên giới hạn trở thành toàn cục — header `X-Forwarded-For`
không được tin vì client tự đặt được và sẽ cho phép tạo bucket mới mỗi lần thử.

## API catalog

| API | Mô tả |
| --- | --- |
| `GET /api/v1/admin/services` | Liệt kê **mọi** record kể cả chưa publish; filter `review_status`, `service_type`, `active`, `q` |
| `GET /api/v1/admin/services/{id}` | Chi tiết kèm evidence |
| `POST /api/v1/admin/services` | Tạo record mới, luôn `active=false` |
| `PATCH /api/v1/admin/services/{id}` | Sửa một phần; chỉ ghi trường được gửi |
| `POST /api/v1/admin/services/{id}/approve` | Đưa vào phục vụ |
| `POST /api/v1/admin/services/{id}/reject` | `review_status=rejected`, rút khỏi phục vụ |
| `POST /api/v1/admin/services/{id}/deactivate` | Rút khỏi phục vụ, **giữ** `review_status` |
| `GET /api/v1/admin/services/{id}/events` | Lịch sử review của record |
| `GET /api/v1/admin/stats` | Số liệu tổng quan |
| `GET /api/v1/admin/queue-health` | Queue depth, failed jobs, số worker |

`reject` và `deactivate` tách nhau có chủ ý: reject là **quyết định review**,
deactivate là **tạm dừng vận hành** (ví dụ link OA chết) và giữ nguyên trạng thái
review để không mất thông tin đã duyệt.

## Publish guardrail

`publish_blockers()` trong `src/domain/catalog_admin.py` là nơi duy nhất định nghĩa
"record này có được phục vụ người dùng không". Nó chặn:

| Điều kiện | Vì sao |
| --- | --- |
| `service_type` không phải `oa`/`mini_app` | Trái constraint của migration `002_zalo_channels_only.sql` |
| `category` ngoài `ServiceCategory` | `PostgresServiceRegistry._row_to_service` gọi `ServiceCategory(...)`; giá trị lạ làm **mọi** request `/navigate` lỗi `ValueError`, không phải lỗi catalog được xử lý |
| `launch_url` ngoài allowlist host hoặc không HTTPS | Đúng thứ response builder được thiết kế để không bao giờ phát ra |
| OA nhưng không phải deeplink số `https://zalo.me/<oa_id>` | Slug, `oa.zalo.me/...`, `/s/...`, query, fragment, dấu `/` cuối đều bị loại |

Guardrail được thực thi ở **tầng repository** (`PostgresAdminCatalog` nhận
`LaunchUrlPolicy` qua constructor), không phải ở tầng HTTP, nên không caller nào
bypass được. Nó áp dụng hai chiều:

- `approve` bị từ chối `409` nếu record chưa sạch;
- `PATCH` một record **đang phục vụ** bị từ chối `409` nếu bản sau khi sửa vi phạm
  guardrail — tránh sửa nhầm làm `/health/ready` trả `503`.

Record chưa publish thì sửa thoải mái; blocker chỉ là cảnh báo hiển thị.

Mỗi item trong listing đều có `is_publishable` và `publish_blockers` để reviewer
thấy lý do trước khi bấm nút, thay vì bấm rồi mới nhận lỗi.

## Embedding bị vô hiệu khi sửa nội dung

Sửa `name`, `provider`, `category`, `description`, `region`, `target_user`,
`organization`, `aliases` hoặc `intents` sẽ **xóa** `embedding` của record đó
(`search_text` được dựng lại theo đúng thứ tự trường của
`scripts/seed_postgres.joined_text` để record sửa qua API xếp hạng giống record do
seeder import).

Xóa vector là cố ý: giữ vector cũ nghĩa là xếp hạng theo ngữ nghĩa của nội dung đã
lỗi thời. Khi `embedding IS NULL`, lane semantic đóng góp 0 cho record đó và FTS +
trigram vẫn chạy. Tạo lại bằng:

```powershell
make catalog-embed
```

`GET /api/v1/admin/stats` trả `missing_embedding` để theo dõi số record đang thiếu
vector, và `publishable_with_blockers` — khác `0` nghĩa là `/health/ready` sẽ báo
`503`.

## Audit

Mọi mutation ghi một dòng vào `service_review_events`
(`db/migrations/003_service_review_events.sql`): action, actor, note, danh sách
trường đã đổi và chuyển trạng thái review. `actor` là TEXT chứ không phải khóa
ngoại vì hiện chỉ có một tài khoản dùng chung; chuyển sang nhiều người dùng về sau
không cần migration.

## Giới hạn hiện tại

- **Một tài khoản dùng chung.** Mọi audit record có `actor="admin"`, nên chưa quy
  trách nhiệm được theo từng người. Cần bảng user + role trước khi có nhiều
  reviewer.
- `GET /api/v1/admin/stats` quét toàn bộ record đang phục vụ trong Python để đếm
  `publishable_with_blockers` (giới hạn 1.000 record). Đủ cho quy mô hiện tại
  (hàng chục dịch vụ) nhưng cần viết lại bằng SQL trước khi catalog lên hàng nghìn.
- Chưa có kiểm tra link tự động; `last_verified_at` chỉ được cập nhật khi có người
  bấm approve.
