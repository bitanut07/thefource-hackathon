# Kết quả có hình ảnh và CTA trên Zalo OA

Tài liệu này được đối chiếu với tài liệu Zalo công khai ngày 28-07-2026. Kết
luận ngắn:

- **Zalo Chatbot Dynamic API** là cách phù hợp nhất cho luồng hiện tại: người
  dùng vừa nhắn OA bằng UID và nhận kết quả tìm kiếm động.
- **ZBS Template Carousel**, ra mắt ngày 15-07-2026, là giao diện ZBS gần mockup
  nhất. Tuy nhiên Zalo hiện chỉ công bố Carousel cho luồng gửi theo số điện
  thoại, chưa hỗ trợ UID. Carousel còn đang được đội ZBS tạo thủ công.
- **ZBS Template tùy chỉnh qua UID** có thể tạo một tin có ảnh và tối đa ba CTA,
  nhưng không tạo được các hàng kết quả độc lập, mỗi hàng có thumbnail và nút
  riêng như mockup.

## Lựa chọn sản phẩm

| Lựa chọn | Khả năng đã được Zalo công khai | Có phù hợp luồng gợi ý này? |
| --- | --- | --- |
| OA OpenAPI `POST /v3.0/oa/message/cs` | Tin tư vấn dạng text, ảnh, file và một số loại tin chăm sóc khác | Client hiện tại dùng đúng endpoint cho text, nhưng tài liệu v3 hiện không công bố payload danh sách/card có CTA cho endpoint này |
| ZBS Template tùy chỉnh qua UID | Template đã đăng ký/kiểm duyệt; ảnh nằm ở header, nội dung có tham số, tối đa ba CTA theo tài liệu giao diện hiện hành | Chỉ xấp xỉ: có thể liệt kê ba kết quả và ba nút ở cuối, không có thumbnail/nút theo từng hàng |
| ZBS Template Carousel | Tối đa năm thẻ; mỗi thẻ có một ảnh, tiêu đề, nội dung và tối đa ba CTA độc lập | Gần mockup nhất về hình thức, nhưng hiện chỉ gửi theo số điện thoại và phải nhờ CSKH ZBS tạo thủ công |
| Zalo Chatbot Dynamic API | Response động dạng text, ảnh, text có nút, và list có ảnh + URL action | Phù hợp nhất với trường hợp người dùng chủ động hỏi rồi nhận các kết quả runtime |

Nguồn chính thức:

