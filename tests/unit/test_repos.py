"""Tests for repository layer.

These tests verify the repository classes are properly structured.
Integration tests with a real database would be in tests/integration/.
"""

from unittest.mock import MagicMock

from budget_me.db.models.account import Account
from budget_me.db.models.ingest_run import (
    IngestRun,
)
from budget_me.db.models.merchant import MerchantRule
from budget_me.db.models.plaid_item import PlaidItem
from budget_me.db.models.transaction import Transaction
from budget_me.db.repos import (
    AccountsRepo,
    IngestRunsRepo,
    ItemsRepo,
    MerchantsRepo,
    TransactionsRepo,
)


class TestBaseRepository:
    """Tests for BaseRepository."""

    def test_base_repository_has_model_attribute(self):
        """BaseRepository subclasses define model attribute."""
        assert hasattr(ItemsRepo, "model")
        assert ItemsRepo.model == PlaidItem

        assert hasattr(AccountsRepo, "model")
        assert AccountsRepo.model == Account

        assert hasattr(TransactionsRepo, "model")
        assert TransactionsRepo.model == Transaction

        assert hasattr(MerchantsRepo, "model")
        assert MerchantsRepo.model == MerchantRule

        assert hasattr(IngestRunsRepo, "model")
        assert IngestRunsRepo.model == IngestRun

    def test_base_repository_requires_session(self):
        """BaseRepository requires a session on init."""
        mock_session = MagicMock()
        repo = ItemsRepo(mock_session)
        assert repo.session is mock_session


class TestItemsRepo:
    """Tests for ItemsRepo."""

    def test_items_repo_has_required_methods(self):
        """ItemsRepo has all required methods."""
        mock_session = MagicMock()
        repo = ItemsRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")
        assert hasattr(repo, "delete")

        # Custom methods
        assert hasattr(repo, "find_by_item_id")
        assert hasattr(repo, "find_by_user_key")
        assert hasattr(repo, "find_active")
        assert hasattr(repo, "update_status")
        assert hasattr(repo, "record_success")
        assert hasattr(repo, "record_error")

    def test_items_repo_methods_are_async(self):
        """ItemsRepo methods are async."""
        import inspect

        mock_session = MagicMock()
        repo = ItemsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.find_by_item_id)
        assert inspect.iscoroutinefunction(repo.find_by_user_key)
        assert inspect.iscoroutinefunction(repo.find_active)
        assert inspect.iscoroutinefunction(repo.update_status)
        assert inspect.iscoroutinefunction(repo.record_success)
        assert inspect.iscoroutinefunction(repo.record_error)


class TestTransactionsRepo:
    """Tests for TransactionsRepo."""

    def test_transactions_repo_has_required_methods(self):
        """TransactionsRepo has all required methods."""
        mock_session = MagicMock()
        repo = TransactionsRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")
        assert hasattr(repo, "delete")

        # Custom methods
        assert hasattr(repo, "find_by_plaid_transaction_id")
        assert hasattr(repo, "find_by_date_range")
        assert hasattr(repo, "find_by_plaid_item")
        assert hasattr(repo, "upsert")
        assert hasattr(repo, "bulk_upsert")
        assert hasattr(repo, "delete_by_plaid_id")
        assert hasattr(repo, "delete_by_plaid_ids")

        # Project tag methods
        assert hasattr(repo, "set_project_tag")
        assert hasattr(repo, "get_project_summary")

        # Card-side payment reconciliation
        assert hasattr(repo, "get_card_payments")

    def test_transactions_repo_methods_are_async(self):
        """TransactionsRepo methods are async."""
        import inspect

        mock_session = MagicMock()
        repo = TransactionsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.find_by_plaid_transaction_id)
        assert inspect.iscoroutinefunction(repo.find_by_date_range)
        assert inspect.iscoroutinefunction(repo.find_by_plaid_item)
        assert inspect.iscoroutinefunction(repo.upsert)
        assert inspect.iscoroutinefunction(repo.bulk_upsert)
        assert inspect.iscoroutinefunction(repo.delete_by_plaid_id)
        assert inspect.iscoroutinefunction(repo.delete_by_plaid_ids)
        assert inspect.iscoroutinefunction(repo.set_project_tag)
        assert inspect.iscoroutinefunction(repo.get_project_summary)
        assert inspect.iscoroutinefunction(repo.get_card_payments)

    async def test_set_project_tag_noop_for_empty_ids(self):
        """set_project_tag returns 0 and does not touch the DB for empty ids."""
        mock_session = MagicMock()
        repo = TransactionsRepo(mock_session)

        result = await repo.set_project_tag([], "example_project_2027")

        assert result == 0
        mock_session.execute.assert_not_called()


