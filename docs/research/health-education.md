# Khảo sát ứng viên dịch vụ y tế và giáo dục

Ngày kiểm tra: 2026-07-23

## Phạm vi và cách làm

Tệp dữ liệu đi kèm có 10 ứng viên dùng cho hai nhóm `healthcare` và `education`. Việc khảo sát chỉ dùng trang công khai của đơn vị cung cấp, trang Zalo OA công khai và danh sách đối tác trên trang Zalo OA chính thức. Không đăng nhập Zalo, không gọi API ẩn, không thu UID, hội thoại, người theo dõi hoặc dữ liệu người dùng.

Các bản ghi đều có `active: false` và `review_status: candidate`. Đây là dữ liệu staging để kiểm duyệt, không phải danh mục đã được Zalo hay nhóm dự án chứng thực.

## Kết quả

| Nhóm | Ứng viên | Kênh đã xác minh | Dữ liệu đủ dựng card | Ghi chú |
| --- | --- | --- | --- | --- |
| Y tế | Nhà thuốc Long Châu | OA | Có | Zalo liệt kê là đối tác; website chính chủ liên kết cùng OA |
| Y tế | BookingCare | Website | Có | Có tìm cơ sở, bác sĩ, chuyên khoa và đặt lịch |
| Y tế | Vinmec | Website | Có | Có mạng lưới cơ sở, chuyên khoa và đặt lịch |
| Y tế | Mắt Sài Gòn | Website | Có | Phù hợp trực tiếp với truy vấn “khám mắt gần đây” |
| Y tế | Bệnh viện Mắt Trung ương | Website | Có | Phạm vi địa lý xác minh là Hà Nội |
| Giáo dục | Edupia | OA | Có | Zalo liệt kê là đối tác; website chính chủ liên kết cùng OA |
| Giáo dục | VioEdu | Website | Có | Phù hợp truy vấn “học Toán lớp 5” |
| Giáo dục | Monkey Math | Website | Có | Toán bằng tiếng Anh cho mầm non và tiểu học |
| Giáo dục | QANDA | Website | Có | Chat, ảnh bài tập, lời giải AI và hỏi giáo viên |
| Giáo dục | OLM | Website | Có | Học liệu và luyện tập từ mầm non đến lớp 12 |

## Mức xác minh OA

Hai đường dẫn OA của Long Châu và Edupia đều:

- xuất hiện trong dữ liệu `PARTNERS` của `https://oa.zalo.me/home`;
- trả về trang công khai thành công;
- được website chính chủ liên kết tới cùng đường dẫn.

Không quan sát trực tiếp được dấu xác minh trên giao diện OA trong quá trình khảo sát. Vì vậy `oa_badge_status` của cả hai vẫn là `unknown`, không phải `verified`.

Các ứng viên còn lại chỉ được xác minh ở kênh website. Dù footer có biểu tượng Zalo hoặc đơn vị có thể đang vận hành OA/Mini App, dữ liệu không suy diễn loại kênh nếu chưa xác minh được đích chính chủ.

## Khả năng phục vụ giao diện hội thoại

Mỗi bản ghi có đủ các thành phần cơ bản để dựng card như mockup:

- `name`, `provider`, `description`, `logo_url`;
- `launch_url` làm CTA “Mở dịch vụ”;
- `regions` để agent hỏi lại vị trí khi người dùng nói “gần đây”;
- `target_users`, `capabilities`, `aliases` để tìm và xếp hạng;
- `intents[].example_queries` để tạo dữ liệu thử nghiệm cho tin nhắn văn bản hoặc transcript giọng nói;
- `evidence` và `verification` để kiểm duyệt trước khi bật.

Ví dụ luồng y tế:

1. Người dùng: “Tìm chỗ khám mắt cho mẹ gần đây”.
2. Agent nhận diện `find_eye_clinic_nearby`, đối tượng là người lớn tuổi, nhưng còn thiếu khu vực.
3. Agent hỏi một câu về quận/tỉnh.
4. Sau khi có vị trí, agent lọc `regions`, trả tối đa năm card phù hợp và mở website chính chủ.

Ví dụ luồng giáo dục:

1. Người dùng hoặc transcript: “Tìm ứng dụng học toán lớp 5”.
2. Agent so khớp `learn_grade_5_math` và `learn_k12_subject`.
3. VioEdu, OLM, Monkey Math và QANDA có thể được xếp theo nhu cầu cụ thể: học theo chương trình, luyện đề, Toán bằng tiếng Anh hoặc giải bài bằng AI.

## Guardrail trước khi đưa vào registry chính

- Không xem thứ tự kết quả y tế là đánh giá chất lượng chuyên môn hoặc khuyến nghị điều trị.
- Với triệu chứng cấp cứu, agent phải ưu tiên hướng dẫn liên hệ cơ sở cấp cứu thay vì chỉ trả card.
- Kiểm tra lại đường dẫn, mô tả, phạm vi hoạt động và trạng thái dịch vụ theo lịch định kỳ.
- Chỉ đổi `active` sang `true` sau khi người kiểm duyệt xác nhận nguồn, quyền dùng hình ảnh và CTA.
- `logo_url` chỉ là URL tham chiếu công khai; không tự tải, cache hoặc phân phối lại logo khi chưa rõ quyền sử dụng.
- Không thu hay lưu nội dung giọng nói, dữ liệu sức khỏe, hồ sơ học sinh hoặc thông tin định danh trong quá trình khám phá dịch vụ.

## Tệp dữ liệu

`data/research/raw/health_education.json`
