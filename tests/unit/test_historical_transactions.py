"""Provider-free tests for historical Plaid transaction backfill."""

from contextlib import asynccontextmanager
from datetime import date
from uuid import uuid4

import pytest

from budget_me.plaid.historical_transactions import (
    HistoricalFetchResult,
    fetch_historical_transactions,
)


@pytest.mark.asyncio
async def test_public_backfill_holds_coordination_around_full_item_work(mocker):
    """Direct and CLI callers cannot bypass the close/backfill barrier."""
    events = []

    @asynccontextmanager
    async def tracked_coordination():
        events.append("lock-acquired")
        try:
            yield
        finally:
            events.append("lock-released")

    expected = HistoricalFetchResult(
        transactions_fetched=1,
        transactions_added=1,
        transactions_updated=0,
        oldest_date=date(2026, 7, 1),
        newest_date=date(2026, 7, 1),
    )

    async def backfill_work(*args, **kwargs):
        events.append("backfill-work")
        return expected

    mocker.patch(
        "budget_me.plaid.historical_transactions.hold_sync_item_coordination",
        tracked_coordination,
    )
    delegate = mocker.patch(
        "budget_me.plaid.historical_transactions."
        "_fetch_historical_transactions_under_coordination",
        mocker.AsyncMock(side_effect=backfill_work),
    )

    item_id = uuid4()
    result = await fetch_historical_transactions(
        item_id,
        days=365,
        account_ids=["checking-1"],
    )

    assert events == ["lock-acquired", "backfill-work", "lock-released"]
    assert result == expected
    delegate.assert_awaited_once_with(
        item_id,
        days=365,
        account_ids=["checking-1"],
    )
