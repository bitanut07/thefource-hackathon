# Runbook vận hành MVP

## Sơ đồ vận hành

`compose.yaml` chạy API, RQ worker và Redis cho môi trường phát triển. API text
`POST /api/v1/navigate` gọi Gemini đồng bộ, sau đó tìm trong Service Registry
JSON ở bộ nhớ và trả tối đa năm candidate qua URL allowlist. Runtime mặc định đọc
`data/registry/services.real.json`, hiện có 8 dịch vụ với danh tính và URL công
khai đã review.

Fake LLM adapter chỉ dùng trong test/CI. Webhook Zalo vẫn chặn bằng
`501 ZALO_CONTRACT_NOT_CONFIGURED`; signature/idempotency, send-message, OA
token lifecycle, STT thật và audio chưa phải năng lực runtime hiện có.

## Khởi động local

Yêu cầu: Python 3.12, uv 0.11.19, Docker có Compose plugin và GNU Make hoặc
lệnh tương đương.

```bash
make setup
uv sync --locked --extra dev --link-mode copy
```

`make setup` chỉ tạo `.env` và `.venv`, không cài dependency. Trước khi chạy,
trong `.env` giữ `LLM_PROVIDER=gemini`, xác nhận
`REGISTRY_DATA_PATH=data/registry/services.real.json` và đặt
`GEMINI_API_KEY` bằng key mới chưa từng công khai. Tạo thêm
`NAVIGATOR_API_KEY` ngẫu nhiên, dài ít nhất 16 ký tự và độc lập với Gemini key,
để bảo vệ toàn bộ API `/api/v1/*`.
Không dùng lại key từng xuất hiện trong chat, log, issue hoặc commit.

Chạy stack ở terminal A:

```bash
make dev
```

Kiểm tra ở terminal B:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
docker compose ps
```

`/health/live` chỉ kiểm tra API process. `/health/ready` yêu cầu Gemini key,
Navigator API key, Registry có record hoạt động, allowlist bao phủ các URL đang
hoạt động và Redis trả ping; cấu hình thiếu/sai hoặc Redis lỗi trả `503`.
Registry được validate fail-fast khi API dựng pipeline lúc khởi động; worker
validate khi dựng pipeline để xử lý job.

Gọi API text:

```bash
read -rsp "NAVIGATOR_API_KEY: " NAVIGATOR_API_KEY && echo
curl --fail \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -d '{"text":"Tôi muốn đóng tiền điện ở TP.HCM."}' \
  http://localhost:8000/api/v1/navigate
```

API trả `401` khi key truy cập sai, `429` khi hết slot xử lý, `503` khi thiếu
cấu hình và `502` khi provider trả lỗi hoặc structured output không hợp lệ.
Không có fallback tạo service/URL ngoài Registry.

Swagger cũng cung cấp API kiểm chứng từng lớp:

- `/api/v1/intents/extract`: structured query từ Gemini;
- `/api/v1/services` và `/api/v1/services/{service_id}`: Registry runtime;
- `/api/v1/research/search`: RAG research-only, không URL/CTA;
- `/api/v1/navigate`: flow end-to-end.

### Review console quản trị catalog

Console là bề mặt duy nhất được ghi vào Service Catalog. Cần
`SEARCH_BACKEND=postgres`, `DATABASE_URL` và `ADMIN_PASSWORD` dài từ 12 ký tự; mật
khẩu ngắn hơn bị coi như chưa cấu hình và mọi route admin trả `503`.

```powershell
make catalog-migrate   # áp dụng bảng audit service_review_events
```

Lấy session rồi gọi API quản trị:

```bash
read -rsp "ADMIN_PASSWORD: " ADMIN_PASSWORD && echo
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/admin/session \
  -H "Content-Type: application/json" \
  -d "{\"password\":\"$ADMIN_PASSWORD\"}" | python -c "import json,sys;print(json.load(sys.stdin)['token'])")
curl --fail -H "Authorization: Bearer $TOKEN" \
  "http://localhost:8000/api/v1/admin/stats"
