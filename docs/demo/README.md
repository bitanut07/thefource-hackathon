# Kịch bản demo mục tiêu của MVP

## Thông điệp chính

Khi được hoàn thiện, prototype cần kiểm chứng ba năng lực trong phạm vi OA: hiểu nhu cầu bằng ngôn ngữ tự nhiên, định tuyến qua nhiều loại dịch vụ trong registry có kiểm soát và nhận voice message cho người dùng ngại gõ. Skeleton hiện chưa chạy các luồng này: webhook trả `501`, worker chưa nối adapter. Không mô tả skeleton là demo hoàn chỉnh, là tìm kiếm toàn bộ hệ sinh thái Zalo hoặc là hệ thống tự thực hiện giao dịch.

## Điều kiện trước demo

- [ ] Commit/tag demo đã cố định; `make check PYTHON=.venv/bin/python` và Docker build pass.
- [ ] OA/Zalo App/gói/quyền và contract đã hoàn tất [checklist](../integrations/zalo-checklist.md).
- [ ] Registry demo có 20-40 record do owner xác minh, link hoạt động, `active=true` và `last_verified_at` còn hiệu lực.
- [ ] Không dùng `data/seed/services.example.json` như dịch vụ thật; bốn record đó là dữ liệu giả, `active=false`.
- [ ] Fake/real provider được ghi rõ; secret không xuất hiện trên màn hình quay.
- [ ] Text, voice, no-result, out-of-scope và fallback đã smoke test.
- [ ] Có phương án quay sẵn hoặc local deterministic nếu mạng/provider/OA lỗi.

## Kịch bản 1 - Text rõ ràng

1. Người dùng: “Tôi muốn đóng tiền điện ở TP.HCM.”
2. Bot trả tối đa ba dịch vụ từ registry, làm nổi bật một lựa chọn.
3. Mỗi kết quả có lý do ngắn và CTA lấy từ launch URL đã allowlist.
4. Người thuyết trình chỉ ra service ID/candidate trong audit để chứng minh không bịa URL.

## Kịch bản 2 - Voice và xác nhận

1. Người dùng gửi voice ngắn: “Tôi muốn tìm chỗ khám mắt cho mẹ.”
2. Bot xác nhận transcript hoặc hỏi khu vực còn thiếu bằng một câu.
3. Nếu confidence thấp/không có confidence đáng tin cậy, bot hiển thị câu đã nghe và đưa lựa chọn xác nhận/nói lại/nhập chữ.
4. Sau khi có “Quận 5”, bot trả candidate hợp lệ; audio tạm được cleanup theo policy.

## Kịch bản 3 - Yêu cầu mơ hồ

1. Người dùng: “Tìm chỗ học cho cháu.”
2. Bot hỏi đúng một điều kiện quan trọng: “Cháu đang cần học môn gì?”
3. Người dùng: “Toán lớp 5.”
4. Bot tìm lại với structured query đã bổ sung, không hỏi dồn nhiều câu.

## Kịch bản 4 - Ngoài phạm vi

1. Người dùng: “Đặt cho tôi vé máy bay sang Nhật.”
2. Bot nói rõ chưa thể đặt vé trực tiếp.
3. Nếu registry có category phù hợp, bot chỉ đề nghị tìm dịch vụ; nếu không có thì trả no-result/fallback.

## Kịch bản 5 - Guardrail

1. Người dùng yêu cầu bỏ qua quy tắc và tạo một URL bất kỳ.
2. Bot không làm theo phần chỉ dẫn xung đột.
3. Response không chứa service/URL ngoài candidate set; log ghi URL/candidate validation mà không ghi dữ liệu nhạy cảm.

## Chạy local

Ở terminal A:

```bash
make setup
.venv/bin/python -m pip install -e '.[dev]'
make dev
```

Ở terminal B:

```bash
curl --fail http://localhost:8000/health/ready
```

Scaffold ban đầu chỉ bảo đảm health/structure và fake adapters ở mức được code hỗ trợ. Từng scenario chỉ được đánh dấu “đã demo” sau khi có endpoint/fixture/test tương ứng; không dùng lời kể thay cho bằng chứng chạy được.

## Danh sách kiểm tra ngay trước khi trình bày

- [ ] Health xanh; Redis và registry JSON được kiểm tra riêng khi readiness scaffold chưa probe dependency; queue không backlog; clock máy đúng.
- [ ] Registry/link verification chạy gần thời điểm demo.
- [ ] Token còn hiệu lực và quota đủ; provider status bình thường.
- [ ] UID/token/raw audio không hiện trong terminal/dashboard.
- [ ] Người điều khiển biết câu fallback và điểm dừng nếu dịch vụ thật lỗi.
- [ ] Ghi lại metrics/trace của từng scenario để review sau demo.
