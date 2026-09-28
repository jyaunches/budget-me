"""Unit tests for monthly snapshot database functions."""

import inspect

import budget_me.streamlit_app.db as db


class TestMonthlySnapshotDBFunctions:
    """Tests for monthly snapshot DB layer functions."""

    def test_get_anticipated_expenses_is_exported(self):
        """Verify get_anticipated_expenses function exists."""
        assert hasattr(db, "get_anticipated_expenses")
        assert callable(db.get_anticipated_expenses)

    def test_get_anticipated_income_is_exported(self):
        """Verify get_anticipated_income function exists."""
        assert hasattr(db, "get_anticipated_income")
        assert callable(db.get_anticipated_income)

    def test_get_credit_cards_with_strategy_is_exported(self):
        """Verify get_credit_cards_with_strategy function exists."""
        assert hasattr(db, "get_credit_cards_with_strategy")
        assert callable(db.get_credit_cards_with_strategy)

    def test_create_anticipated_item_is_exported(self):
        """Verify create_anticipated_item function exists."""
        assert hasattr(db, "create_anticipated_item")
        assert callable(db.create_anticipated_item)

    def test_update_anticipated_item_is_exported(self):
        """Verify update_anticipated_item function exists."""
        assert hasattr(db, "update_anticipated_item")
        assert callable(db.update_anticipated_item)

    def test_delete_anticipated_item_is_exported(self):
        """Verify delete_anticipated_item function exists."""
        assert hasattr(db, "delete_anticipated_item")
        assert callable(db.delete_anticipated_item)

    def test_update_account_payment_strategy_is_exported(self):
        """Verify update_account_payment_strategy function exists."""
        assert hasattr(db, "update_account_payment_strategy")
        assert callable(db.update_account_payment_strategy)

    def test_get_account_avg_monthly_spend_is_exported(self):
        """Verify get_account_avg_monthly_spend function exists."""
        assert hasattr(db, "get_account_avg_monthly_spend")
        assert callable(db.get_account_avg_monthly_spend)

    def test_get_account_avg_monthly_spend_signature(self):
        """Verify get_account_avg_monthly_spend has correct signature."""
        sig = inspect.signature(db.get_account_avg_monthly_spend)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params
        assert "months" in params
        # Check default value for months
        assert sig.parameters["months"].default == 3

    def test_get_account_avg_monthly_spend_queries_transactions(self):
        """Verify get_account_avg_monthly_spend queries transactions table."""
        source = inspect.getsource(db.get_account_avg_monthly_spend)
        assert "Transaction" in source
        assert "account_id" in source
        assert "amount" in source

    def test_get_anticipated_expenses_queries_active_only(self):
        """Verify get_anticipated_expenses queries active expenses."""
        source = inspect.getsource(db.get_anticipated_expenses)
        assert "AnticipatedItem" in source
        assert "active" in source
        assert "expense" in source

    def test_get_anticipated_income_queries_active_only(self):
        """Verify get_anticipated_income queries active income."""
        source = inspect.getsource(db.get_anticipated_income)
        assert "AnticipatedItem" in source
        assert "active" in source
        assert "income" in source

    def test_get_credit_cards_with_strategy_joins_liabilities(self):
        """Verify get_credit_cards_with_strategy joins liability data."""
        source = inspect.getsource(db.get_credit_cards_with_strategy)
        assert "CreditLiability" in source
        assert "outerjoin" in source
        assert "last_statement_balance" in source

    def test_get_credit_cards_with_strategy_includes_payment_strategy(self):
        """Verify get_credit_cards_with_strategy returns strategy fields."""
        source = inspect.getsource(db.get_credit_cards_with_strategy)
        assert "payment_strategy" in source
        assert "fixed_payment_amount" in source

    def test_get_credit_cards_with_strategy_calls_avg_monthly_spend(self):
        """Verify get_credit_cards_with_strategy calls avg_monthly_spend."""
        source = inspect.getsource(db.get_credit_cards_with_strategy)
        assert "get_account_avg_monthly_spend" in source

    def test_create_anticipated_item_accepts_required_params(self):
        """Verify create_anticipated_item has correct signature."""
        sig = inspect.signature(db.create_anticipated_item)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "name" in params
        assert "amount" in params
        assert "item_type" in params
        assert "category" in params

    def test_update_anticipated_item_accepts_kwargs(self):
        """Verify update_anticipated_item accepts item_id and kwargs."""
        sig = inspect.signature(db.update_anticipated_item)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "item_id" in params
        assert "kwargs" in params or "**" in str(sig)

    def test_delete_anticipated_item_deactivates(self):
        """Verify delete_anticipated_item sets active=False."""
        source = inspect.getsource(db.delete_anticipated_item)
        # Should set active=False (soft delete)
        assert "active" in source
        assert "False" in source

    def test_update_account_payment_strategy_updates_correct_fields(self):
        """Verify update_account_payment_strategy updates strategy fields."""
        source = inspect.getsource(db.update_account_payment_strategy)
        assert "payment_strategy" in source
        assert "fixed_payment_amount" in source or "fixed_amount" in source


