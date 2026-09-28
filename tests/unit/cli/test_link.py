"""Tests for link CLI command."""

import warnings


class TestLinkDeprecation:
    """Tests for link command deprecation warnings."""

    def test_link_command_shows_deprecation_warning(self, mocker, monkeypatch):
        """link command emits deprecation warning."""
        # Set required environment variables
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        # Mock server startup and webbrowser to prevent actual execution
        mocker.patch("budget_me.cli.commands.link.start_link_server")
        mocker.patch("budget_me.cli.commands.link.webbrowser.open")

        from budget_me.cli.commands.link import link_command
        from budget_me.config import get_settings

        get_settings.cache_clear()

        # Capture warnings
        with warnings.catch_warnings(record=True) as w:
            warnings.simplefilter("always")
            link_command()

            # Verify deprecation warning was emitted
            link_warnings = [
                warning
                for warning in w
                if issubclass(warning.category, DeprecationWarning)
                and "budget-me link" in str(warning.message)
            ]
            assert len(link_warnings) == 1
            assert "deprecated" in str(link_warnings[0].message).lower()
            assert "streamlit" in str(link_warnings[0].message).lower()