class TestMerchantsRepo:
    """Tests for MerchantsRepo."""

    def test_merchants_repo_has_required_methods(self):
        """MerchantsRepo has all required methods."""
        mock_session = MagicMock()
        repo = MerchantsRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")
        assert hasattr(repo, "delete")

        # Custom methods
        assert hasattr(repo, "get_active_rules")
        assert hasattr(repo, "get_mapped_name")
        assert hasattr(repo, "set_mapped_name")
        assert hasattr(repo, "get_all_mappings")
        assert hasattr(repo, "delete_mapping")

    def test_merchants_repo_methods_are_async(self):
        """MerchantsRepo methods are async."""
        import inspect

        mock_session = MagicMock()
        repo = MerchantsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.get_active_rules)
        assert inspect.iscoroutinefunction(repo.get_mapped_name)
        assert inspect.iscoroutinefunction(repo.set_mapped_name)
        assert inspect.iscoroutinefunction(repo.get_all_mappings)
        assert inspect.iscoroutinefunction(repo.delete_mapping)


class TestAccountsRepo:
    """Tests for AccountsRepo."""

    def test_accounts_repo_has_required_methods(self):
        """AccountsRepo has all required methods."""
        mock_session = MagicMock()
        repo = AccountsRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")
        assert hasattr(repo, "delete")

        # Custom methods
        assert hasattr(repo, "find_by_item_id")
        assert hasattr(repo, "find_by_account_id")
        assert hasattr(repo, "bulk_upsert")

    def test_accounts_repo_methods_are_async(self):
        """AccountsRepo methods are async."""
        import inspect

        mock_session = MagicMock()
        repo = AccountsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.find_by_item_id)
        assert inspect.iscoroutinefunction(repo.find_by_account_id)
        assert inspect.iscoroutinefunction(repo.bulk_upsert)


class TestAccountsRepoBulkUpsertBehavior:
    """Tests for AccountsRepo bulk_upsert display_name preservation."""

    def test_bulk_upsert_does_not_update_display_name_field(self):
        """bulk_upsert updates Plaid fields but not display_name.

        Verifies that the bulk_upsert method only updates specific Plaid fields
        (name, type, subtype, mask, balance_available, balance_current) and does
        not modify display_name, which is user-editable and must persist.
        """
        import inspect

        from budget_me.db.repos.accounts_repo import AccountsRepo

        source = inspect.getsource(AccountsRepo.bulk_upsert)

        # Verify display_name is NOT assigned in the update block
        # The code should update: name, type, subtype, mask, balance_available, balance_current
        # But NOT display_name
        assert "acc.name = acc_data" in source
        assert "acc.type = acc_data" in source
        assert "acc.subtype = acc_data" in source
        assert "acc.mask = acc_data" in source
        assert "acc.balance_available = acc_data" in source
        assert "acc.balance_current = acc_data" in source

        # Verify display_name is never assigned from acc_data
        assert "acc.display_name = acc_data" not in source

    def test_bulk_upsert_has_display_name_preservation_comment(self):
        """bulk_upsert includes comment about preserving display_name."""
        import inspect

        from budget_me.db.repos.accounts_repo import AccountsRepo

        source = inspect.getsource(AccountsRepo.bulk_upsert)

        # Verify the code documents the display_name preservation behavior
        assert "display_name" in source.lower()
        assert "preserve" in source.lower() or "not be overwritten" in source.lower()


