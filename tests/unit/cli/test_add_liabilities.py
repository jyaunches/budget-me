"""Tests for add_liabilities CLI command."""

import warnings


class TestAddLiabilitiesDeprecation:
    """Tests for add_liabilities command deprecation warnings."""

    def test_add_liabilities_command_shows_deprecation_warning(
        self, mocker, monkeypatch
    ):
        """add_liabilities command emits deprecation warning."""
        # Set required environment variables
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.cli.commands.add_liabilities import add_liabilities_command
        from budget_me.config import get_settings

        get_settings.cache_clear()

        # Mock asyncio.run to prevent actual execution (imported inside function)
        import asyncio

        mocker.patch.object(asyncio, "run")

        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            add_liabilities_command()

            # Verify deprecation warning was emitted
            assert len(w) >= 1
            deprecation_warnings = [
                warning
                for warning in w
                if issubclass(warning.category, DeprecationWarning)
            ]
            assert len(deprecation_warnings) == 1
            assert "deprecated" in str(deprecation_warnings[0].message).lower()
            assert "streamlit" in str(deprecation_warnings[0].message).lower()
