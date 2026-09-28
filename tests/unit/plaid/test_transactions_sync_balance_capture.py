"""Unit tests for balance snapshot capture during transaction sync."""

from datetime import date
from uuid import uuid4

import pytest

from budget_me.plaid.transactions_sync import _refresh_accounts


@pytest.mark.asyncio
async def test_refresh_accounts_stores_balance_snapshot(mocker):
    """Test that _refresh_accounts creates balance snapshots for each account."""
    # Mock Plaid client
    mock_client = mocker.MagicMock()
    mock_account = mocker.MagicMock()
    mock_account.account_id = "plaid_acc_1"
    mock_account.name = "Checking"
    mock_account.type = mocker.MagicMock(value="depository")
    mock_account.subtype = mocker.MagicMock(value="checking")
    mock_account.mask = "1234"
    mock_account.balances = mocker.MagicMock()
    mock_account.balances.current = 1000.50
    mock_account.balances.available = 950.25

    mock_response = mocker.MagicMock()
    mock_response.accounts = [mock_account]
    mock_client.accounts_get.return_value = mock_response

    mocker.patch(
        "budget_me.plaid.transactions_sync.get_plaid_client", return_value=mock_client
    )

    # Mock AccountsRepo
    mock_accounts_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountsRepo",
        return_value=mock_accounts_repo,
    )

    # Mock AccountBalanceSnapshotRepo - this should be called
    mock_snapshot_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountBalanceSnapshotRepo",
        return_value=mock_snapshot_repo,
    )

    # Mock session
    session = mocker.AsyncMock()

    # Call the function
    await _refresh_accounts("test_token", uuid4(), session)

    # Verify balance snapshot was created
    mock_snapshot_repo.upsert.assert_called_once_with(
        account_id="plaid_acc_1",
        snapshot_date=date.today(),
        balance_current=1000.50,
        balance_available=950.25,
    )


@pytest.mark.asyncio
async def test_refresh_accounts_updates_existing_snapshot_same_day(mocker):
    """Test that running sync twice on same day upserts (not duplicates) balance snapshot."""
    # Mock Plaid client
    mock_client = mocker.MagicMock()
    mock_account = mocker.MagicMock()
    mock_account.account_id = "plaid_acc_1"
    mock_account.name = "Checking"
    mock_account.type = mocker.MagicMock(value="depository")
    mock_account.subtype = mocker.MagicMock(value="checking")
    mock_account.mask = "1234"
    mock_account.balances = mocker.MagicMock()
    mock_account.balances.current = 1000.00
    mock_account.balances.available = 950.00

    mock_response = mocker.MagicMock()
    mock_response.accounts = [mock_account]
    mock_client.accounts_get.return_value = mock_response

    mocker.patch(
        "budget_me.plaid.transactions_sync.get_plaid_client", return_value=mock_client
    )

    # Mock repos
    mock_accounts_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountsRepo",
        return_value=mock_accounts_repo,
    )

    mock_snapshot_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountBalanceSnapshotRepo",
        return_value=mock_snapshot_repo,
    )

    session = mocker.AsyncMock()
    item_id = uuid4()

    # First sync
    await _refresh_accounts("test_token", item_id, session)

    # Update balance
    mock_account.balances.current = 1100.00
    mock_account.balances.available = 1050.00

    # Second sync same day
    await _refresh_accounts("test_token", item_id, session)

    # Verify upsert was called twice (once for each sync)
    assert mock_snapshot_repo.upsert.call_count == 2
    # Verify the second call had updated balance
    mock_snapshot_repo.upsert.assert_called_with(
        account_id="plaid_acc_1",
        snapshot_date=date.today(),
        balance_current=1100.00,
        balance_available=1050.00,
    )


@pytest.mark.asyncio
async def test_balance_snapshot_has_correct_values(mocker):
    """Test that balance snapshot stores exact values from Plaid response."""
    # Mock Plaid client
    mock_client = mocker.MagicMock()
    mock_account = mocker.MagicMock()
    mock_account.account_id = "plaid_acc_1"
    mock_account.name = "Savings"
    mock_account.type = mocker.MagicMock(value="depository")
    mock_account.subtype = mocker.MagicMock(value="savings")
    mock_account.mask = "5678"
    mock_account.balances = mocker.MagicMock()
    mock_account.balances.current = 12345.67
    mock_account.balances.available = 11999.99

    mock_response = mocker.MagicMock()
    mock_response.accounts = [mock_account]
    mock_client.accounts_get.return_value = mock_response

    mocker.patch(
        "budget_me.plaid.transactions_sync.get_plaid_client", return_value=mock_client
    )

    # Mock repos
    mock_accounts_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountsRepo",
        return_value=mock_accounts_repo,
    )

    mock_snapshot_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountBalanceSnapshotRepo",
        return_value=mock_snapshot_repo,
    )

    session = mocker.AsyncMock()

    await _refresh_accounts("test_token", uuid4(), session)

    # Verify exact balance values were passed to snapshot repo
    mock_snapshot_repo.upsert.assert_called_once_with(
        account_id="plaid_acc_1",
        snapshot_date=date.today(),
        balance_current=12345.67,
        balance_available=11999.99,
    )


@pytest.mark.asyncio
async def test_refresh_accounts_handles_multiple_accounts(mocker):
    """Test that balance snapshots are created for all accounts in Plaid response."""
    # Mock Plaid client
    mock_client = mocker.MagicMock()

    # Create 3 mock accounts
    mock_accounts = []
    for i, (acc_id, balance, name) in enumerate(
        [
            ("plaid_acc_1", 1000.00, "Checking"),
            ("plaid_acc_2", 5000.00, "Savings"),
            ("plaid_acc_3", -2500.00, "Credit Card"),
        ]
    ):
        acc = mocker.MagicMock()
        acc.account_id = acc_id
        acc.name = name
        acc.type = mocker.MagicMock(value="depository" if i < 2 else "credit")
        acc.subtype = mocker.MagicMock(
            value=("checking" if i == 0 else "savings" if i == 1 else "credit_card")
        )
        acc.mask = f"{1234 + i * 2000}"
        acc.balances = mocker.MagicMock()
        acc.balances.current = balance
        acc.balances.available = balance - 50 if i < 2 else 7500.00
        mock_accounts.append(acc)

    mock_response = mocker.MagicMock()
    mock_response.accounts = mock_accounts
    mock_client.accounts_get.return_value = mock_response

    mocker.patch(
        "budget_me.plaid.transactions_sync.get_plaid_client", return_value=mock_client
    )

    # Mock repos
    mock_accounts_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountsRepo",
        return_value=mock_accounts_repo,
    )

    mock_snapshot_repo = mocker.AsyncMock()
    mocker.patch(
        "budget_me.plaid.transactions_sync.AccountBalanceSnapshotRepo",
        return_value=mock_snapshot_repo,
    )

    session = mocker.AsyncMock()

    await _refresh_accounts("test_token", uuid4(), session)

    # Verify all 3 accounts got balance snapshots
    assert mock_snapshot_repo.upsert.call_count == 3

    # Verify the calls were made with correct account_ids and balances
    calls = mock_snapshot_repo.upsert.call_args_list
    account_ids = {call.kwargs["account_id"] for call in calls}
    assert account_ids == {"plaid_acc_1", "plaid_acc_2", "plaid_acc_3"}

    # Verify balances
    balances = {call.kwargs["balance_current"] for call in calls}
    assert balances == {1000.00, 5000.00, -2500.00}
