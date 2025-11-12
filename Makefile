.PHONY: help install dev-install clean test lint format type-check pre-commit run docker-build docker-run

help:  ## Show this help message
	@echo "AAISP CHAOS API Exporter - Development Commands"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

install:  ## Install production dependencies
	uv sync --no-dev

dev-install:  ## Install development dependencies
	uv sync
	uv run pre-commit install

clean:  ## Clean build artifacts and caches
	rm -rf build/ dist/ *.egg-info
	rm -rf .pytest_cache .mypy_cache .ruff_cache
	rm -rf htmlcov coverage.xml .coverage
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name '*.pyc' -delete

test:  ## Run tests with coverage
	uv run pytest

test-verbose:  ## Run tests with verbose output
	uv run pytest -vv

test-coverage:  ## Run tests and generate coverage report
	uv run pytest --cov-report=html
	@echo "Coverage report generated in htmlcov/index.html"

lint:  ## Run linting checks
	uv run ruff check .

format:  ## Format code
	uv run ruff format .

format-check:  ## Check code formatting without making changes
	uv run ruff format --check .

type-check:  ## Run type checking
	uv run mypy src/

pre-commit:  ## Run all pre-commit hooks
	uv run pre-commit run --all-files

ci:  ## Run all CI checks (lint, type-check, test)
	$(MAKE) lint
	$(MAKE) type-check
	$(MAKE) test

run:  ## Run the exporter locally
	uv run python -m aaisp_exporter

run-dev:  ## Run the exporter with auto-reload
	uv run uvicorn aaisp_exporter.app:app --reload --host 0.0.0.0 --port 9099

docker-build:  ## Build Docker image
	docker build -t aaisp-exporter:latest .

docker-run:  ## Run Docker container
	docker run -p 9099:9099 --env-file .env aaisp-exporter:latest

docker-compose-up:  ## Start with docker-compose
	docker-compose up -d

docker-compose-down:  ## Stop docker-compose
	docker-compose down

docs-serve:  ## Serve documentation locally (if using mkdocs)
	@if [ -f "mkdocs.yml" ]; then \
		uv run mkdocs serve; \
	else \
		echo "mkdocs.yml not found. Documentation not yet set up."; \
	fi

update-deps:  ## Update dependencies
	uv lock --upgrade

lock:  ## Generate uv.lock file
	uv lock

sync:  ## Sync environment with lock file
	uv sync
