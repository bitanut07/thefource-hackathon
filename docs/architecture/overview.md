# Tổng quan kiến trúc mục tiêu của MVP

## Trạng thái runtime hiện tại

Luồng text chạy đồng bộ qua `POST /api/v1/navigate`: Gemini trích xuất
structured query, Registry áp dụng hard filter và ranking, URL policy kiểm tra
allowlist, rồi response builder trả tối đa ba candidate. Runtime đọc
`data/registry/services.real.json`, hiện có 8 dịch vụ với danh tính và liên kết
công khai đã review; mục tiêu MVP vẫn là 20-40 dịch vụ.

`/health/ready` yêu cầu có Gemini key, Navigator API key, Registry đang hoạt
động, allowlist bao phủ các URL và Redis sẵn sàng; cấu hình sai trả `503`.
Registry được validate fail-fast khi API dựng pipeline lúc khởi động và khi
worker dựng pipeline để xử lý job. API text xác thực `X-API-Key` và giới hạn số
lệnh Gemini đồng thời. Fake LLM adapter chỉ được inject trong test/CI.

Webhook Zalo vẫn cố ý trả `501 ZALO_CONTRACT_NOT_CONFIGURED`. Signature,
idempotency, Zalo send-message, OA token lifecycle và voice/STT thật vẫn phải
được hoàn thiện trước khi bật tích hợp Zalo production.

## Bối cảnh và phạm vi

Zalo AI Service Navigator là một trợ lý triển khai dưới dạng Zalo Official Account (OA). MVP nhận text hoặc voice message, chuyển voice thành text khi cần, trích xuất nhu cầu có cấu trúc, tìm trong Service Registry do nhóm kiểm soát và trả tối đa ba lựa chọn hợp lệ.

MVP **không** tìm toàn bộ OA/Mini App trên Zalo, không tự đặt lịch/thanh toán và
không để mô hình ngôn ngữ tự tạo tên dịch vụ hoặc URL. Các nhóm theo kế hoạch
ban đầu là y tế, điện/nước/tiện ích, giáo dục và giao thông/dịch vụ công;
`shopping_delivery` là mở rộng có kiểm soát theo ADR-0004, không biến hệ thống
thành RAG/crawler tổng quát.

Stack được chọn cho scaffold:

- FastAPI cho HTTP API và webhook gateway.
- RQ trên Redis cho hàng đợi công việc.
- File JSON được review và nạp vào bộ nhớ cho Service Registry 20-40 record.
- Gemini qua LLM adapter; adapter Zalo OA và STT vẫn là các cổng chưa bật thật.

## Luồng API text đang chạy

```mermaid
flowchart LR
    C["API client"] -->|"POST /api/v1/navigate"| API["FastAPI"]
    API --> LLM["Gemini adapter: structured query"]
    API --> REG["Service Registry: 8 record đã review"]
    REG --> FILTER["Hard filter + ranking + URL allowlist"]
    FILTER --> RESP["Tối đa 3 service card"]
```

Gemini chỉ trích xuất nhu cầu. Service ID, tên và URL trong phản hồi phải đến từ
candidate set của Registry. API này là bề mặt kiểm chứng text trước khi nối OA;
nó không chứng minh webhook hoặc gửi tin Zalo đã hoạt động.

## Sơ đồ thành phần mục tiêu

```mermaid
flowchart LR
    U["Người dùng Zalo"] -->|"Text / voice message"| OA["Zalo OA"]
    OA -->|"Webhook HTTPS"| API["FastAPI webhook gateway"]
    API -->|"Xác minh + idempotency"| Q["RQ / Redis"]
    Q --> W["Agent worker"]
    W -->|"Nếu có audio"| STT["STT adapter"]
    W --> LLM["LLM adapter: structured query"]
    W --> REG["Service Registry JSON / bộ nhớ"]
    W --> AUDIT["Query & audit log"]
    W --> ZALO["Zalo OA adapter"]
    ZALO --> OA
```

Webhook chỉ xác minh, chuẩn hóa envelope, kiểm tra idempotency và enqueue. STT, LLM, search và gửi phản hồi chạy ở worker để webhook có thể acknowledge sớm sau khi event hợp lệ được ghi nhận.

## Ranh giới module

Toàn bộ mã ứng dụng nằm trực tiếp dưới `src/` theo cấu trúc phẳng, tương ứng với các khối mà nhóm cần làm:

```text
main.py / api / worker
          |
          v
        skills
          |
          v
domain + llm + voice + zalo
```

- `api`: route health và webhook; không chứa thuật toán search hay prompt.
- `worker`: RQ jobs và wiring; không chứa nghiệp vụ riêng.
- `skills`: điều phối text/voice, clarification, search và response policy.
- `domain`: model, registry JSON, search, URL policy, audit và privacy.
- `llm`: schema/client cho provider LLM.
- `voice`: tải tạm, gọi STT, confidence flow và cleanup theo retention.
- `zalo`: xác minh webhook và gửi phản hồi qua Zalo OA.
- `config.py` và `main.py`: cấu hình cùng FastAPI entrypoint tối thiểu.

