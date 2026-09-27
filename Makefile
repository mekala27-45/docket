.PHONY: install test web reports rederive api
install:
	uv sync --python 3.12
	cd web && npm ci
test:
	uv run pytest
	uv run ruff check packages scripts tests
	uv run mypy
	uv run python scripts/render_reports.py --check
	uv run python scripts/quality_gates.py
	uv run python scripts/validate_palette.py
web:
	cd web && npm run build
reports:
	uv run python scripts/render_reports.py
rederive:
	uv run python scripts/reset_and_rederive.py
api:
	uv run uvicorn packages.api.main:app --host 127.0.0.1 --port 8000
