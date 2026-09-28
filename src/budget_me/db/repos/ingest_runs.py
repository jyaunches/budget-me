"""Repository for IngestRun operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from budget_me.db.models.ingest_run import (
    IngestRun,
    IngestRunItem,
    IngestRunItemStatus,
    IngestRunStatus,
    IngestRunType,
)
from budget_me.db.repos.base import BaseRepository


class IngestRunsRepo(BaseRepository[IngestRun]):
    """Repository for IngestRun and IngestRunItem operations."""

    model = IngestRun

    async def create_run(
        self,
        run_type: IngestRunType,
        items_total: int = 0,
    ) -> IngestRun:
        """Create a new ingest run.

        Args:
            run_type: The type of ingest run (scheduled, manual, webhook).
            items_total: The total number of items to process.

        Returns:
            The created IngestRun.
        """
        run = IngestRun(
            started_at=datetime.now(UTC),
            run_type=run_type,
            status=IngestRunStatus.RUNNING,
            items_total=items_total,
        )
        self.session.add(run)
        await self.session.flush()
        return run

    async def complete_run(
        self,
        run_id: uuid.UUID,
        status: IngestRunStatus,
        items_ok: int = 0,
        items_failed: int = 0,
        tx_added: int = 0,
        tx_modified: int = 0,
        tx_removed: int = 0,
        error_summary: str | None = None,
    ) -> IngestRun | None:
        """Complete an ingest run with final statistics.

        Args:
            run_id: The IngestRun UUID.
            status: The final status.
            items_ok: Number of items processed successfully.
            items_failed: Number of items that failed.
            tx_added: Total transactions added.
            tx_modified: Total transactions modified.
            tx_removed: Total transactions removed.
            error_summary: Optional summary of errors.

        Returns:
            The updated IngestRun if found, None otherwise.
        """
        run = await self.get_by_id(run_id)
        if run is None:
            return None

        run.ended_at = datetime.now(UTC)
        run.status = status
        run.items_ok = items_ok
        run.items_failed = items_failed
        run.tx_added = tx_added
        run.tx_modified = tx_modified
        run.tx_removed = tx_removed
        run.error_summary = error_summary

        await self.session.flush()
        return run

    async def add_run_item(
        self,
        ingest_run_id: uuid.UUID,
        plaid_item_id: uuid.UUID,
    ) -> IngestRunItem:
        """Add an item to an ingest run.

        Args:
            ingest_run_id: The IngestRun UUID.
            plaid_item_id: The PlaidItem UUID.

        Returns:
            The created IngestRunItem.
        """
        item = IngestRunItem(
            ingest_run_id=ingest_run_id,
            plaid_item_id=plaid_item_id,
            status=IngestRunItemStatus.PENDING,
        )
        self.session.add(item)
        await self.session.flush()
        return item

    async def complete_run_item(
        self,
        run_item_id: uuid.UUID,
        status: IngestRunItemStatus,
        tx_added: int = 0,
        tx_modified: int = 0,
        tx_removed: int = 0,
        duration_ms: int | None = None,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> IngestRunItem | None:
        """Complete an ingest run item with results.

        Args:
            run_item_id: The IngestRunItem UUID.
            status: The final status.
            tx_added: Transactions added for this item.
            tx_modified: Transactions modified for this item.
            tx_removed: Transactions removed for this item.
            duration_ms: Processing duration in milliseconds.
            error_code: Error code if failed.
            error_message: Error message if failed.

        Returns:
            The updated IngestRunItem if found, None otherwise.
        """
        item = await self.session.get(IngestRunItem, run_item_id)
        if item is None:
            return None

        item.status = status
        item.tx_added = tx_added
        item.tx_modified = tx_modified
        item.tx_removed = tx_removed
        item.duration_ms = duration_ms
        item.error_code = error_code
        item.error_message = error_message

        await self.session.flush()
        return item

    async def get_run_items(self, ingest_run_id: uuid.UUID) -> list[IngestRunItem]:
        """Get all items for an ingest run.

        Args:
            ingest_run_id: The IngestRun UUID.

        Returns:
            List of IngestRunItems for the run.
        """
        stmt = select(IngestRunItem).where(IngestRunItem.ingest_run_id == ingest_run_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_recent_runs(self, limit: int = 10) -> list[IngestRun]:
        """Get recent ingest runs.

        Args:
            limit: Maximum number of runs to return.

        Returns:
            List of IngestRuns ordered by started_at descending.
        """
        stmt = select(IngestRun).order_by(IngestRun.started_at.desc()).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_running(self) -> list[IngestRun]:
        """Get all currently running ingest runs.

        Returns:
            List of IngestRuns with RUNNING status.
        """
        stmt = select(IngestRun).where(IngestRun.status == IngestRunStatus.RUNNING)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
