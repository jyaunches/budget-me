"""Repository for Account operations."""

import uuid

from sqlalchemy import select

from budget_me.db.models.account import Account
from budget_me.db.repos.base import BaseRepository


class AccountsRepo(BaseRepository[Account]):
    """Repository for Account CRUD and account management operations."""

    model = Account

    async def find_by_item_id(self, plaid_item_id: uuid.UUID) -> list[Account]:
        """Find all accounts for a PlaidItem.

        Args:
            plaid_item_id: The PlaidItem UUID.

        Returns:
            List of Accounts belonging to the PlaidItem.
        """
        stmt = select(Account).where(Account.plaid_item_id == plaid_item_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_account_id(self, account_id: str) -> Account | None:
        """Find an account by Plaid's account_id.

        Args:
            account_id: The Plaid-assigned account identifier.

        Returns:
            The Account if found, None otherwise.
        """
        stmt = select(Account).where(Account.account_id == account_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def bulk_upsert(
        self, plaid_item_id: uuid.UUID, accounts_data: list[dict]
    ) -> None:
        """Upsert multiple accounts for a PlaidItem.

        For existing accounts (matched by account_id), updates all fields.
        For new accounts, creates them.

        Args:
            plaid_item_id: The PlaidItem UUID these accounts belong to.
            accounts_data: List of account data dictionaries with keys:
                account_id, name, type, subtype, mask, balance_available, balance_current
        """
        # Find existing accounts by plaid_item_id
        existing_accounts = await self.find_by_item_id(plaid_item_id)
        existing_map = {acc.account_id: acc for acc in existing_accounts}

        for acc_data in accounts_data:
            account_id = acc_data["account_id"]
            if account_id in existing_map:
                # Update existing account - only Plaid fields, preserving display_name
                # Note: display_name is user-editable and must not be overwritten by syncs
                acc = existing_map[account_id]
                acc.name = acc_data["name"]
                acc.type = acc_data["type"]
                acc.subtype = acc_data.get("subtype")
                acc.mask = acc_data.get("mask")
                acc.balance_available = acc_data.get("balance_available")
                acc.balance_current = acc_data.get("balance_current")
            else:
                # Create new account
                await self.create(plaid_item_id=plaid_item_id, **acc_data)

        await self.session.flush()

    async def get_excluded(self) -> list[Account]:
        """Get all accounts marked as excluded.

        Returns:
            List of Accounts where is_excluded is True.
        """
        stmt = select(Account).where(Account.is_excluded == True)  # noqa: E712
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def get_all(self) -> list[Account]:
        """Get all accounts.

        Returns:
            List of all Accounts.
        """
        stmt = select(Account)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def find_by_mask_and_item(
        self, mask: str, plaid_item_id: uuid.UUID
    ) -> Account | None:
        """Find an account by mask (last 4 digits) within a specific Plaid item.

        Args:
            mask: The last 4 digits of the account number.
            plaid_item_id: The PlaidItem UUID to search within.

        Returns:
            The Account if found, None otherwise.
        """
        stmt = select(Account).where(
            Account.mask == mask,
            Account.plaid_item_id == plaid_item_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()
