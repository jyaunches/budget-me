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
from plaid.model.link_token_create_hosted_link import LinkTokenCreateHostedLink
from plaid.model.link_token_create_request import LinkTokenCreateRequest
from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
from plaid.model.link_token_get_request import LinkTokenGetRequest
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
from budget_me.plaid.investments_sync import sync_investments_for_access_token


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


def create_hosted_link_session(
    user_id: str, redirect_uri: str | None = None
) -> dict[str, str]:
    """Create a top-level Plaid Hosted Link session for a new bank connection.

    Streamlit custom HTML runs in a nested ``srcdoc`` iframe with an opaque
    origin. Hosted Link keeps Plaid in a normal, top-level secure browser tab
    and lets the server retrieve the result after the user returns.
    """
    client = get_plaid_client()
    try:
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "client_name": "Budget Me",
            "products": [Products("transactions")],
            "additional_consented_products": [Products("liabilities")],
            "country_codes": [CountryCode("US")],
            "language": "en",
            "transactions": LinkTokenTransactions(days_requested=90),
            "hosted_link": LinkTokenCreateHostedLink(),
        }
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri

        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
        hosted_link_url = getattr(response, "hosted_link_url", None)
        if not hosted_link_url:
            raise PlaidError(message="Plaid did not return a Hosted Link URL")

        return {
            "link_token": response.link_token,
            "hosted_link_url": hosted_link_url,
        }
    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create Hosted Link session: {e.reason}",
            status=e.status,
        ) from e


def get_hosted_link_public_tokens(link_token: str) -> list[str]:
    """Return distinct public tokens from a completed Hosted Link session."""
    client = get_plaid_client()
    try:
        response = client.link_token_get(LinkTokenGetRequest(link_token=link_token))
    except ApiException as e:
        raise PlaidError(
            message=f"Failed to check Hosted Link session: {e.reason}",
            status=e.status,
        ) from e

    public_tokens: list[str] = []
    for link_session in response.link_sessions or []:
        results = getattr(link_session, "results", None)
        for item in getattr(results, "item_add_results", None) or []:
            token = getattr(item, "public_token", None)
            if token and token not in public_tokens:
                public_tokens.append(token)

        # Support older single-Item response shapes as a compatibility fallback.
        on_success = getattr(link_session, "on_success", None)
        token = getattr(on_success, "public_token", None)
        if token and token not in public_tokens:
            public_tokens.append(token)

    return public_tokens


def create_investment_link_token(user_id: str, redirect_uri: str | None = None) -> str:
    """Create a Link token restricted to investment-compatible accounts."""
    client = get_plaid_client()
    try:
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "client_name": "Budget Me",
            "products": [Products("investments")],
            "country_codes": [CountryCode("US")],
            "language": "en",
        }
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri

        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
        return response.link_token
    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create investment link token: {e.reason}",
            status=e.status,
        ) from e


def create_investments_upgrade_token(
    access_token: str,
    user_id: str,
    redirect_uri: str | None = None,
) -> str:
    """Create update-mode Link consent for Investments on an existing Item."""
    client = get_plaid_client()
    try:
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "client_name": "Budget Me",
            "country_codes": [CountryCode("US")],
            "language": "en",
            "access_token": access_token,
            "additional_consented_products": [Products("investments")],
        }
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri
        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
        return response.link_token
    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create Investments upgrade token: {e.reason}",
            status=e.status,
        ) from e


