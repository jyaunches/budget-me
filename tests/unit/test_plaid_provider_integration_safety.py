"""Fail-closed checks for the real Plaid Sandbox integration suite."""

from unittest.mock import Mock

import pytest

from tests.integration import conftest as integration_conftest

VALID_TEST_URL = (
    "postgresql://budget_me_test:budget_me_test@127.0.0.1/budget_me_plaid_test"
)


@pytest.fixture(autouse=True)
def valid_provider_gate(monkeypatch) -> None:
    """Start each test from an explicit, synthetic Sandbox configuration."""
    monkeypatch.setenv("BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS", "1")
    monkeypatch.setenv("BUDGET_ME_PLAID_TEST_DATABASE_URL", VALID_TEST_URL)
    monkeypatch.setenv("BUDGET_ME_PLAID_TEST_CLIENT_ID", "sandbox-test-client")
    monkeypatch.setenv("BUDGET_ME_PLAID_TEST_SECRET", "sandbox-test-secret")
    monkeypatch.setenv("PLAID_ENV", "sandbox")
    monkeypatch.delenv("CI", raising=False)


def test_provider_target_accepts_exact_loopback_database() -> None:
    """Accept only the dedicated provider-test database on loopback."""
    url = integration_conftest._validated_plaid_provider_test_url()

    assert url.host == "127.0.0.1"
    assert url.database == "budget_me_plaid_test"


def test_provider_target_requires_explicit_opt_in(monkeypatch) -> None:
    """Reject valid-looking inputs when the write/provider opt-in is absent."""
    monkeypatch.delenv("BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS")

    with pytest.raises(pytest.UsageError, match="provider tests are disabled"):
        integration_conftest._validated_plaid_provider_test_url()


def test_provider_target_never_falls_back_to_inherited_database_url(
    monkeypatch,
) -> None:
    """Ignore an ordinary live-looking DATABASE_URL when the test URL is absent."""
    monkeypatch.delenv("BUDGET_ME_PLAID_TEST_DATABASE_URL")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://owner:secret@db.example.com:5432/household_budget",
    )

    with pytest.raises(pytest.UsageError, match="DATABASE_URL and dotenv"):
        integration_conftest._validated_plaid_provider_test_url()


@pytest.mark.parametrize(
    ("url", "message"),
    [
        (
            "postgresql://test:test@127.0.0.1/postgres",
            "exact database name",
        ),
        (
            "postgresql://test:test@db.example.com/budget_me_plaid_test",
            "loopback host",
        ),
        (
            "sqlite:///budget_me_plaid_test",
            "PostgreSQL backend",
        ),
        (
            "postgresql://test:test@127.0.0.1/budget_me_plaid_test?sslmode=require",
            "must not include query parameters",
        ),
    ],
)
def test_provider_target_rejects_ordinary_or_ambiguous_database_urls(
    monkeypatch, url: str, message: str
) -> None:
    """Reject ordinary database names, remote hosts, and URL overrides."""
    monkeypatch.setenv("BUDGET_ME_PLAID_TEST_DATABASE_URL", url)

    with pytest.raises(pytest.UsageError, match=message):
        integration_conftest._validated_plaid_provider_test_url()


@pytest.mark.parametrize("plaid_env", ["production", "", "Sandbox"])
def test_provider_target_requires_exact_sandbox_environment(
    monkeypatch, plaid_env: str
) -> None:
    """Reject production and implicit or misspelled Plaid environments."""
    monkeypatch.setenv("PLAID_ENV", plaid_env)

    with pytest.raises(pytest.UsageError, match="PLAID_ENV=sandbox"):
        integration_conftest._validated_plaid_provider_test_url()


@pytest.mark.parametrize(
    "missing_variable",
    ["BUDGET_ME_PLAID_TEST_CLIENT_ID", "BUDGET_ME_PLAID_TEST_SECRET"],
)
def test_provider_target_ignores_inherited_ordinary_plaid_credentials(
    monkeypatch, missing_variable: str
) -> None:
    """Require dedicated credentials even when ordinary provider values exist."""
    monkeypatch.setenv("PLAID_CLIENT_ID", "inherited-live-looking-client")
    monkeypatch.setenv("PLAID_SECRET", "inherited-live-looking-secret")
    monkeypatch.setenv(missing_variable, "   ")

    with pytest.raises(pytest.UsageError, match="ordinary PLAID_CLIENT_ID"):
        integration_conftest._validated_plaid_provider_test_url()


def test_provider_target_allows_service_host_only_in_ci(monkeypatch) -> None:
    """Keep container service DNS unavailable to ordinary local runs."""
    monkeypatch.setenv(
        "BUDGET_ME_PLAID_TEST_DATABASE_URL",
        "postgresql://test:test@postgres/budget_me_plaid_test",
    )

    with pytest.raises(pytest.UsageError, match="accepted only when CI=true"):
        integration_conftest._validated_plaid_provider_test_url()

    monkeypatch.setenv("CI", "true")
    assert integration_conftest._validated_plaid_provider_test_url().host == "postgres"


def test_precollection_gate_rejects_before_calls_or_writes(monkeypatch) -> None:
    """Stop test execution before a provider function or database write can run."""
    provider_call = Mock()
    database_write = Mock()
    monkeypatch.delenv("BUDGET_ME_PLAID_TEST_DATABASE_URL")
    monkeypatch.delenv("BUDGET_ME_PLAID_TEST_CLIENT_ID")
    monkeypatch.delenv("BUDGET_ME_PLAID_TEST_SECRET")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://owner:secret@db.example.com:5432/household_budget",
    )
    monkeypatch.setenv("PLAID_CLIENT_ID", "inherited-live-looking-client")
    monkeypatch.setenv("PLAID_SECRET", "inherited-live-looking-secret")

    def continue_after_configuration() -> None:
        integration_conftest.pytest_configure(None)
        provider_call()
        database_write()

    with pytest.raises(pytest.UsageError, match="BUDGET_ME_PLAID_TEST_DATABASE_URL"):
        continue_after_configuration()

    provider_call.assert_not_called()
    database_write.assert_not_called()