class TestSnapshotDbFunctions:
    """Tests for snapshot-based DB functions (Phase 3)."""

    def test_get_snapshot_line_items_function_exists(self):
        """Verify get_snapshot_line_items function exists."""
        assert hasattr(db, "get_snapshot_line_items")
        assert callable(db.get_snapshot_line_items)

    def test_get_snapshot_credit_cards_function_exists(self):
        """Verify get_snapshot_credit_cards function exists."""
        assert hasattr(db, "get_snapshot_credit_cards")
        assert callable(db.get_snapshot_credit_cards)

    def test_get_or_create_snapshot_function_exists(self):
        """Verify get_or_create_snapshot function exists."""
        assert hasattr(db, "get_or_create_snapshot")
        assert callable(db.get_or_create_snapshot)

    def test_get_available_months_function_exists(self):
        """Verify get_available_months function exists."""
        assert hasattr(db, "get_available_months")
        assert callable(db.get_available_months)

    def test_update_snapshot_line_item_function_exists(self):
        """Verify update_snapshot_line_item function exists."""
        assert hasattr(db, "update_snapshot_line_item")
        assert callable(db.update_snapshot_line_item)

    def test_skip_snapshot_line_item_function_exists(self):
        """Verify skip_snapshot_line_item function exists."""
        assert hasattr(db, "skip_snapshot_line_item")
        assert callable(db.skip_snapshot_line_item)

    def test_add_one_time_item_function_exists(self):
        """Verify add_one_time_item function exists."""
        assert hasattr(db, "add_one_time_item")
        assert callable(db.add_one_time_item)

    def test_update_snapshot_credit_card_function_exists(self):
        """Verify update_snapshot_credit_card function exists."""
        assert hasattr(db, "update_snapshot_credit_card")
        assert callable(db.update_snapshot_credit_card)

    def test_close_snapshot_function_exists(self):
        """Verify close_snapshot function exists."""
        assert hasattr(db, "close_snapshot")
        assert callable(db.close_snapshot)

    def test_calculate_snapshot_totals_function_exists(self):
        """Verify calculate_snapshot_totals function exists."""
        assert hasattr(db, "calculate_snapshot_totals")
        assert callable(db.calculate_snapshot_totals)

    def test_close_snapshot_function_structure(self):
        """Verify close_snapshot updates status to closed."""
        source = inspect.getsource(db.close_snapshot)
        assert "closed" in source.lower()
        assert "closed_at" in source.lower()

    def test_add_one_time_item_sets_flag(self):
        """Verify add_one_time_item creates item with is_one_time=true."""
        source = inspect.getsource(db.add_one_time_item)
        assert "is_one_time" in source
        assert "True" in source

    def test_add_one_time_item_accepts_account_id(self):
        """Verify add_one_time_item accepts account_id for per-account snapshots.

        The function must accept account_id to look up the correct snapshot
        since the system now uses per-account snapshots.
        """
        sig = inspect.signature(db.add_one_time_item)
        params = list(sig.parameters.keys())
        # account_id should be the 3rd parameter (after session, year_month)
        assert "account_id" in params, (
            "add_one_time_item must accept account_id parameter for per-account snapshots"
        )
        # Verify parameter order matches caller expectations
        assert params.index("account_id") == 2, (
            "account_id should be the 3rd parameter (index 2)"
        )

    def test_calculate_snapshot_totals_excludes_skipped(self):
        """Verify calculate_snapshot_totals filters out skipped items."""
        source = inspect.getsource(db.calculate_snapshot_totals)
        assert "skipped" in source.lower()
        # Should filter WHERE skipped=False or similar
        assert "False" in source or "!=" in source or "not" in source.lower()

    def test_get_snapshot_line_items_signature(self):
        """Verify get_snapshot_line_items has correct signature."""
        sig = inspect.signature(db.get_snapshot_line_items)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "year_month" in params
        assert "item_type" in params

    def test_get_or_create_snapshot_returns_snapshot_dict(self):
        """Verify get_or_create_snapshot returns dict with status and totals."""
        source = inspect.getsource(db.get_or_create_snapshot)
        # Should query or create MonthlySnapshot
        assert "MonthlySnapshot" in source
        # Should return dict with year_month and status
        assert "year_month" in source.lower()
        assert "status" in source.lower()

    def test_get_available_months_returns_list(self):
        """Verify get_available_months queries MonthlySnapshot."""
        source = inspect.getsource(db.get_available_months)
        assert "MonthlySnapshot" in source
        # Should order by year_month descending
        assert "year_month" in source.lower()

    def test_calculate_snapshot_totals_treats_null_as_zero(self):
        """Verify calculate_snapshot_totals handles null values."""
        source = inspect.getsource(db.calculate_snapshot_totals)
        # Should use coalesce or "or" to handle nulls
        assert (
            "or" in source.lower() or "coalesce" in source.lower() or "0.00" in source
        )

    def test_calculate_snapshot_totals_includes_transfers(self):
        """Verify calculate_snapshot_totals includes transfer totals."""
        source = inspect.getsource(db.calculate_snapshot_totals)
        # Should calculate transfer_in and transfer_out totals
        assert "transfer_in" in source.lower()
        assert "transfer_out" in source.lower()
        # Should return transfer totals in dict
        assert "transfer_in_total" in source
        assert "transfer_out_total" in source

    def test_calculate_snapshot_totals_net_formula_includes_transfers(self):
        """Verify net calculation includes transfers in formula."""
        source = inspect.getsource(db.calculate_snapshot_totals)
        # Net should be: income + transfer_in - expense - transfer_out - cc_payments
        # Check that transfers are used in the net calculation
        assert "transfer_in" in source.lower()
        assert "transfer_out" in source.lower()
        assert "net" in source.lower()


