# Budget Me Development Makefile
# Use uv as the package manager for all operations

.PHONY: help install dev audit test test-verbose test-cov test-file lint format check clean serve streamlit db-migrate db-downgrade db-reset db-history generate-key rules-status rules-import rules-export test-database-integration test-plaid-integration

help: ## Show available commands
	@echo "Budget Me Development Commands:"
	@echo "================================"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-15s %s\n", $$1, $$2}'

install: ## Install production dependencies
	uv sync --no-dev

dev: ## Install all dependencies including development tools
	uv sync --all-extras

audit: ## Audit locked runtime dependencies for known vulnerabilities
	@BUDGET_ME_AUDIT_REQUIREMENTS="$$(mktemp)"; \
	trap 'rm -f "$$BUDGET_ME_AUDIT_REQUIREMENTS"' EXIT; \
	uv export --frozen --no-dev --no-emit-project --output-file "$$BUDGET_ME_AUDIT_REQUIREMENTS" >/dev/null; \
	uv run pip-audit --requirement "$$BUDGET_ME_AUDIT_REQUIREMENTS" --no-deps --disable-pip

test: ## Run unit tests
	PYTHONPATH=src uv run pytest tests/unit/ -v

test-verbose: ## Run unit tests with verbose output
	PYTHONPATH=src uv run pytest tests/unit/ -vv

test-cov: ## Run unit tests with coverage reporting
	PYTHONPATH=src uv run pytest tests/unit/ -v --cov=src --cov-report=html --cov-report=term-missing

test-file: ## Run specific test file (use FILE=path/to/test.py)
	PYTHONPATH=src uv run pytest $(FILE) -v

test-database-integration: ## Migrate and test an explicitly configured disposable PostgreSQL database
	@test "$(BUDGET_ME_ALLOW_DATABASE_TESTS)" = "1" || { echo "Refusing: set BUDGET_ME_ALLOW_DATABASE_TESTS=1 only for a disposable PostgreSQL database."; exit 1; }
	@test -n "$(BUDGET_ME_TEST_DATABASE_URL)" || { echo "Refusing: set BUDGET_ME_TEST_DATABASE_URL; DATABASE_URL and .env are ignored."; exit 1; }
	BUDGET_ME_DISABLE_DOTENV=1 BUDGET_ME_ALLOW_INTEGRATION_TESTS=1 BUDGET_ME_ALLOW_DATABASE_TESTS="$(BUDGET_ME_ALLOW_DATABASE_TESTS)" BUDGET_ME_TEST_DATABASE_URL="$(BUDGET_ME_TEST_DATABASE_URL)" APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run pytest tests/integration/test_database_readiness.py::test_database_target_is_disposable -q --no-cov -m database_integration
	BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$(BUDGET_ME_TEST_DATABASE_URL)" PYTHONPATH=src uv run alembic upgrade head
	BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$(BUDGET_ME_TEST_DATABASE_URL)" PYTHONPATH=src uv run alembic current --check-heads
	BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$(BUDGET_ME_TEST_DATABASE_URL)" PYTHONPATH=src uv run alembic check
	BUDGET_ME_DISABLE_DOTENV=1 BUDGET_ME_ALLOW_INTEGRATION_TESTS=1 BUDGET_ME_ALLOW_DATABASE_TESTS="$(BUDGET_ME_ALLOW_DATABASE_TESTS)" BUDGET_ME_TEST_DATABASE_URL="$(BUDGET_ME_TEST_DATABASE_URL)" APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run pytest tests/integration/ -v --no-cov -m database_integration

