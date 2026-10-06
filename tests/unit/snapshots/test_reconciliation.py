"""Focused behavioral tests for immutable snapshot reconciliation receipts."""

import json
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest

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
from budget_me.snapshots import reconciliation
from budget_me.snapshots.reconciliation_manifest import (
    LineItemDecision,
    LineItemMatch,
    ReconciliationAllocation,
    ReconciliationManifest,
    TransactionDecision,
)

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
MONTH = "2026-07"
CHECKING_ID = "checking-1"
CARD_ID = "card-1"
CHECKING_PLAID_ITEM_ID = uuid4()
CARD_PLAID_ITEM_ID = uuid4()


def _account(
    *,
    account_id: str = CHECKING_ID,
    account_type: str = "depository",
    plaid_item_id: UUID = CHECKING_PLAID_ITEM_ID,
    paying_account_id: str | None = None,
) -> Account:
    return Account(
        id=uuid4(),
        plaid_item_id=plaid_item_id,
        account_id=account_id,
        name=f"Private {account_id}",
        type=account_type,
        subtype="checking" if account_type == "depository" else "credit card",
        is_excluded=False,
        paying_account_id=paying_account_id,
        created_at=NOW - timedelta(days=100),
        updated_at=NOW - timedelta(hours=3),
    )


def _snapshot() -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month=MONTH,
        account_id=CHECKING_ID,
        status=SnapshotStatus.OPEN,
        income_total=Decimal("0.00"),
        expense_total=Decimal("0.00"),
        transfer_in_total=Decimal("0.00"),
        transfer_out_total=Decimal("0.00"),
        reimbursement_in_total=Decimal("0.00"),
        reimbursement_out_total=Decimal("0.00"),
        credit_card_total=Decimal("0.00"),
        net=Decimal("0.00"),
        starting_balance=Decimal("1000.00"),
        closing_balance=None,
        closing_balance_frozen=False,
        last_synced_at=None,
        created_at=NOW - timedelta(days=40),
        updated_at=NOW - timedelta(hours=2),
    )


def _transaction(
    amount: str,
    category: str | None,
    *,
    account_id: str = CHECKING_ID,
    transaction_date: date = date(2026, 7, 15),
    reviewed: bool = True,
    pending: bool = False,
    reimbursable: bool = False,
    name: str = "PRIVATE SOURCE DESCRIPTION",
) -> Transaction:
    return Transaction(
        id=uuid4(),
        plaid_transaction_id=f"plaid-{uuid4()}",
        plaid_item_id=(
            CHECKING_PLAID_ITEM_ID if account_id == CHECKING_ID else CARD_PLAID_ITEM_ID
        ),
        account_id=account_id,
        date=transaction_date,
        amount=Decimal(amount),
        iso_currency_code="USD",
        name=name,
        merchant_name="PRIVATE MERCHANT",
        normalized_merchant="private merchant",
        pending=pending,
        raw={},
        budget_category=category,
        reviewed=reviewed,
        reviewed_at=NOW - timedelta(hours=3) if reviewed else None,
        reimbursable=reimbursable,
        reimbursement_status="pending" if reimbursable else None,
        reimbursement_note="PRIVATE REIMBURSEMENT NOTE" if reimbursable else None,
        created_at=NOW - timedelta(days=20),
        updated_at=NOW - timedelta(hours=2),
    )


def _line_item(
    snapshot_id: UUID,
    amount: str,
    *,
    item_type: str = "expense",
    skipped: bool = False,
    name: str = "PRIVATE PLANNED ITEM",
) -> SnapshotLineItem:
    return SnapshotLineItem(
        id=uuid4(),
        snapshot_id=snapshot_id,
        item_type=item_type,
        name=name,
        amount=Decimal(amount),
        category="private plan category",
        is_one_time=True,
        skipped=skipped,
        created_at=NOW - timedelta(days=40),
        updated_at=NOW - timedelta(hours=2),
    )


def _card(snapshot_id: UUID) -> SnapshotCreditCard:
    return SnapshotCreditCard(
        id=uuid4(),
        snapshot_id=snapshot_id,
        account_id=CARD_ID,
        statement_balance=Decimal("400.00"),
        payment_strategy="pay_in_full",
        calculated_payment=Decimal("40.00"),
        actual_payment_amount=Decimal("40.00"),
        actual_payment_date=date(2026, 7, 22),
        created_at=NOW - timedelta(days=40),
        updated_at=NOW - timedelta(hours=2),
    )


