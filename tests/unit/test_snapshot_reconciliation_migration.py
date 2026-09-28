"""Tests for the immutable snapshot reconciliation ledger migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from sqlalchemy import CheckConstraint, Column, ForeignKeyConstraint


def _load_migration():
    migration_path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_08_10_0000_add_snapshot_reconciliation_ledger.py"
    )
    spec = importlib.util.spec_from_file_location(
        "add_snapshot_reconciliation_ledger", migration_path
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _upgrade_calls(migration):
    calls = []
    migration.op = SimpleNamespace(
        add_column=lambda *args, **kwargs: calls.append(("add_column", args, kwargs)),
        create_table=lambda *args, **kwargs: calls.append(
            ("create_table", args, kwargs)
        ),
        create_index=lambda *args, **kwargs: calls.append(
            ("create_index", args, kwargs)
        ),
        execute=lambda statement: calls.append(("execute", (statement,), {})),
    )
    migration.upgrade()
    return calls


def _table_args(calls, table_name):
    return next(
        args
        for operation, args, _kwargs in calls
        if operation == "create_table" and args[0] == table_name
    )


def _constraint_sql(table_args, name):
    return str(
        next(
            item.sqltext
            for item in table_args[1:]
            if isinstance(item, CheckConstraint) and item.name == name
        )
    )


def test_migration_follows_head_creates_ledger_in_order_and_enables_rls():
    migration = _load_migration()
    calls = _upgrade_calls(migration)

    assert migration.revision == "e7b4c2d91a60"
    assert migration.down_revision == "c21f6a9d8e34"
    assert [
        args[0] for operation, args, _kwargs in calls if operation == "create_table"
    ] == list(migration.LEDGER_TABLES)

    added_columns = [
        (args[0], args[1].name)
        for operation, args, _kwargs in calls
        if operation == "add_column"
    ]
    assert added_columns == [
        ("monthly_snapshots", "reimbursement_in_total"),
        ("monthly_snapshots", "reimbursement_out_total"),
    ]

    statements = [
        str(args[0]) for operation, args, _kwargs in calls if operation == "execute"
    ]
    for statement in migration.ENABLE_RLS_SQL:
        assert statement in statements
    assert all("ENABLE ROW LEVEL SECURITY" in sql for sql in migration.ENABLE_RLS_SQL)
    assert "POLICY" not in "\n".join(statements).upper()


def test_migration_keeps_copied_source_identifiers_independent():
    migration = _load_migration()
    calls = _upgrade_calls(migration)

    transaction_args = _table_args(calls, migration.TRANSACTION_RESOLUTIONS_TABLE)
    transaction_columns = {
        item.name: item for item in transaction_args[1:] if isinstance(item, Column)
    }
    assert {
        "transaction_id",
        "fingerprint",
        "account_id",
        "transaction_date",
        "signed_amount",
        "currency",
        "source_updated_at",
        "classification_source",
        "manual_locked",
        "pair_group_id",
    }.issubset(transaction_columns)

    transaction_targets = {
        element.target_fullname
        for item in transaction_args[1:]
        if isinstance(item, ForeignKeyConstraint)
        for element in item.elements
    }
    assert transaction_targets == {"snapshot_reconciliation_runs.id"}

    line_args = _table_args(calls, migration.LINE_ITEM_RESOLUTIONS_TABLE)
    line_targets = {
        element.target_fullname
        for item in line_args[1:]
        if isinstance(item, ForeignKeyConstraint)
        for element in item.elements
    }
    assert line_targets == {"snapshot_reconciliation_runs.id"}


def test_migration_allows_allocation_card_payments_but_not_adjustment_card_payments():
    migration = _load_migration()
    calls = _upgrade_calls(migration)

    allocation_args = _table_args(calls, migration.TRANSACTION_ALLOCATIONS_TABLE)
    allocation_flow = _constraint_sql(
        allocation_args, "ck_snapshot_transaction_allocations_flow_type"
    )
    assert "card_payment" in allocation_flow
    assert "excluded" not in allocation_flow

    line_args = _table_args(calls, migration.LINE_ITEM_RESOLUTIONS_TABLE)
    adjustment_flow = _constraint_sql(
        line_args, "ck_snapshot_line_item_resolutions_adjustment_flow_type"
    )
    assert "reimbursement_in" in adjustment_flow
    assert "reimbursement_out" in adjustment_flow
    assert "card_payment" not in adjustment_flow
    assert "excluded" not in adjustment_flow


def test_migration_defers_exact_allocation_sum_and_enforces_same_run_matches():
    migration = _load_migration()
    calls = _upgrade_calls(migration)
    statements = "\n".join(
        str(args[0]) for operation, args, _kwargs in calls if operation == "execute"
    )

    assert statements.count("DEFERRABLE INITIALLY DEFERRED") == 2
    assert "COALESCE" in statements
    assert "SUM(allocation.amount)" in statements
    assert "abs(resolution.signed_amount)" in statements
    assert "line_resolution.run_id = transaction_resolution.run_id" in statements
    assert "line-item matches must reference parents from the same run" in statements


def test_migration_makes_inserted_runs_and_children_immutable():
    migration = _load_migration()
    calls = _upgrade_calls(migration)
    statements = "\n".join(
        str(args[0]) for operation, args, _kwargs in calls if operation == "execute"
    )

    run_function = migration.CREATE_RUN_IMMUTABILITY_FUNCTION_SQL
    assert "OLD.is_current IS TRUE" in run_function
    assert "NEW.is_current IS FALSE" in run_function
    assert "NEW.updated_at := OLD.updated_at" in run_function
    assert "NEW IS NOT DISTINCT FROM OLD" in run_function
    assert f"BEFORE UPDATE OR DELETE ON public.{migration.RUNS_TABLE}" in statements

    for table_name, trigger_name in migration.CHILD_IMMUTABILITY_TRIGGERS:
        assert trigger_name in statements
        assert f"BEFORE UPDATE OR DELETE ON public.{table_name}" in statements
    assert "ledger rows are immutable after insert" in statements


def test_downgrade_drops_ledger_in_reverse_dependency_order():
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        execute=lambda statement: calls.append(("execute", (statement,), {})),
        drop_index=lambda *args, **kwargs: calls.append(("drop_index", args, kwargs)),
        drop_table=lambda *args, **kwargs: calls.append(("drop_table", args, kwargs)),
        drop_column=lambda *args, **kwargs: calls.append(("drop_column", args, kwargs)),
    )

    migration.downgrade()

    assert [
        args[0] for operation, args, _kwargs in calls if operation == "drop_table"
    ] == list(reversed(migration.LEDGER_TABLES))
    assert [
        (args[0], args[1])
        for operation, args, _kwargs in calls
        if operation == "drop_column"
    ] == [
        ("monthly_snapshots", "reimbursement_out_total"),
        ("monthly_snapshots", "reimbursement_in_total"),
    ]

    statements = "\n".join(
        str(args[0]) for operation, args, _kwargs in calls if operation == "execute"
    )
    assert migration.RUN_IMMUTABILITY_TRIGGER_NAME in statements
    assert migration.RUN_IMMUTABILITY_FUNCTION_NAME in statements
    assert migration.CHILD_IMMUTABILITY_FUNCTION_NAME in statements
    for _table_name, trigger_name in migration.CHILD_IMMUTABILITY_TRIGGERS:
        assert trigger_name in statements
