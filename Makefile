.PHONY: help install install-dev test test-coverage lint format format-check check validate-configs clean run pre-commit-install pre-commit-run build publish publish-test ci

# Default target
.DEFAULT_GOAL := help

# Colors for output
BLUE   := \033[0;34m
GREEN  := \033[0;32m
YELLOW := \033[0;33m
RED    := \033[0;31m
NC     := \033[0m

help: ## Show this help message
	@echo "$(BLUE)mock-mcp-server - Development Commands$(NC)"
	@echo ""
	@echo "$(GREEN)Setup:$(NC)"
	@grep -E '^install.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Testing:$(NC)"
	@grep -E '^(test|validate-configs).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Code Quality:$(NC)"
	@grep -E '^(lint|format|format-check|check|ci):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Running:$(NC)"
	@grep -E '^run.*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Publishing:$(NC)"
	@grep -E '^(build|publish).*:.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'
	@echo ""
	@echo "$(GREEN)Utilities:$(NC)"
	@grep -E '^(clean|pre-commit-install|pre-commit-run):.*##' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*##"}; {printf "  $(BLUE)%-22s$(NC) %s\n", $$1, $$2}'

# --- setup ------------------------------------------------------------------

install: ## Install runtime dependencies only
	@echo "$(GREEN)Installing runtime dependencies...$(NC)"
	uv sync --no-dev
	@echo "$(GREEN)+ Done$(NC)"

install-dev: ## Install runtime + dev dependencies
	@echo "$(GREEN)Installing dev dependencies...$(NC)"
	uv sync
	@echo "$(GREEN)+ Done$(NC)"

# --- testing ----------------------------------------------------------------

test: ## Run the full test suite
	@echo "$(GREEN)Running tests...$(NC)"
	uv run pytest
	@echo "$(GREEN)+ All tests passed$(NC)"

test-coverage: ## Run tests with coverage report
	@echo "$(GREEN)Running tests with coverage...$(NC)"
	uv run pytest --cov=app --cov-report=term-missing --cov-report=html
	@echo "$(YELLOW)HTML coverage at htmlcov/index.html$(NC)"

validate-configs: ## Load + build every YAML profile in configs/
	@echo "$(GREEN)Validating configs...$(NC)"
	uv run pytest tests/test_configs.py -v
	@echo "$(GREEN)+ All configs valid$(NC)"

# --- code quality -----------------------------------------------------------

lint: ## Run linter (ruff check)
	uv run ruff check app tests

format: ## Format code (ruff format) and auto-fix lint issues
	uv run ruff format app tests
	uv run ruff check --fix app tests

format-check: ## Check formatting without writing changes
	uv run ruff format --check app tests
	uv run ruff check app tests

typecheck: ## Run mypy
	uv run mypy app

check: format-check lint typecheck test validate-configs ## Run all checks in order
	@echo "$(GREEN)+ All checks passed$(NC)"

ci: check ## Alias used by GitHub Actions
	@echo "$(GREEN)+ CI checks passed$(NC)"

# --- run --------------------------------------------------------------------

run: ## Run the bundled monthly-report profile
	uv run mock-mcp --config monthly-report

run-help: ## Show CLI help
	uv run mock-mcp --help

# --- pre-commit -------------------------------------------------------------

pre-commit-install: ## Install pre-commit git hooks
	uv run pre-commit install

pre-commit-run: ## Run all pre-commit hooks against all files
	uv run pre-commit run --all-files

# --- packaging --------------------------------------------------------------

clean: ## Remove build artifacts and caches
	@find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	@find . -type f -name "*.pyc" -delete
	@find . -type f -name "*.pyo" -delete
	@find . -type d -name "*.egg-info" -exec rm -rf {} + 2>/dev/null || true
	@rm -rf build/ dist/ .pytest_cache/ .mypy_cache/ .ruff_cache/ htmlcov/ .coverage
	@echo "$(GREEN)+ Clean$(NC)"

build: clean ## Build sdist + wheel into dist/
	uv build
	@ls -la dist/

publish-test: build ## Publish to TestPyPI
	uv publish --publish-url https://test.pypi.org/legacy/

publish: build ## Publish to PyPI
	uv publish
