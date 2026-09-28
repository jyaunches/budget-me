"""Repository for Merchant operations."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert

from budget_me.db.models.merchant import MerchantMap, MerchantRule
from budget_me.db.repos.base import BaseRepository


class MerchantsRepo(BaseRepository[MerchantRule]):
    """Repository for MerchantRule and MerchantMap operations."""

    model = MerchantRule

    async def get_active_rules(self) -> list[MerchantRule]:
        """Get all active merchant rules ordered by priority.

        Returns:
            List of enabled MerchantRules ordered by priority (highest first).
        """
        stmt = (
            select(MerchantRule)
            .where(MerchantRule.enabled == True)  # noqa: E712
            .order_by(MerchantRule.priority.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_mapped_name(self, input_name: str) -> str | None:
        """Get the normalized name for an input merchant name.

        Args:
            input_name: The raw merchant name to look up.

        Returns:
            The normalized name if found in cache, None otherwise.
        """
        stmt = select(MerchantMap.normalized).where(
            MerchantMap.input_name == input_name
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def set_mapped_name(self, input_name: str, normalized: str) -> MerchantMap:
        """Set or update a merchant name mapping.

        Args:
            input_name: The raw merchant name.
            normalized: The normalized merchant name.

        Returns:
            The created or updated MerchantMap.
        """
        stmt = insert(MerchantMap).values(
            input_name=input_name,
            normalized=normalized,
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=["input_name"],
            set_={"normalized": stmt.excluded.normalized},
        )
        await self.session.execute(stmt)
        await self.session.flush()

        # Return the mapping
        result = await self.session.execute(
            select(MerchantMap).where(MerchantMap.input_name == input_name)
        )
        return result.scalar_one()

    async def get_all_mappings(self, limit: int = 1000) -> list[MerchantMap]:
        """Get all merchant name mappings.

        Args:
            limit: Maximum number of mappings to return.

        Returns:
            List of MerchantMap entries.
        """
        stmt = select(MerchantMap).limit(limit)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def delete_mapping(self, input_name: str) -> bool:
        """Delete a merchant name mapping.

        Args:
            input_name: The input name to delete.

        Returns:
            True if a mapping was deleted, False otherwise.
        """
        mapping = await self.session.get(MerchantMap, input_name)
        if mapping:
            await self.session.delete(mapping)
            await self.session.flush()
            return True
        return False
