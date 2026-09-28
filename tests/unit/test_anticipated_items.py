"""Unit tests for AnticipatedItem model."""

from budget_me.db.models.anticipated_item import AnticipatedItem, ItemType


class TestAnticipatedItemModel:
    """Tests for AnticipatedItem model structure."""

    def test_anticipated_item_model_has_required_columns(self):
        """Verify all required columns exist on AnticipatedItem model."""
        required_columns = {
            "id",
            "name",
            "amount",
            "item_type",
            "category",
            "active",
            "created_at",
            "updated_at",
        }
        actual_columns = {col.name for col in AnticipatedItem.__table__.columns}
        assert required_columns.issubset(actual_columns), (
            f"Missing columns: {required_columns - actual_columns}"
        )

    def test_anticipated_item_item_type_enum_values(self):
        """Verify ItemType enum has correct values."""
        assert ItemType.EXPENSE == "expense"
        assert ItemType.INCOME == "income"

    def test_anticipated_item_active_defaults_to_true(self):
        """Verify active column defaults to True."""
        active_column = AnticipatedItem.__table__.c.active
        assert active_column.default is not None
        assert active_column.default.arg is True

    def test_anticipated_item_has_indexes(self):
        """Verify index exists on (item_type, active)."""
        indexes = AnticipatedItem.__table__.indexes
        # Check that at least one index includes both item_type and active
        index_columns = [{col.name for col in idx.columns} for idx in indexes]
        assert any({"item_type", "active"}.issubset(cols) for cols in index_columns), (
            "Missing index on (item_type, active)"
        )

    def test_anticipated_item_has_account_id_column(self):
        """Verify AnticipatedItem has account_id column."""
        columns = {col.name for col in AnticipatedItem.__table__.columns}
        assert "account_id" in columns

    def test_anticipated_item_has_account_relationship(self):
        """Verify AnticipatedItem has account relationship."""
        assert hasattr(AnticipatedItem, "account")
