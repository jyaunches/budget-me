"""PostgreSQL proof for the reconcile-cc preview/apply boundary."""

from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from sqlalchemy import delete
from sqlalchemy.orm import Session

from budget_me.cli.commands.reconcile_cc import _reconcile_async
from budget_me.db.models.account import Account
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.plaid_item import PlaidItem
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.transaction import Transaction
from budget_me.streamlit_app.db import get_sync_engine

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def _capture_state(
    engine,
    *,
    card_ids: tuple[UUID, ...],
    snapshot_ids: tuple[UUID, ...],
    transaction_ids: tuple[UUID, ...],
) -> dict[str, dict[UUID, tuple]]:
    """Read every field whose mutation would violate the command boundary."""
    with Session(bind=engine) as session:
        cards = {
            card_id: (
                card.actual_payment_amount,
                card.actual_payment_date,
                card.created_at,
                card.updated_at,
            )
            for card_id in card_ids
            if (card := session.get(SnapshotCreditCard, card_id)) is not None
        }
        snapshots = {
            snapshot_id: (
                snapshot.status,
                snapshot.last_synced_at,
                snapshot.created_at,
                snapshot.updated_at,
            )
            for snapshot_id in snapshot_ids
            if (snapshot := session.get(MonthlySnapshot, snapshot_id)) is not None
        }
        transactions = {
            transaction_id: (
                transaction.amount,
                transaction.date,
                transaction.created_at,
                transaction.updated_at,
            )
            for transaction_id in transaction_ids
            if (transaction := session.get(Transaction, transaction_id)) is not None
        }
    return {
        "cards": cards,
        "snapshots": snapshots,
        "transactions": transactions,
    }


