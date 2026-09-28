"""Integration tests for AccountBalanceSnapshotRepo."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError

from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.repos.account_balance_snapshot_repo import AccountBalanceSnapshotRepo

pytestmark = pytest.mark.asyncio


async def create_test_account(conn):
    """Helper to create a test account."""
    # Create plaid item
    plaid_item_result = await conn.execute(
        text("""
            INSERT INTO plaid_items (id, user_key, item_id, access_token_enc, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                'test-user',
                :item_id,
                'test-access-token-encrypted',
                NOW(),
                NOW()
            )
            RETURNING id
        """),
        {"item_id": f"test-item-{uuid4()}"},
    )
    plaid_item_id = plaid_item_result.fetchone()[0]

    # Create account
    account_result = await conn.execute(
        text("""
            INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                :plaid_item_id,
                :account_id,
                'Test Account',
                'depository',
                NOW(),
                NOW()
            )
            RETURNING account_id
        """),
        {
            "plaid_item_id": plaid_item_id,
            "account_id": f"test-acc-{uuid4()}",
        },
    )
    return account_result.fetchone()[0]


async def test_upsert_creates_new_snapshot(db_session):
    """Test that upsert creates a new snapshot when none exists."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    repo = AccountBalanceSnapshotRepo(session)
    snapshot = await repo.upsert(
        account_id=test_account_id,
        snapshot_date=date(2025, 12, 15),
        balance_current=Decimal("5000.00"),
        balance_available=Decimal("4800.00"),
    )

    assert snapshot.account_id == test_account_id
    assert snapshot.snapshot_date == date(2025, 12, 15)
    assert snapshot.balance_current == Decimal("5000.00")
    assert snapshot.balance_available == Decimal("4800.00")


async def test_upsert_updates_existing_snapshot(db_session):
    """Test that upsert updates an existing snapshot for same account+date."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    repo = AccountBalanceSnapshotRepo(session)

    # First insert
    await repo.upsert(
        account_id=test_account_id,
        snapshot_date=date(2025, 12, 15),
        balance_current=Decimal("5000.00"),
        balance_available=Decimal("4800.00"),
    )

    # Second insert with same date but different values
    updated = await repo.upsert(
        account_id=test_account_id,
        snapshot_date=date(2025, 12, 15),
        balance_current=Decimal("5500.00"),
        balance_available=Decimal("5300.00"),
    )

    assert updated.balance_current == Decimal("5500.00")
    assert updated.balance_available == Decimal("5300.00")

    # Verify only one record exists
    result = await session.execute(
        select(func.count())
        .select_from(AccountBalanceSnapshot)
        .where(
            AccountBalanceSnapshot.account_id == test_account_id,
            AccountBalanceSnapshot.snapshot_date == date(2025, 12, 15),
        )
    )
    count = result.scalar_one()
    assert count == 1


async def test_get_for_date_range_returns_snapshots(db_session):
    """Test that get_for_date_range returns snapshots in date order."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    repo = AccountBalanceSnapshotRepo(session)

    # Create snapshots for Dec 1, 15, 31
    await repo.upsert(
        test_account_id, date(2025, 12, 1), Decimal("10000"), Decimal("9800")
    )
    await repo.upsert(
        test_account_id, date(2025, 12, 15), Decimal("8000"), Decimal("7800")
    )
    await repo.upsert(
        test_account_id, date(2025, 12, 31), Decimal("6000"), Decimal("5800")
    )

    # Query December range
    snapshots = await repo.get_for_date_range(
        account_id=test_account_id,
        start_date=date(2025, 12, 1),
        end_date=date(2025, 12, 31),
    )

    assert len(snapshots) == 3
    assert snapshots[0].snapshot_date == date(2025, 12, 1)
    assert snapshots[1].snapshot_date == date(2025, 12, 15)
    assert snapshots[2].snapshot_date == date(2025, 12, 31)
    assert snapshots[0].balance_current == Decimal("10000")


async def test_unique_constraint_enforced(db_session):
    """Test that database enforces unique constraint on (account_id, snapshot_date)."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    # Insert first snapshot directly via raw SQL to bypass upsert
    await conn.execute(
        text("""
            INSERT INTO account_balance_snapshots
            (id, account_id, snapshot_date, balance_current, created_at)
            VALUES (
                gen_random_uuid(),
                :account_id,
                :snapshot_date,
                :balance_current,
                NOW()
            )
        """),
        {
            "account_id": test_account_id,
            "snapshot_date": date(2025, 12, 15),
            "balance_current": Decimal("5000"),
        },
    )

    # Try to insert duplicate
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("""
                INSERT INTO account_balance_snapshots
                (id, account_id, snapshot_date, balance_current, created_at)
                VALUES (
                    gen_random_uuid(),
                    :account_id,
                    :snapshot_date,
                    :balance_current,
                    NOW()
                )
            """),
            {
                "account_id": test_account_id,
                "snapshot_date": date(2025, 12, 15),
                "balance_current": Decimal("6000"),
            },
        )
