"""Synchronization for Plaid investment holdings and transactions."""

import json
import uuid
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal
from enum import Enum
from typing import Any

from loguru import logger
from plaid.api_client import ApiException
from plaid.model.investments_holdings_get_request import InvestmentsHoldingsGetRequest
from plaid.model.investments_transactions_get_request import (
    InvestmentsTransactionsGetRequest,
)
from plaid.model.investments_transactions_get_request_options import (
    InvestmentsTransactionsGetRequestOptions,
)
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.config import get_settings
from budget_me.crypto.token_encryption import TokenEncryption
from budget_me.db.engine import get_async_session
from budget_me.db.repos import AccountsRepo, InvestmentsRepo, ItemsRepo
from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError

TRANSACTION_HISTORY_DAYS = 730
TRANSACTION_PAGE_SIZE = 500


@dataclass(frozen=True)
class InvestmentsSyncResult:
    """Counts returned by a complete Investments sync."""

    accounts_updated: int
    securities_updated: int
    holdings_updated: int
    transactions_added: int
    transactions_updated: int
    transactions_ready: bool


def _value(value: Any) -> Any:
    return getattr(value, "value", value)


def _decimal(value: Any) -> Decimal | None:
    return Decimal(str(value)) if value is not None else None


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, (date, datetime)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    if hasattr(value, "to_dict"):
        return _json_value(value.to_dict())
    try:
        json.dumps(value)
        return value
    except (TypeError, ValueError):
        return str(value)


def _parse_accounts(accounts: list[Any]) -> list[dict[str, Any]]:
    return [
        {
            "account_id": account.account_id,
            "name": account.name,
            "type": _value(account.type),
            "subtype": _value(account.subtype) if account.subtype else None,
            "mask": account.mask,
            "balance_available": _decimal(account.balances.available),
            "balance_current": _decimal(account.balances.current),
        }
        for account in accounts
    ]


def _parse_security(security: Any) -> dict[str, Any]:
    return {
        "security_id": security.security_id,
        "institution_security_id": security.institution_security_id,
        "institution_id": security.institution_id,
        "name": security.name,
        "ticker_symbol": security.ticker_symbol,
        "security_type": _value(security.type) if security.type else None,
        "close_price": _decimal(security.close_price),
        "close_price_as_of": security.close_price_as_of,
        "iso_currency_code": security.iso_currency_code,
        "unofficial_currency_code": security.unofficial_currency_code,
        "raw": _json_value(security),
    }


def _parse_holding(holding: Any, plaid_item_id: uuid.UUID) -> dict[str, Any]:
    return {
        "plaid_item_id": plaid_item_id,
        "account_id": holding.account_id,
        "security_id": holding.security_id,
        "quantity": _decimal(holding.quantity) or Decimal("0"),
        "institution_price": _decimal(holding.institution_price) or Decimal("0"),
        "institution_price_as_of": holding.institution_price_as_of,
        "institution_value": _decimal(holding.institution_value) or Decimal("0"),
        "cost_basis": _decimal(holding.cost_basis),
        "iso_currency_code": holding.iso_currency_code,
        "unofficial_currency_code": holding.unofficial_currency_code,
        "raw": _json_value(holding),
    }


def _parse_transaction(transaction: Any, plaid_item_id: uuid.UUID) -> dict[str, Any]:
    return {
        "investment_transaction_id": transaction.investment_transaction_id,
        "plaid_item_id": plaid_item_id,
        "account_id": transaction.account_id,
        "security_id": transaction.security_id,
        "cancel_transaction_id": transaction.cancel_transaction_id,
        "date": transaction.date,
        "name": transaction.name,
        "amount": _decimal(transaction.amount) or Decimal("0"),
        "fees": _decimal(transaction.fees),
        "price": _decimal(transaction.price),
        "quantity": _decimal(transaction.quantity),
        "transaction_type": _value(transaction.type) if transaction.type else None,
        "subtype": _value(transaction.subtype) if transaction.subtype else None,
        "iso_currency_code": transaction.iso_currency_code,
        "unofficial_currency_code": transaction.unofficial_currency_code,
        "raw": _json_value(transaction),
    }