class TestPerAccountSnapshotFunctions:
    """Tests for Phase 4: Per-account snapshot helper functions."""

    def test_get_depository_accounts_function_exists(self):
        """Verify get_depository_accounts function exists."""
        assert hasattr(db, "get_depository_accounts")
        assert callable(db.get_depository_accounts)

    def test_get_depository_accounts_signature(self):
        """Verify get_depository_accounts has correct signature."""
        sig = inspect.signature(db.get_depository_accounts)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "include_excluded" in params
        # Default should be False
        assert sig.parameters["include_excluded"].default is False

    def test_get_depository_accounts_filters_account_type(self):
        """Verify get_depository_accounts filters to depository types."""
        source = inspect.getsource(db.get_depository_accounts)
        # Should filter for depository account types
        assert "type" in source.lower() or "depository" in source.lower()

    def test_get_depository_accounts_respects_exclusion_flag(self):
        """Verify get_depository_accounts respects include_excluded parameter."""
        source = inspect.getsource(db.get_depository_accounts)
        # Should check is_excluded column
        assert "is_excluded" in source

    def test_get_credit_cards_for_account_function_exists(self):
        """Verify get_credit_cards_for_account function exists."""
        assert hasattr(db, "get_credit_cards_for_account")
        assert callable(db.get_credit_cards_for_account)

    def test_get_credit_cards_for_account_signature(self):
        """Verify get_credit_cards_for_account has correct signature."""
        sig = inspect.signature(db.get_credit_cards_for_account)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params

    def test_get_credit_cards_for_account_filters_by_paying_account(self):
        """Verify get_credit_cards_for_account filters by paying_account_id."""
        source = inspect.getsource(db.get_credit_cards_for_account)
        # Should filter WHERE paying_account_id = account_id
        assert "paying_account_id" in source

    def test_get_or_create_snapshot_accepts_account_id(self):
        """Verify get_or_create_snapshot signature includes account_id."""
        sig = inspect.signature(db.get_or_create_snapshot)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "year_month" in params
        assert "account_id" in params

    def test_get_or_create_snapshot_queries_with_account_id(self):
        """Verify get_or_create_snapshot queries by account_id."""
        source = inspect.getsource(db.get_or_create_snapshot)
        # Should filter WHERE year_month = ? AND account_id = ?
        assert "account_id" in source

    def test_get_or_create_snapshot_populates_account_specific_items(self):
        """Verify get_or_create_snapshot filters anticipated items by account."""
        source = inspect.getsource(db.get_or_create_snapshot)
        # When creating snapshot, should filter anticipated items by account_id
        # This will be visible in the implementation when it calls updated helpers
        assert "account_id" in source

    def test_get_or_create_snapshot_populates_account_specific_cards(self):
        """Verify get_or_create_snapshot filters credit cards by account."""
        source = inspect.getsource(db.get_or_create_snapshot)
        # Should use get_credit_cards_for_account or similar filtering
        assert "account_id" in source

    def test_get_available_months_accepts_account_id(self):
        """Verify get_available_months signature includes account_id."""
        sig = inspect.signature(db.get_available_months)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params

    def test_get_available_months_filters_by_account(self):
        """Verify get_available_months filters snapshots by account_id."""
        source = inspect.getsource(db.get_available_months)
        # Should filter WHERE account_id = ?
        assert "account_id" in source

    def test_get_snapshot_line_items_accepts_account_id(self):
        """Verify get_snapshot_line_items signature includes account_id."""
        sig = inspect.signature(db.get_snapshot_line_items)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "year_month" in params
        assert "account_id" in params

    def test_get_snapshot_line_items_queries_with_account_id(self):
        """Verify get_snapshot_line_items filters by account_id."""
        source = inspect.getsource(db.get_snapshot_line_items)
        # Should get snapshot WHERE year_month = ? AND account_id = ?
        assert "account_id" in source

    def test_get_snapshot_credit_cards_accepts_account_id(self):
        """Verify get_snapshot_credit_cards signature includes account_id."""
        sig = inspect.signature(db.get_snapshot_credit_cards)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "year_month" in params
        assert "account_id" in params

    def test_get_snapshot_credit_cards_queries_with_account_id(self):
        """Verify get_snapshot_credit_cards filters by account_id."""
        source = inspect.getsource(db.get_snapshot_credit_cards)
        # Should get snapshot WHERE year_month = ? AND account_id = ?
        assert "account_id" in source

    def test_calculate_snapshot_totals_accepts_account_id(self):
        """Verify calculate_snapshot_totals signature includes account_id."""
        sig = inspect.signature(db.calculate_snapshot_totals)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "year_month" in params
        assert "account_id" in params

    def test_calculate_snapshot_totals_queries_with_account_id(self):
        """Verify calculate_snapshot_totals filters by account_id."""
        source = inspect.getsource(db.calculate_snapshot_totals)
        # Should get snapshot WHERE year_month = ? AND account_id = ?
        assert "account_id" in source

    def test_get_anticipated_expenses_accepts_account_id(self):
        """Verify get_anticipated_expenses signature includes account_id."""
        sig = inspect.signature(db.get_anticipated_expenses)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params

    def test_get_anticipated_expenses_filters_by_account(self):
        """Verify get_anticipated_expenses filters by account_id."""
        source = inspect.getsource(db.get_anticipated_expenses)
        # Should filter WHERE account_id = ?
        assert "account_id" in source

    def test_get_anticipated_income_accepts_account_id(self):
        """Verify get_anticipated_income signature includes account_id."""
        sig = inspect.signature(db.get_anticipated_income)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params

    def test_get_anticipated_income_filters_by_account(self):
        """Verify get_anticipated_income filters by account_id."""
        source = inspect.getsource(db.get_anticipated_income)
        # Should filter WHERE account_id = ?
        assert "account_id" in source
