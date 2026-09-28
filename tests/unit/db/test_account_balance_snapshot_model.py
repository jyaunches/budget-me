"""Unit tests for AccountBalanceSnapshot model."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot


def test_account_balance_snapshot_model_fields():
    """Verify AccountBalanceSnapshot model has all required fields with correct types."""
    snapshot = AccountBalanceSnapshot(
        id=uuid4(),
        account_id=str(uuid4()),
        snapshot_date=date(2025, 12, 31),
        balance_current=Decimal("1000.50"),
        balance_available=Decimal("950.25"),
        created_at=datetime.now(UTC),
    )
    assert isinstance(snapshot.id, type(uuid4()))
    assert isinstance(snapshot.account_id, str)
    assert isinstance(snapshot.snapshot_date, date)
    assert isinstance(snapshot.balance_current, Decimal)
    assert isinstance(snapshot.balance_available, Decimal)
    assert isinstance(snapshot.created_at, datetime)
