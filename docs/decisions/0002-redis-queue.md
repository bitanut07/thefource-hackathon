# ADR-0002: RQ trên Redis cho hàng đợi MVP

## Trạng thái

Được chấp nhận cho scaffold MVP

## Ngày

2026-07-22

## Bối cảnh

Webhook cần acknowledge sớm trong khi STT, LLM, hybrid search và OA API có độ trễ/khả năng lỗi. Nhóm cần queue nhẹ, chạy local bằng container và có retry/quan sát failed jobs đủ cho prototype.

## Quyết định

Dùng RQ với Redis làm message queue cho MVP. API enqueue một event envelope đã chuẩn hóa; worker xử lý job theo correlation ID và idempotency key. Retry phải có giới hạn và failed jobs phải được quan sát/cách ly trước khi replay.

Queue không thay thế source of truth cho trạng thái nghiệp vụ. Idempotency/result state cần được lưu bền vững để việc giao lại hoặc replay không gửi phản hồi trùng.

## Các phương án đã cân nhắc

### Xử lý trực tiếp trong request

Đơn giản hơn nhưng gắn latency webhook với provider bên ngoài, retry khó kiểm soát và dễ timeout.

### NATS JetStream

Có mô hình streaming/durable consumer mạnh hơn và là lựa chọn trong plan, nhưng tăng cấu hình/vận hành cho quy mô MVP.

### Celery

Hệ sinh thái và workflow phong phú hơn, nhưng API/configuration rộng hơn nhu cầu hiện tại. Có thể đánh giá lại khi cần scheduling/complex workflow sâu hơn.

## Hệ quả

- Local development cần Redis và ít nhất một worker.
- Job payload phải versioned, nhỏ và không chứa token hoặc audio bytes không cần thiết.
- Phải định nghĩa timeout, retry/backoff, retention kết quả và quy trình replay.
- Cần metric queue depth/lag, job duration, retry count và failed-job count.
- Nếu chuyển sang NATS/Celery, port queue giúp giới hạn phạm vi thay đổi.
