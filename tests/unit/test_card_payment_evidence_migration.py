"""Tests for card-payment evidence migration."""

import importlib.util
from pathlib import Path
from types import SimpleNamespace


def _load_migration():
    path = (
        Path(__file__).parents[2]
        / "alembic"
        / "versions"
        / "2026_09_15_0000_add_card_payment_evidence.py"
    )
    spec = importlib.util.spec_from_file_location("card_payment_evidence", path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_upgrade_binds_checking_evidence_to_a_transaction() -> None:
    migration = _load_migration()
    calls = []
    migration.op = SimpleNamespace(
        add_column=lambda *args, **kwargs: calls.append(("add_column", args, kwargs)),
        create_foreign_key=lambda *args, **kwargs: calls.append(
            ("create_foreign_key", args, kwargs)
        ),
        create_check_constraint=lambda *args, **kwargs: calls.append(
            ("create_check_constraint", args, kwargs)
        ),
    )

    migration.upgrade()

    assert migration.down_revision == "e7b4c2d91a60"
    added = [
        args[1].name for operation, args, _kwargs in calls if operation == "add_column"
    ]
    assert added == [
        "actual_payment_source",
        "actual_payment_transaction_id",
        "actual_payment_note",
    ]
    foreign_key = next(
        (args, kwargs)
        for operation, args, kwargs in calls
        if operation == "create_foreign_key"
    )
    assert foreign_key[0][2:] == (
        "transactions",
        ["actual_payment_transaction_id"],
        ["id"],
    )
    assert foreign_key[1]["ondelete"] == "RESTRICT"
    constraint = next(
        args
        for operation, args, _kwargs in calls
        if operation == "create_check_constraint"
    )
    assert "actual_payment_transaction_id IS NOT NULL" in constraint[2]
    assert "actual_payment_note" in constraint[2]
