"""Preview and initialize a missing monthly snapshot without hidden side effects."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from enum import Enum
from typing import Any
from uuid import UUID

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from budget_me.db.models.account import Account, PaymentStrategy
from budget_me.db.models.anticipated_item import AnticipatedItem
from budget_me.db.models.credit_liability import CreditLiability
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.sync_coordination import acquire_close_coordination_lock
from budget_me.forecasting.engine import get_item_months_in_range

_AUDIT_VERSION = 1
_ZERO = Decimal("0.00")
_SUPPORTED_ITEM_TYPES = {"income", "expense"}
_SUPPORTED_FREQUENCIES = {"monthly", "quarterly", "annual", "one_time"}
_SNAPSHOT_INITIALIZATION_LOCK_SQL = text(
    "LOCK TABLE monthly_snapshots IN SHARE ROW EXCLUSIVE MODE"
)
_CONFIGURATION_LOCK_SQLS = (
    text("LOCK TABLE accounts IN SHARE MODE"),
    text("LOCK TABLE anticipated_items IN SHARE MODE"),
    text("LOCK TABLE credit_liabilities IN SHARE MODE"),
)


def _enum_value(value: Any) -> Any:
    """Return a persisted enum value while leaving ordinary values unchanged."""
    return value.value if isinstance(value, Enum) else value


def _money(value: Decimal | None) -> str | None:
    """Serialize currency deterministically without converting through float."""
    return None if value is None else format(value, ".2f")


def _timestamp(value: datetime | None) -> str | None:
    """Serialize a timestamp deterministically in UTC."""
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=UTC)
    return value.astimezone(UTC).isoformat()


def _validate_year_month(year_month: str) -> None:
    """Require the canonical YYYY-MM spelling before opening a transaction."""
    try:
        parsed = datetime.strptime(year_month, "%Y-%m")
    except (TypeError, ValueError) as exc:
        raise ValueError("year_month must use YYYY-MM") from exc
    if parsed.strftime("%Y-%m") != year_month:
        raise ValueError("year_month must use YYYY-MM")


@dataclass(frozen=True)
class SnapshotInitializationTotals:
    """Proposed cached totals for a newly initialized planning snapshot."""

    income_total: Decimal
    expense_total: Decimal
    transfer_in_total: Decimal
    transfer_out_total: Decimal
    reimbursement_in_total: Decimal
    reimbursement_out_total: Decimal
    credit_card_total: Decimal
    net: Decimal

    def to_dict(self) -> dict[str, str]:
        """Return stable JSON-safe currency strings."""
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
class SnapshotInitializationPreview:
    """Aggregate-only, hash-bound proposal for a missing monthly snapshot."""

    year_month: str
    account_id: str
    anticipated_item_count: int
    income_item_count: int
    expense_item_count: int
    credit_card_count: int
    totals: SnapshotInitializationTotals
    blockers: tuple[str, ...]
    warnings: tuple[str, ...]
    audit_hash: str

    @property
    def can_initialize(self) -> bool:
        """Return whether every initialization invariant is satisfied."""
        return not self.blockers

    def to_dict(self) -> dict[str, Any]:
        """Return an aggregate-only representation safe for CLI/UI rendering."""
        return {
            "year_month": self.year_month,
            "account_id": self.account_id,
            "counts": {
                "anticipated_items": self.anticipated_item_count,
                "income_items": self.income_item_count,
                "expense_items": self.expense_item_count,
                "credit_cards": self.credit_card_count,
            },
            "totals": self.totals.to_dict(),
            "blockers": list(self.blockers),
            "warnings": list(self.warnings),
            "can_initialize": self.can_initialize,
            "audit_hash": self.audit_hash,
        }


@dataclass(frozen=True)
class _InitializationInputs:
    account: Account | None
    existing_snapshot: MonthlySnapshot | None
    anticipated_items: tuple[AnticipatedItem, ...]
    card_sources: tuple[tuple[Account, CreditLiability | None], ...]


@dataclass(frozen=True)
class _LineItemSeed:
    source_item_id: UUID
    item_type: str
    name: str
    amount: Decimal
    category: str | None
    is_one_time: bool


@dataclass(frozen=True)
class _CreditCardSeed:
    account_id: str
    statement_balance: Decimal | None
    payment_strategy: str
    fixed_payment_amount: Decimal | None
    calculated_payment: Decimal
    due_date: date | None


@dataclass(frozen=True)
class _PreparedInitialization:
    preview: SnapshotInitializationPreview
    line_items: tuple[_LineItemSeed, ...]
    credit_cards: tuple[_CreditCardSeed, ...]


def _load_initialization_inputs(
    session: Session, year_month: str, account_id: str
) -> _InitializationInputs:
    """Read every logical input without flushing or mutating caller state."""
    with session.no_autoflush:
        account = session.execute(
            select(Account).where(Account.account_id == account_id)
        ).scalar_one_or_none()
        existing_snapshot = session.execute(
            select(MonthlySnapshot).where(
                MonthlySnapshot.year_month == year_month,
                MonthlySnapshot.account_id == account_id,
            )
        ).scalar_one_or_none()
        anticipated_items = tuple(
            session.execute(
                select(AnticipatedItem)
                .where(
                    AnticipatedItem.active.is_(True),
                    AnticipatedItem.account_id == account_id,
                )
                .order_by(AnticipatedItem.id)
            ).scalars()
        )
        card_sources = tuple(
            session.execute(
                select(Account, CreditLiability)
                .outerjoin(
                    CreditLiability,
                    CreditLiability.account_id == Account.account_id,
                )
                .where(
                    Account.type == "credit",
                    Account.paying_account_id == account_id,
                    Account.is_excluded.is_(False),
                )
                .order_by(Account.account_id)
            ).all()
        )
    return _InitializationInputs(
        account=account,
        existing_snapshot=existing_snapshot,
        anticipated_items=anticipated_items,
        card_sources=card_sources,
    )


def _account_payload(account: Account | None) -> dict[str, Any] | None:
    if account is None:
        return None
    return {
        "id": str(account.id),
        "account_id": account.account_id,
        "type": account.type,
        "subtype": account.subtype,
        "is_excluded": account.is_excluded,
        "updated_at": _timestamp(account.updated_at),
    }


def _snapshot_payload(snapshot: MonthlySnapshot | None) -> dict[str, Any] | None:
    if snapshot is None:
        return None
    return {
        "id": str(snapshot.id),
        "year_month": snapshot.year_month,
        "account_id": snapshot.account_id,
        "status": _enum_value(snapshot.status),
        "updated_at": _timestamp(snapshot.updated_at),
    }


def _item_payload(item: AnticipatedItem, *, included: bool) -> dict[str, Any]:
    return {
        "id": str(item.id),
        "name": item.name,
        "amount": _money(item.amount),
        "item_type": _enum_value(item.item_type),
        "category": item.category,
        "active": item.active,
        "frequency": _enum_value(item.frequency),
        "start_month": item.start_month,
        "end_month": item.end_month,
        "account_id": item.account_id,
        "included": included,
        "updated_at": _timestamp(item.updated_at),
    }


def _card_payload(
    account: Account, liability: CreditLiability | None
) -> dict[str, Any]:
    return {
        "account": {
            "id": str(account.id),
            "account_id": account.account_id,
            "type": account.type,
            "subtype": account.subtype,
            "is_excluded": account.is_excluded,
            "paying_account_id": account.paying_account_id,
            "payment_strategy": _enum_value(account.payment_strategy),
            "fixed_payment_amount": _money(account.fixed_payment_amount),
            "updated_at": _timestamp(account.updated_at),
        },
        "liability": None
        if liability is None
        else {
            "id": str(liability.id),
            "account_id": liability.account_id,
            "last_statement_balance": _money(liability.last_statement_balance),
            "next_payment_due_date": liability.next_payment_due_date.isoformat()
            if liability.next_payment_due_date
            else None,
            "updated_at": _timestamp(liability.updated_at),
        },
    }


def _prepare_initialization(
    year_month: str,
    account_id: str,
    inputs: _InitializationInputs,
) -> _PreparedInitialization:
    """Create deterministic seeds, aggregates, blockers, and an audit hash."""
    blockers: list[str] = []
    warnings: list[str] = [
        "Initialization seeds current anticipated-item and card configuration. "
        "For a historical month, review every seeded row before reconciliation "
        "or close."
    ]

    if inputs.account is None:
        blockers.append("Account does not exist.")
    else:
        if inputs.account.is_excluded:
            blockers.append("Account is excluded from monthly snapshots.")
        if inputs.account.type != "depository":
            blockers.append("Account must be a depository account.")
    if inputs.existing_snapshot is not None:
        blockers.append("A snapshot already exists for this month and account.")

    line_items: list[_LineItemSeed] = []
    item_payloads: list[dict[str, Any]] = []
    unsupported_item_types = 0
    unsupported_frequencies = 0
    negative_item_amounts = 0
    for item in sorted(inputs.anticipated_items, key=lambda value: str(value.id)):
        item_type = _enum_value(item.item_type)
        frequency = _enum_value(item.frequency)
        supported_type = item_type in _SUPPORTED_ITEM_TYPES
        supported_frequency = frequency in _SUPPORTED_FREQUENCIES
        nonnegative_amount = item.amount >= _ZERO
        if not supported_type:
            unsupported_item_types += 1
        if not supported_frequency:
            unsupported_frequencies += 1
        if not nonnegative_amount:
            negative_item_amounts += 1

        included = bool(
            supported_type
            and supported_frequency
            and nonnegative_amount
            and year_month in get_item_months_in_range(item, year_month, year_month)
        )
        item_payloads.append(_item_payload(item, included=included))
        if included:
            line_items.append(
                _LineItemSeed(
                    source_item_id=item.id,
                    item_type=item_type,
                    name=item.name,
                    amount=item.amount,
                    category=item.category,
                    is_one_time=frequency == "one_time",
                )
            )

    if unsupported_item_types:
        blockers.append(
            f"{unsupported_item_types} anticipated item(s) have unsupported types."
        )
    if unsupported_frequencies:
        blockers.append(
            f"{unsupported_frequencies} anticipated item(s) have unsupported frequencies."
        )
    if negative_item_amounts:
        blockers.append(
            f"{negative_item_amounts} anticipated item(s) have negative amounts."
        )

    credit_cards: list[_CreditCardSeed] = []
    card_payloads: list[dict[str, Any]] = []
    unsupported_card_strategies = 0
    missing_statement_balances = 0
    missing_fixed_payments = 0
    negative_fixed_payments = 0
    credit_statement_balances = 0
    for card, liability in sorted(
        inputs.card_sources, key=lambda value: value[0].account_id
    ):
        strategy = _enum_value(card.payment_strategy)
        statement_balance = (
            liability.last_statement_balance if liability is not None else None
        )
        fixed_payment = card.fixed_payment_amount
        card_payloads.append(_card_payload(card, liability))

        if strategy == PaymentStrategy.PAY_IN_FULL.value:
            if statement_balance is None:
                missing_statement_balances += 1
                calculated_payment = _ZERO
            elif statement_balance < _ZERO:
                credit_statement_balances += 1
                calculated_payment = _ZERO
            else:
                calculated_payment = statement_balance
        elif strategy == PaymentStrategy.PROMOTIONAL_PAYDOWN.value:
            if fixed_payment is None:
                missing_fixed_payments += 1
                calculated_payment = _ZERO
            elif fixed_payment < _ZERO:
                negative_fixed_payments += 1
                calculated_payment = _ZERO
            else:
                calculated_payment = fixed_payment
        else:
            unsupported_card_strategies += 1
            calculated_payment = _ZERO

        credit_cards.append(
            _CreditCardSeed(
                account_id=card.account_id,
                statement_balance=statement_balance,
                payment_strategy=strategy,
                fixed_payment_amount=fixed_payment,
                calculated_payment=calculated_payment,
                due_date=(
                    liability.next_payment_due_date if liability is not None else None
                ),
            )
        )

    if unsupported_card_strategies:
        blockers.append(
            f"{unsupported_card_strategies} assigned card(s) have unsupported "
            "payment strategies."
        )
    if negative_fixed_payments:
        blockers.append(
            f"{negative_fixed_payments} assigned card(s) have negative fixed payments."
        )
    if missing_statement_balances:
        warnings.append(
            f"{missing_statement_balances} pay-in-full card(s) have no statement "
            "balance; proposed payment is 0.00."
        )
    if missing_fixed_payments:
        warnings.append(
            f"{missing_fixed_payments} promotional-paydown card(s) have no fixed "
            "payment; proposed payment is 0.00."
        )
    if credit_statement_balances:
        warnings.append(
            f"{credit_statement_balances} pay-in-full card(s) have credit statement "
            "balances; proposed payment is floored at 0.00."
        )

    income_total = sum(
        (item.amount for item in line_items if item.item_type == "income"),
        start=_ZERO,
    )
    expense_total = sum(
        (item.amount for item in line_items if item.item_type == "expense"),
        start=_ZERO,
    )
    credit_card_total = sum(
        (card.calculated_payment for card in credit_cards), start=_ZERO
    )
    net = income_total - expense_total - credit_card_total
    totals = SnapshotInitializationTotals(
        income_total=income_total,
        expense_total=expense_total,
        transfer_in_total=_ZERO,
        transfer_out_total=_ZERO,
        reimbursement_in_total=_ZERO,
        reimbursement_out_total=_ZERO,
        credit_card_total=credit_card_total,
        net=net,
    )

    payload = {
        "version": _AUDIT_VERSION,
        "year_month": year_month,
        "account_id": account_id,
        "account": _account_payload(inputs.account),
        "existing_snapshot": _snapshot_payload(inputs.existing_snapshot),
        "anticipated_items": item_payloads,
        "credit_cards": card_payloads,
        "proposed_totals": totals.to_dict(),
    }
    audit_hash = hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    preview = SnapshotInitializationPreview(
        year_month=year_month,
        account_id=account_id,
        anticipated_item_count=len(line_items),
        income_item_count=sum(item.item_type == "income" for item in line_items),
        expense_item_count=sum(item.item_type == "expense" for item in line_items),
        credit_card_count=len(credit_cards),
        totals=totals,
        blockers=tuple(blockers),
        warnings=tuple(warnings),
        audit_hash=audit_hash,
    )
    return _PreparedInitialization(
        preview=preview,
        line_items=tuple(line_items),
        credit_cards=tuple(credit_cards),
    )


def build_initialization_preview(
    session: Session, year_month: str, account_id: str
) -> SnapshotInitializationPreview:
    """Build an aggregate missing-snapshot proposal without changing the session."""
    _validate_year_month(year_month)
    inputs = _load_initialization_inputs(session, year_month, account_id)
    return _prepare_initialization(year_month, account_id, inputs).preview


def initialize_snapshot(
    session: Session,
    year_month: str,
    account_id: str,
    *,
    confirm_month: str,
    audit_hash: str,
) -> MonthlySnapshot:
    """Create one missing snapshot after revalidating a hash-bound proposal.

    The caller owns commit/rollback. This function flushes only.
    """
    _validate_year_month(year_month)
    if confirm_month != year_month:
        raise ValueError(f"Confirmation must exactly match {year_month}")

    session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
    acquire_close_coordination_lock(session)
    session.execute(_SNAPSHOT_INITIALIZATION_LOCK_SQL)
    for lock_statement in _CONFIGURATION_LOCK_SQLS:
        session.execute(lock_statement)

    inputs = _load_initialization_inputs(session, year_month, account_id)
    prepared = _prepare_initialization(year_month, account_id, inputs)
    if audit_hash != prepared.preview.audit_hash:
        raise ValueError("Audit hash mismatch; run a fresh initialization preview")
    if prepared.preview.blockers:
        raise ValueError(
            "Cannot initialize snapshot: " + " ".join(prepared.preview.blockers)
        )

    totals = prepared.preview.totals
    snapshot = MonthlySnapshot(
        year_month=year_month,
        account_id=account_id,
        status=SnapshotStatus.OPEN,
        income_total=totals.income_total,
        expense_total=totals.expense_total,
        transfer_in_total=totals.transfer_in_total,
        transfer_out_total=totals.transfer_out_total,
        reimbursement_in_total=totals.reimbursement_in_total,
        reimbursement_out_total=totals.reimbursement_out_total,
        credit_card_total=totals.credit_card_total,
        net=totals.net,
        starting_balance=None,
        closing_balance=None,
        closing_balance_frozen=False,
        closed_at=None,
        last_synced_at=None,
    )
    session.add(snapshot)
    session.flush()

    session.add_all(
        [
            SnapshotLineItem(
                snapshot_id=snapshot.id,
                source_item_id=item.source_item_id,
                item_type=item.item_type,
                name=item.name,
                amount=item.amount,
                category=item.category,
                is_one_time=item.is_one_time,
                skipped=False,
            )
            for item in prepared.line_items
        ]
        + [
            SnapshotCreditCard(
                snapshot_id=snapshot.id,
                account_id=card.account_id,
                statement_balance=card.statement_balance,
                payment_strategy=card.payment_strategy,
                fixed_payment_amount=card.fixed_payment_amount,
                calculated_payment=card.calculated_payment,
                due_date=card.due_date,
                actual_payment_amount=None,
                actual_payment_date=None,
            )
            for card in prepared.credit_cards
        ]
    )
    session.flush()
    return snapshot
