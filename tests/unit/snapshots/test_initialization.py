"""Focused tests for guarded missing-snapshot initialization."""

from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import Mock, patch
from uuid import uuid4

import pytest

from budget_me.db.models.account import Account
from budget_me.db.models.anticipated_item import AnticipatedItem
from budget_me.db.models.credit_liability import CreditLiability
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.snapshots import initialization

NOW = datetime(2026, 8, 10, 12, 0, tzinfo=UTC)
MONTH = "2026-07"
ACCOUNT_ID = "checking-account"


def _account(
    *,
    account_id: str = ACCOUNT_ID,
    account_type: str = "depository",
    is_excluded: bool = False,
    payment_strategy: str = "pay_in_full",
    fixed_payment_amount: Decimal | None = None,
    paying_account_id: str | None = None,
) -> Account:
    return Account(
        id=uuid4(),
        plaid_item_id=uuid4(),
        account_id=account_id,
        name=f"Private name {account_id}",
        type=account_type,
        subtype="checking" if account_type == "depository" else "credit card",
        is_excluded=is_excluded,
        payment_strategy=payment_strategy,
        fixed_payment_amount=fixed_payment_amount,
        paying_account_id=paying_account_id,
        created_at=NOW,
        updated_at=NOW,
    )


def _item(
    name: str,
    amount: str,
    item_type: str,
    *,
    frequency: str = "monthly",
    start_month: str | None = None,
    end_month: str | None = None,
    category: str | None = None,
) -> AnticipatedItem:
    return AnticipatedItem(
        id=uuid4(),
        name=name,
        amount=Decimal(amount),
        item_type=item_type,
        category=category,
        active=True,
        frequency=frequency,
        start_month=start_month,
        end_month=end_month,
        account_id=ACCOUNT_ID,
        created_at=NOW,
        updated_at=NOW,
    )


def _liability(card: Account, statement_balance: str | None) -> CreditLiability:
    return CreditLiability(
        id=uuid4(),
        plaid_item_id=card.plaid_item_id,
        account_id=card.account_id,
        last_statement_balance=(
            Decimal(statement_balance) if statement_balance is not None else None
        ),
        next_payment_due_date=date(2026, 7, 20),
        created_at=NOW,
        updated_at=NOW,
    )


def _inputs(
    *,
    account: Account | None = None,
    existing_snapshot: MonthlySnapshot | None = None,
    items: tuple[AnticipatedItem, ...] = (),
    cards: tuple[tuple[Account, CreditLiability | None], ...] = (),
) -> initialization._InitializationInputs:
    return initialization._InitializationInputs(
        account=account if account is not None else _account(),
        existing_snapshot=existing_snapshot,
        anticipated_items=items,
        card_sources=cards,
    )


def _missing_account_inputs() -> initialization._InitializationInputs:
    return initialization._InitializationInputs(
        account=None,
        existing_snapshot=None,
        anticipated_items=(),
        card_sources=(),
    )


def test_preview_is_deterministic_aggregate_only_and_month_aware() -> None:
    """The hash sees full inputs while output exposes only counts and totals."""
    income = _item("Private salary", "1000.00", "income")
    quarterly = _item(
        "Private quarterly bill", "100.00", "expense", frequency="quarterly"
    )
    one_time = _item(
        "Private July bill",
        "25.00",
        "expense",
        frequency="one_time",
        start_month=MONTH,
    )
    future = _item(
        "Private August bill",
        "99.00",
        "expense",
        frequency="annual",
        start_month="2026-08",
    )
    full_card = _account(
        account_id="full-card",
        account_type="credit",
        paying_account_id=ACCOUNT_ID,
    )
    promo_card = _account(
        account_id="promo-card",
        account_type="credit",
        payment_strategy="promotional_paydown",
        fixed_payment_amount=Decimal("50.00"),
        paying_account_id=ACCOUNT_ID,
    )
    inputs = _inputs(
        items=(future, one_time, quarterly, income),
        cards=((promo_card, None), (full_card, _liability(full_card, "200.00"))),
    )

    first = initialization._prepare_initialization(MONTH, ACCOUNT_ID, inputs).preview
    reordered = initialization._prepare_initialization(
        MONTH,
        ACCOUNT_ID,
        initialization._InitializationInputs(
            account=inputs.account,
            existing_snapshot=None,
            anticipated_items=tuple(reversed(inputs.anticipated_items)),
            card_sources=tuple(reversed(inputs.card_sources)),
        ),
    ).preview

    assert first.can_initialize is True
    assert first.anticipated_item_count == 3
    assert first.income_item_count == 1
    assert first.expense_item_count == 2
    assert first.credit_card_count == 2
    assert first.totals.to_dict() == {
        "income_total": "1000.00",
        "expense_total": "125.00",
        "transfer_in_total": "0.00",
        "transfer_out_total": "0.00",
        "reimbursement_in_total": "0.00",
        "reimbursement_out_total": "0.00",
        "credit_card_total": "250.00",
        "net": "625.00",
    }
    assert first.audit_hash == reordered.audit_hash
    assert any("seeds current" in warning for warning in first.warnings)
    assert any("review every seeded row" in warning for warning in first.warnings)

    rendered = json.dumps(first.to_dict())
    for private_value in (
        "Private salary",
        "Private quarterly bill",
        "Private July bill",
        "Private August bill",
        "full-card",
        "promo-card",
    ):
        assert private_value not in rendered

    income.category = "changed-private-category"
    changed = initialization._prepare_initialization(MONTH, ACCOUNT_ID, inputs).preview
    assert changed.audit_hash != first.audit_hash


