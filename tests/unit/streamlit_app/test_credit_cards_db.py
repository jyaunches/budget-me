"""Tests for credit cards page database functions."""

import inspect


class TestGetAllCreditCardsWithFullDetails:
    """Tests for get_all_credit_cards_with_full_details function."""

    def test_function_is_exported(self):
        """get_all_credit_cards_with_full_details is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_all_credit_cards_with_full_details")
        assert callable(db.get_all_credit_cards_with_full_details)

    def test_function_includes_account_fields(self):
        """Function query includes all account fields."""
        from budget_me.streamlit_app.db import get_all_credit_cards_with_full_details

        source = inspect.getsource(get_all_credit_cards_with_full_details)

        # Required account fields
        assert "Account.account_id" in source
        assert "Account.name" in source
        assert "Account.display_name" in source
        assert "Account.mask" in source
        assert "Account.balance_current" in source
        assert "Account.payment_strategy" in source
        assert "Account.fixed_payment_amount" in source
        assert "Account.paying_account_id" in source
        assert "Account.is_excluded" in source

    def test_function_includes_institution_id(self):
        """Function query includes institution_id from PlaidItem."""
        from budget_me.streamlit_app.db import get_all_credit_cards_with_full_details

        source = inspect.getsource(get_all_credit_cards_with_full_details)

        assert "PlaidItem.institution_id" in source
        assert "outerjoin" in source.lower()

    def test_function_includes_aprs(self):
        """Function fetches APR data for each card."""
        from budget_me.streamlit_app.db import get_all_credit_cards_with_full_details

        source = inspect.getsource(get_all_credit_cards_with_full_details)

        # Should query CreditLiabilityApr
        assert "CreditLiabilityApr" in source

    def test_function_filters_credit_cards(self):
        """Function filters for credit card subtype."""
        from budget_me.streamlit_app.db import get_all_credit_cards_with_full_details

        source = inspect.getsource(get_all_credit_cards_with_full_details)

        assert '"credit card"' in source or "'credit card'" in source
        assert "Account.subtype" in source

    def test_function_includes_paying_account_display(self):
        """Function includes paying account display name."""
        from budget_me.streamlit_app.db import get_all_credit_cards_with_full_details

        source = inspect.getsource(get_all_credit_cards_with_full_details)

        # Should have alias or join for paying account
        assert "paying_account" in source.lower()
