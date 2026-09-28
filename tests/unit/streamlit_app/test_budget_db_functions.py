"""Tests for budget database helper functions in db.py.

These tests verify the budget functions are properly structured and exported.
Integration tests with a real database are in tests/integration/.
"""

import inspect


class TestBudgetDbFunctions:
    """Tests for budget-related db.py module exports."""

    def test_get_category_budgets_is_exported(self):
        """get_category_budgets function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_category_budgets")
        assert callable(db.get_category_budgets)

    def test_upsert_category_budget_is_exported(self):
        """upsert_category_budget function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "upsert_category_budget")
        assert callable(db.upsert_category_budget)

    def test_get_category_actuals_is_exported(self):
        """get_category_actuals function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_category_actuals")
        assert callable(db.get_category_actuals)

    def test_get_available_budget_months_is_exported(self):
        """get_available_budget_months function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_available_budget_months")
        assert callable(db.get_available_budget_months)

    def test_is_budget_month_locked_is_exported(self):
        """is_budget_month_locked function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "is_budget_month_locked")
        assert callable(db.is_budget_month_locked)

    def test_get_budget_categories_from_yaml_is_exported(self):
        """get_budget_categories_from_yaml function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_budget_categories_from_yaml")
        assert callable(db.get_budget_categories_from_yaml)

    def test_copy_budgets_from_month_is_exported(self):
        """copy_budgets_from_month function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "copy_budgets_from_month")
        assert callable(db.copy_budgets_from_month)

    def test_get_previous_month_is_exported(self):
        """get_previous_month function is exported from db module."""
        from budget_me.streamlit_app import db

        assert hasattr(db, "get_previous_month")
        assert callable(db.get_previous_month)


class TestBudgetFunctionSignatures:
    """Tests for budget function signatures."""

    def test_get_category_budgets_signature(self):
        """get_category_budgets has correct parameters."""
        from budget_me.streamlit_app.db import get_category_budgets

        sig = inspect.signature(get_category_budgets)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params
        assert "year_month" in params

    def test_upsert_category_budget_signature(self):
        """upsert_category_budget has correct parameters."""
        from budget_me.streamlit_app.db import upsert_category_budget

        sig = inspect.signature(upsert_category_budget)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params
        assert "year_month" in params
        assert "category" in params
        assert "amount" in params

    def test_get_category_actuals_signature(self):
        """get_category_actuals has correct parameters."""
        from budget_me.streamlit_app.db import get_category_actuals

        sig = inspect.signature(get_category_actuals)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params
        assert "year_month" in params

    def test_copy_budgets_from_month_signature(self):
        """copy_budgets_from_month has correct parameters."""
        from budget_me.streamlit_app.db import copy_budgets_from_month

        sig = inspect.signature(copy_budgets_from_month)
        params = list(sig.parameters.keys())
        assert "session" in params
        assert "account_id" in params
        assert "target_month" in params
        assert "source_month" in params


class TestBudgetMonthLocking:
    """Tests for is_budget_month_locked logic."""

    def test_is_budget_month_locked_imports_date(self):
        """is_budget_month_locked uses date module for comparison."""
        from budget_me.streamlit_app.db import is_budget_month_locked

        source = inspect.getsource(is_budget_month_locked)
        assert "date.today()" in source
        assert "strftime" in source


class TestGetPreviousMonth:
    """Tests for get_previous_month logic."""

    def test_get_previous_month_uses_relativedelta(self):
        """get_previous_month uses relativedelta for date arithmetic."""
        from budget_me.streamlit_app.db import get_previous_month

        source = inspect.getsource(get_previous_month)
        assert "relativedelta" in source
        assert "months=1" in source


class TestGetBudgetCategoriesFromYaml:
    """Tests for get_budget_categories_from_yaml."""

    def test_get_budget_categories_from_yaml_uses_rules_loader(self):
        """The category catalog comes from the packaged OSS rules file."""
        from budget_me.streamlit_app.db import get_budget_categories_from_yaml

        source = inspect.getsource(get_budget_categories_from_yaml)
        assert "PACKAGED_RULES_PATH" in source
        assert "get_rules_path" not in source
        assert "load_rules" in source

    def test_get_budget_categories_from_yaml_returns_list(self):
        """get_budget_categories_from_yaml returns a list."""
        from budget_me.streamlit_app.db import get_budget_categories_from_yaml

        categories = get_budget_categories_from_yaml()
        assert isinstance(categories, list)
        assert len(categories) > 0

    def test_get_budget_categories_from_yaml_includes_common_categories(self):
        """get_budget_categories_from_yaml includes expected categories."""
        from budget_me.streamlit_app.db import get_budget_categories_from_yaml

        categories = get_budget_categories_from_yaml()
        assert "groceries" in categories
        assert "dining" in categories
        assert "utilities" in categories
