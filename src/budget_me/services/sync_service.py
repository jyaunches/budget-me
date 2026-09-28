"""Sync service with IngestRun tracking for transaction synchronization."""

import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from decimal import Decimal

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.models.ingest_run import (
    IngestRunItemStatus,
    IngestRunStatus,
    IngestRunType,
)
from budget_me.db.repos.ingest_runs import IngestRunsRepo
from budget_me.db.repos.items import ItemsRepo
from budget_me.db.sync_coordination import acquire_sync_admission_lock
from budget_me.plaid.errors import PlaidError
from budget_me.plaid.liabilities_sync import sync_liabilities
from budget_me.plaid.transactions_sync import (
    ItemSyncResult as EngineSyncResult,
)
from budget_me.plaid.transactions_sync import (
    sync_item,
)

# Maximum transactions to include per category per item
MAX_TRANSACTIONS_PER_CATEGORY = 100


@dataclass
class TransactionDetail:
    """Minimal transaction detail for added transactions."""

    id: uuid.UUID
    plaid_transaction_id: str
    date: date
    amount: Decimal
    name: str
    account_id: str


@dataclass
class ModifiedTransactionDetail:
    """Transaction detail with change tracking for modified transactions."""

    id: uuid.UUID
    plaid_transaction_id: str
    date: date
    amount: Decimal
    name: str
    account_id: str
    changes: list[str] = field(default_factory=list)


@dataclass
class TransactionDetails:
    """Container for transaction details during sync."""

    added: list[TransactionDetail] = field(default_factory=list)
    modified: list[ModifiedTransactionDetail] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # plaid_transaction_ids


@dataclass
class SyncItemResult:
    """Result of syncing a single PlaidItem."""

    item_id: uuid.UUID
    institution_id: str | None
    institution_name: str | None
    success: bool
    added: int = 0
    modified: int = 0
    removed: int = 0
    duration_ms: int = 0
    error_code: str | None = None
    error_message: str | None = None
    transactions: TransactionDetails | None = None


@dataclass
class SyncRunResult:
    """Result of a complete sync run."""

    run_id: uuid.UUID
    status: IngestRunStatus
    items_total: int
    items_ok: int
    items_failed: int
    tx_added: int
    tx_modified: int
    tx_removed: int
    item_results: list[SyncItemResult]
    started_at: datetime
    ended_at: datetime | None = None
    duration_ms: int = 0
    error_summary: str | None = None


