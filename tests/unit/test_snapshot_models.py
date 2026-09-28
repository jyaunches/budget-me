"""Unit tests for snapshot models."""

import uuid
from decimal import Decimal

from budget_me.db.models.account import PaymentStrategy
from budget_me.db.models.anticipated_item import ItemType
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem


class TestSnapshotModels:
    """Test snapshot model structure and enums."""

    def test_monthly_snapshot_model_creation(self):
        """Test basic MonthlySnapshot model creation."""
        snapshot = MonthlySnapshot(year_month="2025-01", status=SnapshotStatus.OPEN)
        assert snapshot.year_month == "2025-01"
        assert snapshot.status == SnapshotStatus.OPEN
        assert snapshot.income_total is None
        assert snapshot.expense_total is None
        assert snapshot.credit_card_total is None
        assert snapshot.net is None
        assert snapshot.closed_at is None

    def test_snapshot_status_enum_values(self):
        """Test SnapshotStatus enum has correct values."""
        assert SnapshotStatus.OPEN == "open"
        assert SnapshotStatus.CLOSED == "closed"
        assert len(SnapshotStatus) == 2

    def test_snapshot_line_item_uses_item_type_enum(self):
        """Test SnapshotLineItem uses ItemType enum from anticipated_item."""
        item = SnapshotLineItem(
            snapshot_id=uuid.uuid4(),
            item_type=ItemType.EXPENSE,
            name="Rent",
            amount=Decimal("2000.00"),
        )
        assert item.item_type == ItemType.EXPENSE

    def test_snapshot_credit_card_uses_payment_strategy_enum(self):
        """Test SnapshotCreditCard uses PaymentStrategy enum from account."""
        card = SnapshotCreditCard(
            snapshot_id=uuid.uuid4(),
            account_id="account-123",
            payment_strategy=PaymentStrategy.PAY_IN_FULL,
            calculated_payment=Decimal("1500.00"),
        )
        assert card.payment_strategy == PaymentStrategy.PAY_IN_FULL

    def test_snapshot_relationships_defined(self):
        """Test MonthlySnapshot has relationships to line_items and credit_cards."""
        assert hasattr(MonthlySnapshot, "line_items")
        assert hasattr(MonthlySnapshot, "credit_cards")

    def test_monthly_snapshot_has_transfer_fields(self):
        """Test MonthlySnapshot has transfer_in_total and transfer_out_total fields."""
        snapshot = MonthlySnapshot(year_month="2025-12", status=SnapshotStatus.OPEN)
        assert hasattr(snapshot, "transfer_in_total")
        assert hasattr(snapshot, "transfer_out_total")
        assert snapshot.transfer_in_total is None
        assert snapshot.transfer_out_total is None

    def test_monthly_snapshot_has_account_id_field(self):
        """Test MonthlySnapshot has account_id field."""
        snapshot = MonthlySnapshot(
            year_month="2025-12", account_id="test-acc-123", status=SnapshotStatus.OPEN
        )
        assert hasattr(snapshot, "account_id")
        assert snapshot.account_id == "test-acc-123"

    def test_monthly_snapshot_has_account_relationship(self):
        """Test MonthlySnapshot has relationship to Account."""
        assert hasattr(MonthlySnapshot, "account")

    def test_monthly_snapshot_table_args_has_unique_constraint(self):
        """Test MonthlySnapshot has unique constraint on (year_month, account_id)."""
        from sqlalchemy import UniqueConstraint

        # Check __table_args__
        table_args = MonthlySnapshot.__table_args__

        # Find UniqueConstraint
        unique_constraints = [
            arg for arg in table_args if isinstance(arg, UniqueConstraint)
        ]
        assert len(unique_constraints) > 0

        # Verify columns - should have constraint on (year_month, account_id)
        constraint = unique_constraints[0]
        column_names = [col.name for col in constraint.columns]
        assert "year_month" in column_names
        assert "account_id" in column_names
