"""Shared fixtures and safety gates for integration tests."""

import os
from pathlib import Path

import pytest
from sqlalchemy.engine import URL, make_url
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.engine import get_engine

DATABASE_INTEGRATION_MODULES = {
    "test_account_balance_snapshot_repo.py",
    "test_anticipated_item_migration.py",
    "test_balance_calculation.py",
    "test_category_budget_db.py",
    "test_close_snapshot_balance.py",
    "test_database_readiness.py",
    "test_funding_sources_migration.py",
    "test_guarded_snapshot_close.py",
    "test_per_account_snapshots_migration.py",
    "test_projected_payment_migration.py",
    "test_reimbursement_link_db.py",
    "test_snapshot_reconciliation.py",
    "test_transaction_migration.py",
}
LOCAL_DATABASE_HOSTS = {"127.0.0.1", "localhost", "::1"}
CI_DATABASE_HOSTS = {"postgres"}
TEST_DATABASE_NAME = "budget_me_test"
PLAID_PROVIDER_TEST_MODULE = "test_plaid_integration.py"
PLAID_PROVIDER_TEST_DATABASE_NAME = "budget_me_plaid_test"
PLAID_PROVIDER_CREDENTIAL_ENV_VARS = (
    "BUDGET_ME_PLAID_TEST_CLIENT_ID",
    "BUDGET_ME_PLAID_TEST_SECRET",
)


def pytest_configure(config):
    """Validate explicit provider inputs before provider tests are collected."""
    del config
    if os.environ.get("BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS") == "1":
        _validated_plaid_provider_test_url()


@pytest.hookimpl(tryfirst=True)
def pytest_collection_modifyitems(items):
    """Mark only database-backed, provider-free integration modules."""
    for item in items:
        path = Path(str(item.path))
        if (
            path.parent.name == "integration"
            and path.name in DATABASE_INTEGRATION_MODULES
        ):
            item.add_marker(pytest.mark.database_integration)
        if (
            path.parent.name == "integration"
            and path.name == PLAID_PROVIDER_TEST_MODULE
        ):
            item.add_marker(pytest.mark.plaid_provider_integration)


def _validated_database_test_url() -> URL:
    """Return the explicitly configured disposable PostgreSQL target."""
    if os.environ.get("BUDGET_ME_ALLOW_DATABASE_TESTS") != "1":
        raise pytest.UsageError(
            "Database tests are disabled. Set BUDGET_ME_ALLOW_DATABASE_TESTS=1 "
            "only for a disposable PostgreSQL database."
        )

    raw_url = os.environ.get("BUDGET_ME_TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError(
            "Database tests require BUDGET_ME_TEST_DATABASE_URL; DATABASE_URL and "
            "dotenv values are intentionally ignored."
        )

    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise pytest.UsageError(
            "BUDGET_ME_TEST_DATABASE_URL is not a valid SQLAlchemy URL."
        ) from exc

    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError(
            "BUDGET_ME_TEST_DATABASE_URL must use the PostgreSQL backend."
        )
    if url.query:
        raise pytest.UsageError(
            "BUDGET_ME_TEST_DATABASE_URL must not include query parameters."
        )
    if url.database != TEST_DATABASE_NAME:
        raise pytest.UsageError(
            f"Database tests require the exact database name {TEST_DATABASE_NAME!r}."
        )

    allowed_hosts = set(LOCAL_DATABASE_HOSTS)
    if os.environ.get("CI", "").lower() == "true":
        allowed_hosts.update(CI_DATABASE_HOSTS)
    if url.host not in allowed_hosts:
        raise pytest.UsageError(
            "Database tests require a loopback host. The 'postgres' service host "
            "is accepted only when CI=true."
        )

    return url


