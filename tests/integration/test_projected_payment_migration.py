"""Integration tests for projected_monthly_payment migration."""

import pytest
from sqlalchemy import inspect

from budget_me.db.engine import get_engine


@pytest.mark.asyncio
async def test_migration_adds_projected_monthly_payment_column():
    """Verify projected_monthly_payment column exists on accounts after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {col["name"]: col for col in inspector.get_columns("accounts")}
            return columns

        columns = await conn.run_sync(_inspect_table)

        assert "projected_monthly_payment" in columns
        assert "NUMERIC" in str(columns["projected_monthly_payment"]["type"])
        assert columns["projected_monthly_payment"]["nullable"] is True
