"""Repository for AnticipatedItem operations."""

import uuid
from decimal import Decimal

from sqlalchemy import select

from budget_me.db.models.anticipated_item import AnticipatedItem
from budget_me.db.repos.base import BaseRepository


class AnticipatedItemsRepo(BaseRepository[AnticipatedItem]):
    """Repository for AnticipatedItem CRUD operations."""

    model = AnticipatedItem

    async def get_active(self) -> list[AnticipatedItem]:
        """Get all active anticipated items.

        Returns:
            List of active AnticipatedItem instances.
        """
        stmt = select(AnticipatedItem).where(AnticipatedItem.active.is_(True))
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_active_by_type(self, item_type: str) -> list[AnticipatedItem]:
        """Get all active anticipated items filtered by type.

        Args:
            item_type: The type of items to retrieve ('expense' or 'income').

        Returns:
            List of active AnticipatedItem instances matching the type.
        """
        stmt = select(AnticipatedItem).where(
            AnticipatedItem.active.is_(True), AnticipatedItem.item_type == item_type
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(
        self,
        name: str,
        amount: Decimal,
        item_type: str,
        category: str | None = None,
    ) -> AnticipatedItem:
        """Create a new anticipated item.

        Args:
            name: Display name for the item.
            amount: Monthly amount.
            item_type: Type of item ('expense' or 'income').
            category: Optional category for grouping.

        Returns:
            The created AnticipatedItem instance.
        """
        instance = AnticipatedItem(
            name=name, amount=amount, item_type=item_type, category=category
        )
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, item_id: uuid.UUID, **kwargs) -> AnticipatedItem | None:
        """Update an anticipated item.

        Args:
            item_id: UUID of the item to update.
            **kwargs: Fields to update.

        Returns:
            The updated AnticipatedItem instance if found, None otherwise.
        """
        item = await self.get_by_id(item_id)
        if item is None:
            return None

        for key, value in kwargs.items():
            setattr(item, key, value)
        await self.session.flush()
        return item

    async def delete(self, item_id: uuid.UUID) -> bool:
        """Soft delete (deactivate) an anticipated item.

        Args:
            item_id: UUID of the item to delete.

        Returns:
            True if item was found and deactivated, False otherwise.
        """
        item = await self.get_by_id(item_id)
        if item is None:
            return False

        item.active = False
        await self.session.flush()
        return True
