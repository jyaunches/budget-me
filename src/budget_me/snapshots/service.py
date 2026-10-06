"""Read-only snapshot close previews and guarded close operations."""

from __future__ import annotations

import hashlib
import json
import uuid
from calendar import monthrange
from collections.abc import Generator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from budget_me.db.models.account import Account
from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.models.ingest_run import (
    IngestRun,
    IngestRunItem,
    IngestRunItemStatus,
    IngestRunStatus,
)
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.transaction import Transaction
from budget_me.db.sync_coordination import (
    acquire_close_coordination_lock,
    acquire_transaction_reconciliation_lock,
)
from budget_me.snapshots.card_payment_evidence import (
    actual_matches_feed_or_evidence,
    has_checking_account_marker,
)
from budget_me.snapshots.reconciliation import (
    CurrentReconciliationEvidence,
    validate_current_reconciliation,
)

RECONCILIATION_MAX_AGE = timedelta(hours=24)
_AUDIT_VERSION = 9
_ZERO = Decimal("0.00")
_CARD_PAYMENT_DETAILED = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
_LEGACY_CARD_PAYMENT_DETAILED = "Payment, Credit Card"


def _money(value: Decimal | None) -> str | None:
    """Serialize money deterministically without converting through float."""
    return None if value is None else format(value, ".2f")


def _timestamp(value: datetime | None) -> str | None:
    """Serialize timestamps deterministically in UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _as_utc(value: datetime) -> datetime:
    """Normalize a database timestamp for safe age comparisons."""
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _status_value(value: str | SnapshotStatus) -> str:
    """Return the persisted enum value instead of its Python repr."""
    return value.value if isinstance(value, SnapshotStatus) else value


def _raw_card_payment_detailed(transaction: Transaction) -> str | None:
    """Return Plaid's detailed category without trusting optional raw JSON."""
    raw = transaction.raw or {}
    personal_finance_category = raw.get("personal_finance_category")
    if not isinstance(personal_finance_category, dict):
        return None
    detailed = personal_finance_category.get("detailed")
    return detailed if isinstance(detailed, str) else None


def _is_card_payment(transaction: Transaction) -> bool:
    """Match both current and legacy card-side payment classifications."""
    return transaction.amount < _ZERO and (
        _raw_card_payment_detailed(transaction) == _CARD_PAYMENT_DETAILED
        or transaction.category_detailed
        in {_CARD_PAYMENT_DETAILED, _LEGACY_CARD_PAYMENT_DETAILED}
    )


@dataclass(frozen=True)
class SnapshotCloseTotals:
    """Actual cash-flow totals that will be frozen for a closed snapshot."""

    income_total: Decimal
    expense_total: Decimal
    transfer_in_total: Decimal
    transfer_out_total: Decimal
    credit_card_total: Decimal
    net: Decimal
    reimbursement_in_total: Decimal = _ZERO
    reimbursement_out_total: Decimal = _ZERO

    def to_dict(self) -> dict[str, str]:
        """Return stable, JSON-safe currency strings."""
        return {
            "income_total": _money(self.income_total) or "0.00",
            "expense_total": _money(self.expense_total) or "0.00",
            "transfer_in_total": _money(self.transfer_in_total) or "0.00",
            "transfer_out_total": _money(self.transfer_out_total) or "0.00",
            "reimbursement_in_total": _money(self.reimbursement_in_total) or "0.00",
            "reimbursement_out_total": _money(self.reimbursement_out_total) or "0.00",
            "credit_card_total": _money(self.credit_card_total) or "0.00",
            "net": _money(self.net) or "0.00",
        }


@dataclass(frozen=True)
class SnapshotTransactionCounts:
    """Review-state counts for one depository account and calendar month."""

    posted: int
    pending: int
    unreviewed: int
    uncategorized: int
    reimbursable: int

    def to_dict(self) -> dict[str, int]:
        """Return machine-readable review counts."""
        return {
            "posted": self.posted,
            "pending": self.pending,
            "unreviewed": self.unreviewed,
            "uncategorized": self.uncategorized,
            "reimbursable": self.reimbursable,
        }


@dataclass(frozen=True)
class PlaidItemSyncEvidence:
    """Non-secret lifecycle evidence for one Plaid item in one ingest run."""

    plaid_item_id: str
    ingest_run_id: str | None = None
    ingest_run_item_id: str | None = None
    item_status: str | None = None
    run_status: str | None = None
    started_at: datetime | None = None
    ended_at: datetime | None = None
    items_total: int | None = None
    items_ok: int | None = None
    items_failed: int | None = None
    run_tx_added: int | None = None
    run_tx_modified: int | None = None
    run_tx_removed: int | None = None
    item_tx_added: int | None = None
    item_tx_modified: int | None = None
    item_tx_removed: int | None = None
    duration_ms: int | None = None

    def to_dict(self) -> dict[str, Any]:
        """Return only UUID, status, timestamp, and count evidence."""
        return {
            "plaid_item_id": self.plaid_item_id,
            "ingest_run_id": self.ingest_run_id,
            "ingest_run_item_id": self.ingest_run_item_id,
            "item_status": self.item_status,
            "run_status": self.run_status,
            "started_at": _timestamp(self.started_at),
            "ended_at": _timestamp(self.ended_at),
            "items_total": self.items_total,
            "items_ok": self.items_ok,
            "items_failed": self.items_failed,
            "run_tx_added": self.run_tx_added,
            "run_tx_modified": self.run_tx_modified,
            "run_tx_removed": self.run_tx_removed,
            "item_tx_added": self.item_tx_added,
            "item_tx_modified": self.item_tx_modified,
            "item_tx_removed": self.item_tx_removed,
            "duration_ms": self.duration_ms,
        }