test-plaid-integration: ## Migrate and run the explicitly gated real Plaid Sandbox suite
	@test "$$BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS" = "1" || { echo "Refusing: set BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1 only for an intentional Plaid Sandbox run."; exit 1; }
	@test -n "$$BUDGET_ME_PLAID_TEST_DATABASE_URL" || { echo "Refusing: set BUDGET_ME_PLAID_TEST_DATABASE_URL; ordinary DATABASE_URL values and .env are ignored."; exit 1; }
	@test "$$PLAID_ENV" = "sandbox" || { echo "Refusing: set PLAID_ENV=sandbox exactly."; exit 1; }
	@test -n "$$BUDGET_ME_PLAID_TEST_CLIENT_ID" || { echo "Refusing: set the dedicated BUDGET_ME_PLAID_TEST_CLIENT_ID."; exit 1; }
	@test -n "$$BUDGET_ME_PLAID_TEST_SECRET" || { echo "Refusing: set the dedicated BUDGET_ME_PLAID_TEST_SECRET."; exit 1; }
	@BUDGET_ME_DISABLE_DOTENV=1 BUDGET_ME_ALLOW_INTEGRATION_TESTS=1 BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1 DATABASE_URL= DATABASE_URL_DEV= DATABASE_URL_PROD= PLAID_CLIENT_ID= PLAID_SECRET= APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run pytest tests/integration/test_plaid_integration.py --collect-only -q --no-cov -m plaid_provider_integration
	@BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$$BUDGET_ME_PLAID_TEST_DATABASE_URL" DATABASE_URL_DEV= DATABASE_URL_PROD= PLAID_CLIENT_ID= PLAID_SECRET= APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run alembic upgrade head
	@BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$$BUDGET_ME_PLAID_TEST_DATABASE_URL" DATABASE_URL_DEV= DATABASE_URL_PROD= PLAID_CLIENT_ID= PLAID_SECRET= APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run alembic current --check-heads
	@BUDGET_ME_DISABLE_DOTENV=1 DATABASE_URL="$$BUDGET_ME_PLAID_TEST_DATABASE_URL" DATABASE_URL_DEV= DATABASE_URL_PROD= PLAID_CLIENT_ID= PLAID_SECRET= APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run alembic check
	@BUDGET_ME_DISABLE_DOTENV=1 BUDGET_ME_ALLOW_INTEGRATION_TESTS=1 BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1 DATABASE_URL= DATABASE_URL_DEV= DATABASE_URL_PROD= PLAID_CLIENT_ID= PLAID_SECRET= APP_TOKEN_ENC_KEY=MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA= PYTHONPATH=src uv run pytest tests/integration/test_plaid_integration.py -v --no-cov -m plaid_provider_integration

lint: ## Run code linting with ruff
	uv run ruff check src tests

format: ## Format code with ruff
	uv run ruff format src tests
	uv run ruff check --fix src tests

check: ## Run full code quality check (lint + test)
	make lint
	make test

clean: ## Clean build artifacts and cache
	rm -rf .pytest_cache/
	rm -rf htmlcov/
	rm -rf .coverage
	rm -rf build/
	rm -rf dist/
	rm -rf *.egg-info/
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete

serve: ## Start development server with hot reload
	PYTHONPATH=src uv run uvicorn budget_me.api.app:create_app --factory --host 0.0.0.0 --port 8000 --reload

# Database commands
db-migrate: ## Run database migrations (upgrade to latest)
	PYTHONPATH=src uv run alembic upgrade head

db-downgrade: ## Rollback one database migration
	PYTHONPATH=src uv run alembic downgrade -1

db-reset: ## Reset database (downgrade all, then upgrade) - DEV ONLY!
	@test "$$BUDGET_ME_ALLOW_DB_RESET" = "1" || { echo "Refusing: set BUDGET_ME_ALLOW_DB_RESET=1 only for a disposable development database."; exit 1; }
	@echo "WARNING: This will reset your database!"
	@read -p "Are you sure? [y/N] " confirm && [ "$$confirm" = "y" ] || exit 1
	PYTHONPATH=src uv run alembic downgrade base
	PYTHONPATH=src uv run alembic upgrade head

db-history: ## Show migration history
	PYTHONPATH=src uv run alembic history --verbose

db-current: ## Show current migration revision
	PYTHONPATH=src uv run alembic current

# Streamlit app
streamlit: ## Launch Streamlit transaction review app
	PYTHONPATH=src uv run streamlit run --server.address 127.0.0.1 src/budget_me/streamlit_app/app.py

# Categorization-rule commands
rules-status: ## Show effective packaged and PostgreSQL categorization-rule counts
	PYTHONPATH=src uv run budget-me rules status

rules-import: ## Merge RULES_FILE into PostgreSQL (use the CLI directly for safety flags)
	@test -n "$$RULES_FILE" || { echo "Refusing: set RULES_FILE to a protected categorization-rules YAML file."; exit 1; }
	PYTHONPATH=src uv run budget-me rules import "$$RULES_FILE"

rules-export: ## Export effective rules to RULES_FILE (refuses to overwrite)
	@test -n "$$RULES_FILE" || { echo "Refusing: set RULES_FILE to a protected destination YAML file."; exit 1; }
	PYTHONPATH=src uv run budget-me rules export "$$RULES_FILE"

# Utility commands

generate-key: ## Generate a new Fernet encryption key
	@uv run python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
