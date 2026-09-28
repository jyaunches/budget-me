"""Transaction synchronization engine using Plaid's cursor-based sync API."""

import uuid
from dataclasses import dataclass, field
from datetime import UTC, date, timedelta
from decimal import Decimal
from typing import Any

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.accounts_get_request import AccountsGetRequest
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.models.plaid_item import PlaidItemStatus
from budget_me.db.repos import AccountsRepo, CursorsRepo, ItemsRepo, TransactionsRepo
from budget_me.db.repos.account_balance_snapshot_repo import AccountBalanceSnapshotRepo
from budget_me.db.sync_coordination import hold_sync_item_coordination
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import (
    PlaidAuthError,
    PlaidInstitutionError,
    PlaidItemError,
    map_plaid_error,
)


@dataclass
class TransactionDetail:
    """Minimal transaction detail for added transactions."""

    id: uuid.UUID
    plaid_transaction_id: str
    date: date
    amount: Decimal
    name: str
    account_id: str


@dataclass
class ModifiedTransactionDetail:
    """Transaction detail with change tracking."""

    id: uuid.UUID
    plaid_transaction_id: str
    date: date
    amount: Decimal
    name: str
    account_id: str
    changes: list[str] = field(default_factory=list)


@dataclass
class SyncTransactionDetails:
    """Container for transaction details during sync."""

    added: list[TransactionDetail] = field(default_factory=list)
    modified: list[ModifiedTransactionDetail] = field(default_factory=list)
    removed: list[str] = field(default_factory=list)  # plaid_transaction_ids


@dataclass
class ItemSyncResult:
    """Result of syncing a single item."""

    added: int
    modified: int
    removed: int
    transaction_details: SyncTransactionDetails | None = None


async def sync_item(
    item_id: uuid.UUID, include_transactions: bool = False
) -> ItemSyncResult:
    """Synchronize one item while excluding guarded snapshot close."""
    async with hold_sync_item_coordination():
        return await _sync_item_under_coordination(
            item_id, include_transactions=include_transactions
        )


