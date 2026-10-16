"""Existing-Item consent and verification helpers for Plaid Investments."""

import uuid

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.models.plaid_item import PlaidItemStatus
from budget_me.db.repos import ItemsRepo
from budget_me.plaid.investments_sync import sync_investments_for_access_token
from budget_me.plaid.link_flow import create_investments_upgrade_token


async def create_item_investments_upgrade_token(
    plaid_item_id: uuid.UUID,
    user_id: str,
    redirect_uri: str | None = None,
) -> str:
    """Create update-mode Link consent for a stored Plaid Item."""
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)
    async with get_async_session() as session:
        item = await ItemsRepo(session).get_by_id(plaid_item_id)
        if item is None:
            raise ValueError(f"Item {plaid_item_id} not found")
        access_token = encryptor.decrypt(item.access_token_enc)

    return create_investments_upgrade_token(
        access_token=access_token,
        user_id=user_id,
        redirect_uri=redirect_uri,
    )


async def verify_item_investments_access(plaid_item_id: uuid.UUID) -> dict:
    """Prove holdings access before recording Investments as enabled locally."""
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)
    async with get_async_session() as session:
        items_repo = ItemsRepo(session)
        item = await items_repo.get_by_id(plaid_item_id)
        if item is None:
            raise ValueError(f"Item {plaid_item_id} not found")

        result = await sync_investments_for_access_token(
            access_token=encryptor.decrypt(item.access_token_enc),
            plaid_item_id=plaid_item_id,
            session=session,
            include_transactions=False,
        )
        await items_repo.add_product(plaid_item_id, "investments")
        await items_repo.update_status(plaid_item_id, PlaidItemStatus.ACTIVE)
        return {
            "id": str(item.id),
            "institution_name": item.institution_name or item.institution_id,
            "status": PlaidItemStatus.ACTIVE.value,
            "holdings_updated": result.holdings_updated,
        }