- [Zalo Chatbot Dynamic API](https://chatbot.zalo.me/oa/docs/advanced/dynamic-api-msg)
- [Zalo Chatbot – bắt đầu](https://chatbot.zalo.me/oa/docs/getting-started/intro)
- [Tin Tư vấn đính kèm ảnh](https://docs.zaloplatforms.com/docs/OA/tin-nhan/tin-tu-van/gui-tin-tu-van-dinh-kem-anh)
- [Gửi ZBS Template Message qua UID](https://docs.zaloplatforms.com/docs/ZBS/gui-tin-template-qua-uid/api-gui-tin-qua-uid)
- [ZBS Template Carousel](https://zalo.solutions/news/zbs-ra-mat-template-carousel-quang-ba-nhieu-san-pham-trong-1-mau-tin/t01j6wcti3yw2tmss19h37b9)
- [Danh sách component ZBS](https://docs.zaloplatforms.com/docs/ZBS/quan-ly-template/bat-dau/danh-sach-components)
- [Cài đặt kỹ thuật template ZBS](https://zalo.solutions/news/cai-dat-ki-thuat-trong-mau-thong-bao-zns/imvakq20x8mrojyrevo975jt)
- [Định dạng tham số trong CTA](https://zalo.solutions/blog/cac-dinh-dang-du-lieu-khi-truyen-vao-tham-so-tren-noi-dung-zns/hd5soyjh3gv18ophwzdn49ty)
- [Thông báo ra mắt ZBS Template Message](https://zalo.solutions/news/thong-bao-hop-nhat-dinh-nghia-tin-uid-va-zns-thanh-zbs-template-message/cp1zx4bq8mzhhszgz0br1ocd)
- [Quy định kiểm duyệt template](https://zalo.solutions/news/quy-dinh-chung-khi-kiem-duyet-mau-tin-zns/xdygqtrjjm97k28rsh07wr72)
- [Hướng dẫn CTA trong template](https://zalo.solutions/blog/huong-dan-them-nut-thao-tac-cta-trong-mau-zns/a7x4qv3exty0yrgztcrxinbo)
- [Điều khoản và đơn giá ZBS](https://zalo.solutions/terms)

## Hai layout có thể triển khai

### 1. List: gần mockup nhất

Dynamic API công bố message `type=list`, tối đa năm phần tử. Mỗi phần tử có
`title`, `subtitle`, `image_url` HTTPS tùy chọn và `action` kiểu `url`.
Payload dưới đây chỉ minh họa schema bằng domain `example.com` dành cho tài
liệu; không phải một OA hoặc service record thật.

```json
{
  "version": "chatbot",
  "content": {
    "messages": [
      {
        "type": "text",
        "text": "Dưới đây là các dịch vụ phù hợp:"
      },
      {
        "type": "list",
        "elements": [
          {
            "title": "Tên dịch vụ từ registry",
            "subtitle": "Lý do phù hợp từ dữ liệu registry",
            "image_url": "https://cdn.example.com/approved-logo.png",
            "action": {
              "type": "url",
              "url": "https://example.com/verified-service"
            }
          }
        ]
      }
    ]
  }
}
```

Người dùng bấm phần tử để mở URL. Schema công khai không có trường đặt nhãn nút
riêng trên từng dòng list, nên không được cam kết UI sẽ hiện đúng nút
“Mở dịch vụ” hay đúng pixel như mockup. Phần render cuối cùng do ứng dụng Zalo
quyết định.

### 2. Text + URL button: có nhãn “Mở dịch vụ” rõ ràng

Dynamic API cũng công bố text message có `buttons`, gồm button `type=url`.
Renderer trong repository tạo một message giới thiệu và một message có nút cho
mỗi kết quả. Do response chỉ được tối đa năm messages, layout này trả tối đa
bốn kết quả.

Layout này đảm bảo payload có nhãn nút, nhưng không tạo một hàng có logo, nội
dung và nút giống hệt mockup.

## Code đã chuẩn bị

`src/zalo/chatbot.py` cung cấp:

```python
payload = render_dynamic_response(
    navigator_response,
    layout="list",
    image_urls={
        str(service_id): "https://cdn.example.com/approved-logo.png",
    },
)
```

Đổi sang `layout="buttons"` nếu ưu tiên nút “Mở dịch vụ”. Renderer:

- chỉ lấy URL đã nằm trong `ServiceChoice`, không để LLM tự tạo URL;
- giới hạn năm list elements hoặc tổng cộng năm messages;
- từ chối `image_url` không phải HTTPS;
- bỏ ảnh nếu service chưa có tài sản hình ảnh đã được duyệt.

## Các bước nối production

1. Xác nhận OA đã xác thực và có menu Zalo Chatbot/đủ điều kiện dùng tính năng
   trong OA Manager.
2. Tạo rule khi người dùng gửi tin nhắn, rồi gọi Dynamic API endpoint.
3. Endpoint phải trả HTTP 200 trong **dưới hai giây** và trả Zalo Chatbot Format.
   Tài liệu công khai cho phép tối đa năm messages.
4. Đưa tìm kiếm deterministic hoặc kết quả cache vào critical path. Không nên
   chờ một lần gọi LLM không có timeout chặt, vì flow `/api/v1/navigate` hiện
   chưa có SLO dưới hai giây.
5. Trong màn hình cấu hình Dynamic API thực của OA, xác minh request body mà
   Zalo gửi và cách truyền secret. Tài liệu công khai nêu rõ response contract,
   nhưng trang này không công bố đủ inbound request/header contract để đoán an
   toàn trong code.
6. Test trên tài khoản Zalo mobile thật. Chỉ bật production sau khi kiểm tra
   deeplink, fallback, timeout và retry.

### Cấu hình đã triển khai trong repository

Endpoint production là:

```text
GET https://zah-19.123c.vn/integrations/zalo/chatbot/dynamic
```

Trong file `.env` **trên VPS** (không commit), tạo một secret ngẫu nhiên mới và
thêm các biến sau. Secret chỉ đi trong header, không đưa vào URL hay log.

```dotenv
ZALO_REPLY_MODE=chatbot_dynamic
ZALO_CHATBOT_TOKEN=<secret-ngau-nhien-rieng>
ZALO_CHATBOT_TIMEOUT_SECONDS=1.25
ZALO_CHATBOT_MAX_CONCURRENCY=8
ZALO_CHATBOT_LAYOUT=list
```

Trong màn hình **Edit Request** của Zalo Chatbot:

1. Chọn `GET`.
2. Điền URL `https://zah-19.123c.vn/integrations/zalo/chatbot/dynamic?q=<biến_tin_nhắn_của_Chatbot>`.
3. Thêm header `X-Chatbot-Token` với đúng giá trị `ZALO_CHATBOT_TOKEN`.
4. Bấm **Test the Request**, kiểm tra response có `version: "chatbot"`, rồi lưu
   rule và thử bằng tài khoản Zalo thật.

Tên chính xác của biến tin nhắn ở bước 2 phải chọn từ biến mà UI/log của Zalo
Chatbot cung cấp; tài liệu công khai không xác nhận một tên chung để đoán. API
cũng chấp nhận `text`, `query`, `message` và `input` để thuận tiện khi test,
nhưng `q` là quy ước nên dùng khi cấu hình production.

Khi `ZALO_REPLY_MODE=chatbot_dynamic`, webhook OA đã xác thực sẽ không enqueue
worker gửi tin tư vấn text cũ, tránh người dùng nhận hai câu trả lời. Chỉ bật
biến này sau khi rule Dynamic API đã hoạt động; nếu cần rollback, đổi lại
`consultation` và restart API/worker.

### Migration và quy trình duyệt ảnh

Migration `db/migrations/003_service_visual_assets.sql` tạo kho asset có nguồn,
bằng chứng quyền sử dụng, trạng thái duyệt và người duyệt. Chạy migration này
trên database production trước khi thêm ảnh. Với database đã tồn tại, Docker
không tự chạy file init mới; chạy migration một lần bằng kết nối `psql` trong
container PostgreSQL, rồi seed/restart stack theo hướng dẫn deploy của dự án.

Chỉ row có `approval_status='approved'`, `is_active=true`, `placement='chatbot_list'`
và URL HTTPS mới được renderer đưa vào `image_url`. Vì chưa có logo nào được
hội đồng/chủ sở hữu duyệt trong registry hiện tại, release này sẽ hiển thị list
có tiêu đề, mô tả và vùng bấm mở dịch vụ trước; logo sẽ tự xuất hiện sau khi có
asset đã phê duyệt được insert vào bảng này.

## Dữ liệu hình ảnh còn thiếu

Registry runtime hiện chưa có trường/logo đã được phê duyệt. Không hotlink logo
từ kết quả tìm kiếm hoặc dùng ảnh nghiên cứu khi chưa rõ quyền sử dụng. Với mỗi
service cần lưu một HTTPS asset do đội sở hữu hoặc được chủ thể cho phép dùng,
đồng thời giữ nguồn và trạng thái review. Cho đến lúc đó renderer sẽ bỏ
`image_url`; dữ liệu tên, lý do và CTA vẫn là dữ liệu registry thật.

## ZBS có thể dùng đến mức nào?

### Template tùy chỉnh gửi qua UID

Endpoint chính thức là `POST /v3.0/oa/message/template`, với `user_id`,
`template_id` và `template_data` đúng schema của template đã được duyệt. Một
template tùy chỉnh có thể dùng:

- một vùng ảnh/logo ở đầu tin;
- title/paragraph/table có tham số;
- tối đa ba CTA theo bài cài đặt kỹ thuật/giao diện hiện hành;
- URL CTA có phần tham số động, nhưng base URL/cấu trúc CTA là một phần của
template được duyệt và nhãn nút không dùng tham số.

Có một mâu thuẫn trong tài liệu chính thức tại ngày kiểm tra: trang
`Danh sách Components` của Platform Hub vẫn mô tả `BUTTONS.items` tối đa hai
phần tử, trong khi bài cài đặt kỹ thuật và cập nhật giao diện mới công bố tối đa
ba CTA cho template tùy chỉnh. Vì vậy số nút thực tế phải được xác nhận trên
ZBS Account/template pilot; không hard-code ba nút trước khi có template được
duyệt.

Do đó có thể thiết kế bản xấp xỉ gồm ba dòng kết quả và ba nút “Mở dịch vụ 1”,
“Mở dịch vụ 2”, “Mở dịch vụ 3”. Các nút nằm ở cuối template; không nằm cạnh
từng thumbnail như mockup. Không nên để tham số trở thành một URL đích hoàn
toàn tùy ý. Nếu cần route động, dùng domain redirect do đội sở hữu, token service
đã ký và chỉ redirect tới URL registry đã allowlist; cấu trúc này vẫn phải được
ZBS duyệt rõ ràng.

### Template Carousel gửi theo số điện thoại

Thông báo chính thức ngày 15-07-2026 công bố:

- tối đa năm card/template;
- mỗi card bắt buộc có một ảnh, paragraph và có thể có title;
- tối đa ba CTA/card, tối đa 15 CTA/template;
- số lượng, vị trí, tên và phân loại CTA phải giống nhau giữa các card; URL có
  thể khác;
- hiện tạo thủ công qua CSKH ZBS trong khoảng 2-3 ngày làm việc;
- hiện chỉ hỗ trợ luồng ZBS Template Message theo số điện thoại.

Carousel đúng hướng nếu hội đồng/ZBS chấp thuận cả use case, dữ liệu người nhận,
quyền sử dụng logo và cơ chế truyền dữ liệu động. Tài liệu công khai chưa xác
nhận card title/body/image có thể được thay toàn bộ theo từng lần gửi. Vì vậy
không được giả định một template Carousel có thể nhận năm service bất kỳ từ AI
cho đến khi ZBS cung cấp schema `template_data` thật của template đã duyệt.

### Điều kiện chính sách và chi phí

Điều khoản ZBS cập nhật ngày 09-07-2026 định nghĩa người nhận là người đã có
giao dịch trước đó với đối tác và yêu cầu lệnh tin gắn với sự kiện giao dịch;
trường hợp ngoài phạm vi được xét từng trường hợp. Với một trợ lý công cộng trả
kết quả ngay sau câu hỏi, cần xin xác nhận ngoại lệ/use case bằng văn bản, không
chỉ xác thực OA.

Đơn giá công khai chưa VAT tại thời điểm kiểm tra gồm 300 đồng cho “template
khác”, cộng 300 đồng nếu có thành phần hình ảnh. CTA tới website/Zalo Mini App
của doanh nghiệp khác là 500 đồng mỗi nút. Phí thực tế của Carousel cần được
đối tác ZBS báo giá/xác nhận.

## Hồ sơ cần gửi hội đồng/ZBS để xác minh

Yêu cầu câu trả lời bằng văn bản cho sáu điểm:

1. OA/AppID này có được cấp Template Carousel không?
2. Carousel có thể gửi theo UID từ webhook `user_send_text`, hay vẫn chỉ hỗ trợ
   số điện thoại?
3. Card image/title/body và CTA URL nào là parameter runtime; gửi schema
   `template_data` chính thức của template.
4. Use case “người dùng chủ động hỏi và nhận gợi ý dịch vụ bên thứ ba” được duyệt
   dưới tag nào và có được miễn/đánh giá riêng so với điều kiện giao dịch không?
5. Bộ giấy tờ hợp tác/quyền sử dụng logo, tên thương hiệu và deeplink của từng
   dịch vụ cần cung cấp là gì?
6. Đơn giá đầy đủ của một Carousel ba hoặc năm card, gồm ảnh và CTA bên thứ ba.

Nếu câu trả lời cho mục 2 hoặc 3 là “không”, giữ Dynamic API làm đường production.

## Vì sao không mặc định chọn ZBS cho trường hợp này

ZBS Template Message yêu cầu template thuộc OA, đã được Zalo duyệt, và dữ liệu
gửi phải đúng cấu trúc template. Zalo cũng công bố quy định kiểm duyệt CTA:
link phải nằm trong CTA, phải truy cập được, không dùng link rút gọn; nhắc tới
thương hiệu bên thứ ba có thể cần bằng chứng hợp tác. ZBS còn có cơ chế tính
phí theo loại tin/thành phần/CTA và phương thức gửi.

Vì danh sách gợi ý thay đổi theo câu hỏi và có thể dẫn tới nhiều OA/thương hiệu
không thuộc OA gửi, không được giả định một template ZBS đã duyệt sẽ chấp nhận
mọi kết quả runtime. Sự hỗ trợ của hội đồng rất hữu ích để xin phê duyệt
Carousel/use case ngoại lệ, nhưng không tự thay đổi giới hạn UID, component hoặc
schema đã được Zalo công bố.