def _inputs(
    *,
    account: Account | None = None,
    snapshot: MonthlySnapshot | None = None,
    line_items: tuple[SnapshotLineItem, ...] = (),
    cards: tuple[SnapshotCreditCard, ...] = (),
    credit_accounts: tuple[Account, ...] = (),
    transactions: tuple[Transaction, ...] = (),
    reimbursement_links: tuple[ReimbursementLink, ...] = (),
    current_run: SnapshotReconciliationRun | None = None,
) -> reconciliation._ReconciliationInputs:
    return reconciliation._ReconciliationInputs(
        account=account or _account(),
        snapshot=snapshot or _snapshot(),
        line_items=line_items,
        cards=cards,
        credit_accounts=credit_accounts,
        transactions=transactions,
        reimbursement_links=reimbursement_links,
        current_run=current_run,
    )


def _allocation(
    flow_type: str, amount: str, category: str = "reviewed category"
) -> ReconciliationAllocation:
    return ReconciliationAllocation.model_validate(
        {"flow_type": flow_type, "amount": amount, "category": category}
    )


def _decision(
    transaction: Transaction,
    flow_type: str,
    amount: str,
    *,
    manual_locked: bool = True,
    category: str = "reviewed category",
) -> TransactionDecision:
    return TransactionDecision(
        transaction_id=transaction.id,
        manual_locked=manual_locked,
        allocations=[_allocation(flow_type, amount, category)],
    )


def _manifest(
    transaction_decisions: list[TransactionDecision],
    line_item_decisions: list[LineItemDecision] | None = None,
) -> ReconciliationManifest:
    return ReconciliationManifest(
        version=1,
        year_month=MONTH,
        account_id=CHECKING_ID,
        transaction_decisions=transaction_decisions,
        line_item_decisions=line_item_decisions or [],
    )