`domain` không phụ thuộc trực tiếp SDK của provider. Runtime gọi Gemini qua LLM
adapter và chỉ hỗ trợ `LLM_PROVIDER=gemini`; test/CI inject fake adapter để không
phụ thuộc secret, quota hoặc network.

## Luồng text và voice

```mermaid
sequenceDiagram
    participant Z as Zalo OA
    participant A as API
    participant R as Redis/RQ
    participant W as Worker
    participant S as STT
    participant D as Registry
    participant O as OA adapter

    Z->>A: Webhook event
    A->>A: Kiểm tra contract/signature và chống trùng
    A->>R: Đưa event chuẩn hóa vào hàng đợi
    A-->>Z: Xác nhận đã nhận
    R->>W: Giao job
    opt Tin nhắn voice
        W->>S: Audio tạm -> transcript
        S-->>W: Text + confidence nếu có
    end
    W->>D: Truy vấn cấu trúc + lọc cứng
    D-->>W: Candidate hợp lệ đã xếp hạng
    W->>O: Phản hồi chỉ từ candidate hợp lệ
    O-->>Z: Loại tin được hỗ trợ
```

Chi tiết signature, event name, trường audio, endpoint gửi tin và token lifecycle chưa được giả định trong sơ đồ. Chúng chỉ được hiện thực sau khi hoàn tất [checklist Zalo](../integrations/zalo-checklist.md).

## Tìm kiếm và quyền quyết định

Pipeline bám theo plan:

1. Chuẩn hóa lỗi chính tả, tên địa phương và alias.
2. Lọc cứng theo `active`, category và vùng khi có.
3. Keyword search trên tên, alias, mô tả và intent trong registry bộ nhớ.
4. Tính điểm rule-based; có thể rerank một tập ứng viên nhỏ.
5. Kiểm tra URL theo allowlist trước khi tạo phản hồi.

Kho tri thức SQLite/FTS phục vụ staging và nghiên cứu không được nối trực tiếp
vào quyết định candidate của endpoint hiện tại. BM25/vector chỉ có thể là tín
hiệu rerank tùy chọn sau khi có đánh giá; chúng không được kích hoạt record chưa
review hoặc bỏ qua allowlist. PostgreSQL/pgvector chỉ được xem xét khi
registry/traffic vượt phạm vi hackathon.

Mô hình ngôn ngữ chỉ được phép trả structured query và diễn đạt kết quả do backend cung cấp. Registry/search backend là thành phần duy nhất quyết định service ID và launch URL nào có thể xuất hiện.

## Dữ liệu tối thiểu

Registry JSON cần biểu diễn ít nhất:

- `service`: tên, provider, loại dịch vụ, category, mô tả, vùng, target user, launch URL, `active`, `owner`, `last_verified_at` và priority.
- `service_alias`: các cách gọi đời thường, viết tắt hoặc lỗi phát âm.
- `service_intent`: intent và example query.

Runtime hiện đọc `data/registry/services.real.json` với 8 record `active=true`
đã review danh tính và URL công khai. Con số này mới là lát cắt kiểm chứng API,
chưa đạt mục tiêu 20-40 dịch vụ của Sprint 2 và không đồng nghĩa mọi OA badge
hoặc khả năng giao dịch bên trong từng channel đã được xác minh.

Audit runtime mục tiêu là cấu trúc riêng, không nằm trong file registry: message/event correlation ID, UID đã giảm thiểu hoặc hash, query chuẩn hóa, intent, lựa chọn và confidence. Persistence audit bền vững chưa thuộc scaffold hiện tại.

Audio là dữ liệu tạm thời, không phải dữ liệu registry. Thời hạn lưu, nơi lưu và cơ chế xóa phải được chốt trước khi bật voice thật.

## Độ tin cậy và bảo mật bắt buộc

- HTTPS và xác minh webhook theo contract Zalo hiện hành.
- Idempotency theo định danh event/message đã xác minh.
- Token/secret chỉ qua biến môi trường hoặc secret manager; không ghi log.
- Gemini key thiếu/rỗng làm readiness/API điều hướng trả `503`; key từng bị
  công khai phải được rotate trước khi sử dụng.
- `NAVIGATOR_API_KEY` độc lập bảo vệ API text; key sai trả `401`, hết slot xử lý
  trả `429` kèm `Retry-After`.
- Retry có giới hạn, backoff và nơi cách ly failed jobs để tránh vòng lặp.
- Hash/giảm thiểu UID trong analytics; cấu hình retention cho audio/log.
- URL allowlist, schema validation và tách system policy khỏi input người dùng.
- Timeout/circuit-breaker hợp lý cho LLM, STT và OA API; fallback rõ ràng.

## Observability và tiêu chí nghiệm thu

Mỗi flow cần correlation ID xuyên suốt API, queue và worker. Theo dõi tối thiểu webhook latency, queue lag, STT/LLM latency, lỗi OA API, invalid signature, duplicate event, URL bị chặn và fallback.

Chất lượng sản phẩm được đo bằng intent accuracy, slot extraction F1, Recall@3, Top-1 accuracy, no-result/clarification rate, median/P95 latency, STT success/confirm-again rate và click/select rate. Ngưỡng mục tiêu vẫn là quyết định cần chốt; không hard-code một ngưỡng không có chủ sở hữu.
