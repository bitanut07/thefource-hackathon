# Nghiên cứu pending: dịch vụ ăn uống tại VNG Campus

Ngày kiểm tra: 2026-07-23

## Kết luận

Chưa có bản ghi nào đủ điều kiện đưa vào active catalog.

Nguồn chính chủ của VNG chỉ xác nhận VNG Campus có:

- canteen;
- siêu thị tiện lợi;
- phòng cung cấp thức ăn nhẹ;
- đồ uống miễn phí.

Nguồn này không nêu tên nhà vận hành, thương hiệu, thực đơn, giá, giờ mở cửa, đường dẫn dịch vụ hay khả năng đặt món. Vì vậy không thể dùng nó để xác nhận một nhà hàng hoặc quán cụ thể đang hoạt động tại Campus.

Nguồn: [Giới thiệu về VNG](https://career.vng.com.vn/vi/gioi-thieu-ve-vng).

## Ba Sao và Danh Hoa

Hai tên này được lưu đúng trạng thái `user_reported`:

| Tên | Nguồn | Launch URL | Trạng thái |
| --- | --- | --- | --- |
| Ba Sao | Người dùng cung cấp | `null` | `needs_official_url` |
| Danh Hoa | Người dùng cung cấp | `null` | `needs_official_url` |

Không suy đoán OA, Mini App, website, địa chỉ hoặc pháp nhân từ tên gọi. Để nâng cấp thành candidate có thể kiểm duyệt, cần ít nhất một nguồn chính chủ công khai liên kết tên dịch vụ với VNG Campus và một URL mở dịch vụ hợp lệ.

## Tham chiếu Mini App công khai

Hai đường dẫn sau mở được và metadata công khai nhận diện đúng tên:

- [Highlands Rewards](https://zalo.me/s/327411629127312067/)
- [Phúc Long Rewards](https://zalo.me/s/2001374113466962529/)

Chúng chỉ là tham chiếu Mini App công khai. Không có bằng chứng trong phạm vi khảo sát này rằng Highlands hoặc Phúc Long hiện diện tại VNG Campus. Việc đường dẫn mở được cũng không chứng minh Mini App hỗ trợ đặt món, nhận tại Campus hoặc giao tới Campus.

Do đó cả hai được giữ ở `review_status: reference_only`, `active: false`.

## Điều kiện để tiếp tục xác minh

Một dịch vụ ăn uống chỉ nên được đề xuất trong AI Service Navigator khi có đủ:

1. nguồn chính chủ xác nhận tên và mối liên hệ với VNG Campus;
2. URL OA, Mini App hoặc website do chính đơn vị công bố;
3. CTA thực sự phục vụ nhu cầu người dùng, ví dụ xem thực đơn hoặc đặt món;
4. kiểm tra thủ công về phạm vi phục vụ, giờ hoạt động và điều kiện sử dụng;
5. bằng chứng được ghi ngày kiểm tra và record vẫn để `active: false` cho tới khi duyệt.

## Tệp dữ liệu

`data/research/pending/vng-campus-food.json`
