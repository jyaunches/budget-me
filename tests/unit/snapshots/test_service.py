"""Behavioral tests for guarded monthly snapshot closes."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from budget_me.db.models.account import Account
from budget_me.db.models.ingest_run import (
    IngestRunItemStatus,
    IngestRunStatus,
)
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.transaction import Transaction
from budget_me.snapshots import service

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
PAYING_PLAID_ITEM_ID = uuid4()
CARD_PLAID_ITEM_ID = uuid4()
UNRELATED_PLAID_ITEM_ID = uuid4()


def _account() -> Account:
    return Account(
        id=uuid4(),
        plaid_item_id=PAYING_PLAID_ITEM_ID,
        account_id="checking-1",
        name="Primary Checking",
        type="depository",
        is_excluded=False,
        created_at=NOW,
        updated_at=NOW,
    )


def _snapshot(*, last_synced_at: datetime | None = None) -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month="2026-07",
        account_id="checking-1",
        status=SnapshotStatus.OPEN,
        last_synced_at=last_synced_at or NOW - timedelta(hours=1),
        created_at=NOW,
        updated_at=NOW,
    )


def _next_snapshot(
    *,
    status: SnapshotStatus = SnapshotStatus.OPEN,
    starting_balance: Decimal | None = None,
) -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month="2026-08",
        account_id="checking-1",
        status=status,
        starting_balance=starting_balance,
        created_at=NOW,
        updated_at=NOW,
    )


def _prior_snapshot(
    *,
    status: SnapshotStatus = SnapshotStatus.CLOSED,
    starting_balance: Decimal | None = Decimal("9000.00"),
    closing_balance: Decimal | None = Decimal("10000.00"),
    frozen: bool = True,
) -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month="2026-06",
        account_id="checking-1",
        status=status,
        starting_balance=starting_balance,
        closing_balance=closing_balance,
        closing_balance_frozen=frozen,
        created_at=NOW,
        updated_at=NOW,
    )


def _item(snapshot_id, item_type: str, amount: str) -> SnapshotLineItem:
    return SnapshotLineItem(
        id=uuid4(),
        snapshot_id=snapshot_id,
        item_type=item_type,
        name=item_type,
        amount=Decimal(amount),
        skipped=False,
        is_one_time=True,
        created_at=NOW,
        updated_at=NOW,
    )


def _card(
    snapshot_id,
    *,
    account_id: str = "card-1",
    actual_amount: Decimal | None = Decimal("700.00"),
    actual_date: date | None = date(2026, 7, 15),
) -> SnapshotCreditCard:
    return SnapshotCreditCard(
        id=uuid4(),
        snapshot_id=snapshot_id,
        account_id=account_id,
        payment_strategy="pay_in_full",
        calculated_payment=Decimal("1000.00"),
        actual_payment_amount=actual_amount,
        actual_payment_date=actual_date,
        created_at=NOW,
        updated_at=NOW,
    )


def _card_account(
    account_id: str = "card-1",
    *,
    paying_account_id: str | None = "checking-1",
    is_excluded: bool = False,
    plaid_item_id=CARD_PLAID_ITEM_ID,
) -> Account:
    return Account(
        id=uuid4(),
        plaid_item_id=plaid_item_id,
        account_id=account_id,
        name=f"Card {account_id}",
        type="credit",
        paying_account_id=paying_account_id,
        is_excluded=is_excluded,
        created_at=NOW,
        updated_at=NOW,
    )


def _card_payment(
    *,
    account_id: str = "card-1",
    amount: str = "-700.00",
    payment_date: date = date(2026, 7, 15),
    pending: bool = False,
    legacy: bool = False,
    normalized: bool = False,
) -> Transaction:
    return Transaction(
        id=uuid4(),
        plaid_transaction_id=f"payment-{uuid4()}",
        plaid_item_id=uuid4(),
        account_id=account_id,
        date=payment_date,
        amount=Decimal(amount),
        name="Card payment",
        pending=pending,
        category_detailed=(
            "Payment, Credit Card"
            if legacy
            else "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
            if normalized
            else None
        ),
        raw={}
        if legacy or normalized
        else {
            "personal_finance_category": {
                "detailed": "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT"
            }
        },
        reviewed=True,
        budget_category="credit_card_payment",
        created_at=NOW - timedelta(hours=3),
        updated_at=NOW - timedelta(hours=2),
    )


def _sync_evidence(
    plaid_item_id=PAYING_PLAID_ITEM_ID,
    *,
    started_at: datetime = NOW - timedelta(hours=3),
    ended_at: datetime | None = NOW - timedelta(hours=2),
    item_status: IngestRunItemStatus = IngestRunItemStatus.SUCCESS,
    run_status: IngestRunStatus = IngestRunStatus.COMPLETED,
    item_tx_removed: int = 0,
) -> service.PlaidItemSyncEvidence:
    return service.PlaidItemSyncEvidence(
        plaid_item_id=str(plaid_item_id),
        ingest_run_id=str(uuid4()),
        ingest_run_item_id=str(uuid4()),
        item_status=item_status.value,
        run_status=run_status.value,
        started_at=started_at,
        ended_at=ended_at,
        items_total=1,
        items_ok=1 if item_status == IngestRunItemStatus.SUCCESS else 0,
        items_failed=0,
        run_tx_added=0,
        run_tx_modified=0,
        run_tx_removed=item_tx_removed,
        item_tx_added=0,
        item_tx_modified=0,
        item_tx_removed=item_tx_removed,
        duration_ms=100,
    )


def _successful_sync_evidence(*, include_card: bool = False):
    evidence = [_sync_evidence()]
    if include_card:
        evidence.append(_sync_evidence(CARD_PLAID_ITEM_ID))
    return evidence


def _minimal_preview(
    *,
    evidence=(),
    active_evidence=(),
    cards=(),
    credit_card_accounts=(),
):
    return service._calculate_preview(
        snapshot=_snapshot(),
        account=_account(),
        items=[],
        cards=cards,
        credit_card_accounts=credit_card_accounts,
        transactions=[],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("100.00"),
        captured_balance=Decimal("100.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=evidence,
        active_plaid_item_sync_evidence=active_evidence,
    )


def _ready_preview(
    *,
    legacy_payment: bool = False,
    next_snapshot: MonthlySnapshot | None = None,
):
    snapshot = _snapshot()
    items = [
        _item(snapshot.id, "income", "5000.00"),
        _item(snapshot.id, "expense", "2000.00"),
        _item(snapshot.id, "transfer_in", "300.00"),
        _item(snapshot.id, "transfer_out", "100.00"),
    ]
    return snapshot, service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=items,
        cards=[_card(snapshot.id)],
        credit_card_accounts=[_card_account()],
        transactions=[_card_payment(legacy=legacy_payment)],
        missing_paying_cards=[],
        next_snapshot=next_snapshot,
        starting_balance=Decimal("10000.00"),
        captured_balance=Decimal("12500.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )


def test_preview_uses_posted_card_payments_and_all_cash_flow_totals():
    """Closing cash flow uses posted card payments, while preserving the plan."""
    _, preview = _ready_preview()

    assert preview.planned_credit_card_total == Decimal("1000.00")
    assert preview.actual_credit_card_total == Decimal("700.00")
    assert preview.remaining_credit_card_total == Decimal("300.00")
    assert preview.totals.income_total == Decimal("5000.00")
    assert preview.totals.expense_total == Decimal("2000.00")
    assert preview.totals.transfer_in_total == Decimal("300.00")
    assert preview.totals.transfer_out_total == Decimal("100.00")
    assert preview.totals.credit_card_total == Decimal("700.00")
    assert preview.totals.net == Decimal("2500.00")
    assert preview.projected_closing_balance == Decimal("12500.00")
    assert preview.captured_difference == Decimal("0.00")
    assert preview.can_close is True


def test_preview_accepts_a_reconciled_zero_card_payment():
    """A stored zero is reviewed actual cash flow, not a missing result."""
    snapshot = _snapshot()
    card = _card(snapshot.id)
    card.actual_payment_amount = Decimal("0.00")
    card.actual_payment_date = None

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[card],
        credit_card_accounts=[_card_account()],
        transactions=[],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=Decimal("1000.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )

    assert preview.actual_credit_card_total == Decimal("0.00")
    assert preview.missing_actual_credit_card_count == 0
    assert preview.can_close is True


def test_preview_hash_is_order_independent_and_changes_with_financial_inputs():
    """The audit hash is stable, but invalidates when a reviewed input changes."""
    snapshot = _snapshot()
    account = _account()
    items = [
        _item(snapshot.id, "income", "100.00"),
        _item(snapshot.id, "expense", "25.00"),
    ]
    card = _card(snapshot.id)
    kwargs = {
        "snapshot": snapshot,
        "account": account,
        "cards": [card],
        "credit_card_accounts": [_card_account()],
        "transactions": [_card_payment()],
        "missing_paying_cards": [],
        "next_snapshot": None,
        "starting_balance": Decimal("1000.00"),
        "captured_balance": None,
        "now": NOW,
        "max_reconciliation_age": timedelta(hours=24),
    }

    first = service._calculate_preview(items=items, **kwargs)
    reordered = service._calculate_preview(items=list(reversed(items)), **kwargs)
    assert first.audit_hash == reordered.audit_hash

    member = kwargs["credit_card_accounts"][0]
    member.paying_account_id = "checking-2"
    membership_changed = service._calculate_preview(items=items, **kwargs)
    assert membership_changed.audit_hash != first.audit_hash
    member.paying_account_id = "checking-1"

    card.actual_payment_amount = Decimal("701.00")
    changed = service._calculate_preview(items=items, **kwargs)
    assert changed.audit_hash != first.audit_hash


def test_preview_hash_and_output_include_only_non_secret_item_sync_evidence():
    """Lifecycle counts are serialized and protected by the close audit hash."""
    evidence = _sync_evidence()
    first = _minimal_preview(evidence=[evidence])
    changed = _minimal_preview(
        evidence=[replace(evidence, item_tx_removed=1, run_tx_removed=1)]
    )

    payload = first.to_dict()["plaid_item_sync_evidence"][0]
    assert first.can_close is True
    assert payload["plaid_item_id"] == str(PAYING_PLAID_ITEM_ID)
    assert payload["item_status"] == IngestRunItemStatus.SUCCESS.value
    assert "error_message" not in payload
    assert changed.audit_hash != first.audit_hash


def test_sync_evidence_uses_last_completion_not_last_start():
    """An older-started run that finishes last cannot be hidden by overlap."""
    newer_started_run_id = uuid4()
    older_started_run_id = uuid4()

    def evidence_row(*, run_id, started_at, ended_at, item_status, run_status):
        run_item = MagicMock()
        run_item.id = uuid4()
        run_item.plaid_item_id = PAYING_PLAID_ITEM_ID
        run_item.status = item_status
        run_item.tx_added = 0
        run_item.tx_modified = 0
        run_item.tx_removed = 0
        run_item.duration_ms = 100
        run = MagicMock()
        run.id = run_id
        run.started_at = started_at
        run.ended_at = ended_at
        run.status = run_status
        run.items_total = 1
        run.items_ok = int(item_status == IngestRunItemStatus.SUCCESS)
        run.items_failed = int(item_status == IngestRunItemStatus.FAILED)
        run.tx_added = 0
        run.tx_modified = 0
        run.tx_removed = 0
        return run_item, run

    newer_started_success = evidence_row(
        run_id=newer_started_run_id,
        started_at=NOW - timedelta(hours=3),
        ended_at=NOW - timedelta(hours=2),
        item_status=IngestRunItemStatus.SUCCESS,
        run_status=IngestRunStatus.COMPLETED,
    )
    older_started_late_failure = evidence_row(
        run_id=older_started_run_id,
        started_at=NOW - timedelta(hours=4),
        ended_at=NOW - timedelta(minutes=30),
        item_status=IngestRunItemStatus.FAILED,
        run_status=IngestRunStatus.FAILED,
    )
    result = MagicMock()
    # Match the query's start-descending row order to exercise the old failure.
    result.all.return_value = [newer_started_success, older_started_late_failure]
    session = MagicMock()
    session.execute.return_value = result

    latest, active = service._load_plaid_item_sync_evidence(
        session, [PAYING_PLAID_ITEM_ID]
    )

    assert len(latest) == 1
    assert latest[0].ingest_run_id == str(older_started_run_id)
    assert latest[0].item_status == IngestRunItemStatus.FAILED.value
    assert active == ()
    preview = _minimal_preview(evidence=latest)
    assert any(
        "is failed; success is required" in blocker for blocker in preview.blockers
    )
    assert any("completed after" in blocker for blocker in preview.blockers)


@pytest.mark.parametrize(
    ("evidence", "blocker_text"),
    [
        ([], "No Plaid ingest history"),
        (
            [_sync_evidence(ended_at=NOW - timedelta(hours=26))],
            "too old relative to reconciliation",
        ),
        (
            [
                _sync_evidence(
                    item_status=IngestRunItemStatus.FAILED,
                    run_status=IngestRunStatus.FAILED,
                )
            ],
            "success is required",
        ),
        (
            [
                _sync_evidence(
                    item_status=IngestRunItemStatus.FAILED,
                    run_status=IngestRunStatus.PARTIAL,
                )
            ],
            "success is required",
        ),
    ],
)
def test_preview_blocks_missing_old_failed_or_partial_failed_evidence(
    evidence, blocker_text: str
):
    preview = _minimal_preview(evidence=evidence)

    assert any(blocker_text in blocker for blocker in preview.blockers)
    assert preview.can_close is False


def test_preview_accepts_partial_parent_when_relevant_item_succeeded():
    preview = _minimal_preview(
        evidence=[_sync_evidence(run_status=IngestRunStatus.PARTIAL)]
    )

    assert preview.can_close is True


def test_preview_blocks_relevant_running_or_pending_activity():
    active = _sync_evidence(
        ended_at=None,
        item_status=IngestRunItemStatus.PENDING,
        run_status=IngestRunStatus.RUNNING,
    )
    preview = _minimal_preview(
        evidence=_successful_sync_evidence(), active_evidence=[active]
    )

    assert any("running or pending" in blocker for blocker in preview.blockers)
    assert preview.can_close is False


def test_preview_blocks_successful_sync_completed_after_reconciliation():
    preview = _minimal_preview(
        evidence=[_sync_evidence(ended_at=NOW - timedelta(minutes=30))]
    )

    assert any("completed after" in blocker for blocker in preview.blockers)
    assert preview.can_close is False


def test_preview_ignores_unrelated_running_or_pending_activity():
    unrelated = _sync_evidence(
        UNRELATED_PLAID_ITEM_ID,
        ended_at=None,
        item_status=IngestRunItemStatus.PENDING,
        run_status=IngestRunStatus.RUNNING,
    )
    preview = _minimal_preview(
        evidence=_successful_sync_evidence(), active_evidence=[unrelated]
    )

    assert preview.active_plaid_item_sync_evidence == ()
    assert preview.can_close is True


def test_preview_requires_success_for_every_relevant_plaid_item():
    snapshot = _snapshot()
    card = _card(snapshot.id, actual_amount=Decimal("0.00"), actual_date=None)
    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[card],
        credit_card_accounts=[_card_account()],
        transactions=[],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("100.00"),
        captured_balance=Decimal("100.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )

    assert preview.can_close is True
    assert {item.plaid_item_id for item in preview.plaid_item_sync_evidence} == {
        str(PAYING_PLAID_ITEM_ID),
        str(CARD_PLAID_ITEM_ID),
    }


def test_relevant_plaid_items_exclude_card_with_checking_payment_evidence():
    snapshot = _snapshot()
    card = _card(snapshot.id)
    card.actual_payment_source = "checking_account"
    card.actual_payment_transaction_id = uuid4()
    card.actual_payment_note = "Exact posted checking debit; card feed unavailable."

    relevant = service._relevant_plaid_item_ids(_account(), [card], [_card_account()])

    assert relevant == (PAYING_PLAID_ITEM_ID,)


def test_relevant_plaid_items_keep_shared_item_needed_by_another_card():
    snapshot = _snapshot()
    evidenced = _card(snapshot.id)
    evidenced.actual_payment_source = "checking_account"
    evidenced.actual_payment_transaction_id = uuid4()
    evidenced.actual_payment_note = (
        "Exact posted checking debit; card feed unavailable."
    )
    ordinary = _card(snapshot.id, account_id="card-2")

    relevant = service._relevant_plaid_item_ids(
        _account(),
        [evidenced, ordinary],
        [_card_account(), _card_account("card-2")],
    )

    assert set(relevant) == {PAYING_PLAID_ITEM_ID, CARD_PLAID_ITEM_ID}


def test_preview_blocks_stale_pending_and_null_balance():
    """A stale review, pending activity, and unknown close are hard blockers."""
    snapshot = _snapshot(last_synced_at=NOW - timedelta(days=2))
    transaction = Transaction(
        id=uuid4(),
        plaid_transaction_id="pending-1",
        plaid_item_id=uuid4(),
        account_id="checking-1",
        date=date(2026, 7, 31),
        amount=Decimal("10.00"),
        name="Pending",
        pending=True,
        reviewed=False,
        created_at=NOW - timedelta(days=3),
        updated_at=NOW - timedelta(days=3),
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[transaction],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=None,
        captured_balance=None,
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )

    assert any("stale" in blocker for blocker in preview.blockers)
    assert any("pending" in blocker for blocker in preview.blockers)
    assert any("closing balance" in blocker for blocker in preview.blockers)
    assert preview.can_close is False


def test_preview_blocks_pre_month_end_review_missing_actuals_and_capture_delta():
    """Historical close requires a complete post-month reconciliation."""
    snapshot = _snapshot(last_synced_at=datetime(2026, 7, 30, tzinfo=UTC))
    card = _card(snapshot.id)
    card.actual_payment_amount = None

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[card],
        credit_card_accounts=[_card_account()],
        transactions=[],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=Decimal("1200.00"),
        now=NOW,
        max_reconciliation_age=timedelta(days=30),
    )

    assert preview.missing_actual_credit_card_count == 1
    assert preview.captured_difference == Decimal("200.00")
    assert any(
        "before the calendar month ended" in blocker for blocker in preview.blockers
    )
    assert any("no posted actual amount" in blocker for blocker in preview.blockers)
    assert any("does not match" in blocker for blocker in preview.blockers)


def test_preview_blocks_posted_unreviewed_and_uncategorized_activity():
    """A sync timestamp cannot mask incomplete transaction review."""
    snapshot = _snapshot(last_synced_at=NOW)
    transaction = Transaction(
        id=uuid4(),
        plaid_transaction_id="posted-1",
        plaid_item_id=uuid4(),
        account_id="checking-1",
        date=date(2026, 7, 30),
        amount=Decimal("10.00"),
        name="Needs review",
        pending=False,
        reviewed=False,
        budget_category=None,
        reimbursable=True,
        created_at=NOW - timedelta(hours=2),
        updated_at=NOW - timedelta(hours=1),
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[transaction],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("100.00"),
        captured_balance=Decimal("100.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
    )

    assert preview.transaction_counts.posted == 1
    assert preview.transaction_counts.unreviewed == 1
    assert preview.transaction_counts.uncategorized == 1
    assert preview.transaction_counts.reimbursable == 1
    assert any("remain unreviewed" in blocker for blocker in preview.blockers)
    assert any("remain uncategorized" in blocker for blocker in preview.blockers)


@pytest.mark.parametrize(
    ("legacy", "normalized"),
    [(False, False), (True, False), (False, True)],
)
def test_preview_accepts_all_supported_posted_card_payment_shapes(
    legacy: bool,
    normalized: bool,
):
    """Raw PFC, normalized PFC, and restored legacy rows reconcile identically."""
    snapshot = _snapshot()
    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[_card(snapshot.id)],
        credit_card_accounts=[_card_account()],
        transactions=[
            _card_payment(
                legacy=legacy,
                normalized=normalized,
            )
        ],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=Decimal("300.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )

    assert not any("does not match" in blocker for blocker in preview.blockers)
    assert preview.can_close is True


def test_preview_requires_exact_month_end_capture_even_with_projection():
    """A mathematically complete projection cannot replace observed month-end cash."""
    snapshot = _snapshot()
    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[_card(snapshot.id)],
        credit_card_accounts=[_card_account()],
        transactions=[_card_payment()],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=None,
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
    )

    assert preview.projected_closing_balance == Decimal("300.00")
    assert preview.closing_balance_to_freeze is None
    assert any(
        "exact month-end closing balance capture" in blocker
        for blocker in preview.blockers
    )
    assert preview.can_close is False


def test_preview_blocks_pending_and_mismatched_card_side_payments():
    """Stored actuals must exactly equal posted card-side amount and latest date."""
    snapshot = _snapshot()
    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[_card(snapshot.id)],
        credit_card_accounts=[_card_account()],
        transactions=[
            _card_payment(amount="-600.00", payment_date=date(2026, 7, 10)),
            _card_payment(
                amount="-100.00",
                payment_date=date(2026, 7, 15),
                pending=True,
                legacy=True,
            ),
        ],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=Decimal("300.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
    )

    assert any("card-side payment(s)" in blocker for blocker in preview.blockers)
    assert any(
        "does not match posted card-side payments" in blocker
        for blocker in preview.blockers
    )
    assert preview.can_close is False


def test_preview_accepts_exact_checking_transaction_evidence():
    """A card-feed gap is accepted only when a posted checking row proves it."""
    snapshot = _snapshot()
    checking_payment = _card_payment(
        account_id="checking-1",
        amount="180.00",
        payment_date=date(2026, 7, 23),
    )
    card = _card(
        snapshot.id,
        actual_amount=Decimal("180.00"),
        actual_date=date(2026, 7, 23),
    )
    card.actual_payment_source = "checking_account"
    card.actual_payment_transaction_id = checking_payment.id
    card.actual_payment_note = "Unique posted checking debit; card feed omitted it."

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[card],
        credit_card_accounts=[_card_account()],
        transactions=[checking_payment],
        missing_paying_cards=[],
        next_snapshot=None,
        starting_balance=Decimal("1000.00"),
        captured_balance=Decimal("820.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(include_card=True),
    )

    assert not any(
        "does not match posted card-side" in item for item in preview.blockers
    )
    assert preview.can_close is True


def test_preview_blocks_missing_stale_and_reassigned_membership():
    """Current assignments must be represented without erasing excluded history."""
    snapshot = _snapshot()
    reassigned = _card(
        snapshot.id,
        account_id="card-reassigned",
        actual_amount=Decimal("0.00"),
        actual_date=None,
    )
    unassigned = _card(
        snapshot.id,
        account_id="card-unassigned",
        actual_amount=Decimal("0.00"),
        actual_date=None,
    )
    excluded = _card(
        snapshot.id,
        account_id="card-excluded",
        actual_amount=Decimal("10.00"),
        actual_date=date(2026, 7, 8),
    )
    reassigned_account = _card_account(
        "card-reassigned",
        paying_account_id="checking-2",
    )
    unassigned_account = _card_account(
        "card-unassigned",
        paying_account_id=None,
    )
    excluded_account = _card_account(
        "card-excluded",
        paying_account_id=None,
        is_excluded=True,
    )
    missing_account = _card_account("card-missing")

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[reassigned, unassigned, excluded],
        credit_card_accounts=[
            reassigned_account,
            unassigned_account,
            excluded_account,
            missing_account,
        ],
        transactions=[
            _card_payment(
                account_id="card-excluded",
                amount="-10.00",
                payment_date=date(2026, 7, 8),
                legacy=True,
            )
        ],
        missing_paying_cards=[unassigned_account],
        next_snapshot=None,
        starting_balance=Decimal("100.00"),
        captured_balance=Decimal("90.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
    )

    assert any("missing from the snapshot" in blocker for blocker in preview.blockers)
    assert any("is stale" in blocker for blocker in preview.blockers)
    assert any("was reassigned" in blocker for blocker in preview.blockers)
    assert not any(
        "Card card-excluded is stale" in blocker for blocker in preview.blockers
    )


def test_preview_audits_and_guards_existing_next_month():
    """Next-month state participates in both refusal logic and the audit hash."""
    snapshot = _snapshot()
    next_snapshot = _next_snapshot()
    kwargs = {
        "snapshot": snapshot,
        "account": _account(),
        "items": [],
        "cards": [],
        "credit_card_accounts": [],
        "transactions": [],
        "missing_paying_cards": [],
        "next_snapshot": next_snapshot,
        "starting_balance": Decimal("300.00"),
        "captured_balance": Decimal("300.00"),
        "now": NOW,
        "max_reconciliation_age": timedelta(hours=24),
        "plaid_item_sync_evidence": _successful_sync_evidence(),
    }

    empty_next = service._calculate_preview(**kwargs)
    assert empty_next.can_close is True
    assert empty_next.next_year_month == "2026-08"
    assert empty_next.next_snapshot_id == str(next_snapshot.id)
    assert empty_next.next_snapshot_status == SnapshotStatus.OPEN.value
    assert empty_next.next_starting_balance is None

    next_snapshot.starting_balance = Decimal("299.00")
    conflicting = service._calculate_preview(**kwargs)
    assert conflicting.audit_hash != empty_next.audit_hash
    assert any("conflicts with" in blocker for blocker in conflicting.blockers)

    next_snapshot.starting_balance = Decimal("300.00")
    matching = service._calculate_preview(**kwargs)
    assert matching.can_close is True

    next_snapshot.status = SnapshotStatus.CLOSED
    closed = service._calculate_preview(**kwargs)
    assert any("already closed" in blocker for blocker in closed.blockers)


def test_preview_blocks_out_of_order_close_without_using_open_prior_estimate():
    """An OPEN prior month is a blocker, never an implicit calculated rollover."""
    snapshot = _snapshot()
    prior = _prior_snapshot(
        status=SnapshotStatus.OPEN,
        closing_balance=Decimal("999.00"),
        frozen=False,
    )
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, prior, Decimal("777.00")
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[],
        missing_paying_cards=[],
        prior_snapshot=prior,
        next_snapshot=None,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        captured_balance=Decimal("0.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(),
    )

    assert starting_balance is None
    assert preview.starting_balance_provenance == "invalid_prior_snapshot"
    assert any("must be closed first" in blocker for blocker in preview.blockers)
    assert preview.can_close is False


def test_preview_blocks_direct_start_that_conflicts_with_frozen_prior():
    """A stored current-month override cannot break the frozen rollover chain."""
    snapshot = _snapshot()
    snapshot.starting_balance = Decimal("10001.00")
    prior = _prior_snapshot()
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, prior, None
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[],
        missing_paying_cards=[],
        prior_snapshot=prior,
        next_snapshot=None,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        captured_balance=Decimal("10001.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(),
    )

    assert preview.direct_starting_balance == Decimal("10001.00")
    assert preview.starting_balance_provenance == "current_snapshot_direct"
    assert any("conflicts with prior-month frozen close" in b for b in preview.blockers)


@pytest.mark.parametrize(
    ("frozen", "closing_balance", "blocker_text"),
    [
        (False, Decimal("10000.00"), "has no frozen close"),
        (True, None, "has a null closing balance"),
    ],
)
def test_preview_blocks_unfrozen_or_null_prior_close(
    frozen: bool,
    closing_balance: Decimal | None,
    blocker_text: str,
):
    """CLOSED alone is insufficient; the prior close must be frozen and non-null."""
    snapshot = _snapshot()
    prior = _prior_snapshot(frozen=frozen, closing_balance=closing_balance)
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, prior, None
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[],
        missing_paying_cards=[],
        prior_snapshot=prior,
        next_snapshot=None,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        captured_balance=Decimal("0.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
    )

    assert starting_balance is None
    assert any(blocker_text in blocker for blocker in preview.blockers)


def test_preview_accepts_and_serializes_valid_frozen_prior():
    """A valid prior close supplies the exact starting balance and audit metadata."""
    snapshot = _snapshot()
    prior = _prior_snapshot()
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, prior, None
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[],
        missing_paying_cards=[],
        prior_snapshot=prior,
        next_snapshot=None,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        captured_balance=Decimal("10000.00"),
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(),
    )
    payload = preview.to_dict()

    assert preview.can_close is True
    assert preview.starting_balance == Decimal("10000.00")
    assert preview.starting_balance_provenance == "prior_frozen_close"
    assert payload["prior_year_month"] == "2026-06"
    assert payload["prior_snapshot_id"] == str(prior.id)
    assert payload["prior_snapshot_status"] == SnapshotStatus.CLOSED.value
    assert payload["prior_direct_starting_balance"] == "9000.00"
    assert payload["prior_closing_balance"] == "10000.00"
    assert payload["prior_closing_balance_frozen"] is True
    assert payload["prior_snapshot_updated_at"] == NOW.isoformat()


def test_preview_hash_invalidates_when_prior_snapshot_changes():
    """Prior state is part of the v4 deterministic close audit."""
    snapshot = _snapshot()
    prior = _prior_snapshot()
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, prior, None
    )
    kwargs = {
        "snapshot": snapshot,
        "account": _account(),
        "items": [],
        "cards": [],
        "credit_card_accounts": [],
        "transactions": [],
        "missing_paying_cards": [],
        "prior_snapshot": prior,
        "next_snapshot": None,
        "starting_balance": starting_balance,
        "starting_balance_provenance": provenance,
        "captured_balance": Decimal("10000.00"),
        "now": NOW,
        "max_reconciliation_age": timedelta(hours=24),
    }

    first = service._calculate_preview(**kwargs)
    prior.updated_at = NOW + timedelta(seconds=1)
    changed = service._calculate_preview(**kwargs)

    assert first.audit_hash != changed.audit_hash


@pytest.mark.parametrize(
    ("direct_balance", "exact_fallback", "expected_source"),
    [
        (
            Decimal("10000.00"),
            Decimal("9999.00"),
            "bootstrap_direct_starting_balance",
        ),
        (None, Decimal("10000.00"), "bootstrap_exact_balance"),
    ],
)
def test_preview_allows_explicit_no_prior_bootstrap(
    direct_balance: Decimal | None,
    exact_fallback: Decimal,
    expected_source: str,
):
    """The first tracked month may use a direct start or exact prior-end capture."""
    snapshot = _snapshot()
    snapshot.starting_balance = direct_balance
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, None, exact_fallback
    )

    preview = service._calculate_preview(
        snapshot=snapshot,
        account=_account(),
        items=[],
        cards=[],
        credit_card_accounts=[],
        transactions=[],
        missing_paying_cards=[],
        prior_snapshot=None,
        next_snapshot=None,
        starting_balance=starting_balance,
        starting_balance_provenance=provenance,
        captured_balance=starting_balance,
        now=NOW,
        max_reconciliation_age=timedelta(hours=24),
        plaid_item_sync_evidence=_successful_sync_evidence(),
    )

    assert preview.can_close is True
    assert preview.starting_balance == Decimal("10000.00")
    assert preview.starting_balance_provenance == expected_source
    assert preview.prior_year_month == "2026-06"
    assert preview.prior_snapshot_id is None


def test_preview_blocks_bootstrap_across_existing_history_gap():
    """A missing immediate prior is not a first-month bootstrap when history exists."""
    snapshot = _snapshot()
    snapshot.starting_balance = Decimal("10000.00")
    starting_balance, provenance = service._resolve_starting_balance(
        snapshot, None, Decimal("9999.00")
    )
    kwargs = {
        "snapshot": snapshot,
        "account": _account(),
        "items": [],
        "cards": [],
        "credit_card_accounts": [],
        "transactions": [],
        "missing_paying_cards": [],
        "prior_snapshot": None,
        "next_snapshot": None,
        "starting_balance": starting_balance,
        "starting_balance_provenance": provenance,
        "captured_balance": starting_balance,
        "now": NOW,
        "max_reconciliation_age": timedelta(hours=24),
        "plaid_item_sync_evidence": _successful_sync_evidence(),
    }

    first_month = service._calculate_preview(**kwargs)
    history_gap = service._calculate_preview(
        **kwargs,
        has_earlier_snapshot=True,
    )

    assert first_month.can_close is True
    assert history_gap.can_close is False
    assert history_gap.has_earlier_snapshot is True
    assert history_gap.audit_hash != first_month.audit_hash
    assert history_gap.to_dict()["has_earlier_snapshot"] is True
    assert any(
        "missing despite earlier snapshot history" in b for b in history_gap.blockers
    )


def test_guarded_close_does_not_create_an_absent_next_month(monkeypatch):
    """Closing does not implicitly create a future snapshot row."""
    snapshot, preview = _ready_preview()
    session = MagicMock()
    locked_result = MagicMock()
    locked_result.scalars.return_value = [snapshot]
    session.execute.side_effect = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        locked_result,
    ]
    monkeypatch.setattr(service, "build_close_preview", lambda *args, **kwargs: preview)

    returned = service.close_snapshot(
        session,
        "2026-07",
        "checking-1",
        confirm_month="2026-07",
        audit_hash=preview.audit_hash,
        now=NOW,
    )

    assert returned.status == SnapshotStatus.CLOSED.value
    assert returned.next_snapshot_id is None
    session.add.assert_not_called()


def test_guarded_close_requires_hash_and_caches_every_total(monkeypatch):
    """A matching preview locks rollover rows and freezes every actual total."""
    prior_snapshot = _prior_snapshot()
    next_snapshot = _next_snapshot()
    snapshot, preview = _ready_preview(next_snapshot=next_snapshot)
    session = MagicMock()
    locked_result = MagicMock()
    locked_result.scalars.return_value = [prior_snapshot, snapshot, next_snapshot]
    session.execute.side_effect = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        locked_result,
    ]
    monkeypatch.setattr(service, "build_close_preview", lambda *args, **kwargs: preview)

    returned = service.close_snapshot(
        session,
        "2026-07",
        "checking-1",
        confirm_month="2026-07",
        audit_hash=preview.audit_hash,
        now=NOW,
    )

    assert returned.audit_hash == preview.audit_hash
    assert returned.status == SnapshotStatus.CLOSED.value
    assert returned.closed_at == NOW
    assert returned.next_starting_balance == Decimal("12500.00")
    assert snapshot.status == SnapshotStatus.CLOSED
    assert snapshot.income_total == Decimal("5000.00")
    assert snapshot.expense_total == Decimal("2000.00")
    assert snapshot.transfer_in_total == Decimal("300.00")
    assert snapshot.transfer_out_total == Decimal("100.00")
    assert snapshot.credit_card_total == Decimal("700.00")
    assert snapshot.net == Decimal("2500.00")
    assert snapshot.closing_balance == Decimal("12500.00")
    assert snapshot.closing_balance_frozen is True
    assert next_snapshot.starting_balance == Decimal("12500.00")
    session.add.assert_not_called()
    session.flush.assert_called_once()
    isolation_statement = session.execute.call_args_list[0].args[0]
    coordination_statement = session.execute.call_args_list[1].args[0]
    transaction_statement = session.execute.call_args_list[2].args[0]
    lock_statement = session.execute.call_args_list[3].args[0]
    assert str(isolation_statement) == "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"
    assert str(coordination_statement) == "LOCK TABLE plaid_items IN SHARE MODE"
    assert str(transaction_statement) == "LOCK TABLE transactions IN SHARE MODE"
    lock_sql = str(lock_statement)
    lock_months = next(
        value
        for value in lock_statement.compile().params.values()
        if isinstance(value, list)
    )
    assert lock_months == ["2026-06", "2026-07", "2026-08"]
    assert "ORDER BY monthly_snapshots.year_month" in lock_sql
    assert "FOR UPDATE" in lock_sql


def test_guarded_close_rejects_stale_audit_hash_without_mutating(monkeypatch):
    """The preview must be repeated after any audited input changes."""
    snapshot, preview = _ready_preview()
    session = MagicMock()
    locked_result = MagicMock()
    locked_result.scalars.return_value = [snapshot]
    session.execute.side_effect = [
        MagicMock(),
        MagicMock(),
        MagicMock(),
        locked_result,
    ]
    monkeypatch.setattr(service, "build_close_preview", lambda *args, **kwargs: preview)

    with pytest.raises(ValueError, match="Audit hash mismatch"):
        service.close_snapshot(
            session,
            "2026-07",
            "checking-1",
            confirm_month="2026-07",
            audit_hash="wrong",
            now=NOW,
        )

    assert snapshot.status == SnapshotStatus.OPEN
    assert snapshot.closing_balance_frozen is not True
    session.flush.assert_not_called()