@pytest.mark.parametrize(
    ("inputs", "message"),
    [
        (_missing_account_inputs(), "does not exist"),
        (_inputs(account=_account(is_excluded=True)), "excluded"),
        (
            _inputs(account=_account(account_type="credit")),
            "must be a depository",
        ),
        (
            _inputs(
                existing_snapshot=MonthlySnapshot(
                    id=uuid4(),
                    year_month=MONTH,
                    account_id=ACCOUNT_ID,
                    status=SnapshotStatus.OPEN,
                    created_at=NOW,
                    updated_at=NOW,
                )
            ),
            "already exists",
        ),
    ],
)
def test_preview_blocks_invalid_target_states(
    inputs: initialization._InitializationInputs, message: str
) -> None:
    preview = initialization._prepare_initialization(MONTH, ACCOUNT_ID, inputs).preview

    assert preview.can_initialize is False
    assert any(message in blocker for blocker in preview.blockers)


def test_preview_blocks_invalid_seed_data_and_aggregates_warnings() -> None:
    invalid_item = _item("Private invalid", "-1.00", "other", frequency="weekly")
    bad_card = _account(
        account_id="bad-card",
        account_type="credit",
        payment_strategy="unknown",
        paying_account_id=ACCOUNT_ID,
    )
    no_statement_card = _account(
        account_id="no-statement-card",
        account_type="credit",
        paying_account_id=ACCOUNT_ID,
    )

    preview = initialization._prepare_initialization(
        MONTH,
        ACCOUNT_ID,
        _inputs(
            items=(invalid_item,),
            cards=((bad_card, None), (no_statement_card, None)),
        ),
    ).preview

    assert preview.can_initialize is False
    assert any("unsupported types" in blocker for blocker in preview.blockers)
    assert any("unsupported frequencies" in blocker for blocker in preview.blockers)
    assert any("negative amounts" in blocker for blocker in preview.blockers)
    assert any("payment strategies" in blocker for blocker in preview.blockers)
    assert any("1 pay-in-full card" in warning for warning in preview.warnings)


