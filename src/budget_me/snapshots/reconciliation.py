"""Guarded transaction-to-snapshot reconciliation with immutable receipts."""

from __future__ import annotations

import hashlib
import json
import uuid
from calendar import monthrange
from dataclasses import dataclass, replace
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any

from sqlalchemy import or_, select, text
from sqlalchemy.orm import Session

from budget_me.db.models.account import Account
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.reimbursement_link import ReimbursementLink
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.snapshot_reconciliation import (
    SnapshotLineItemMatch,
    SnapshotLineItemResolution,
    SnapshotReconciliationRun,
    SnapshotTransactionAllocation,
    SnapshotTransactionResolution,
)
from budget_me.db.models.transaction import Transaction
from budget_me.db.sync_coordination import (
    acquire_close_coordination_lock,
    acquire_transaction_reconciliation_lock,
)
from budget_me.snapshots.card_payment_evidence import actual_matches_feed_or_evidence
from budget_me.snapshots.reconciliation_manifest import (
    LineItemDecision,
    ReconciliationAllocation,
    ReconciliationManifest,
    TransactionDecision,
    manifest_decision_hash,
)

_ZERO = Decimal("0.00")
_INPUT_VERSION = 2
_OUTFLOW_TYPES = {"expense", "transfer_out", "reimbursement_out", "card_payment"}
_INFLOW_TYPES = {"income", "transfer_in", "reimbursement_in"}
_LINE_FLOW_TYPES = {"income", "expense", "transfer_in", "transfer_out"}
_CARD_PAYMENT_DETAILED = "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
_LEGACY_CARD_PAYMENT_DETAILED = "Payment, Credit Card"
_SNAPSHOT_TABLE_LOCK = text("LOCK TABLE monthly_snapshots IN SHARE ROW EXCLUSIVE MODE")
_INPUT_TABLE_LOCKS = (
    text("LOCK TABLE accounts IN SHARE MODE"),
    text("LOCK TABLE snapshot_line_items IN SHARE MODE"),
    text("LOCK TABLE snapshot_credit_cards IN SHARE MODE"),
    text("LOCK TABLE reimbursement_links IN SHARE MODE"),
)


def _enum_value(value: Any) -> Any:
    return value.value if isinstance(value, Enum) else value


def _money(value: Decimal | None) -> str | None:
    return None if value is None else format(value, ".2f")


def _timestamp(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)


