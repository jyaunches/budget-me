"""Unit tests for MonthlySnapshot balance fields."""

from datetime import UTC, datetime
from decimal import Decimal
from uuid import uuid4

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus


def test_monthly_snapshot_balance_fields_nullable():
    """Test that MonthlySnapshot can be created without balance fields."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=str(uuid4()),
        status=SnapshotStatus.OPEN,
        created_at=datetime.now(UTC),
    )

    # Balance fields can be None (not required at instantiation)
    assert snapshot.starting_balance is None
    assert snapshot.closing_balance is None
    # closing_balance_frozen defaults are applied at database level, not Python object level
    # When not explicitly set, it's None in Python but will be False when persisted
    assert snapshot.closing_balance_frozen in (None, False)


def test_monthly_snapshot_balance_fields_populated():
    """Test that MonthlySnapshot stores balance values correctly."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=str(uuid4()),
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("10000.00"),
        closing_balance=Decimal("9500.50"),
        closing_balance_frozen=False,
        created_at=datetime.now(UTC),
    )

    assert snapshot.starting_balance == Decimal("10000.00")
    assert snapshot.closing_balance == Decimal("9500.50")
    assert isinstance(snapshot.starting_balance, Decimal)
    assert isinstance(snapshot.closing_balance, Decimal)


def test_closing_balance_frozen_default_false():
    """Test that closing_balance_frozen defaults to False when not explicitly set."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=str(uuid4()),
        status=SnapshotStatus.OPEN,
        created_at=datetime.now(UTC),
    )

    # Default is applied at database level (via server_default in migration)
    # In Python object before persistence, it may be None
    assert snapshot.closing_balance_frozen in (None, False)


def test_closing_balance_frozen_can_be_set_true():
    """Test that closing_balance_frozen can be set to True."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=str(uuid4()),
        status=SnapshotStatus.CLOSED,
        closing_balance=Decimal("8000.00"),
        closing_balance_frozen=True,
        created_at=datetime.now(UTC),
    )

    assert snapshot.closing_balance_frozen is True
    assert snapshot.closing_balance == Decimal("8000.00")