def _full_case() -> tuple[
    reconciliation._ReconciliationInputs,
    ReconciliationManifest,
    dict[str, Transaction],
]:
    snapshot = _snapshot()
    transactions = {
        "income": _transaction("-1000.00", "salary"),
        "expense": _transaction("300.00", "groceries"),
        "transfer_in": _transaction("-100.00", "transfer"),
        "transfer_out": _transaction("50.00", "transfer"),
        "reimbursement_in": _transaction("-25.00", "reimbursement"),
        "reimbursement_out": _transaction(
            "60.00", "business travel", reimbursable=True
        ),
        "card_payment": _transaction("40.00", "credit card payment"),
    }
    card_side = _transaction(
        "-40.00",
        "credit card payment",
        account_id=CARD_ID,
        transaction_date=date(2026, 7, 22),
    )
    card_side.raw = {
        "personal_finance_category": {"detailed": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"}
    }
    item = _line_item(snapshot.id, "300.00")
    decisions = [
        _decision(transactions[flow_type], flow_type, amount)
        for flow_type, amount in (
            ("income", "1000.00"),
            ("expense", "300.00"),
            ("transfer_in", "100.00"),
            ("transfer_out", "50.00"),
            ("reimbursement_in", "25.00"),
            ("reimbursement_out", "60.00"),
            ("card_payment", "40.00"),
        )
    ]
    line_decision = LineItemDecision(
        line_item_id=item.id,
        resolution="fulfilled",
        remaining_amount="0.00",
        matches=[
            LineItemMatch(
                transaction_id=transactions["expense"].id,
                allocation_index=0,
                amount="300.00",
            )
        ],
    )
    card_account = _account(
        account_id=CARD_ID,
        account_type="credit",
        plaid_item_id=CARD_PLAID_ITEM_ID,
        paying_account_id=CHECKING_ID,
    )
    inputs = _inputs(
        snapshot=snapshot,
        line_items=(item,),
        cards=(_card(snapshot.id),),
        credit_accounts=(card_account,),
        transactions=(*transactions.values(), card_side),
    )
    return inputs, _manifest(decisions, [line_decision]), transactions


def _single_transaction_case(
    *,
    source_amount: str = "10.00",
    flow_type: str = "expense",
    allocation_amount: str = "10.00",
    source_category: str | None = "groceries",
    reviewed: bool = True,
    manual_locked: bool = True,
) -> tuple[reconciliation._ReconciliationInputs, ReconciliationManifest]:
    transaction = _transaction(
        source_amount,
        source_category,
        reviewed=reviewed,
    )
    return (
        _inputs(transactions=(transaction,)),
        _manifest(
            [
                _decision(
                    transaction,
                    flow_type,
                    allocation_amount,
                    manual_locked=manual_locked,
                )
            ]
        ),
    )


def _receipt_from_preview(
    inputs: reconciliation._ReconciliationInputs,
    manifest: ReconciliationManifest,
    preview: reconciliation.SnapshotReconciliationPreview,
) -> reconciliation._ReconciliationInputs:
    assert inputs.snapshot is not None
    run = SnapshotReconciliationRun(
        id=uuid4(),
        snapshot_id=inputs.snapshot.id,
        version=manifest.version,
        is_current=True,
        manifest_hash=preview.manifest_hash,
        input_hash=preview.input_hash,
        reconciled_at=NOW,
        income_total=preview.totals.income_total,
        expense_total=preview.totals.expense_total,
        transfer_in_total=preview.totals.transfer_in_total,
        transfer_out_total=preview.totals.transfer_out_total,
        reimbursement_in_total=preview.totals.reimbursement_in_total,
        reimbursement_out_total=preview.totals.reimbursement_out_total,
        credit_card_total=preview.totals.credit_card_total,
        net=preview.totals.net,
        posted_transaction_count=preview.posted_transaction_count,
        allocation_count=preview.allocation_count,
        line_item_count=preview.line_item_count,
        has_remaining_items=preview.remaining_item_count > 0,
        created_at=NOW,
        updated_at=NOW,
    )
    run.snapshot = inputs.snapshot
    transactions_by_id = {
        transaction.id: transaction for transaction in inputs.transactions
    }
    allocations_by_locator: dict[tuple[UUID, int], SnapshotTransactionAllocation] = {}
    transaction_resolutions: list[SnapshotTransactionResolution] = []
    for decision in manifest.transaction_decisions:
        source = transactions_by_id[decision.transaction_id]
        resolution = SnapshotTransactionResolution(
            id=uuid4(),
            run_id=run.id,
            transaction_id=source.id,
            fingerprint=reconciliation.transaction_fingerprint(source),
            account_id=source.account_id,
            transaction_date=source.date,
            signed_amount=source.amount,
            currency=source.iso_currency_code,
            source_updated_at=source.updated_at,
            classification_source="manifest",
            manual_locked=decision.manual_locked,
            pair_group_id=decision.pair_group_id,
        )
        allocations = []
        for index, allocation_decision in enumerate(decision.allocations):
            allocation = SnapshotTransactionAllocation(
                id=uuid4(),
                resolution_id=resolution.id,
                allocation_index=index,
                flow_type=allocation_decision.flow_type,
                amount=allocation_decision.amount,
                category=allocation_decision.category,
            )
            allocations.append(allocation)
            allocations_by_locator[(source.id, index)] = allocation
        resolution.allocations = allocations
        transaction_resolutions.append(resolution)
    run.transaction_resolutions = transaction_resolutions

    line_resolutions: list[SnapshotLineItemResolution] = []
    for decision in manifest.line_item_decisions:
        resolution = SnapshotLineItemResolution(
            id=uuid4(),
            run_id=run.id,
            line_item_id=decision.line_item_id,
            resolution=decision.resolution,
            remaining_amount=decision.remaining_amount,
            adjustment_flow_type=decision.adjustment_flow_type,
            adjustment_amount=decision.adjustment_amount,
            authorization_note=decision.authorization_note,
        )
        resolution.matches = [
            SnapshotLineItemMatch(
                id=uuid4(),
                resolution_id=resolution.id,
                allocation_id=allocations_by_locator[
                    (match.transaction_id, match.allocation_index)
                ].id,
                amount=match.amount,
            )
            for match in decision.matches
        ]
        line_resolutions.append(resolution)
    run.line_item_resolutions = line_resolutions

    for field in (
        "income_total",
        "expense_total",
        "transfer_in_total",
        "transfer_out_total",
        "reimbursement_in_total",
        "reimbursement_out_total",
        "credit_card_total",
        "net",
    ):
        setattr(inputs.snapshot, field, getattr(preview.totals, field))
    inputs.snapshot.last_synced_at = NOW
    return replace(inputs, current_run=run)


def test_complete_preview_totals_include_reimbursements_and_net() -> None:
    inputs, manifest, _ = _full_case()

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert preview.blockers == ()
    assert preview.can_apply is True
    assert preview.posted_transaction_count == 7
    assert preview.allocation_count == 7
    assert preview.line_item_count == 1
    assert preview.totals.to_dict() == {
        "income_total": "1000.00",
        "expense_total": "300.00",
        "transfer_in_total": "100.00",
        "transfer_out_total": "50.00",
        "reimbursement_in_total": "25.00",
        "reimbursement_out_total": "60.00",
        "credit_card_total": "40.00",
        "net": "675.00",
    }


def test_reconciliation_accepts_exact_checking_transaction_evidence() -> None:
    inputs, manifest, transactions = _full_case()
    checking_payment = transactions["card_payment"]
    checking_payment.budget_category = "credit_card_payment"
    card = inputs.cards[0]
    card.actual_payment_amount = checking_payment.amount
    card.actual_payment_date = checking_payment.date
    card.actual_payment_source = "checking_account"
    card.actual_payment_transaction_id = checking_payment.id
    card.actual_payment_note = "Unique posted checking debit; card feed omitted it."
    inputs = replace(
        inputs,
        transactions=tuple(
            transaction
            for transaction in inputs.transactions
            if transaction.account_id != CARD_ID
        ),
    )

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert preview.blockers == ()
    assert preview.can_apply is True


def test_preview_output_is_aggregate_only() -> None:
    inputs, manifest, _ = _full_case()

    rendered = json.dumps(reconciliation._prepare_preview(inputs, manifest).to_dict())

    for private_value in (
        "PRIVATE SOURCE DESCRIPTION",
        "PRIVATE MERCHANT",
        "PRIVATE REIMBURSEMENT NOTE",
        "PRIVATE PLANNED ITEM",
    ):
        assert private_value not in rendered
    assert "transaction_decisions" not in rendered
    assert "line_item_decisions" not in rendered


@pytest.mark.parametrize(
    ("case_overrides", "expected_blocker"),
    [
        ({"reviewed": False}, "posted transactions remain unreviewed"),
        ({"source_category": None}, "posted transactions remain uncategorized"),
        (
            {"source_category": "uncategorized"},
            "posted transactions remain uncategorized",
        ),
        ({"manual_locked": False}, "transaction decision(s) are not manually locked"),
        (
            {"flow_type": "income"},
            "cash-out transaction contains an inflow allocation",
        ),
        (
            {"source_amount": "-10.00", "flow_type": "expense"},
            "cash-in transaction contains an outflow allocation",
        ),
        (
            {"allocation_amount": "9.99"},
            "allocation must exactly equal its source magnitude",
        ),
    ],
)
def test_preview_enforces_review_category_sign_amount_and_manual_lock_guards(
    case_overrides: dict[str, Any], expected_blocker: str
) -> None:
    inputs, manifest = _single_transaction_case(**case_overrides)

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert any(expected_blocker in blocker for blocker in preview.blockers)
    assert preview.can_apply is False


def test_preview_requires_complete_transaction_and_line_item_coverage() -> None:
    snapshot = _snapshot()
    transaction = _transaction("20.00", "groceries")
    item = _line_item(snapshot.id, "20.00")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )

    preview = reconciliation._prepare_preview(inputs, _manifest([]))

    assert "Manifest is missing 1 posted transaction decision(s)." in preview.blockers
    assert "Manifest is missing 1 line-item decision(s)." in preview.blockers


