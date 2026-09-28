"""Shared test fixtures and configuration."""

import os

import pytest
from fastapi.testclient import TestClient

UNIT_DATABASE_ENV_VARS = (
    "DATABASE_URL",
    "DATABASE_URL_DEV",
    "DATABASE_URL_PROD",
)

# Unit tests must not inherit a developer's private dotenv values. Provider and
# encryption settings are deliberately synthetic and database settings remain
# unset so an accidental database access fails closed.
os.environ["BUDGET_ME_DISABLE_DOTENV"] = "1"
if os.environ.get("BUDGET_ME_ALLOW_INTEGRATION_TESTS") != "1":
    for variable in UNIT_DATABASE_ENV_VARS:
        os.environ.pop(variable, None)
    os.environ.update(
        {
            "APP_TOKEN_ENC_KEY": ("MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="),
            "PLAID_CLIENT_ID": "test-client",
            "PLAID_SECRET": "test-secret",
            "PLAID_ENV": "sandbox",
            "AUTH_REQUIRED": "false",
        }
    )

DATABASE_TEST_PATHS = {
    "tests/unit/streamlit_app/test_monthly_snapshot_page.py",
}


def pytest_collection_modifyitems(items):
    """Keep database/provider tests behind explicit, process-wide opt-ins."""
    integration_allowed = os.environ.get("BUDGET_ME_ALLOW_INTEGRATION_TESTS") == "1"
    plaid_provider_allowed = (
        os.environ.get("BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS") == "1"
    )

    for item in items:
        item_path = item.path.as_posix()

        if "/tests/integration/" in f"/{item_path}" or item_path.startswith(
            "tests/integration/"
        ):
            item.add_marker(pytest.mark.integration)
            if not integration_allowed:
                item.add_marker(
                    pytest.mark.skip(
                        reason=(
                            "integration tests require "
                            "BUDGET_ME_ALLOW_INTEGRATION_TESTS=1 and disposable services"
                        )
                    )
                )

        if any(item_path.endswith(path) for path in DATABASE_TEST_PATHS):
            item.add_marker(pytest.mark.requires_database)

        if (
            item.get_closest_marker("plaid_provider_integration") is not None
            and not plaid_provider_allowed
        ):
            item.add_marker(
                pytest.mark.skip(
                    reason=(
                        "Plaid provider tests require the dedicated "
                        "BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1 safety gate"
                    )
                )
            )


@pytest.fixture
def app():
    """Create application instance for testing."""
    from budget_me.api.app import create_app

    return create_app()


@pytest.fixture
def client(app):
    """Create test client."""
    return TestClient(app)


@pytest.fixture
def mock_env(monkeypatch):
    """Mock environment variables for testing."""
    # Add environment variable mocks as needed
    pass
