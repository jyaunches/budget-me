"""Recurring transactions using Plaid's Recurring Transactions API."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.transactions_recurring_get_request import (
    TransactionsRecurringGetRequest,
)

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.repos import ItemsRepo
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError


@dataclass
class RecurringStream:
    """Represents a recurring payment stream."""

    stream_id: str
    account_id: str
    description: str
    merchant_name: str | None
    average_amount: Decimal
    frequency: str
    status: str
    category: list[str]
    last_date: str | None
    is_active: bool
    first_date: str | None
    last_amount: Decimal | None


async def get_recurring_transactions(item_id: uuid.UUID) -> list[RecurringStream]:
    """
    Fetch recurring transaction streams for a Plaid item.

    This function:
    1. Loads the item and decrypts access token
    2. Calls Plaid /transactions/recurring/get endpoint
    3. Parses outflow streams (recurring payments/charges)
    4. Returns structured data for display

    Args:
        item_id: The PlaidItem UUID to fetch recurring transactions for

    Returns:
        list[RecurringStream]: List of recurring payment streams

    Raises:
        PlaidError: If recurring transactions fetch fails
        ValueError: If item not found
    """
    client = get_plaid_client()
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    async with get_async_session() as session:
        # Load item
        items_repo = ItemsRepo(session)
        item = await items_repo.get_by_id(item_id)

        if not item:
            raise ValueError(f"Item {item_id} not found")

        # Decrypt access token
        access_token = encryptor.decrypt(item.access_token_enc)

        try:
            # Fetch recurring transactions from Plaid
            request = TransactionsRecurringGetRequest(access_token=access_token)
            response = client.transactions_recurring_get(request)

            # Parse outflow streams (recurring payments)
            streams = []

            if response.outflow_streams:
                for stream in response.outflow_streams:
                    parsed_stream = RecurringStream(
                        stream_id=stream.stream_id,
                        account_id=stream.account_id,
                        description=stream.description,
                        merchant_name=stream.merchant_name
                        if stream.merchant_name
                        else None,
                        average_amount=Decimal(str(stream.average_amount.amount)),
                        frequency=str(stream.frequency)
                        if stream.frequency
                        else "UNKNOWN",
                        status=str(stream.status) if stream.status else "UNKNOWN",
                        category=stream.category if stream.category else [],
                        last_date=stream.last_date if stream.last_date else None,
                        is_active=stream.is_active,
                        first_date=stream.first_date if stream.first_date else None,
                        last_amount=(
                            Decimal(str(stream.last_amount.amount))
                            if stream.last_amount
                            else None
                        ),
                    )
                    streams.append(parsed_stream)

            logger.info(
                f"Fetched {len(streams)} recurring outflow streams for item {item_id}"
            )

            return streams

        except ApiException as e:
            raise PlaidError(
                message=f"Failed to fetch recurring transactions: {e.reason}",
                status=e.status,
            ) from e
