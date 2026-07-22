.DEFAULT_GOAL := help

PYTHON ?= .venv/bin/python
COMPOSE ?= docker compose

.PHONY: help setup dev test lint typecheck check seed tree

help: ## Hiển thị các lệnh dành cho lập trình viên.
	@awk 'BEGIN {FS = ":.*## "; printf "Cách dùng: make <target>\n\nCác target:\n"} /^[a-zA-Z_-]+:.*## / {printf "  %-12s %s\n", $$1, $$2}' $(MAKEFILE_LIST)

setup: ## Tạo .env và .venv, chưa cài dependency.
	./scripts/bootstrap.sh

dev: ## Chạy API, worker và Redis bằng Docker Compose.
	$(COMPOSE) up --build

test: ## Chạy test suite.
	$(PYTHON) -m pytest

lint: ## Kiểm tra định dạng và quy tắc lint.
	$(PYTHON) -m ruff check .
	$(PYTHON) -m ruff format --check .

typecheck: ## Chạy kiểm tra kiểu tĩnh.
	$(PYTHON) -m mypy src tests

check: ## Chạy lint, kiểm tra kiểu và test.
	PYTHON=$(PYTHON) ./scripts/check.sh

seed: ## Kiểm tra fixture registry JSON; chưa nạp vào runtime.
	$(PYTHON) scripts/seed_registry.py

tree: ## In cây repository và bỏ qua file sinh tự động.
	@if command -v tree >/dev/null 2>&1; then \
		tree -a -I '.git|.venv|__pycache__|.pytest_cache|.mypy_cache|.ruff_cache|.DS_Store|tmp'; \
	else \
		find . -type d \( -name .git -o -name .venv -o -name __pycache__ -o -name .pytest_cache -o -name .mypy_cache -o -name .ruff_cache -o -name tmp \) -prune -o -name .DS_Store -prune -o -type f -print | sort; \
	fi