@dataclass(frozen=True)
class SnapshotClosePreview:
    """Read-only close calculation bound to a stable audit hash."""

    year_month: str
    account_id: str
    account_name: str
    snapshot_id: str
    status: str
    last_synced_at: datetime | None
    starting_balance: Decimal | None
    captured_closing_balance: Decimal | None
    projected_closing_balance: Decimal | None
    closing_balance_to_freeze: Decimal | None
    captured_difference: Decimal | None
    planned_credit_card_total: Decimal
    actual_credit_card_total: Decimal
    remaining_credit_card_total: Decimal
    missing_actual_credit_card_count: int
    transaction_counts: SnapshotTransactionCounts
    totals: SnapshotCloseTotals
    blockers: tuple[str, ...]
    audit_hash: str
    direct_starting_balance: Decimal | None = None
    starting_balance_provenance: str = "unavailable"
    prior_year_month: str | None = None
    prior_snapshot_id: str | None = None
    prior_snapshot_status: str | None = None
    prior_direct_starting_balance: Decimal | None = None
    prior_closing_balance: Decimal | None = None
    prior_closing_balance_frozen: bool | None = None
    prior_snapshot_updated_at: datetime | None = None
    has_earlier_snapshot: bool = False
    next_year_month: str | None = None
    next_snapshot_id: str | None = None
    next_snapshot_status: str | None = None
    next_starting_balance: Decimal | None = None
    closed_at: datetime | None = None
    plaid_item_sync_evidence: tuple[PlaidItemSyncEvidence, ...] = ()
    active_plaid_item_sync_evidence: tuple[PlaidItemSyncEvidence, ...] = ()
    reconciliation_evidence: CurrentReconciliationEvidence | None = None

    @property
    def can_close(self) -> bool:
        """Return whether every hard close invariant is satisfied."""
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        """Return a stable JSON-safe representation for CLI and UI clients."""
        return {
            "year_month": self.year_month,
            "account_id": self.account_id,
            "account_name": self.account_name,
            "snapshot_id": self.snapshot_id,
            "status": self.status,
            "last_synced_at": _timestamp(self.last_synced_at),
            "starting_balance": _money(self.starting_balance),
            "captured_closing_balance": _money(self.captured_closing_balance),
            "projected_closing_balance": _money(self.projected_closing_balance),
            "closing_balance_to_freeze": _money(self.closing_balance_to_freeze),
            "captured_difference": _money(self.captured_difference),
            "planned_credit_card_total": _money(self.planned_credit_card_total),
            "actual_credit_card_total": _money(self.actual_credit_card_total),
            "remaining_credit_card_total": _money(self.remaining_credit_card_total),
            "missing_actual_credit_card_count": self.missing_actual_credit_card_count,
            "transaction_counts": self.transaction_counts.to_dict(),
            "totals": self.totals.to_dict(),
            "blockers": list(self.blockers),
            "can_close": self.can_close,
            "audit_hash": self.audit_hash,
            "direct_starting_balance": _money(self.direct_starting_balance),
            "starting_balance_provenance": self.starting_balance_provenance,
            "prior_year_month": self.prior_year_month,
            "prior_snapshot_id": self.prior_snapshot_id,
            "prior_snapshot_status": self.prior_snapshot_status,
            "prior_direct_starting_balance": _money(self.prior_direct_starting_balance),
            "prior_closing_balance": _money(self.prior_closing_balance),
            "prior_closing_balance_frozen": self.prior_closing_balance_frozen,
            "prior_snapshot_updated_at": _timestamp(self.prior_snapshot_updated_at),
            "has_earlier_snapshot": self.has_earlier_snapshot,
            "next_year_month": self.next_year_month,
            "next_snapshot_id": self.next_snapshot_id,
            "next_snapshot_status": self.next_snapshot_status,
            "next_starting_balance": _money(self.next_starting_balance),
            "closed_at": _timestamp(self.closed_at),
            "plaid_item_sync_evidence": [
                evidence.to_dict() for evidence in self.plaid_item_sync_evidence
            ],
            "active_plaid_item_sync_evidence": [
                evidence.to_dict() for evidence in self.active_plaid_item_sync_evidence
            ],
            "reconciliation_evidence": (
                self.reconciliation_evidence.audit_dict()
                if self.reconciliation_evidence is not None
                else None
            ),
        }


@contextmanager
def get_read_only_session() -> Generator[Session, None, None]:
    """Yield a PostgreSQL transaction that rejects accidental writes."""
    from budget_me.streamlit_app.db import get_sync_engine

    engine = get_sync_engine()
    session = Session(bind=engine)
    try:
        session.execute(text("SET TRANSACTION READ ONLY"))
        yield session
    finally:
        session.rollback()
        session.close()
        engine.dispose()


def _month_bounds(year_month: str) -> tuple[date, date]:
    """Parse YYYY-MM and return inclusive calendar-month bounds."""
    parsed = datetime.strptime(year_month, "%Y-%m")
    last_day = monthrange(parsed.year, parsed.month)[1]
    return date(parsed.year, parsed.month, 1), date(parsed.year, parsed.month, last_day)


def _next_year_month(year_month: str) -> str:
    """Return the calendar month immediately after YYYY-MM."""
    start_date, _ = _month_bounds(year_month)
    if start_date.month == 12:
        return f"{start_date.year + 1:04d}-01"
    return f"{start_date.year:04d}-{start_date.month + 1:02d}"


def _prior_year_month(year_month: str) -> str:
    """Return the calendar month immediately before YYYY-MM."""
    start_date, _ = _month_bounds(year_month)
    if start_date.month == 1:
        return f"{start_date.year - 1:04d}-12"
    return f"{start_date.year:04d}-{start_date.month - 1:02d}"


def _has_frozen_close(snapshot: MonthlySnapshot | None) -> bool:
    """Return whether a prior snapshot is authoritative rollover state."""
    return bool(
        snapshot is not None
        and snapshot.status == SnapshotStatus.CLOSED
        and snapshot.closing_balance_frozen
        and snapshot.closing_balance is not None
    )


def _starting_balance_provenance(
    snapshot: MonthlySnapshot,
    prior_snapshot: MonthlySnapshot | None,
    starting_balance: Decimal | None,
) -> str:
    """Describe the exact source used for a candidate month's starting balance."""
    if snapshot.starting_balance is not None:
        if prior_snapshot is None:
            return "bootstrap_direct_starting_balance"
        if (
            _has_frozen_close(prior_snapshot)
            and snapshot.starting_balance == prior_snapshot.closing_balance
        ):
            return "prior_frozen_close"
        return "current_snapshot_direct"
    if (
        _has_frozen_close(prior_snapshot)
        and starting_balance == prior_snapshot.closing_balance
    ):
        return "prior_frozen_close"
    if prior_snapshot is not None:
        return "invalid_prior_snapshot"
    if starting_balance is not None:
        return "bootstrap_exact_balance"
    return "unavailable"


