"""PostgreSQL regressions for Plaid mutation and snapshot-close freshness."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

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
from budget_me.db.repos.transactions import TransactionsRepo
from budget_me.snapshots.reconciliation_manifest import (
    ReconciliationAllocation,
    ReconciliationManifest,
    TransactionDecision,
)
from budget_me.snapshots.service import build_close_preview
from budget_me.streamlit_app.db import get_sync_engine
from tests.integration.snapshot_reconciliation_helpers import (
    delete_reconciliation_receipts,
    seed_reconciliation_receipt,
)

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def _provider_values(plaid_item_id, transaction_id: str) -> dict:
    return {
        "plaid_transaction_id": transaction_id,
        "plaid_item_id": plaid_item_id,
        "account_id": "freshness-checking",
        "date": date(2026, 7, 15),
        "amount": Decimal("20.00"),
        "name": "Updated provider transaction",
        "raw": {},
    }


@pytest.mark.asyncio
async def test_every_provider_upsert_advances_updated_at(db_session) -> None:
    """All three Core upserts advance the persisted PostgreSQL timestamp."""
    session, _ = db_session
    plaid_item = PlaidItem(
        user_key="integration",
        item_id=f"upsert-freshness-{uuid4().hex}",
        access_token_enc="synthetic",
    )
    session.add(plaid_item)
    await session.flush()
    repo = TransactionsRepo(session)
    old_timestamp = datetime(2000, 1, 1, tzinfo=UTC)

    for index, method_name in enumerate(
        ("upsert", "bulk_upsert", "bulk_upsert_with_details")
    ):
        transaction_id = f"upsert-freshness-{method_name}-{uuid4().hex}"
        transaction = Transaction(
            plaid_transaction_id=transaction_id,
            plaid_item_id=plaid_item.id,
            account_id="freshness-checking",
            date=date(2026, 7, 15),
            amount=Decimal("10.00") + index,
            name="Original provider transaction",
            raw={},
            created_at=old_timestamp,
            updated_at=old_timestamp,
        )
        session.add(transaction)
        await session.flush()
        values = _provider_values(plaid_item.id, transaction_id)

        if method_name == "upsert":
            await repo.upsert(
                values["plaid_transaction_id"],
                values["plaid_item_id"],
                values["account_id"],
                values["date"],
                values["amount"],
                values["name"],
                raw=values["raw"],
            )
        elif method_name == "bulk_upsert":
            await repo.bulk_upsert([values])
        else:
            await repo.bulk_upsert_with_details([values])

        persisted_timestamp = (
            await session.execute(
                select(Transaction.updated_at).where(
                    Transaction.plaid_transaction_id == transaction_id
                )
            )
        ).scalar_one()
        assert persisted_timestamp > old_timestamp


def test_ingest_audit_catches_running_sync_and_hard_deleted_transaction(
    database_test_target,
) -> None:
    """A Plaid removal remains stale through its ingest run after the row is gone."""
    engine = get_sync_engine()
    session = Session(bind=engine)
    suffix = uuid4().hex
    account_id = f"ingest-freshness-checking-{suffix}"
    reconciled_at = datetime(2100, 1, 1, 12, 0, tzinfo=UTC)
    run_ids = []
    receipt_snapshot_ids = []
    plaid_item = PlaidItem(
        user_key="integration",
        item_id=f"ingest-freshness-item-{suffix}",
        access_token_enc="synthetic",
    )

    try:
        session.add(plaid_item)
        session.flush()
        session.add(
            Account(
                plaid_item_id=plaid_item.id,
                account_id=account_id,
                name="Synthetic Freshness Checking",
                type="depository",
                subtype="checking",
                is_excluded=False,
            )
        )
        session.flush()
        snapshot = MonthlySnapshot(
            year_month="2099-12",
            account_id=account_id,
            status=SnapshotStatus.OPEN,
            starting_balance=Decimal("100.00"),
            last_synced_at=reconciled_at,
        )
        transaction = Transaction(
            plaid_transaction_id=f"hard-delete-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=account_id,
            date=date(2099, 12, 15),
            amount=Decimal("5.00"),
            name="Synthetic reviewed transaction",
            pending=False,
            reviewed=True,
            budget_category="groceries",
            created_at=reconciled_at - timedelta(hours=2),
            updated_at=reconciled_at - timedelta(hours=1),
        )
        running = IngestRun(
            started_at=reconciled_at - timedelta(hours=3),
            run_type=IngestRunType.MANUAL,
            status=IngestRunStatus.RUNNING,
            items_total=1,
        )
        latest_before_review = IngestRun(
            started_at=reconciled_at - timedelta(hours=2),
            ended_at=reconciled_at - timedelta(hours=1, minutes=59),
            run_type=IngestRunType.MANUAL,
            status=IngestRunStatus.COMPLETED,
            items_total=1,
            items_ok=1,
        )
        session.add_all(
            [
                snapshot,
                transaction,
                running,
                latest_before_review,
                AccountBalanceSnapshot(
                    account_id=account_id,
                    snapshot_date=date(2099, 12, 31),
                    balance_current=Decimal("100.00"),
                ),
            ]
        )
        session.flush()
        running_item = IngestRunItem(
            ingest_run_id=running.id,
            plaid_item_id=plaid_item.id,
            status=IngestRunItemStatus.PENDING,
        )
        session.add_all(
            [
                running_item,
                IngestRunItem(
                    ingest_run_id=latest_before_review.id,
                    plaid_item_id=plaid_item.id,
                    status=IngestRunItemStatus.SUCCESS,
                ),
            ]
        )
        session.commit()
        run_ids.extend([running.id, latest_before_review.id])
        receipt_snapshot_ids.append(snapshot.id)
        seed_reconciliation_receipt(
            session,
            ReconciliationManifest(
                version=1,
                year_month="2099-12",
                account_id=account_id,
                transaction_decisions=[
                    TransactionDecision(
                        transaction_id=transaction.id,
                        allocations=[
                            ReconciliationAllocation(
                                flow_type="expense",
                                amount="5.00",
                                category="groceries",
                            )
                        ],
                    )
                ],
                line_item_decisions=[],
            ),
            reconciled_at=reconciled_at,
        )

        in_flight = build_close_preview(
            session,
            "2099-12",
            account_id,
            now=reconciled_at + timedelta(minutes=5),
        )
        assert any("running or pending" in item for item in in_flight.blockers)

        running.status = IngestRunStatus.COMPLETED
        running.ended_at = reconciled_at - timedelta(minutes=30)
        running.items_ok = 1
        running_item.status = IngestRunItemStatus.SUCCESS
        session.commit()
        baseline = build_close_preview(
            session,
            "2099-12",
            account_id,
            now=reconciled_at + timedelta(minutes=5),
        )
        assert not any("ingest" in item.lower() for item in baseline.blockers)

        session.execute(delete(Transaction).where(Transaction.id == transaction.id))
        removal_run = IngestRun(
            started_at=reconciled_at + timedelta(minutes=1),
            ended_at=reconciled_at + timedelta(minutes=2),
            run_type=IngestRunType.MANUAL,
            status=IngestRunStatus.COMPLETED,
            items_total=1,
            items_ok=1,
            tx_removed=1,
        )
        session.add(removal_run)
        session.flush()
        session.add(
            IngestRunItem(
                ingest_run_id=removal_run.id,
                plaid_item_id=plaid_item.id,
                status=IngestRunItemStatus.SUCCESS,
                tx_removed=1,
            )
        )
        session.commit()
        run_ids.append(removal_run.id)

        after_removal = build_close_preview(
            session,
            "2099-12",
            account_id,
            now=reconciled_at + timedelta(minutes=5),
        )
        assert any("completed after" in item for item in after_removal.blockers)
        assert after_removal.audit_hash != baseline.audit_hash
    finally:
        session.rollback()
        delete_reconciliation_receipts(session, receipt_snapshot_ids)
        if run_ids:
            session.execute(delete(IngestRun).where(IngestRun.id.in_(run_ids)))
        session.execute(
            delete(MonthlySnapshot).where(MonthlySnapshot.account_id == account_id)
        )
        session.execute(
            delete(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == account_id
            )
        )
        if plaid_item.id is not None:
            session.execute(delete(PlaidItem).where(PlaidItem.id == plaid_item.id))
        session.commit()
        session.close()
        engine.dispose()
