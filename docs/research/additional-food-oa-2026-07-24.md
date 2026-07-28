# Bổ sung Zalo OA ăn uống ngày 2026-07-24

## Kết quả

- Thêm **21 Zalo OA** về nhà hàng, đồ ăn nhanh, bánh mì, cà phê, đồ uống và
  tiệm bánh vào tầng research.
- Catalog sau khi tổng hợp có **83 dịch vụ**: **66 OA** và **17 website**.
  Riêng nhóm `shopping_delivery` có **30 record**.
- Khi dựng lại SQLite RAG, index có **88 tài liệu**: 83 record catalog và 5
  tài liệu context/pending.
- Trong batch mới có **17 record mức `high`** và **4 record mức `medium`**.
  Cả 21 record đều giữ `active: false`, `review_status: candidate` và
  `oa_badge_status: unknown`; chưa record nào được dùng làm CTA runtime.

## OA mới theo nhóm và mức tin cậy

| Nhóm | Mức `high` | Mức `medium` |
| --- | --- | --- |
| Chuỗi nhà hàng | Pizza 4P's; Cơm tấm PHÚC LỘC THỌ; Lotteria Việt Nam; GoldSun Food; Buffet Poseidon; Chay Sala | GoGi House Lê Trọng Tấn TPHCM; Manwah Lotte Mart Mậu Thân Cần Thơ |
| Đồ ăn nhanh và bánh mì | Bonchon Vietnam; Bánh Mì Huynh Hoa; Chops | Texas Chicken Vietnam; Bánh mì PewPew |
| Cà phê, đồ uống và tiệm bánh | Trung Nguyên Legend; Paris Baguette Việt Nam; ToCoToCo Bubble Tea; Coca-Cola; Bánh Givral; Maison Marou; Hỷ Lâm Môn Bakery; Morico | Không |

`medium` không có nghĩa là URL không mở được. Bốn record này có trang OA số và
tên thương hiệu khớp, nhưng còn thiếu backlink trực tiếp từ website chính chủ,
phạm vi chi nhánh chưa đủ rõ hoặc cần kiểm tra lại trong ứng dụng Zalo.

## Nguồn đối chiếu

Mỗi OA dưới đây được giữ bằng deeplink số. Cột nguồn đối chiếu lấy trực tiếp từ
`evidence` trong ba batch raw; nguồn có thể là website chính chủ hoặc alias do
Zalo vận hành.