def _validated_plaid_provider_test_url() -> URL:
    """Return an explicit disposable DB target for real Plaid Sandbox tests."""
    if os.environ.get("BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS") != "1":
        raise pytest.UsageError(
            "Plaid provider tests are disabled. Set "
            "BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1 only for an intentional "
            "Plaid Sandbox run."
        )

    raw_url = os.environ.get("BUDGET_ME_PLAID_TEST_DATABASE_URL")
    if not raw_url:
        raise pytest.UsageError(
            "Plaid provider tests require BUDGET_ME_PLAID_TEST_DATABASE_URL; "
            "DATABASE_URL and dotenv values are intentionally ignored."
        )

    try:
        url = make_url(raw_url)
    except Exception as exc:
        raise pytest.UsageError(
            "BUDGET_ME_PLAID_TEST_DATABASE_URL is not a valid SQLAlchemy URL."
        ) from exc

    if url.get_backend_name() != "postgresql":
        raise pytest.UsageError(
            "BUDGET_ME_PLAID_TEST_DATABASE_URL must use the PostgreSQL backend."
        )
    if url.query:
        raise pytest.UsageError(
            "BUDGET_ME_PLAID_TEST_DATABASE_URL must not include query parameters."
        )
    if url.database != PLAID_PROVIDER_TEST_DATABASE_NAME:
        raise pytest.UsageError(
            "Plaid provider tests require the exact database name "
            f"{PLAID_PROVIDER_TEST_DATABASE_NAME!r}."
        )

    allowed_hosts = set(LOCAL_DATABASE_HOSTS)
    if os.environ.get("CI", "").lower() == "true":
        allowed_hosts.update(CI_DATABASE_HOSTS)
    if url.host not in allowed_hosts:
        raise pytest.UsageError(
            "Plaid provider tests require a loopback host. The 'postgres' service "
            "host is accepted only when CI=true."
        )

    if os.environ.get("PLAID_ENV") != "sandbox":
        raise pytest.UsageError(
            "Plaid provider tests require the explicit setting PLAID_ENV=sandbox."
        )

    missing_credentials = [
        variable
        for variable in PLAID_PROVIDER_CREDENTIAL_ENV_VARS
        if not os.environ.get(variable, "").strip()
    ]
    if missing_credentials:
        raise pytest.UsageError(
            "Plaid provider tests require explicit dedicated Sandbox client and "
            "secret values; ordinary PLAID_CLIENT_ID and PLAID_SECRET values are "
            "intentionally ignored."
        )

    return url


@pytest.fixture(autouse=True)
def database_test_target(request, monkeypatch):
    """Route marked tests only to the validated disposable database URL."""
    if request.node.get_closest_marker("database_integration") is None:
        yield None
        return

    url = _validated_database_test_url()
    raw_url = url.render_as_string(hide_password=False)

    monkeypatch.setenv("BUDGET_ME_DISABLE_DOTENV", "1")
    monkeypatch.setenv("DATABASE_URL", raw_url)
    monkeypatch.delenv("DATABASE_URL_DEV", raising=False)
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)

    import budget_me.config as config_module

    original_settings = config_module.settings
    config_module.get_settings.cache_clear()
    config_module.settings = config_module.get_settings()
    get_engine.cache_clear()
    try:
        yield url
    finally:
        get_engine.cache_clear()
        config_module.get_settings.cache_clear()
        config_module.settings = original_settings


@pytest.fixture(autouse=True)
def plaid_provider_test_target(request, monkeypatch):
    """Route provider tests only after all dedicated Sandbox gates pass."""
    if request.node.get_closest_marker("plaid_provider_integration") is None:
        yield None
        return

    url = _validated_plaid_provider_test_url()
    raw_url = url.render_as_string(hide_password=False)

    monkeypatch.setenv("BUDGET_ME_DISABLE_DOTENV", "1")
    monkeypatch.setenv("DATABASE_URL", raw_url)
    monkeypatch.delenv("DATABASE_URL_DEV", raising=False)
    monkeypatch.delenv("DATABASE_URL_PROD", raising=False)
    monkeypatch.setenv("PLAID_CLIENT_ID", os.environ["BUDGET_ME_PLAID_TEST_CLIENT_ID"])
    monkeypatch.setenv("PLAID_SECRET", os.environ["BUDGET_ME_PLAID_TEST_SECRET"])
    monkeypatch.setenv("PLAID_ENV", "sandbox")

    import budget_me.config as config_module
    import budget_me.plaid.client as plaid_client_module

    original_settings = config_module.settings
    config_module.get_settings.cache_clear()
    config_module.settings = config_module.get_settings()
    plaid_client_module._client_cache.clear()
    get_engine.cache_clear()
    try:
        yield url
    finally:
        get_engine.cache_clear()
        plaid_client_module._client_cache.clear()
        config_module.get_settings.cache_clear()
        config_module.settings = original_settings


@pytest.fixture(autouse=True)
async def cleanup_connections(
    request, database_test_target, plaid_provider_test_target
):
    """Ensure database connections are properly cleaned up after each test."""
    yield
    if (
        request.node.get_closest_marker("database_integration") is not None
        or request.node.get_closest_marker("plaid_provider_integration") is not None
    ):
        engine = get_engine()
        await engine.dispose()


@pytest.fixture
async def db_session(database_test_target):
    """Provide a database session that rolls back after each test.

    This fixture creates a connection with a savepoint, yields a session,
    then rolls back all changes. This prevents test data from polluting
    the database.
    """
    engine = get_engine()
    async with engine.connect() as conn:
        trans = await conn.begin()
        try:
            session = AsyncSession(bind=conn, expire_on_commit=False)
            try:
                yield session, conn
            finally:
                await session.close()
        finally:
            if trans.is_active:
                await trans.rollback()
