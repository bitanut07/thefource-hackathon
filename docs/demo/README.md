# Kịch bản kiểm chứng API text và demo mục tiêu

## Trạng thái hiện tại

`POST /api/v1/navigate` là API text thật của ứng dụng. Endpoint dùng Gemini để
trích xuất structured query, sau đó backend tìm trong
`data/registry/services.real.json`, áp dụng hard filter/ranking/URL allowlist và
trả tối đa ba candidate.

Registry hiện có 8 dịch vụ với danh tính và liên kết công khai đã review. Đây là
lát cắt để kiểm chứng flow, chưa đạt mục tiêu 20-40 dịch vụ của Sprint 2 và không
đồng nghĩa mọi OA badge hoặc khả năng giao dịch bên trong channel đã được xác
minh.

Webhook `POST /webhooks/zalo` vẫn trả
`501 ZALO_CONTRACT_NOT_CONFIGURED`. Vì vậy phần chạy được hiện tại là API text,
không phải tích hợp OA production. Voice/STT và gửi phản hồi qua Zalo vẫn thuộc
các sprint tiếp theo.

## Thông điệp chính

Prototype cần chứng minh AI hiểu nhu cầu tự nhiên nhưng không quyết định tên,
service ID hoặc URL. Gemini chỉ tạo structured query; Service Registry và
allowlist mới quyết định candidate nào được trả về. Dữ liệu nghiên cứu chưa
review không được tự động kích hoạt.

Không mô tả hệ thống là công cụ tìm toàn bộ hệ sinh thái Zalo hoặc là hệ thống
tự thực hiện giao dịch. OA là một channel trong Service Catalog có kiểm soát.

## Điều kiện kiểm chứng API text

- [ ] Commit/tag kiểm chứng đã cố định; `make check PYTHON=.venv/bin/python` và
  Docker build pass.
- [ ] `.env` giữ `LLM_PROVIDER=gemini`, có `GEMINI_API_KEY` mới và một
  `NAVIGATOR_API_KEY` riêng; secret không xuất hiện trên màn hình quay.
- [ ] Redis sẵn sàng và `GET /health/ready` trả `200`.
- [ ] 8 record trong `data/registry/services.real.json` load thành công; URL
  thuộc `ALLOWED_LAUNCH_HOSTS`.
- [ ] Fake LLM adapter chỉ được dùng trong test/CI, không dùng để trình bày
  runtime thật.
- [ ] Text rõ ràng, hỏi lại, no-result, out-of-scope và lỗi provider đã được
  smoke test.

## Chạy API hiện tại

Ở terminal A:

```bash
make setup
uv sync --locked --extra dev --link-mode copy
# Đặt GEMINI_API_KEY mới đã rotate và NAVIGATOR_API_KEY riêng trong .env.
make dev
```

Ở terminal B:

```bash
curl --fail http://localhost:8000/health/live
curl --fail http://localhost:8000/health/ready
read -rsp "NAVIGATOR_API_KEY: " NAVIGATOR_API_KEY && echo
curl --fail \
  -H "Content-Type: application/json" \
  -H "X-API-Key: $NAVIGATOR_API_KEY" \
  -d '{"text":"Tôi muốn đóng tiền điện ở TP.HCM."}' \
  http://localhost:8000/api/v1/navigate
```

Có thể dùng Swagger tại `http://localhost:8000/docs`, bấm **Authorize** và nhập
`NAVIGATOR_API_KEY`. Dùng `/api/v1/intents/extract` để xem JSON Gemini,
`/api/v1/services` để xem Registry, `/api/v1/research/search` để xem dữ liệu
research-only và `/api/v1/navigate` để test end-to-end. Key sai trả `401`, quá
tải trả `429`, thiếu cấu hình trả `503`; provider lỗi/JSON sai schema trả `502`.

## Kịch bản 1 - Text rõ ràng

1. Gửi: “Tôi muốn đóng tiền điện ở TP.HCM.”
2. Gemini trích xuất nhu cầu có cấu trúc, không đề xuất URL.
3. Backend trả tối đa ba dịch vụ từ Registry và làm nổi bật lý do khớp.
4. Đối chiếu `service_id` và `launch_url` trong response với Registry để chứng
   minh không bịa link.

## Kịch bản 2 - Tìm dịch vụ y tế

1. Gửi: “Tìm chỗ khám mắt cho mẹ ở TP.HCM.”
2. Kiểm tra structured context dẫn tới candidate y tế phù hợp.
3. Xác nhận URL chỉ thuộc allowlist và không có dịch vụ ngoài 8 record hiện tại.

## Kịch bản 3 - Mua sắm

1. Gửi: “Tôi cần tìm siêu thị mua thực phẩm.”
2. Kiểm tra kết quả thuộc category `shopping_delivery`.
3. Không suy diễn các quán/căng-tin nội bộ chưa có record và URL đã review.

## Kịch bản 4 - No-result và guardrail

1. Gửi một yêu cầu không có trong Registry hoặc yêu cầu mô hình tạo URL bất kỳ.
2. Bot trả no-result/out-of-scope phù hợp.
3. Response không chứa service/URL ngoài candidate set.

## Kịch bản OA/voice mục tiêu

Các kịch bản sau chỉ được trình bày như năng lực đã chạy sau khi hoàn tất checklist
Zalo, contract test và sprint tương ứng:

1. Zalo OA gửi webhook text, gateway xác minh signature/idempotency, enqueue và
   acknowledge sớm.
2. Voice ngắn được tải tạm, STT trả transcript/confidence, bot hỏi xác nhận khi
   confidence thấp và cleanup audio theo policy.
3. OA adapter gửi response bằng loại tin đã được Zalo hỗ trợ và kiểm chứng.

Cho đến thời điểm đó, phản hồi `501` của webhook là safety gate đúng thiết kế,
không phải bằng chứng OA đã tích hợp.

## Danh sách kiểm tra trước khi trình bày

- [ ] `/health/live` và `/health/ready` xanh; queue không backlog; clock máy đúng.
- [ ] Gemini key và Navigator API key còn hiệu lực, không xuất hiện trong
  terminal/log; quota Gemini đủ.
- [ ] Registry/link verification chạy gần thời điểm trình bày; 8 record hiện tại
  được mô tả đúng là lát cắt đã review, mục tiêu vẫn là 20-40.
- [ ] Không tuyên bố OA production, voice hoặc giao dịch trong OA đã hoạt động.
- [ ] UID/token/raw event/audio không xuất hiện trong terminal/dashboard.
- [ ] Có câu fallback và điểm dừng nếu provider hoặc dịch vụ công khai lỗi.
- [ ] Ghi lại config/commit cùng metrics của từng scenario để review.