@pytest.mark.asyncio
async def test_reconcile_cc_writes_only_after_exact_confirmed_apply(
    database_test_target,
) -> None:
    """Default/dry preview roll back; apply is scoped; closed rows stay frozen."""
    engine = get_sync_engine()
    suffix = uuid4().hex
    month = "2096-07"
    historical = datetime(2020, 1, 1, 12, 0, tzinfo=UTC)
    selected_checking_id = f"reconcile-selected-checking-{suffix}"
    selected_card_id = f"reconcile-selected-card-{suffix}"
    other_checking_id = f"reconcile-other-checking-{suffix}"
    other_card_id = f"reconcile-other-card-{suffix}"
    closed_checking_id = f"reconcile-closed-checking-{suffix}"
    closed_card_id = f"reconcile-closed-card-{suffix}"
    account_ids = (
        selected_checking_id,
        other_checking_id,
        closed_checking_id,
    )
    plaid_item_id: UUID | None = None

    try:
        with Session(bind=engine) as session:
            plaid_item = PlaidItem(
                user_key="integration",
                item_id=f"reconcile-boundary-item-{suffix}",
                access_token_enc="synthetic",
            )
            session.add(plaid_item)
            session.flush()
            plaid_item_id = plaid_item.id

            checkings = [
                Account(
                    plaid_item_id=plaid_item.id,
                    account_id=account_id,
                    name="Synthetic Checking",
                    type="depository",
                    subtype="checking",
                    is_excluded=False,
                )
                for account_id in account_ids
            ]
            session.add_all(checkings)
            session.flush()
            cards = [
                Account(
                    plaid_item_id=plaid_item.id,
                    account_id=card_id,
                    name="Synthetic Card",
                    type="credit",
                    subtype="credit card",
                    paying_account_id=checking_id,
                    is_excluded=False,
                )
                for card_id, checking_id in (
                    (selected_card_id, selected_checking_id),
                    (other_card_id, other_checking_id),
                    (closed_card_id, closed_checking_id),
                )
            ]
            session.add_all(cards)
            session.flush()

            selected_snapshot = MonthlySnapshot(
                year_month=month,
                account_id=selected_checking_id,
                status=SnapshotStatus.OPEN,
                last_synced_at=historical,
                created_at=historical,
                updated_at=historical,
            )
            other_snapshot = MonthlySnapshot(
                year_month=month,
                account_id=other_checking_id,
                status=SnapshotStatus.OPEN,
                last_synced_at=historical,
                created_at=historical,
                updated_at=historical,
            )
            closed_snapshot = MonthlySnapshot(
                year_month=month,
                account_id=closed_checking_id,
                status=SnapshotStatus.CLOSED,
                last_synced_at=historical,
                closing_balance_frozen=True,
                closed_at=historical,
                created_at=historical,
                updated_at=historical,
            )
            session.add_all([selected_snapshot, other_snapshot, closed_snapshot])
            session.flush()

            snapshot_cards = [
                SnapshotCreditCard(
                    snapshot_id=snapshot.id,
                    account_id=card_id,
                    payment_strategy="pay_in_full",
                    calculated_payment=Decimal("100.00"),
                    actual_payment_amount=amount,
                    actual_payment_date=payment_date,
                    created_at=historical,
                    updated_at=historical,
                )
                for snapshot, card_id, amount, payment_date in (
                    (
                        selected_snapshot,
                        selected_card_id,
                        Decimal("10.00"),
                        date(2096, 7, 1),
                    ),
                    (
                        other_snapshot,
                        other_card_id,
                        Decimal("20.00"),
                        date(2096, 7, 2),
                    ),
                    (
                        closed_snapshot,
                        closed_card_id,
                        Decimal("30.00"),
                        date(2096, 7, 3),
                    ),
                )
            ]
            session.add_all(snapshot_cards)

            transactions = [
                Transaction(
                    plaid_transaction_id=f"reconcile-payment-{label}-{suffix}",
                    plaid_item_id=plaid_item.id,
                    account_id=card_id,
                    date=payment_date,
                    amount=amount,
                    name="Synthetic card payment",
                    pending=False,
                    category_detailed="Payment, Credit Card",
                    reviewed=True,
                    created_at=historical,
                    updated_at=historical,
                )
                for label, card_id, amount, payment_date in (
                    (
                        "selected",
                        selected_card_id,
                        Decimal("-42.00"),
                        date(2096, 7, 20),
                    ),
                    (
                        "other",
                        other_card_id,
                        Decimal("-52.00"),
                        date(2096, 7, 21),
                    ),
                    (
                        "closed",
                        closed_card_id,
                        Decimal("-62.00"),
                        date(2096, 7, 22),
                    ),
                )
            ]
            session.add_all(transactions)
            session.commit()

            card_row_ids = tuple(card.id for card in snapshot_cards)
            snapshot_row_ids = (
                selected_snapshot.id,
                other_snapshot.id,
                closed_snapshot.id,
            )
            transaction_row_ids = tuple(transaction.id for transaction in transactions)
            selected_snapshot_card_row_id = snapshot_cards[0].id
            selected_snapshot_row_id = selected_snapshot.id
            other_snapshot_card_row_id = snapshot_cards[1].id
            closed_snapshot_card_row_id = snapshot_cards[2].id

        baseline = _capture_state(
            engine,
            card_ids=card_row_ids,
            snapshot_ids=snapshot_row_ids,
            transaction_ids=transaction_row_ids,
        )

        assert await _reconcile_async(month, selected_checking_id) == 0
        assert (
            _capture_state(
                engine,
                card_ids=card_row_ids,
                snapshot_ids=snapshot_row_ids,
                transaction_ids=transaction_row_ids,
            )
            == baseline
        )

        assert await _reconcile_async(month, selected_checking_id, dry_run=True) == 0
        assert (
            _capture_state(
                engine,
                card_ids=card_row_ids,
                snapshot_ids=snapshot_row_ids,
                transaction_ids=transaction_row_ids,
            )
            == baseline
        )

        assert (
            await _reconcile_async(
                month,
                selected_checking_id,
                apply=True,
                confirm_month=month,
            )
            == 0
        )
        applied = _capture_state(
            engine,
            card_ids=card_row_ids,
            snapshot_ids=snapshot_row_ids,
            transaction_ids=transaction_row_ids,
        )
        selected_card_state = applied["cards"][selected_snapshot_card_row_id]
        assert selected_card_state[0] == Decimal("42.00")
        assert selected_card_state[1] == date(2096, 7, 20)
        assert selected_card_state[2] == historical
        assert selected_card_state[3] > historical
        assert (
            applied["snapshots"][selected_snapshot_row_id]
            == baseline["snapshots"][selected_snapshot_row_id]
        )
        assert (
            applied["cards"][other_snapshot_card_row_id]
            == baseline["cards"][other_snapshot_card_row_id]
        )
        assert (
            applied["cards"][closed_snapshot_card_row_id]
            == baseline["cards"][closed_snapshot_card_row_id]
        )
        assert applied["transactions"] == baseline["transactions"]

        assert (
            await _reconcile_async(
                month,
                closed_checking_id,
                apply=True,
                confirm_month=month,
            )
            == 1
        )
        assert (
            _capture_state(
                engine,
                card_ids=card_row_ids,
                snapshot_ids=snapshot_row_ids,
                transaction_ids=transaction_row_ids,
            )
            == applied
        )
    finally:
        with Session(bind=engine) as session:
            session.execute(
                delete(MonthlySnapshot).where(
                    MonthlySnapshot.account_id.in_(account_ids)
                )
            )
            if plaid_item_id is not None:
                session.execute(delete(PlaidItem).where(PlaidItem.id == plaid_item_id))
            session.commit()
        engine.dispose()
