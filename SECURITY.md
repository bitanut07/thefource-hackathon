# Chính sách bảo mật

## Trạng thái hỗ trợ

Dự án đang ở giai đoạn scaffold/MVP và chưa có bản phát hành production được cam kết hỗ trợ. Chỉ revision mới nhất trên nhánh mặc định được xem xét; không nên triển khai với dữ liệu/credential thật nếu checklist tích hợp, threat review và kiểm thử chưa hoàn tất.

## Báo cáo lỗ hổng

Không tạo GitHub issue công khai và không gửi proof-of-concept chứa token, UID, raw webhook, attachment URL có thời hạn, audio hoặc transcript người dùng.

Sau khi repository GitHub được tạo, owner cần bật **Private vulnerability reporting**. Nếu mục **Security > Report a vulnerability** khả dụng, hãy dùng kênh đó. Nếu chưa khả dụng, liên hệ maintainer qua kênh bảo mật riêng do owner công bố trước khi public repo; không dùng issue/discussion công khai.

Báo cáo nên có:

- loại và mức ảnh hưởng dự kiến;
- commit/tag và cấu hình liên quan;
- bước tái hiện tối thiểu bằng dữ liệu giả;
- phạm vi credential/dữ liệu bị ảnh hưởng;
- đề xuất giảm thiểu nếu có.

Owner phải điền kênh liên hệ và mục tiêu thời gian phản hồi trước khi coi policy này là sẵn sàng production. Không gửi secret để “chứng minh” lỗi; hãy cung cấp fingerprint/thời gian đã redacted.

## Phạm vi ưu tiên

- Bypass xác minh webhook, replay hoặc idempotency.
- Token/secret lộ qua repo, log, image, error hoặc CI artifact.
- SSRF/path traversal khi tải voice attachment hoặc verify launch URL.
- LLM/prompt injection làm lộ dữ liệu hoặc tạo service/URL ngoài registry.
- Bypass `active`, allowlist, authorization hoặc tenant/OA boundary.
- UID/raw event/audio/transcript bị lưu quá mức retention hoặc truy cập trái phép.
- Queue/job deserialization, retry storm hoặc duplicate send có tác động người dùng.
- Dependency/container/loader dữ liệu tạo đường thực thi hoặc escalation ngoài dự kiến.

Các lỗi chất lượng thông thường không tạo tác động bảo mật có thể dùng bug template.

## Xử lý credential bị lộ

Nếu nghi secret đã xuất hiện trong commit/log/chat:

1. Revoke/rotate credential tại provider trước khi chỉ xóa text khỏi Git.
2. Dừng adapter/traffic liên quan nếu cần để giới hạn tác động.
3. Xác định nơi secret đã được dùng. Coi log hiện tại là dữ liệu có thể nhạy cảm cho đến khi redaction runtime được tích hợp và kiểm thử; không giả định log đã được làm sạch.
4. Làm sạch history/artifact theo quy trình owner, nhưng coi secret cũ là không còn tin cậy.
5. Thêm regression guard (secret scan/redaction/test) trước khi khôi phục.

Không commit `.env`; `.env.example` chỉ chứa tên biến và giá trị mặc định không nhạy cảm.

## Yêu cầu trước production

`compose.yaml` chỉ dành cho phát triển local và không được dùng làm cấu hình production. Việc đặt biến retention, hash salt hoặc allowlist chỉ là cấu hình; nó không chứng minh enforcement/xóa dữ liệu đã được triển khai.

- Hoàn tất contract evidence trong `docs/integrations/zalo-checklist.md`.
- Secret manager, rotation, least privilege và audit access được cấu hình.
- Threat model bao phủ webhook, queue, audio download, provider egress, registry và admin API.
- Data retention/deletion/consent và incident notification owner được chốt.
- URL allowlist, input/schema validation, egress restriction và log redaction có test.
- Dependency/container scan và backup/restore rehearsal có owner.

Tài liệu này không thay thế đánh giá pháp lý, quyền riêng tư hoặc chính sách Zalo/provider áp dụng cho dữ liệu thật.
