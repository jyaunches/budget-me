"""Unit tests for parsing and orchestrating Plaid Investments responses."""

from datetime import date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest


def _security():
    return SimpleNamespace(
        security_id="security-1",
        institution_security_id="provider-security-1",
        institution_id="ins_test",
        name="Example Fund",
        ticker_symbol="EXMPL",
        type="mutual fund",
        close_price=12.34,
        close_price_as_of=date(2026, 10, 5),
        iso_currency_code="USD",
        unofficial_currency_code=None,
        to_dict=lambda: {"security_id": "security-1"},
    )


def _account():
    return SimpleNamespace(
        account_id="account-1",
        name="Retirement",
        type="investment",
        subtype="401k",
        mask="1234",
        balances=SimpleNamespace(available=None, current=1000),
    )


def _holding():
    return SimpleNamespace(
        account_id="account-1",
        security_id="security-1",
        quantity=10,
        institution_price=100,
        institution_price_as_of=datetime(2026, 10, 5),
        institution_value=1000,
        cost_basis=800,
        iso_currency_code="USD",
        unofficial_currency_code=None,
        to_dict=lambda: {"account_id": "account-1"},
    )


@pytest.mark.asyncio
async def test_holdings_sync_replaces_current_state_and_creates_snapshot(mocker):
    from budget_me.plaid.investments_sync import sync_investments_for_access_token

    client = mocker.MagicMock()
    client.investments_holdings_get.return_value = SimpleNamespace(
        accounts=[_account()], securities=[_security()], holdings=[_holding()]
    )
    mocker.patch(
        "budget_me.plaid.investments_sync.get_plaid_client", return_value=client
    )
    accounts_repo = mocker.MagicMock()
    accounts_repo.bulk_upsert = mocker.AsyncMock()
    investments_repo = mocker.MagicMock()
    investments_repo.upsert_securities = mocker.AsyncMock(return_value=1)
    investments_repo.replace_holdings = mocker.AsyncMock(return_value=1)
    investments_repo.upsert_holding_snapshots = mocker.AsyncMock(return_value=1)
    mocker.patch(
        "budget_me.plaid.investments_sync.AccountsRepo",
        return_value=accounts_repo,
    )
    mocker.patch(
        "budget_me.plaid.investments_sync.InvestmentsRepo",
        return_value=investments_repo,
    )
    session = mocker.AsyncMock()
    item_id = uuid4()

    result = await sync_investments_for_access_token(
        access_token="access",
        plaid_item_id=item_id,
        session=session,
        include_transactions=False,
    )

    assert result.holdings_updated == 1
    holdings = investments_repo.replace_holdings.await_args.args[1]
    assert holdings[0]["institution_value"] == Decimal("1000")
    assert holdings[0]["cost_basis"] == Decimal("800")
    investments_repo.upsert_holding_snapshots.assert_awaited_once()
    client.investments_transactions_get.assert_not_called()


def test_investment_transaction_parsing_preserves_contribution_fields():
    from budget_me.plaid.investments_sync import _parse_transaction

    transaction = SimpleNamespace(
        investment_transaction_id="investment-tx-1",
        account_id="account-1",
        security_id=None,
        cancel_transaction_id=None,
        date=date(2026, 10, 1),
        name="401K CONTRIBUTION",
        amount=-500,
        fees=0,
        price=0,
        quantity=0,
        type="cash",
        subtype="contribution",
        iso_currency_code="USD",
        unofficial_currency_code=None,
        to_dict=lambda: {"subtype": "contribution"},
    )

    parsed = _parse_transaction(transaction, uuid4())

    assert parsed["amount"] == Decimal("-500")
    assert parsed["transaction_type"] == "cash"
    assert parsed["subtype"] == "contribution"