def test_fulfilled_line_item_requires_a_real_match_and_allows_plan_variance() -> None:
    snapshot = _snapshot()
    transaction = _transaction("100.00", "groceries")
    item = _line_item(snapshot.id, "100.00")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )
    exact = _manifest(
        [_decision(transaction, "expense", "100.00")],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="fulfilled",
                remaining_amount="0.00",
                matches=[
                    LineItemMatch(
                        transaction_id=transaction.id,
                        allocation_index=0,
                        amount="100.00",
                    )
                ],
            )
        ],
    )
    variance = exact.model_copy(
        update={
            "line_item_decisions": [
                exact.line_item_decisions[0].model_copy(
                    update={
                        "matches": [
                            LineItemMatch(
                                transaction_id=transaction.id,
                                allocation_index=0,
                                amount="99.99",
                            )
                        ]
                    }
                )
            ]
        }
    )
    unmatched = _manifest(
        [_decision(transaction, "expense", "100.00")],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="fulfilled",
                remaining_amount="0.00",
                matches=[],
            )
        ],
    )
    incompatible = exact.model_copy(
        update={
            "transaction_decisions": [_decision(transaction, "transfer_out", "100.00")]
        }
    )

    assert reconciliation._prepare_preview(inputs, exact).blockers == ()
    assert reconciliation._prepare_preview(inputs, variance).blockers == ()
    assert any(
        "at least one actual allocation" in blocker
        for blocker in reconciliation._prepare_preview(inputs, unmatched).blockers
    )
    assert any(
        "incompatible cash-flow type" in blocker
        for blocker in reconciliation._prepare_preview(inputs, incompatible).blockers
    )


