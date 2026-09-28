"""PostgreSQL proof for immutable reconciliation followed by guarded close."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import delete
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
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.transaction import Transaction
from budget_me.snapshots.reconciliation import (
    apply_reconciliation,
    build_reconciliation_preview,
    validate_current_reconciliation,
)
from budget_me.snapshots.reconciliation_manifest import (
    LineItemDecision,
    LineItemMatch,
    ReconciliationAllocation,
    ReconciliationManifest,
    TransactionDecision,
)
from budget_me.snapshots.service import build_close_preview, close_snapshot
from budget_me.streamlit_app.db import get_sync_engine
from tests.integration.snapshot_reconciliation_helpers import (
    delete_reconciliation_receipts,
)

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def test_reconciliation_receipt_is_required_and_allows_exact_close(
    database_test_target,
) -> None:
    """A complete manifest becomes the sole actual-total authority for close."""
    engine = get_sync_engine()
    session = Session(bind=engine)
    suffix = uuid4().hex
    checking_id = f"receipt-checking-{suffix}"
    plaid_item = PlaidItem(
        user_key="integration",
        item_id=f"receipt-item-{suffix}",
        access_token_enc="synthetic",
    )
    reconciliation_time = datetime(2026, 1, 1, 11, 0, tzinfo=UTC)
    close_time = reconciliation_time + timedelta(hours=1)
    ingest_run_id = None
    receipt_snapshot_ids = []

    try:
        session.add(plaid_item)
        session.flush()
        session.add(
            Account(
                plaid_item_id=plaid_item.id,
                account_id=checking_id,
                name="Synthetic Checking",
                type="depository",
                subtype="checking",
                is_excluded=False,
            )
        )
        session.flush()
        snapshot = MonthlySnapshot(
            year_month="2025-12",
            account_id=checking_id,
            status=SnapshotStatus.OPEN,
            starting_balance=Decimal("1000.00"),
            last_synced_at=None,
        )
        session.add(snapshot)
        session.flush()
        receipt_snapshot_ids.append(snapshot.id)
        line_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type="expense",
            name="Synthetic planned expense",
            amount=Decimal("50.00"),
            category="groceries",
            is_one_time=True,
            skipped=False,
        )
        transaction = Transaction(
            plaid_transaction_id=f"receipt-transaction-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 15),
            amount=Decimal("50.00"),
            name="Synthetic reviewed purchase",
            pending=False,
            reviewed=True,
            budget_category="groceries",
            created_at=reconciliation_time - timedelta(hours=3),
            updated_at=reconciliation_time - timedelta(hours=2),
        )
        run = IngestRun(
            started_at=reconciliation_time - timedelta(hours=3),
            ended_at=reconciliation_time - timedelta(hours=2),
            run_type=IngestRunType.MANUAL,
            status=IngestRunStatus.COMPLETED,
            items_total=1,
            items_ok=1,
        )
        session.add_all(
            [
                line_item,
                transaction,
                run,
                AccountBalanceSnapshot(
                    account_id=checking_id,
                    snapshot_date=date(2025, 12, 31),
                    balance_current=Decimal("950.00"),
                ),
            ]
        )
        session.flush()
        ingest_run_id = run.id
        session.add(
            IngestRunItem(
                ingest_run_id=run.id,
                plaid_item_id=plaid_item.id,
                status=IngestRunItemStatus.SUCCESS,
            )
        )
        session.commit()

        blocked = build_close_preview(session, "2025-12", checking_id, now=close_time)
        assert blocked.can_close is False
        assert any(
            "immutable reconciliation receipt" in value for value in blocked.blockers
        )
        session.rollback()

        manifest = ReconciliationManifest(
            version=1,
            year_month="2025-12",
            account_id=checking_id,
            transaction_decisions=[
                TransactionDecision(
                    transaction_id=transaction.id,
                    manual_locked=True,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="expense",
                            amount="50.00",
                            category="groceries",
                        )
                    ],
                )
            ],
            line_item_decisions=[
                LineItemDecision(
                    line_item_id=line_item.id,
                    resolution="fulfilled",
                    remaining_amount="0.00",
                    matches=[
                        LineItemMatch(
                            transaction_id=transaction.id,
                            allocation_index=0,
                            amount="50.00",
                        )
                    ],
                )
            ],
        )
        preview = build_reconciliation_preview(session, manifest)
        assert preview.can_apply is True
        assert preview.totals.net == Decimal("-50.00")
        session.rollback()

        applied = apply_reconciliation(
            session,
            manifest,
            confirm_month="2025-12",
            input_hash=preview.input_hash,
            now=reconciliation_time,
        )
        session.commit()
        assert applied.current_run_id is not None

        evidence = validate_current_reconciliation(session, "2025-12", checking_id)
        assert evidence.is_valid is True
        assert evidence.totals is not None
        assert evidence.totals.expense_total == Decimal("50.00")
        session.rollback()

        close_preview = build_close_preview(
            session, "2025-12", checking_id, now=close_time
        )
        assert close_preview.can_close is True
        assert close_preview.totals.net == Decimal("-50.00")
        assert close_preview.projected_closing_balance == Decimal("950.00")
        session.rollback()

        closed = close_snapshot(
            session,
            "2025-12",
            checking_id,
            confirm_month="2025-12",
            audit_hash=close_preview.audit_hash,
            now=close_time,
        )
        session.commit()
        assert closed.status == SnapshotStatus.CLOSED.value
        assert closed.reconciliation_evidence is not None
        assert closed.reconciliation_evidence.is_valid is True
    finally:
        session.rollback()
        delete_reconciliation_receipts(session, receipt_snapshot_ids)
        session.execute(
            delete(MonthlySnapshot).where(MonthlySnapshot.account_id == checking_id)
        )
        session.execute(
            delete(AccountBalanceSnapshot).where(
                AccountBalanceSnapshot.account_id == checking_id
            )
        )
        if ingest_run_id is not None:
            session.execute(delete(IngestRun).where(IngestRun.id == ingest_run_id))
        if plaid_item.id is not None:
            session.execute(delete(PlaidItem).where(PlaidItem.id == plaid_item.id))
        session.commit()
        session.close()
        engine.dispose()
