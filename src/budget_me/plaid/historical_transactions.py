"""Historical transaction fetch using Plaid's /transactions/get endpoint.

Unlike /transactions/sync (cursor-based, incremental), this endpoint fetches
all transactions within a date range. Use for backfilling historical data.
"""

import uuid
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.transactions_get_request import TransactionsGetRequest
from plaid.model.transactions_get_request_options import TransactionsGetRequestOptions

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.repos import AccountsRepo, ItemsRepo, TransactionsRepo
from budget_me.db.sync_coordination import hold_sync_item_coordination
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError


@dataclass
class HistoricalFetchResult:
    """Result of fetching historical transactions."""

    transactions_fetched: int
    transactions_added: int
    transactions_updated: int
    oldest_date: date | None
    newest_date: date | None


async def fetch_historical_transactions(
    item_id: uuid.UUID,
    days: int = 180,
    account_ids: list[str] | None = None,
) -> HistoricalFetchResult:
    """Backfill one item while excluding guarded snapshot close."""
    async with hold_sync_item_coordination():
        return await _fetch_historical_transactions_under_coordination(
            item_id,
            days=days,
            account_ids=account_ids,
        )


async def _fetch_historical_transactions_under_coordination(
    item_id: uuid.UUID,
    days: int = 180,
    account_ids: list[str] | None = None,
) -> HistoricalFetchResult:
    """
    Fetch historical transactions using Plaid /transactions/get endpoint.

    Unlike /transactions/sync (incremental), this fetches all transactions
    in a date range regardless of cursor state. Useful for backfilling
    historical data that wasn't captured during initial link.

    Args:
        item_id: The PlaidItem UUID to fetch transactions for
        days: Number of days of history to fetch (default: 180)
        account_ids: Optional list of Plaid account IDs to filter.
                    If None, fetches for all accounts in the item.

    Returns:
        HistoricalFetchResult with counts and date range

    Raises:
        PlaidError: If API call fails
        ValueError: If item not found
    """
    client = get_plaid_client()
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    end_date = date.today()
    start_date = end_date - timedelta(days=days)

    async with get_async_session() as session:
        # Load item
        items_repo = ItemsRepo(session)
        transactions_repo = TransactionsRepo(session)

        item = await items_repo.get_by_id(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")

        # Decrypt access token
        access_token = encryptor.decrypt(item.access_token_enc)

        # Build request options
        options = TransactionsGetRequestOptions()
        if account_ids:
            options.account_ids = account_ids

        # Fetch all transactions with pagination
        all_transactions: list[dict[str, Any]] = []
        offset = 0
        total_transactions = None

        logger.info(
            f"Fetching historical transactions for item {item_id}",
            start_date=str(start_date),
            end_date=str(end_date),
            account_ids=account_ids,
        )

        try:
            while True:
                # Build request
                request = TransactionsGetRequest(
                    access_token=access_token,
                    start_date=start_date,
                    end_date=end_date,
                    options=options,
                )
                request.options.offset = offset
                request.options.count = 500  # Max per request

                # Call Plaid API
                response = client.transactions_get(request)

                # First response tells us total count
                if total_transactions is None:
                    total_transactions = response.total_transactions
                    logger.info(f"Total transactions available: {total_transactions}")

                # Process transactions
                for txn in response.transactions:
                    txn_dict = _plaid_transaction_to_dict(txn, item_id)
                    all_transactions.append(txn_dict)

                # Check if we have all transactions
                offset += len(response.transactions)
                if offset >= total_transactions:
                    break

                logger.debug(f"Fetched {offset}/{total_transactions} transactions")

        except ApiException as e:
            raise PlaidError(
                message=f"Failed to fetch transactions: {e.reason}",
                status=e.status,
            ) from e

        # Bulk upsert all transactions
        if all_transactions:
            added, updated = await transactions_repo.bulk_upsert(all_transactions)

            # Find date range
            dates = [t["date"] for t in all_transactions]
            oldest = min(dates) if dates else None
            newest = max(dates) if dates else None

            logger.info(
                "Historical fetch complete",
                fetched=len(all_transactions),
                added=added,
                updated=updated,
                oldest=str(oldest),
                newest=str(newest),
            )

            return HistoricalFetchResult(
                transactions_fetched=len(all_transactions),
                transactions_added=added,
                transactions_updated=updated,
                oldest_date=oldest,
                newest_date=newest,
            )

        return HistoricalFetchResult(
            transactions_fetched=0,
            transactions_added=0,
            transactions_updated=0,
            oldest_date=None,
            newest_date=None,
        )


async def fetch_historical_for_account_mask(
    item_id: uuid.UUID,
    account_mask: str,
    days: int = 180,
) -> HistoricalFetchResult:
    """
    Fetch historical transactions for a specific account by mask.

    Convenience wrapper that looks up the account_id from the mask.

    Args:
        item_id: The PlaidItem UUID
        account_mask: Last 4 digits of account number (e.g., "0000")
        days: Number of days of history to fetch

    Returns:
        HistoricalFetchResult

    Raises:
        ValueError: If account with mask not found
    """
    async with get_async_session() as session:
        accounts_repo = AccountsRepo(session)

        # Find account by mask within this item
        account = await accounts_repo.find_by_mask_and_item(account_mask, item_id)
        if not account:
            raise ValueError(
                f"Account with mask {account_mask} not found for item {item_id}"
            )

        logger.info(f"Found account: {account.name} ({account.mask})")

    # Fetch with the specific account_id
    return await fetch_historical_transactions(
        item_id=item_id,
        days=days,
        account_ids=[account.account_id],
    )


def _plaid_transaction_to_dict(plaid_txn: Any, item_id: uuid.UUID) -> dict[str, Any]:
    """
    Convert a Plaid transaction object to a dictionary for DB storage.

    Note: This is duplicated from transactions_sync.py to keep modules independent.
    Consider extracting to a shared module if more duplication occurs.
    """
    return {
        "plaid_transaction_id": plaid_txn.transaction_id,
        "plaid_item_id": item_id,
        "account_id": plaid_txn.account_id,
        "date": date.fromisoformat(plaid_txn.date)
        if isinstance(plaid_txn.date, str)
        else plaid_txn.date,
        "amount": plaid_txn.amount,
        "name": plaid_txn.name,
        "merchant_name": getattr(plaid_txn, "merchant_name", None),
        "pending": getattr(plaid_txn, "pending", False),
        "payment_channel": getattr(plaid_txn, "payment_channel", None),
        "category_primary": plaid_txn.category[0] if plaid_txn.category else None,
        "category_detailed": ", ".join(plaid_txn.category)
        if plaid_txn.category
        else None,
        "authorized_date": (
            date.fromisoformat(plaid_txn.authorized_date)
            if hasattr(plaid_txn, "authorized_date")
            and plaid_txn.authorized_date
            and isinstance(plaid_txn.authorized_date, str)
            else None
        ),
        "raw": _to_json_serializable(plaid_txn.to_dict())
        if hasattr(plaid_txn, "to_dict")
        else {},
    }


def _to_json_serializable(obj: Any) -> Any:
    """Convert Plaid objects to JSON-serializable format."""
    if isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [_to_json_serializable(item) for item in obj]
    elif isinstance(obj, date):
        return obj.isoformat()
    elif isinstance(obj, Decimal):
        return float(obj)
    elif hasattr(obj, "to_dict"):
        return _to_json_serializable(obj.to_dict())
    return obj
