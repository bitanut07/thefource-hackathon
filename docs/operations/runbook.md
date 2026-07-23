# Runbook vận hành MVP

## Sơ đồ vận hành

`compose.yaml` chạy API, RQ worker và Redis cho môi trường phát triển. Local MVP
nạp Service Registry JSON vào bộ nhớ và xử lý text bằng fake deterministic
provider qua `/demo/query` hoặc `/demo/queue`. Webhook Zalo vẫn chặn bằng `501`;
signature/idempotency, adapter Zalo thật, LLM/STT thật và audio chưa phải năng
lực runtime hiện có.

## Khởi động local

Yêu cầu: Python 3.12, Docker có Compose plugin và GNU Make hoặc lệnh tương đương.

```bash
make setup
.venv/bin/python -m pip install -e '.[dev]'
```

`make setup` chỉ tạo `.env` và `.venv`, không cài dependency. Chạy stack ở terminal A:

```bash
make dev
```

Kiểm tra ở terminal B:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
docker compose ps
```

Trong scaffold hiện tại, `/health/ready` chưa probe Redis hoặc xác nhận registry JSON đã load. Trước khi demo thật phải bổ sung dependency/config checks có timeout và test; trạng thái `200` hiện chỉ chứng minh API process trả được response.

Nếu chỉ chạy Redis bằng container, chạy API trực tiếp ở terminal A:

```bash
docker compose up -d redis
.venv/bin/uvicorn main:app --host 0.0.0.0 --port 8000
```

Worker trực tiếp:

Chạy ở terminal B:

```bash
.venv/bin/zsn-worker
```

## Lệnh thường dùng

```bash
make check PYTHON=.venv/bin/python       # lint + typecheck + test
make seed PYTHON=.venv/bin/python        # validate fixture registry mặc định
make tree        # xem cấu trúc repo
docker compose logs -f api worker
docker compose down
```

`make seed` là validation gate cho `data/seed/services.example.json`. Runtime
loader validate đầy đủ file tại `REGISTRY_DATA_PATH` khi dựng pipeline. Registry
demo pass không có nghĩa các dịch vụ đã được xác minh để dùng thật.

## Kiểm tra trước khi bật webhook thật

- [ ] Hoàn tất [checklist Zalo](../integrations/zalo-checklist.md) và contract tests.
- [ ] Secret production nằm trong secret manager, không nằm trong `.env`/log/image.
- [ ] Registry JSON thật có 20-40 record đã xác minh, schema hợp lệ và được load thành công; sample `active=false` không được bật tự động.
- [ ] URL allowlist, audio retention và UID hash salt đã cấu hình.
- [ ] API public dùng HTTPS; readiness không công khai secret/dependency detail.
- [ ] Dashboard/alert cho queue backlog, error rate, latency và failed jobs hoạt động.

## Chẩn đoán mục tiêu sau khi hoàn thiện integration

Các mục dưới đây là runbook đích. Skeleton chưa enqueue webhook, chưa gọi provider và chưa có audit writer/redaction runtime hoàn chỉnh; vì vậy không dùng chúng để tuyên bố các kiểm soát đã hoạt động.

### API live nhưng readiness lỗi

1. Xem `docker compose ps` và log API.
2. Kiểm tra kết nối Redis và trạng thái loader registry mà không log dữ liệu nhạy cảm.
3. Xác nhận file registry đúng phiên bản/hash dự kiến.
4. Nếu dependency bên ngoài không thuộc readiness contract, không để nó làm API flap.

### Webhook không vào queue

1. Tìm correlation/event ID đã hash hoặc redacted trong structured log.
2. Kiểm tra validation/signature failure và clock skew theo contract đã xác minh.
3. Kiểm tra Redis connectivity và queue name.
4. Đối chiếu fixture với tài liệu/event version hiện hành.
5. Không log raw body nếu nó chứa dữ liệu cá nhân hoặc URL attachment.

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

### LLM/STT lỗi hoặc timeout

1. Kiểm tra provider status/quota mà không lộ request data.
2. Xác nhận timeout và circuit breaker; không retry đồng loạt.
3. LLM lỗi: dùng no-result/fallback an toàn, không tạo câu trả lời từ dữ liệu chưa kiểm soát.
4. STT lỗi/confidence thấp: xin người dùng nhập chữ hoặc xác nhận transcript.
5. Kiểm tra job cleanup để audio tạm vẫn bị xóa khi exception.

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
