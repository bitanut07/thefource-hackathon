## Thay đổi

<!-- Mô tả ngắn vấn đề và kết quả của PR. -->

## Cách kiểm chứng

<!-- Liệt kê command/test/evidence đã chạy. Không dán token, UID, raw event hoặc audio thật. -->

## Danh sách kiểm tra

- [ ] PR có phạm vi nhỏ, không trộn thay đổi không liên quan.
- [ ] `make check` chạy thành công hoặc đã giải thích rõ phần chưa chạy.
- [ ] Docker build/Compose liên quan đã được kiểm tra khi thay đổi runtime/infra.
- [ ] Test bao phủ happy path và failure/guardrail có liên quan.
- [ ] Tài liệu, `.env.example`, schema registry JSON và ADR đã cập nhật khi cần.
- [ ] Không commit secret, UID/raw payload, attachment URL hoặc audio người dùng thật.
- [ ] Tên/URL dịch vụ chỉ đến từ registry và URL allowlist.
- [ ] Thay đổi Zalo contract kèm link tài liệu chính thức, ngày kiểm tra và fixture đã ẩn dữ liệu.
- [ ] Registry schema/queue payload/API change có kế hoạch tương thích hoặc rollback.

## Ảnh hưởng demo/vận hành

<!-- Nêu config/schema mới, rủi ro, metric hoặc bước runbook cần chú ý; ghi “Không” nếu không có. -->
