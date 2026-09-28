"""Tests for Plaid Link flow module."""

import pytest
from plaid.model.products import Products


class TestLinkTokenCreation:
    """Tests for link token creation."""

    def test_create_link_token_returns_token(self, monkeypatch, mocker):
        """create_link_token returns a link_token string."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_link_token

        get_settings.cache_clear()

        # Mock the Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-test-token"

        # Mock the client's link_token_create method
        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client",
            return_value=mocker.MagicMock(
                link_token_create=mocker.MagicMock(return_value=mock_response)
            ),
        )

        link_token = create_link_token(user_id="test-user-123")

        assert link_token == "link-sandbox-test-token"

    def test_create_link_token_requests_transactions(self, monkeypatch, mocker):
        """create_link_token requests transactions product."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_link_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-test-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_link_token(user_id="test-user-123")

        # Verify the request was made with transactions product
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        # Check that products includes transactions
        assert Products("transactions") in request.products

    def test_create_link_token_includes_liabilities(self, monkeypatch, mocker):
        """create_link_token includes liabilities in additional_consented_products."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_link_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-test-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_link_token(user_id="test-user-123")

        # Verify the request was made with additional_consented_products
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        # Check that additional_consented_products includes liabilities
        assert hasattr(request, "additional_consented_products")
        assert request.additional_consented_products is not None
        assert Products("liabilities") in request.additional_consented_products

    def test_create_link_token_sets_history_days(self, monkeypatch, mocker):
        """create_link_token requests 90 days of transaction history."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import create_link_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.link_token = "link-sandbox-test-token"

        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(return_value=mock_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        create_link_token(user_id="test-user-123")

        # Verify the request was made with 90 days history
        call_args = mock_client.link_token_create.call_args
        request = call_args[0][0]

        # Check that transactions has days_requested = 90
        assert request.transactions is not None
        assert request.transactions.days_requested == 90

    def test_create_link_token_handles_error(self, monkeypatch, mocker):
        """create_link_token raises PlaidError on API failure."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "invalid-client-id")
        monkeypatch.setenv("PLAID_SECRET", "invalid-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from plaid.api_client import ApiException

        from budget_me.config import get_settings
        from budget_me.plaid.errors import PlaidError
        from budget_me.plaid.link_flow import create_link_token

        get_settings.cache_clear()

        # Mock the client to raise an ApiException
        mock_client = mocker.MagicMock()
        mock_client.link_token_create = mocker.MagicMock(
            side_effect=ApiException(status=400, reason="Invalid credentials")
        )

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        # Should raise our PlaidError wrapper
        with pytest.raises(PlaidError) as exc_info:
            create_link_token(user_id="test-user-123")

        assert "Invalid credentials" in str(exc_info.value) or "400" in str(
            exc_info.value
        )


class TestTokenExchange:
    """Tests for public token exchange and item storage."""

    @pytest.mark.asyncio
    async def test_exchange_token_returns_item_ids(self, monkeypatch, mocker):
        """exchange_public_token returns item_id (db UUID) and plaid_item_id."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv(
            "APP_TOKEN_ENC_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        )
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        # Mock the Plaid API response
        mock_response = mocker.MagicMock()
        mock_response.access_token = "access-sandbox-test-token"
        mock_response.item_id = "test-item-id"

        # Mock item_get response
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Test Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        # Mock accounts response (empty accounts for simplicity)
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        # Mock the database session and repos
        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=None)
        mock_items_repo.create = mocker.AsyncMock(
            return_value=mocker.MagicMock(id="item-uuid")
        )

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.create = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock get_async_session to return our mock session
        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        # Mock ItemsRepo to return our mock repo
        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.CursorsRepo", return_value=mock_cursors_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        result = await exchange_public_token("public-sandbox-test-token", "user-123")

        # access_token is NOT returned for security - only IDs
        assert result["item_id"] == "item-uuid"
        assert result["plaid_item_id"] == "test-item-id"

    @pytest.mark.asyncio
    async def test_exchange_token_stores_encrypted(self, monkeypatch, mocker):
        """exchange_public_token creates PlaidItem with encrypted access_token."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv(
            "APP_TOKEN_ENC_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        )
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.access_token = "access-sandbox-test-token"
        mock_response.item_id = "test-item-id"

        # Mock item_get response
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Test Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        # Mock accounts response (empty accounts for simplicity)
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=None)

        # Capture the kwargs passed to create
        captured_kwargs = {}

        async def capture_create(**kwargs):
            nonlocal captured_kwargs
            captured_kwargs = kwargs
            return mocker.MagicMock(id="item-uuid")

        mock_items_repo.create = mocker.AsyncMock(side_effect=capture_create)

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.create = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.CursorsRepo", return_value=mock_cursors_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        await exchange_public_token("public-sandbox-test-token", "user-123")

        # Verify that create was called with kwargs
        mock_items_repo.create.assert_called_once()

        # Verify the access_token_enc is encrypted (not plaintext)
        assert "access_token_enc" in captured_kwargs
        assert captured_kwargs["access_token_enc"] != "access-sandbox-test-token"
        assert len(captured_kwargs["access_token_enc"]) > 0

    @pytest.mark.asyncio
    async def test_exchange_token_creates_cursor(self, monkeypatch, mocker):
        """exchange_public_token creates PlaidCursor with null cursor."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv(
            "APP_TOKEN_ENC_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        )
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.access_token = "access-sandbox-test-token"
        mock_response.item_id = "test-item-id"

        # Mock item_get response
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Test Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        # Mock accounts response (empty accounts for simplicity)
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=None)
        mock_items_repo.create = mocker.AsyncMock(
            return_value=mocker.MagicMock(id="item-uuid")
        )

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.create = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.CursorsRepo", return_value=mock_cursors_repo
        )

        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        await exchange_public_token("public-sandbox-test-token", "user-123")

        # Verify cursor was created with kwargs
        mock_cursors_repo.create.assert_called_once()
        # Check kwargs - create() now receives kwargs, not a model instance
        call_kwargs = mock_cursors_repo.create.call_args[1]
        assert call_kwargs["plaid_item_id"] == "item-uuid"
        assert call_kwargs["transactions_cursor"] is None

    @pytest.mark.asyncio
    async def test_exchange_token_idempotent(self, monkeypatch, mocker):
        """exchange_public_token updates existing item, doesn't duplicate."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv(
            "APP_TOKEN_ENC_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        )
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        mock_response = mocker.MagicMock()
        mock_response.access_token = "access-sandbox-test-token"
        mock_response.item_id = "test-item-id"

        # Mock item_get response
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Test Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        # Mock accounts response (empty accounts for simplicity)
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        # Mock existing item
        existing_item = mocker.MagicMock()
        existing_item.id = "existing-uuid"
        existing_item.item_id = "test-item-id"

        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=existing_item)
        mock_items_repo.update = mocker.AsyncMock(return_value=existing_item)

        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        await exchange_public_token("public-sandbox-test-token", "user-123")

        # Verify update was called, not create
        mock_items_repo.update.assert_called_once()
        mock_items_repo.create.assert_not_called()

    @pytest.mark.asyncio
    async def test_exchange_token_fetches_accounts(self, monkeypatch, mocker):
        """exchange_public_token fetches and stores accounts after token exchange."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv(
            "APP_TOKEN_ENC_KEY", "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA="
        )
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        # Mock Plaid responses
        mock_exchange_response = mocker.MagicMock()
        mock_exchange_response.access_token = "access-sandbox-test-token"
        mock_exchange_response.item_id = "test-item-id"

        # Mock item_get response
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Test Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        # Mock accounts response with proper structure
        mock_account = mocker.MagicMock()
        mock_account.account_id = "acct_123"
        mock_account.name = "Checking"
        mock_account.type = "depository"
        mock_account.subtype = "checking"
        mock_account.mask = "1234"
        mock_balances = mocker.MagicMock()
        mock_balances.available = 100.50
        mock_balances.current = 110.25
        mock_account.balances = mock_balances

        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = [mock_account]

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_exchange_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        # Mock database session and repos
        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=None)
        mock_items_repo.create = mocker.AsyncMock(
            return_value=mocker.MagicMock(id="item-uuid")
        )

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.create = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )
        mocker.patch(
            "budget_me.plaid.link_flow.CursorsRepo", return_value=mock_cursors_repo
        )
        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        await exchange_public_token("public-sandbox-test-token", "user-123")

        # Verify accounts_get was called with correct access token
        mock_client.accounts_get.assert_called_once()
        call_args = mock_client.accounts_get.call_args[0][0]
        assert call_args.access_token == "access-sandbox-test-token"

        # Verify AccountsRepo.bulk_upsert was called
        mock_accounts_repo.bulk_upsert.assert_called_once()
        call_args = mock_accounts_repo.bulk_upsert.call_args
        assert call_args[0][0] == "item-uuid"  # plaid_item_id
        accounts_data = call_args[0][1]
        assert len(accounts_data) == 1
        assert accounts_data[0]["account_id"] == "acct_123"
        assert accounts_data[0]["name"] == "Checking"
        assert accounts_data[0]["balance_available"] == 100.50

    async def test_exchange_token_captures_institution_id(self, mocker, monkeypatch):
        """Token exchange should fetch and store institution_id via /item/get."""
        # Set environment variables
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.link_flow import exchange_public_token

        get_settings.cache_clear()

        # Mock settings
        mocker.patch(
            "budget_me.plaid.link_flow.get_settings",
            return_value=mocker.MagicMock(app_token_enc_key="test-key"),
        )

        # Mock token encryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.encrypt = mocker.MagicMock(return_value="encrypted-token")
        mocker.patch(
            "budget_me.plaid.link_flow.TokenEncryption", return_value=mock_encryptor
        )

        # Mock Plaid token exchange response
        mock_exchange_response = mocker.MagicMock()
        mock_exchange_response.access_token = "access-sandbox-test-token"
        mock_exchange_response.item_id = "item-sandbox-123"

        # Mock Plaid item/get response (returns institution_id)
        mock_item = mocker.MagicMock()
        mock_item.institution_id = "ins_test"
        mock_item_get_response = mocker.MagicMock()
        mock_item_get_response.item = mock_item

        # Mock Plaid accounts response
        mock_account = mocker.MagicMock()
        mock_account.account_id = "acct_123"
        mock_account.name = "Checking"
        mock_account.type = "depository"
        mock_account.subtype = "checking"
        mock_account.mask = "1234"
        mock_balances = mocker.MagicMock()
        mock_balances.available = 100.50
        mock_balances.current = 110.25
        mock_account.balances = mock_balances

        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = [mock_account]

        # Mock institution response
        mock_institution = mocker.MagicMock()
        mock_institution.name = "Example Bank"
        mock_institution_response = mocker.MagicMock()
        mock_institution_response.institution = mock_institution

        mock_client = mocker.MagicMock()
        mock_client.item_public_token_exchange = mocker.MagicMock(
            return_value=mock_exchange_response
        )
        mock_client.item_get = mocker.MagicMock(return_value=mock_item_get_response)
        mock_client.institutions_get_by_id = mocker.MagicMock(
            return_value=mock_institution_response
        )
        mock_client.accounts_get = mocker.MagicMock(return_value=mock_accounts_response)

        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client", return_value=mock_client
        )

        # Mock database session and repos
        mock_session = mocker.AsyncMock()
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.find_by_item_id = mocker.AsyncMock(return_value=None)
        mock_items_repo.create = mocker.AsyncMock(
            return_value=mocker.MagicMock(id="item-uuid")
        )

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.create = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session)
            ),
        )

        mocker.patch(
            "budget_me.plaid.link_flow.ItemsRepo", return_value=mock_items_repo
        )
        mocker.patch(
            "budget_me.plaid.link_flow.CursorsRepo", return_value=mock_cursors_repo
        )
        mocker.patch(
            "budget_me.plaid.link_flow.AccountsRepo", return_value=mock_accounts_repo
        )

        await exchange_public_token("public-sandbox-test-token", "user-123")

        # Verify item_get was called to fetch institution_id
        mock_client.item_get.assert_called_once()

        # Verify institutions_get_by_id was called to fetch institution name
        mock_client.institutions_get_by_id.assert_called_once()

        # Verify items_repo.create was called WITH institution_id and institution_name
        mock_items_repo.create.assert_called_once()
        create_call_kwargs = mock_items_repo.create.call_args[1]
        assert "institution_id" in create_call_kwargs, (
            "institution_id should be passed to items_repo.create"
        )
        assert create_call_kwargs["institution_id"] == "ins_test", (
            "institution_id should be set to the value from Plaid item/get response"
        )
        assert "institution_name" in create_call_kwargs, (
            "institution_name should be passed to items_repo.create"
        )
        assert create_call_kwargs["institution_name"] == "Example Bank", (
            "institution_name should be set to the value from Plaid institutions/get_by_id response"
        )