async def _sync_item_under_coordination(
    item_id: uuid.UUID, include_transactions: bool = False
) -> ItemSyncResult:
    """
    Synchronize transactions for a Plaid item using cursor-based sync.

    This function:
    1. Fetches the access token and cursor for the item
    2. Calls /transactions/sync with pagination handling
    3. Processes added/modified/removed transactions
    4. Updates the cursor after successful sync
    5. Applies 90-day history window on initial sync

    Args:
        item_id: The PlaidItem UUID to sync
        include_transactions: If True, capture transaction details for output

    Returns:
        ItemSyncResult: Contains counts and optionally transaction details

    Raises:
        PlaidError: If sync fails
    """
    client = get_plaid_client()
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    async with get_async_session() as session:
        # Load item and cursor
        items_repo = ItemsRepo(session)
        cursors_repo = CursorsRepo(session)
        transactions_repo = TransactionsRepo(session)

        item = await items_repo.get_by_id(item_id)
        if not item:
            raise ValueError(f"Item {item_id} not found")

        # Decrypt access token
        access_token = encryptor.decrypt(item.access_token_enc)

        # Get current cursor
        cursor_record = await cursors_repo.find_by_item_id(item_id)
        if not cursor_record:
            raise ValueError(f"Cursor not found for item {item_id}")

        current_cursor = cursor_record.transactions_cursor

        # Track counts across all pages
        total_added = 0
        total_modified = 0
        total_removed = 0

        # Track transaction details if requested
        transaction_details: SyncTransactionDetails | None = None
        if include_transactions:
            transaction_details = SyncTransactionDetails()

        # Pagination loop
        has_more = True
        next_cursor = current_cursor

        while has_more:
            try:
                # Build request
                request = TransactionsSyncRequest(access_token=access_token)
                if next_cursor:
                    request.cursor = next_cursor

                # Call Plaid API
                response = client.transactions_sync(request)

                # Process added transactions
                if response.added:
                    transactions_to_add = []
                    for txn in response.added:
                        # Convert Plaid transaction to dict
                        txn_dict = _plaid_transaction_to_dict(txn, item_id)

                        # Apply 90-day window check
                        if _is_within_90_days(txn_dict["date"]):
                            transactions_to_add.append(txn_dict)

                    if transactions_to_add:
                        if include_transactions:
                            (
                                added,
                                modified,
                                added_txns,
                                modified_txns,
                            ) = await transactions_repo.bulk_upsert_with_details(
                                transactions_to_add
                            )
                            # Convert to detail objects
                            for txn in added_txns:
                                transaction_details.added.append(
                                    TransactionDetail(
                                        id=txn.id,
                                        plaid_transaction_id=txn.plaid_transaction_id,
                                        date=txn.date,
                                        amount=txn.amount,
                                        name=txn.name,
                                        account_id=txn.account_id,
                                    )
                                )
                            for txn, changes in modified_txns:
                                transaction_details.modified.append(
                                    ModifiedTransactionDetail(
                                        id=txn.id,
                                        plaid_transaction_id=txn.plaid_transaction_id,
                                        date=txn.date,
                                        amount=txn.amount,
                                        name=txn.name,
                                        account_id=txn.account_id,
                                        changes=changes,
                                    )
                                )
                        else:
                            added, modified = await transactions_repo.bulk_upsert(
                                transactions_to_add
                            )
                        total_added += added
                        total_modified += modified

                # Process modified transactions
                if response.modified:
                    transactions_to_modify = []
                    for txn in response.modified:
                        txn_dict = _plaid_transaction_to_dict(txn, item_id)

                        # Apply 90-day window check
                        if _is_within_90_days(txn_dict["date"]):
                            transactions_to_modify.append(txn_dict)

                    if transactions_to_modify:
                        if include_transactions:
                            (
                                added,
                                modified,
                                added_txns,
                                modified_txns,
                            ) = await transactions_repo.bulk_upsert_with_details(
                                transactions_to_modify
                            )
                            # Convert to detail objects
                            for txn in added_txns:
                                transaction_details.added.append(
                                    TransactionDetail(
                                        id=txn.id,
                                        plaid_transaction_id=txn.plaid_transaction_id,
                                        date=txn.date,
                                        amount=txn.amount,
                                        name=txn.name,
                                        account_id=txn.account_id,
                                    )
                                )
                            for txn, changes in modified_txns:
                                transaction_details.modified.append(
                                    ModifiedTransactionDetail(
                                        id=txn.id,
                                        plaid_transaction_id=txn.plaid_transaction_id,
                                        date=txn.date,
                                        amount=txn.amount,
                                        name=txn.name,
                                        account_id=txn.account_id,
                                        changes=changes,
                                    )
                                )
                        else:
                            added, modified = await transactions_repo.bulk_upsert(
                                transactions_to_modify
                            )
                        total_added += added
                        total_modified += modified

                # Process removed transactions
                if response.removed:
                    removed_ids = [txn.transaction_id for txn in response.removed]
                    deleted_count = await transactions_repo.delete_by_plaid_ids(
                        removed_ids
                    )
                    total_removed += deleted_count
                    # Capture removed IDs if tracking details
                    if include_transactions:
                        transaction_details.removed.extend(removed_ids)

                # Update cursor after processing this page
                next_cursor = response.next_cursor
                has_more = response.has_more

                # Save cursor after each page
                await cursors_repo.update_cursor(item_id, next_cursor)
                await session.commit()

            except ApiException as e:
                # Map to appropriate PlaidError subclass
                plaid_error = map_plaid_error(e)

                # Log the error with context
                logger.error(
                    "Plaid API error during transaction sync",
                    item_id=str(item_id),
                    error_code=plaid_error.error_code,
                    status=plaid_error.status,
                    message=plaid_error.message,
                )

                # Handle specific error types
                if isinstance(plaid_error, PlaidItemError):
                    # Item needs relink
                    item.status = PlaidItemStatus.RELINK_REQUIRED
                    await items_repo.update(item)
                    await session.commit()
                    logger.warning(
                        "Item marked for relink",
                        item_id=str(item_id),
                        error_code=plaid_error.error_code,
                    )
                    raise plaid_error from e

                elif isinstance(plaid_error, PlaidInstitutionError):
                    # Institution unavailable - log error details but keep status active
                    from datetime import datetime

                    item.last_error_at = datetime.now(UTC)
                    item.last_error_code = plaid_error.error_code
                    item.last_error_message = plaid_error.message
                    await items_repo.update(item)
                    await session.commit()
                    logger.warning(
                        "Item error due to institution issue",
                        item_id=str(item_id),
                        error_code=plaid_error.error_code,
                    )
                    raise plaid_error from e

                elif isinstance(plaid_error, PlaidAuthError):
                    # Authentication error - critical
                    logger.error(
                        "Plaid authentication error",
                        error_code=plaid_error.error_code,
                    )
                    raise plaid_error from e

                elif (
                    plaid_error.error_code
                    == "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION"
                ):
                    # Restart from initial cursor
                    logger.info(
                        "Restarting sync due to mutation during pagination",
                        item_id=str(item_id),
                    )
                    next_cursor = current_cursor
                    has_more = True
                    continue

                else:
                    # Generic error - log and raise
                    raise plaid_error from e

        # Refresh account balances after successful transaction sync
        await _refresh_accounts(access_token, item_id, session)
        await session.commit()

    return ItemSyncResult(
        added=total_added,
        modified=total_modified,
        removed=total_removed,
        transaction_details=transaction_details,
    )


