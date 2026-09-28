"""Tests for the follow-on financial-table RLS migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

EXPECTED_TABLES = (
    "credit_liabilities",
    "credit_liability_aprs",
    "anticipated_items",
    "monthly_snapshots",
    "snapshot_line_items",
    "snapshot_credit_cards",
    "loan_details",
    "account_balance_snapshots",
    "category_budgets",
    "reimbursement_links",
    "funding_sources",
)


def _load_migration():
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_07_30_0000_enable_rls_on_remaining_financial_tables.py"
    )
    spec = importlib.util.spec_from_file_location(
        "remaining_financial_rls", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_precedes_cleanup_and_covers_remaining_financial_tables():
    migration = _load_migration()

    assert migration.revision == "a38d91f0c4e2"
    assert migration.down_revision == "5db7aa663bb5"
    assert migration.TABLES == EXPECTED_TABLES


def test_upgrade_and_downgrade_only_toggle_rls():
    migration = _load_migration()
    executed = []
    migration.op = SimpleNamespace(execute=executed.append)

    migration.upgrade()
    assert executed == [
        f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'
        for table in EXPECTED_TABLES
    ]

    executed.clear()
    migration.downgrade()
    assert executed == [
        f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY'
        for table in EXPECTED_TABLES
    ]
