# Tài liệu kỹ thuật

Thư mục này chuyển kế hoạch sản phẩm thành các quyết định và hướng dẫn có thể kiểm tra bằng code. PDF nguồn được giữ cục bộ ngoài lịch sử Git; khi thay đổi cách triển khai, hãy cập nhật tài liệu Markdown/ADR thay vì sửa trực tiếp PDF.

## Bản đồ tài liệu

| Tài liệu | Mục đích |
| --- | --- |
| [Tổng quan kiến trúc](./architecture/overview.md) | Ranh giới module, luồng text/voice, dữ liệu và trust boundary |
| [ADR-0001](./decisions/0001-modular-monolith.md) | Chọn modular monolith cho MVP |
| [ADR-0002](./decisions/0002-redis-queue.md) | Chọn RQ/Redis cho xử lý bất đồng bộ |
| [ADR-0003](./decisions/0003-registry-source-of-truth.md) | Chọn Service Registry làm nguồn sự thật |
| [ADR-0004](./decisions/0004-multichannel-and-optional-hybrid-retrieval.md) | Mở rộng service đa kênh và hybrid retrieval có kiểm soát |
| [Checklist Zalo](./integrations/zalo-checklist.md) | Các contract/quyền phải xác minh trước khi bật tích hợp thật |
| [Runbook](./operations/runbook.md) | Khởi động, quan sát và xử lý sự cố |
| [Evaluation](./evaluation/README.md) | Schema bộ test và cách đo chất lượng |
| [Demo](./demo/README.md) | Kịch bản và checklist demo |

## Thứ tự ưu tiên khi có mâu thuẫn

1. Contract đã được xác minh từ tài liệu chính thức và fixture/contract test có ngày ghi nhận.
2. ADR đang có trạng thái `Được chấp nhận`.
3. PDF kế hoạch MVP cục bộ, nếu được cấp quyền truy cập, đối với phạm vi sản phẩm và tiêu chí nghiệm thu.
4. README và hướng dẫn vận hành.

Endpoint, payload, signature, token lifecycle, hạn mức và loại tin của Zalo là dữ liệu thay đổi theo phiên bản/quyền ứng dụng. Không lấy ví dụ cũ trên Internet làm contract nếu chưa có bằng chứng và contract test tương ứng.

## Nguồn chính thức

Các liên kết dưới đây được kiểm tra ngày **22/07/2026**:

- FastAPI: [Bigger Applications](https://fastapi.tiangolo.com/tutorial/bigger-applications/), [Settings and Environment Variables](https://fastapi.tiangolo.com/advanced/settings/), [Testing](https://fastapi.tiangolo.com/tutorial/testing/) và [FastAPI in Containers - Docker](https://fastapi.tiangolo.com/deployment/docker/).
- RQ: [RQ documentation](https://python-rq.org/docs/).
- Nâng cấp registry tương lai (không thuộc scaffold hiện tại): [pgvector repository](https://github.com/pgvector/pgvector).
- Zalo: [Developer portal](https://developers.zalo.me/), [documentation home](https://docs.zaloplatforms.com/) và [Open APIs documentation](https://docs.zaloplatforms.com/docs/OA).

Zalo hiện có cả đường dẫn tài liệu cũ và cổng tài liệu mới. Khi triển khai, hãy lưu URL chính xác của trang mô tả event/API đang dùng, ngày truy cập và phiên bản/quyền liên quan trong [checklist tích hợp](./integrations/zalo-checklist.md).
