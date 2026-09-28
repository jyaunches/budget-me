"""Repository for account balance snapshot operations."""

from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
from budget_me.db.repos.base import BaseRepository


class AccountBalanceSnapshotRepo(BaseRepository[AccountBalanceSnapshot]):
    """Repository for managing account balance snapshots."""

    model = AccountBalanceSnapshot

    def __init__(self, session: AsyncSession):
        """Initialize repository with database session."""
        super().__init__(session)

    async def upsert(
        self,
        account_id: str,
        snapshot_date: date,
        balance_current: Decimal,
        balance_available: Decimal | None = None,
    ) -> AccountBalanceSnapshot:
        """
        Create or update a balance snapshot for an account on a specific date.

        Args:
            account_id: Account ID to store snapshot for
            snapshot_date: Date of the snapshot
            balance_current: Current balance at snapshot time
            balance_available: Available balance at snapshot time (optional)

        Returns:
            The created or updated AccountBalanceSnapshot instance
        """
        # Query for existing snapshot
        stmt = select(AccountBalanceSnapshot).where(
            AccountBalanceSnapshot.account_id == account_id,
            AccountBalanceSnapshot.snapshot_date == snapshot_date,
        )
        result = await self.session.execute(stmt)
        existing = result.scalar_one_or_none()

        if existing:
            # Update existing snapshot
            existing.balance_current = balance_current
            existing.balance_available = balance_available
            await self.session.flush()
            return existing
        else:
            # Create new snapshot
            snapshot = AccountBalanceSnapshot(
                account_id=account_id,
                snapshot_date=snapshot_date,
                balance_current=balance_current,
                balance_available=balance_available,
            )
            self.session.add(snapshot)
            await self.session.flush()
            return snapshot

    async def get_for_date_range(
        self,
        account_id: str,
        start_date: date,
        end_date: date,
    ) -> list[AccountBalanceSnapshot]:
        """
        Get all balance snapshots for an account within a date range.

        Args:
            account_id: Account ID to query snapshots for
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)

        Returns:
            List of AccountBalanceSnapshot instances ordered by date ascending
        """
        stmt = (
            select(AccountBalanceSnapshot)
            .where(
                AccountBalanceSnapshot.account_id == account_id,
                AccountBalanceSnapshot.snapshot_date >= start_date,
                AccountBalanceSnapshot.snapshot_date <= end_date,
            )
            .order_by(AccountBalanceSnapshot.snapshot_date.asc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())