def create_update_link_token(
    access_token: str,
    user_id: str,
    redirect_uri: str | None = None,
) -> str:
    """Create a Plaid Link token that repairs an existing Item.

    Update mode is the required recovery path for ``ITEM_LOGIN_REQUIRED``.
    Products and product-specific options must be omitted so Plaid repairs the
    existing authorization instead of creating or expanding an Item.
    """
    client = get_plaid_client()

    try:
        request_kwargs = {
            "user": LinkTokenCreateRequestUser(client_user_id=user_id),
            "client_name": "Budget Me",
            "country_codes": [CountryCode("US")],
            "language": "en",
            "access_token": access_token,
        }
        if redirect_uri:
            request_kwargs["redirect_uri"] = redirect_uri

        response = client.link_token_create(LinkTokenCreateRequest(**request_kwargs))
        return response.link_token
    except ApiException as e:
        raise PlaidError(
            message=f"Failed to create update-mode link token: {e.reason}",
            status=e.status,
        ) from e


async def list_plaid_items_for_link() -> list[dict[str, object]]:
    """Return non-secret Plaid Item metadata for the Link Account page."""
    async with get_async_session() as session:
        items = await ItemsRepo(session).get_all()

    return [
        {
            "id": str(item.id),
            "institution_name": item.institution_name or item.institution_id,
            "status": item.status.value,
            "last_error_code": item.last_error_code,
            "products": list(item.products or []),
        }
        for item in sorted(
            items,
            key=lambda value: (
                value.institution_name or value.institution_id or "",
                str(value.id),
            ),
        )
    ]


async def create_item_relink_token(
    plaid_item_id: uuid.UUID,
    user_id: str,
    redirect_uri: str | None = None,
) -> str:
    """Create an update-mode Link token for a stored Plaid Item."""
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    async with get_async_session() as session:
        item = await ItemsRepo(session).get_by_id(plaid_item_id)
        if item is None:
            raise ValueError(f"Item {plaid_item_id} not found")
        access_token = encryptor.decrypt(item.access_token_enc)

    return create_update_link_token(
        access_token=access_token,
        user_id=user_id,
        redirect_uri=redirect_uri,
    )


async def verify_item_relink(plaid_item_id: uuid.UUID) -> dict[str, str | None]:
    """Verify repaired provider access and reactivate the existing Item.

    The browser callback alone is not trusted. A successful ``/item/get`` call
    proves that Plaid accepted the update-mode flow before local status and
    account balances are refreshed.
    """
    client = get_plaid_client()
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    try:
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)
            item = await items_repo.get_by_id(plaid_item_id)
            if item is None:
                raise ValueError(f"Item {plaid_item_id} not found")

            access_token = encryptor.decrypt(item.access_token_enc)
            client.item_get(ItemGetRequest(access_token=access_token))
            await _fetch_and_store_accounts(access_token, plaid_item_id, session)
            await items_repo.update_status(plaid_item_id, PlaidItemStatus.ACTIVE)

            return {
                "id": str(item.id),
                "institution_name": item.institution_name or item.institution_id,
                "status": PlaidItemStatus.ACTIVE.value,
            }
    except ApiException as e:
        raise PlaidError(
            message=f"Plaid has not confirmed the repaired connection: {e.reason}",
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


async def exchange_public_token(
    public_token: str,
    user_id: str,
    products: list[str] | None = None,
) -> dict:
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
    enabled_products = products or ["transactions"]

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
                    products=sorted(
                        set(existing_item.products or []) | set(enabled_products)
                    ),
                )
                db_item_id = existing_item.id
            else:
                # Create new item
                created_item = await items_repo.create(
                    user_key=user_id,
                    item_id=item_id,
                    access_token_enc=encrypted_token,
                    products=enabled_products,
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

            # Holdings are available immediately for an investment Link. Historical
            # investment transactions are loaded by the explicit investments sync.
            if "investments" in enabled_products:
                await sync_investments_for_access_token(
                    access_token=access_token,
                    plaid_item_id=db_item_id,
                    session=session,
                    include_transactions=False,
                )

        return {
            "item_id": str(db_item_id),  # Database UUID for internal use
            "plaid_item_id": item_id,  # Plaid's item identifier
        }

    except ApiException as e:
        raise PlaidError(
            message=f"Failed to exchange public token: {e.reason}",
            status=e.status,
        ) from e
