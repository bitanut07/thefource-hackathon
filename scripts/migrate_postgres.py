#!/usr/bin/env python3
"""Apply the idempotent PostgreSQL Service Catalog schema migrations."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
MIGRATIONS_DIR = ROOT / "db" / "migrations"


def configure_utf8_output() -> None:
    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=os.environ.get("DATABASE_URL", ""),
        help="PostgreSQL URL; mặc định lấy DATABASE_URL.",
    )
    return parser.parse_args()


def main() -> int:
    configure_utf8_output()
    args = parse_args()
    if not args.database_url.strip():
        raise SystemExit("DATABASE_URL là bắt buộc.")
    migrations = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not migrations:
        raise SystemExit("Không tìm thấy migration SQL.")

    with psycopg.connect(args.database_url, autocommit=True) as connection:
        for path in migrations:
            connection.execute(path.read_text(encoding="utf-8"))
            print(f"Đã áp dụng {path.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
