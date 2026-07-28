# ADR-0004: Mở rộng đa kênh và hybrid retrieval có kiểm soát

## Trạng thái

Được chấp nhận cho phạm vi MVP

## Ngày

2026-07-23

## Bối cảnh

Kế hoạch ban đầu tập trung vào trợ lý tìm OA/Mini App trên Zalo, với Service Registry nhỏ, đã review và có guardrail chống hallucination. Nhu cầu thực tế có thể dẫn tới cùng một dịch vụ qua nhiều kênh như Zalo OA, Zalo Mini App, website, ứng dụng di động, hotline, địa điểm vật lý hoặc ứng dụng nội bộ. Câu hỏi tự nhiên cũng có thể chứa ngữ cảnh tổ chức, địa điểm và quyền truy cập, ví dụ nhân viên VNG tìm đồ ăn tại VNG Campus.

Mở rộng schema và retrieval giúp bao phủ các trường hợp này, nhưng không được biến MVP thành crawler/RAG tổng quát hoặc làm yếu quyết định trong ADR-0003. Đặc biệt, dữ liệu thu thập được và kết quả do LLM suy luận không đủ điều kiện để tự động trở thành dịch vụ có thể đề xuất hoặc có nút mở.

## Quyết định

### Giữ nguyên nguồn sự thật và phạm vi MVP

Service Registry tiếp tục là nguồn sự thật duy nhất cho:

- service ID và channel ID được phép xuất hiện trong phản hồi;
- tên, loại dịch vụ và metadata vận hành được công bố;
- launch URL hoặc thông tin liên hệ được phép đưa cho người dùng;
- trạng thái `active`, trạng thái xác minh, owner và thời điểm xác minh.

MVP tiếp tục giới hạn khoảng 20-40 dịch vụ đã review. Dữ liệu nghiên cứu/cào có thể được lưu làm evidence hoặc nguồn đề xuất record, nhưng không tự động kích hoạt record, tạo ID công bố hay tạo launch URL. Chỉ candidate đã qua Registry, hard filter và URL allowlist mới được chuyển cho response builder.

### Xem OA là một channel của service

Một service có thể có nhiều channel, trong đó Zalo OA là một loại bên cạnh Zalo Mini App, website, mobile deep link, hotline, địa điểm vật lý và kênh nội bộ. Search xếp hạng service trước; backend sau đó chọn channel đủ điều kiện theo ngữ cảnh client, quyền truy cập, trạng thái xác minh và chính sách ưu tiên.

Việc thêm channel không làm thay đổi guardrail:

- channel chưa xác minh hoặc không hoạt động không được tạo CTA;
- URL không có trong Registry hoặc không qua allowlist bị loại;
- Gemini không được tự tạo, sửa hoặc chọn URL ngoài candidate set;
- dữ liệu chỉ có evidence nhưng chưa có published channel có thể được giữ để review, không được trình bày như dịch vụ đang hoạt động.

### Giữ baseline đơn giản, cho phép rerank tùy chọn

Baseline của MVP vẫn là hard filter theo các trường có cấu trúc, sau đó keyword/rule score trên tập record nhỏ trong bộ nhớ. Đây là đường chạy bắt buộc và là fallback khi provider hoặc retrieval bổ sung không khả dụng.

BM25 và vector similarity có thể được thêm như tín hiệu retrieval/rerank tùy chọn để xử lý cách diễn đạt tự nhiên tốt hơn. Các tín hiệu này:

- chỉ được tìm hoặc xếp hạng trong candidate universe mà backend kiểm soát;
- không được kích hoạt record chưa review;
- không được nới hard filter về `active`, location, organization, eligibility hoặc trạng thái xác minh;
- không được bỏ qua URL allowlist hay bước đối chiếu cuối của response builder;
- phải có đánh giá offline chứng minh cải thiện trước khi trở thành mặc định.

Top-K nội bộ có thể lớn hơn số card hiển thị để hỗ trợ rerank hoặc soạn lời giải thích, nhưng phản hồi người dùng vẫn tuân theo giới hạn tối đa năm dịch vụ của kế hoạch MVP.

### Tích hợp Gemini qua adapter

Gemini được gọi qua LLM adapter/port của kiến trúc modular monolith, không được import SDK trực tiếp vào domain. Runtime thật có thể cấu hình Gemini để trích xuất structured query và soạn lời giải thích từ candidate đã lọc. Schema output phải được validate và mọi service/channel trong output phải được đối chiếu lại với candidate set.

Fake/local adapter vẫn được giữ cho unit test, integration test và CI để test không phụ thuộc mạng, quota hoặc secret. Nó không phải provider mặc định của môi trường chạy thật. API key chỉ được nạp từ secret/environment configuration, không được commit vào repository, log hoặc fixture.

### Hoãn hạ tầng tìm kiếm lớn

JSON/in-memory Registry và baseline search đủ cho 20-40 service của MVP. PostgreSQL, pgvector, vector database riêng hoặc search cluster chỉ được xem xét khi có bằng chứng về quy mô dữ liệu, tải đồng thời, nhu cầu quản trị nhiều người hoặc kết quả đánh giá cho thấy giải pháp hiện tại không đáp ứng.

## Luồng MVP sau quyết định

1. Nhận tin nhắn và dùng Gemini adapter hoặc fallback để trích xuất structured query.
2. Registry áp dụng hard filter theo trạng thái, category, location, organization và eligibility.
3. Keyword/rule score xếp hạng candidate; BM25/vector có thể rerank trong cùng candidate universe.
4. Backend chọn channel đã xác minh và kiểm tra URL allowlist.
5. Response composer deterministic là baseline an toàn. Gemini có thể được bật
   để soạn lời giải thích từ candidate đã khóa sau khi có schema đối chiếu
   ID/URL và evaluation chứng minh lợi ích.
6. Response builder đối chiếu ID/URL và trả tối đa năm service card; điểm ranking
   nội bộ không đi ra API.

## Các phương án đã cân nhắc

### Cho RAG trả trực tiếp dữ liệu đã cào

Coverage cao hơn nhưng không có ranh giới rõ giữa evidence và dịch vụ được công bố. Cách này có thể phát tán tên sai, link giả hoặc channel đã ngừng hoạt động, nên không được chọn.

### Chuyển toàn bộ Registry sang vector database ngay

Không mang lại lợi ích vận hành tương xứng cho 20-40 service, đồng thời tăng dependency, migration và điểm lỗi. Vector retrieval chỉ là tín hiệu tùy chọn, không thay Service Registry.

### Loại bỏ fake adapter khi bật Gemini

Làm test/CI phụ thuộc provider, quota và secret, gây flakiness và khó kiểm chứng failure path. Fake adapter vẫn cần thiết nhưng được tách khỏi cấu hình runtime thật.

## Hệ quả

- Schema Registry cần tách khái niệm service và channel mà vẫn tương thích với record MVP hiện có.
- Dữ liệu nghiên cứu phải có trạng thái provenance/xác minh rõ và cần bước review trước khi publish.
- Evaluation cần đo cả chất lượng intent extraction, retrieval/rerank, hard-filter violations và tính toàn vẹn ID/URL.
- Runtime thật cần xử lý timeout, quota, retry có giới hạn và fallback khi Gemini không khả dụng.
- Việc mở rộng sang dịch vụ ngoài OA không đổi thứ tự sprint hay tiêu chí tối đa năm đề xuất của kế hoạch ban đầu.
- Quyết định này bổ sung ADR-0003; nếu có mâu thuẫn, ràng buộc Registry là nguồn sự thật và URL allowlist của ADR-0003 được ưu tiên.
