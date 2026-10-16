"""Migration coverage for investment financial data."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_migration():
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_10_06_0000_add_investment_data.py"
    )
    spec = importlib.util.spec_from_file_location("investment_data", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_creates_all_tables_and_enables_rls():
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        create_table=lambda *args, **kwargs: calls.append(
            ("create_table", args, kwargs)
        ),
        create_index=lambda *args, **kwargs: calls.append(
            ("create_index", args, kwargs)
        ),
        execute=lambda statement: calls.append(("execute", statement, {})),
    )

    migration.upgrade()

    created = [args[0] for operation, args, _ in calls if operation == "create_table"]
    assert created == list(migration.TABLES)
    statements = [args for operation, args, _ in calls if operation == "execute"]
    assert statements == [
        f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY'
        for table in migration.TABLES
    ]
    assert migration.down_revision == "f5b6a7c8d901"


def test_downgrade_drops_in_reverse_dependency_order():
    migration = _load_migration()
    dropped = []
    migration.op = SimpleNamespace(drop_table=dropped.append)

    migration.downgrade()

    assert dropped == list(reversed(migration.TABLES))
