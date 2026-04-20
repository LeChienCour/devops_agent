.DEFAULT_GOAL := help
SHELL := /bin/bash

SRC_DIRS := src/ tests/

# ---------------------------------------------------------------------------
# Help (auto-generated from ## comments)
# ---------------------------------------------------------------------------
.PHONY: help
help: ## Show this help message
	@echo "FinOps Agent — available targets:"
	@echo ""
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'
	@echo ""

# ---------------------------------------------------------------------------
# Setup
# ---------------------------------------------------------------------------
.PHONY: install
install: ## Install all dependencies (uses uv if available, otherwise pip)
	@if command -v uv >/dev/null 2>&1; then \
		echo "Using uv..."; \
		uv sync --all-extras; \
	else \
		echo "uv not found, using pip..."; \
		pip install -e ".[dev]"; \
	fi

# ---------------------------------------------------------------------------
# Code quality
# ---------------------------------------------------------------------------
.PHONY: lint
lint: ## Run ruff linter and format checker (no writes)
	ruff check $(SRC_DIRS)
	ruff format --check $(SRC_DIRS)

.PHONY: format
format: ## Auto-format code and apply safe lint fixes
	ruff format $(SRC_DIRS)
	ruff check --fix $(SRC_DIRS)

.PHONY: typecheck
typecheck: ## Run mypy strict type checker against src/
	mypy src/

# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------
.PHONY: test
test: ## Run unit tests with short traceback
	pytest tests/unit/ -v --tb=short

.PHONY: test-integration
test-integration: ## Run integration tests (requires AWS credentials or moto)
	pytest tests/integration/ -v --tb=short

.PHONY: test-all
test-all: ## Run all tests with coverage report
	pytest tests/ -v --cov=src --cov-report=term-missing

# ---------------------------------------------------------------------------
# Housekeeping
# ---------------------------------------------------------------------------
.PHONY: clean
clean: ## Remove all generated/cache artifacts
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".mypy_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".ruff_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name ".pytest_cache" -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "dist"         -exec rm -rf {} + 2>/dev/null || true
	find . -type d -name "*.egg-info"   -exec rm -rf {} + 2>/dev/null || true
	@echo "Clean complete."
