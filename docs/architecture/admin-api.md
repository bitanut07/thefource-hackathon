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
| `GET /api/v1/admin/services` | Liệt kê **mọi** record kể cả chưa publish; filter `review_status`, `service_type`, `active`, `q`, `deleted` |
| `GET /api/v1/admin/services/{id}` | Chi tiết kèm evidence |
| `POST /api/v1/admin/services` | Tạo record mới, luôn `active=false`; từ chối `409` nếu trùng `launch_url` |
| `PATCH /api/v1/admin/services/{id}` | Sửa một phần; chỉ ghi trường được gửi |
| `DELETE /api/v1/admin/services/{id}` | Xóa mềm: rút khỏi phục vụ + ẩn, giữ evidence và audit |
| `POST /api/v1/admin/services/{id}/restore` | Bỏ dấu đã xóa; record về trạng thái chưa phục vụ |
| `POST /api/v1/admin/services/{id}/approve` | Đưa vào phục vụ |
| `POST /api/v1/admin/services/{id}/reject` | `review_status=rejected`, rút khỏi phục vụ |
| `POST /api/v1/admin/services/{id}/deactivate` | Rút khỏi phục vụ, **giữ** `review_status` |
| `POST /api/v1/admin/services/bulk-approve` | Duyệt nhiều record, báo kết quả từng dòng |
| `POST /api/v1/admin/services/import` | Nhập `.xlsx`/`.csv`, tạo record **chờ duyệt** |
| `GET /api/v1/admin/services/import/template` | Tải file mẫu CSV |
| `GET /api/v1/admin/services/{id}/events` | Lịch sử review của record |
| `GET /api/v1/admin/stats` | Số liệu tổng quan |
| `GET /api/v1/admin/queue-health` | Queue depth, failed jobs, tuổi job chờ lâu nhất |

Bốn cách rút một dịch vụ khỏi phục vụ tách nhau có chủ ý, vì chúng mang thông tin
khác nhau và cần đọc lại được về sau:

| Hành động | `active` | `review_status` | `deleted_at` | Dùng khi |
| --- | --- | --- | --- | --- |
| `deactivate` | `false` | giữ nguyên | `NULL` | Tạm dừng vận hành, ví dụ link OA chết |
| `reject` | `false` | `rejected` | `NULL` | Quyết định review: không nhận dịch vụ này |
| `DELETE` | `false` | giữ nguyên | `now()` | Bỏ khỏi catalog nhưng giữ bằng chứng |
| `restore` | `false` | giữ nguyên | `NULL` | Hoàn tác việc xóa |

## Xóa mềm

`DELETE` không xóa hàng khỏi database. Xóa cứng sẽ cascade mất luôn evidence và
lịch sử review — tức là mất bằng chứng *vì sao* dịch vụ từng được phục vụ, thứ
reviewer cần đọc lại sau khi dịch vụ đã bị bỏ.

Migration `005_service_soft_delete.sql` thêm cột `deleted_at` và constraint
`CHECK (NOT active OR deleted_at IS NULL)`, nên trạng thái "đã xóa mà vẫn đang
phục vụ" là **không biểu diễn được**, không chỉ là điều code tránh làm. Nhờ vậy
`PostgresServiceRegistry` không cần thêm filter nào: nó đã yêu cầu `active=true`.

Record đã xóa bị ẩn khỏi listing mặc định (`deleted` để trống), và
`publish_blockers` chặn duyệt lại cho tới khi phục hồi.

## Nhập từ Excel/CSV

`POST /api/v1/admin/services/import` nhận `.xlsx` hoặc `.csv` (tối đa 5 MB, 500
dòng). Mọi dòng được tạo với `active=false`, `review_status=candidate`: **một file
Excel không thể tự đẩy liên kết ra cho người dùng thật**, vẫn phải có người bấm
duyệt. Sau khi nhập, dùng `bulk-approve` để duyệt cả lô.

Parser cố ý dễ tính với dữ liệu thật:

- tên cột nhận cả tiếng Việt (`Tên dịch vụ`, `Nhà cung cấp`, `Loại kênh`,
  `Danh mục`, `Mô tả`, `Liên kết`…) và tiếng Anh, không phân biệt dấu/hoa thường,
  thứ tự cột không quan trọng;
- CSV tự nhận delimiter `,` `;` hoặc tab — Excel bản tiếng Việt xuất ra `;` vì dấu
  thập phân là `,`;
- Excel lưu số chưa format thành float, nên `50` đọc ra `50` chứ không phải `50.0`;
- `aliases` cách nhau bằng `;`, `intents` theo dạng `tên_intent | câu hỏi ví dụ`.

Từng dòng được báo cáo riêng nên một dòng sai không hủy cả file, và số dòng khớp
với số dòng trong Excel để dễ tìm. Dòng có `launch_url` đã tồn tại trong catalog bị
bỏ qua — hai record cùng deeplink sẽ làm trợ lý gợi ý trùng một đích đến.

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
- **Record đã xóa tích lũy vô hạn.** Chưa có cơ chế dọn; cần chốt thời hạn lưu rồi
  mới xóa cứng.
- **Import không cập nhật record đã có.** Dòng trùng `launch_url` bị bỏ qua, không
  ghi đè. Muốn sửa thì dùng `PATCH`.
- `GET /api/v1/admin/stats` quét toàn bộ record đang phục vụ trong Python để đếm
  `publishable_with_blockers` (giới hạn 1.000 record). Đủ cho quy mô hiện tại
  (hàng chục dịch vụ) nhưng cần viết lại bằng SQL trước khi catalog lên hàng nghìn.
- Chưa có kiểm tra link tự động; `last_verified_at` chỉ được cập nhật khi có người
  bấm approve.
