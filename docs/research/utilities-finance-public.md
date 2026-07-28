# Nghiên cứu ứng viên: tiện ích, tài chính và hành chính công

Ngày kiểm tra: **2026-07-24**

## Kết quả

- 12 ứng viên: 4 `utilities`, 4 `finance_banking`, 4 `public_admin`.
- Kênh đích: 3 Zalo OA được nguồn chính chủ hoặc danh sách đối tác Zalo liên kết; 9 website chính chủ.
- Cả 12 bản ghi đều có URL đích mở được khi kiểm tra và đều để `active: false`, `review_status: candidate`.
- Không ứng viên nào được gắn `oa_badge_status: verified`: ba OA công khai chưa được quan sát trực tiếp dấu xác minh nên để `unknown`.
- `logo_url` chỉ là URL tham chiếu trên tên miền chính chủ/Zalo OA; không tải, sao chép hoặc suy diễn quyền sử dụng logo.

## Ba OA có liên kết nguồn gốc

| Ứng viên | OA | Bằng chứng liên kết |
| --- | --- | --- |
| VinaPhone | <https://zalo.me/3725994261701149374> | Landing chính thức `<https://oa.zalo.me/vinaphone>` nhúng trực tiếp OA số này |
| Viettel chăm sóc khách hàng | <https://zalo.me/1570758701534064697> | Trang chính chủ Viettel tại <https://business-sinvoice.vietteltelecom.vn/> |
| Ngân hàng BIDV | <https://zalo.me/3644272514222140240> | Trang chính chủ BIDV tại <https://bidv.com.vn/vn/ca-nhan/san-pham-dich-vu/thanh-toan/don-vi-thanh-toan> |

Trang EVNHANOI chính thức xác nhận có kênh Zalo, nhưng không công bố URL OA có thể đối chiếu trong nguồn đã kiểm tra. Bản ghi EVNHANOI vì vậy chỉ dùng website và không suy đoán OA ID.

## Lưu ý kiểm duyệt trước khi đưa vào registry

1. Mở từng OA trong ứng dụng Zalo để kiểm tra dấu xác minh, tên hiển thị, menu/CTA và phạm vi chức năng thực tế.
2. Với tài chính và dịch vụ công, Navigator chỉ tìm và điều hướng; không hỏi OTP, mật khẩu, số định danh, mã số thuế, số dư hoặc dữ liệu hồ sơ.
3. Kiểm tra lại Cổng Dịch vụ công TP.HCM trước khi kích hoạt. Cổng còn mở nhưng tài liệu 2025-2026 cho thấy nhiều hành trình đang chuyển về Cổng Dịch vụ công Quốc gia hoặc VNeID.
4. Chưa phân loại ZaloPay là `mini_app`: nguồn chính chủ xác nhận truy cập trong Zalo, nhưng chưa đủ bằng chứng về loại tích hợp kỹ thuật.

Chi tiết trường dữ liệu, câu mẫu, bằng chứng và ghi chú xác minh nằm trong `data/research/raw/utilities_finance_public.json`.
