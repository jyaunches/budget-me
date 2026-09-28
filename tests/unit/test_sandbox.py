"""Tests for Plaid Sandbox utilities."""


class TestSandboxHelpers:
    """Tests for sandbox test helper functions."""

    def test_sandbox_create_item(self, monkeypatch, mocker):
        """create_sandbox_item returns public_token for testing."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.sandbox import create_sandbox_item

        get_settings.cache_clear()

        # Mock Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.public_token = "public-sandbox-token-123"

        mock_client = mocker.MagicMock()
        mock_client.sandbox_public_token_create.return_value = mock_response

        mocker.patch(
            "budget_me.plaid.sandbox.get_plaid_client",
            return_value=mock_client,
        )

        # Create sandbox item
        institution_id = "ins_109508"  # First Platypus Bank
        products = ["transactions"]

        public_token = create_sandbox_item(institution_id, products)

        # Verify we got a public token back
        assert public_token == "public-sandbox-token-123"
        mock_client.sandbox_public_token_create.assert_called_once()

    def test_sandbox_fire_webhook(self, monkeypatch, mocker):
        """fire_sandbox_webhook triggers webhook successfully."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.sandbox import fire_sandbox_webhook

        get_settings.cache_clear()

        # Mock Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.webhook_fired = True

        mock_client = mocker.MagicMock()
        mock_client.sandbox_item_fire_webhook.return_value = mock_response

        mocker.patch(
            "budget_me.plaid.sandbox.get_plaid_client",
            return_value=mock_client,
        )

        # Fire webhook
        access_token = "access-sandbox-token"
        webhook_code = "DEFAULT_UPDATE"

        result = fire_sandbox_webhook(access_token, webhook_code)

        # Verify webhook was fired
        assert result is True
        mock_client.sandbox_item_fire_webhook.assert_called_once()

    def test_sandbox_reset_login(self, monkeypatch, mocker):
        """reset_sandbox_login forces item into LOGIN_REQUIRED state."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.sandbox import reset_sandbox_login

        get_settings.cache_clear()

        # Mock Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.reset_login = True

        mock_client = mocker.MagicMock()
        mock_client.sandbox_item_reset_login.return_value = mock_response

        mocker.patch(
            "budget_me.plaid.sandbox.get_plaid_client",
            return_value=mock_client,
        )

        # Reset item login
        access_token = "access-sandbox-token"

        result = reset_sandbox_login(access_token)

        # Verify login was reset
        assert result is True
        mock_client.sandbox_item_reset_login.assert_called_once()

    def test_sandbox_create_item_with_options(self, monkeypatch, mocker):
        """create_sandbox_item accepts optional parameters."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.sandbox import create_sandbox_item

        get_settings.cache_clear()

        # Mock Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.public_token = "public-sandbox-token-456"

        mock_client = mocker.MagicMock()
        mock_client.sandbox_public_token_create.return_value = mock_response

        mocker.patch(
            "budget_me.plaid.sandbox.get_plaid_client",
            return_value=mock_client,
        )

        # Create sandbox item with custom user credentials
        institution_id = "ins_109508"
        products = ["transactions"]
        options = {
            "override_username": "user_good",
            "override_password": "pass_good",
        }

        public_token = create_sandbox_item(institution_id, products, options=options)

        # Verify token returned
        assert public_token == "public-sandbox-token-456"
