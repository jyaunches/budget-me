"""Tests for transaction sync engine."""

from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

import pytest

from budget_me.db.models.plaid_item import PlaidItemStatus


class TestTransactionSync:
    """Tests for the transaction sync engine."""

    @pytest.fixture(autouse=True)
    def mock_database_session(self, mocker):
        """Keep sync tests independent of local database configuration."""
        session = mocker.AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield session

        @asynccontextmanager
        async def fake_coordination():
            yield

        mocker.patch(
            "budget_me.plaid.transactions_sync.get_async_session", fake_session
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.hold_sync_item_coordination",
            fake_coordination,
        )

    @pytest.mark.asyncio
    async def test_public_sync_holds_coordination_around_full_item_work(self, mocker):
        """Direct callers cannot bypass the close/sync admission barrier."""
        from budget_me.plaid.transactions_sync import ItemSyncResult, sync_item

        events = []

        @asynccontextmanager
        async def tracked_coordination():
            events.append("lock-acquired")
            try:
                yield
            finally:
                events.append("lock-released")

        async def item_work(*args, **kwargs):
            events.append("item-work")
            return ItemSyncResult(added=1, modified=2, removed=3)

        mocker.patch(
            "budget_me.plaid.transactions_sync.hold_sync_item_coordination",
            tracked_coordination,
        )
        delegate = mocker.patch(
            "budget_me.plaid.transactions_sync._sync_item_under_coordination",
            mocker.AsyncMock(side_effect=item_work),
        )

        item_id = uuid4()
        result = await sync_item(item_id, include_transactions=True)

        assert events == ["lock-acquired", "item-work", "lock-released"]
        assert result == ItemSyncResult(added=1, modified=2, removed=3)
        delegate.assert_awaited_once_with(item_id, include_transactions=True)

    @pytest.mark.asyncio
    async def test_sync_initial_fetches_all_pages(self, monkeypatch, mocker):
        """Sync with no cursor (initial sync) loops until has_more=false."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        # Mock the repos and client to simulate pagination
        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"
        mock_item.status = PlaidItemStatus.ACTIVE

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = None  # Initial sync

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock Plaid API responses - two pages
        response_page1 = mocker.MagicMock()
        response_page1.added = []
        response_page1.modified = []
        response_page1.removed = []
        response_page1.has_more = True
        response_page1.next_cursor = "cursor_page2"

        response_page2 = mocker.MagicMock()
        response_page2.added = []
        response_page2.modified = []
        response_page2.removed = []
        response_page2.has_more = False
        response_page2.next_cursor = "cursor_final"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.side_effect = [response_page1, response_page2]

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        # Mock the repository methods
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        mock_transactions_repo.bulk_upsert = mocker.AsyncMock(return_value=(0, 0))
        mock_transactions_repo.delete_by_plaid_ids = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock repository constructors
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        # Run sync
        await sync_item(item_id)

        # Verify transactions_sync was called twice
        assert mock_client.transactions_sync.call_count == 2

    @pytest.mark.asyncio
    async def test_sync_adds_new_transactions(self, monkeypatch, mocker):
        """Sync response with added transactions inserts them in DB."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        # Mock item and cursor
        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"
        mock_item.status = PlaidItemStatus.ACTIVE

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "existing_cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock transaction
        mock_transaction = mocker.MagicMock()
        mock_transaction.transaction_id = "txn_1"
        mock_transaction.account_id = "acc_1"
        mock_transaction.amount = 100.50
        mock_transaction.date = date.today().isoformat()
        mock_transaction.name = "Test Transaction"
        mock_transaction.category = ["Food", "Restaurants"]
        mock_transaction.to_dict.return_value = {"transaction_id": "txn_1"}

        # Mock Plaid API response with added transactions
        mock_response = mocker.MagicMock()
        mock_response.added = [mock_transaction]
        mock_response.modified = []
        mock_response.removed = []
        mock_response.has_more = False
        mock_response.next_cursor = "new_cursor"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        # Mock repositories
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        mock_transactions_repo.bulk_upsert = mocker.AsyncMock(return_value=(1, 0))

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        # Run sync
        result = await sync_item(item_id)

        # Verify bulk_upsert was called with added transactions
        mock_transactions_repo.bulk_upsert.assert_called()
        assert result.added == 1

    @pytest.mark.asyncio
    async def test_sync_updates_modified_transactions(self, monkeypatch, mocker):
        """Sync response with modified transactions updates them in DB."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "existing_cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock modified transaction
        mock_transaction = mocker.MagicMock()
        mock_transaction.transaction_id = "txn_1"
        mock_transaction.account_id = "acc_1"
        mock_transaction.amount = 100.50
        mock_transaction.date = date.today().isoformat()
        mock_transaction.name = "Test Transaction"
        mock_transaction.category = ["Food"]
        mock_transaction.to_dict.return_value = {"transaction_id": "txn_1"}

        mock_response = mocker.MagicMock()
        mock_response.added = []
        mock_response.modified = [mock_transaction]
        mock_response.removed = []
        mock_response.has_more = False
        mock_response.next_cursor = "new_cursor"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        mock_transactions_repo.bulk_upsert = mocker.AsyncMock(return_value=(0, 1))

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        result = await sync_item(item_id)

        # Verify bulk_upsert was called with modified transactions
        mock_transactions_repo.bulk_upsert.assert_called()
        assert result.modified == 1

    @pytest.mark.asyncio
    async def test_sync_removes_deleted_transactions(self, monkeypatch, mocker):
        """Sync response with removed transaction IDs deletes them from DB."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "existing_cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock removed transaction
        mock_removed = mocker.MagicMock()
        mock_removed.transaction_id = "txn_deleted"

        mock_response = mocker.MagicMock()
        mock_response.added = []
        mock_response.modified = []
        mock_response.removed = [mock_removed]
        mock_response.has_more = False
        mock_response.next_cursor = "new_cursor"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        mock_transactions_repo.delete_by_plaid_ids = mocker.AsyncMock(return_value=1)

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        result = await sync_item(item_id)

        # Verify delete_by_plaid_ids was called with removed transaction IDs
        mock_transactions_repo.delete_by_plaid_ids.assert_called_once()
        assert result.removed == 1

    @pytest.mark.asyncio
    async def test_sync_saves_cursor(self, monkeypatch, mocker):
        """Successful sync updates PlaidCursor with next_cursor."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "old_cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        mock_response = mocker.MagicMock()
        mock_response.added = []
        mock_response.modified = []
        mock_response.removed = []
        mock_response.has_more = False
        mock_response.next_cursor = "new_cursor_value"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        await sync_item(item_id)

        # Verify cursor was updated
        mock_cursors_repo.update_cursor.assert_called_once_with(
            item_id, "new_cursor_value"
        )

    @pytest.mark.asyncio
    async def test_sync_returns_counts(self, monkeypatch, mocker):
        """Sync returns counts of added, modified, removed transactions."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock response with various transaction types
        def make_mock_txn(txn_id):
            txn = mocker.MagicMock()
            txn.transaction_id = txn_id
            txn.account_id = "acc_1"
            txn.amount = 50.0
            txn.date = date.today().isoformat()
            txn.name = "Transaction"
            txn.category = ["Shopping"]
            txn.to_dict.return_value = {"transaction_id": txn_id}
            return txn

        mock_added = [make_mock_txn("txn_1"), make_mock_txn("txn_2")]
        mock_modified = [make_mock_txn("txn_3")]

        mock_removed = []
        for i in range(3):
            removed = mocker.MagicMock()
            removed.transaction_id = f"txn_removed_{i}"
            mock_removed.append(removed)

        mock_response = mocker.MagicMock()
        mock_response.added = mock_added
        mock_response.modified = mock_modified
        mock_response.removed = mock_removed
        mock_response.has_more = False
        mock_response.next_cursor = "new_cursor"

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        # First call for added (2 new), second call for modified (0 new, 1 modified)
        mock_transactions_repo.bulk_upsert = mocker.AsyncMock(
            side_effect=[(2, 0), (0, 1)]
        )
        mock_transactions_repo.delete_by_plaid_ids = mocker.AsyncMock(return_value=3)

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        # Mock Plaid accounts_get response
        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = []
        mock_client.accounts_get.return_value = mock_accounts_response

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )

        result = await sync_item(item_id)

        # Verify counts
        assert result.added == 2
        assert result.modified == 1
        assert result.removed == 3

    @pytest.mark.asyncio
    async def test_error_item_login_required_sets_status(self, monkeypatch, mocker):
        """ITEM_LOGIN_REQUIRED error during sync marks item as relink_required."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.errors import PlaidItemError
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"
        mock_item.status = PlaidItemStatus.ACTIVE

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock Plaid API to raise ITEM_LOGIN_REQUIRED error
        from plaid.api_client import ApiException

        api_ex = ApiException(status=400, reason="Item login required")
        api_ex.body = '{"error_code": "ITEM_LOGIN_REQUIRED"}'

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.side_effect = api_ex

        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get_by_id.return_value = mock_item
        mock_items_repo.update = mocker.AsyncMock()

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor

        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )

        # Expect PlaidItemError to be raised
        with pytest.raises(PlaidItemError):
            await sync_item(item_id)

        # Verify item status was updated to relink_required
        assert mock_item.status == PlaidItemStatus.RELINK_REQUIRED
        mock_items_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_error_invalid_credentials_raises(self, monkeypatch, mocker):
        """Invalid API credentials raises PlaidAuthError."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "invalid-client-id")
        monkeypatch.setenv("PLAID_SECRET", "invalid-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.errors import PlaidAuthError
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "cursor"

        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock Plaid API to raise INVALID_API_KEYS error
        from plaid.api_client import ApiException

        api_ex = ApiException(status=401, reason="Invalid credentials")
        api_ex.body = '{"error_code": "INVALID_API_KEYS"}'

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.side_effect = api_ex

        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor

        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )

        # Expect PlaidAuthError to be raised
        with pytest.raises(PlaidAuthError):
            await sync_item(item_id)

    @pytest.mark.asyncio
    async def test_error_institution_down_logs(self, monkeypatch, mocker):
        """INSTITUTION_NOT_RESPONDING error logs and marks item as error status."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.errors import PlaidInstitutionError
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"
        mock_item.status = PlaidItemStatus.ACTIVE

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "cursor"

        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock Plaid API to raise INSTITUTION_NOT_RESPONDING error
        from plaid.api_client import ApiException

        api_ex = ApiException(status=400, reason="Institution down")
        api_ex.body = '{"error_code": "INSTITUTION_NOT_RESPONDING"}'

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.side_effect = api_ex

        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get_by_id.return_value = mock_item
        mock_items_repo.update = mocker.AsyncMock()

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor

        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )

        # Expect PlaidInstitutionError to be raised
        with pytest.raises(PlaidInstitutionError):
            await sync_item(item_id)

        # Verify item error details were recorded
        assert mock_item.last_error_code == "INSTITUTION_NOT_RESPONDING"
        assert mock_item.last_error_at is not None
        assert mock_item.last_error_message is not None
        mock_items_repo.update.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_item_refreshes_accounts(self, monkeypatch, mocker):
        """sync_item refreshes account data after processing transactions."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import get_settings
        from budget_me.plaid.transactions_sync import sync_item

        get_settings.cache_clear()

        item_id = uuid4()

        # Mock PlaidItem
        mock_item = mocker.MagicMock()
        mock_item.id = item_id
        mock_item.access_token_enc = "encrypted_token"
        mock_item.status = PlaidItemStatus.ACTIVE

        mock_cursor = mocker.MagicMock()
        mock_cursor.transactions_cursor = "cursor"

        # Mock TokenEncryption
        mock_encryptor = mocker.MagicMock()
        mock_encryptor.decrypt.return_value = "access_token"
        mocker.patch(
            "budget_me.plaid.transactions_sync.TokenEncryption",
            return_value=mock_encryptor,
        )

        # Mock Plaid transactions_sync response
        mock_txn_response = mocker.MagicMock()
        mock_txn_response.added = []
        mock_txn_response.modified = []
        mock_txn_response.removed = []
        mock_txn_response.has_more = False
        mock_txn_response.next_cursor = "cursor_xyz"

        # Mock Plaid accounts_get response
        mock_account = mocker.MagicMock()
        mock_account.account_id = "acct_1"
        mock_account.name = "Checking"
        mock_account.type = "depository"
        mock_account.subtype = "checking"
        mock_account.mask = "1234"
        mock_account.balances.available = 250.00
        mock_account.balances.current = 275.00

        mock_accounts_response = mocker.MagicMock()
        mock_accounts_response.accounts = [mock_account]

        mock_client = mocker.MagicMock()
        mock_client.transactions_sync.return_value = mock_txn_response
        mock_client.accounts_get.return_value = mock_accounts_response

        mocker.patch(
            "budget_me.plaid.transactions_sync.get_plaid_client",
            return_value=mock_client,
        )

        # Mock repositories
        mock_items_repo = mocker.AsyncMock()
        mock_items_repo.get.return_value = mock_item

        mock_cursors_repo = mocker.AsyncMock()
        mock_cursors_repo.find_by_item_id.return_value = mock_cursor
        mock_cursors_repo.update_cursor = mocker.AsyncMock()

        mock_transactions_repo = mocker.AsyncMock()
        mock_transactions_repo.bulk_upsert = mocker.AsyncMock(return_value=(0, 0))

        mock_accounts_repo = mocker.AsyncMock()
        mock_accounts_repo.bulk_upsert = mocker.AsyncMock()

        mock_balance_snapshot_repo = mocker.AsyncMock()
        mock_balance_snapshot_repo.upsert = mocker.AsyncMock()

        mocker.patch(
            "budget_me.plaid.transactions_sync.ItemsRepo",
            return_value=mock_items_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.CursorsRepo",
            return_value=mock_cursors_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.TransactionsRepo",
            return_value=mock_transactions_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountsRepo",
            return_value=mock_accounts_repo,
        )
        mocker.patch(
            "budget_me.plaid.transactions_sync.AccountBalanceSnapshotRepo",
            return_value=mock_balance_snapshot_repo,
        )

        await sync_item(item_id)

        # Verify accounts_get was called
        mock_client.accounts_get.assert_called_once()

        # Verify AccountsRepo.bulk_upsert was called with correct data
        mock_accounts_repo.bulk_upsert.assert_called_once()
        call_args = mock_accounts_repo.bulk_upsert.call_args
        assert call_args[0][0] == item_id  # plaid_item_id
        accounts_data = call_args[0][1]
        assert len(accounts_data) == 1
        assert accounts_data[0]["account_id"] == "acct_1"
        assert accounts_data[0]["name"] == "Checking"
        assert accounts_data[0]["balance_current"] == 275.00

    def test_items_repo_update_signature_matches_base_repository(self):
        """Verify BaseRepository.update signature takes instance only.

        This test documents the expected signature for items_repo.update()
        to prevent regression of the bug where update(item_id, item) was
        called instead of update(item).

        BaseRepository.update signature: update(self, instance, **kwargs)
        Correct call: items_repo.update(item)
        Wrong call: items_repo.update(item_id, item) - causes TypeError
        """
        import inspect

        from budget_me.db.repos.base import BaseRepository

        # Get the update method signature
        sig = inspect.signature(BaseRepository.update)
        params = list(sig.parameters.keys())

        # Should have: self, instance, **kwargs
        assert params[0] == "self", "First param should be self"
        assert params[1] == "instance", "Second param should be instance"

        # The instance parameter should not have a default
        instance_param = sig.parameters["instance"]
        assert instance_param.default is inspect.Parameter.empty, (
            "instance should be a required positional parameter"
        )