def _resolve_starting_balance(
    snapshot: MonthlySnapshot,
    prior_snapshot: MonthlySnapshot | None,
    bootstrap_exact_balance: Decimal | None,
) -> tuple[Decimal | None, str]:
    """Resolve only authoritative rollover state or an explicit first-month bootstrap."""
    if snapshot.starting_balance is not None:
        starting_balance = snapshot.starting_balance
    elif _has_frozen_close(prior_snapshot):
        starting_balance = prior_snapshot.closing_balance
    elif prior_snapshot is None:
        starting_balance = bootstrap_exact_balance
    else:
        # Never silently roll an OPEN or otherwise invalid prior estimate forward.
        starting_balance = None
    return (
        starting_balance,
        _starting_balance_provenance(snapshot, prior_snapshot, starting_balance),
    )


def _transaction_counts(
    transactions: Sequence[Transaction], account_id: str
) -> SnapshotTransactionCounts:
    """Count review state for posted activity on the paying account itself."""
    account_transactions = [
        transaction
        for transaction in transactions
        if transaction.account_id == account_id
    ]
    posted = [
        transaction for transaction in account_transactions if not transaction.pending
    ]
    return SnapshotTransactionCounts(
        posted=len(posted),
        pending=sum(transaction.pending for transaction in account_transactions),
        unreviewed=sum(not transaction.reviewed for transaction in posted),
        uncategorized=sum(
            not (transaction.budget_category or "").strip()
            or (transaction.budget_category or "").strip().casefold() == "uncategorized"
            for transaction in posted
        ),
        reimbursable=sum(transaction.reimbursable is True for transaction in posted),
    )


def list_included_depository_accounts(session: Session) -> list[Account]:
    """List close-relevant accounts without creating snapshot rows."""
    return list(
        session.execute(
            select(Account)
            .where(
                Account.type == "depository",
                Account.is_excluded.is_(False),
            )
            .order_by(Account.account_id)
        ).scalars()
    )


