"""Provider-free PostgreSQL checks for Plaid sync/close coordination."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from threading import Event
from uuid import uuid4

import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from budget_me.db.engine import get_async_session
from budget_me.db.models.account import Account
from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.models.ingest_run import (
    IngestRun,
    IngestRunItem,
    IngestRunItemStatus,
    IngestRunStatus,
    IngestRunType,
)
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.plaid_item import PlaidItem
from budget_me.db.models.transaction import Transaction
from budget_me.db.sync_coordination import (
    acquire_close_coordination_lock,
    hold_sync_item_coordination,
)
from budget_me.plaid import historical_transactions
from budget_me.snapshots.reconciliation_manifest import ReconciliationManifest
from budget_me.snapshots.service import (
    _load_plaid_item_sync_evidence,
    build_close_preview,
    close_snapshot,
)
from budget_me.streamlit_app.db import get_sync_engine
from tests.integration.snapshot_reconciliation_helpers import (
    delete_reconciliation_receipts,
    seed_reconciliation_receipt,
)

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def _new_plaid_item(session: Session, suffix: str) -> PlaidItem:
    item = PlaidItem(
        user_key="coordination-test",
        item_id=f"coordination-item-{suffix}",
        access_token_enc="synthetic",
    )
    session.add(item)
    session.commit()
    return item


def test_admitted_sync_publishes_pending_before_close_reads() -> None:
    """Sync-first close waits, then gets a fresh view of PENDING evidence."""
    engine = get_sync_engine()
    setup_session = Session(bind=engine, expire_on_commit=False)
    item = _new_plaid_item(setup_session, uuid4().hex)
    run_id = uuid4()
    run_item_id = uuid4()
    sync_session = Session(bind=engine)
    close_attempted = Event()
    close_acquired = Event()

    try:
        sync_session.execute(text("LOCK TABLE plaid_items IN ROW EXCLUSIVE MODE"))
        sync_session.add(
            IngestRun(
                id=run_id,
                started_at=datetime.now(UTC),
                run_type=IngestRunType.MANUAL,
                status=IngestRunStatus.RUNNING,
                items_total=1,
            )
        )
        sync_session.add(
            IngestRunItem(
                id=run_item_id,
                ingest_run_id=run_id,
                plaid_item_id=item.id,
                status=IngestRunItemStatus.PENDING,
            )
        )
        sync_session.flush()

        def close_after_barrier() -> IngestRunItemStatus:
            with Session(bind=engine) as close_session:
                close_session.execute(
                    text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE")
                )
                close_session.execute(text("SET LOCAL lock_timeout = '2s'"))
                close_attempted.set()
                acquire_close_coordination_lock(close_session)
                close_acquired.set()
                return close_session.execute(
                    select(IngestRunItem.status).where(IngestRunItem.id == run_item_id)
                ).scalar_one()

        with ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(close_after_barrier)
            assert close_attempted.wait(timeout=1)
            assert not close_acquired.wait(timeout=0.2)
            sync_session.commit()
            assert future.result(timeout=5) == IngestRunItemStatus.PENDING
            assert close_acquired.is_set()
    finally:
        sync_session.rollback()
        sync_session.close()
        with Session(bind=engine) as cleanup_session:
            cleanup_session.execute(delete(IngestRun).where(IngestRun.id == run_id))
            cleanup_session.execute(delete(PlaidItem).where(PlaidItem.id == item.id))
            cleanup_session.commit()
        setup_session.close()
        engine.dispose()


@pytest.mark.asyncio
async def test_close_first_prevents_public_item_sync_admission() -> None:
    """Close-first holds direct item synchronization out through commit."""
    engine = get_sync_engine()
    close_session = Session(bind=engine)
    attempted = asyncio.Event()
    admitted = asyncio.Event()

    async def attempt_sync_admission() -> None:
        attempted.set()
        async with hold_sync_item_coordination():
            admitted.set()

    task = None
    try:
        close_session.execute(text("SET TRANSACTION ISOLATION LEVEL SERIALIZABLE"))
        acquire_close_coordination_lock(close_session)
        task = asyncio.create_task(attempt_sync_admission())
        await asyncio.wait_for(attempted.wait(), timeout=1)
        await asyncio.sleep(0.2)
        assert not admitted.is_set()

        close_session.commit()
        await asyncio.wait_for(task, timeout=5)
        assert admitted.is_set()
    finally:
        close_session.rollback()
        close_session.close()
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
        engine.dispose()


@pytest.mark.asyncio
async def test_historical_backfill_blocks_close_until_committed_change_is_visible(
    monkeypatch,
) -> None:
    """Close waits for backfill, then rejects its post-reconciliation write."""
    engine = get_sync_engine()
    session = Session(bind=engine, expire_on_commit=False)
    suffix = uuid4().hex
    item = _new_plaid_item(session, suffix)
    account_id = f"backfill-close-checking-{suffix}"
    year_month = "2097-12"
    reconciled_at = datetime(2098, 1, 1, 12, 0, tzinfo=UTC)
    close_now = reconciled_at + timedelta(minutes=5)
    run = IngestRun(
        started_at=reconciled_at - timedelta(hours=2),
        ended_at=reconciled_at - timedelta(hours=1),
        run_type=IngestRunType.MANUAL,
        status=IngestRunStatus.COMPLETED,
        items_total=1,
        items_ok=1,
    )
    backfill_entered = asyncio.Event()
    allow_backfill_commit = asyncio.Event()
    close_attempted = Event()
    backfill_task = None
    close_future = None
    receipt_snapshot_ids = []

    try:
        session.add_all(
            [
                Account(
                    plaid_item_id=item.id,
                    account_id=account_id,
                    name="Synthetic Backfill Checking",
                    type="depository",
                    subtype="checking",
                    is_excluded=False,
                ),
                MonthlySnapshot(
                    year_month=year_month,
                    account_id=account_id,
                    status=SnapshotStatus.OPEN,
                    starting_balance=Decimal("100.00"),
                    last_synced_at=reconciled_at,
                ),
                AccountBalanceSnapshot(
                    account_id=account_id,
                    snapshot_date=date(2097, 12, 31),
                    balance_current=Decimal("100.00"),
                ),
                run,
            ]
        )
        session.flush()
        session.add(
            IngestRunItem(
                ingest_run_id=run.id,
                plaid_item_id=item.id,
                status=IngestRunItemStatus.SUCCESS,
            )
        )
        session.commit()
        snapshot_id = session.execute(
            select(MonthlySnapshot.id).where(
                MonthlySnapshot.year_month == year_month,
                MonthlySnapshot.account_id == account_id,
            )
        ).scalar_one()
        receipt_snapshot_ids.append(snapshot_id)
        seed_reconciliation_receipt(
            session,
            ReconciliationManifest(
                version=1,
                year_month=year_month,
                account_id=account_id,
                transaction_decisions=[],
                line_item_decisions=[],
            ),
            reconciled_at=reconciled_at,
        )

        baseline = build_close_preview(
            session,
            year_month,
            account_id,
            now=close_now,
        )
        assert baseline.can_close is True
        session.rollback()

        async def commit_synthetic_backfill(*args, **kwargs):
            backfill_entered.set()
            await allow_backfill_commit.wait()
            async with get_async_session() as write_session:
                write_session.add(
                    Transaction(
                        plaid_transaction_id=f"backfill-close-txn-{suffix}",
                        plaid_item_id=item.id,
                        account_id=account_id,
                        date=date(2097, 12, 15),
                        amount=Decimal("5.00"),
                        name="Synthetic post-reconciliation backfill",
                        pending=False,
                        reviewed=True,
                        budget_category="groceries",
                        created_at=reconciled_at + timedelta(minutes=1),
                        updated_at=reconciled_at + timedelta(minutes=1),
                    )
                )
            return historical_transactions.HistoricalFetchResult(
                transactions_fetched=1,
                transactions_added=1,
                transactions_updated=0,
                oldest_date=date(2097, 12, 15),
                newest_date=date(2097, 12, 15),
            )

        monkeypatch.setattr(
            historical_transactions,
            "_fetch_historical_transactions_under_coordination",
            commit_synthetic_backfill,
        )

        backfill_task = asyncio.create_task(
            historical_transactions.fetch_historical_transactions(item.id)
        )
        await asyncio.wait_for(backfill_entered.wait(), timeout=1)

        def attempt_close() -> Exception | None:
            close_attempted.set()
            with Session(bind=engine) as close_session:
                try:
                    close_snapshot(
                        close_session,
                        year_month,
                        account_id,
                        confirm_month=year_month,
                        audit_hash=baseline.audit_hash,
                        now=close_now,
                    )
                    close_session.commit()
                except Exception as exc:
                    close_session.rollback()
                    return exc
            return None

        with ThreadPoolExecutor(max_workers=1) as executor:
            close_future = executor.submit(attempt_close)
            assert close_attempted.wait(timeout=1)
            await asyncio.sleep(0.2)
            assert not close_future.done()

            allow_backfill_commit.set()
            await asyncio.wait_for(backfill_task, timeout=5)
            close_error = await asyncio.wait_for(
                asyncio.wrap_future(close_future), timeout=5
            )

        assert isinstance(close_error, ValueError)
        assert "Audit hash mismatch" in str(close_error)
        session.rollback()
        after_backfill = build_close_preview(
            session,
            year_month,
            account_id,
            now=close_now,
        )
        assert after_backfill.audit_hash != baseline.audit_hash
        assert any(
            "Transactions changed after" in blocker
            for blocker in after_backfill.blockers
        )
        assert (
            session.execute(
                select(MonthlySnapshot.status).where(
                    MonthlySnapshot.year_month == year_month,
                    MonthlySnapshot.account_id == account_id,
                )
            ).scalar_one()
            == SnapshotStatus.OPEN
        )
    finally:
        allow_backfill_commit.set()
        if backfill_task is not None and not backfill_task.done():
            await asyncio.gather(backfill_task, return_exceptions=True)
        if close_future is not None and not close_future.done():
            await asyncio.wait_for(asyncio.wrap_future(close_future), timeout=5)
        session.rollback()
        delete_reconciliation_receipts(session, receipt_snapshot_ids)
        session.execute(
            delete(IngestRunItem).where(IngestRunItem.ingest_run_id == run.id)
        )
        session.execute(delete(IngestRun).where(IngestRun.id == run.id))
        session.execute(
            delete(MonthlySnapshot).where(
                MonthlySnapshot.year_month == year_month,
                MonthlySnapshot.account_id == account_id,
            )
        )
        session.execute(
            delete(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id
            )
        )
        session.execute(delete(Transaction).where(Transaction.account_id == account_id))
        session.execute(delete(PlaidItem).where(PlaidItem.id == item.id))
        session.commit()
        session.close()
        engine.dispose()


def test_sync_evidence_uses_last_terminal_completion_in_postgresql() -> None:
    """A late older-started failure remains visible after overlapping success."""
    engine = get_sync_engine()
    session = Session(bind=engine, expire_on_commit=False)
    item = _new_plaid_item(session, uuid4().hex)
    now = datetime.now(UTC)
    older_started_failure = IngestRun(
        started_at=now - timedelta(hours=4),
        ended_at=now - timedelta(minutes=30),
        run_type=IngestRunType.MANUAL,
        status=IngestRunStatus.FAILED,
        items_total=1,
        items_failed=1,
    )
    newer_started_success = IngestRun(
        started_at=now - timedelta(hours=3),
        ended_at=now - timedelta(hours=2),
        run_type=IngestRunType.MANUAL,
        status=IngestRunStatus.COMPLETED,
        items_total=1,
        items_ok=1,
    )
    run_ids = ()

    try:
        session.add_all([older_started_failure, newer_started_success])
        session.flush()
        run_ids = (older_started_failure.id, newer_started_success.id)
        session.add_all(
            [
                IngestRunItem(
                    ingest_run_id=older_started_failure.id,
                    plaid_item_id=item.id,
                    status=IngestRunItemStatus.FAILED,
                ),
                IngestRunItem(
                    ingest_run_id=newer_started_success.id,
                    plaid_item_id=item.id,
                    status=IngestRunItemStatus.SUCCESS,
                ),
            ]
        )
        session.commit()

        latest, active = _load_plaid_item_sync_evidence(session, [item.id])

        assert active == ()
        assert len(latest) == 1
        assert latest[0].ingest_run_id == str(older_started_failure.id)
        assert latest[0].item_status == IngestRunItemStatus.FAILED.value
        assert latest[0].ended_at == older_started_failure.ended_at
    finally:
        session.rollback()
        if run_ids:
            session.execute(delete(IngestRun).where(IngestRun.id.in_(run_ids)))
        session.execute(delete(PlaidItem).where(PlaidItem.id == item.id))
        session.commit()
        session.close()
        engine.dispose()
