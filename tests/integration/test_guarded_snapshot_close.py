"""PostgreSQL behavior checks for guarded monthly snapshot closing."""

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
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.models.transaction import Transaction
from budget_me.snapshots.reconciliation_manifest import (
    LineItemDecision,
    LineItemMatch,
    ReconciliationAllocation,
    ReconciliationManifest,
    TransactionDecision,
)
from budget_me.snapshots.service import build_close_preview, close_snapshot
from budget_me.streamlit_app.db import get_starting_balance, get_sync_engine
from tests.integration.snapshot_reconciliation_helpers import (
    delete_reconciliation_receipts,
    seed_reconciliation_receipt,
)

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def _add_successful_ingest(session: Session, plaid_item_id, ended_at: datetime):
    run = IngestRun(
        started_at=ended_at - timedelta(minutes=1),
        ended_at=ended_at,
        run_type=IngestRunType.MANUAL,
        status=IngestRunStatus.COMPLETED,
        items_total=1,
        items_ok=1,
    )
    session.add(run)
    session.flush()
    session.add(
        IngestRunItem(
            ingest_run_id=run.id,
            plaid_item_id=plaid_item_id,
            status=IngestRunItemStatus.SUCCESS,
        )
    )
    return run.id


def test_guarded_close_freezes_actuals_and_seeds_next_month(
    database_test_target,
) -> None:
    """Close one reconciled account atomically with all cached totals."""
    engine = get_sync_engine()
    session = Session(bind=engine)
    now = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
    suffix = uuid4().hex
    plaid_item = PlaidItem(
        user_key="integration",
        item_id=f"guarded-close-item-{suffix}",
        access_token_enc="synthetic",
    )
    checking_id = f"guarded-close-checking-{suffix}"
    ingest_run_id = None
    receipt_snapshot_ids = []

    try:
        session.add(plaid_item)
        session.flush()
        checking = Account(
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            name="Synthetic Checking",
            type="depository",
            subtype="checking",
            is_excluded=False,
        )
        card = Account(
            plaid_item_id=plaid_item.id,
            account_id=f"guarded-close-card-{suffix}",
            name="Synthetic Card",
            type="credit",
            subtype="credit card",
            paying_account_id=checking_id,
            is_excluded=False,
        )
        session.add_all([checking, card])
        session.flush()

        snapshot = MonthlySnapshot(
            year_month="2025-12",
            account_id=checking_id,
            status=SnapshotStatus.OPEN,
            starting_balance=Decimal("1000.00"),
            last_synced_at=now - timedelta(hours=1),
        )
        session.add(snapshot)
        session.flush()
        next_snapshot = MonthlySnapshot(
            year_month="2026-01",
            account_id=checking_id,
            status=SnapshotStatus.OPEN,
            starting_balance=None,
        )
        session.add(next_snapshot)
        income_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type="income",
            name="Synthetic income",
            amount=Decimal("100.00"),
            is_one_time=True,
            skipped=False,
        )
        expense_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type="expense",
            name="Synthetic expense",
            amount=Decimal("50.00"),
            is_one_time=True,
            skipped=False,
        )
        transfer_in_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type="transfer_in",
            name="Synthetic transfer in",
            amount=Decimal("20.00"),
            is_one_time=True,
            skipped=False,
        )
        transfer_out_item = SnapshotLineItem(
            snapshot_id=snapshot.id,
            item_type="transfer_out",
            name="Synthetic transfer out",
            amount=Decimal("10.00"),
            is_one_time=True,
            skipped=False,
        )
        income_transaction = Transaction(
            plaid_transaction_id=f"guarded-close-income-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 5),
            amount=Decimal("-100.00"),
            name="Synthetic payroll deposit",
            pending=False,
            reviewed=True,
            budget_category="salary",
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(hours=2),
        )
        expense_transaction = Transaction(
            plaid_transaction_id=f"guarded-close-expense-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 15),
            amount=Decimal("50.00"),
            name="Synthetic reviewed purchase",
            pending=False,
            reviewed=True,
            budget_category="groceries",
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(hours=2),
        )
        transfer_in_transaction = Transaction(
            plaid_transaction_id=f"guarded-close-transfer-in-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 10),
            amount=Decimal("-20.00"),
            name="Synthetic transfer in",
            pending=False,
            reviewed=True,
            budget_category="transfer",
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(hours=2),
        )
        transfer_out_transaction = Transaction(
            plaid_transaction_id=f"guarded-close-transfer-out-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 11),
            amount=Decimal("10.00"),
            name="Synthetic transfer out",
            pending=False,
            reviewed=True,
            budget_category="transfer",
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(hours=2),
        )
        checking_card_payment = Transaction(
            plaid_transaction_id=f"guarded-close-checking-card-payment-{suffix}",
            plaid_item_id=plaid_item.id,
            account_id=checking_id,
            date=date(2025, 12, 20),
            amount=Decimal("100.00"),
            name="Synthetic checking card payment",
            pending=False,
            reviewed=True,
            budget_category="credit_card_payment",
            created_at=now - timedelta(hours=3),
            updated_at=now - timedelta(hours=2),
        )
        session.add_all(
            [
                income_item,
                expense_item,
                transfer_in_item,
                transfer_out_item,
                SnapshotCreditCard(
                    snapshot_id=snapshot.id,
                    account_id=card.account_id,
                    payment_strategy="pay_in_full",
                    calculated_payment=Decimal("120.00"),
                    actual_payment_amount=Decimal("100.00"),
                    actual_payment_date=date(2025, 12, 20),
                ),
                AccountBalanceSnapshot(
                    account_id=checking_id,
                    snapshot_date=date(2025, 12, 31),
                    balance_current=Decimal("960.00"),
                ),
                income_transaction,
                expense_transaction,
                transfer_in_transaction,
                transfer_out_transaction,
                checking_card_payment,
                Transaction(
                    plaid_transaction_id=f"guarded-close-card-payment-{suffix}",
                    plaid_item_id=plaid_item.id,
                    account_id=card.account_id,
                    date=date(2025, 12, 20),
                    amount=Decimal("-100.00"),
                    name="Synthetic card payment",
                    pending=False,
                    category_detailed="Payment, Credit Card",
                    reviewed=True,
                    budget_category="credit_card_payment",
                    created_at=now - timedelta(hours=3),
                    updated_at=now - timedelta(hours=2),
                ),
            ]
        )
        ingest_run_id = _add_successful_ingest(
            session, plaid_item.id, now - timedelta(hours=2)
        )
        session.flush()
        manifest = ReconciliationManifest(
            version=1,
            year_month="2025-12",
            account_id=checking_id,
            transaction_decisions=[
                TransactionDecision(
                    transaction_id=income_transaction.id,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="income", amount="100.00", category="salary"
                        )
                    ],
                ),
                TransactionDecision(
                    transaction_id=expense_transaction.id,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="expense",
                            amount="50.00",
                            category="groceries",
                        )
                    ],
                ),
                TransactionDecision(
                    transaction_id=transfer_in_transaction.id,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="transfer_in",
                            amount="20.00",
                            category="transfer",
                        )
                    ],
                ),
                TransactionDecision(
                    transaction_id=transfer_out_transaction.id,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="transfer_out",
                            amount="10.00",
                            category="transfer",
                        )
                    ],
                ),
                TransactionDecision(
                    transaction_id=checking_card_payment.id,
                    allocations=[
                        ReconciliationAllocation(
                            flow_type="card_payment",
                            amount="100.00",
                            category="credit_card_payment",
                        )
                    ],
                ),
            ],
            line_item_decisions=[
                LineItemDecision(
                    line_item_id=item.id,
                    resolution="fulfilled",
                    matches=[
                        LineItemMatch(
                            transaction_id=transaction.id,
                            allocation_index=0,
                            amount=amount,
                        )
                    ],
                )
                for item, transaction, amount in (
                    (income_item, income_transaction, "100.00"),
                    (expense_item, expense_transaction, "50.00"),
                    (transfer_in_item, transfer_in_transaction, "20.00"),
                    (transfer_out_item, transfer_out_transaction, "10.00"),
                )
            ],
        )
        session.commit()
        receipt_snapshot_ids.append(snapshot.id)
        applied = seed_reconciliation_receipt(
            session,
            manifest,
            reconciled_at=now - timedelta(hours=1),
        )
        assert applied.totals.net == Decimal("-40.00")

        preview = build_close_preview(session, "2025-12", checking_id, now=now)
        assert preview.can_close is True
        assert preview.totals.net == Decimal("-40.00")
        assert preview.closing_balance_to_freeze == Decimal("960.00")
        assert preview.next_snapshot_id == str(next_snapshot.id)
        assert preview.next_starting_balance is None
        session.rollback()

        closed = close_snapshot(
            session,
            "2025-12",
            checking_id,
            confirm_month="2025-12",
            audit_hash=preview.audit_hash,
            now=now,
        )
        session.commit()

        persisted = session.get(MonthlySnapshot, snapshot.id)
        assert persisted is not None
        assert persisted.status == SnapshotStatus.CLOSED
        assert persisted.income_total == Decimal("100.00")
        assert persisted.expense_total == Decimal("50.00")
        assert persisted.transfer_in_total == Decimal("20.00")
        assert persisted.transfer_out_total == Decimal("10.00")
        assert persisted.credit_card_total == Decimal("100.00")
        assert persisted.net == Decimal("-40.00")
        assert persisted.closing_balance == Decimal("960.00")
        assert persisted.closing_balance_frozen is True
        assert closed.audit_hash == preview.audit_hash
        assert closed.next_starting_balance == Decimal("960.00")

        persisted_next = session.get(MonthlySnapshot, next_snapshot.id)
        assert persisted_next is not None
        assert persisted_next.starting_balance == Decimal("960.00")
        next_start, is_frozen = get_starting_balance(session, checking_id, "2026-01")
        assert next_start == Decimal("960.00")
        assert is_frozen is True
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