def get_account_transaction_counts(
    session: Session, year_month: str, account_id: str
) -> SnapshotTransactionCounts:
    """Read review-state counts for an account even when its snapshot is missing."""
    start_date, end_date = _month_bounds(year_month)
    transactions = list(
        session.execute(
            select(Transaction).where(
                Transaction.account_id == account_id,
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
        ).scalars()
    )
    return _transaction_counts(transactions, account_id)


def _sum_line_items(items: Sequence[SnapshotLineItem]) -> tuple[Decimal, ...]:
    """Return income, expense, transfer-in, and transfer-out totals."""
    totals = {
        "income": _ZERO,
        "expense": _ZERO,
        "transfer_in": _ZERO,
        "transfer_out": _ZERO,
    }
    for item in items:
        if item.skipped or item.item_type not in totals:
            continue
        totals[item.item_type] += item.amount or _ZERO
    return (
        totals["income"],
        totals["expense"],
        totals["transfer_in"],
        totals["transfer_out"],
    )


def _relevant_plaid_item_ids(
    account: Account,
    cards: Sequence[SnapshotCreditCard],
    credit_card_accounts: Sequence[Account],
) -> tuple[uuid.UUID, ...]:
    """Return Plaid items whose feeds are required to close the snapshot.

    A card with complete checking-side payment evidence does not depend on its
    card feed for this cash snapshot. This matters for a closed or relink-required
    card whose exact payment is still present in the paying account. If another
    relevant card shares that Plaid item without checking evidence, the item is
    still required.
    """
    snapshot_cards_by_account_id = {card.account_id: card for card in cards}
    snapshot_card_ids = set(snapshot_cards_by_account_id)
    relevant_ids = {account.plaid_item_id}
    for card_account in credit_card_accounts:
        is_relevant = card_account.account_id in snapshot_card_ids or (
            card_account.type == "credit"
            and not card_account.is_excluded
            and card_account.paying_account_id == account.account_id
        )
        if not is_relevant:
            continue
        snapshot_card = snapshot_cards_by_account_id.get(card_account.account_id)
        if snapshot_card is not None and has_checking_account_marker(snapshot_card):
            continue
        relevant_ids.add(card_account.plaid_item_id)
    return tuple(sorted(relevant_ids, key=str))


def _plaid_item_sync_evidence(
    run_item: IngestRunItem, run: IngestRun
) -> PlaidItemSyncEvidence:
    """Project ORM rows into the deliberately non-secret close evidence shape."""
    return PlaidItemSyncEvidence(
        plaid_item_id=str(run_item.plaid_item_id),
        ingest_run_id=str(run.id),
        ingest_run_item_id=str(run_item.id),
        item_status=getattr(run_item.status, "value", run_item.status),
        run_status=getattr(run.status, "value", run.status),
        started_at=run.started_at,
        ended_at=run.ended_at,
        items_total=run.items_total,
        items_ok=run.items_ok,
        items_failed=run.items_failed,
        run_tx_added=run.tx_added,
        run_tx_modified=run.tx_modified,
        run_tx_removed=run.tx_removed,
        item_tx_added=run_item.tx_added,
        item_tx_modified=run_item.tx_modified,
        item_tx_removed=run_item.tx_removed,
        duration_ms=run_item.duration_ms,
    )


def _load_plaid_item_sync_evidence(
    session: Session, relevant_item_ids: Sequence[uuid.UUID]
) -> tuple[tuple[PlaidItemSyncEvidence, ...], tuple[PlaidItemSyncEvidence, ...]]:
    """Load last-completed and active evidence for relevant Plaid items.

    Runs may overlap, so start order cannot establish which result was last to
    affect the database. Terminal evidence is selected by ``ended_at``; active
    evidence is gathered independently across the complete history.
    """
    if not relevant_item_ids:
        return (), ()

    rows = session.execute(
        select(IngestRunItem, IngestRun)
        .join(IngestRun, IngestRun.id == IngestRunItem.ingest_run_id)
        .where(IngestRunItem.plaid_item_id.in_(relevant_item_ids))
        .order_by(
            IngestRunItem.plaid_item_id,
            IngestRun.started_at.desc(),
            IngestRun.id.desc(),
            IngestRunItem.id.desc(),
        )
    ).all()

    evidence_by_item_id: dict[str, list[PlaidItemSyncEvidence]] = {}
    active: list[PlaidItemSyncEvidence] = []
    for run_item, run in rows:
        evidence = _plaid_item_sync_evidence(run_item, run)
        evidence_by_item_id.setdefault(evidence.plaid_item_id, []).append(evidence)
        if (
            evidence.item_status == IngestRunItemStatus.PENDING.value
            or evidence.run_status == IngestRunStatus.RUNNING.value
        ):
            active.append(evidence)

    latest: list[PlaidItemSyncEvidence] = []
    for item_id in relevant_item_ids:
        item_id_string = str(item_id)
        item_evidence = evidence_by_item_id.get(item_id_string, [])
        terminal_evidence = [
            evidence
            for evidence in item_evidence
            if evidence.ended_at is not None
            and evidence.item_status != IngestRunItemStatus.PENDING.value
            and evidence.run_status != IngestRunStatus.RUNNING.value
        ]
        candidates = terminal_evidence or item_evidence
        latest.append(
            max(
                candidates,
                key=lambda evidence: (
                    _as_utc(evidence.ended_at or evidence.started_at)
                    if evidence.ended_at is not None or evidence.started_at is not None
                    else datetime.min.replace(tzinfo=UTC),
                    _as_utc(evidence.started_at)
                    if evidence.started_at is not None
                    else datetime.min.replace(tzinfo=UTC),
                    evidence.ingest_run_id or "",
                    evidence.ingest_run_item_id or "",
                ),
            )
            if candidates
            else PlaidItemSyncEvidence(plaid_item_id=item_id_string)
        )

    return tuple(latest), tuple(
        sorted(
            active,
            key=lambda evidence: (
                evidence.plaid_item_id,
                _timestamp(evidence.started_at) or "",
                evidence.ingest_run_id or "",
                evidence.ingest_run_item_id or "",
            ),
        )
    )


def _audit_payload(
    *,
    snapshot: MonthlySnapshot,
    account: Account,
    items: Sequence[SnapshotLineItem],
    cards: Sequence[SnapshotCreditCard],
    credit_card_accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    plaid_item_sync_evidence: Sequence[PlaidItemSyncEvidence],
    active_plaid_item_sync_evidence: Sequence[PlaidItemSyncEvidence],
    prior_snapshot: MonthlySnapshot | None,
    next_snapshot: MonthlySnapshot | None,
    captured_balance: Decimal | None,
    starting_balance: Decimal | None,
    starting_balance_provenance: str,
    has_earlier_snapshot: bool,
    reconciliation_evidence: CurrentReconciliationEvidence | None,
) -> dict[str, Any]:
    """Build the deterministic input payload protected by the audit hash."""
    return {
        "version": _AUDIT_VERSION,
        "snapshot": {
            "id": str(snapshot.id),
            "year_month": snapshot.year_month,
            "account_id": snapshot.account_id,
            "status": _status_value(snapshot.status),
            "direct_starting_balance": _money(snapshot.starting_balance),
            "last_synced_at": _timestamp(snapshot.last_synced_at),
            "updated_at": _timestamp(snapshot.updated_at),
        },
        "account": {
            "account_id": account.account_id,
            "is_excluded": account.is_excluded,
            "updated_at": _timestamp(account.updated_at),
        },
        "starting_balance": _money(starting_balance),
        "starting_balance_provenance": starting_balance_provenance,
        "has_earlier_snapshot": has_earlier_snapshot,
        "captured_balance": _money(captured_balance),
        "reconciliation_evidence": (
            reconciliation_evidence.audit_dict()
            if reconciliation_evidence is not None
            else None
        ),
        "plaid_item_sync_evidence": [
            evidence.to_dict() for evidence in plaid_item_sync_evidence
        ],
        "active_plaid_item_sync_evidence": [
            evidence.to_dict() for evidence in active_plaid_item_sync_evidence
        ],
        "prior_snapshot": None
        if prior_snapshot is None
        else {
            "id": str(prior_snapshot.id),
            "year_month": prior_snapshot.year_month,
            "account_id": prior_snapshot.account_id,
            "status": _status_value(prior_snapshot.status),
            "direct_starting_balance": _money(prior_snapshot.starting_balance),
            "closing_balance": _money(prior_snapshot.closing_balance),
            "closing_balance_frozen": prior_snapshot.closing_balance_frozen,
            "updated_at": _timestamp(prior_snapshot.updated_at),
        },
        "next_snapshot": None
        if next_snapshot is None
        else {
            "id": str(next_snapshot.id),
            "year_month": next_snapshot.year_month,
            "account_id": next_snapshot.account_id,
            "status": _status_value(next_snapshot.status),
            "starting_balance": _money(next_snapshot.starting_balance),
            "updated_at": _timestamp(next_snapshot.updated_at),
        },
        "items": sorted(
            (
                {
                    "id": str(item.id),
                    "type": item.item_type,
                    "amount": _money(item.amount),
                    "skipped": item.skipped,
                    "updated_at": _timestamp(item.updated_at),
                }
                for item in items
            ),
            key=lambda item: item["id"],
        ),
        "cards": sorted(
            (
                {
                    "id": str(card.id),
                    "account_id": card.account_id,
                    "planned": _money(card.calculated_payment),
                    "actual": _money(card.actual_payment_amount),
                    "actual_date": card.actual_payment_date.isoformat()
                    if card.actual_payment_date
                    else None,
                    "actual_source": getattr(card, "actual_payment_source", None),
                    "actual_transaction_id": str(
                        getattr(card, "actual_payment_transaction_id", None)
                    ),
                    "actual_note": getattr(card, "actual_payment_note", None),
                    "updated_at": _timestamp(card.updated_at),
                }
                for card in cards
            ),
            key=lambda card: card["id"],
        ),
        # Current account membership is a close input, not mutable metadata.
        # Reassigning, excluding, or adding a card invalidates an earlier preview.
        "credit_card_membership": sorted(
            (
                {
                    "account_id": card_account.account_id,
                    "type": card_account.type,
                    "is_excluded": card_account.is_excluded,
                    "paying_account_id": card_account.paying_account_id,
                    "updated_at": _timestamp(card_account.updated_at),
                }
                for card_account in credit_card_accounts
            ),
            key=lambda card_account: card_account["account_id"],
        ),
        # Transaction content is hashed, never printed. A late Plaid sync therefore
        # invalidates an already-reviewed close without exposing transaction detail.
        "transactions": sorted(
            (
                {
                    "id": str(transaction.id),
                    "account_id": transaction.account_id,
                    "date": transaction.date.isoformat(),
                    "amount": _money(transaction.amount),
                    "pending": transaction.pending,
                    "category_detailed": transaction.category_detailed,
                    "raw_card_payment_detailed": _raw_card_payment_detailed(
                        transaction
                    ),
                    "budget_category": transaction.budget_category,
                    "reimbursable": transaction.reimbursable,
                    "reviewed": transaction.reviewed,
                    "updated_at": _timestamp(transaction.updated_at),
                }
                for transaction in transactions
            ),
            key=lambda transaction: transaction["id"],
        ),
    }


def _calculate_preview(
    *,
    snapshot: MonthlySnapshot,
    account: Account,
    items: Sequence[SnapshotLineItem],
    cards: Sequence[SnapshotCreditCard],
    credit_card_accounts: Sequence[Account],
    transactions: Sequence[Transaction],
    missing_paying_cards: Sequence[Account],
    next_snapshot: MonthlySnapshot | None,
    starting_balance: Decimal | None,
    captured_balance: Decimal | None,
    now: datetime,
    max_reconciliation_age: timedelta,
    plaid_item_sync_evidence: Sequence[PlaidItemSyncEvidence] = (),
    active_plaid_item_sync_evidence: Sequence[PlaidItemSyncEvidence] = (),
    prior_snapshot: MonthlySnapshot | None = None,
    starting_balance_provenance: str | None = None,
    has_earlier_snapshot: bool = False,
    reconciliation_evidence: CurrentReconciliationEvidence | None = None,
) -> SnapshotClosePreview:
    """Pure close calculation used by database and behavioral tests."""
    income, expense, transfer_in, transfer_out = _sum_line_items(items)
    planned_cards = sum(
        (card.calculated_payment or _ZERO for card in cards), start=_ZERO
    )
    actual_cards = sum(
        (card.actual_payment_amount or _ZERO for card in cards), start=_ZERO
    )
    remaining_cards = max(planned_cards - actual_cards, _ZERO)
    missing_actual_cards = sum(card.actual_payment_amount is None for card in cards)
    transaction_counts = _transaction_counts(transactions, account.account_id)
    reimbursement_in = _ZERO
    reimbursement_out = _ZERO
    if reconciliation_evidence is not None:
        if reconciliation_evidence.totals is None:
            income = expense = transfer_in = transfer_out = _ZERO
            actual_cards_for_totals = _ZERO
        else:
            reconciled_totals = reconciliation_evidence.totals
            income = reconciled_totals.income_total
            expense = reconciled_totals.expense_total
            transfer_in = reconciled_totals.transfer_in_total
            transfer_out = reconciled_totals.transfer_out_total
            reimbursement_in = reconciled_totals.reimbursement_in_total
            reimbursement_out = reconciled_totals.reimbursement_out_total
            actual_cards_for_totals = reconciled_totals.credit_card_total
        net = (
            income
            + transfer_in
            + reimbursement_in
            - expense
            - transfer_out
            - reimbursement_out
            - actual_cards_for_totals
        )
    else:
        # Every public database preview supplies receipt evidence and therefore
        # fails closed without a run. Pure behavioral tests may omit it.
        actual_cards_for_totals = actual_cards
        net = income + transfer_in - expense - transfer_out - actual_cards
    totals = SnapshotCloseTotals(
        income_total=income,
        expense_total=expense,
        transfer_in_total=transfer_in,
        transfer_out_total=transfer_out,
        reimbursement_in_total=reimbursement_in,
        reimbursement_out_total=reimbursement_out,
        credit_card_total=actual_cards_for_totals,
        net=net,
    )

    projected = starting_balance + net if starting_balance is not None else None
    # A close freezes observed month-end cash, never an uncaptured projection.
    close_value = captured_balance
    difference = (
        captured_balance - projected
        if captured_balance is not None and projected is not None
        else None
    )

    blockers: list[str] = []
    _, month_end = _month_bounds(snapshot.year_month)
    prior_year_month = _prior_year_month(snapshot.year_month)
    provenance = starting_balance_provenance or _starting_balance_provenance(
        snapshot, prior_snapshot, starting_balance
    )
    relevant_plaid_item_ids = _relevant_plaid_item_ids(
        account, cards, credit_card_accounts
    )
    latest_evidence_by_item_id = {
        evidence.plaid_item_id: evidence
        for evidence in plaid_item_sync_evidence
        if evidence.plaid_item_id
        in {str(item_id) for item_id in relevant_plaid_item_ids}
    }
    scoped_sync_evidence = tuple(
        latest_evidence_by_item_id.get(
            str(item_id), PlaidItemSyncEvidence(plaid_item_id=str(item_id))
        )
        for item_id in relevant_plaid_item_ids
    )
    relevant_item_id_strings = {str(item_id) for item_id in relevant_plaid_item_ids}
    scoped_active_evidence = tuple(
        sorted(
            (
                evidence
                for evidence in active_plaid_item_sync_evidence
                if evidence.plaid_item_id in relevant_item_id_strings
            ),
            key=lambda evidence: (
                evidence.plaid_item_id,
                _timestamp(evidence.started_at) or "",
                evidence.ingest_run_id or "",
                evidence.ingest_run_item_id or "",
            ),
        )
    )
    if snapshot.status == SnapshotStatus.CLOSED:
        blockers.append("Snapshot is already closed.")
    if account.is_excluded:
        blockers.append("Account is excluded from monthly snapshots.")
    if reconciliation_evidence is not None:
        blockers.extend(reconciliation_evidence.blockers)
    for evidence in scoped_active_evidence:
        blockers.append(
            "Plaid ingest activity is still running or pending for relevant item "
            f"{evidence.plaid_item_id}."
        )
    for evidence in scoped_sync_evidence:
        if evidence.ingest_run_id is None or evidence.ingest_run_item_id is None:
            blockers.append(
                "No Plaid ingest history exists for relevant item "
                f"{evidence.plaid_item_id}."
            )
            continue
        if evidence.item_status != IngestRunItemStatus.SUCCESS.value:
            blockers.append(
                "Latest Plaid item sync for relevant item "
                f"{evidence.plaid_item_id} is {evidence.item_status}; success is required."
            )
        if evidence.run_status not in {
            IngestRunStatus.COMPLETED.value,
            IngestRunStatus.PARTIAL.value,
        }:
            blockers.append(
                "Latest Plaid parent run for relevant item "
                f"{evidence.plaid_item_id} is {evidence.run_status}; "
                "completed or partial is required."
            )
        if evidence.ended_at is None:
            blockers.append(
                "Latest Plaid parent run for relevant item "
                f"{evidence.plaid_item_id} has no completion timestamp."
            )
    # last_synced_at is a legacy marker that predates immutable receipts.
    # Once receipt evidence is available, never use that marker as proof of a
    # modern reconciliation: migrated plan caches may otherwise appear to be
    # stale actuals and generate a cascade of misleading derivative blockers.
    reconciliation_time = (
        reconciliation_evidence.reconciled_at
        if reconciliation_evidence is not None
        else snapshot.last_synced_at
    )
    if reconciliation_time is None:
        if reconciliation_evidence is None:
            blockers.append("Snapshot has not been reconciled with transactions.")
    else:
        synced_at = _as_utc(reconciliation_time)
        if now - synced_at > max_reconciliation_age:
            blockers.append(
                "Snapshot reconciliation is stale; review it again before closing."
            )
        if synced_at.date() < month_end:
            blockers.append("Snapshot was reconciled before the calendar month ended.")
        for evidence in scoped_sync_evidence:
            if evidence.ended_at is None:
                continue
            ended_at = _as_utc(evidence.ended_at)
            if ended_at > synced_at:
                blockers.append(
                    "Latest Plaid sync for relevant item "
                    f"{evidence.plaid_item_id} completed after the snapshot was "
                    "last reconciled."
                )
            elif (
                evidence.item_status == IngestRunItemStatus.SUCCESS.value
                and evidence.run_status
                in {
                    IngestRunStatus.COMPLETED.value,
                    IngestRunStatus.PARTIAL.value,
                }
                and synced_at - ended_at > max_reconciliation_age
            ):
                blockers.append(
                    "Latest successful Plaid sync for relevant item "
                    f"{evidence.plaid_item_id} is too old relative to reconciliation."
                )
        latest_transaction_update = max(
            (_as_utc(transaction.updated_at) for transaction in transactions),
            default=None,
        )
        if latest_transaction_update and latest_transaction_update > synced_at:
            blockers.append(
                "Transactions changed after the snapshot was last reconciled."
            )
    if transaction_counts.pending:
        blockers.append(f"{transaction_counts.pending} transactions are still pending.")
    if transaction_counts.unreviewed:
        blockers.append(
            f"{transaction_counts.unreviewed} posted transactions remain unreviewed."
        )
    if transaction_counts.uncategorized:
        blockers.append(
            f"{transaction_counts.uncategorized} posted transactions remain uncategorized."
        )
    for card in missing_paying_cards:
        name = card.display_name or card.name
        blockers.append(f"Credit card {name} has no paying account assignment.")

    card_accounts_by_id = {
        card_account.account_id: card_account for card_account in credit_card_accounts
    }
    snapshot_card_ids = {card.account_id for card in cards}
    currently_assigned_cards = [
        card_account
        for card_account in credit_card_accounts
        if card_account.type == "credit"
        and not card_account.is_excluded
        and card_account.paying_account_id == account.account_id
    ]
    for card_account in currently_assigned_cards:
        if card_account.account_id not in snapshot_card_ids:
            name = card_account.display_name or card_account.name
            blockers.append(
                f"Currently assigned credit card {name} is missing from the snapshot."
            )

    for card in cards:
        card_account = card_accounts_by_id.get(card.account_id)
        if card_account is None:
            blockers.append(
                f"Snapshot credit card {card.account_id} is stale; "
                "the account no longer exists."
            )
            card_name = card.account_id
        else:
            card_name = card_account.display_name or card_account.name
            if card_account.type != "credit":
                blockers.append(
                    f"Snapshot credit card {card_name} is stale; "
                    "the account is no longer a credit account."
                )
            elif (
                not card_account.is_excluded
                and card_account.paying_account_id != account.account_id
            ):
                if card_account.paying_account_id is None:
                    blockers.append(
                        f"Snapshot credit card {card_name} is stale; "
                        "it is no longer assigned to this paying account."
                    )
                else:
                    blockers.append(
                        f"Snapshot credit card {card_name} was reassigned to "
                        f"{card_account.paying_account_id}."
                    )

        card_payments = [
            transaction
            for transaction in transactions
            if transaction.account_id == card.account_id
            and _is_card_payment(transaction)
        ]
        pending_payments = [
            transaction for transaction in card_payments if transaction.pending
        ]
        posted_payments = [
            transaction for transaction in card_payments if not transaction.pending
        ]
        if pending_payments:
            blockers.append(
                f"{len(pending_payments)} card-side payment(s) for {card_name} "
                "are still pending."
            )

        expected_amount = sum(
            (abs(transaction.amount) for transaction in posted_payments),
            start=_ZERO,
        )
        expected_date = max(
            (transaction.date for transaction in posted_payments),
            default=None,
        )
        if not actual_matches_feed_or_evidence(
            card,
            expected_amount,
            expected_date,
            transactions=transactions,
            paying_account_id=account.account_id,
        ):
            blockers.append(
                f"Snapshot actual for {card_name} does not match posted card-side "
                f"payments (stored {_money(card.actual_payment_amount)} on "
                f"{card.actual_payment_date}; expected {_money(expected_amount)} "
                f"on {expected_date})."
            )

    if missing_actual_cards:
        blockers.append(
            f"{missing_actual_cards} snapshot credit cards have no posted actual amount."
        )
    if difference is not None and difference != _ZERO:
        blockers.append(
            "Projected close does not match the captured month-end balance "
            f"(difference: {difference:+.2f})."
        )
    if captured_balance is None:
        blockers.append(
            "No exact month-end closing balance capture exists for "
            f"{month_end.isoformat()}."
        )

    if prior_snapshot is None and has_earlier_snapshot:
        blockers.append(
            f"Immediate prior-month snapshot {prior_year_month} is missing despite "
            "earlier snapshot history; repair the rollover chain before closing."
        )

    if prior_snapshot is not None:
        if prior_snapshot.status != SnapshotStatus.CLOSED:
            blockers.append(
                f"Prior-month snapshot {prior_year_month} must be closed first."
            )
        if not prior_snapshot.closing_balance_frozen:
            blockers.append(
                f"Prior-month snapshot {prior_year_month} has no frozen close."
            )
        if prior_snapshot.closing_balance is None:
            blockers.append(
                f"Prior-month snapshot {prior_year_month} has a null closing balance."
            )
        if (
            _has_frozen_close(prior_snapshot)
            and starting_balance != prior_snapshot.closing_balance
        ):
            blockers.append(
                f"Starting balance {_money(starting_balance)} conflicts with "
                f"prior-month frozen close "
                f"{_money(prior_snapshot.closing_balance)}."
            )

    next_year_month = _next_year_month(snapshot.year_month)
    if next_snapshot is not None:
        if next_snapshot.status == SnapshotStatus.CLOSED:
            blockers.append(f"Next-month snapshot {next_year_month} is already closed.")
        elif (
            next_snapshot.starting_balance is not None
            and close_value is not None
            and next_snapshot.starting_balance != close_value
        ):
            blockers.append(
                f"Next-month snapshot {next_year_month} has starting balance "
                f"{next_snapshot.starting_balance:.2f}, which conflicts with "
                f"the proposed frozen close {close_value:.2f}."
            )

    if close_value is None:
        blockers.append("No non-null closing balance can be determined.")

    payload = _audit_payload(
        snapshot=snapshot,
        account=account,
        items=items,
        cards=cards,
        credit_card_accounts=credit_card_accounts,
        transactions=transactions,
        plaid_item_sync_evidence=scoped_sync_evidence,
        active_plaid_item_sync_evidence=scoped_active_evidence,
        prior_snapshot=prior_snapshot,
        next_snapshot=next_snapshot,
        captured_balance=captured_balance,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        has_earlier_snapshot=has_earlier_snapshot,
        reconciliation_evidence=reconciliation_evidence,
    )
    audit_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()

    return SnapshotClosePreview(
        year_month=snapshot.year_month,
        account_id=account.account_id,
        account_name=account.display_name or account.name,
        snapshot_id=str(snapshot.id),
        status=_status_value(snapshot.status),
        last_synced_at=snapshot.last_synced_at,
        starting_balance=starting_balance,
        captured_closing_balance=captured_balance,
        projected_closing_balance=projected,
        closing_balance_to_freeze=close_value,
        captured_difference=difference,
        planned_credit_card_total=planned_cards,
        actual_credit_card_total=actual_cards,
        remaining_credit_card_total=remaining_cards,
        missing_actual_credit_card_count=missing_actual_cards,
        transaction_counts=transaction_counts,
        totals=totals,
        blockers=tuple(blockers),
        audit_hash=audit_hash,
        direct_starting_balance=snapshot.starting_balance,
        starting_balance_provenance=provenance,
        prior_year_month=prior_year_month,
        prior_snapshot_id=(
            str(prior_snapshot.id) if prior_snapshot is not None else None
        ),
        prior_snapshot_status=(
            _status_value(prior_snapshot.status) if prior_snapshot is not None else None
        ),
        prior_direct_starting_balance=(
            prior_snapshot.starting_balance if prior_snapshot is not None else None
        ),
        prior_closing_balance=(
            prior_snapshot.closing_balance if prior_snapshot is not None else None
        ),
        prior_closing_balance_frozen=(
            prior_snapshot.closing_balance_frozen
            if prior_snapshot is not None
            else None
        ),
        prior_snapshot_updated_at=(
            prior_snapshot.updated_at if prior_snapshot is not None else None
        ),
        has_earlier_snapshot=has_earlier_snapshot,
        next_year_month=next_year_month,
        next_snapshot_id=str(next_snapshot.id) if next_snapshot is not None else None,
        next_snapshot_status=(
            _status_value(next_snapshot.status) if next_snapshot is not None else None
        ),
        next_starting_balance=(
            next_snapshot.starting_balance if next_snapshot is not None else None
        ),
        plaid_item_sync_evidence=scoped_sync_evidence,
        active_plaid_item_sync_evidence=scoped_active_evidence,
        reconciliation_evidence=reconciliation_evidence,
    )


def build_close_preview(
    session: Session,
    year_month: str,
    account_id: str,
    *,
    now: datetime | None = None,
    max_reconciliation_age: timedelta = RECONCILIATION_MAX_AGE,
) -> SnapshotClosePreview:
    """Calculate a per-account close preview without mutating the session."""
    start_date, end_date = _month_bounds(year_month)
    snapshot = session.execute(
        select(MonthlySnapshot).where(
            MonthlySnapshot.year_month == year_month,
            MonthlySnapshot.account_id == account_id,
        )
    ).scalar_one_or_none()
    if snapshot is None:
        raise ValueError(f"Snapshot for {year_month} / {account_id} not found")

    account = session.execute(
        select(Account).where(Account.account_id == account_id)
    ).scalar_one_or_none()
    if account is None:
        raise ValueError(f"Account {account_id} not found")

    items = list(
        session.execute(
            select(SnapshotLineItem).where(SnapshotLineItem.snapshot_id == snapshot.id)
        ).scalars()
    )
    cards = list(
        session.execute(
            select(SnapshotCreditCard).where(
                SnapshotCreditCard.snapshot_id == snapshot.id
            )
        ).scalars()
    )
    prior_year_month = _prior_year_month(year_month)
    prior_snapshot = session.execute(
        select(MonthlySnapshot).where(
            MonthlySnapshot.year_month == prior_year_month,
            MonthlySnapshot.account_id == account_id,
        )
    ).scalar_one_or_none()
    has_earlier_snapshot = False
    if prior_snapshot is None:
        has_earlier_snapshot = (
            session.execute(
                select(MonthlySnapshot.id)
                .where(
                    MonthlySnapshot.account_id == account_id,
                    MonthlySnapshot.year_month < year_month,
                )
                .limit(1)
            ).scalar_one_or_none()
            is not None
        )
    next_year_month = _next_year_month(year_month)
    next_snapshot = session.execute(
        select(MonthlySnapshot).where(
            MonthlySnapshot.year_month == next_year_month,
            MonthlySnapshot.account_id == account_id,
        )
    ).scalar_one_or_none()

    credit_card_accounts = list(
        session.execute(
            select(Account).where(Account.type == "credit").order_by(Account.account_id)
        ).scalars()
    )
    current_assigned_card_ids = [
        card_account.account_id
        for card_account in credit_card_accounts
        if not card_account.is_excluded and card_account.paying_account_id == account_id
    ]
    snapshot_card_ids = [card.account_id for card in cards]
    relevant_account_ids = sorted(
        {account_id, *current_assigned_card_ids, *snapshot_card_ids}
    )
    relevant_plaid_item_ids = _relevant_plaid_item_ids(
        account, cards, credit_card_accounts
    )
    plaid_item_sync_evidence, active_plaid_item_sync_evidence = (
        _load_plaid_item_sync_evidence(session, relevant_plaid_item_ids)
    )
    transactions = list(
        session.execute(
            select(Transaction).where(
                Transaction.account_id.in_(relevant_account_ids),
                Transaction.date >= start_date,
                Transaction.date <= end_date,
            )
        ).scalars()
    )
    missing_paying_cards = [
        card_account
        for card_account in credit_card_accounts
        if not card_account.is_excluded and card_account.paying_account_id is None
    ]
    captured = session.execute(
        select(AccountBalanceSnapshot).where(
            AccountBalanceSnapshot.account_id == account_id,
            AccountBalanceSnapshot.snapshot_date == end_date,
        )
    ).scalar_one_or_none()

    bootstrap_balance = None
    if (
        prior_snapshot is None
        and not has_earlier_snapshot
        and snapshot.starting_balance is None
    ):
        _, prior_month_end = _month_bounds(prior_year_month)
        bootstrap_capture = session.execute(
            select(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.snapshot_date == prior_month_end,
            )
        ).scalar_one_or_none()
        bootstrap_balance = (
            bootstrap_capture.balance_current if bootstrap_capture is not None else None
        )

    starting_balance, provenance = _resolve_starting_balance(
        snapshot, prior_snapshot, bootstrap_balance
    )
    reconciliation_evidence = validate_current_reconciliation(
        session, year_month, account_id
    )
    return _calculate_preview(
        snapshot=snapshot,
        account=account,
        items=items,
        cards=cards,
        credit_card_accounts=credit_card_accounts,
        transactions=transactions,
        plaid_item_sync_evidence=plaid_item_sync_evidence,
        active_plaid_item_sync_evidence=active_plaid_item_sync_evidence,
        missing_paying_cards=missing_paying_cards,
        prior_snapshot=prior_snapshot,
        next_snapshot=next_snapshot,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        has_earlier_snapshot=has_earlier_snapshot,
        captured_balance=captured.balance_current if captured else None,
        now=_as_utc(now or datetime.now(UTC)),
        max_reconciliation_age=max_reconciliation_age,
        reconciliation_evidence=reconciliation_evidence,
    )


def close_snapshot(
    session: Session,
    year_month: str,
    account_id: str,
    *,
    confirm_month: str,
    audit_hash: str,
    now: datetime | None = None,
) -> SnapshotClosePreview:
    """Close one snapshot after revalidating confirmation, hash, and blockers.

    The caller owns the surrounding transaction. This function only flushes, so
    any exception causes the entire close to be rolled back by the session scope.
    """
    if confirm_month != year_month:
        raise ValueError(f"Confirmation must exactly match {year_month}")

    # Pin every preview input to one serializable transaction and lock the prior,
    # current, and next headers in calendar order before recalculating the hash.
    # LOCK is deliberately the first operation after isolation is set: it does
    # not establish an MVCC snapshot, so a close that waits for an admitted sync
    # sees that sync's committed RUNNING/PENDING or terminal evidence.
    session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    acquire_close_coordination_lock(session)
    acquire_transaction_reconciliation_lock(session)
    prior_year_month = _prior_year_month(year_month)
    next_year_month = _next_year_month(year_month)
    locked_snapshots = list(
        session.execute(
            select(MonthlySnapshot)
            .where(
                MonthlySnapshot.year_month.in_(
                    [prior_year_month, year_month, next_year_month]
                ),
                MonthlySnapshot.account_id == account_id,
            )
            .order_by(MonthlySnapshot.year_month)
            .with_for_update()
        ).scalars()
    )
    snapshots_by_month = {
        locked_snapshot.year_month: locked_snapshot
        for locked_snapshot in locked_snapshots
    }
    snapshot = snapshots_by_month.get(year_month)
    if snapshot is None:
        raise ValueError(f"Snapshot for {year_month} / {account_id} not found")

    next_snapshot = snapshots_by_month.get(next_year_month)

    preview = build_close_preview(session, year_month, account_id, now=now)
    if audit_hash != preview.audit_hash:
        raise ValueError("Audit hash mismatch; run a fresh close preview")
    if preview.blockers:
        raise ValueError("Cannot close snapshot: " + " ".join(preview.blockers))
    if preview.closing_balance_to_freeze is None:
        raise ValueError("Cannot close snapshot without a closing balance")

    snapshot.income_total = preview.totals.income_total
    snapshot.expense_total = preview.totals.expense_total
    snapshot.transfer_in_total = preview.totals.transfer_in_total
    snapshot.transfer_out_total = preview.totals.transfer_out_total
    snapshot.reimbursement_in_total = preview.totals.reimbursement_in_total
    snapshot.reimbursement_out_total = preview.totals.reimbursement_out_total
    snapshot.credit_card_total = preview.totals.credit_card_total
    snapshot.net = preview.totals.net
    snapshot.closing_balance = preview.closing_balance_to_freeze
    snapshot.closing_balance_frozen = True
    snapshot.status = SnapshotStatus.CLOSED
    closed_at = _as_utc(now or datetime.now(UTC))
    snapshot.closed_at = closed_at
    if next_snapshot is not None and next_snapshot.starting_balance is None:
        next_snapshot.starting_balance = preview.closing_balance_to_freeze
    session.flush()
    return replace(
        preview,
        status=SnapshotStatus.CLOSED.value,
        next_starting_balance=(
            next_snapshot.starting_balance
            if next_snapshot is not None
            else preview.next_starting_balance
        ),
        closed_at=closed_at,
    )
