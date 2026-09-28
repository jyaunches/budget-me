"""Repository for PlaidItem operations."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import select

from budget_me.db.models.plaid_item import PlaidItem, PlaidItemStatus
from budget_me.db.repos.base import BaseRepository


class ItemsRepo(BaseRepository[PlaidItem]):
    """Repository for PlaidItem CRUD and status operations."""

    model = PlaidItem

    async def find_by_item_id(self, item_id: str) -> PlaidItem | None:
        """Find a PlaidItem by its Plaid item_id.

        Args:
            item_id: The Plaid-assigned item identifier.

        Returns:
            The PlaidItem if found, None otherwise.
        """
        stmt = select(PlaidItem).where(PlaidItem.item_id == item_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_user_key(self, user_key: str) -> list[PlaidItem]:
        """Find all PlaidItems for a user.

        Args:
            user_key: The user identifier.

        Returns:
            List of PlaidItems belonging to the user.
        """
        stmt = select(PlaidItem).where(PlaidItem.user_key == user_key)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_active(self) -> list[PlaidItem]:
        """Find all active PlaidItems.

        Returns:
            List of PlaidItems with ACTIVE status.
        """
        stmt = select(PlaidItem).where(PlaidItem.status == PlaidItemStatus.ACTIVE)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def update_status(
        self,
        id: uuid.UUID,
        status: PlaidItemStatus,
        error_code: str | None = None,
        error_message: str | None = None,
    ) -> PlaidItem | None:
        """Update the status of a PlaidItem.

        Args:
            id: The PlaidItem UUID.
            status: The new status.
            error_code: Optional error code if status indicates an error.
            error_message: Optional error message.

        Returns:
            The updated PlaidItem if found, None otherwise.
        """
        item = await self.get_by_id(id)
        if item is None:
            return None

        item.status = status

        if status == PlaidItemStatus.ACTIVE:
            item.last_success_at = datetime.now(UTC)
            item.last_error_code = None
            item.last_error_message = None
        elif error_code or error_message:
            item.last_error_at = datetime.now(UTC)
            item.last_error_code = error_code
            item.last_error_message = error_message

        await self.session.flush()
        return item

    async def record_success(self, id: uuid.UUID) -> PlaidItem | None:
        """Record a successful sync for a PlaidItem.

        Args:
            id: The PlaidItem UUID.

        Returns:
            The updated PlaidItem if found, None otherwise.
        """
        item = await self.get_by_id(id)
        if item is None:
            return None

        item.last_success_at = datetime.now(UTC)
        item.status = PlaidItemStatus.ACTIVE
        await self.session.flush()
        return item

    async def record_error(
        self,
        id: uuid.UUID,
        error_code: str,
        error_message: str,
        new_status: PlaidItemStatus | None = None,
    ) -> PlaidItem | None:
        """Record an error for a PlaidItem.

        Args:
            id: The PlaidItem UUID.
            error_code: The error code from Plaid.
            error_message: The error message.
            new_status: Optional new status (e.g., RELINK_REQUIRED).

        Returns:
            The updated PlaidItem if found, None otherwise.
        """
        item = await self.get_by_id(id)
        if item is None:
            return None

        item.last_error_at = datetime.now(UTC)
        item.last_error_code = error_code
        item.last_error_message = error_message

        if new_status:
            item.status = new_status

        await self.session.flush()
        return item

    async def add_product(self, id: uuid.UUID, product: str) -> PlaidItem | None:
        """Add a product to a PlaidItem's products list.

        Args:
            id: The PlaidItem UUID.
            product: The product to add (e.g., "liabilities").

        Returns:
            The updated PlaidItem if found, None otherwise.
        """
        item = await self.get_by_id(id)
        if item is None:
            return None

        # Only add if not already present
        if product not in item.products:
            item.products = item.products + [product]
            await self.session.flush()

        return item
