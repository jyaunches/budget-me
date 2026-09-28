"""Integration tests for closing snapshots and freezing balances."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo

pytestmark = pytest.mark.asyncio


async def create_test_account(conn):
    """Create a test account with plaid_item."""
    result = await conn.execute(
        text("""
        INSERT INTO plaid_items (id, user_key, item_id, access_token_enc, created_at, updated_at)
        VALUES (gen_random_uuid(), 'test', :item_id, 'enc', NOW(), NOW())
        RETURNING id
    """),
        {"item_id": f"item-{uuid4()}"},
    )
    plaid_item_id = result.fetchone()[0]

    result = await conn.execute(
        text("""
        INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
        VALUES (gen_random_uuid(), :plaid_item_id, :account_id, 'Test', 'depository', NOW(), NOW())
        RETURNING account_id
    """),
        {"plaid_item_id": plaid_item_id, "account_id": f"acc-{uuid4()}"},
    )
    return result.fetchone()[0]


async def test_repository_close_refuses_without_mutating_snapshot(db_session):
    """The repository cannot bypass the guarded snapshot close service."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("10000"),
        income_total=Decimal("5000"),
        expense_total=Decimal("7000"),
        closing_balance=None,
        closing_balance_frozen=False,
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    with pytest.raises(
        RuntimeError,
        match=r"budget_me\.snapshots\.service\.close_snapshot\(\)",
    ):
        await repo.close(dec.id)

    await session.refresh(dec)
    assert dec.status == SnapshotStatus.OPEN
    assert dec.closing_balance is None
    assert dec.closing_balance_frozen is False
    assert dec.closed_at is None
    assert dec.income_total == Decimal("5000")
    assert dec.expense_total == Decimal("7000")


async def test_closed_month_balance_is_inherited_by_next_month(db_session):
    """A later month reads the frozen balance persisted by a guarded close."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.CLOSED,
        starting_balance=Decimal("10000"),
        income_total=Decimal("3000"),
        expense_total=Decimal("5000"),
        closing_balance=Decimal("8000"),
        closing_balance_frozen=True,
        closed_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    jan_starting, is_frozen = await repo.get_starting_balance(account_id, "2026-01")
    assert jan_starting == Decimal("8000")
    assert is_frozen is True


async def test_closing_balance_prefers_reconciled_net_over_wrong_daily_capture(
    db_session,
):
    """A wrong daily balance capture must be ignored in favor of starting + net.

    Regression: a same-day posting (e.g. a check clearing on the last day of the
    month) made Plaid's daily balance capture wrong, and closing froze that wrong
    value — which then cascaded into every following month's starting balance.
    The reconciled net (starting + income - expense - cc + transfers) is
    authoritative; the daily capture is only a fallback.
    """
    session, conn = db_session
    account_id = await create_test_account(conn)

    # December: starting 10000, income 5000, expense 7000 -> reconciled net = 8000
    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("10000"),
        income_total=Decimal("5000"),
        expense_total=Decimal("7000"),
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    # A WRONG daily capture for 12/31 (e.g. it missed a same-day check)
    await conn.execute(
        text("""
            INSERT INTO account_balance_snapshots
            (id, account_id, snapshot_date, balance_current, created_at)
            VALUES (gen_random_uuid(), :a, :d, :b, NOW())
        """),
        {"a": account_id, "d": date(2025, 12, 31), "b": Decimal("9999")},
    )

    repo = MonthlySnapshotRepo(session)

    bal, is_frozen = await repo.get_closing_balance(account_id, "2025-12")
    assert bal == Decimal("8000")
    assert is_frozen is False
