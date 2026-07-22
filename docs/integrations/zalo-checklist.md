# Checklist tích hợp Zalo OA

Checklist này là cổng kiểm soát trước khi nối scaffold với OA thật. Không điền endpoint, tên event, trường payload hay công thức signature theo trí nhớ hoặc blog cũ. Mỗi mục cần bằng chứng từ trang chính thức đúng sản phẩm/phiên bản và một contract test/fixture đã ẩn dữ liệu nhạy cảm.

Nguồn bắt đầu: [Zalo Developer portal](https://developers.zalo.me/) và [Open APIs documentation](https://docs.zaloplatforms.com/docs/OA).

## 1. OA, Zalo App và quyền

- [ ] Chốt OA dùng cho development/demo và owner chịu trách nhiệm.
- [ ] Ghi loại OA, trạng thái xác thực, gói dịch vụ và ngày kiểm tra quyền lợi.
- [ ] Chốt Zalo App kết nối với OA và môi trường test/production.
- [ ] Xác minh quyền nhận/gửi từng loại tin cần cho text và voice.
- [ ] Xác minh cửa sổ tương tác, hạn mức, phí và chính sách nội dung hiện hành.
- [ ] Có phương án demo an toàn nếu quyền/gói chưa được cấp đúng hạn.

## 2. Webhook contract

- [ ] Lưu URL tài liệu chính xác và ngày truy cập cho text event.
- [ ] Lưu URL tài liệu chính xác và ngày truy cập cho audio/attachment event.
- [ ] Ghi HTTP method, content type, acknowledgement và retry behavior đã xác minh.
- [ ] Xác định event/message ID dùng cho idempotency; thử event gửi lại.
- [ ] Xác định cơ chế/canonical input kiểm tra signature hiện hành.
- [ ] Kiểm tra timestamp/replay protection nếu contract yêu cầu.
- [ ] Tạo fixture text tối thiểu đã loại UID/token/URL tạm thật.
- [ ] Tạo fixture voice tối thiểu đã loại UID/token/URL tạm thật.
- [ ] Contract test từ chối signature sai và không xử lý trùng.
- [ ] Webhook chỉ enqueue sau khi validation thành công và acknowledge theo contract.

## 3. Audio và STT handoff

- [ ] Xác minh cách nhận/tải attachment và authorization cần thiết.
- [ ] Kiểm tra URL tải có thời hạn, giới hạn kích thước, MIME type và codec thực tế.
- [ ] Đặt timeout, giới hạn byte/duration và chống redirect/SSRF khi tải audio.
- [ ] Chốt nơi lưu tạm, mã hóa, quyền truy cập và thời hạn xóa.
- [ ] Xác minh cách xử lý khi provider không trả confidence.
- [ ] Có UX xác nhận transcript thấp/không xác định confidence.

## 4. Token lifecycle và secret

- [ ] Xác minh access/refresh token flow, expiry, rotation và revoke bằng tài liệu hiện hành.
- [ ] Ghi owner của credential và quy trình cấp/thu hồi khi thành viên rời nhóm.
- [ ] Chỉ inject secret qua môi trường/secret manager; `.env` không được commit.
- [ ] Redaction token, UID, attachment URL và header nhạy cảm trong log/error trace.
- [ ] Test refresh đồng thời để tránh nhiều worker ghi đè token mới.
- [ ] Có cảnh báo trước expiry hoặc khi refresh liên tiếp thất bại.

## 5. Gửi phản hồi

- [ ] Xác minh endpoint, body, recipient identifier và loại tin cho phản hồi hiện tại.
- [ ] Xác minh loại CTA/link nào được hỗ trợ cho OA, Mini App và website.
- [ ] Mapping lỗi thành retryable/non-retryable; không retry vô hạn.
- [ ] Kiểm tra idempotency phía ứng dụng để không gửi hai tin cho một event.
- [ ] Kiểm tra giới hạn độ dài/nút/kết quả; response policy vẫn tối đa ba dịch vụ.
- [ ] Test với UID test được phép và không lưu UID thô trong analytics.

## 6. Chính sách, riêng tư và fallback

- [ ] Bot chỉ phản hồi tương tác thuộc phạm vi MVP; không broadcast/chủ động hàng loạt.
- [ ] Chốt notice/consent phù hợp cho việc dùng STT/LLM bên thứ ba.
- [ ] Chốt retention cho raw event, transcript, audio và audit log.
- [ ] Có cách yêu cầu xóa dữ liệu và xác minh dữ liệu đã xóa.
- [ ] Xác minh quy trình nhân viên tiếp quản trong OA Manager.
- [ ] Có câu trả lời ngoài phạm vi/no-result và không hứa hệ thống đã thực hiện giao dịch.

## 7. Kiểm thử trước demo/phát hành

- [ ] Text event thật đi end-to-end qua OA test.
- [ ] Voice event thật đi end-to-end, bao gồm confidence thấp/failure.
- [ ] Duplicate/retry không tạo phản hồi trùng.
- [ ] Token hết hạn, rate limit, timeout và OA API 5xx có hành vi dự kiến.
- [ ] Không có tên/URL ngoài registry trong toàn bộ test set.
- [ ] Kiểm tra link/`active`/`last_verified_at` ngay trước demo.
- [ ] Xem log để xác nhận không rò token, UID thô hoặc attachment URL nhạy cảm.
- [ ] Ghi rõ phiên bản/tag/commit đã demo và thời điểm xác minh contract.

## Nhật ký bằng chứng

| Hạng mục | URL tài liệu chính thức | Ngày kiểm tra | Quyền/phiên bản | Fixture/test | Người xác minh |
| --- | --- | --- | --- | --- | --- |
| Text webhook | TODO | TODO | TODO | TODO | TODO |
| Voice webhook | TODO | TODO | TODO | TODO | TODO |
| Signature | TODO | TODO | TODO | TODO | TODO |
| Token lifecycle | TODO | TODO | TODO | TODO | TODO |
| Send message | TODO | TODO | TODO | TODO | TODO |
| Hạn mức/gói OA | TODO | TODO | TODO | TODO | TODO |