class TestIngestRunsRepo:
    """Tests for IngestRunsRepo."""

    def test_ingest_runs_repo_has_required_methods(self):
        """IngestRunsRepo has all required methods."""
        mock_session = MagicMock()
        repo = IngestRunsRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")
        assert hasattr(repo, "delete")

        # Custom methods
        assert hasattr(repo, "create_run")
        assert hasattr(repo, "complete_run")
        assert hasattr(repo, "add_run_item")
        assert hasattr(repo, "complete_run_item")
        assert hasattr(repo, "get_run_items")
        assert hasattr(repo, "get_recent_runs")
        assert hasattr(repo, "get_running")

    def test_ingest_runs_repo_methods_are_async(self):
        """IngestRunsRepo methods are async."""
        import inspect

        mock_session = MagicMock()
        repo = IngestRunsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.create_run)
        assert inspect.iscoroutinefunction(repo.complete_run)
        assert inspect.iscoroutinefunction(repo.add_run_item)
        assert inspect.iscoroutinefunction(repo.complete_run_item)
        assert inspect.iscoroutinefunction(repo.get_run_items)
        assert inspect.iscoroutinefunction(repo.get_recent_runs)
        assert inspect.iscoroutinefunction(repo.get_running)


class TestLiabilitiesRepo:
    """Tests for LiabilitiesRepo."""

    def test_liabilities_repo_has_required_methods(self):
        """LiabilitiesRepo has all required methods."""
        from budget_me.db.repos import LiabilitiesRepo

        mock_session = MagicMock()
        repo = LiabilitiesRepo(mock_session)

        # Base methods
        assert hasattr(repo, "get_by_id")
        assert hasattr(repo, "create")
        assert hasattr(repo, "update")

        # Custom methods
        assert hasattr(repo, "find_by_item_id")
        assert hasattr(repo, "find_by_account_id")
        assert hasattr(repo, "upsert_liability")
        assert hasattr(repo, "upsert_aprs")

    def test_liabilities_repo_methods_are_async(self):
        """LiabilitiesRepo methods are async."""
        import inspect

        from budget_me.db.repos import LiabilitiesRepo

        mock_session = MagicMock()
        repo = LiabilitiesRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.find_by_item_id)
        assert inspect.iscoroutinefunction(repo.find_by_account_id)
        assert inspect.iscoroutinefunction(repo.upsert_liability)
        assert inspect.iscoroutinefunction(repo.upsert_aprs)


class TestItemsRepoAddProduct:
    """Tests for ItemsRepo add_product method."""

    def test_items_repo_has_add_product_method(self):
        """ItemsRepo has add_product method."""
        mock_session = MagicMock()
        repo = ItemsRepo(mock_session)

        assert hasattr(repo, "add_product")

    def test_items_repo_add_product_is_async(self):
        """ItemsRepo add_product method is async."""
        import inspect

        mock_session = MagicMock()
        repo = ItemsRepo(mock_session)

        assert inspect.iscoroutinefunction(repo.add_product)


class TestRepoImports:
    """Tests for repository module exports."""

    def test_all_repos_exported(self):
        """All repositories are exported from the repos module."""
        from budget_me.db import repos

        assert hasattr(repos, "BaseRepository")
        assert hasattr(repos, "ItemsRepo")
        assert hasattr(repos, "AccountsRepo")
        assert hasattr(repos, "TransactionsRepo")
        assert hasattr(repos, "MerchantsRepo")
        assert hasattr(repos, "IngestRunsRepo")
        assert hasattr(repos, "LiabilitiesRepo")
        assert hasattr(repos, "AnticipatedItemsRepo")
        assert hasattr(repos, "MonthlySnapshotRepo")
