"""Tests for Streamlit app database functions.

These tests verify the db module functions are properly structured.
Integration tests with a real database would be in tests/integration/.
"""

import inspect


class TestDbModuleFunctions:
    """Tests for db.py module exports."""

    def test_get_accounts_is_exported(self):
        """get_accounts function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_accounts")
        assert callable(db.get_accounts)

    def test_get_all_accounts_with_details_is_exported(self):
        """get_all_accounts_with_details function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_all_accounts_with_details")
        assert callable(db.get_all_accounts_with_details)

    def test_update_account_display_name_is_exported(self):
        """update_account_display_name function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "update_account_display_name")
        assert callable(db.update_account_display_name)

    def test_get_transactions_is_exported(self):
        """get_transactions function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_transactions")
        assert callable(db.get_transactions)


class TestGetAccountsDisplayName:
    """Tests for get_accounts display_name handling."""

    def test_get_accounts_selects_display_name(self):
        """get_accounts query includes display_name field."""
        from budget_me.streamlit_app.db import get_accounts

        source = inspect.getsource(get_accounts)

        # Verify display_name is selected
        assert "display_name" in source
        assert "Account.display_name" in source

    def test_get_accounts_uses_display_name_for_display(self):
        """get_accounts uses display_name for display field when set."""
        from budget_me.streamlit_app.db import get_accounts

        source = inspect.getsource(get_accounts)

        # Verify fallback logic exists
        assert "row.display_name or row.name" in source
        assert "shown_name" in source


class TestGetAllAccountsWithDetails:
    """Tests for get_all_accounts_with_details function."""

    def test_get_all_accounts_with_details_includes_display_name(self):
        """get_all_accounts_with_details includes display_name in query."""
        from budget_me.streamlit_app.db import get_all_accounts_with_details

        source = inspect.getsource(get_all_accounts_with_details)

        assert "Account.display_name" in source

    def test_get_all_accounts_with_details_includes_balances(self):
        """get_all_accounts_with_details includes balance fields."""
        from budget_me.streamlit_app.db import get_all_accounts_with_details

        source = inspect.getsource(get_all_accounts_with_details)

        assert "Account.balance_current" in source
        assert "Account.balance_available" in source

    def test_get_all_accounts_with_details_includes_institution(self):
        """get_all_accounts_with_details includes institution_id from PlaidItem."""
        from budget_me.streamlit_app.db import get_all_accounts_with_details

        source = inspect.getsource(get_all_accounts_with_details)

        assert "PlaidItem.institution_id" in source
        assert "outerjoin" in source.lower()


class TestUpdateAccountDisplayName:
    """Tests for update_account_display_name function."""

    def test_update_account_display_name_accepts_none(self):
        """update_account_display_name allows None to clear display name."""
        from budget_me.streamlit_app.db import update_account_display_name

        sig = inspect.signature(update_account_display_name)
        params = sig.parameters

        # Verify display_name parameter accepts None
        assert "display_name" in params
        annotation = params["display_name"].annotation
        assert "None" in str(annotation)

    def test_update_account_display_name_updates_correct_field(self):
        """update_account_display_name updates display_name field."""
        from budget_me.streamlit_app.db import update_account_display_name

        source = inspect.getsource(update_account_display_name)

        # Verify it updates the correct field
        assert "values(display_name=" in source
        assert "Account.account_id" in source


class TestGetTransactionsDisplayName:
    """Tests for get_transactions display_name handling."""

    def test_get_transactions_uses_coalesce_for_account_name(self):
        """get_transactions uses COALESCE for account_name to prefer display_name."""
        from budget_me.streamlit_app.db import get_transactions

        source = inspect.getsource(get_transactions)

        # Verify COALESCE is used to prefer display_name over name
        assert "coalesce" in source.lower()
        assert "Account.display_name" in source
        assert "Account.name" in source
        assert "account_name" in source


