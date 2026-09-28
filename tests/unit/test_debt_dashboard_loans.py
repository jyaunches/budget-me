"""Unit tests for Debt Dashboard - Loan Queries (Phase 1)."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from budget_me.db.models.loan_details import LoanType
from budget_me.streamlit_app.db import get_loans_with_interest


class TestGetLoansWithInterest:
    """Tests for get_loans_with_interest database query."""

    def test_get_loans_with_interest_returns_loan_data(self):
        """Returns list with loan data including balance, rate, payment, calculated interest."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock result rows (mortgage and auto loan)
        mock_rows = [
            Mock(
                loan_type=LoanType.MORTGAGE,
                account_name="Test Mortgage",
                mask="0001",
                balance=Decimal("123456.78"),
                interest_rate=Decimal("6.25"),
                monthly_payment=Decimal("987.65"),
                maturity_date=date(2050, 1, 1),
                lender_name="Example Mortgage",
                collateral_description=None,
            ),
            Mock(
                loan_type=LoanType.AUTO,
                account_name="Test Auto Loan",  # display_name
                mask="0002",
                balance=Decimal("23456.78"),
                interest_rate=Decimal("3.5"),
                monthly_payment=Decimal("456.78"),
                maturity_date=date(2031, 1, 1),
                lender_name="Example Auto Lender",
                collateral_description="Example Vehicle",
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_loans_with_interest
        loans = get_loans_with_interest(mock_session)

        # Assert: Returns 2 loans
        assert len(loans) == 2

        # Assert: Mortgage data is correct
        mortgage = next(
            loan for loan in loans if loan["loan_type"] == LoanType.MORTGAGE
        )
        assert mortgage["account_name"] == "Test Mortgage"
        assert mortgage["mask"] == "0001"
        assert mortgage["balance"] == 123456.78
        assert mortgage["interest_rate"] == 6.25
        assert mortgage["monthly_payment"] == 987.65
        assert mortgage["maturity_date"] == date(2050, 1, 1)
        assert mortgage["lender_name"] == "Example Mortgage"
        assert "monthly_interest" in mortgage

        # Assert: Auto loan data is correct
        auto = next(loan for loan in loans if loan["loan_type"] == LoanType.AUTO)
        assert auto["account_name"] == "Test Auto Loan"
        assert auto["mask"] == "0002"
        assert auto["balance"] == 23456.78
        assert auto["interest_rate"] == 3.5
        assert auto["monthly_payment"] == 456.78
        assert auto["maturity_date"] == date(2031, 1, 1)
        assert auto["collateral_description"] == "Example Vehicle"
        assert "monthly_interest" in auto

    def test_get_loans_with_interest_calculates_monthly_interest(self):
        """Calculates monthly interest correctly: (balance × rate / 100) / 12."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock result with known balance and rate
        mock_rows = [
            Mock(
                loan_type=LoanType.MORTGAGE,
                account_name="Test Loan",
                mask="1234",
                balance=Decimal("100000.00"),  # $100,000
                interest_rate=Decimal("6.0"),  # 6%
                monthly_payment=Decimal("600.00"),
                maturity_date=date(2050, 1, 1),
                lender_name="Test Bank",
                collateral_description=None,
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_loans_with_interest
        loans = get_loans_with_interest(mock_session)

        # Assert: Interest calculation is correct
        # (100000 * 6.0 / 100) / 12 = 500.00
        assert len(loans) == 1
        assert loans[0]["monthly_interest"] == 500.00

    def test_get_loans_with_interest_handles_null_balance(self):
        """Handles null balance_current by treating it as zero."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock result with zero balance (COALESCE result)
        mock_rows = [
            Mock(
                loan_type=LoanType.AUTO,
                account_name="Test Loan",
                mask="1234",
                balance=0,  # COALESCE(NULL, 0) = 0
                interest_rate=Decimal("5.0"),
                monthly_payment=Decimal("400.00"),
                maturity_date=date(2030, 1, 1),
                lender_name="Test Bank",
                collateral_description=None,
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_loans_with_interest
        loans = get_loans_with_interest(mock_session)

        # Assert: Balance and interest are zero
        assert len(loans) == 1
        assert loans[0]["balance"] == 0.0
        assert loans[0]["monthly_interest"] == 0.0