async def sync_investments_for_access_token(
    *,
    access_token: str,
    plaid_item_id: uuid.UUID,
    session: AsyncSession,
    include_transactions: bool = True,
    async_update: bool = False,
) -> InvestmentsSyncResult:
    """Fetch and persist Investments data using an already-decrypted token."""
    client = get_plaid_client()
    investments_repo = InvestmentsRepo(session)
    accounts_repo = AccountsRepo(session)

    try:
        holdings_response = client.investments_holdings_get(
            InvestmentsHoldingsGetRequest(access_token=access_token)
        )
        accounts = _parse_accounts(list(holdings_response.accounts or []))
        securities = [
            _parse_security(security)
            for security in list(holdings_response.securities or [])
        ]
        holdings = [
            _parse_holding(holding, plaid_item_id)
            for holding in list(holdings_response.holdings or [])
        ]

        await accounts_repo.bulk_upsert(plaid_item_id, accounts)
        await investments_repo.upsert_securities(securities)
        await investments_repo.replace_holdings(plaid_item_id, holdings)
        await investments_repo.upsert_holding_snapshots(holdings, date.today())

        transactions_added = 0
        transactions_updated = 0
        transactions_ready = not include_transactions

        if include_transactions:
            start_date = date.today() - timedelta(days=TRANSACTION_HISTORY_DAYS)
            end_date = date.today()
            offset = 0
            while True:
                options = InvestmentsTransactionsGetRequestOptions(
                    count=TRANSACTION_PAGE_SIZE,
                    offset=offset,
                    async_update=async_update,
                )
                transaction_response = client.investments_transactions_get(
                    InvestmentsTransactionsGetRequest(
                        access_token=access_token,
                        start_date=start_date,
                        end_date=end_date,
                        options=options,
                    )
                )
                page_securities = [
                    _parse_security(security)
                    for security in list(transaction_response.securities or [])
                ]
                await investments_repo.upsert_securities(page_securities)
                page_transactions = [
                    _parse_transaction(transaction, plaid_item_id)
                    for transaction in list(
                        transaction_response.investment_transactions or []
                    )
                ]
                added, updated = await investments_repo.upsert_transactions(
                    page_transactions
                )
                transactions_added += added
                transactions_updated += updated
                offset += len(page_transactions)
                if not page_transactions:
                    break
                if offset >= transaction_response.total_investment_transactions:
                    break
            transactions_ready = True

        await session.flush()
        logger.info(
            "Synced investment data",
            plaid_item_id=str(plaid_item_id),
            holdings=len(holdings),
            transactions_added=transactions_added,
            transactions_updated=transactions_updated,
        )
        return InvestmentsSyncResult(
            accounts_updated=len(accounts),
            securities_updated=len(securities),
            holdings_updated=len(holdings),
            transactions_added=transactions_added,
            transactions_updated=transactions_updated,
            transactions_ready=transactions_ready,
        )
    except ApiException as exc:
        raise PlaidError(
            message=f"Failed to fetch investments: {exc.reason}", status=exc.status
        ) from exc


async def sync_investments(
    plaid_item_id: uuid.UUID,
    *,
    include_transactions: bool = True,
    async_update: bool = False,
) -> InvestmentsSyncResult:
    """Synchronize one stored Plaid Item that has Investments enabled."""
    settings = get_settings()
    encryptor = TokenEncryption(settings.app_token_enc_key)

    async with get_async_session() as session:
        item = await ItemsRepo(session).get_by_id(plaid_item_id)
        if item is None:
            raise ValueError(f"Item {plaid_item_id} not found")
        if "investments" not in item.products:
            raise ValueError(f"Item {plaid_item_id} does not have Investments enabled")

        return await sync_investments_for_access_token(
            access_token=encryptor.decrypt(item.access_token_enc),
            plaid_item_id=plaid_item_id,
            session=session,
            include_transactions=include_transactions,
            async_update=async_update,
        )
