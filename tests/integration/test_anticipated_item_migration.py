"""Integration tests for anticipated_items schema migration."""

import pytest
from sqlalchemy import inspect

from budget_me.db.engine import get_engine


@pytest.mark.asyncio
async def test_migration_adds_frequency_column():
    """Verify frequency column exists on anticipated_items after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("anticipated_items")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        assert "frequency" in columns
        assert str(columns["frequency"]["type"]) in ["VARCHAR", "VARCHAR(20)"]
        assert columns["frequency"]["nullable"] is False
        # Check that default is set
        assert columns["frequency"]["default"] is not None or "monthly" in str(
            columns["frequency"]
        )


@pytest.mark.asyncio
async def test_migration_adds_date_columns():
    """Verify start_month and end_month columns exist after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("anticipated_items")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        # Check start_month
        assert "start_month" in columns
        assert str(columns["start_month"]["type"]) in ["VARCHAR", "VARCHAR(7)"]
        assert columns["start_month"]["nullable"] is True

        # Check end_month
        assert "end_month" in columns
        assert str(columns["end_month"]["type"]) in ["VARCHAR", "VARCHAR(7)"]
        assert columns["end_month"]["nullable"] is True
