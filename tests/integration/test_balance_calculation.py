"""Integration tests for balance calculation in MonthlySnapshotRepo."""

from datetime import UTC, datetime
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


async def test_get_starting_balance_from_closed_month(db_session):
    """Test get_starting_balance returns frozen closing from previous month."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    nov = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-11",
        account_id=account_id,
        status=SnapshotStatus.CLOSED,
        closing_balance=Decimal("5000"),
        closing_balance_frozen=True,
        created_at=datetime.now(UTC),
    )
    session.add(nov)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_starting_balance(account_id, "2025-12")

    assert balance == Decimal("5000")
    assert frozen is True


async def test_get_closing_balance_frozen(db_session):
    """Test get_closing_balance returns frozen value for closed month."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.CLOSED,
        closing_balance=Decimal("3000"),
        closing_balance_frozen=True,
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_closing_balance(account_id, "2025-12")

    assert balance == Decimal("3000")
    assert frozen is True


async def test_get_closing_balance_calculated(db_session):
    """Test get_closing_balance calculates for open month."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("5000"),
        income_total=Decimal("2000"),
        expense_total=Decimal("3500"),
        credit_card_total=Decimal("500"),
        transfer_in_total=Decimal("1000"),
        transfer_out_total=Decimal("100"),
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_closing_balance(account_id, "2025-12")

    # 5000 + 2000 - 3500 - 500 + 1000 - 100 = 3900
    assert balance == Decimal("3900")
    assert frozen is False


async def test_freeze_closing_balance(db_session):
    """Legacy freezes refuse without mutating the open snapshot."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("5000"),
        income_total=Decimal("1000"),
        expense_total=Decimal("2000"),
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    with pytest.raises(
        RuntimeError,
        match=r"budget_me\.snapshots\.service\.close_snapshot\(\)",
    ):
        await repo.freeze_closing_balance(dec.id)

    await session.refresh(dec)
    assert dec.status == SnapshotStatus.OPEN
    assert dec.closing_balance is None
    assert dec.closing_balance_frozen is False


async def test_get_starting_balance_from_open_month_with_closing_balance(db_session):
    """Test get_starting_balance returns estimated closing from open previous month.

    This test demonstrates the bug where get_starting_balance only uses
    the previous month's closing_balance if that month is CLOSED.
    It should also use the closing_balance if it's set on an OPEN month
    (as an estimate), returning it with frozen=False.
    """
    session, conn = db_session
    account_id = await create_test_account(conn)

    # Create December as OPEN with closing_balance set (estimated)
    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        closing_balance=Decimal("4500"),
        closing_balance_frozen=False,
        created_at=datetime.now(UTC),
    )
    session.add(dec)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_starting_balance(account_id, "2026-01")

    # Should return December's estimated closing balance
    assert balance == Decimal("4500")
    # Should be marked as not frozen since December is still open
    assert frozen is False


async def test_get_starting_balance_from_open_month_calculated_close(db_session):
    """A future month inherits the live calculated close of an open month."""
    session, conn = db_session
    account_id = await create_test_account(conn)

    july = MonthlySnapshot(
        id=uuid4(),
        year_month="2026-07",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("5000"),
        income_total=Decimal("2000"),
        expense_total=Decimal("1000"),
        credit_card_total=Decimal("500"),
        transfer_in_total=Decimal("100"),
        transfer_out_total=Decimal("50"),
        created_at=datetime.now(UTC),
    )
    session.add(july)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_starting_balance(account_id, "2026-08")

    assert balance == Decimal("5550")
    assert frozen is False


async def test_get_closing_balance_calculated_from_derived_starting(db_session):
    """Test get_closing_balance calculates using derived starting balance.

    When a month doesn't have starting_balance stored directly but can
    derive it from the previous month's closing_balance, the closing
    balance should still be calculated.
    """
    session, conn = db_session
    account_id = await create_test_account(conn)

    # Create December as OPEN with closing_balance set (estimated)
    dec = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        closing_balance=Decimal("5000"),
        closing_balance_frozen=False,
        created_at=datetime.now(UTC),
    )
    session.add(dec)

    # Create January with NO starting_balance but with totals
    jan = MonthlySnapshot(
        id=uuid4(),
        year_month="2026-01",
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        income_total=Decimal("3000"),
        expense_total=Decimal("1500"),
        credit_card_total=Decimal("500"),
        transfer_in_total=Decimal("0"),
        transfer_out_total=Decimal("0"),
        created_at=datetime.now(UTC),
    )
    session.add(jan)
    await session.flush()

    repo = MonthlySnapshotRepo(session)
    balance, frozen = await repo.get_closing_balance(account_id, "2026-01")

    # Should calculate: 5000 (derived starting) + 3000 - 1500 - 500 = 6000
    assert balance == Decimal("6000")
    assert frozen is False
