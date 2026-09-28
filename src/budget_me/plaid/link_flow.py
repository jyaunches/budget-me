"""Plaid Link flow implementation for connecting bank accounts."""

import uuid
from decimal import Decimal

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.country_code import CountryCode
from plaid.model.institutions_get_by_id_request import InstitutionsGetByIdRequest
from plaid.model.item_get_request import ItemGetRequest
from plaid.model.item_public_token_exchange_request import (
    ItemPublicTokenExchangeRequest,
)
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_transactions import LinkTokenTransactions
from plaid.model.products import Products
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.models.plaid_item import PlaidItemStatus
from budget_me.db.repos import AccountsRepo, CursorsRepo, ItemsRepo
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError


def create_link_token(user_id: str, redirect_uri: str | None = None) -> str:
    """
    Create a Plaid Link token for initializing the Link flow.

    This token is used to initialize Plaid Link in the frontend/browser.
    It's configured to request the Transactions product with 90 days of history.

    Args:
        user_id: Unique identifier for the user (used by Plaid for tracking)
        redirect_uri: OAuth redirect URI (required for OAuth institutions like USAA)

    Returns:
        str: Link token that can be used to initialize Plaid Link

    Raises:
        PlaidError: If link token creation fails
    """
    client = get_plaid_client()

    try:
        # Create the request
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "client_name": "Budget Me",
            "products": [Products("transactions")],
            "additional_consented_products": [Products("liabilities")],
            "country_codes": [CountryCode("US")],
            "language": "en",
            "transactions": LinkTokenTransactions(days_requested=90),
        }

        # Add redirect_uri for OAuth institutions (USAA, Chase, etc.)
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri

        request = LinkTokenCreateRequest(**request_kwargs)

        # Make the API call
        response = client.link_token_create(request)

        return response.link_token

    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create link token: {e.reason}",
            status=e.status,
        ) from e


def create_liabilities_upgrade_token(
    access_token: str, redirect_uri: str | None = None
) -> str:
    """
    Create a Plaid Link token for adding Liabilities product to an existing item.

    This token is used to initialize Plaid Link in update mode, allowing the user
    to grant additional consent for the Liabilities product without re-linking.

    Args:
        access_token: Plaid access token for the existing item
        redirect_uri: OAuth redirect URI (required for OAuth institutions like USAA)

    Returns:
        str: Link token that can be used to initialize Plaid Link in update mode

    Raises:
        PlaidError: If link token creation fails
    """
    client = get_plaid_client()

    try:
        # Create the request for update mode
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id="upgrade"),
            "client_name": "Budget Me",
            "country_codes": [CountryCode("US")],
            "language": "en",
            "access_token": access_token,
            "additional_consented_products": [Products("liabilities")],
        }

        # Add redirect_uri for OAuth institutions
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri

        request = LinkTokenCreateRequest(**request_kwargs)

        # Make the API call
        response = client.link_token_create(request)

        return response.link_token

    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create liabilities upgrade token: {e.reason}",
            status=e.status,
        ) from e


async def add_liabilities_to_item(plaid_item_id: uuid.UUID) -> None:
    """
    Add the liabilities product to an existing PlaidItem.

    This function updates the item's products list to include "liabilities".
    It should be called after successfully completing the Link update flow.

    Args:
        plaid_item_id: Database UUID for the PlaidItem
    """
    async with get_async_session() as session:
        items_repo = ItemsRepo(session)
        await items_repo.add_product(plaid_item_id, "liabilities")

    logger.info(f"Added liabilities product to item {plaid_item_id}")