def test_reimbursable_outflow_can_fulfill_planned_expense() -> None:
    """A reimbursable checking debit still satisfies its planned expense."""
    snapshot = _snapshot()
    transaction = _transaction("50.90", "utilities", reimbursable=True)
    item = _line_item(snapshot.id, "50.90")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )
    manifest = _manifest(
        [_decision(transaction, "reimbursement_out", "50.90")],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="fulfilled",
                remaining_amount="0.00",
                matches=[
                    LineItemMatch(
                        transaction_id=transaction.id,
                        allocation_index=0,
                        amount="50.90",
                    )
                ],
            )
        ],
    )

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert preview.blockers == ()
    assert preview.totals.expense_total == Decimal("0.00")
    assert preview.totals.reimbursement_out_total == Decimal("50.90")


def test_remaining_line_item_balances_matches_and_reports_remaining_amount() -> None:
    snapshot = _snapshot()
    transaction = _transaction("60.00", "groceries")
    item = _line_item(snapshot.id, "100.00")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )
    decision = LineItemDecision(
        line_item_id=item.id,
        resolution="remaining",
        remaining_amount="40.00",
        matches=[
            LineItemMatch(
                transaction_id=transaction.id,
                allocation_index=0,
                amount="60.00",
            )
        ],
    )
    manifest = _manifest([_decision(transaction, "expense", "60.00")], [decision])

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert preview.blockers == ()
    assert preview.can_apply is True
    assert preview.remaining_item_count == 1
    assert preview.remaining_item_total == Decimal("40.00")
    assert preview.warnings == (
        "1 planned line item(s) remain unresolved; apply is allowed but close will "
        "stay blocked.",
    )

    unbalanced = manifest.model_copy(
        update={
            "line_item_decisions": [
                decision.model_copy(update={"remaining_amount": Decimal("39.99")})
            ]
        }
    )
    assert any(
        "balance to their planned amount" in blocker
        for blocker in reconciliation._prepare_preview(inputs, unbalanced).blockers
    )


def test_line_item_matches_cannot_exceed_the_source_allocation() -> None:
    snapshot = _snapshot()
    transaction = _transaction("100.00", "groceries")
    item = _line_item(snapshot.id, "100.01")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )
    manifest = _manifest(
        [_decision(transaction, "expense", "100.00")],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="fulfilled",
                remaining_amount="0.00",
                matches=[
                    LineItemMatch(
                        transaction_id=transaction.id,
                        allocation_index=0,
                        amount="100.01",
                    )
                ],
            )
        ],
    )

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert "Line-item matches exceed a transaction allocation." in preview.blockers


def test_authorized_line_adjustment_contributes_to_actual_totals() -> None:
    snapshot = _snapshot()
    item = _line_item(snapshot.id, "25.00")
    inputs = _inputs(snapshot=snapshot, line_items=(item,))
    manifest = _manifest(
        [],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="adjustment",
                remaining_amount="0.00",
                adjustment_flow_type="expense",
                adjustment_amount="25.00",
                authorization_note="Operator authorized bank-proven variance",
            )
        ],
    )

    preview = reconciliation._prepare_preview(inputs, manifest)

    assert preview.blockers == ()
    assert preview.totals.expense_total == Decimal("25.00")
    assert preview.totals.net == Decimal("-25.00")


def test_input_hash_changes_when_a_live_source_fact_changes() -> None:
    inputs, manifest = _single_transaction_case()
    original = reconciliation._prepare_preview(inputs, manifest)

    inputs.transactions[0].merchant_name = "CHANGED PRIVATE MERCHANT"
    changed = reconciliation._prepare_preview(inputs, manifest)

    assert changed.manifest_hash == original.manifest_hash
    assert changed.input_hash != original.input_hash


