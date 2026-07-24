# Public service discovery staging

Thư mục này chứa dữ liệu ứng viên thu thập từ các trang công khai để chuẩn bị
cho Service Registry. Đây **không** phải danh sách OA đã được Zalo xác minh và
không được nạp trực tiếp vào runtime.

## Nguyên tắc

- Chỉ dùng trang công khai của Zalo, cơ quan hoặc doanh nghiệp sở hữu dịch vụ.
- Không đăng nhập, không gọi API ẩn, không thu UID, tin nhắn hay dữ liệu người dùng.
- Một trang `zalo.me` truy cập được không đồng nghĩa với OA đã có dấu xác minh.
- Mọi record luôn có `active=false` và `review_status=candidate`.
- URL logo chỉ là tham chiếu để đối chiếu. Không hotlink hoặc sao chép vào sản
  phẩm trước khi kiểm tra quyền sử dụng.
- Mô tả, capability và câu hỏi mẫu phải truy ngược được về `evidence`.

## Luồng dữ liệu

1. Agent ghi kết quả độc lập vào `raw/*.json`.
2. Chạy `python scripts/build_research_catalog.py`.
3. Kiểm tra báo cáo lỗi/trùng và review thủ công OA badge, quyền logo, launch URL.
4. Chỉ record đã qua review mới được chuyển sang registry vận hành bằng một thay
   đổi riêng.

Dataset tổng hợp dùng schema `oa-candidates.schema.json`. Các trường phục vụ
giao diện trong mockup gồm `name`, `description`, `logo_url`, `cta_label` và
`launch_url`; các trường phục vụ tìm kiếm/hỏi lại gồm `category`, `regions`,
`target_users`, `organization_contexts`, `capabilities`, `aliases` và `intents`.

`organization_contexts` lưu quan hệ với công ty/campus để các câu như “tôi là
nhân viên VNG” có thể ưu tiên dịch vụ nội bộ hoặc tại chỗ. Quan hệ do người dùng
cung cấp vẫn phải để `verification_status=user_reported` cho tới khi có nguồn và
URL chính chủ.
