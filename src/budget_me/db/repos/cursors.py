"""Repository for PlaidCursor operations."""

import uuid

from sqlalchemy import select

from budget_me.db.models.plaid_cursor import PlaidCursor
from budget_me.db.repos.base import BaseRepository


class CursorsRepo(BaseRepository[PlaidCursor]):
    """Repository for PlaidCursor CRUD operations."""

    model = PlaidCursor

    async def find_by_item_id(self, item_id: uuid.UUID) -> PlaidCursor | None:
        """Find a PlaidCursor by item_id.

        Args:
            item_id: The PlaidItem UUID.

        Returns:
            The PlaidCursor if found, None otherwise.
        """
        stmt = select(PlaidCursor).where(PlaidCursor.plaid_item_id == item_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def update_cursor(
        self, item_id: uuid.UUID, cursor: str
    ) -> PlaidCursor | None:
        """Update the cursor value for an item.

        Args:
            item_id: The PlaidItem UUID.
            cursor: The new cursor value.

        Returns:
            The updated PlaidCursor if found, None otherwise.
        """
        plaid_cursor = await self.find_by_item_id(item_id)
        if not plaid_cursor:
            return None

        plaid_cursor.transactions_cursor = cursor
        await self.session.flush()
        return plaid_cursor
