"""Tests for CategoryBudget model structure."""

from budget_me.db.models import CategoryBudget


class TestCategoryBudgetModel:
    """Tests for CategoryBudget model structure."""

    def test_category_budget_model_has_required_fields(self):
        """CategoryBudget model has all required fields."""
        assert hasattr(CategoryBudget, "id")
        assert hasattr(CategoryBudget, "account_id")
        assert hasattr(CategoryBudget, "year_month")
        assert hasattr(CategoryBudget, "category")
        assert hasattr(CategoryBudget, "budget_amount")
        assert hasattr(CategoryBudget, "created_at")
        assert hasattr(CategoryBudget, "updated_at")

    def test_category_budget_has_account_relationship(self):
        """CategoryBudget has account relationship."""
        assert hasattr(CategoryBudget, "account")
        # Verify it's a relationship attribute
        assert "account" in CategoryBudget.__mapper__.relationships

    def test_category_budget_tablename(self):
        """CategoryBudget uses correct table name."""
        assert CategoryBudget.__tablename__ == "category_budgets"
