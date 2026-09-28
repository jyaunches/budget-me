"""Liabilities synchronization using Plaid's Liabilities product API."""

import uuid
from dataclasses import dataclass
from decimal import Decimal

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.liabilities_get_request import LiabilitiesGetRequest

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.repos import ItemsRepo, LiabilitiesRepo
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError


@dataclass
class LiabilitiesSyncResult:
    """Result of syncing liabilities for an item."""

    accounts_updated: int
    aprs_tracked: int
    skipped: bool


async def sync_liabilities(item_id: uuid.UUID) -> LiabilitiesSyncResult:
    """
    Synchronize liabilities for a Plaid item.

    This function:
    1. Checks if item has liabilities product enabled
    2. If not, returns early with skipped=True
    3. Fetches liabilities from Plaid /liabilities/get endpoint
    4. Parses and stores credit liability data
    5. Stores APR details for each liability

    Args:
        item_id: The PlaidItem UUID to sync

    Returns:
        LiabilitiesSyncResult: Contains counts and skip status

    Raises:
        PlaidError: If liabilities fetch fails
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

        # Check if liabilities product is enabled
        if "liabilities" not in item.products:
            logger.debug("Item does not have liabilities product; skipping")
            return LiabilitiesSyncResult(
                accounts_updated=0, aprs_tracked=0, skipped=True
            )

        # Decrypt access token
        access_token = encryptor.decrypt(item.access_token_enc)

        try:
            # Fetch liabilities from Plaid
            request = LiabilitiesGetRequest(access_token=access_token)
            response = client.liabilities_get(request)

            # Process credit liabilities
            liabilities_repo = LiabilitiesRepo(session)
            accounts_updated = 0
            total_aprs = 0

            if response.liabilities.credit:
                for credit in response.liabilities.credit:
                    # Parse liability data
                    liability_data = _parse_credit_liability(credit)

                    # Upsert liability record
                    liability = await liabilities_repo.upsert_liability(
                        plaid_item_id=item_id,
                        account_id=credit.account_id,
                        data=liability_data,
                    )

                    # Parse and upsert APRs
                    aprs_data = _parse_aprs(credit.aprs) if credit.aprs else []

                    if aprs_data:
                        await liabilities_repo.upsert_aprs(liability.id, aprs_data)

                    accounts_updated += 1
                    total_aprs += len(aprs_data)

            logger.info(
                f"Synced liabilities for item {item_id}: "
                f"{accounts_updated} accounts, {total_aprs} APRs"
            )

            return LiabilitiesSyncResult(
                accounts_updated=accounts_updated,
                aprs_tracked=total_aprs,
                skipped=False,
            )

        except ApiException as e:
            raise PlaidError(
                message=f"Failed to fetch liabilities: {e.reason}", status=e.status
            ) from e


def _parse_credit_liability(credit_data) -> dict:
    """
    Parse credit liability data from Plaid response.

    Args:
        credit_data: Credit liability object from Plaid response

    Returns:
        dict: Parsed liability data ready for database storage
    """
    return {
        "is_overdue": credit_data.is_overdue,
        "last_payment_amount": (
            Decimal(str(credit_data.last_payment_amount))
            if credit_data.last_payment_amount is not None
            else None
        ),
        "last_payment_date": credit_data.last_payment_date,
        "last_statement_balance": (
            Decimal(str(credit_data.last_statement_balance))
            if credit_data.last_statement_balance is not None
            else None
        ),
        "last_statement_issue_date": credit_data.last_statement_issue_date,
        "minimum_payment_amount": (
            Decimal(str(credit_data.minimum_payment_amount))
            if credit_data.minimum_payment_amount is not None
            else None
        ),
        "next_payment_due_date": credit_data.next_payment_due_date,
    }


def _parse_aprs(aprs_data) -> list[dict]:
    """
    Parse APR data from Plaid response.

    Args:
        aprs_data: List of APR objects from Plaid response

    Returns:
        list[dict]: Parsed APR data ready for database storage
    """
    parsed_aprs = []

    for apr in aprs_data:
        parsed_aprs.append(
            {
                "apr_type": apr.apr_type,
                "apr_percentage": Decimal(str(apr.apr_percentage)),
                "balance_subject_to_apr": (
                    Decimal(str(apr.balance_subject_to_apr))
                    if apr.balance_subject_to_apr is not None
                    else None
                ),
                "interest_charge_amount": (
                    Decimal(str(apr.interest_charge_amount))
                    if apr.interest_charge_amount is not None
                    else None
                ),
            }
        )

    return parsed_aprs
