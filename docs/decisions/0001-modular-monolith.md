# ADR-0001: Modular monolith cho MVP

## Trạng thái

Được chấp nhận cho scaffold MVP

## Ngày

2026-07-22

## Bối cảnh

MVP cần một HTTP webhook gateway và một worker bất đồng bộ, nhưng nghiệp vụ agent, registry, search, voice và audit còn thay đổi nhanh. Nhóm hackathon cần triển khai end-to-end trong sáu sprint ngắn, test được mà không cần Zalo/LLM/STT thật và vẫn giữ ranh giới đủ rõ để tách dịch vụ sau này.

## Quyết định

Dùng một Python project có cấu trúc phẳng trực tiếp dưới `src/`, với hai process độc lập:

- FastAPI process nhận HTTP/webhook và expose health/admin API.
- RQ worker process xử lý STT, agent/search và gửi phản hồi.

Các adapter Zalo, LLM, STT, queue và persistence đi qua interface/port. Logic nghiệp vụ không import SDK provider trực tiếp.

## Các phương án đã cân nhắc

### Microservices ngay từ đầu

Tách deployment và scale độc lập tốt hơn, nhưng tăng contract, network failure, observability và vận hành quá sớm so với phạm vi 20-40 dịch vụ của MVP.

### Một process đồng bộ

Ít thành phần hơn, nhưng STT/LLM có thể làm webhook chậm, khó retry và không đáp ứng nguyên tắc acknowledge sớm trong plan.

### Spring Boot

Là lựa chọn hợp lệ trong plan. Scaffold chọn FastAPI để có vòng lặp prototype gọn và ecosystem Python thuận tiện cho retrieval/evaluation. Đây không phải đánh giá Spring Boot kém phù hợp nói chung.

## Hệ quả

- API và worker dùng chung domain/contracts, giảm duplication.
- Cần kiểm tra dependency direction để entrypoint/infrastructure không rò vào domain.
- Redis vẫn là dependency triển khai riêng dù code là monolith; registry JSON được nạp vào bộ nhớ process.
- Có thể tách module thành service khi có bằng chứng về scale, ownership hoặc isolation; không tách chỉ vì cấu trúc thư mục.