def test_public_preview_reads_without_writing() -> None:
    session = Mock()
    inputs = _inputs(items=(_item("Private plan", "10.00", "expense"),))

    with patch.object(
        initialization, "_load_initialization_inputs", return_value=inputs
    ) as loader:
        preview = initialization.build_initialization_preview(
            session, MONTH, ACCOUNT_ID
        )

    assert preview.can_initialize is True
    loader.assert_called_once_with(session, MONTH, ACCOUNT_ID)
    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_invalid_month_and_confirmation_fail_before_database_access() -> None:
    session = Mock()

    with pytest.raises(ValueError, match="YYYY-MM"):
        initialization.build_initialization_preview(session, "2026-7", ACCOUNT_ID)
    with pytest.raises(ValueError, match="exactly match"):
        initialization.initialize_snapshot(
            session,
            MONTH,
            ACCOUNT_ID,
            confirm_month="2026-06",
            audit_hash="unused",
        )

    session.execute.assert_not_called()
    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_initialize_locks_revalidates_and_flushes_without_committing() -> None:
    income = _item("Private salary", "500.00", "income")
    expense = _item("Private bill", "100.00", "expense")
    card = _account(
        account_id="card-account",
        account_type="credit",
        paying_account_id=ACCOUNT_ID,
    )
    inputs = _inputs(
        items=(income, expense),
        cards=((card, _liability(card, "50.00")),),
    )
    preview = initialization._prepare_initialization(MONTH, ACCOUNT_ID, inputs).preview
    session = Mock()
    events: list[str] = []
    session.execute.side_effect = lambda statement: events.append(str(statement))

    def assign_snapshot_id() -> None:
        if session.add.called:
            candidate = session.add.call_args.args[0]
            if candidate.id is None:
                candidate.id = uuid4()

    session.flush.side_effect = assign_snapshot_id

    def record_plaid_lock(_session) -> None:
        events.append("plaid-share-lock")

    with (
        patch.object(
            initialization, "_load_initialization_inputs", return_value=inputs
        ),
        patch.object(
            initialization,
            "acquire_close_coordination_lock",
            side_effect=record_plaid_lock,
        ),
    ):
        snapshot = initialization.initialize_snapshot(
            session,
            MONTH,
            ACCOUNT_ID,
            confirm_month=MONTH,
            audit_hash=preview.audit_hash,
        )

    assert events == [
        "SET TRANSACTION ISOLATION LEVEL SERIALIZABLE",
        "plaid-share-lock",
        "LOCK TABLE monthly_snapshots IN SHARE ROW EXCLUSIVE MODE",
        "LOCK TABLE accounts IN SHARE MODE",
        "LOCK TABLE anticipated_items IN SHARE MODE",
        "LOCK TABLE credit_liabilities IN SHARE MODE",
    ]
    assert snapshot.status == SnapshotStatus.OPEN
    assert snapshot.income_total == Decimal("500.00")
    assert snapshot.expense_total == Decimal("100.00")
    assert snapshot.transfer_in_total == Decimal("0.00")
    assert snapshot.transfer_out_total == Decimal("0.00")
    assert snapshot.reimbursement_in_total == Decimal("0.00")
    assert snapshot.reimbursement_out_total == Decimal("0.00")
    assert snapshot.credit_card_total == Decimal("50.00")
    assert snapshot.net == Decimal("350.00")
    assert snapshot.last_synced_at is None

    session.add.assert_called_once_with(snapshot)
    children = session.add_all.call_args.args[0]
    line_items = [child for child in children if isinstance(child, SnapshotLineItem)]
    cards = [child for child in children if isinstance(child, SnapshotCreditCard)]
    assert len(line_items) == 2
    assert {item.source_item_id for item in line_items} == {income.id, expense.id}
    assert len(cards) == 1
    assert cards[0].actual_payment_amount is None
    assert cards[0].calculated_payment == Decimal("50.00")
    assert session.flush.call_count == 2
    session.commit.assert_not_called()
    session.rollback.assert_not_called()


def test_initialize_rejects_hash_mismatch_without_writing() -> None:
    inputs = _inputs()
    session = Mock()

    with (
        patch.object(
            initialization, "_load_initialization_inputs", return_value=inputs
        ),
        patch.object(initialization, "acquire_close_coordination_lock"),
        pytest.raises(ValueError, match="Audit hash mismatch"),
    ):
        initialization.initialize_snapshot(
            session,
            MONTH,
            ACCOUNT_ID,
            confirm_month=MONTH,
            audit_hash="0" * 64,
        )

    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_called()
    session.commit.assert_not_called()


def test_initialize_rejects_newly_existing_snapshot_after_preview() -> None:
    preview_inputs = _inputs()
    preview = initialization._prepare_initialization(
        MONTH, ACCOUNT_ID, preview_inputs
    ).preview
    existing = MonthlySnapshot(
        id=uuid4(),
        year_month=MONTH,
        account_id=ACCOUNT_ID,
        status=SnapshotStatus.OPEN,
        created_at=NOW,
        updated_at=NOW,
    )
    apply_inputs = _inputs(existing_snapshot=existing)
    session = Mock()

    with (
        patch.object(
            initialization, "_load_initialization_inputs", return_value=apply_inputs
        ),
        patch.object(initialization, "acquire_close_coordination_lock"),
        pytest.raises(ValueError, match="Audit hash mismatch"),
    ):
        initialization.initialize_snapshot(
            session,
            MONTH,
            ACCOUNT_ID,
            confirm_month=MONTH,
            audit_hash=preview.audit_hash,
        )

    session.add.assert_not_called()
    session.flush.assert_not_called()


def test_initialize_rejects_matching_blocked_preview_without_writing() -> None:
    inputs = _missing_account_inputs()
    preview = initialization._prepare_initialization(MONTH, ACCOUNT_ID, inputs).preview
    session = Mock()

    with (
        patch.object(
            initialization, "_load_initialization_inputs", return_value=inputs
        ),
        patch.object(initialization, "acquire_close_coordination_lock"),
        pytest.raises(ValueError, match="Cannot initialize snapshot"),
    ):
        initialization.initialize_snapshot(
            session,
            MONTH,
            ACCOUNT_ID,
            confirm_month=MONTH,
            audit_hash=preview.audit_hash,
        )

    session.add.assert_not_called()
    session.add_all.assert_not_called()
    session.flush.assert_not_called()
