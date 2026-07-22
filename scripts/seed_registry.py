#!/usr/bin/env python3
"""Kiểm tra dữ liệu seed của registry mà không thay đổi file nguồn.

TODO: Nối ``--apply`` vào loader registry sau khi chốt schema và cơ chế reload.
Trước thời điểm đó, script chỉ chạy dry-run để không thể ghi đè dữ liệu registry.
"""

from __future__ import annotations

import argparse
import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

DEFAULT_SEED_PATH = Path("data/seed/services.example.json")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_SEED_PATH,
        help=f"đường dẫn seed JSON (mặc định: {DEFAULT_SEED_PATH})",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="dành cho loader registry tương lai; hiện chưa triển khai",
    )
    return parser.parse_args()


def load_records(path: Path) -> list[Mapping[str, Any]]:
    with path.open(encoding="utf-8") as seed_file:
        payload = json.load(seed_file)

    if isinstance(payload, Mapping):
        payload = payload.get("services")
    if not isinstance(payload, list):
        raise ValueError("gốc seed phải là danh sách hoặc object chứa trường 'services'")
    if not all(isinstance(record, Mapping) for record in payload):
        raise ValueError("mỗi service phải là một JSON object")
    return payload


def first_non_empty(record: Mapping[str, Any], keys: tuple[str, ...]) -> Any:
    return next((record.get(key) for key in keys if record.get(key)), None)


def validate_records(records: list[Mapping[str, Any]]) -> list[str]:
    errors: list[str] = []
    seen_ids: set[str] = set()

    for index, record in enumerate(records, start=1):
        service_id = first_non_empty(record, ("id", "service_id", "slug"))
        name = first_non_empty(record, ("name", "display_name"))
        launch_url = record.get("launch_url")

        if not isinstance(service_id, str):
            errors.append(f"record {index}: thiếu chuỗi id/service_id/slug")
        elif service_id in seen_ids:
            errors.append(f"record {index}: trùng định danh dịch vụ {service_id!r}")
        else:
            seen_ids.add(service_id)

        if not isinstance(name, str):
            errors.append(f"record {index}: thiếu chuỗi name/display_name")
        if not isinstance(launch_url, str) or not launch_url.strip():
            errors.append(f"record {index}: thiếu chuỗi launch_url")

    return errors


def main() -> int:
    args = parse_args()
    if args.apply:
        print("lỗi: --apply chưa được triển khai; cần chốt schema và cơ chế reload registry trước.")
        return 2
    if not args.file.is_file():
        print(f"lỗi: không tìm thấy file seed: {args.file}")
        return 2

    try:
        records = load_records(args.file)
        errors = validate_records(records)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"lỗi: không thể kiểm tra {args.file}: {exc}")
        return 2

    if errors:
        for error in errors:
            print(f"lỗi: {error}")
        return 1

    print(f"đã kiểm tra {len(records)} service từ {args.file}; không ghi dữ liệu")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
