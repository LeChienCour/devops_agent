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

# ---------------------------------------------------------------------------
# Infrastructure (Terraform)
# ---------------------------------------------------------------------------
TF_DIR      := infra
DEMO_DIR    := infra/demo
TF_VARS     ?=                          # e.g. TF_VARS="-var='environment=prod'"

.PHONY: tf-init
tf-init: ## Init Terraform (agent infra)
	terraform -chdir=$(TF_DIR) init

.PHONY: tf-plan
tf-plan: ## Plan agent infra (shows what will change — no resources created)
	terraform -chdir=$(TF_DIR) plan $(TF_VARS)

.PHONY: tf-apply
tf-apply: ## Apply agent infra (requires manual approval unless TF_AUTO_APPROVE=1)
	@if [ "$(TF_AUTO_APPROVE)" = "1" ]; then \
		terraform -chdir=$(TF_DIR) apply -auto-approve $(TF_VARS); \
	else \
		terraform -chdir=$(TF_DIR) apply $(TF_VARS); \
	fi

.PHONY: tf-destroy
tf-destroy: ## Destroy agent infra (requires manual confirmation)
	terraform -chdir=$(TF_DIR) destroy $(TF_VARS)

.PHONY: tf-fmt
tf-fmt: ## Format all Terraform files in infra/ (recursive)
	terraform fmt -recursive $(TF_DIR)

.PHONY: seed-demo
seed-demo: ## Deploy demo leak resources (independent — safe to run alongside agent infra)
	@echo "Initialising demo Terraform root..."
	terraform -chdir=$(DEMO_DIR) init
	@echo "Applying seed_leaks resources..."
	terraform -chdir=$(DEMO_DIR) apply $(TF_VARS)
	@echo ""
	@echo "Demo leaks deployed. Run 'make cleanup-demo' to destroy them after the demo."

.PHONY: cleanup-demo
cleanup-demo: ## Destroy demo leak resources (leaves agent infra untouched)
	@echo "Destroying seed_leaks resources..."
	terraform -chdir=$(DEMO_DIR) destroy $(TF_VARS)
	@echo "Demo resources cleaned up."

# ---------------------------------------------------------------------------
# Lambda build & deploy
# ---------------------------------------------------------------------------
DEPLOY_ENV     ?= dev
DEPLOY_REGION  ?= us-east-1
PROJECT_NAME   ?= finops-agent
FUNCTION_NAME  ?= $(PROJECT_NAME)-agent-$(DEPLOY_ENV)
BUILD_DIR      := dist/lambda_package
LAMBDA_ZIP     := dist/lambda.zip

.PHONY: build
build: ## Build Lambda deployment zip (Linux-compatible wheels via --platform)
	@echo "Building Lambda package..."
	rm -rf $(BUILD_DIR) $(LAMBDA_ZIP)
	mkdir -p $(BUILD_DIR)
	@echo "Installing dependencies (manylinux2014_x86_64)..."
	python -m pip install \
		--platform manylinux2014_x86_64 \
		--target $(BUILD_DIR) \
		--implementation cp \
		--python-version 312 \
		--only-binary=:all: \
		--quiet \
		-r requirements-lambda.txt
	@echo "Copying source modules..."
	cp -r src/agent          $(BUILD_DIR)/agent
	cp -r src/common         $(BUILD_DIR)/common
	cp -r src/notifications  $(BUILD_DIR)/notifications
	@echo "Zipping..."
	cd $(BUILD_DIR) && zip -qr ../../$(LAMBDA_ZIP) . \
		--exclude "*.pyc" --exclude "*/__pycache__/*" --exclude "*.dist-info/*"
	@echo "Done: $(LAMBDA_ZIP) ($$(du -sh $(LAMBDA_ZIP) | cut -f1))"

.PHONY: deploy
deploy: build ## Build Lambda zip and upload to AWS (DEPLOY_ENV=dev DEPLOY_REGION=us-east-1)
	@echo "Deploying $(LAMBDA_ZIP) → $(FUNCTION_NAME) [$(DEPLOY_REGION)]..."
	aws lambda update-function-code \
		--function-name $(FUNCTION_NAME) \
		--zip-file fileb://$(LAMBDA_ZIP) \
		--region $(DEPLOY_REGION) \
		--no-cli-pager
	@echo "Waiting for update to complete..."
	aws lambda wait function-updated \
		--function-name $(FUNCTION_NAME) \
		--region $(DEPLOY_REGION)
	@echo "Deploy complete. Run 'make invoke' to trigger an investigation."

.PHONY: invoke
invoke: ## Trigger an on-demand investigation on the deployed Lambda
	@echo "Invoking $(FUNCTION_NAME)..."
	@aws lambda invoke \
		--function-name $(FUNCTION_NAME) \
		--payload '{"trigger": "on_demand"}' \
		--cli-binary-format raw-in-base64-out \
		--region $(DEPLOY_REGION) \
		--no-cli-pager \
		/tmp/finops_response.json
	@echo ""
	@echo "--- Response ---"
	@python3 -m json.tool /tmp/finops_response.json

.PHONY: logs
logs: ## Tail CloudWatch logs for the Lambda function (live stream)
	aws logs tail /aws/lambda/$(FUNCTION_NAME) \
		--follow \
		--region $(DEPLOY_REGION) \
		--format short
