"""Tests for receipt-backed snapshot actual-detail reporting."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import uuid4

import pytest

from budget_me.db.models.account import Account
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.snapshot_reconciliation import (
    SnapshotLineItemMatch,
    SnapshotLineItemResolution,
    SnapshotReconciliationRun,
    SnapshotTransactionAllocation,
    SnapshotTransactionResolution,
)
from budget_me.db.models.transaction import Transaction
from budget_me.snapshots.reporting import _assemble_report

NOW = datetime(2026, 9, 1, 12, 0, tzinfo=UTC)


def _receipt_graph():
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2026-08",
        account_id="checking-1",
        status=SnapshotStatus.OPEN,
    )
    run = SnapshotReconciliationRun(
        id=uuid4(),
        snapshot_id=snapshot.id,
        version=1,
        is_current=True,
        manifest_hash="a" * 64,
        input_hash="b" * 64,
        reconciled_at=NOW,
        income_total=Decimal("5.00"),
        expense_total=Decimal("25.00"),
        transfer_in_total=Decimal("0.00"),
        transfer_out_total=Decimal("15.00"),
        reimbursement_in_total=Decimal("0.00"),
        reimbursement_out_total=Decimal("0.00"),
        credit_card_total=Decimal("0.00"),
        net=Decimal("-35.00"),
        posted_transaction_count=1,
        allocation_count=2,
        line_item_count=2,
        has_remaining_items=False,
    )
    transaction_id = uuid4()
    transaction_resolution = SnapshotTransactionResolution(
        id=uuid4(),
        run_id=run.id,
        transaction_id=transaction_id,
        fingerprint="c" * 64,
        account_id="checking-1",
        transaction_date=date(2026, 8, 15),
        signed_amount=Decimal("40.00"),
        currency="USD",
        source_updated_at=NOW,
        classification_source="manifest",
        manual_locked=True,
    )
    expense_allocation = SnapshotTransactionAllocation(
        id=uuid4(),
        resolution_id=transaction_resolution.id,
        allocation_index=0,
        flow_type="expense",
        amount=Decimal("25.00"),
        category="groceries",
    )
    transfer_allocation = SnapshotTransactionAllocation(
        id=uuid4(),
        resolution_id=transaction_resolution.id,
        allocation_index=1,
        flow_type="transfer_out",
        amount=Decimal("15.00"),
        category="transfer",
    )
    planned_expense = SnapshotLineItem(
        id=uuid4(),
        snapshot_id=snapshot.id,
        item_type="expense",
        name="Planned groceries",
        amount=Decimal("25.00"),
        category="groceries",
        is_one_time=False,
        skipped=False,
    )
    expense_resolution = SnapshotLineItemResolution(
        id=uuid4(),
        run_id=run.id,
        line_item_id=planned_expense.id,
        resolution="fulfilled",
        remaining_amount=Decimal("0.00"),
    )
    match = SnapshotLineItemMatch(
        id=uuid4(),
        resolution_id=expense_resolution.id,
        allocation_id=expense_allocation.id,
        amount=Decimal("25.00"),
    )
    adjustment_item = SnapshotLineItem(
        id=uuid4(),
        snapshot_id=snapshot.id,
        item_type="income",
        name="Authorized interest adjustment",
        amount=Decimal("5.00"),
        category="interest",
        is_one_time=True,
        skipped=False,
    )
    adjustment_resolution = SnapshotLineItemResolution(
        id=uuid4(),
        run_id=run.id,
        line_item_id=adjustment_item.id,
        resolution="adjustment",
        remaining_amount=Decimal("0.00"),
        adjustment_flow_type="income",
        adjustment_amount=Decimal("5.00"),
        authorization_note="Approved statement interest.",
    )

    expense_allocation.line_item_matches = [match]
    transaction_resolution.allocations = [expense_allocation, transfer_allocation]
    run.transaction_resolutions = [transaction_resolution]
    run.line_item_resolutions = [expense_resolution, adjustment_resolution]

    account = Account(
        id=uuid4(),
        plaid_item_id=uuid4(),
        account_id="checking-1",
        name="Checking",
        display_name="Primary Checking",
        type="depository",
    )
    transaction = Transaction(
        id=transaction_id,
        plaid_transaction_id="txn-1",
        plaid_item_id=uuid4(),
        account_id="checking-1",
        date=date(2026, 8, 15),
        amount=Decimal("40.00"),
        name="Grocery and transfer",
        merchant_name="Example Merchant",
        pending=False,
        reviewed=True,
        budget_category="groceries",
    )
    return {
        "snapshot": snapshot,
        "run": run,
        "transaction": transaction,
        "account": account,
        "items": [planned_expense, adjustment_item],
    }


def test_assemble_report_exposes_allocations_matches_and_adjustments() -> None:
    graph = _receipt_graph()

    report = _assemble_report(
        graph["run"],
        graph["snapshot"],
        transactions_by_id={graph["transaction"].id: graph["transaction"]},
        accounts_by_id={graph["account"].account_id: graph["account"]},
        line_items_by_id={item.id: item for item in graph["items"]},
    )

    expense = report.rows_for("expense")[0]
    assert expense.description == "Example Merchant"
    assert expense.account_name == "Primary Checking"
    assert expense.category == "groceries"
    assert expense.plan_matches[0].name == "Planned groceries"
    assert expense.plan_matches[0].amount == Decimal("25.00")

    transfer = report.rows_for("transfer_out")[0]
    assert transfer.amount == Decimal("15.00")
    assert transfer.category == "transfer"

    adjustment = report.rows_for("income")[0]
    assert adjustment.source_kind == "adjustment"
    assert adjustment.transaction_date is None
    assert adjustment.note == "Approved statement interest."
    assert report.totals.net == Decimal("-35.00")


def test_assemble_report_preserves_copied_facts_when_transaction_is_missing() -> None:
    graph = _receipt_graph()

    report = _assemble_report(
        graph["run"],
        graph["snapshot"],
        transactions_by_id={},
        accounts_by_id={graph["account"].account_id: graph["account"]},
        line_items_by_id={item.id: item for item in graph["items"]},
    )

    assert report.rows_for("expense")[0].description == "Source transaction unavailable"
    assert report.rows_for("expense")[0].transaction_date == date(2026, 8, 15)


def test_assemble_report_rejects_detail_totals_that_do_not_match_receipt() -> None:
    graph = _receipt_graph()
    graph["run"].expense_total = Decimal("24.99")

    with pytest.raises(ValueError, match="detail rows do not match receipt totals"):
        _assemble_report(
            graph["run"],
            graph["snapshot"],
            transactions_by_id={graph["transaction"].id: graph["transaction"]},
            accounts_by_id={graph["account"].account_id: graph["account"]},
            line_items_by_id={item.id: item for item in graph["items"]},
        )
