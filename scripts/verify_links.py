#!/usr/bin/env python3
"""Kiểm tra tĩnh launch URL trong registry mà không gọi mạng.

Allowlist host tùy chọn được đọc từ ``ALLOWED_LAUNCH_HOSTS`` dưới dạng danh sách
phân tách bằng dấu phẩy. Chưa triển khai kiểm tra link trực tiếp vì cần timeout,
giới hạn redirect, lọc DNS/IP và audit log rõ ràng để tránh tạo ra lỗ hổng SSRF.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

DEFAULT_SEED_PATH = Path("data/registry/services.real.json")


def configure_utf8_output() -> None:
    """Keep Vietnamese CLI output usable on legacy Windows code pages."""

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--file", type=Path, default=DEFAULT_SEED_PATH)
    parser.add_argument(
        "--require-allowlist",
        action="store_true",
        help="báo lỗi khi ALLOWED_LAUNCH_HOSTS rỗng",
    )
    return parser.parse_args()


def load_records(path: Path) -> list[Mapping[str, Any]]:
    with path.open(encoding="utf-8") as source:
        payload = json.load(source)
    if isinstance(payload, Mapping):
        payload = payload.get("services")
    if not isinstance(payload, list) or not all(isinstance(record, Mapping) for record in payload):
        raise ValueError("cần danh sách hoặc object chứa danh sách 'services'")
    return payload


def configured_hosts() -> set[str]:
    raw_hosts = os.environ.get("ALLOWED_LAUNCH_HOSTS", "")
    return {host.strip().lower().rstrip(".") for host in raw_hosts.split(",") if host.strip()}


def validate_url(url: Any, allowed_hosts: set[str]) -> str | None:
    if not isinstance(url, str) or not url.strip():
        return "launch_url phải là chuỗi không rỗng"

    parsed = urlsplit(url)
    if parsed.scheme != "https":
        return "launch_url phải dùng https"
    if not parsed.hostname:
        return "launch_url phải có hostname"
    if parsed.username or parsed.password:
        return "launch_url không được chứa credential"

    hostname = parsed.hostname.lower().rstrip(".")
    if allowed_hosts and hostname not in allowed_hosts:
        return f"hostname {hostname!r} không nằm trong ALLOWED_LAUNCH_HOSTS"
    return None


def main() -> int:
    configure_utf8_output()
    args = parse_args()
    if not args.file.is_file():
        print(f"lỗi: không tìm thấy file registry: {args.file}")
        return 2

    allowed_hosts = configured_hosts()
    if args.require_allowlist and not allowed_hosts:
        print("lỗi: ALLOWED_LAUNCH_HOSTS phải có ít nhất một hostname")
        return 2
    if not allowed_hosts:
        print("cảnh báo: ALLOWED_LAUNCH_HOSTS rỗng; chỉ kiểm tra cấu trúc URL")

    try:
        records = load_records(args.file)
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"lỗi: không thể đọc {args.file}: {exc}")
        return 2

    failures = 0
    for index, record in enumerate(records, start=1):
        error = validate_url(record.get("launch_url"), allowed_hosts)
        if error:
            failures += 1
            identifier = record.get("id") or record.get("service_id") or index
            print(f"lỗi: service {identifier!r}: {error}")

    if failures:
        print(f"không đạt kiểm tra tĩnh với {failures} liên kết")
        return 1

    print(f"đã kiểm tra tĩnh {len(records)} liên kết; không gọi mạng")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