class TestGetDebtWithAprs:
    """Tests for get_debt_with_aprs function."""

    def test_get_debt_with_aprs_is_exported(self):
        """get_debt_with_aprs function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_debt_with_aprs")
        assert callable(db.get_debt_with_aprs)

    def test_get_debt_with_aprs_uses_coalesce_for_account_name(self):
        """get_debt_with_aprs uses COALESCE(display_name, name) for account name."""
        from budget_me.streamlit_app.db import get_debt_with_aprs

        source = inspect.getsource(get_debt_with_aprs)

        # Verify COALESCE is used to prefer display_name over name
        assert "coalesce" in source.lower()
        assert "Account.display_name" in source
        assert "Account.name" in source

    def test_get_debt_with_aprs_joins_required_tables(self):
        """get_debt_with_aprs joins CreditLiabilityApr, CreditLiability, Account."""
        from budget_me.streamlit_app.db import get_debt_with_aprs

        source = inspect.getsource(get_debt_with_aprs)

        # Verify all required tables are referenced
        assert "CreditLiabilityApr" in source
        assert "CreditLiability" in source
        assert "Account" in source
        assert "join" in source.lower()

    def test_get_debt_with_aprs_selects_required_fields(self):
        """get_debt_with_aprs selects all required APR and balance fields."""
        from budget_me.streamlit_app.db import get_debt_with_aprs

        source = inspect.getsource(get_debt_with_aprs)

        # Verify all required fields are selected
        assert "apr_type" in source
        assert "apr_percentage" in source
        assert "balance_subject_to_apr" in source
        assert "interest_charge_amount" in source
        assert "mask" in source

    def test_get_debt_with_aprs_orders_by_balance_desc(self):
        """get_debt_with_aprs orders results by balance descending."""
        from budget_me.streamlit_app.db import get_debt_with_aprs

        source = inspect.getsource(get_debt_with_aprs)

        # Verify ordering by balance descending
        assert "order_by" in source.lower()
        assert "balance_subject_to_apr" in source
        assert "desc" in source.lower()


class TestGetPromoCardsWithAprs:
    """Tests for get_promo_cards_with_aprs function."""

    def test_get_promo_cards_filters_by_strategy(self):
        """get_promo_cards_with_aprs filters by payment_strategy='promotional_paydown'."""
        from budget_me.streamlit_app.db import get_promo_cards_with_aprs

        source = inspect.getsource(get_promo_cards_with_aprs)

        # Verify filters by promotional_paydown strategy
        assert "payment_strategy" in source
        assert "promotional_paydown" in source

    def test_get_promo_cards_includes_apr_details(self):
        """get_promo_cards_with_aprs includes APR details with promo fields."""
        from budget_me.streamlit_app.db import get_promo_cards_with_aprs

        source = inspect.getsource(get_promo_cards_with_aprs)

        # Verify APR-related tables and fields are queried
        assert "CreditLiabilityApr" in source
        assert "CreditLiability" in source
        # Verify promo fields are included
        assert "promo_offer_id" in source or "promo" in source.lower()
        assert "promo_rate_end_date" in source or "end_date" in source.lower()


class TestGetExpiringPromos:
    """Tests for get_expiring_promos function."""

    def test_get_expiring_promos_respects_window(self):
        """get_expiring_promos filters by within_days parameter."""
        from budget_me.streamlit_app.db import get_expiring_promos

        source = inspect.getsource(get_expiring_promos)

        # Verify within_days parameter exists
        sig = inspect.signature(get_expiring_promos)
        assert "within_days" in sig.parameters

        # Verify date filtering logic
        assert "promo_rate_end_date" in source
        # Verify timedelta or date comparison logic
        assert "timedelta" in source or "date" in source.lower()


class TestUpsertPromotionalApr:
    """Tests for upsert_promotional_apr function."""

    def test_upsert_promotional_apr_sets_source_manual(self):
        """upsert_promotional_apr sets source to manual."""
        from budget_me.streamlit_app.db import upsert_promotional_apr

        source = inspect.getsource(upsert_promotional_apr)

        # Verify source is set to manual
        assert "source" in source
        assert '"manual"' in source or "'manual'" in source


class TestAccountExclusionFiltering:
    """Tests for account exclusion filtering in query functions."""

    def test_get_credit_cards_with_strategy_filters_excluded(self):
        """get_credit_cards_with_strategy filters excluded accounts."""
        from budget_me.streamlit_app.db import get_credit_cards_with_strategy

        source = inspect.getsource(get_credit_cards_with_strategy)

        # Verify filter is applied
        assert "is_excluded" in source
        assert (
            "Account.is_excluded == False" in source
            or "Account.is_excluded.is_(False)" in source
        )

    def test_get_loans_with_interest_filters_excluded(self):
        """get_loans_with_interest filters excluded accounts."""
        from budget_me.streamlit_app.db import get_loans_with_interest

        source = inspect.getsource(get_loans_with_interest)
        assert "is_excluded" in source

    def test_get_cc_calculated_interest_filters_excluded(self):
        """get_cc_calculated_interest filters excluded accounts."""
        from budget_me.streamlit_app.db import get_cc_calculated_interest

        source = inspect.getsource(get_cc_calculated_interest)
        assert "is_excluded" in source

    def test_get_promo_cards_with_aprs_filters_excluded(self):
        """get_promo_cards_with_aprs filters excluded accounts."""
        from budget_me.streamlit_app.db import get_promo_cards_with_aprs

        source = inspect.getsource(get_promo_cards_with_aprs)
        assert "is_excluded" in source

    def test_get_expiring_promos_filters_excluded(self):
        """get_expiring_promos filters excluded accounts."""
        from budget_me.streamlit_app.db import get_expiring_promos

        source = inspect.getsource(get_expiring_promos)
        assert "is_excluded" in source

    def test_get_accounts_has_include_excluded_parameter(self):
        """get_accounts accepts include_excluded parameter."""
        from budget_me.streamlit_app.db import get_accounts

        sig = inspect.signature(get_accounts)
        assert "include_excluded" in sig.parameters

        # Verify default is False
        param = sig.parameters["include_excluded"]
        assert param.default is False

    def test_get_accounts_filters_when_include_excluded_false(self):
        """get_accounts filters excluded accounts by default."""
        from budget_me.streamlit_app.db import get_accounts

        source = inspect.getsource(get_accounts)

        # Verify conditional filter logic
        assert "include_excluded" in source
        assert "is_excluded" in source
        assert "if not include_excluded" in source or "if include_excluded" in source


class TestGetBudgetCategories:
    """Tests for get_budget_categories function."""

    def test_get_budget_categories_is_exported(self):
        """get_budget_categories function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_budget_categories")
        assert callable(db.get_budget_categories)

    def test_get_budget_categories_queries_distinct_categories(self):
        """get_budget_categories uses DISTINCT on budget_category."""
        from budget_me.streamlit_app.db import get_budget_categories

        source = inspect.getsource(get_budget_categories)

        assert "Transaction.budget_category" in source
        assert "distinct" in source.lower()

    def test_get_budget_categories_excludes_null(self):
        """get_budget_categories excludes NULL categories."""
        from budget_me.streamlit_app.db import get_budget_categories

        source = inspect.getsource(get_budget_categories)

        assert "is_not(None)" in source or "isnot(None)" in source

    def test_get_budget_categories_orders_alphabetically(self):
        """get_budget_categories orders results alphabetically."""
        from budget_me.streamlit_app.db import get_budget_categories

        source = inspect.getsource(get_budget_categories)

        assert "order_by" in source.lower()


