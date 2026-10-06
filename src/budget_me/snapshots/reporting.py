"""Read-only reporting for immutable snapshot reconciliation receipts."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from budget_me.db.models.account import Account
from budget_me.db.models.monthly_snapshot import MonthlySnapshot
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.snapshot_reconciliation import (
    SnapshotReconciliationRun,
    SnapshotTransactionAllocation,
    SnapshotTransactionResolution,
)
from budget_me.db.models.transaction import Transaction
from budget_me.snapshots.reconciliation import ReconciliationTotals

_ZERO = Decimal("0.00")
_FLOW_TYPES = (
    "income",
    "expense",
    "transfer_in",
    "transfer_out",
    "reimbursement_in",
    "reimbursement_out",
    "card_payment",
)


@dataclass(frozen=True)
class ReconciledPlanMatch:
    """One portion of an actual allocation matched to a planned line item."""

    name: str
    amount: Decimal


@dataclass(frozen=True)
class ReconciledActualRow:
    """One transaction allocation or authorized non-transaction adjustment."""

    flow_type: str
    amount: Decimal
    category: str | None
    transaction_date: date | None
    description: str
    account_id: str
    account_name: str
    source_kind: str
    transaction_id: UUID | None = None
    allocation_index: int | None = None
    plan_matches: tuple[ReconciledPlanMatch, ...] = ()
    note: str | None = None


@dataclass(frozen=True)
class ReconciledActualReport:
    """Receipt-backed actual detail for one monthly snapshot."""

    year_month: str
    account_id: str
    run_id: UUID
    version: int
    reconciled_at: datetime
    totals: ReconciliationTotals
    rows: tuple[ReconciledActualRow, ...]

    def rows_for(self, flow_type: str) -> tuple[ReconciledActualRow, ...]:
        """Return rows for one normalized cash-flow type."""
        return tuple(row for row in self.rows if row.flow_type == flow_type)


def _run_totals(run: SnapshotReconciliationRun) -> ReconciliationTotals:
    return ReconciliationTotals(
        income_total=run.income_total,
        expense_total=run.expense_total,
        transfer_in_total=run.transfer_in_total,
        transfer_out_total=run.transfer_out_total,
        reimbursement_in_total=run.reimbursement_in_total,
        reimbursement_out_total=run.reimbursement_out_total,
        credit_card_total=run.credit_card_total,
        net=run.net,
    )


def _expected_flow_totals(run: SnapshotReconciliationRun) -> dict[str, Decimal]:
    return {
        "income": run.income_total,
        "expense": run.expense_total,
        "transfer_in": run.transfer_in_total,
        "transfer_out": run.transfer_out_total,
        "reimbursement_in": run.reimbursement_in_total,
        "reimbursement_out": run.reimbursement_out_total,
        "card_payment": run.credit_card_total,
    }


def _account_label(account: Account | None, account_id: str) -> str:
    if account is None:
        return account_id
    return account.display_name or account.name


def _transaction_description(transaction: Transaction | None) -> str:
    if transaction is None:
        return "Source transaction unavailable"
    return transaction.merchant_name or transaction.name


def _assemble_report(
    run: SnapshotReconciliationRun,
    snapshot: MonthlySnapshot,
    *,
    transactions_by_id: Mapping[UUID, Transaction],
    accounts_by_id: Mapping[str, Account],
    line_items_by_id: Mapping[UUID, SnapshotLineItem],
) -> ReconciledActualReport:
    """Build and cross-check display rows from one immutable receipt."""
    line_resolutions_by_id = {
        resolution.id: resolution for resolution in run.line_item_resolutions
    }
    rows: list[ReconciledActualRow] = []

    for resolution in run.transaction_resolutions:
        transaction = transactions_by_id.get(resolution.transaction_id)
        account = accounts_by_id.get(resolution.account_id)
        for allocation in resolution.allocations:
            plan_matches: list[ReconciledPlanMatch] = []
            for match in allocation.line_item_matches:
                line_resolution = line_resolutions_by_id.get(match.resolution_id)
                line_item = (
                    line_items_by_id.get(line_resolution.line_item_id)
                    if line_resolution is not None
                    else None
                )
                plan_matches.append(
                    ReconciledPlanMatch(
                        name=(
                            line_item.name
                            if line_item is not None
                            else "Unavailable planned item"
                        ),
                        amount=match.amount,
                    )
                )
            rows.append(
                ReconciledActualRow(
                    flow_type=allocation.flow_type,
                    amount=allocation.amount,
                    category=allocation.category,
                    transaction_date=resolution.transaction_date,
                    description=_transaction_description(transaction),
                    account_id=resolution.account_id,
                    account_name=_account_label(account, resolution.account_id),
                    source_kind="transaction",
                    transaction_id=resolution.transaction_id,
                    allocation_index=allocation.allocation_index,
                    plan_matches=tuple(
                        sorted(
                            plan_matches,
                            key=lambda value: (value.name.casefold(), value.amount),
                        )
                    ),
                )
            )

    snapshot_account = accounts_by_id.get(snapshot.account_id or "")
    for resolution in run.line_item_resolutions:
        if (
            resolution.resolution != "adjustment"
            or resolution.adjustment_flow_type is None
            or resolution.adjustment_amount is None
        ):
            continue
        line_item = line_items_by_id.get(resolution.line_item_id)
        name = line_item.name if line_item is not None else "Authorized adjustment"
        rows.append(
            ReconciledActualRow(
                flow_type=resolution.adjustment_flow_type,
                amount=resolution.adjustment_amount,
                category=line_item.category if line_item is not None else None,
                transaction_date=None,
                description=name,
                account_id=snapshot.account_id or "",
                account_name=_account_label(
                    snapshot_account, snapshot.account_id or "Unknown account"
                ),
                source_kind="adjustment",
                plan_matches=(
                    ReconciledPlanMatch(name=name, amount=resolution.adjustment_amount),
                ),
                note=resolution.authorization_note,
            )
        )

    flow_order = {flow_type: index for index, flow_type in enumerate(_FLOW_TYPES)}
    rows.sort(
        key=lambda row: (
            flow_order[row.flow_type],
            row.transaction_date is None,
            row.transaction_date or date.max,
            row.description.casefold(),
            str(row.transaction_id or ""),
            row.allocation_index if row.allocation_index is not None else -1,
        )
    )

    calculated: defaultdict[str, Decimal] = defaultdict(lambda: _ZERO)
    for row in rows:
        calculated[row.flow_type] += row.amount
    expected = _expected_flow_totals(run)
    if any(calculated[flow_type] != amount for flow_type, amount in expected.items()):
        raise ValueError("Reconciliation detail rows do not match receipt totals")
    calculated_net = (
        calculated["income"]
        + calculated["transfer_in"]
        + calculated["reimbursement_in"]
        - calculated["expense"]
        - calculated["transfer_out"]
        - calculated["reimbursement_out"]
        - calculated["card_payment"]
    )
    if calculated_net != run.net:
        raise ValueError("Reconciliation detail rows do not match receipt net")

    return ReconciledActualReport(
        year_month=snapshot.year_month,
        account_id=snapshot.account_id or "",
        run_id=run.id,
        version=run.version,
        reconciled_at=run.reconciled_at,
        totals=_run_totals(run),
        rows=tuple(rows),
    )


def get_reconciled_actual_report(
    session: Session, year_month: str, account_id: str
) -> ReconciledActualReport | None:
    """Return the current receipt's itemized actuals, or ``None`` if absent."""
    snapshot = session.execute(
        select(MonthlySnapshot).where(
            MonthlySnapshot.year_month == year_month,
            MonthlySnapshot.account_id == account_id,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        return None

    run = session.execute(
        select(SnapshotReconciliationRun)
        .options(
            selectinload(SnapshotReconciliationRun.transaction_resolutions)
            .selectinload(SnapshotTransactionResolution.allocations)
            .selectinload(SnapshotTransactionAllocation.line_item_matches),
            selectinload(SnapshotReconciliationRun.line_item_resolutions),
        )
        .where(
            SnapshotReconciliationRun.snapshot_id == snapshot.id,
            SnapshotReconciliationRun.is_current.is_(True),
        )
    ).scalar_one_or_none()
    if run is None:
        return None

    transaction_ids = [
        resolution.transaction_id for resolution in run.transaction_resolutions
    ]
    transactions_by_id: dict[UUID, Transaction] = {}
    if transaction_ids:
        transactions_by_id = {
            transaction.id: transaction
            for transaction in session.execute(
                select(Transaction).where(Transaction.id.in_(transaction_ids))
            ).scalars()
        }

    account_ids = {resolution.account_id for resolution in run.transaction_resolutions}
    if snapshot.account_id:
        account_ids.add(snapshot.account_id)
    accounts_by_id: dict[str, Account] = {}
    if account_ids:
        accounts_by_id = {
            account.account_id: account
            for account in session.execute(
                select(Account).where(Account.account_id.in_(sorted(account_ids)))
            ).scalars()
        }

    line_item_ids = [
        resolution.line_item_id for resolution in run.line_item_resolutions
    ]
    line_items_by_id: dict[UUID, SnapshotLineItem] = {}
    if line_item_ids:
        line_items_by_id = {
            item.id: item
            for item in session.execute(
                select(SnapshotLineItem).where(SnapshotLineItem.id.in_(line_item_ids))
            ).scalars()
        }

    return _assemble_report(
        run,
        snapshot,
        transactions_by_id=transactions_by_id,
        accounts_by_id=accounts_by_id,
        line_items_by_id=line_items_by_id,
    )
