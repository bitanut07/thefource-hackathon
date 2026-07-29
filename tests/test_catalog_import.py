"""Spreadsheet import parser tests.

The parser is the boundary where uncontrolled spreadsheet content becomes catalog
drafts, so these focus on what it must refuse and on the messy shapes real Excel
exports arrive in.
"""

import csv
import io

import pytest

from domain.catalog_import import (
    MAX_IMPORT_ROWS,
    ImportFormatError,
    parse_service_spreadsheet,
    template_rows,
)
from domain.models import ServiceCategory, ServiceType

CANONICAL_OA_URL = "https://zalo.me/1234567890123456789"


def _csv(rows: list[list[str]], delimiter: str = ",") -> bytes:
    buffer = io.StringIO()
    csv.writer(buffer, delimiter=delimiter).writerows(rows)
    return buffer.getvalue().encode("utf-8")


def _xlsx(rows: list[list[object]]) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    for row in rows:
        sheet.append(row)
    buffer = io.BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


HEADER = [
    "name",
    "provider",
    "service_type",
    "category",
    "description",
    "launch_url",
]
VALID_ROW = [
    "Dịch vụ A",
    "Đơn vị A",
    "oa",
    "utilities",
    "Mô tả dịch vụ A.",
    CANONICAL_OA_URL,
]


def test_parses_a_minimal_valid_csv() -> None:
    rows = parse_service_spreadsheet(_csv([HEADER, VALID_ROW]), "services.csv")

    assert len(rows) == 1
    draft = rows[0].draft
    assert draft is not None
    assert draft.name == "Dịch vụ A"
    assert draft.service_type is ServiceType.OA
    assert draft.category is ServiceCategory.UTILITIES
    assert draft.launch_url == CANONICAL_OA_URL
    assert rows[0].row_number == 2


def test_parses_xlsx_and_reads_numbers_without_a_decimal_tail() -> None:
    # Excel stores an unformatted 50 as 50.0; a draft priority of "50.0" would fail.
    content = _xlsx(
        [
            [*HEADER, "service_priority"],
            [*VALID_ROW, 50.0],
        ]
    )

    rows = parse_service_spreadsheet(content, "services.xlsx")

    assert rows[0].draft is not None
    assert rows[0].draft.service_priority == 50


def test_accepts_vietnamese_headers_in_any_order() -> None:
    content = _csv(
        [
            ["Mô tả", "Tên dịch vụ", "Liên kết", "Danh mục", "Loại kênh", "Nhà cung cấp"],
            ["Mô tả B.", "Dịch vụ B", CANONICAL_OA_URL, "health", "oa", "Đơn vị B"],
        ]
    )

    rows = parse_service_spreadsheet(content, "dich-vu.csv")

    assert rows[0].draft is not None
    assert rows[0].draft.name == "Dịch vụ B"
    assert rows[0].draft.category is ServiceCategory.HEALTH


def test_detects_semicolon_delimited_exports() -> None:
    # Vietnamese Excel locales export with ';' because the decimal separator is ','.
    content = _csv([HEADER, VALID_ROW], delimiter=";")

    rows = parse_service_spreadsheet(content, "services.csv")

    assert rows[0].draft is not None
    assert rows[0].draft.name == "Dịch vụ A"


def test_reports_bad_rows_individually_instead_of_failing_the_file() -> None:
    content = _csv(
        [
            HEADER,
            VALID_ROW,
            ["", "Đơn vị C", "oa", "utilities", "Mô tả C.", CANONICAL_OA_URL + "0"],
            [
                "Dịch vụ D",
                "Đơn vị D",
                "oa",
                "khong-co-danh-muc",
                "Mô tả D.",
                CANONICAL_OA_URL + "1",
            ],
        ]
    )

    rows = parse_service_spreadsheet(content, "services.csv")

    assert len(rows) == 3
    assert rows[0].draft is not None
    assert rows[1].draft is None and rows[1].error is not None
    assert "name" in rows[1].error
    assert rows[2].draft is None and rows[2].error is not None
    assert "category" in rows[2].error
    # Row numbers stay aligned with the spreadsheet so the uploader can find them.
    assert [row.row_number for row in rows] == [2, 3, 4]


