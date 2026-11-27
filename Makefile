# Agent harness. `make check` is the one command AGENTS.md and CI both run.
# First run after cloning: `make setup && make protos` (or just `make check`,
# which fetches proto/ itself when src/xiaomi_pb/ is missing).

PY ?= /usr/bin/python3
# `make docs-serve` bind address. Default is local-only; use 0.0.0.0:8000 for LAN access.
DOCS_ADDR ?= 127.0.0.1:8000

.PHONY: setup protos fmt lint test sizes check docs docs-serve

setup: ## Create .venv from the distro Python (the one with AF_BLUETOOTH)
	uv sync --python $(PY)

protos: ## Download proto/ and regenerate src/xiaomi_pb/ (pinned, checksummed)
	./fetch_protos.sh

fmt: ## Apply ruff formatting and safe lint fixes
	uv run ruff format .
	uv run ruff check --fix .
	uv run python scripts/check_docs.py --fix

lint: ## Static checks: ruff, shell syntax, docs lint
	uv run ruff check .
	uv run ruff format --check .
	bash -n fetch_protos.sh
	@if command -v shellcheck >/dev/null; then shellcheck fetch_protos.sh; else echo "shellcheck not installed, skipped"; fi
	uv run python scripts/check_docs.py

test: ## Unit tests; hardware/network markers are excluded by pytest config
	@test -f src/xiaomi_pb/xiaomi_pb2.py || $(MAKE) protos
	uv run pytest

sizes: ## Context budget: fail if AGENTS.md or a docs page grows too large
	uv run python scripts/context_sizes.py

docs: ## Build the GitHub Pages site into site/ (mkdocs + Material, strict)
	uv run mkdocs build --strict

docs-serve: ## Live-preview the site (LAN: make docs-serve DOCS_ADDR=0.0.0.0:8000)
	uv run mkdocs serve --dev-addr $(DOCS_ADDR)

check: lint test sizes docs
	uv run python -m compileall -q src tests
	@echo "harness OK"
