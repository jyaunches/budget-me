"""Tests for the persistent categorization-rules migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import CheckConstraint, Column, UniqueConstraint


def _load_migration():
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_08_02_0000_add_categorization_rules.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_categorization_rules", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_migration_follows_current_head_and_enables_rls_without_policies():
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        create_table=lambda *args, **kwargs: calls.append(
            ("create_table", args, kwargs)
        ),
        create_index=lambda *args, **kwargs: calls.append(
            ("create_index", args, kwargs)
        ),
        execute=lambda statement: calls.append(("execute", statement)),
    )

    migration.upgrade()

    assert migration.revision == "c21f6a9d8e34"
    assert migration.down_revision == "d4a7e9c2f610"
    assert [call[0] for call in calls] == [
        "create_table",
        "create_index",
        "execute",
    ]
    assert calls[-1] == ("execute", migration.ENABLE_RLS_SQL)
    assert "ENABLE ROW LEVEL SECURITY" in migration.ENABLE_RLS_SQL
    assert "POLICY" not in migration.ENABLE_RLS_SQL


def test_migration_schema_matches_model_constraints_and_index():
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        create_table=lambda *args, **kwargs: calls.append(
            ("create_table", args, kwargs)
        ),
        create_index=lambda *args, **kwargs: calls.append(
            ("create_index", args, kwargs)
        ),
        execute=lambda statement: None,
    )

    migration.upgrade()

    _, table_args, _ = calls[0]
    assert table_args[0] == migration.TABLE_NAME
    columns = {item.name: item for item in table_args[1:] if isinstance(item, Column)}
    assert set(columns) == {
        "id",
        "rule_type",
        "pattern",
        "normalized_pattern",
        "category",
        "reimbursement_note",
        "enabled",
        "source",
        "confidence",
        "created_at",
        "updated_at",
    }
    assert str(columns["normalized_pattern"].computed.sqltext) == (
        "lower(btrim(pattern))"
    )
    assert columns["normalized_pattern"].computed.persisted is True

    constraints = {
        item.name: item
        for item in table_args[1:]
        if isinstance(item, (CheckConstraint, UniqueConstraint))
    }
    assert {
        "uq_categorization_rules_type_pattern",
        "ck_categorization_rules_pattern_length",
        "ck_categorization_rules_type",
        "ck_categorization_rules_source",
        "ck_categorization_rules_confidence",
        "ck_categorization_rules_payload",
    }.issubset(constraints)

    _, index_args, index_kwargs = calls[1]
    assert index_args == (
        "ix_categorization_rules_enabled_type",
        migration.TABLE_NAME,
        ["enabled", "rule_type"],
    )
    assert index_kwargs == {"unique": False}


def test_downgrade_drops_index_before_table():
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        drop_index=lambda *args, **kwargs: calls.append(("drop_index", args, kwargs)),
        drop_table=lambda *args, **kwargs: calls.append(("drop_table", args, kwargs)),
    )

    migration.downgrade()

    assert calls == [
        (
            "drop_index",
            ("ix_categorization_rules_enabled_type",),
            {"table_name": migration.TABLE_NAME},
        ),
        ("drop_table", (migration.TABLE_NAME,), {}),
    ]
