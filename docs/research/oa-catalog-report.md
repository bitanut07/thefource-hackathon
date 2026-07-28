# Báo cáo dữ liệu cho AI Service Navigator

Ngày tổng hợp: 2026-07-24

## Kết quả hiện tại

Dataset staging có **83 ứng viên**, phủ đủ 8 nhóm dịch vụ trong mockup:

| Nhóm | Tổng | OA | Website | Tin cậy cao | Cần review thêm |
| --- | ---: | ---: | ---: | ---: | ---: |
| Điện, nước & tiện ích | 6 | 4 | 2 | 5 | 1 |
| Y tế & sức khỏe | 10 | 6 | 4 | 9 | 1 |
| Giáo dục & đào tạo | 10 | 6 | 4 | 10 | 0 |
| Giao thông & du lịch | 5 | 5 | 0 | 3 | 2 |
| Dịch vụ công | 10 | 6 | 4 | 8 | 2 |
| Tài chính & ngân hàng | 8 | 5 | 3 | 6 | 2 |
| Mua sắm & giao hàng | 30 | 30 | 0 | 26 | 4 |
| Giải trí | 4 | 4 | 0 | 1 | 3 |
| **Tổng** | **83** | **66** | **17** | **68** | **15** |

Cả 66 OA đều dùng deeplink số `https://zalo.me/<OA_ID>`. Các record mức `high`
có nguồn chính chủ hoặc chuỗi ánh xạ Zalo đủ mạnh; 15 record mức `medium` tiếp
tục nằm ở tầng review vì thiếu backlink trực tiếp, có phạm vi chưa rõ hoặc cần
kiểm tra lại danh tính trong ứng dụng. Chi tiết batch 29 OA nằm trong
[`additional-oa-2026-07-24.md`](additional-oa-2026-07-24.md); batch 21 OA ăn
uống nằm trong
[`additional-food-oa-2026-07-24.md`](additional-food-oa-2026-07-24.md).

## Đủ gì để dựng hội thoại như mockup

Mỗi record đã có:

- card: `name`, `provider`, `description`, `logo_url`, `cta_label`, `launch_url`;
- hiểu nhu cầu: `category`, `subcategory`, `capabilities`, `aliases`;
- tìm kiếm bằng text hoặc transcript: `intents[].example_queries`;
- hỏi lại khi thiếu thông tin: `regions`, `target_users` và
  `organization_contexts`;
- kiểm duyệt: `evidence`, `verification`, `active`, `review_status`.

Luồng đề xuất:

1. Chuẩn hóa tin nhắn hoặc transcript thành intent, category, khu vực và đối
   tượng.
2. Nếu truy vấn có “gần đây” nhưng thiếu địa điểm, chỉ hỏi lại một câu về khu vực.
3. Lọc từ registry đã duyệt và xếp hạng theo intent, alias, capability, region.
4. Trả tối đa năm card; tên, logo và URL chỉ lấy từ registry, không để LLM tự tạo.
5. Voice dùng chung pipeline với text và không lưu audio sau xử lý.

## Chưa được phép coi là production-ready

- Cả 66 OA đều có `oa_badge_status=unknown`. Public HTML không cung cấp bằng
  chứng đủ để gắn nhãn “đã xác minh”; reviewer cần mở từng OA trong ứng dụng Zalo.
- Logo chỉ là URL tham chiếu. Một record CGV chưa có logo phù hợp, và mọi asset
  cần kiểm tra quyền sử dụng trước khi cache hoặc phân phối.
- Runtime API đã hiểu thêm nhóm ăn uống/mua sắm và ngữ cảnh công ty, nhưng schema
  registry vẫn chưa có logo, capabilities, evidence hoặc trạng thái review. Dataset
  nghiên cứu này chưa được nạp trực tiếp vào registry chạy thật
  `data/registry/services.real.json`; các record chưa qua gate chỉ được đưa vào kho
  RAG nghiên cứu và không có quyền tạo launch URL.
- Các hostname mới chưa được đưa vào `ALLOWED_LAUNCH_HOSTS`; chỉ bổ sung
  allowlist cho record đã qua review, không mở wildcard.
- Dữ liệu đã đủ rộng để thử retrieval, nhưng độ phủ không đồng nghĩa đã được
  phép launch. Ưu tiên review lại 15 record `medium` và kiểm thử các OA có tác
  động cao trước demo diện rộng.
- Với y tế, tài chính và dịch vụ công, Navigator chỉ tìm và điều hướng. Không nhận
  OTP, mật khẩu, dữ liệu sức khỏe, mã định danh hay hồ sơ người dùng.

## Trường hợp VNG Campus

Query “Là nhân viên VNG hiện tôi cần mua đồ ăn” đã có thể được chuẩn hóa thành
`category=shopping_delivery`, `intent=find_food_service`,
`target_user=vng_employee` và `organization=VNG`. Registry chạy thật chỉ trả các
record đã qua gate; hệ thống không tự tạo tên OA hoặc URL để lấp chỗ trống.

Ba Sao và Danh Hoa đang nằm trong
`data/research/pending/vng-campus-food.json` ở trạng thái người dùng cung cấp,
không có launch URL và không được đưa vào active catalog. Highlands Rewards và
Phúc Long Rewards chỉ là tham chiếu Mini App công khai; chưa có bằng chứng chúng
hiện diện hoặc nhận đặt món tại VNG Campus.

Chạy `uv run python scripts/build_rag_db.py` để đưa catalog research và pending facts
vào `data/rag/service-catalog.sqlite3`. Kho SQLite này chỉ phục vụ tra cứu
knowledge staging qua `POST /api/v1/research/search`; nó chưa thay thế Service
Registry của API điều hướng và mọi record chưa qua gate vẫn `launchable=false`.
Index hiện có 88 tài liệu, gồm 83 record catalog và 5 tài liệu context/pending.

## Gate kích hoạt

Chỉ chuyển một record sang registry chạy thật sau khi:

1. xác nhận badge OA hoặc quyền sở hữu kênh;
2. kiểm thử CTA/menu thực tế và phạm vi chức năng;
3. xác nhận quyền sử dụng logo;
4. link health check đạt;
5. có owner và lịch tái kiểm tra;
6. chuyển `active=true` trong một PR review riêng.