def test_draft_is_private_unlocked_and_classifies_all_supported_directions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    reimbursement_out = _transaction("20.00", "work travel", reimbursable=True)
    reimbursement_in = _transaction("-20.00", "reimbursement")
    transfer_out = _transaction("30.00", "bank transfer")
    transfer_in = _transaction("-30.00", "bank transfer")
    income = _transaction("-40.00", "salary")
    expense = _transaction("40.00", "groceries")
    zero = _transaction("0.00", "zero")
    pending = _transaction("5.00", "groceries", pending=True)
    skipped = _line_item(snapshot.id, "10.00", skipped=True)
    remaining = _line_item(snapshot.id, "11.00")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(
            reimbursement_out,
            reimbursement_in,
            transfer_out,
            transfer_in,
            income,
            expense,
            zero,
            pending,
        ),
        line_items=(skipped, remaining),
    )
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: inputs)

    draft = reconciliation.build_reconciliation_draft(None, MONTH, CHECKING_ID)

    decisions = {
        decision.transaction_id: decision for decision in draft.transaction_decisions
    }
    assert pending.id not in decisions
    assert all(not decision.manual_locked for decision in decisions.values())
    assert {
        transaction_id: decision.allocations[0].flow_type
        for transaction_id, decision in decisions.items()
        if decision.allocations
    } == {
        reimbursement_out.id: "reimbursement_out",
        reimbursement_in.id: "reimbursement_in",
        transfer_out.id: "transfer_out",
        transfer_in.id: "transfer_in",
        income.id: "income",
        expense.id: "expense",
    }
    assert decisions[zero.id].allocations == []
    assert decisions[expense.id].source_date == "2026-07-15"
    assert decisions[expense.id].source_amount == Decimal("40.00")
    assert decisions[expense.id].source_description == "PRIVATE MERCHANT"
    assert decisions[expense.id].source_budget_category == "groceries"
    assert decisions[expense.id].source_reviewed is True
    assert [
        (item.resolution, item.remaining_amount) for item in draft.line_item_decisions
    ] == [
        ("skipped", Decimal("0.00")),
        ("remaining", Decimal("11.00")),
    ]
    assert draft.line_item_decisions[1].source_name == "PRIVATE PLANNED ITEM"
    assert draft.line_item_decisions[1].source_item_type == "expense"
    assert draft.line_item_decisions[1].source_planned_amount == Decimal("11.00")


class _ScalarResult:
    def __init__(self, value: Any = None) -> None:
        self.value = value

    def scalar_one_or_none(self) -> Any:
        return self.value


class _ApplySession:
    def __init__(self, snapshot: MonthlySnapshot) -> None:
        self.snapshot = snapshot
        self.events: list[str] = []

    def execute(self, statement: Any) -> _ScalarResult:
        sql = str(statement)
        if sql.startswith("SET TRANSACTION"):
            event = "serializable"
        elif sql.startswith("LOCK TABLE monthly_snapshots"):
            event = "snapshot_table_lock"
        elif sql.startswith("LOCK TABLE accounts"):
            event = "accounts_lock"
        elif sql.startswith("LOCK TABLE snapshot_line_items"):
            event = "line_items_lock"
        elif sql.startswith("LOCK TABLE snapshot_credit_cards"):
            event = "cards_lock"
        elif sql.startswith("LOCK TABLE reimbursement_links"):
            event = "reimbursements_lock"
        elif sql.startswith("SELECT monthly_snapshots"):
            event = "snapshot_row_lock"
        else:  # pragma: no cover - assertion below explains unexpected SQL
            event = sql
        self.events.append(event)
        return _ScalarResult(self.snapshot if event == "snapshot_row_lock" else None)

    def flush(self) -> None:
        self.events.append("flush")


class _CurrentRunsResult:
    def __init__(self, runs: list[SnapshotReconciliationRun]) -> None:
        self.runs = runs

    def scalars(self) -> list[SnapshotReconciliationRun]:
        return self.runs


class _PersistSession:
    def __init__(self, current_runs: list[SnapshotReconciliationRun]) -> None:
        self.current_runs = current_runs
        self.added: list[Any] = []
        self.flush_count = 0

    def execute(self, _statement: Any) -> _CurrentRunsResult:
        return _CurrentRunsResult(self.current_runs)

    def add(self, value: Any) -> None:
        self.added.append(value)

    def flush(self) -> None:
        self.flush_count += 1


def test_persist_manifest_supersedes_current_and_copies_immutable_receipt_rows() -> (
    None
):
    inputs, manifest, _ = _full_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    old_run = SnapshotReconciliationRun(id=uuid4(), is_current=True)
    session = _PersistSession([old_run])
    assert inputs.snapshot is not None

    run = reconciliation._persist_manifest(
        session,
        snapshot=inputs.snapshot,
        inputs=inputs,
        manifest=manifest,
        preview=preview,
        reconciled_at=NOW,
    )

    assert old_run.is_current is False
    assert session.flush_count == 1
    assert run in session.added
    assert run.is_current is True
    assert run.manifest_hash == preview.manifest_hash
    assert run.input_hash == preview.input_hash
    assert run.reimbursement_in_total == Decimal("25.00")
    assert run.reimbursement_out_total == Decimal("60.00")
    assert run.net == Decimal("675.00")
    assert run.posted_transaction_count == 7
    assert run.allocation_count == 7
    assert run.line_item_count == 1
    assert run.has_remaining_items is False

    resolutions = [
        value
        for value in session.added
        if isinstance(value, SnapshotTransactionResolution)
    ]
    allocations = [
        value
        for value in session.added
        if isinstance(value, SnapshotTransactionAllocation)
    ]
    line_resolutions = [
        value
        for value in session.added
        if isinstance(value, SnapshotLineItemResolution)
    ]
    matches = [
        value for value in session.added if isinstance(value, SnapshotLineItemMatch)
    ]
    assert len(resolutions) == 7
    assert len(allocations) == 7
    assert len(line_resolutions) == 1
    assert len(matches) == 1
    assert all(resolution.manual_locked for resolution in resolutions)
    assert {allocation.flow_type for allocation in allocations} == {
        "income",
        "expense",
        "transfer_in",
        "transfer_out",
        "reimbursement_in",
        "reimbursement_out",
        "card_payment",
    }
    assert matches[0].allocation_id in {allocation.id for allocation in allocations}