def test_duplicate_launch_url_within_one_file_is_refused() -> None:
    content = _csv([HEADER, VALID_ROW, ["Dịch vụ khác", *VALID_ROW[1:]]])

    rows = parse_service_spreadsheet(content, "services.csv")

    assert rows[0].draft is not None
    assert rows[1].draft is None
    assert rows[1].error is not None
    assert "dòng 2" in rows[1].error


def test_aliases_and_intents_split_on_semicolons() -> None:
    content = _csv(
        [
            [*HEADER, "aliases", "intents"],
            [
                *VALID_ROW,
                "tên khác 1; tên khác 2; tên khác 1",
                "thanh_toan | tôi muốn đóng tiền; tra_cuu | tra cứu hóa đơn",
            ],
        ]
    )

    rows = parse_service_spreadsheet(content, "services.csv")

    draft = rows[0].draft
    assert draft is not None
    # Duplicates collapse; the schema forbids repeating an alias.
    assert draft.aliases == ("tên khác 1", "tên khác 2")
    assert [item.intent for item in draft.intents] == ["thanh_toan", "tra_cuu"]
    assert draft.intents[0].example_query == "tôi muốn đóng tiền"


def test_intent_without_an_example_is_rejected_with_the_expected_format() -> None:
    content = _csv([[*HEADER, "intents"], [*VALID_ROW, "thanh_toan"]])

    rows = parse_service_spreadsheet(content, "services.csv")

    assert rows[0].draft is None
    assert rows[0].error is not None
    assert "tên_intent" in rows[0].error


def test_missing_required_columns_names_them() -> None:
    content = _csv([["name", "provider"], ["Dịch vụ", "Đơn vị"]])

    with pytest.raises(ImportFormatError, match="Thiếu cột bắt buộc"):
        parse_service_spreadsheet(content, "services.csv")


def test_unsupported_and_empty_files_are_refused() -> None:
    with pytest.raises(ImportFormatError, match="Chỉ hỗ trợ"):
        parse_service_spreadsheet(b"data", "services.json")
    with pytest.raises(ImportFormatError, match="\\.xlsx hoặc \\.csv"):
        parse_service_spreadsheet(b"data", "services.xls")
    with pytest.raises(ImportFormatError, match="rỗng"):
        parse_service_spreadsheet(b"", "services.csv")
    with pytest.raises(ImportFormatError, match="không có dòng nào"):
        parse_service_spreadsheet(_csv([[], []]), "services.csv")


def test_row_limit_is_enforced() -> None:
    rows: list[list[str]] = [HEADER]
    for index in range(MAX_IMPORT_ROWS + 1):
        rows.append(
            ["Dịch vụ", "Đơn vị", "oa", "utilities", "Mô tả.", f"https://zalo.me/1{index:018d}"]
        )

    with pytest.raises(ImportFormatError, match=str(MAX_IMPORT_ROWS)):
        parse_service_spreadsheet(_csv(rows), "services.csv")


def test_blank_spreadsheet_rows_are_skipped_not_reported_as_errors() -> None:
    content = _csv([HEADER, VALID_ROW, ["", "", "", "", "", ""]])

    rows = parse_service_spreadsheet(content, "services.csv")

    assert len(rows) == 1


def test_template_round_trips_through_the_parser() -> None:
    # The template is what users are told to fill in, so it must itself import.
    headers, example = template_rows()

    rows = parse_service_spreadsheet(_csv([list(headers), list(example)]), "template.csv")

    assert len(rows) == 1
    assert rows[0].draft is not None, rows[0].error