def _plaid_transaction_to_dict(plaid_txn: Any, item_id: uuid.UUID) -> dict[str, Any]:
    """
    Convert a Plaid transaction object to a dictionary for DB storage.

    Args:
        plaid_txn: Plaid transaction object from API response
        item_id: The PlaidItem UUID

    Returns:
        dict: Transaction data ready for DB insertion
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
    """
    Convert an object to JSON-serializable format.

    Handles Plaid model objects, enums, dates, and other types.
    """
    import json
    from enum import Enum

    if obj is None:
        return None
    elif isinstance(obj, (str, int, float, bool)):
        return obj
    elif isinstance(obj, Enum):
        return obj.value
    elif isinstance(obj, (date,)):
        return obj.isoformat()
    elif isinstance(obj, dict):
        return {k: _to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [_to_json_serializable(item) for item in obj]
    elif hasattr(obj, "to_dict"):
        return _to_json_serializable(obj.to_dict())
    elif hasattr(obj, "__dict__"):
        return _to_json_serializable(vars(obj))
    else:
        # Try to convert to string as last resort
        try:
            json.dumps(obj)
            return obj
        except (TypeError, ValueError):
            return str(obj)


def _is_within_90_days(transaction_date: date) -> bool:
    """
    Check if a transaction date is within the 90-day history window.

    Args:
        transaction_date: The date of the transaction

    Returns:
        bool: True if within 90 days, False otherwise
    """
    cutoff_date = date.today() - timedelta(days=90)
    return transaction_date >= cutoff_date


async def _refresh_accounts(
    access_token: str, plaid_item_id: uuid.UUID, session: AsyncSession
) -> None:
    """
    Refresh account data (balances and metadata) from Plaid.

    Args:
        access_token: Decrypted Plaid access token
        plaid_item_id: The PlaidItem UUID
        session: Active database session
    """
    client = get_plaid_client()

    # Fetch accounts from Plaid
    request = AccountsGetRequest(access_token=access_token)
    response = client.accounts_get(request)

    # Transform Plaid response to dict format
    accounts_data = [
        {
            "account_id": acc.account_id,
            "name": acc.name,
            "type": getattr(acc.type, "value", acc.type) if acc.type else None,
            "subtype": getattr(acc.subtype, "value", acc.subtype)
            if acc.subtype
            else None,
            "mask": acc.mask,
            "balance_available": acc.balances.available,
            "balance_current": acc.balances.current,
        }
        for acc in response.accounts
    ]

    # Upsert accounts (create new or update existing)
    accounts_repo = AccountsRepo(session)
    await accounts_repo.bulk_upsert(plaid_item_id, accounts_data)

    # Store balance snapshots for each account
    balance_snapshot_repo = AccountBalanceSnapshotRepo(session)
    snapshot_date = date.today()

    for acc_data in accounts_data:
        # Skip if balance_current is None
        if acc_data["balance_current"] is None:
            logger.warning(
                "Skipping balance snapshot - balance_current is None",
                account_id=acc_data["account_id"],
            )
            continue

        try:
            await balance_snapshot_repo.upsert(
                account_id=acc_data["account_id"],
                snapshot_date=snapshot_date,
                balance_current=acc_data["balance_current"],
                balance_available=acc_data["balance_available"],
            )
        except Exception as e:
            # Log but don't fail sync - balance snapshots are supplementary data
            logger.error(
                "Failed to store balance snapshot",
                account_id=acc_data["account_id"],
                error=str(e),
            )

    logger.info(
        "Refreshed account balances",
        plaid_item_id=str(plaid_item_id),
        account_count=len(accounts_data),
    )
