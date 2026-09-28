"""Repository for funding sources."""

from decimal import Decimal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.models.funding_source import FundingSource


class FundingSourcesRepository:
    """Repository for funding source operations."""

    def __init__(self, session: AsyncSession):
        self.session = session

    async def get_all(self) -> list[FundingSource]:
        """Get all funding sources."""
        result = await self.session.execute(
            select(FundingSource).order_by(FundingSource.name)
        )
        return result.scalars().all()

    async def get_active(self) -> list[FundingSource]:
        """Get all active funding sources."""
        result = await self.session.execute(
            select(FundingSource)
            .where(FundingSource.active.is_(True))
            .order_by(FundingSource.name)
        )
        return result.scalars().all()

    async def get_by_id(self, source_id: UUID) -> FundingSource | None:
        """Get a funding source by ID."""
        result = await self.session.execute(
            select(FundingSource).where(FundingSource.id == source_id)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        name: str,
        source_type: str,
        available_amount: Decimal,
        notes: str | None = None,
    ) -> FundingSource:
        """Create a new funding source."""
        source = FundingSource(
            name=name,
            source_type=source_type,
            available_amount=available_amount,
            notes=notes,
            active=True,
        )
        self.session.add(source)
        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def update(self, source_id: UUID, **kwargs) -> FundingSource:
        """Update a funding source."""
        source = await self.get_by_id(source_id)
        if not source:
            raise ValueError(f"Funding source {source_id} not found")

        for key, value in kwargs.items():
            if hasattr(source, key):
                setattr(source, key, value)

        await self.session.commit()
        await self.session.refresh(source)
        return source

    async def delete(self, source_id: UUID) -> bool:
        """Soft delete a funding source (set active=False)."""
        source = await self.get_by_id(source_id)
        if not source:
            return False

        source.active = False
        await self.session.commit()
        return True
