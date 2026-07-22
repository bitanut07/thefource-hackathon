# ADR-0003: Service Registry là nguồn sự thật duy nhất cho đề xuất

## Trạng thái

Được chấp nhận

## Ngày

2026-07-22

## Bối cảnh

MVP không có giả định về API công khai để tìm toàn cục mọi OA/Mini App. Cho phép LLM tự nêu dịch vụ hoặc URL tạo rủi ro hallucination, phishing và kết quả không còn hoạt động.

## Quyết định

Chỉ service record do backend lấy từ Service Registry JSON đã review mới được xuất hiện trong phản hồi. MVP nạp 20-40 record vào bộ nhớ và dùng hard filter, keyword/rule score cùng optional rerank. Mọi candidate phải:

- có `active=true`;
- thỏa hard filter cần thiết;
- có launch URL được kiểm tra theo allowlist;
- có owner và lịch sử/khung thời gian xác minh phù hợp với chính sách vận hành.

LLM nhận candidate đã lọc với ID ổn định để soạn lời giải thích; nó không có quyền thêm tên, ID hoặc URL mới. Response builder đối chiếu output lần cuối với candidate set.

## Các phương án đã cân nhắc

### Cho LLM tìm tự do trên web

Coverage có thể rộng hơn nhưng không kiểm soát nguồn, độ mới và launch URL; không đáp ứng tiêu chí không hallucinate của plan.

### Chỉ keyword search

Dễ giải thích và vận hành, nhưng xử lý kém các cách diễn đạt tự nhiên/voice. Vẫn giữ làm một tín hiệu và fallback trong hybrid search.

### PostgreSQL/pgvector hoặc vector database riêng

Có thể hỗ trợ dữ liệu lớn, full-text/vector retrieval và persistence bền vững, nhưng tăng dependency/vận hành không cần thiết cho registry 20-40 record của hackathon. Đây là hướng nâng cấp tương lai, không thuộc scaffold hiện tại.

## Hệ quả

- Cần quy trình seed/review, ownership, `last_verified_at`, link health check và deactivate nhanh.
- Registry nhỏ có thể tăng no-result rate; giải pháp là cải thiện alias/example query và coverage có kiểm soát, không nới guardrail.
- Dataset minh họa trong repo phải `active=false` và dùng domain an toàn; không được xem là danh mục đã xác minh.
- Audit phải lưu candidate/selection ID để chứng minh phản hồi không vượt registry.