def test_guarded_close_loads_and_locks_frozen_prior(
    database_test_target,
) -> None:
    """The PostgreSQL close path revalidates one authoritative prior rollover."""
    engine = get_sync_engine()
    session = Session(bind=engine)
    now = datetime(2026, 8, 1, 12, 0, tzinfo=UTC)
    suffix = uuid4().hex
    plaid_item = PlaidItem(
        user_key="integration",
        item_id=f"prior-close-item-{suffix}",
        access_token_enc="synthetic",
    )
    checking_id = f"prior-close-checking-{suffix}"
    ingest_run_id = None
    receipt_snapshot_ids = []

    try:
        session.add(plaid_item)
        session.flush()
        session.add(
            Account(
                plaid_item_id=plaid_item.id,
                account_id=checking_id,
                name="Prior Provenance Checking",
                type="depository",
                subtype="checking",
                is_excluded=False,
            )
        )
        session.flush()
        prior = MonthlySnapshot(
            year_month="2026-06",
            account_id=checking_id,
            status=SnapshotStatus.CLOSED,
            starting_balance=Decimal("900.00"),
            closing_balance=Decimal("1000.00"),
            closing_balance_frozen=True,
            closed_at=now - timedelta(days=31),
        )
        current = MonthlySnapshot(
            year_month="2026-07",
            account_id=checking_id,
            status=SnapshotStatus.OPEN,
            starting_balance=None,
            last_synced_at=now - timedelta(hours=1),
        )
        session.add_all(
            [
                prior,
                current,
                AccountBalanceSnapshot(
                    account_id=checking_id,
                    snapshot_date=date(2026, 7, 31),
                    balance_current=Decimal("1000.00"),
                ),
            ]
        )
        ingest_run_id = _add_successful_ingest(
            session, plaid_item.id, now - timedelta(hours=2)
        )
        session.commit()
        receipt_snapshot_ids.append(current.id)
        seed_reconciliation_receipt(
            session,
            ReconciliationManifest(
                version=1,
                year_month="2026-07",
                account_id=checking_id,
                transaction_decisions=[],
                line_item_decisions=[],
            ),
            reconciled_at=now - timedelta(hours=1),
        )

        preview = build_close_preview(session, "2026-07", checking_id, now=now)
        assert preview.can_close is True
        assert preview.starting_balance == Decimal("1000.00")
        assert preview.starting_balance_provenance == "prior_frozen_close"
        assert preview.prior_snapshot_id == str(prior.id)
        assert preview.prior_snapshot_status == SnapshotStatus.CLOSED.value
        assert preview.prior_direct_starting_balance == Decimal("900.00")
        assert preview.prior_closing_balance == Decimal("1000.00")
        assert preview.prior_closing_balance_frozen is True
        session.rollback()

        closed = close_snapshot(
            session,
            "2026-07",
            checking_id,
            confirm_month="2026-07",
            audit_hash=preview.audit_hash,
            now=now,
        )
        session.commit()

        persisted = session.get(MonthlySnapshot, current.id)
        assert persisted is not None
        assert persisted.status == SnapshotStatus.CLOSED
        assert persisted.closing_balance == Decimal("1000.00")
        assert closed.starting_balance_provenance == "prior_frozen_close"
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