```

`NAVIGATOR_API_KEY` **không** mở được route admin: key đó chỉ cấp quyền đọc.
Chi tiết guardrail publish, audit và giới hạn hiện tại nằm trong
[Review Console API](../architecture/admin-api.md).

Hai số cần theo dõi từ `GET /api/v1/admin/stats`:

- `publishable_with_blockers` khác `0`: có record đang phục vụ nhưng vi phạm
  guardrail, nên `/health/ready` sẽ trả `503`. Dùng
  `POST /api/v1/admin/services/{id}/deactivate` để rút record đó ra trước khi sửa.
- `missing_embedding`: số record thiếu vector sau khi bị sửa nội dung; chạy
  `make catalog-embed` để tạo lại.

Nếu chỉ chạy Redis bằng container, chạy API trực tiếp ở terminal A:

```bash
docker compose up -d redis
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Đường dẫn trực tiếp vẫn cần `.env` chứa Gemini key, registry path và allowlist.
Worker chưa tham gia request đồng bộ `/api/v1/navigate`, nhưng vẫn được giữ cho
queue và luồng webhook mục tiêu. Chạy worker trực tiếp ở terminal B:

```bash
.venv/bin/zsn-worker
```

## Lệnh thường dùng

```bash
make check PYTHON=.venv/bin/python       # lint + typecheck + test
make seed PYTHON=.venv/bin/python        # chỉ validate fixture kiểm thử mặc định
.venv/bin/python scripts/seed_registry.py --file data/registry/services.real.json
make tree        # xem cấu trúc repo
docker compose logs -f api worker
docker compose down
```

`make seed` và lệnh có `--file` ở trên đều kiểm tra registry thật mặc định mà
không ghi dữ liệu. Kiểm tra tĩnh URL theo allowlist:

```bash
ALLOWED_LAUNCH_HOSTS=zalo.me \
  .venv/bin/python scripts/verify_links.py \
  --file data/registry/services.real.json \
  --require-allowlist
```

Script URL kiểm tra cấu trúc/host và bắt buộc record OA dùng đúng deeplink số
`https://zalo.me/<OA_ID>` nhưng không gọi mạng. Slug, `oa.zalo.me/...`, Mini App
`/s/...`, query, fragment và dấu `/` cuối không được dùng làm CTA OA. Việc 8
liên kết pass không đồng nghĩa mọi OA badge, tính năng trong channel hoặc tích
hợp OA production đã được xác minh; mục tiêu Sprint 2 vẫn là 20-40 dịch vụ đã
review.

Kho research có thể được index để reviewer tra cứu:

```bash
.venv/bin/python scripts/build_rag_db.py
```

Output mặc định là `data/rag/service-catalog.sqlite3`. API research-only có thể
đọc kho này để kiểm chứng dữ liệu, nhưng kho chưa tham gia ranking của Navigator
và không được dùng để tạo CTA. Nếu sau này index record đã approved/verified,
truyền
`--allowed-launch-hosts` bằng danh sách host chính xác; host ngoài allowlist hoặc
status không nằm trong positive allowlist làm build thất bại.

## Kiểm tra trước khi bật webhook thật

- [ ] Hoàn tất [checklist Zalo](../integrations/zalo-checklist.md) và contract tests.
- [ ] Secret production nằm trong secret manager, không nằm trong `.env`/log/image.
- [ ] Mở rộng 8 record hiện tại thành 20-40 record đã review, schema hợp lệ và
  được load thành công; evidence/candidate chưa xác minh không được bật tự động.
- [ ] URL allowlist, audio retention và UID hash salt đã cấu hình.
- [ ] API public dùng HTTPS; readiness không công khai secret/dependency detail.
- [ ] Dashboard/alert cho queue backlog, error rate, latency và failed jobs hoạt động.

## Chẩn đoán

Mục Gemini/API text áp dụng cho runtime hiện tại. Các mục webhook, queue,
send-message và STT là runbook đích cho các sprint sau; không dùng chúng để
tuyên bố tích hợp OA production đã hoạt động.

### API live nhưng readiness lỗi

1. Xem `docker compose ps` và log API.
2. Xác nhận Gemini key và Navigator API key có giá trị mà không in key.
3. Kiểm tra Registry có record hoạt động và allowlist bao phủ chính xác host.
4. Kiểm tra kết nối Redis.
5. Nếu app không khởi động, kiểm tra `REGISTRY_DATA_PATH`, schema và allowlist mà
   không log dữ liệu nhạy cảm.