async def _fetch_and_store_accounts(
    access_token: str, plaid_item_id: uuid.UUID, session: AsyncSession
) -> None:
    """Fetch accounts from Plaid and store them in the database.

    Args:
        access_token: Plaid access token for the item
        plaid_item_id: Database UUID for the PlaidItem
        session: Async database session
    """
    client = get_plaid_client()

    try:
        # Fetch accounts from Plaid
        request = AccountsGetRequest(access_token=access_token)
        response = client.accounts_get(request)

        # Transform Plaid response to account data
        accounts_data = [
            {
                "account_id": acc.account_id,
                "name": acc.name,
                "type": getattr(acc.type, "value", acc.type) if acc.type else None,
                "subtype": getattr(acc.subtype, "value", acc.subtype)
                if acc.subtype
                else None,
                "mask": acc.mask,
                "balance_available": (
                    Decimal(str(acc.balances.available))
                    if acc.balances.available is not None
                    else None
                ),
                "balance_current": (
                    Decimal(str(acc.balances.current))
                    if acc.balances.current is not None
                    else None
                ),
            }
            for acc in response.accounts
        ]

        # Store accounts using AccountsRepo
        accounts_repo = AccountsRepo(session)
        await accounts_repo.bulk_upsert(plaid_item_id, accounts_data)

        logger.info(f"Stored {len(accounts_data)} accounts for item {plaid_item_id}")

    except ApiException as e:
        raise PlaidError(
            message=f"Failed to fetch accounts: {e.reason}",
            status=e.status,
        ) from e


async def exchange_public_token(public_token: str, user_id: str) -> dict:
    """
    Exchange a public token for an access token and store the Plaid item.

    This function:
    1. Exchanges the public_token for an access_token and item_id
    2. Encrypts the access_token before storage
    3. Creates or updates the PlaidItem record
    4. Initializes a PlaidCursor for transaction syncing (if new item)

    Args:
        public_token: The public token from Plaid Link
        user_id: User identifier to associate with the item

    Returns:
        dict: Contains access_token and item_id

    Raises:
        PlaidError: If token exchange fails
    """
    client = get_plaid_client()
    settings = get_settings()

    try:
        # Exchange public token for access token
        request = ItemPublicTokenExchangeRequest(public_token=public_token)
        response = client.item_public_token_exchange(request)

        access_token = response.access_token
        item_id = response.item_id

        # Fetch item details to get institution_id
        item_request = ItemGetRequest(access_token=access_token)
        item_response = client.item_get(item_request)
        institution_id = item_response.item.institution_id

        # Fetch institution name
        institution_name = None
        if institution_id:
            try:
                inst_request = InstitutionsGetByIdRequest(
                    institution_id=institution_id,
                    country_codes=[CountryCode("US")],
                )
                inst_response = client.institutions_get_by_id(inst_request)
                institution_name = inst_response.institution.name
            except ApiException:
                logger.warning(f"Could not fetch institution name for {institution_id}")

        # Encrypt the access token
        encryptor = TokenEncryption(settings.app_token_enc_key)
        encrypted_token = encryptor.encrypt(access_token)

        # Store in database
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)

            # Check if item already exists (idempotency)
            existing_item = await items_repo.find_by_item_id(item_id)

            if existing_item:
                # Update existing item
                await items_repo.update(
                    existing_item,
                    access_token_enc=encrypted_token,
                    status=PlaidItemStatus.ACTIVE,
                    user_key=user_id,
                    institution_id=institution_id,
                    institution_name=institution_name,
                )
                db_item_id = existing_item.id
            else:
                # Create new item
                created_item = await items_repo.create(
                    user_key=user_id,
                    item_id=item_id,
                    access_token_enc=encrypted_token,
                    status=PlaidItemStatus.ACTIVE,
                    institution_id=institution_id,
                    institution_name=institution_name,
                )
                db_item_id = created_item.id

                # Initialize cursor for this item
                cursors_repo = CursorsRepo(session)
                await cursors_repo.create(
                    plaid_item_id=created_item.id,
                    transactions_cursor=None,  # Will be set on first sync
                )

            # Fetch and store accounts (for both new and existing items)
            await _fetch_and_store_accounts(access_token, db_item_id, session)

        return {
            "item_id": str(db_item_id),  # Database UUID for internal use
            "plaid_item_id": item_id,  # Plaid's item identifier
        }

    except ApiException as e:
        raise PlaidError(
            message=f"Failed to exchange public token: {e.reason}",
            status=e.status,
        ) from e