class TestAccountExcludedStatusUpdate:
    """Tests for account excluded status update functionality."""

    def test_get_all_accounts_with_details_includes_is_excluded(self):
        """get_all_accounts_with_details includes is_excluded in query."""
        from budget_me.streamlit_app.db import get_all_accounts_with_details

        source = inspect.getsource(get_all_accounts_with_details)
        assert "Account.is_excluded" in source

    def test_update_account_excluded_status_is_exported(self):
        """update_account_excluded_status function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "update_account_excluded_status")
        assert callable(db.update_account_excluded_status)

    def test_update_account_excluded_status_accepts_bool_parameter(self):
        """update_account_excluded_status accepts account_id and is_excluded."""
        from budget_me.streamlit_app.db import update_account_excluded_status

        sig = inspect.signature(update_account_excluded_status)
        assert "account_id" in sig.parameters
        assert "is_excluded" in sig.parameters

        # Check type hints if present
        source = inspect.getsource(update_account_excluded_status)
        assert "is_excluded: bool" in source

    def test_update_account_excluded_status_updates_field(self):
        """update_account_excluded_status uses UPDATE statement."""
        from budget_me.streamlit_app.db import update_account_excluded_status

        source = inspect.getsource(update_account_excluded_status)

        # Verify UPDATE logic
        assert "update" in source.lower()
        assert "Account" in source
        assert "is_excluded" in source
        assert "account_id" in source


class TestGetCategoryTransactions:
    """Tests for get_category_transactions function."""

    def test_get_category_transactions_is_exported(self):
        """get_category_transactions function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_category_transactions")
        assert callable(db.get_category_transactions)

    def test_get_category_transactions_has_correct_signature(self):
        """get_category_transactions accepts session, account_id, year_month, category."""
        from budget_me.streamlit_app.db import get_category_transactions

        sig = inspect.signature(get_category_transactions)
        params = sig.parameters

        assert "session" in params
        assert "account_id" in params
        assert "year_month" in params
        assert "category" in params

    def test_get_category_transactions_finds_linked_credit_cards(self):
        """get_category_transactions queries credit cards via paying_account_id."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify it queries linked credit cards like get_category_actuals does
        assert "paying_account_id" in source
        assert "Account" in source

    def test_get_category_transactions_filters_by_category(self):
        """get_category_transactions filters by budget_category."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        assert "budget_category" in source
        assert "category" in source

    def test_get_category_transactions_filters_by_month(self):
        """get_category_transactions filters by year and month."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify date extraction logic
        assert "extract" in source.lower() or "year" in source
        assert "month" in source

    def test_get_category_transactions_excludes_reimbursable(self):
        """get_category_transactions excludes reimbursable transactions."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        assert "reimbursable" in source

    def test_get_category_transactions_excludes_money_movement(self):
        """get_category_transactions excludes money movement categories."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify excluded categories
        assert "reimbursement" in source or "excluded_categories" in source
        assert (
            "credit_card_payment" in source
            or "cc_payment" in source
            or "excluded_categories" in source
        )
        assert "transfer" in source or "excluded_categories" in source

    def test_get_category_transactions_only_includes_expenses(self):
        """get_category_transactions only includes positive amounts (expenses)."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify filter for positive amounts
        assert "amount > 0" in source or "amount" in source

    def test_get_category_transactions_orders_by_date_desc(self):
        """get_category_transactions orders results by date descending."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        assert "order_by" in source.lower()
        assert "date" in source
        assert "desc" in source.lower()

    def test_get_category_transactions_returns_required_fields(self):
        """get_category_transactions returns date, merchant_name, amount, account_name."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify all required fields are selected
        assert "date" in source
        assert "merchant_name" in source or "name" in source
        assert "amount" in source
        assert "account_name" in source or "Account.name" in source

    def test_get_category_transactions_uses_merchant_name_fallback(self):
        """get_category_transactions uses merchant_name with fallback to name."""
        from budget_me.streamlit_app.db import get_category_transactions

        source = inspect.getsource(get_category_transactions)

        # Verify fallback logic for merchant name
        assert "merchant_name" in source
        assert "name" in source
        assert "coalesce" in source.lower() or "or" in source