def test_apply_uses_global_lock_order_and_persists_all_cached_totals(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest, _ = _full_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    assert inputs.snapshot is not None
    session = _ApplySession(inputs.snapshot)
    run = SnapshotReconciliationRun(id=uuid4())

    monkeypatch.setattr(
        reconciliation,
        "acquire_close_coordination_lock",
        lambda _: session.events.append("close_lock"),
    )
    monkeypatch.setattr(
        reconciliation,
        "acquire_transaction_reconciliation_lock",
        lambda _: session.events.append("transaction_lock"),
    )

    def load_inputs(*_: Any) -> reconciliation._ReconciliationInputs:
        session.events.append("load_inputs")
        return inputs

    def prepare(*_: Any) -> reconciliation.SnapshotReconciliationPreview:
        session.events.append("prepare")
        return preview

    def persist(*_: Any, **__: Any) -> SnapshotReconciliationRun:
        session.events.append("persist")
        return run

    monkeypatch.setattr(reconciliation, "_load_inputs", load_inputs)
    monkeypatch.setattr(reconciliation, "_prepare_preview", prepare)
    monkeypatch.setattr(reconciliation, "_persist_manifest", persist)

    applied = reconciliation.apply_reconciliation(
        session,
        manifest,
        confirm_month=MONTH,
        input_hash=preview.input_hash,
        now=NOW,
    )

    assert session.events == [
        "serializable",
        "close_lock",
        "transaction_lock",
        "snapshot_table_lock",
        "snapshot_row_lock",
        "accounts_lock",
        "line_items_lock",
        "cards_lock",
        "reimbursements_lock",
        "load_inputs",
        "prepare",
        "persist",
        "flush",
    ]
    assert applied.current_run_id == str(run.id)
    assert inputs.snapshot.last_synced_at == NOW
    for field in (
        "income_total",
        "expense_total",
        "transfer_in_total",
        "transfer_out_total",
        "reimbursement_in_total",
        "reimbursement_out_total",
        "credit_card_total",
        "net",
    ):
        assert getattr(inputs.snapshot, field) == getattr(preview.totals, field)


def test_apply_rejects_stale_input_hash_before_persistence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest = _single_transaction_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    assert inputs.snapshot is not None
    session = _ApplySession(inputs.snapshot)
    monkeypatch.setattr(
        reconciliation, "acquire_close_coordination_lock", lambda _: None
    )
    monkeypatch.setattr(
        reconciliation, "acquire_transaction_reconciliation_lock", lambda _: None
    )
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: inputs)
    monkeypatch.setattr(reconciliation, "_prepare_preview", lambda *_: preview)
    monkeypatch.setattr(
        reconciliation,
        "_persist_manifest",
        lambda *_, **__: pytest.fail("stale input must not persist"),
    )

    with pytest.raises(ValueError, match="Input hash mismatch"):
        reconciliation.apply_reconciliation(
            session,
            manifest,
            confirm_month=MONTH,
            input_hash="0" * 64,
            now=NOW,
        )


def test_current_receipt_validates_and_exposes_only_aggregate_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest, _ = _full_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)

    evidence = reconciliation.validate_current_reconciliation(None, MONTH, CHECKING_ID)
    rendered = json.dumps(evidence.audit_dict())

    assert evidence.is_valid is True
    assert evidence.blockers == ()
    assert evidence.totals == preview.totals
    assert evidence.audit_dict()["version"] == 1
    assert evidence.audit_dict()["counts"] == {
        "posted_transactions": 7,
        "allocations": 7,
        "line_items": 1,
    }
    assert evidence.audit_dict()["has_remaining_items"] is False
    assert evidence.recomputed_manifest_hash == preview.manifest_hash
    assert evidence.run_input_hash == preview.input_hash
    assert "PRIVATE" not in rendered
    assert "transaction_resolutions" not in rendered
    assert "line_item_resolutions" not in rendered


