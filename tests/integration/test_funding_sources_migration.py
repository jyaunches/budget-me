"""Integration tests for funding_sources table migration."""

import pytest
from sqlalchemy import inspect

from budget_me.db.engine import get_engine


@pytest.mark.asyncio
async def test_migration_creates_funding_sources_table():
    """Verify funding_sources table exists after migration."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _check_table_exists(connection):
            inspector = inspect(connection)
            tables = inspector.get_table_names()
            return "funding_sources" in tables

        exists = await conn.run_sync(_check_table_exists)
        assert exists is True


@pytest.mark.asyncio
async def test_funding_sources_columns():
    """Verify funding_sources table has correct columns."""
    engine = get_engine()

    async with engine.connect() as conn:

        def _inspect_table(connection):
            inspector = inspect(connection)
            columns = {
                col["name"]: col for col in inspector.get_columns("funding_sources")
            }
            return columns

        columns = await conn.run_sync(_inspect_table)

        # Check all required columns exist
        assert "id" in columns
        assert "name" in columns
        assert "source_type" in columns
        assert "available_amount" in columns
        assert "notes" in columns
        assert "active" in columns
        assert "created_at" in columns
        assert "updated_at" in columns

        # Check column types
        assert str(columns["name"]["type"]) in ["VARCHAR", "VARCHAR(255)"]
        assert str(columns["source_type"]["type"]) in ["VARCHAR", "VARCHAR(30)"]
        assert "NUMERIC" in str(columns["available_amount"]["type"])
        assert str(columns["notes"]["type"]) == "TEXT"
        assert str(columns["active"]["type"]) == "BOOLEAN"

        # Check nullability
        assert columns["name"]["nullable"] is False
        assert columns["source_type"]["nullable"] is False
        assert columns["available_amount"]["nullable"] is False
        assert columns["notes"]["nullable"] is True
        assert columns["active"]["nullable"] is False
