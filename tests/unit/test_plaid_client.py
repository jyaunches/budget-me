"""Tests for Plaid client module."""


class TestPlaidClient:
    """Tests for PlaidClient wrapper."""

    def test_plaid_client_uses_correct_host_sandbox(self, monkeypatch):
        """PlaidClient configured for sandbox.plaid.com when PLAID_ENV=sandbox."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.client import get_plaid_client

        get_settings.cache_clear()

        client = get_plaid_client()

        # Check that host is set to sandbox
        assert "sandbox" in client.api_client.configuration.host

    def test_plaid_client_uses_production_host(self, monkeypatch):
        """PlaidClient configured for production.plaid.com when PLAID_ENV=production."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "production")

        from budget_me.config import get_settings
        from budget_me.plaid.client import get_plaid_client

        get_settings.cache_clear()

        client = get_plaid_client()

        # Check that host is set to production
        assert "production" in client.api_client.configuration.host

    def test_plaid_client_caching(self, monkeypatch):
        """get_plaid_client returns same instance on subsequent calls."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.client import get_plaid_client

        get_settings.cache_clear()

        client1 = get_plaid_client()
        client2 = get_plaid_client()

        # Should be the same instance
        assert client1 is client2
