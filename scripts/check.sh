#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_root=$(dirname -- "$script_dir")
cd "$project_root"

python_bin=${PYTHON:-python3}

if ! command -v "$python_bin" >/dev/null 2>&1; then
  printf 'lỗi: không tìm thấy Python executable %s.\n' "$python_bin" >&2
  exit 1
fi

require_module() {
  module=$1
  if ! "$python_bin" -c "import importlib.util; raise SystemExit(0 if importlib.util.find_spec('$module') else 1)"; then
    printf 'lỗi: thiếu dependency phát triển: %s\n' "$module" >&2
    printf 'Hãy cài dev dependency rồi chạy lại make check.\n' >&2
    exit 1
  fi
}

require_module ruff
require_module mypy
require_module pytest

printf 'Đang chạy Ruff lint...\n'
"$python_bin" -m ruff check .
printf 'Đang kiểm tra định dạng Ruff...\n'
"$python_bin" -m ruff format --check .
printf 'Đang chạy mypy...\n'
"$python_bin" -m mypy src tests
printf 'Đang chạy pytest...\n'
"$python_bin" -m pytest
