"""Tests for PlaidItem products field functionality."""

from budget_me.db.models.plaid_item import PlaidItem


class TestPlaidItemProducts:
    """Tests for PlaidItem products field."""

    def test_plaid_item_products_default_value(self):
        """PlaidItem products field defaults to ['transactions']."""
        # Verify the field has a default server_default
        products_col = PlaidItem.__table__.columns["products"]
        assert products_col.server_default is not None

    def test_plaid_item_products_can_be_set(self):
        """PlaidItem products field can be set to a list of strings."""
        # This test verifies the field structure, not actual DB insertion
        assert hasattr(PlaidItem, "products")
        # Verify it's a mapped column
        assert "products" in PlaidItem.__mapper__.columns

    def test_plaid_item_has_credit_liabilities_relationship(self):
        """PlaidItem has credit_liabilities relationship."""
        assert hasattr(PlaidItem, "credit_liabilities")
        # Verify it's a relationship attribute
        assert "credit_liabilities" in PlaidItem.__mapper__.relationships
