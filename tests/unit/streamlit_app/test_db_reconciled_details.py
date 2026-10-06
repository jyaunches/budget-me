"""Tests for the Streamlit adapter over receipt-backed actual details."""

from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

from budget_me.snapshots.reconciliation import ReconciliationTotals
from budget_me.snapshots.reporting import ReconciledActualRow, ReconciledPlanMatch
from budget_me.streamlit_app import db


def test_get_reconciled_actual_details_returns_display_ready_receipt_rows() -> None:
    transaction_id = uuid4()
    report = SimpleNamespace(
        run_id=uuid4(),
        version=1,
        reconciled_at=datetime(2026, 9, 1, tzinfo=UTC),
        totals=ReconciliationTotals(
            income_total=Decimal("100.00"),
            expense_total=Decimal("0.00"),
            transfer_in_total=Decimal("0.00"),
            transfer_out_total=Decimal("0.00"),
            reimbursement_in_total=Decimal("0.00"),
            reimbursement_out_total=Decimal("0.00"),
            credit_card_total=Decimal("0.00"),
            net=Decimal("100.00"),
        ),
        rows=(
            ReconciledActualRow(
                flow_type="income",
                amount=Decimal("100.00"),
                category="salary",
                transaction_date=date(2026, 8, 15),
                description="Payroll",
                account_id="checking-1",
                account_name="Primary Checking",
                source_kind="transaction",
                transaction_id=transaction_id,
                allocation_index=0,
                plan_matches=(ReconciledPlanMatch("Paycheck", Decimal("100.00")),),
            ),
        ),
    )

    with patch(
        "budget_me.snapshots.reporting.get_reconciled_actual_report",
        return_value=report,
    ):
        details = db.get_reconciled_actual_details(MagicMock(), "2026-08", "checking-1")

    assert details is not None
    assert details["totals"]["income"] == 100.0
    assert details["rows"] == [
        {
            "flow_type": "income",
            "amount": 100.0,
            "category": "salary",
            "date": date(2026, 8, 15),
            "description": "Payroll",
            "account": "Primary Checking",
            "source_kind": "transaction",
            "transaction_id": str(transaction_id),
            "allocation_index": 0,
            "matched_plan": [{"name": "Paycheck", "amount": 100.0}],
            "note": None,
        }
    ]


def test_get_reconciled_actual_details_preserves_legacy_absence() -> None:
    with patch(
        "budget_me.snapshots.reporting.get_reconciled_actual_report",
        return_value=None,
    ):
        assert (
            db.get_reconciled_actual_details(MagicMock(), "2026-08", "checking-1")
            is None
        )