| OA số | Nguồn đối chiếu |
| --- | --- |
| [Pizza 4P's](https://zalo.me/1139866614914597381) | [Website Pizza 4P's](https://pizza4ps.com/vn/policy/?lang=vietnamese) |
| [Cơm tấm PHÚC LỘC THỌ](https://zalo.me/2969085200217280478) | [Website Cơm Tấm Phúc Lộc Thọ](https://comtamphucloctho.vn/) |
| [Lotteria Việt Nam](https://zalo.me/532153540884181118) | [Website Lotteria Việt Nam](https://www.lotteria.vn/) |
| [GoldSun Food](https://zalo.me/1109935404164297158) | [Website Khao Lao thuộc hệ thống GoldSun](https://khaolao.vn/mien-bac-giai-ma-suc-hut-cua-bst-summer-drink/) |
| [GoGi House Lê Trọng Tấn TPHCM](https://zalo.me/4065039816957305114) | [Trang đặt bàn GoGi House](https://gogi.com.vn/dat-ban) |
| [Manwah Lotte Mart Mậu Thân Cần Thơ](https://zalo.me/2660021698955201092) | [Website Manwah](https://manwah.com.vn/) và [Lotte Mart Việt Nam](https://lottemart.com.vn/chi-nhanh-lotte-mart/manwah-mung-8-3-manwah-tang-nang-ty-ty-yeu-thuong/) |
| [Buffet Poseidon](https://zalo.me/860658002480563692) | [Thông báo chống giả mạo của Buffet Poseidon](https://buffetposeidon.com/tin-tuc/bao-ve-khach-hang-truoc-thu-doan-mao-danh-lua-dao-poseidon-huy-fanpage-poseidon-tphcm) |
| [Chay Sala](https://zalo.me/3768100295324169194) | [Website Chay Sala](https://chaysala.com/blogs/news/mam-cung-tet-chay-sala-2026-tron-dao-hieu-ngat-tu-bi) |
| [Texas Chicken Vietnam](https://zalo.me/884340211286408960) | [Alias Zalo OA](https://oa.zalo.me/texaschickenvietnam) và [website Texas Chicken](https://texaschickenvn.com/) |
| [Bonchon Vietnam](https://zalo.me/4565429732152793097) | [Website Bonchon Vietnam](https://bonchon.com.vn/tin-tuc/dang-ky-thanh-vien-bonchon-nhan-ngay-uu-dai-khung) |
| [Bánh Mì Huynh Hoa](https://zalo.me/2130785890579320795) | [Website Bánh Mì Huynh Hoa](https://banhmihuynhhoa.vn/) |
| [Bánh mì PewPew](https://zalo.me/1847796981349404351) | [Alias Zalo OA](https://oa.zalo.me/banhmipewpew) và [website Bánh mì PewPew](https://www.banhmipewpew.com/) |
| [Chops](https://zalo.me/1799406254854247759) | [Website Chops](https://chops.vn/vi/trang-chu-tieng-viet/) |
| [Trung Nguyên Legend](https://zalo.me/1498942390064218601) | [Alias Zalo OA](https://oa.zalo.me/trungnguyenlegend) và [website Trung Nguyên Legend](https://trungnguyenlegend.com/) |
| [Paris Baguette Việt Nam](https://zalo.me/2170657541451452996) | [Alias Zalo OA](https://oa.zalo.me/parisbaguettevietnam) và [website Paris Baguette](https://parisbaguette.com.vn/about-us/) |
| [ToCoToCo Bubble Tea](https://zalo.me/2268915497539367639) | [Alias Zalo OA](https://oa.zalo.me/tocotocotea) và [website ToCoToCo](https://tocotoco.com.vn/) |
| [Coca-Cola](https://zalo.me/878180153557257351) | [Alias Zalo OA](https://oa.zalo.me/cocacola) và [website Coca-Cola Việt Nam](https://www.coca-cola.com/vn/vi) |
| [Bánh Givral](https://zalo.me/1081789048959776589) | [Alias Zalo OA](https://oa.zalo.me/givralbakery) và [website Givral Bakery](https://givralbakery.com.vn/) |
| [Maison Marou](https://zalo.me/3606090787743852073) | [Alias Zalo OA](https://oa.zalo.me/maisonmarou) và [website Maison Marou](https://maisonmarou.com/vi) |
| [Hỷ Lâm Môn Bakery](https://zalo.me/512238328228106090) | [Alias Zalo OA](https://oa.zalo.me/hylammon) và [website Hỷ Lâm Môn](https://hylammon.com.vn/) |
| [Morico](https://zalo.me/933370737442378632) | [Alias Zalo OA](https://oa.zalo.me/morico) và [website Morico](https://morico.life/about-us/) |

## Alias bị loại

Các alias cũ tìm thấy cho **Jollibee, Pizza Hut, Domino's Pizza, The Pizza
Company và Popeyes** không được nhập. Khi kiểm tra, chúng chuyển tới màn hình
đăng nhập Zalo hoặc không còn cho ra trang số có tiêu đề khớp thương hiệu. Một
số alias cũ trong nhóm cà phê/đồ uống cũng bị loại theo cùng tiêu chí.

Không suy đoán OA ID từ tên thương hiệu, QR hoặc kết quả tìm kiếm. Chỉ record có
URL số công khai không đổi đích và tiêu đề khớp mới được giữ ở tầng research.

## Dữ liệu và cách tạo lại index

- Chuỗi nhà hàng:
  `data/research/raw/additional_restaurant_chains_2026_07_24.json`
- Đồ ăn nhanh và bánh mì:
  `data/research/raw/additional_fast_food_pizza_2026_07_24.json`
- Cà phê, đồ uống và tiệm bánh:
  `data/research/raw/additional_cafe_drinks_bakery_2026_07_24.json`

```powershell
uv run python scripts/build_research_catalog.py
uv run python scripts/build_rag_db.py
```

Các record này chỉ phục vụ retrieval qua `POST /api/v1/research/search`. Việc
đưa một OA vào Service Registry thật vẫn cần kiểm tra huy hiệu trong ứng dụng,
menu/CTA, phạm vi dịch vụ, quyền dùng logo, owner và lịch tái kiểm tra.
