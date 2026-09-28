"""Unit tests for liabilities CLI command."""

import json
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from budget_me.cli.main import app
from budget_me.db.models.account import Account
from budget_me.db.models.credit_liability import (
    AprType,
    CreditLiability,
    CreditLiabilityApr,
)


class TestLiabilitiesCommand:
    """Tests for budget-me liabilities command."""

    @pytest.fixture(autouse=True)
    def mock_database_session(self, mocker):
        """Keep command tests independent of local database configuration."""
        session = mocker.AsyncMock()

        @asynccontextmanager
        async def fake_session():
            yield session

        mocker.patch(
            "budget_me.cli.commands.liabilities.get_async_session", fake_session
        )

    @pytest.fixture
    def runner(self):
        """Click CLI runner."""
        return CliRunner()

    @pytest.fixture
    def sample_account(self):
        """Sample account for testing."""
        return Account(
            id=uuid4(),
            plaid_item_id=uuid4(),
            account_id="acc_example_001",
            name="Example Rewards",
            mask="0001",
            type="credit",
            subtype="credit card",
            balance_current=Decimal("123.45"),
        )

    @pytest.fixture
    def sample_liability(self, sample_account):
        """Sample credit liability with APRs."""
        liability = CreditLiability(
            id=uuid4(),
            plaid_item_id=sample_account.plaid_item_id,
            account_id=sample_account.account_id,
            is_overdue=False,
            last_payment_amount=Decimal("250.00"),
            last_payment_date=date(2025, 12, 15),
            last_statement_balance=Decimal("173.45"),
            last_statement_issue_date=date(2025, 12, 1),
            minimum_payment_amount=Decimal("25.00"),
            next_payment_due_date=date(2026, 1, 15),
        )
        liability.account = sample_account
        liability.aprs = [
            CreditLiabilityApr(
                id=uuid4(),
                credit_liability_id=liability.id,
                apr_type=AprType.PURCHASE.value,
                apr_percentage=Decimal("24.99"),
                balance_subject_to_apr=Decimal("123.45"),
            ),
            CreditLiabilityApr(
                id=uuid4(),
                credit_liability_id=liability.id,
                apr_type=AprType.BALANCE_TRANSFER.value,
                apr_percentage=Decimal("0.00"),
                balance_subject_to_apr=Decimal("1000.00"),
            ),
        ]
        return liability

    def test_liabilities_command_displays_table_format(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command displays Rich table with accounts and APRs."""
        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        # Mock async method
        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities"])

        assert result.exit_code == 0
        assert "Example Rewards" in result.output
        assert "0001" in result.output
        assert "24.99%" in result.output
        assert "Balance Transfer" in result.output

    def test_liabilities_command_shows_payment_info(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command shows payment information section."""
        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities"])

        assert result.exit_code == 0
        assert "Payment Info" in result.output or "payment" in result.output.lower()
        assert "$25.00" in result.output  # minimum payment
        assert "2026-01-15" in result.output or "Jan" in result.output  # due date

    def test_liabilities_command_highlights_overdue_status(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command highlights overdue payments."""
        # Make liability overdue
        sample_liability.is_overdue = True

        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities"])

        assert result.exit_code == 0
        # Should contain some overdue indicator
        assert "OVERDUE" in result.output.upper() or "overdue" in result.output.lower()

    def test_liabilities_command_json_output_valid(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command outputs valid JSON with --json flag."""
        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities", "--json"])

        assert result.exit_code == 0
        # Should be valid JSON
        data = json.loads(result.output)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_liabilities_command_json_includes_all_fields(
        self, runner, sample_liability, mocker
    ):
        """JSON output includes all liability and APR fields."""
        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities", "--json"])

        assert result.exit_code == 0
        data = json.loads(result.output)
        liability = data[0]

        # Check key fields present
        assert "account_name" in liability
        assert "account_mask" in liability
        assert "balance" in liability
        assert "aprs" in liability
        assert "minimum_payment_amount" in liability
        assert "next_payment_due_date" in liability
        assert "is_overdue" in liability

        # Check APR structure
        assert len(liability["aprs"]) == 2
        apr = liability["aprs"][0]
        assert "apr_type" in apr
        assert "apr_percentage" in apr
        assert "balance_subject_to_apr" in apr

    def test_liabilities_command_no_data_shows_helpful_message(self, runner, mocker):
        """Liabilities command shows helpful message when no data exists."""
        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return []

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities"])

        assert result.exit_code == 0
        # Should suggest using add-liabilities
        assert (
            "add-liabilities" in result.output.lower()
            or "no liabilities" in result.output.lower()
        )

    def test_liabilities_command_filters_by_account_name(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command filters by account name."""
        # Create second account
        other_account = Account(
            id=uuid4(),
            plaid_item_id=uuid4(),
            account_id="acc_example_002",
            name="Example Cashback",
            mask="0002",
            type="credit",
            subtype="credit card",
            balance_current=Decimal("2345.67"),
        )
        other_liability = CreditLiability(
            id=uuid4(),
            plaid_item_id=other_account.plaid_item_id,
            account_id=other_account.account_id,
            is_overdue=False,
            minimum_payment_amount=Decimal("450.00"),
            next_payment_due_date=date(2026, 1, 10),
        )
        other_liability.account = other_account
        other_liability.aprs = []

        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability, other_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities", "--account", "Example Rewards"])

        assert result.exit_code == 0
        assert "Example Rewards" in result.output
        assert "Example Cashback" not in result.output

    def test_liabilities_command_filters_by_account_mask(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command filters by account mask (last 4 digits)."""
        # Create second account
        other_account = Account(
            id=uuid4(),
            plaid_item_id=uuid4(),
            account_id="acc_example_002",
            name="Example Cashback",
            mask="0002",
            type="credit",
            subtype="credit card",
            balance_current=Decimal("2345.67"),
        )
        other_liability = CreditLiability(
            id=uuid4(),
            plaid_item_id=other_account.plaid_item_id,
            account_id=other_account.account_id,
            is_overdue=False,
        )
        other_liability.account = other_account
        other_liability.aprs = []

        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability, other_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities", "--account", "0001"])

        assert result.exit_code == 0
        assert "Example Rewards" in result.output or "0001" in result.output
        assert "0002" not in result.output

    def test_liabilities_command_shows_promotional_apr_indicator(
        self, runner, sample_liability, mocker
    ):
        """Liabilities command indicates promotional APR rates."""
        # Add promotional APR
        promo_apr = CreditLiabilityApr(
            id=uuid4(),
            credit_liability_id=sample_liability.id,
            apr_type=AprType.SPECIAL.value,
            apr_percentage=Decimal("0.00"),
            balance_subject_to_apr=Decimal("1000.00"),
        )
        sample_liability.aprs.append(promo_apr)

        mock_repo = mocker.patch("budget_me.cli.commands.liabilities.LiabilitiesRepo")
        mock_repo_instance = MagicMock()
        mock_repo.return_value = mock_repo_instance

        async def mock_get_all_with_details():
            return [sample_liability]

        mock_repo_instance.get_all_with_details = mock_get_all_with_details

        result = runner.invoke(app, ["liabilities"])

        assert result.exit_code == 0
        # Should show promotional rate with special indicator
        assert (
            "special" in result.output.lower()
            or "promo" in result.output.lower()
            or "↳" in result.output
        )

    def test_liabilities_command_appears_in_main_help(self, runner):
        """Liabilities command appears in main CLI help."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "liabilities" in result.output.lower()
