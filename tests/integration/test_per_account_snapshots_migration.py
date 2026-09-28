"""Integration tests for per-account snapshots database migration."""

from uuid import uuid4

import pytest
from sqlalchemy import inspect, text

from budget_me.db.engine import get_engine


@pytest.mark.asyncio
async def test_migration_adds_account_id_to_monthly_snapshots():
    """Verify account_id column exists on monthly_snapshots after migration."""
    engine = get_engine()

    async with engine.connect() as conn:
        # Inspect table (read-only, no transaction needed)
        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("monthly_snapshots")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        assert "account_id" in columns
        # Column should be VARCHAR/String type
        assert str(columns["account_id"]["type"]) in ["VARCHAR", "VARCHAR(255)"]
        assert columns["account_id"]["nullable"] is True


@pytest.mark.asyncio
async def test_migration_adds_account_id_to_anticipated_items():
    """Verify account_id column exists on anticipated_items after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("anticipated_items")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        assert "account_id" in columns
        assert str(columns["account_id"]["type"]) in ["VARCHAR", "VARCHAR(255)"]
        assert columns["account_id"]["nullable"] is True


@pytest.mark.asyncio
async def test_migration_adds_paying_account_id_to_accounts():
    """Verify paying_account_id column exists on accounts after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {col["name"]: col for col in inspector.get_columns("accounts")}
            return columns

        columns = await conn.run_sync(_inspect_table)

        assert "paying_account_id" in columns
        assert str(columns["paying_account_id"]["type"]) in ["VARCHAR", "VARCHAR(255)"]
        assert columns["paying_account_id"]["nullable"] is True


@pytest.mark.asyncio
async def test_monthly_snapshot_unique_constraint_includes_account(db_session):
    """Verify unique constraint allows different accounts for same month."""
    session, conn = db_session

    # Create test plaid item first
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
    plaid_item_id = plaid_item_result.scalar()

    acc1_id = f"test-acc-{uuid4()}"
    acc2_id = f"test-acc-{uuid4()}"

    # Create two test accounts
    await conn.execute(
        text("""
            INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                :plaid_item_id,
                :account_id,
                'Test Account 1',
                'depository',
                NOW(),
                NOW()
            )
        """),
        {"plaid_item_id": plaid_item_id, "account_id": acc1_id},
    )

    await conn.execute(
        text("""
            INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                :plaid_item_id,
                :account_id,
                'Test Account 2',
                'depository',
                NOW(),
                NOW()
            )
        """),
        {"plaid_item_id": plaid_item_id, "account_id": acc2_id},
    )

    # Create snapshots for same month, different accounts - should succeed
    await conn.execute(
        text("""
            INSERT INTO monthly_snapshots (id, year_month, account_id, status, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                '2025-11',
                :account_id,
                'open',
                NOW(),
                NOW()
            )
        """),
        {"account_id": acc1_id},
    )

    await conn.execute(
        text("""
            INSERT INTO monthly_snapshots (id, year_month, account_id, status, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                '2025-11',
                :account_id,
                'open',
                NOW(),
                NOW()
            )
        """),
        {"account_id": acc2_id},
    )

    # Query to verify both exist within this transaction
    result = await conn.execute(
        text(
            "SELECT COUNT(*) FROM monthly_snapshots WHERE year_month = '2025-11' AND account_id IN (:acc1, :acc2)"
        ),
        {"acc1": acc1_id, "acc2": acc2_id},
    )
    count = result.scalar()
    assert count == 2


@pytest.mark.asyncio
async def test_monthly_snapshot_same_month_same_account_fails(db_session):
    """Verify unique constraint prevents duplicate snapshots for same account+month."""
    session, conn = db_session

    # Create test plaid item first
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
    plaid_item_id = plaid_item_result.scalar()

    acc_id = f"test-acc-{uuid4()}"

    # Create test account
    await conn.execute(
        text("""
            INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                :plaid_item_id,
                :account_id,
                'Test Account Unique',
                'depository',
                NOW(),
                NOW()
            )
        """),
        {"plaid_item_id": plaid_item_id, "account_id": acc_id},
    )

    # Create first snapshot
    await conn.execute(
        text("""
            INSERT INTO monthly_snapshots (id, year_month, account_id, status, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                '2025-10',
                :account_id,
                'open',
                NOW(),
                NOW()
            )
        """),
        {"account_id": acc_id},
    )

    # Try to create duplicate - should fail
    with pytest.raises(Exception) as exc_info:
        await conn.execute(
            text("""
                INSERT INTO monthly_snapshots (id, year_month, account_id, status, created_at, updated_at)
                VALUES (
                    gen_random_uuid(),
                    '2025-10',
                    :account_id,
                    'open',
                    NOW(),
                    NOW()
                )
            """),
            {"account_id": acc_id},
        )

    # Should be a constraint violation
    assert (
        "unique" in str(exc_info.value).lower()
        or "duplicate" in str(exc_info.value).lower()
    )
