"""PostgreSQL regressions for snapshot mutation locking and bootstrap history."""

import asyncio
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from budget_me.db.engine import get_engine, get_session_factory
from budget_me.db.models.account import Account
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.plaid_item import PlaidItem
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo
from budget_me.snapshots.service import build_close_preview
from budget_me.streamlit_app.db import get_sync_engine

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


@pytest.mark.asyncio
async def test_reconcile_style_mutation_waits_for_close_and_refreshes_status(
    database_test_target,
) -> None:
    """A stale OPEN identity cannot commit a child edit after the parent closes."""
    sync_engine = get_sync_engine()
    async_engine = get_engine()
    suffix = uuid4().hex
    checking_id = f"mutation-lock-checking-{suffix}"
    card_account_id = f"mutation-lock-card-{suffix}"
    plaid_item_id = None
    snapshot_id = None
    card_row_id = None
    writer_session = get_session_factory(async_engine)()
    close_session = Session(bind=sync_engine)
    mutation_task = None

    try:
        with Session(bind=sync_engine) as setup:
            plaid_item = PlaidItem(
                user_key="integration",
                item_id=f"mutation-lock-item-{suffix}",
                access_token_enc="synthetic",
            )
            setup.add(plaid_item)
            setup.flush()
            plaid_item_id = plaid_item.id
            setup.add(
                Account(
                    plaid_item_id=plaid_item.id,
                    account_id=checking_id,
                    name="Mutation Lock Checking",
                    type="depository",
                    subtype="checking",
                    is_excluded=False,
                )
            )
            setup.flush()
            setup.add(
                Account(
                    plaid_item_id=plaid_item.id,
                    account_id=card_account_id,
                    name="Mutation Lock Card",
                    type="credit",
                    subtype="credit card",
                    paying_account_id=checking_id,
                    is_excluded=False,
                )
            )
            setup.flush()
            snapshot = MonthlySnapshot(
                year_month="2097-07",
                account_id=checking_id,
                status=SnapshotStatus.OPEN,
            )
            setup.add(snapshot)
            setup.flush()
            snapshot_id = snapshot.id
            card = SnapshotCreditCard(
                snapshot_id=snapshot.id,
                account_id=card_account_id,
                statement_balance=Decimal("50.00"),
                payment_strategy="pay_in_full",
                calculated_payment=Decimal("50.00"),
            )
            setup.add(card)
            setup.flush()
            card_row_id = card.id
            setup.commit()

        repo = MonthlySnapshotRepo(writer_session)
        preloaded = await repo.get_open_snapshots()
        assert any(snapshot.id == snapshot_id for snapshot in preloaded)
        await writer_session.execute(text("SET LOCAL lock_timeout = '2s'"))
        await writer_session.execute(text("SET LOCAL statement_timeout = '3s'"))

        locked = close_session.execute(
            select(MonthlySnapshot)
            .where(MonthlySnapshot.id == snapshot_id)
            .with_for_update()
        ).scalar_one()
        locked.status = SnapshotStatus.CLOSED
        locked.closing_balance = Decimal("50.00")
        locked.closing_balance_frozen = True
        close_session.flush()

        mutation_task = asyncio.create_task(
            repo.update_credit_card(
                card_row_id,
                statement_balance=Decimal("500.00"),
            )
        )
        await asyncio.sleep(0.1)
        assert not mutation_task.done(), (
            "mutation did not wait for the concurrent close row lock"
        )

        close_session.commit()
        with pytest.raises(RuntimeError, match="closed and immutable"):
            await asyncio.wait_for(mutation_task, timeout=3)
        await writer_session.rollback()

        with Session(bind=sync_engine) as verify:
            persisted_snapshot = verify.get(MonthlySnapshot, snapshot_id)
            persisted_card = verify.get(SnapshotCreditCard, card_row_id)
            assert persisted_snapshot.status == SnapshotStatus.CLOSED
            assert persisted_card.statement_balance == Decimal("50.00")
    finally:
        close_session.rollback()
        close_session.close()
        if mutation_task is not None:
            if not mutation_task.done():
                mutation_task.cancel()
            await asyncio.gather(mutation_task, return_exceptions=True)
        await writer_session.rollback()
        await writer_session.close()
        with Session(bind=sync_engine) as cleanup:
            if snapshot_id is not None:
                cleanup.execute(
                    delete(MonthlySnapshot).where(MonthlySnapshot.id == snapshot_id)
                )
            if plaid_item_id is not None:
                cleanup.execute(delete(PlaidItem).where(PlaidItem.id == plaid_item_id))
            cleanup.commit()
        sync_engine.dispose()


def test_preview_rejects_missing_prior_when_older_snapshot_exists(
    database_test_target,
) -> None:
    """The DB-backed preview distinguishes a history gap from first bootstrap."""
    engine = get_sync_engine()
    suffix = uuid4().hex
    checking_id = f"bootstrap-gap-checking-{suffix}"
    plaid_item_id = None

    try:
        with Session(bind=engine) as session:
            plaid_item = PlaidItem(
                user_key="integration",
                item_id=f"bootstrap-gap-item-{suffix}",
                access_token_enc="synthetic",
            )
            session.add(plaid_item)
            session.flush()
            plaid_item_id = plaid_item.id
            session.add(
                Account(
                    plaid_item_id=plaid_item.id,
                    account_id=checking_id,
                    name="Bootstrap Gap Checking",
                    type="depository",
                    subtype="checking",
                    is_excluded=False,
                )
            )
            session.flush()
            session.add_all(
                [
                    MonthlySnapshot(
                        year_month="2097-05",
                        account_id=checking_id,
                        status=SnapshotStatus.CLOSED,
                        starting_balance=Decimal("900.00"),
                        closing_balance=Decimal("1000.00"),
                        closing_balance_frozen=True,
                    ),
                    MonthlySnapshot(
                        year_month="2097-07",
                        account_id=checking_id,
                        status=SnapshotStatus.OPEN,
                        starting_balance=Decimal("1000.00"),
                    ),
                ]
            )
            session.commit()

            preview = build_close_preview(session, "2097-07", checking_id)
            assert preview.has_earlier_snapshot is True
            assert preview.can_close is False
            assert any(
                "missing despite earlier snapshot history" in blocker
                for blocker in preview.blockers
            )
    finally:
        with Session(bind=engine) as cleanup:
            cleanup.execute(
                delete(MonthlySnapshot).where(MonthlySnapshot.account_id == checking_id)
            )
            if plaid_item_id is not None:
                cleanup.execute(delete(PlaidItem).where(PlaidItem.id == plaid_item_id))
            cleanup.commit()
        engine.dispose()