6. Xác nhận file registry đúng phiên bản/hash dự kiến.

### API điều hướng trả `502` hoặc `503`

1. `401`: kiểm tra header `X-API-Key` có khớp `NAVIGATOR_API_KEY`.
2. `429`: chờ theo `Retry-After`; kiểm tra tải và giới hạn đồng thời.
3. `503`: kiểm tra key đã cấu hình/rotate, Registry/allowlist, quota và trạng thái
   Gemini; không dán key vào log hoặc ticket.
4. `502`: kiểm tra lỗi provider, timeout và structured-output compatibility của
   model đã cấu hình.
5. Giữ retry hữu hạn; không retry đồng loạt khi gặp quota/rate limit.
6. Không chuyển sang fake runtime và không tạo candidate từ output lỗi.
7. Xác nhận response lỗi không lộ request, secret hoặc nội dung provider thô.

### Webhook không vào queue

1. Nếu response là `501 ZALO_CONTRACT_NOT_CONFIGURED`, đây là safety gate hiện
   tại; không cố bypass khi contract chưa được xác minh.
2. Sau khi gate được thay bằng integration đã review, tìm correlation/event ID
   đã hash hoặc redacted trong structured log.
3. Kiểm tra validation/signature failure và clock skew theo contract đã xác minh.
4. Kiểm tra Redis connectivity và queue name.
5. Đối chiếu fixture với tài liệu/event version hiện hành.
6. Không log raw body nếu nó chứa dữ liệu cá nhân hoặc URL attachment.

### Event bị xử lý hai lần

1. Xác minh idempotency key thực sự lấy từ trường contract đã xác minh.
2. Kiểm tra transaction ghi nhận `processing/done` và thời hạn key.
3. Dừng replay thủ công cho đến khi biết phạm vi duplicate.
4. Đối soát các message đã gửi và ghi incident; không “sửa” bằng cách bỏ retry.

### Queue lag hoặc failed jobs tăng

1. So sánh enqueue rate, processing rate và duration STT/LLM/OA API.
2. Phân loại lỗi retryable/non-retryable trước khi replay.
3. Cô lập failed jobs có cùng nguyên nhân; giới hạn retry/backoff.
4. Scale worker chỉ khi Redis/provider quota và memory footprint của registry chịu được tải tăng.
5. Khi backlog vượt khả năng phục hồi, tạm ngừng intake hoặc trả fallback được duyệt.

### STT lỗi hoặc timeout sau khi bật voice

1. Kiểm tra provider status/quota mà không lộ request data.
2. Xác nhận timeout và circuit breaker; không retry đồng loạt.
3. STT lỗi/confidence thấp: xin người dùng nhập chữ hoặc xác nhận transcript.
4. Kiểm tra job cleanup để audio tạm vẫn bị xóa khi exception.

### OA API không gửi được phản hồi

1. Phân loại token expiry, permission, rate limit, invalid recipient/message type hoặc 5xx theo contract.
2. Không ghi token/UID thô vào ticket hoặc log.
3. Chỉ retry lỗi được đánh dấu retryable; idempotency phải ngăn gửi trùng.
4. Nếu token nghi bị lộ, rotate/revoke trước rồi mới khôi phục traffic.

### URL không hợp lệ xuất hiện

1. Tạm vô hiệu record và chặn host ở allowlist nếu cần.
2. Kiểm tra response candidate IDs so với registry/audit log.
3. Dừng demo/release nếu URL không bắt nguồn từ candidate set đã lọc.
4. Rà prompt, schema validation và response builder; bổ sung regression test.

## Xử lý sự cố bảo mật

1. Giảm thiểu tác động: ngắt credential/adapter hoặc traffic liên quan.
2. Bảo toàn log/audit cần thiết nhưng không sao chép dữ liệu nhạy cảm sang kênh công khai.
3. Rotate token/secret có nguy cơ lộ và xác minh revoke.
4. Xác định thời gian, dữ liệu, người dùng và dịch vụ bị ảnh hưởng.
5. Thực hiện nghĩa vụ thông báo theo owner/pháp lý/chính sách đã chốt.
6. Chỉ khôi phục sau khi có fix, test hồi quy và người chịu trách nhiệm phê duyệt.

Quy trình báo cáo riêng tư nằm trong [SECURITY.md](../../SECURITY.md).