def _month_bounds(year_month: str) -> tuple[date, date]:
    try:
        parsed = datetime.strptime(year_month, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise ValueError("year_month must use YYYY-MM") from exc
    if parsed.strftime("%Y-%m") != year_month:
        raise ValueError("year_month must use YYYY-MM")
    return (
        date(parsed.year, parsed.month, 1),
        date(parsed.year, parsed.month, monthrange(parsed.year, parsed.month)[1]),
    )


def _raw_card_payment_detailed(transaction: Transaction) -> str | None:
    raw = transaction.raw or {}
    category = raw.get("personal_finance_category")
    if not isinstance(category, dict):
        return None
    detailed = category.get("detailed")
    return detailed if isinstance(detailed, str) else None


def _is_card_payment(transaction: Transaction) -> bool:
    return transaction.amount < _ZERO and (
        _raw_card_payment_detailed(transaction) == _CARD_PAYMENT_DETAILED
        or transaction.category_detailed
        in {_CARD_PAYMENT_DETAILED, _LEGACY_CARD_PAYMENT_DETAILED}
    )


def _sha256(payload: Any) -> str:
    encoded = json.dumps(
        payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode()
    return hashlib.sha256(encoded).hexdigest()


@dataclass(frozen=True)
class ReconciliationTotals:
    """Actual normalized cash-flow totals represented by one manifest."""

    income_total: Decimal = _ZERO
    expense_total: Decimal = _ZERO
    transfer_in_total: Decimal = _ZERO
    transfer_out_total: Decimal = _ZERO
    reimbursement_in_total: Decimal = _ZERO
    reimbursement_out_total: Decimal = _ZERO
    credit_card_total: Decimal = _ZERO
    net: Decimal = _ZERO

    def to_dict(self) -> dict[str, str]:
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
class SnapshotReconciliationPreview:
    """Aggregate-only validation result for one private manifest."""

    year_month: str
    account_id: str
    snapshot_id: str | None
    manifest_hash: str
    input_hash: str
    totals: ReconciliationTotals
    posted_transaction_count: int
    allocation_count: int
    line_item_count: int
    remaining_item_count: int
    remaining_item_total: Decimal
    pending_transaction_count: int
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    current_run_id: str | None = None
    is_idempotent: bool = False

    @property
    def can_apply(self) -> bool:
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        return {
            "year_month": self.year_month,
            "account_id": self.account_id,
            "snapshot_id": self.snapshot_id,
            "manifest_hash": self.manifest_hash,
            "input_hash": self.input_hash,
            "totals": self.totals.to_dict(),
            "counts": {
                "posted_transactions": self.posted_transaction_count,
                "allocations": self.allocation_count,
                "line_items": self.line_item_count,
                "remaining_items": self.remaining_item_count,
                "pending_transactions": self.pending_transaction_count,
            },
            "remaining_item_total": _money(self.remaining_item_total) or "0.00",
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "can_apply": self.can_apply,
            "current_run_id": self.current_run_id,
            "is_idempotent": self.is_idempotent,
        }


@dataclass(frozen=True)
class CurrentReconciliationEvidence:
    """Close-facing proof that the current immutable receipt remains valid."""

    run_id: str | None
    reconciled_at: datetime | None
    manifest_hash: str | None
    input_hash: str
    totals: ReconciliationTotals | None
    blockers: tuple[str, ...]
    version: int | None = None
    run_input_hash: str | None = None
    recomputed_manifest_hash: str | None = None
    posted_transaction_count: int | None = None
    allocation_count: int | None = None
    line_item_count: int | None = None
    has_remaining_items: bool | None = None

    @property
    def is_valid(self) -> bool:
        return not self.blockers and self.run_id is not None

    def audit_dict(self) -> dict[str, Any]:
        return {
            "run_id": self.run_id,
            "reconciled_at": _timestamp(self.reconciled_at),
            "manifest_hash": self.manifest_hash,
            "recomputed_manifest_hash": self.recomputed_manifest_hash,
            "input_hash": self.input_hash,
            "run_input_hash": self.run_input_hash,
            "version": self.version,
            "counts": {
                "posted_transactions": self.posted_transaction_count,
                "allocations": self.allocation_count,
                "line_items": self.line_item_count,
            },
            "has_remaining_items": self.has_remaining_items,
            "totals": self.totals.to_dict() if self.totals is not None else None,
            "blockers": list(self.blockers),
        }


@dataclass(frozen=True)
class _ReconciliationInputs:
    account: Account | None
    snapshot: MonthlySnapshot | None
    line_items: tuple[SnapshotLineItem, ...]
    cards: tuple[SnapshotCreditCard, ...]
    credit_accounts: tuple[Account, ...]
    transactions: tuple[Transaction, ...]
    reimbursement_links: tuple[ReimbursementLink, ...]
    current_run: SnapshotReconciliationRun | None


def _transaction_payload(transaction: Transaction) -> dict[str, Any]:
    """Return every logical fact on which an operator decision may depend."""
    return {
        "id": str(transaction.id),
        "plaid_transaction_id": transaction.plaid_transaction_id,
        "account_id": transaction.account_id,
        "date": transaction.date.isoformat(),
        "authorized_date": (
            transaction.authorized_date.isoformat()
            if transaction.authorized_date is not None
            else None
        ),
        "amount": _money(transaction.amount),
        "currency": transaction.iso_currency_code,
        "name": transaction.name,
        "merchant_name": transaction.merchant_name,
        "normalized_merchant": transaction.normalized_merchant,
        "pending": transaction.pending,
        "category_primary": transaction.category_primary,
        "category_detailed": transaction.category_detailed,
        "raw_card_payment_detailed": _raw_card_payment_detailed(transaction),
        "budget_category": transaction.budget_category,
        "reviewed": transaction.reviewed,
        "reviewed_at": _timestamp(transaction.reviewed_at),
        "reimbursable": transaction.reimbursable,
        "reimbursement_status": transaction.reimbursement_status,
        "reimbursement_note": transaction.reimbursement_note,
        "project_tag": transaction.project_tag,
        "updated_at": _timestamp(transaction.updated_at),
    }


def transaction_fingerprint(transaction: Transaction) -> str:
    """Hash copied source facts without persisting merchant/private descriptions."""
    return _sha256(_transaction_payload(transaction))


def _load_inputs(
    session: Session, year_month: str, account_id: str
) -> _ReconciliationInputs:
    start_date, end_date = _month_bounds(year_month)
    with session.no_autoflush:
        account = session.execute(
            select(Account).where(Account.account_id == account_id)
        ).scalar_one_or_none()
        snapshot = session.execute(
            select(MonthlySnapshot).where(
                MonthlySnapshot.year_month == year_month,
                MonthlySnapshot.account_id == account_id,
            )
        ).scalar_one_or_none()
        line_items: tuple[SnapshotLineItem, ...] = ()
        cards: tuple[SnapshotCreditCard, ...] = ()
        current_run = None
        if snapshot is not None:
            line_items = tuple(
                session.execute(
                    select(SnapshotLineItem)
                    .where(SnapshotLineItem.snapshot_id == snapshot.id)
                    .order_by(SnapshotLineItem.id)
                ).scalars()
            )
            cards = tuple(
                session.execute(
                    select(SnapshotCreditCard)
                    .where(SnapshotCreditCard.snapshot_id == snapshot.id)
                    .order_by(SnapshotCreditCard.id)
                ).scalars()
            )
            current_run = session.execute(
                select(SnapshotReconciliationRun).where(
                    SnapshotReconciliationRun.snapshot_id == snapshot.id,
                    SnapshotReconciliationRun.is_current.is_(True),
                )
            ).scalar_one_or_none()

        credit_accounts = tuple(
            session.execute(
                select(Account)
                .where(Account.type == "credit")
                .order_by(Account.account_id)
            ).scalars()
        )
        snapshot_card_ids = {card.account_id for card in cards}
        relevant_credit_accounts = tuple(
            card
            for card in credit_accounts
            if card.account_id in snapshot_card_ids
            or (not card.is_excluded and card.paying_account_id == account_id)
        )
        relevant_account_ids = {
            account_id,
            *(card.account_id for card in relevant_credit_accounts),
            *snapshot_card_ids,
        }
        transactions = tuple(
            session.execute(
                select(Transaction)
                .where(
                    Transaction.account_id.in_(sorted(relevant_account_ids)),
                    Transaction.date >= start_date,
                    Transaction.date <= end_date,
                )
                .order_by(Transaction.id)
            ).scalars()
        )
        transaction_ids = [transaction.id for transaction in transactions]
        links: tuple[ReimbursementLink, ...] = ()
        if transaction_ids:
            links = tuple(
                session.execute(
                    select(ReimbursementLink)
                    .where(
                        or_(
                            ReimbursementLink.expense_transaction_id.in_(
                                transaction_ids
                            ),
                            ReimbursementLink.deposit_transaction_id.in_(
                                transaction_ids
                            ),
                        )
                    )
                    .order_by(ReimbursementLink.id)
                ).scalars()
            )

    return _ReconciliationInputs(
        account=account,
        snapshot=snapshot,
        line_items=line_items,
        cards=cards,
        credit_accounts=relevant_credit_accounts,
        transactions=transactions,
        reimbursement_links=links,
        current_run=current_run,
    )


def _input_payload(inputs: _ReconciliationInputs) -> dict[str, Any]:
    account = inputs.account
    snapshot = inputs.snapshot
    return {
        "version": _INPUT_VERSION,
        "account": None
        if account is None
        else {
            "id": str(account.id),
            "account_id": account.account_id,
            "type": account.type,
            "subtype": account.subtype,
            "is_excluded": account.is_excluded,
            "plaid_item_id": str(account.plaid_item_id),
        },
        "snapshot": None
        if snapshot is None
        else {
            "id": str(snapshot.id),
            "year_month": snapshot.year_month,
            "account_id": snapshot.account_id,
            "status": _enum_value(snapshot.status),
            "starting_balance": _money(snapshot.starting_balance),
            "closing_balance": _money(snapshot.closing_balance),
            "closing_balance_frozen": snapshot.closing_balance_frozen,
        },
        "line_items": [
            {
                "id": str(item.id),
                "source_item_id": (
                    str(item.source_item_id)
                    if item.source_item_id is not None
                    else None
                ),
                "item_type": item.item_type,
                "name": item.name,
                "amount": _money(item.amount),
                "category": item.category,
                "is_one_time": item.is_one_time,
                "skipped": item.skipped,
                "updated_at": _timestamp(item.updated_at),
            }
            for item in inputs.line_items
        ],
        "cards": [
            {
                "id": str(card.id),
                "account_id": card.account_id,
                "statement_balance": _money(card.statement_balance),
                "payment_strategy": card.payment_strategy,
                "fixed_payment_amount": _money(card.fixed_payment_amount),
                "calculated_payment": _money(card.calculated_payment),
                "due_date": card.due_date.isoformat() if card.due_date else None,
                "actual_payment_amount": _money(card.actual_payment_amount),
                "actual_payment_date": (
                    card.actual_payment_date.isoformat()
                    if card.actual_payment_date
                    else None
                ),
                "actual_payment_source": getattr(card, "actual_payment_source", None),
                "actual_payment_transaction_id": str(
                    getattr(card, "actual_payment_transaction_id", None)
                ),
                "actual_payment_note": getattr(card, "actual_payment_note", None),
                "updated_at": _timestamp(card.updated_at),
            }
            for card in inputs.cards
        ],
        "credit_card_membership": [
            {
                "account_id": card.account_id,
                "type": card.type,
                "is_excluded": card.is_excluded,
                "paying_account_id": card.paying_account_id,
                "plaid_item_id": str(card.plaid_item_id),
                "updated_at": _timestamp(card.updated_at),
            }
            for card in inputs.credit_accounts
        ],
        "transactions": [
            _transaction_payload(transaction) for transaction in inputs.transactions
        ],
        "reimbursement_links": [
            {
                "id": str(link.id),
                "expense_transaction_id": str(link.expense_transaction_id),
                "deposit_transaction_id": str(link.deposit_transaction_id),
                "amount": _money(link.amount),
                "linked_at": _timestamp(link.linked_at),
            }
            for link in inputs.reimbursement_links
        ],
    }


def _totals_from_amounts(amounts: dict[str, Decimal]) -> ReconciliationTotals:
    net = (
        amounts["income"]
        + amounts["transfer_in"]
        + amounts["reimbursement_in"]
        - amounts["expense"]
        - amounts["transfer_out"]
        - amounts["reimbursement_out"]
        - amounts["card_payment"]
    )
    return ReconciliationTotals(
        income_total=amounts["income"],
        expense_total=amounts["expense"],
        transfer_in_total=amounts["transfer_in"],
        transfer_out_total=amounts["transfer_out"],
        reimbursement_in_total=amounts["reimbursement_in"],
        reimbursement_out_total=amounts["reimbursement_out"],
        credit_card_total=amounts["card_payment"],
        net=net,
    )


def _prepare_preview(
    inputs: _ReconciliationInputs, manifest: ReconciliationManifest
) -> SnapshotReconciliationPreview:
    manifest_hash = manifest_decision_hash(manifest)
    input_hash = _sha256(_input_payload(inputs))
    blockers: list[str] = []
    warnings: list[str] = []
    snapshot = inputs.snapshot
    account = inputs.account

    if manifest.year_month != (
        snapshot.year_month if snapshot is not None else manifest.year_month
    ):
        blockers.append("Manifest month does not match the snapshot.")
    if manifest.account_id != (
        account.account_id if account is not None else manifest.account_id
    ):
        blockers.append("Manifest account does not match the target account.")
    if account is None:
        blockers.append("Target account was not found.")
    else:
        if account.type != "depository":
            blockers.append("Target account is not a depository account.")
        if account.is_excluded:
            blockers.append("Target account is excluded from monthly snapshots.")
    if snapshot is None:
        blockers.append("Target snapshot was not found.")
    elif snapshot.status != SnapshotStatus.OPEN:
        blockers.append("Only an open snapshot can be reconciled.")

    paying_transactions = [
        transaction
        for transaction in inputs.transactions
        if transaction.account_id == manifest.account_id
    ]
    pending_transactions = [
        transaction for transaction in paying_transactions if transaction.pending
    ]
    posted_transactions = [
        transaction for transaction in paying_transactions if not transaction.pending
    ]
    decisions_by_id = {
        decision.transaction_id: decision for decision in manifest.transaction_decisions
    }
    posted_by_id = {transaction.id: transaction for transaction in posted_transactions}
    missing_decisions = set(posted_by_id) - set(decisions_by_id)
    extra_decisions = set(decisions_by_id) - set(posted_by_id)
    if missing_decisions:
        blockers.append(
            f"Manifest is missing {len(missing_decisions)} posted transaction decision(s)."
        )
    if extra_decisions:
        blockers.append(
            f"Manifest includes {len(extra_decisions)} out-of-scope transaction decision(s)."
        )
    if pending_transactions:
        blockers.append(
            f"{len(pending_transactions)} paying-account transaction(s) are pending."
        )

    amounts = {
        "income": _ZERO,
        "expense": _ZERO,
        "transfer_in": _ZERO,
        "transfer_out": _ZERO,
        "reimbursement_in": _ZERO,
        "reimbursement_out": _ZERO,
        "card_payment": _ZERO,
    }
    allocation_by_locator: dict[tuple[uuid.UUID, int], ReconciliationAllocation] = {}
    unlocked_count = 0
    for transaction in posted_transactions:
        decision = decisions_by_id.get(transaction.id)
        if decision is None:
            continue
        if not transaction.reviewed:
            blockers.append("One or more posted transactions remain unreviewed.")
        normalized_category = (transaction.budget_category or "").strip().casefold()
        if not normalized_category or normalized_category == "uncategorized":
            blockers.append("One or more posted transactions remain uncategorized.")
        if not decision.manual_locked:
            unlocked_count += 1
        source_description = transaction.merchant_name or transaction.name
        if any(
            (
                decision.source_date is not None
                and decision.source_date != transaction.date.isoformat(),
                decision.source_amount is not None
                and decision.source_amount != transaction.amount,
                decision.source_description is not None
                and decision.source_description != source_description,
                decision.source_budget_category is not None
                and decision.source_budget_category
                != (transaction.budget_category or "uncategorized"),
                decision.source_reviewed is not None
                and decision.source_reviewed != transaction.reviewed,
            )
        ):
            blockers.append(
                "One or more private transaction source hints are stale or edited."
            )

        allocated = sum(
            (allocation.amount for allocation in decision.allocations), start=_ZERO
        )
        if allocated != abs(transaction.amount):
            blockers.append(
                "Every transaction allocation must exactly equal its source magnitude."
            )
        if transaction.amount == _ZERO and decision.allocations:
            blockers.append("Zero-amount transactions cannot contain allocations.")
        if transaction.amount > _ZERO and any(
            allocation.flow_type not in _OUTFLOW_TYPES
            for allocation in decision.allocations
        ):
            blockers.append("A cash-out transaction contains an inflow allocation.")
        if transaction.amount < _ZERO and any(
            allocation.flow_type not in _INFLOW_TYPES
            for allocation in decision.allocations
        ):
            blockers.append("A cash-in transaction contains an outflow allocation.")
        for allocation_index, allocation in enumerate(decision.allocations):
            allocation_by_locator[(transaction.id, allocation_index)] = allocation
            amounts[allocation.flow_type] += allocation.amount

    if unlocked_count:
        blockers.append(
            f"{unlocked_count} transaction decision(s) are not manually locked."
        )

    items_by_id = {item.id: item for item in inputs.line_items}
    line_decisions_by_id = {
        decision.line_item_id: decision for decision in manifest.line_item_decisions
    }
    missing_line_decisions = set(items_by_id) - set(line_decisions_by_id)
    extra_line_decisions = set(line_decisions_by_id) - set(items_by_id)
    if missing_line_decisions:
        blockers.append(
            f"Manifest is missing {len(missing_line_decisions)} line-item decision(s)."
        )
    if extra_line_decisions:
        blockers.append(
            f"Manifest includes {len(extra_line_decisions)} stale line-item decision(s)."
        )

    allocation_match_totals: dict[tuple[uuid.UUID, int], Decimal] = {}
    remaining_count = 0
    remaining_total = _ZERO
    for item in inputs.line_items:
        decision = line_decisions_by_id.get(item.id)
        if decision is None:
            continue
        if item.amount <= _ZERO:
            blockers.append("Snapshot line items must have positive amounts.")
        if item.item_type not in _LINE_FLOW_TYPES:
            blockers.append("Snapshot contains an unsupported line-item type.")
        if any(
            (
                decision.source_name is not None and decision.source_name != item.name,
                decision.source_item_type is not None
                and decision.source_item_type != item.item_type,
                decision.source_planned_amount is not None
                and decision.source_planned_amount != item.amount,
            )
        ):
            blockers.append(
                "One or more private line-item source hints are stale or edited."
            )

        matched_total = _ZERO
        for match in decision.matches:
            locator = (match.transaction_id, match.allocation_index)
            allocation = allocation_by_locator.get(locator)
            if allocation is None:
                blockers.append("A line-item match references a missing allocation.")
                continue
            if allocation.flow_type != item.item_type:
                blockers.append(
                    "A line-item match uses an incompatible cash-flow type."
                )
            matched_total += match.amount
            allocation_match_totals[locator] = (
                allocation_match_totals.get(locator, _ZERO) + match.amount
            )

        if decision.resolution == "fulfilled":
            if not decision.matches:
                blockers.append(
                    "Fulfilled line items must reference at least one actual allocation."
                )
        elif decision.resolution == "remaining":
            remaining_count += 1
            remaining_total += decision.remaining_amount
            if matched_total + decision.remaining_amount != item.amount:
                blockers.append(
                    "Partially matched line items must balance to their planned amount."
                )
        elif decision.matches:
            blockers.append("Skipped or adjusted line items cannot contain matches.")

        if decision.resolution == "adjustment":
            if (
                decision.adjustment_flow_type is not None
                and decision.adjustment_amount is not None
            ):
                amounts[decision.adjustment_flow_type] += decision.adjustment_amount

    for locator, matched_total in allocation_match_totals.items():
        if matched_total > allocation_by_locator[locator].amount:
            blockers.append("Line-item matches exceed a transaction allocation.")

    snapshot_card_ids = {card.account_id for card in inputs.cards}
    assigned_card_ids = {
        card.account_id
        for card in inputs.credit_accounts
        if not card.is_excluded and card.paying_account_id == manifest.account_id
    }
    if snapshot_card_ids != assigned_card_ids:
        blockers.append(
            "Snapshot credit-card membership does not match current assignments."
        )
    missing_actual_cards = sum(
        card.actual_payment_amount is None for card in inputs.cards
    )
    if missing_actual_cards:
        blockers.append(
            f"{missing_actual_cards} snapshot credit card(s) have no posted actual amount."
        )
    actual_card_total = sum(
        (card.actual_payment_amount or _ZERO for card in inputs.cards), start=_ZERO
    )
    if amounts["card_payment"] != actual_card_total:
        blockers.append(
            "Manifest card-payment allocations do not match snapshot posted actuals."
        )

    pending_card_payment_count = 0
    mismatched_card_count = 0
    for card in inputs.cards:
        card_transactions = [
            transaction
            for transaction in inputs.transactions
            if transaction.account_id == card.account_id
            and _is_card_payment(transaction)
        ]
        pending_card_payments = [
            transaction for transaction in card_transactions if transaction.pending
        ]
        pending_card_payment_count += len(pending_card_payments)
        posted_card_payments = [
            transaction for transaction in card_transactions if not transaction.pending
        ]
        expected_amount = sum(
            (abs(transaction.amount) for transaction in posted_card_payments),
            start=_ZERO,
        )
        expected_date = max(
            (transaction.date for transaction in posted_card_payments), default=None
        )
        if not actual_matches_feed_or_evidence(
            card,
            expected_amount,
            expected_date,
            transactions=inputs.transactions,
            paying_account_id=inputs.account.account_id,
        ):
            mismatched_card_count += 1
    if pending_card_payment_count:
        blockers.append(
            f"{pending_card_payment_count} card-side payment(s) are pending."
        )
    if mismatched_card_count:
        blockers.append(
            f"{mismatched_card_count} snapshot card actual(s) do not match "
            "posted card-side payments."
        )

    if remaining_count:
        warnings.append(
            f"{remaining_count} planned line item(s) remain unresolved; apply is allowed "
            "but close will stay blocked."
        )
    totals = _totals_from_amounts(amounts)
    current_run = inputs.current_run
    return SnapshotReconciliationPreview(
        year_month=manifest.year_month,
        account_id=manifest.account_id,
        snapshot_id=str(snapshot.id) if snapshot is not None else None,
        manifest_hash=manifest_hash,
        input_hash=input_hash,
        totals=totals,
        posted_transaction_count=len(posted_transactions),
        allocation_count=sum(
            len(decision.allocations) for decision in manifest.transaction_decisions
        ),
        line_item_count=len(inputs.line_items),
        remaining_item_count=remaining_count,
        remaining_item_total=remaining_total,
        pending_transaction_count=len(pending_transactions),
        blockers=tuple(dict.fromkeys(blockers)),
        warnings=tuple(dict.fromkeys(warnings)),
        current_run_id=str(current_run.id) if current_run is not None else None,
        is_idempotent=bool(
            current_run is not None
            and current_run.manifest_hash == manifest_hash
            and current_run.input_hash == input_hash
        ),
    )


def build_reconciliation_preview(
    session: Session, manifest: ReconciliationManifest
) -> SnapshotReconciliationPreview:
    """Validate a private manifest without flushing or mutating the session."""
    inputs = _load_inputs(session, manifest.year_month, manifest.account_id)
    return _prepare_preview(inputs, manifest)


def _persist_manifest(
    session: Session,
    *,
    snapshot: MonthlySnapshot,
    inputs: _ReconciliationInputs,
    manifest: ReconciliationManifest,
    preview: SnapshotReconciliationPreview,
    reconciled_at: datetime,
) -> SnapshotReconciliationRun:
    current_runs = list(
        session.execute(
            select(SnapshotReconciliationRun)
            .where(
                SnapshotReconciliationRun.snapshot_id == snapshot.id,
                SnapshotReconciliationRun.is_current.is_(True),
            )
            .with_for_update()
        ).scalars()
    )
    for current in current_runs:
        current.is_current = False
    session.flush()

    totals = preview.totals
    run = SnapshotReconciliationRun(
        id=uuid.uuid4(),
        snapshot_id=snapshot.id,
        version=manifest.version,
        is_current=True,
        manifest_hash=preview.manifest_hash,
        input_hash=preview.input_hash,
        reconciled_at=reconciled_at,
        income_total=totals.income_total,
        expense_total=totals.expense_total,
        transfer_in_total=totals.transfer_in_total,
        transfer_out_total=totals.transfer_out_total,
        reimbursement_in_total=totals.reimbursement_in_total,
        reimbursement_out_total=totals.reimbursement_out_total,
        credit_card_total=totals.credit_card_total,
        net=totals.net,
        posted_transaction_count=preview.posted_transaction_count,
        allocation_count=preview.allocation_count,
        line_item_count=preview.line_item_count,
        has_remaining_items=preview.remaining_item_count > 0,
    )
    session.add(run)

    transactions_by_id = {
        transaction.id: transaction
        for transaction in inputs.transactions
        if transaction.account_id == manifest.account_id and not transaction.pending
    }
    allocation_ids: dict[tuple[uuid.UUID, int], uuid.UUID] = {}
    for decision in manifest.transaction_decisions:
        transaction = transactions_by_id[decision.transaction_id]
        resolution_id = uuid.uuid4()
        session.add(
            SnapshotTransactionResolution(
                id=resolution_id,
                run_id=run.id,
                transaction_id=transaction.id,
                fingerprint=transaction_fingerprint(transaction),
                account_id=transaction.account_id,
                transaction_date=transaction.date,
                signed_amount=transaction.amount,
                currency=transaction.iso_currency_code,
                source_updated_at=transaction.updated_at,
                classification_source="manifest",
                manual_locked=decision.manual_locked,
                pair_group_id=decision.pair_group_id,
            )
        )
        for allocation_index, allocation in enumerate(decision.allocations):
            allocation_id = uuid.uuid4()
            allocation_ids[(decision.transaction_id, allocation_index)] = allocation_id
            session.add(
                SnapshotTransactionAllocation(
                    id=allocation_id,
                    resolution_id=resolution_id,
                    allocation_index=allocation_index,
                    flow_type=allocation.flow_type,
                    amount=allocation.amount,
                    category=allocation.category,
                )
            )

    for decision in manifest.line_item_decisions:
        resolution_id = uuid.uuid4()
        session.add(
            SnapshotLineItemResolution(
                id=resolution_id,
                run_id=run.id,
                line_item_id=decision.line_item_id,
                resolution=decision.resolution,
                remaining_amount=decision.remaining_amount,
                adjustment_flow_type=decision.adjustment_flow_type,
                adjustment_amount=decision.adjustment_amount,
                authorization_note=decision.authorization_note,
            )
        )
        for match in decision.matches:
            session.add(
                SnapshotLineItemMatch(
                    id=uuid.uuid4(),
                    resolution_id=resolution_id,
                    allocation_id=allocation_ids[
                        (match.transaction_id, match.allocation_index)
                    ],
                    amount=match.amount,
                )
            )
    return run


def apply_reconciliation(
    session: Session,
    manifest: ReconciliationManifest,
    *,
    confirm_month: str,
    input_hash: str,
    now: datetime | None = None,
) -> SnapshotReconciliationPreview:
    """Persist one immutable receipt and refresh cached actual totals.

    The caller owns commit/rollback. The private manifest itself is never stored.
    """
    if confirm_month != manifest.year_month:
        raise ValueError(f"Confirmation must exactly match {manifest.year_month}")

    session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    acquire_close_coordination_lock(session)
    acquire_transaction_reconciliation_lock(session)
    session.execute(_SNAPSHOT_TABLE_LOCK)
    snapshot = session.execute(
        select(MonthlySnapshot)
        .where(
            MonthlySnapshot.year_month == manifest.year_month,
            MonthlySnapshot.account_id == manifest.account_id,
        )
        .with_for_update()
    ).scalar_one_or_none()
    for lock_statement in _INPUT_TABLE_LOCKS:
        session.execute(lock_statement)

    inputs = _load_inputs(session, manifest.year_month, manifest.account_id)
    preview = _prepare_preview(inputs, manifest)
    if input_hash != preview.input_hash:
        raise ValueError("Input hash mismatch; run a fresh reconciliation preview")
    if preview.blockers:
        raise ValueError("Cannot apply reconciliation: " + " ".join(preview.blockers))
    if snapshot is None:
        raise ValueError("Snapshot disappeared during reconciliation")
    if preview.is_idempotent and inputs.current_run is not None:
        evidence = validate_current_reconciliation(
            session, manifest.year_month, manifest.account_id
        )
        if evidence.blockers:
            raise ValueError(
                "Cannot reuse reconciliation receipt: " + " ".join(evidence.blockers)
            )
        return preview

    reconciled_at = _as_utc(now or datetime.now(UTC))
    run = _persist_manifest(
        session,
        snapshot=snapshot,
        inputs=inputs,
        manifest=manifest,
        preview=preview,
        reconciled_at=reconciled_at,
    )
    totals = preview.totals
    snapshot.income_total = totals.income_total
    snapshot.expense_total = totals.expense_total
    snapshot.transfer_in_total = totals.transfer_in_total
    snapshot.transfer_out_total = totals.transfer_out_total
    snapshot.reimbursement_in_total = totals.reimbursement_in_total
    snapshot.reimbursement_out_total = totals.reimbursement_out_total
    snapshot.credit_card_total = totals.credit_card_total
    snapshot.net = totals.net
    snapshot.last_synced_at = reconciled_at
    session.flush()
    return replace(
        preview,
        current_run_id=str(run.id),
        is_idempotent=False,
    )


def _manifest_from_run(run: SnapshotReconciliationRun) -> ReconciliationManifest:
    allocation_locators: dict[uuid.UUID, tuple[uuid.UUID, int]] = {}
    transaction_decisions: list[dict[str, Any]] = []
    for resolution in sorted(
        run.transaction_resolutions, key=lambda value: str(value.transaction_id)
    ):
        allocations = sorted(
            resolution.allocations, key=lambda value: value.allocation_index
        )
        for allocation in allocations:
            allocation_locators[allocation.id] = (
                resolution.transaction_id,
                allocation.allocation_index,
            )
        transaction_decisions.append(
            {
                "transaction_id": str(resolution.transaction_id),
                "manual_locked": resolution.manual_locked,
                "pair_group_id": (
                    str(resolution.pair_group_id)
                    if resolution.pair_group_id is not None
                    else None
                ),
                "allocations": [
                    {
                        "flow_type": allocation.flow_type,
                        "amount": _money(allocation.amount),
                        "category": allocation.category,
                    }
                    for allocation in allocations
                ],
            }
        )

    line_item_decisions: list[dict[str, Any]] = []
    for resolution in sorted(
        run.line_item_resolutions, key=lambda value: str(value.line_item_id)
    ):
        line_item_decisions.append(
            {
                "line_item_id": str(resolution.line_item_id),
                "resolution": resolution.resolution,
                "remaining_amount": _money(resolution.remaining_amount),
                "adjustment_flow_type": resolution.adjustment_flow_type,
                "adjustment_amount": _money(resolution.adjustment_amount),
                "authorization_note": resolution.authorization_note,
                "matches": [
                    {
                        "transaction_id": str(
                            allocation_locators[match.allocation_id][0]
                        ),
                        "allocation_index": allocation_locators[match.allocation_id][1],
                        "amount": _money(match.amount),
                    }
                    for match in sorted(
                        resolution.matches,
                        key=lambda value: (
                            str(allocation_locators[value.allocation_id][0]),
                            allocation_locators[value.allocation_id][1],
                        ),
                    )
                ],
            }
        )
    return ReconciliationManifest.model_validate(
        {
            "version": run.version,
            "year_month": run.snapshot.year_month,
            "account_id": run.snapshot.account_id,
            "transaction_decisions": transaction_decisions,
            "line_item_decisions": line_item_decisions,
        }
    )


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


def validate_current_reconciliation(
    session: Session, year_month: str, account_id: str
) -> CurrentReconciliationEvidence:
    """Rebuild and validate the current receipt against all live logical inputs."""
    inputs = _load_inputs(session, year_month, account_id)
    input_hash = _sha256(_input_payload(inputs))
    run = inputs.current_run
    if run is None:
        return CurrentReconciliationEvidence(
            run_id=None,
            reconciled_at=None,
            manifest_hash=None,
            input_hash=input_hash,
            totals=None,
            blockers=("No current immutable reconciliation receipt exists.",),
        )

    blockers: list[str] = []
    totals = _run_totals(run)
    try:
        persisted_manifest = _manifest_from_run(run)
        persisted_hash = manifest_decision_hash(persisted_manifest)
        rebuilt = _prepare_preview(inputs, persisted_manifest)
    except Exception:
        persisted_hash = None
        rebuilt = None
        blockers.append("Current reconciliation receipt cannot be reconstructed.")

    if run.input_hash != input_hash:
        blockers.append("Current reconciliation receipt is stale for database inputs.")
    if persisted_hash != run.manifest_hash:
        blockers.append("Current reconciliation receipt decision hash is invalid.")
    if rebuilt is not None:
        if rebuilt.blockers:
            blockers.append("Current reconciliation receipt no longer validates.")
        if rebuilt.totals != totals:
            blockers.append("Current reconciliation receipt totals are inconsistent.")
        if rebuilt.posted_transaction_count != run.posted_transaction_count:
            blockers.append("Current reconciliation transaction count is inconsistent.")
        if rebuilt.allocation_count != run.allocation_count:
            blockers.append("Current reconciliation allocation count is inconsistent.")
        if rebuilt.line_item_count != run.line_item_count:
            blockers.append("Current reconciliation line-item count is inconsistent.")
        if (rebuilt.remaining_item_count > 0) != run.has_remaining_items:
            blockers.append(
                "Current reconciliation remaining-item state is inconsistent."
            )
    current_transactions = {
        transaction.id: transaction
        for transaction in inputs.transactions
        if transaction.account_id == account_id and not transaction.pending
    }
    copied_facts_valid = len(current_transactions) == len(run.transaction_resolutions)
    for resolution in run.transaction_resolutions:
        transaction = current_transactions.get(resolution.transaction_id)
        if transaction is None:
            copied_facts_valid = False
            continue
        copied_facts_valid = copied_facts_valid and all(
            (
                resolution.fingerprint == transaction_fingerprint(transaction),
                resolution.account_id == transaction.account_id,
                resolution.transaction_date == transaction.date,
                resolution.signed_amount == transaction.amount,
                resolution.currency == transaction.iso_currency_code,
                _as_utc(resolution.source_updated_at)
                == _as_utc(transaction.updated_at),
                resolution.classification_source == "manifest",
                resolution.manual_locked,
            )
        )
    if not copied_facts_valid:
        blockers.append("Current reconciliation copied source facts are invalid.")
    if run.has_remaining_items:
        blockers.append("Planned line items remain unresolved in reconciliation.")

    snapshot = inputs.snapshot
    if snapshot is None:
        blockers.append("Reconciled snapshot no longer exists.")
    else:
        if snapshot.last_synced_at is None or _as_utc(
            snapshot.last_synced_at
        ) != _as_utc(run.reconciled_at):
            blockers.append("Snapshot reconciliation timestamp does not match receipt.")
        cached = ReconciliationTotals(
            income_total=snapshot.income_total or _ZERO,
            expense_total=snapshot.expense_total or _ZERO,
            transfer_in_total=snapshot.transfer_in_total or _ZERO,
            transfer_out_total=snapshot.transfer_out_total or _ZERO,
            reimbursement_in_total=snapshot.reimbursement_in_total,
            reimbursement_out_total=snapshot.reimbursement_out_total,
            credit_card_total=snapshot.credit_card_total or _ZERO,
            net=snapshot.net or _ZERO,
        )
        if cached != totals:
            blockers.append(
                "Snapshot cached totals do not match reconciliation receipt."
            )

    return CurrentReconciliationEvidence(
        run_id=str(run.id),
        reconciled_at=run.reconciled_at,
        manifest_hash=run.manifest_hash,
        input_hash=input_hash,
        totals=totals,
        blockers=tuple(dict.fromkeys(blockers)),
        version=run.version,
        run_input_hash=run.input_hash,
        recomputed_manifest_hash=persisted_hash,
        posted_transaction_count=run.posted_transaction_count,
        allocation_count=run.allocation_count,
        line_item_count=run.line_item_count,
        has_remaining_items=run.has_remaining_items,
    )


def build_reconciliation_draft(
    session: Session, year_month: str, account_id: str
) -> ReconciliationManifest:
    """Build a private draft whose every transaction still requires operator lock."""
    inputs = _load_inputs(session, year_month, account_id)
    if inputs.snapshot is None:
        raise ValueError(f"Snapshot for {year_month} / {account_id} was not found")
    transaction_decisions: list[TransactionDecision] = []
    for transaction in inputs.transactions:
        if transaction.account_id != account_id or transaction.pending:
            continue
        category = (transaction.budget_category or "uncategorized").strip()
        normalized = category.casefold()
        if transaction.amount > _ZERO:
            if transaction.reimbursable:
                flow_type = "reimbursement_out"
            elif "card" in normalized and "payment" in normalized:
                flow_type = "card_payment"
            elif "transfer" in normalized:
                flow_type = "transfer_out"
            else:
                flow_type = "expense"
        elif transaction.amount < _ZERO:
            if "reimburse" in normalized:
                flow_type = "reimbursement_in"
            elif "transfer" in normalized:
                flow_type = "transfer_in"
            else:
                flow_type = "income"
        else:
            flow_type = None
        allocations = (
            []
            if flow_type is None
            else [
                ReconciliationAllocation(
                    flow_type=flow_type,
                    amount=format(abs(transaction.amount), ".2f"),
                    category=category or "uncategorized",
                )
            ]
        )
        transaction_decisions.append(
            TransactionDecision(
                transaction_id=transaction.id,
                manual_locked=False,
                pair_group_id=None,
                allocations=allocations,
                source_date=transaction.date.isoformat(),
                source_amount=format(transaction.amount, ".2f"),
                source_description=transaction.merchant_name or transaction.name,
                source_budget_category=category or "uncategorized",
                source_reviewed=transaction.reviewed,
            )
        )
    line_item_decisions = [
        LineItemDecision(
            line_item_id=item.id,
            resolution="skipped" if item.skipped else "remaining",
            remaining_amount=("0.00" if item.skipped else format(item.amount, ".2f")),
            source_name=item.name,
            source_item_type=item.item_type,
            source_planned_amount=format(item.amount, ".2f"),
        )
        for item in inputs.line_items
    ]
    return ReconciliationManifest(
        version=1,
        year_month=year_month,
        account_id=account_id,
        transaction_decisions=transaction_decisions,
        line_item_decisions=line_item_decisions,
    )
