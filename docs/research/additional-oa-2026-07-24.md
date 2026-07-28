# Bổ sung Zalo OA ngày 2026-07-24

## Kết quả

- Thêm **29 Zalo OA** mới vào tầng research, nâng catalog lên **62 dịch vụ**:
  **45 OA** và **17 website**.
- SQLite RAG hiện có **67 tài liệu** khi tính thêm các bản ghi knowledge-only/pending
  của VNG Campus.
- 29/29 OA mới dùng deeplink số theo đúng mẫu
  `https://zalo.me/<numeric-oa-id>`, mở được và có tiêu đề trang công khai.
- Tất cả bản ghi mới giữ `active: false`, `review_status: candidate` và
  `oa_badge_status: unknown`. Chưa OA nào được tự động đưa vào Service Registry
  hoặc dùng làm CTA.

## OA mới theo nhóm

| Nhóm | OA mới |
| --- | --- |
| Giáo dục | Hocmaivn; VUS Anh văn Hội Việt Mỹ; Trường Đại học Nông Lâm TPHCM; Khoa Môi trường - HCMUS; Thư viện ĐH Công nghiệp Hà Nội |
| Y tế | Bệnh Viện FV; Bệnh viện Da Liễu TP.HCM; Bệnh viện 199; Bệnh viện Đa khoa Vạn Hạnh; Bệnh viện Đa khoa TTH Vinh |
| Tài chính, bảo hiểm | TPBank; Ngân hàng Số Vikki; Manulife Việt Nam; AIA Vietnam |
| Tiện ích, viễn thông | MobiFone; Cấp nước Cần Thơ 2 |
| Ăn uống, mua sắm | KFC Vietnam; Bách Hoá Xanh; WinMart/WinMart Plus |
| Di chuyển, du lịch | Vietravel; Vietjet; Phương Trang - FUTA Bus Lines |
| Giải trí | Lotte Cinema |
| Hành chính công | BHXH TP.HCM; Trung tâm Dịch vụ việc làm Gia Lai; UBND xã Đạ Tẻh; UBND xã Bà Nà; UBND xã Trung Giã; UBND phường Nhị Chiểu |

## Nguyên tắc thu thập

1. Chỉ đọc trang công khai, không đăng nhập, không thu thập chat, UID, token,
   hồ sơ bệnh án, mã khách hàng hoặc dữ liệu cá nhân.
2. Không suy đoán OA ID từ tên thương hiệu hay QR. Deeplink số phải mở được và
   tên trang phải khớp.
3. Ưu tiên nguồn chính chủ có liên kết ngược tới OA hoặc danh mục/case study do
   Zalo vận hành. Trường hợp chưa có backlink đủ mạnh vẫn là candidate
   research-only với mức tin cậy phù hợp.
4. Không suy luận huy hiệu xác minh từ trang web công khai. Việc duyệt vào
   Service Registry cần kiểm tra lại trong ứng dụng Zalo, menu/CTA và phạm vi
   dịch vụ thực tế.
5. Loại bản ghi có dấu hiệu đổi danh tính. Ví dụ, OA ID cũ từng gắn với EVNSPC
   không được nhập vì hiện trang công khai hiển thị tên Điện lực Đồng Tháp.

## Dữ liệu và cách tạo lại index

- Batch tổng hợp: `data/research/raw/additional_oa_2026_07_24.json`
- Y tế và giáo dục:
  `data/research/raw/additional_health_education_2026_07_24.json`
- Tài chính và tiện ích:
  `data/research/raw/additional_finance_utilities_2026_07_24.json`
- Thương mại và di chuyển:
  `data/research/raw/additional_commerce_transport_2026_07_24.json`

```powershell
uv run python scripts/build_research_catalog.py
uv run python scripts/build_rag_db.py
```

Có thể kiểm tra qua Swagger bằng `POST /api/v1/research/search`. Ví dụ:

```json
{
  "text": "KFC Vietnam gà rán",
  "category": "shopping_delivery",
  "limit": 3
}
```

Endpoint research chỉ trả metadata an toàn và trạng thái review, không trả URL
CTA hay payload nguồn thô.
