"""Metadata tests for the immutable snapshot reconciliation ledger."""

from decimal import Decimal

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from budget_me.db.models import (
    MonthlySnapshot,
    SnapshotLineItemMatch,
    SnapshotLineItemResolution,
    SnapshotReconciliationRun,
    SnapshotTransactionAllocation,
    SnapshotTransactionResolution,
)


def _named_constraints(model, constraint_type):
    return {
        constraint.name: constraint
        for constraint in model.__table__.constraints
        if isinstance(constraint, constraint_type) and constraint.name is not None
    }


def _check_sql(model):
    return {
        name: str(constraint.sqltext)
        for name, constraint in _named_constraints(model, CheckConstraint).items()
    }


def test_monthly_snapshot_and_run_record_all_reconciliation_totals():
    for name in ("reimbursement_in_total", "reimbursement_out_total"):
        column = MonthlySnapshot.__table__.c[name]
        assert column.nullable is False
        assert column.default.arg == Decimal("0.00")
        assert str(column.server_default.arg) == "0.00"

    table = SnapshotReconciliationRun.__table__
    assert table.name == "snapshot_reconciliation_runs"
    assert set(table.c.keys()) == {
        "id",
        "snapshot_id",
        "version",
        "is_current",
        "manifest_hash",
        "input_hash",
        "reconciled_at",
        "income_total",
        "expense_total",
        "transfer_in_total",
        "transfer_out_total",
        "reimbursement_in_total",
        "reimbursement_out_total",
        "credit_card_total",
        "net",
        "posted_transaction_count",
        "allocation_count",
        "line_item_count",
        "has_remaining_items",
        "created_at",
        "updated_at",
    }
    snapshot_fk = next(iter(table.c.snapshot_id.foreign_keys))
    assert snapshot_fk.target_fullname == "monthly_snapshots.id"
    assert snapshot_fk.ondelete == "CASCADE"

    checks = _check_sql(SnapshotReconciliationRun)
    assert (
        "reimbursement_in_total >= 0"
        in checks["ck_snapshot_reconciliation_runs_nonnegative_totals"]
    )
    assert (
        "reimbursement_out_total >= 0"
        in checks["ck_snapshot_reconciliation_runs_nonnegative_totals"]
    )
    assert checks["ck_snapshot_reconciliation_runs_net"] == (
        "net = income_total + transfer_in_total + reimbursement_in_total "
        "- expense_total - transfer_out_total - reimbursement_out_total "
        "- credit_card_total"
    )


def test_run_has_one_partial_current_version_per_snapshot():
    indexes = {
        index.name: index
        for index in SnapshotReconciliationRun.__table__.indexes
        if isinstance(index, Index)
    }
    current = indexes["uq_snapshot_reconciliation_runs_current_snapshot"]
    assert current.unique is True
    assert [column.name for column in current.columns] == ["snapshot_id"]
    assert str(current.dialect_options["postgresql"]["where"]) == "is_current"


def test_transaction_resolution_copies_source_facts_without_source_foreign_keys():
    table = SnapshotTransactionResolution.__table__
    assert table.name == "snapshot_transaction_resolutions"
    assert set(table.c.keys()) == {
        "id",
        "run_id",
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
    }
    assert not table.c.transaction_id.foreign_keys
    assert not table.c.account_id.foreign_keys

    run_fk = next(iter(table.c.run_id.foreign_keys))
    assert run_fk.target_fullname == "snapshot_reconciliation_runs.id"
    assert run_fk.ondelete == "CASCADE"

    unique = _named_constraints(SnapshotTransactionResolution, UniqueConstraint)[
        "uq_snapshot_transaction_resolutions_run_transaction"
    ]
    assert [column.name for column in unique.columns] == ["run_id", "transaction_id"]
    assert (
        _check_sql(SnapshotTransactionResolution)[
            "ck_snapshot_transaction_resolutions_fingerprint"
        ]
        == "fingerprint ~ '^[0-9a-f]{64}$'"
    )


def test_allocations_are_positive_complete_flow_parts_with_stable_order():
    checks = _check_sql(SnapshotTransactionAllocation)
    flow_check = checks["ck_snapshot_transaction_allocations_flow_type"]
    for flow_type in (
        "income",
        "expense",
        "transfer_in",
        "transfer_out",
        "reimbursement_in",
        "reimbursement_out",
        "card_payment",
    ):
        assert f"'{flow_type}'" in flow_check
    assert "excluded" not in flow_check
    assert checks["ck_snapshot_transaction_allocations_amount_positive"] == (
        "amount > 0"
    )
    assert checks["ck_snapshot_transaction_allocations_index_nonnegative"] == (
        "allocation_index >= 0"
    )

    unique = _named_constraints(SnapshotTransactionAllocation, UniqueConstraint)[
        "uq_snapshot_transaction_allocations_resolution_index"
    ]
    assert [column.name for column in unique.columns] == [
        "resolution_id",
        "allocation_index",
    ]


def test_line_item_resolution_keeps_adjustments_explicit_and_not_card_payments():
    table = SnapshotLineItemResolution.__table__
    assert not table.c.line_item_id.foreign_keys

    checks = _check_sql(SnapshotLineItemResolution)
    adjustment_flow_check = checks[
        "ck_snapshot_line_item_resolutions_adjustment_flow_type"
    ]
    assert "'reimbursement_in'" in adjustment_flow_check
    assert "'reimbursement_out'" in adjustment_flow_check
    assert "card_payment" not in adjustment_flow_check
    assert "excluded" not in adjustment_flow_check

    payload_check = checks["ck_snapshot_line_item_resolutions_payload"]
    assert "resolution = 'remaining' AND remaining_amount > 0" in payload_check
    assert "resolution = 'adjustment' AND remaining_amount = 0" in payload_check
    assert "adjustment_amount > 0" in payload_check
    assert "length(btrim(authorization_note)) > 0" in payload_check


def test_line_item_match_is_positive_unique_and_cascades_from_both_parents():
    table = SnapshotLineItemMatch.__table__
    assert (
        _check_sql(SnapshotLineItemMatch)[
            "ck_snapshot_line_item_matches_amount_positive"
        ]
        == "amount > 0"
    )

    unique = _named_constraints(SnapshotLineItemMatch, UniqueConstraint)[
        "uq_snapshot_line_item_matches_resolution_allocation"
    ]
    assert [column.name for column in unique.columns] == [
        "resolution_id",
        "allocation_id",
    ]
    for column_name, target in (
        ("resolution_id", "snapshot_line_item_resolutions.id"),
        ("allocation_id", "snapshot_transaction_allocations.id"),
    ):
        foreign_key = next(iter(table.c[column_name].foreign_keys))
        assert foreign_key.target_fullname == target
        assert foreign_key.ondelete == "CASCADE"
