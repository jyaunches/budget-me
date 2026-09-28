"""Tests for inferred provenance of stored monthly starting balances."""

from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo
from budget_me.streamlit_app.db import get_starting_balance


def _current_snapshot() -> MonthlySnapshot:
    return MonthlySnapshot(
        year_month="2026-01",
        account_id="acc-1",
        starting_balance=Decimal("8000.00"),
    )


PROVENANCE_CASES = [
    pytest.param(
        MonthlySnapshot(
            year_month="2025-12",
            account_id="acc-1",
            status=SnapshotStatus.CLOSED,
            closing_balance=Decimal("8000.00"),
            closing_balance_frozen=True,
        ),
        True,
        id="matching-frozen-prior-close",
    ),
    pytest.param(None, False, id="manual-no-prior"),
    pytest.param(
        MonthlySnapshot(
            year_month="2025-12",
            account_id="acc-1",
            status=SnapshotStatus.CLOSED,
            closing_balance=Decimal("7900.00"),
            closing_balance_frozen=True,
        ),
        False,
        id="conflicting-prior-close",
    ),
    pytest.param(
        MonthlySnapshot(
            year_month="2025-12",
            account_id="acc-1",
            status=SnapshotStatus.CLOSED,
            closing_balance=Decimal("8000.00"),
            closing_balance_frozen=False,
        ),
        False,
        id="prior-close-not-frozen",
    ),
    pytest.param(
        MonthlySnapshot(
            year_month="2025-12",
            account_id="acc-1",
            status=SnapshotStatus.OPEN,
            closing_balance=Decimal("8000.00"),
            closing_balance_frozen=True,
        ),
        False,
        id="prior-snapshot-not-closed",
    ),
]


@pytest.mark.asyncio
@pytest.mark.parametrize(("previous", "expected_frozen"), PROVENANCE_CASES)
async def test_async_stored_starting_balance_provenance(
    previous: MonthlySnapshot | None,
    expected_frozen: bool,
) -> None:
    """The async repository infers provenance only from an exact frozen close."""
    repo = MonthlySnapshotRepo(AsyncMock())
    repo.get_by_year_month = AsyncMock(side_effect=[_current_snapshot(), previous])

    balance, is_frozen = await repo.get_starting_balance("acc-1", "2026-01")

    assert balance == Decimal("8000.00")
    assert is_frozen is expected_frozen


def _query_result(snapshot: MonthlySnapshot | None) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = snapshot
    return result


@pytest.mark.parametrize(("previous", "expected_frozen"), PROVENANCE_CASES)
def test_sync_stored_starting_balance_provenance(
    previous: MonthlySnapshot | None,
    expected_frozen: bool,
) -> None:
    """The Streamlit helper applies the same exact provenance inference."""
    session = MagicMock()
    session.execute.side_effect = [
        _query_result(_current_snapshot()),
        _query_result(previous),
    ]

    balance, is_frozen = get_starting_balance(session, "acc-1", "2026-01")

    assert balance == Decimal("8000.00")
    assert is_frozen is expected_frozen
