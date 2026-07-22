#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
cd "$project_root"

python_bin=${PYTHON:-python3}

if ! command -v "$python_bin" >/dev/null 2>&1; then
  printf 'lỗi: không tìm thấy %s; hãy cài Python 3.12 trước.\n' "$python_bin" >&2
  exit 1
fi

if ! "$python_bin" -c 'import sys; raise SystemExit(0 if sys.version_info[:2] == (3, 12) else 1)'; then
  printf 'lỗi: yêu cầu Python 3.12; phiên bản hiện tại là %s.\n' "$("$python_bin" --version 2>&1)" >&2
  exit 1
fi

if [ ! -f .env ]; then
  umask 077
  cp .env.example .env
  printf 'đã tạo .env từ .env.example\n'
else
  printf 'giữ nguyên .env hiện có\n'
fi

if [ ! -d .venv ]; then
  "$python_bin" -m venv .venv
  printf 'đã tạo .venv\n'
else
  printf 'giữ nguyên .venv hiện có\n'
fi

printf '\nĐã bootstrap xong, chưa cài dependency.\n'
printf 'Tiếp theo: điền secret còn trống trong .env và cài dev dependency theo README.md.\n'