def test_current_receipt_rejects_decision_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest, _ = _full_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    assert current_inputs.current_run is not None
    current_inputs.current_run.transaction_resolutions[0].allocations[
        0
    ].category = "tampered category"
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)

    evidence = reconciliation.validate_current_reconciliation(None, MONTH, CHECKING_ID)

    assert evidence.is_valid is False
    assert (
        "Current reconciliation receipt decision hash is invalid." in evidence.blockers
    )


def test_current_receipt_rejects_stale_live_inputs(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest = _single_transaction_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    current_inputs.transactions[0].merchant_name = "changed after apply"
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)

    evidence = reconciliation.validate_current_reconciliation(None, MONTH, CHECKING_ID)

    assert evidence.is_valid is False
    assert (
        "Current reconciliation receipt is stale for database inputs."
        in evidence.blockers
    )


def test_current_receipt_rejects_timestamp_and_cached_total_tampering(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest, _ = _full_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    assert current_inputs.snapshot is not None
    current_inputs.snapshot.last_synced_at = NOW - timedelta(seconds=1)
    current_inputs.snapshot.reimbursement_out_total += Decimal("1.00")
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)

    evidence = reconciliation.validate_current_reconciliation(None, MONTH, CHECKING_ID)

    assert evidence.is_valid is False
    assert (
        "Snapshot reconciliation timestamp does not match receipt." in evidence.blockers
    )
    assert (
        "Snapshot cached totals do not match reconciliation receipt."
        in evidence.blockers
    )


def test_current_receipt_preserves_remaining_items_as_a_close_blocker(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    snapshot = _snapshot()
    transaction = _transaction("60.00", "groceries")
    item = _line_item(snapshot.id, "100.00")
    inputs = _inputs(
        snapshot=snapshot,
        transactions=(transaction,),
        line_items=(item,),
    )
    manifest = _manifest(
        [_decision(transaction, "expense", "60.00")],
        [
            LineItemDecision(
                line_item_id=item.id,
                resolution="remaining",
                remaining_amount="40.00",
                matches=[
                    LineItemMatch(
                        transaction_id=transaction.id,
                        allocation_index=0,
                        amount="60.00",
                    )
                ],
            )
        ],
    )
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)

    evidence = reconciliation.validate_current_reconciliation(None, MONTH, CHECKING_ID)

    assert evidence.is_valid is False
    assert (
        "Planned line items remain unresolved in reconciliation." in evidence.blockers
    )


def test_idempotent_apply_revalidates_current_receipt_before_returning(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    inputs, manifest = _single_transaction_case()
    preview = reconciliation._prepare_preview(inputs, manifest)
    current_inputs = _receipt_from_preview(inputs, manifest, preview)
    assert current_inputs.current_run is not None
    idempotent_preview = replace(
        preview,
        current_run_id=str(current_inputs.current_run.id),
        is_idempotent=True,
    )
    assert current_inputs.snapshot is not None
    session = _ApplySession(current_inputs.snapshot)
    monkeypatch.setattr(
        reconciliation, "acquire_close_coordination_lock", lambda _: None
    )
    monkeypatch.setattr(
        reconciliation, "acquire_transaction_reconciliation_lock", lambda _: None
    )
    monkeypatch.setattr(reconciliation, "_load_inputs", lambda *_: current_inputs)
    monkeypatch.setattr(
        reconciliation, "_prepare_preview", lambda *_: idempotent_preview
    )
    invalid = reconciliation.CurrentReconciliationEvidence(
        run_id=str(current_inputs.current_run.id),
        reconciled_at=NOW,
        manifest_hash=preview.manifest_hash,
        input_hash=preview.input_hash,
        totals=preview.totals,
        blockers=("Current reconciliation receipt totals are inconsistent.",),
    )
    monkeypatch.setattr(
        reconciliation, "validate_current_reconciliation", lambda *_: invalid
    )
    monkeypatch.setattr(
        reconciliation,
        "_persist_manifest",
        lambda *_, **__: pytest.fail("invalid idempotent receipt must not persist"),
    )

    with pytest.raises(ValueError, match="Cannot reuse reconciliation receipt"):
        reconciliation.apply_reconciliation(
            session,
            manifest,
            confirm_month=MONTH,
            input_hash=preview.input_hash,
            now=NOW,
        )