class SyncService:
    """
    Orchestrates transaction synchronization with IngestRun tracking.

    This service wraps the sync engine to provide:
    - IngestRun lifecycle management (create, complete)
    - Per-item tracking via IngestRunItem
    - Timing and count aggregation
    - Error handling and status determination
    """

    def __init__(self, session: AsyncSession):
        """
        Initialize the SyncService.

        Args:
            session: AsyncSession for database operations.
        """
        self.session = session
        self.ingest_runs_repo = IngestRunsRepo(session)
        self.items_repo = ItemsRepo(session)

    async def run_sync(
        self,
        run_type: IngestRunType = IngestRunType.MANUAL,
        item_id: uuid.UUID | None = None,
        include_transactions: bool = False,
    ) -> SyncRunResult:
        """
        Run a complete sync operation with IngestRun tracking.

        Args:
            run_type: Type of sync run (scheduled, manual, webhook).
            item_id: Optional specific item to sync. If None, syncs all active items.
            include_transactions: If True, include transaction details in results.

        Returns:
            SyncRunResult with counts, status, and per-item results.
        """
        run_start = time.monotonic()
        started_at = datetime.now(UTC)

        # Get items to sync
        if item_id:
            item = await self.items_repo.get_by_id(item_id)
            items = [item] if item else []
        else:
            items = await self.items_repo.find_active()

        # Serialize sync admission with guarded snapshot close before publishing
        # any lifecycle evidence. This lock and the RUNNING/PENDING rows are
        # committed together, so close either wins first or observes the full
        # relevant in-flight scope.
        await acquire_sync_admission_lock(self.session)

        # Create IngestRun
        ingest_run = await self.ingest_runs_repo.create_run(
            run_type=run_type,
            items_total=len(items),
        )

        logger.info(
            "Starting sync run",
            run_type=run_type.value,
            items_total=len(items),
        )

        # Track results
        item_results: list[SyncItemResult] = []
        items_ok = 0
        items_failed = 0
        total_added = 0
        total_modified = 0
        total_removed = 0
        error_messages: list[str] = []

        # Make the complete scope of this run visible before provider work starts.
        # Guarded snapshot close uses these PENDING rows to distinguish relevant
        # in-flight activity from unrelated item syncs.
        run_items_by_plaid_item_id = {}
        for item in items:
            run_item = await self.ingest_runs_repo.add_run_item(
                ingest_run_id=ingest_run.id,
                plaid_item_id=item.id,
            )
            run_items_by_plaid_item_id[item.id] = run_item
        # Publish the RUNNING header and its complete PENDING item scope atomically.
        # The unconditional commit also makes zero-item runs visible before they
        # are finalized below.
        await self.session.commit()

        # Process each item
        for item in items:
            run_item = run_items_by_plaid_item_id[item.id]

            item_start = time.monotonic()
            item_result = SyncItemResult(
                item_id=item.id,
                institution_id=item.institution_id,
                institution_name=item.institution_name,
                success=False,
            )

            try:
                # Sync the item
                result: EngineSyncResult = await sync_item(
                    item.id, include_transactions=include_transactions
                )

                item_result.success = True
                item_result.added = result.added
                item_result.modified = result.modified
                item_result.removed = result.removed
                items_ok += 1

                # Convert transaction details if present
                if result.transaction_details:
                    item_result.transactions = TransactionDetails(
                        added=[
                            TransactionDetail(
                                id=t.id,
                                plaid_transaction_id=t.plaid_transaction_id,
                                date=t.date,
                                amount=t.amount,
                                name=t.name,
                                account_id=t.account_id,
                            )
                            for t in result.transaction_details.added[
                                :MAX_TRANSACTIONS_PER_CATEGORY
                            ]
                        ],
                        modified=[
                            ModifiedTransactionDetail(
                                id=t.id,
                                plaid_transaction_id=t.plaid_transaction_id,
                                date=t.date,
                                amount=t.amount,
                                name=t.name,
                                account_id=t.account_id,
                                changes=t.changes,
                            )
                            for t in result.transaction_details.modified[
                                :MAX_TRANSACTIONS_PER_CATEGORY
                            ]
                        ],
                        removed=result.transaction_details.removed[
                            :MAX_TRANSACTIONS_PER_CATEGORY
                        ],
                    )

                # Aggregate totals
                total_added += result.added
                total_modified += result.modified
                total_removed += result.removed

                # Complete the run item as success
                item_result.duration_ms = int((time.monotonic() - item_start) * 1000)
                await self.ingest_runs_repo.complete_run_item(
                    run_item_id=run_item.id,
                    status=IngestRunItemStatus.SUCCESS,
                    tx_added=result.added,
                    tx_modified=result.modified,
                    tx_removed=result.removed,
                    duration_ms=item_result.duration_ms,
                )
                await self.session.commit()

                logger.info(
                    "Item synced successfully",
                    added=result.added,
                    modified=result.modified,
                    removed=result.removed,
                    duration_ms=item_result.duration_ms,
                )

                # Sync liabilities if product is enabled
                if "liabilities" in item.products:
                    try:
                        liabilities_result = await sync_liabilities(item.id)
                        if not liabilities_result.skipped:
                            logger.info(
                                "Liabilities synced",
                                accounts_updated=liabilities_result.accounts_updated,
                                aprs_tracked=liabilities_result.aprs_tracked,
                            )
                    except Exception as e:
                        # Log but don't fail the overall sync for liabilities errors
                        logger.warning(
                            "Failed to sync liabilities",
                            error_type=type(e).__name__,
                        )

            except PlaidError as e:
                items_failed += 1
                item_result.error_code = e.error_code
                item_result.error_message = e.message
                item_result.duration_ms = int((time.monotonic() - item_start) * 1000)

                # Complete the run item as failed
                await self.ingest_runs_repo.complete_run_item(
                    run_item_id=run_item.id,
                    status=IngestRunItemStatus.FAILED,
                    duration_ms=item_result.duration_ms,
                    error_code=e.error_code,
                    error_message=e.message,
                )
                await self.session.commit()

                error_messages.append(
                    f"{item.institution_id or item.item_id}: {e.error_code}"
                )

                logger.error(
                    "Item sync failed",
                    error_code=e.error_code,
                    duration_ms=item_result.duration_ms,
                )

            except Exception as e:
                items_failed += 1
                item_result.error_code = "UNKNOWN_ERROR"
                item_result.error_message = str(e)
                item_result.duration_ms = int((time.monotonic() - item_start) * 1000)

                # Complete the run item as failed
                await self.ingest_runs_repo.complete_run_item(
                    run_item_id=run_item.id,
                    status=IngestRunItemStatus.FAILED,
                    duration_ms=item_result.duration_ms,
                    error_code="UNKNOWN_ERROR",
                    error_message=str(e),
                )
                await self.session.commit()

                error_messages.append(
                    f"{item.institution_id or item.item_id}: {type(e).__name__}"
                )

                logger.error(
                    "Unexpected error during item sync",
                    error_type=type(e).__name__,
                )

            item_results.append(item_result)

        # Determine final status
        if len(items) == 0:
            status = IngestRunStatus.COMPLETED
        elif items_failed == 0:
            status = IngestRunStatus.COMPLETED
        elif items_ok == 0:
            status = IngestRunStatus.FAILED
        else:
            status = IngestRunStatus.PARTIAL

        # Build error summary
        error_summary = "; ".join(error_messages) if error_messages else None

        # Complete the IngestRun
        run_duration_ms = int((time.monotonic() - run_start) * 1000)
        ended_at = datetime.now(UTC)

        await self.ingest_runs_repo.complete_run(
            run_id=ingest_run.id,
            status=status,
            items_ok=items_ok,
            items_failed=items_failed,
            tx_added=total_added,
            tx_modified=total_modified,
            tx_removed=total_removed,
            error_summary=error_summary,
        )
        await self.session.commit()

        logger.info(
            "Sync run completed",
            status=status.value,
            items_total=len(items),
            items_ok=items_ok,
            items_failed=items_failed,
            tx_added=total_added,
            tx_modified=total_modified,
            tx_removed=total_removed,
            duration_ms=run_duration_ms,
        )

        return SyncRunResult(
            run_id=ingest_run.id,
            status=status,
            items_total=len(items),
            items_ok=items_ok,
            items_failed=items_failed,
            tx_added=total_added,
            tx_modified=total_modified,
            tx_removed=total_removed,
            item_results=item_results,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=run_duration_ms,
            error_summary=error_summary,
        )
