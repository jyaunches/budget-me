"""Tests for liabilities upgrade functionality."""

from plaid.model.products import Products


class TestCreateLiabilitiesUpgradeToken:
    """Tests for creating liabilities upgrade link tokens."""

    def test_create_liabilities_upgrade_token_returns_token(self, monkeypatch, mocker):
        """create_liabilities_upgrade_token returns a link_token string."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_liabilities_upgrade_token

        get_settings.cache_clear()

        # Mock the Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-upgrade-token"

        # Mock the client's link_token_create method
        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client",
            return_value=mocker.MagicMock(
                link_token_create=mocker.MagicMock(return_value=mock_response)
            ),
        )

        link_token = create_liabilities_upgrade_token(
            access_token="access-sandbox-test-token"
        )

        assert link_token == "link-sandbox-upgrade-token"

    def test_create_liabilities_upgrade_token_uses_additional_consented_products(
        self, monkeypatch, mocker
    ):
        """create_liabilities_upgrade_token includes additional_consented_products."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_liabilities_upgrade_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-upgrade-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_liabilities_upgrade_token(access_token="access-sandbox-test-token")

        # Verify the request includes additional_consented_products
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        assert Products("liabilities") in request.additional_consented_products

    def test_create_liabilities_upgrade_token_includes_access_token(
        self, monkeypatch, mocker
    ):
        """create_liabilities_upgrade_token includes access_token in request."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_liabilities_upgrade_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-upgrade-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_liabilities_upgrade_token(access_token="access-sandbox-test-token")

        # Verify the request includes the access_token
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        assert request.access_token == "access-sandbox-test-token"

    def test_create_liabilities_upgrade_token_with_redirect_uri(
        self, monkeypatch, mocker
    ):
        """create_liabilities_upgrade_token includes redirect_uri when provided."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_liabilities_upgrade_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-upgrade-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_liabilities_upgrade_token(
            access_token="access-sandbox-test-token",
            redirect_uri="https://example.com/callback",
        )

        # Verify the request includes the redirect_uri
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        assert request.redirect_uri == "https://example.com/callback"
