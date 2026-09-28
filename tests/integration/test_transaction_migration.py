"""Integration tests for budget_category database migration."""

import pytest
from sqlalchemy import inspect, text

from budget_me.db.engine import get_engine


@pytest.mark.asyncio
async def test_budget_category_migration_up():
    """Verify migration adds budget_category column to transactions table."""
    engine = get_engine()

    async with engine.connect() as conn:
        # Inspect table structure
        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("transactions")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        # Verify budget_category column exists
        assert "budget_category" in columns
        # Column should be VARCHAR(50)
        assert str(columns["budget_category"]["type"]) in ["VARCHAR", "VARCHAR(50)"]
        # Column should be nullable
        assert columns["budget_category"]["nullable"] is True


@pytest.mark.asyncio
async def test_budget_category_index_exists():
    """Verify index exists on budget_category column."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_indexes(connection):
            inspector = inspect(connection)
            indexes = inspector.get_indexes("transactions")
            return indexes

        indexes = await conn.run_sync(_inspect_indexes)

        # Find index on budget_category
        budget_category_indexes = [
            idx for idx in indexes if "budget_category" in idx.get("column_names", [])
        ]

        # Verify at least one index exists
        assert len(budget_category_indexes) > 0
        # Verify index name matches convention
        index_names = [idx["name"] for idx in budget_category_indexes]
        assert "ix_transactions_budget_category" in index_names


@pytest.mark.asyncio
async def test_existing_transactions_have_null_budget_category(db_session):
    """Verify existing transactions have NULL budget_category after migration."""
    session, conn = db_session

    # Create test plaid item first
    plaid_item_result = await conn.execute(
        text("""
            INSERT INTO plaid_items (id, user_key, item_id, access_token_enc, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                'test-user',
                'test-item-budget-cat',
                'test-access-token-encrypted',
                NOW(),
                NOW()
            )
            RETURNING id
        """)
    )
    plaid_item_id = plaid_item_result.scalar()

    # Insert a transaction without budget_category
    await conn.execute(
        text("""
            INSERT INTO transactions (
                id, plaid_transaction_id, plaid_item_id, account_id,
                date, amount, name, created_at, updated_at
            )
            VALUES (
                gen_random_uuid(),
                'test-txn-migration-check',
                :plaid_item_id,
                'test-account-123',
                '2025-01-01',
                100.00,
                'Test Transaction',
                NOW(),
                NOW()
            )
        """),
        {"plaid_item_id": plaid_item_id},
    )

    # Query the transaction
    result = await conn.execute(
        text("""
            SELECT budget_category
            FROM transactions
            WHERE plaid_transaction_id = 'test-txn-migration-check'
        """)
    )
    budget_category = result.scalar()

    # Verify budget_category is NULL
    assert budget_category is None
