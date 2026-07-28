# Zalo category taxonomy

Taxonomy public của Service Navigator bám theo danh mục Zalo do đội cung cấp:

| Nhãn Zalo | API value |
| --- | --- |
| Ăn uống | `food` |
| Giáo dục | `education` |
| Mua sắm | `shopping` |
| Tài chính | `finance` |
| Tiện ích | `utilities` |
| Sức khỏe | `health` |
| Cơ quan nhà nước | `government` |
| Khác (extension) | `other` |

`Tất cả` chỉ là bộ lọc UI tổng hợp, không phải giá trị lưu trong data. `other`
là extension hiển thị “Khác” cho loại dịch vụ không có category tương ứng trong
danh mục Zalo đã cung cấp.

Các record transport/giải trí cũ giữ `internal_category` để bảo toàn provenance,
nhưng được map sang `other` khi build catalog research.
