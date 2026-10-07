"""Unit tests for Debt Dashboard - Credit Card Interest Queries (Phase 2)."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import Mock

from budget_me.streamlit_app.db import (
    get_cc_calculated_interest,
    get_cc_interest_from_transactions,
)


class TestGetCCCalculatedInterest:
    """Tests for get_cc_calculated_interest database query."""

    def test_get_cc_calculated_interest_pay_in_full_is_zero(self):
        """Credit cards with pay_in_full strategy have zero calculated interest."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock credit card with pay_in_full strategy and 20% APR
        mock_rows = [
            Mock(
                account_name="Example Card A",
                mask="0001",
                balance_current=Decimal("1500.00"),
                payment_strategy="pay_in_full",
                balance_updated_at=datetime(2026, 10, 5, tzinfo=UTC),
                # APRs would exist but aren't used for calculation
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_cc_calculated_interest
        cards = get_cc_calculated_interest(mock_session)

        # Assert: calculated_interest is zero (grace period)
        assert len(cards) == 1
        assert cards[0]["calculated_interest"] == 0.0
        assert cards[0]["payment_strategy"] == "pay_in_full"

    def test_get_cc_calculated_interest_promotional_paydown(self):
        """Promotional paydown cards calculate interest only on positive APR balances."""
        # Mock session
        mock_session = Mock()

        # Mock account query result
        mock_account_result = Mock()
        mock_account_rows = [
            Mock(
                account_id="promo_card_1",
                account_name="Example Card B",
                mask="0002",
                balance_current=Decimal("15000.00"),
                payment_strategy="promotional_paydown",
                balance_updated_at=datetime(2026, 10, 5, tzinfo=UTC),
            ),
        ]
        mock_account_result.fetchall.return_value = mock_account_rows

        # Mock APR query result for this card
        mock_apr_result = Mock()
        mock_apr_rows = [
            Mock(
                apr_percentage=Decimal("0.00"),
                balance_subject_to_apr=Decimal("10000.00"),
            ),
            Mock(
                apr_percentage=Decimal("18.00"),
                balance_subject_to_apr=Decimal("5000.00"),
            ),
        ]
        mock_apr_result.fetchall.return_value = mock_apr_rows

        # Mock session.execute to return different results based on call order
        mock_session.execute.side_effect = [mock_account_result, mock_apr_result]

        # Execute: Call get_cc_calculated_interest
        cards = get_cc_calculated_interest(mock_session)

        # Assert: Interest only on 18% balance
        # (5000 * 18 / 100) / 12 = 75.00
        assert len(cards) == 1
        assert cards[0]["calculated_interest"] == 75.00
        assert cards[0]["account_name"] == "Example Card B"
        assert cards[0]["allocation_reconciled"] is True

    def test_get_cc_calculated_interest_multiple_positive_aprs(self):
        """Correctly sums interest from multiple positive APR rates."""
        # Mock session
        mock_session = Mock()

        # Mock account query result
        mock_account_result = Mock()
        mock_account_rows = [
            Mock(
                account_id="multi_apr_card",
                account_name="Multi APR Card",
                mask="0003",
                balance_current=Decimal("5000.00"),
                payment_strategy="promotional_paydown",
                balance_updated_at=datetime(2026, 10, 5, tzinfo=UTC),
            ),
        ]
        mock_account_result.fetchall.return_value = mock_account_rows

        # Mock APR query result - two positive rates
        mock_apr_result = Mock()
        mock_apr_rows = [
            Mock(
                apr_percentage=Decimal("15.00"),
                balance_subject_to_apr=Decimal("3000.00"),
            ),
            Mock(
                apr_percentage=Decimal("20.00"),
                balance_subject_to_apr=Decimal("2000.00"),
            ),
        ]
        mock_apr_result.fetchall.return_value = mock_apr_rows

        mock_session.execute.side_effect = [mock_account_result, mock_apr_result]

        # Execute: Call get_cc_calculated_interest
        cards = get_cc_calculated_interest(mock_session)

        # Assert: Sum of both interests
        # (3000 * 15 / 100 / 12) + (2000 * 20 / 100 / 12)
        # = 37.50 + 33.33 = 70.83
        assert len(cards) == 1
        assert abs(cards[0]["calculated_interest"] - 70.83) < 0.01  # Float precision

    def test_get_cc_calculated_interest_ignores_apr_without_balance(self):
        """APR entries without a balance do not crash the debt dashboard."""
        mock_session = Mock()

        mock_account_result = Mock()
        mock_account_result.fetchall.return_value = [
            Mock(
                account_id="card_with_missing_apr_balance",
                account_name="Card With Incomplete APR Data",
                mask="0004",
                balance_current=Decimal("1000.00"),
                payment_strategy="promotional_paydown",
                balance_updated_at=datetime(2026, 10, 5, tzinfo=UTC),
            )
        ]

        mock_apr_result = Mock()
        mock_apr_result.fetchall.return_value = [
            Mock(
                apr_percentage=Decimal("29.99"),
                balance_subject_to_apr=None,
            )
        ]

        mock_session.execute.side_effect = [mock_account_result, mock_apr_result]

        cards = get_cc_calculated_interest(mock_session)

        assert len(cards) == 1
        assert cards[0]["calculated_interest"] is None
        assert cards[0]["allocation_reconciled"] is False

    def test_get_cc_calculated_interest_withholds_stale_apr_allocation(self):
        """Interest is not presented as exact when APR buckets exceed the balance."""
        mock_session = Mock()

        mock_account_result = Mock()
        mock_account_result.fetchall.return_value = [
            Mock(
                account_id="stale_promo_card",
                account_name="Stale Promo Card",
                mask="0005",
                balance_current=Decimal("1000.00"),
                payment_strategy="promotional_paydown",
                balance_updated_at=datetime(2026, 10, 5, tzinfo=UTC),
            )
        ]
        mock_apr_result = Mock()
        mock_apr_result.fetchall.return_value = [
            Mock(
                apr_percentage=Decimal("0.00"),
                balance_subject_to_apr=Decimal("1200.00"),
            ),
            Mock(
                apr_percentage=Decimal("18.00"),
                balance_subject_to_apr=Decimal("300.00"),
            ),
        ]
        mock_session.execute.side_effect = [mock_account_result, mock_apr_result]

        cards = get_cc_calculated_interest(mock_session)

        assert cards[0]["apr_balance_total"] == 1500.0
        assert cards[0]["allocation_difference"] == -500.0
        assert cards[0]["allocation_reconciled"] is False
        assert cards[0]["calculated_interest"] is None


class TestGetCCInterestFromTransactions:
    """Tests for get_cc_interest_from_transactions database query."""

    def test_get_cc_interest_from_transactions_groups_by_month(self):
        """Groups interest charges by month and account."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock transactions in Dec and Nov
        mock_rows = [
            Mock(
                year_month="2025-12",
                account_name="Example Card A",
                total_interest=Decimal("100.50"),
            ),
            Mock(
                year_month="2025-11",
                account_name="Example Card A",
                total_interest=Decimal("150.75"),
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_cc_interest_from_transactions
        interest_by_month = get_cc_interest_from_transactions(mock_session, months=2)

        # Assert: Returns dict grouped by month
        assert "2025-12" in interest_by_month
        assert "2025-11" in interest_by_month
        assert interest_by_month["2025-12"]["Example Card A"] == 100.50
        assert interest_by_month["2025-11"]["Example Card A"] == 150.75

    def test_get_cc_interest_from_transactions_filters_to_credit_cards(self):
        """Only includes interest from credit card accounts, not savings interest."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock: Only credit card interest returned (savings filtered out in SQL)
        mock_rows = [
            Mock(
                year_month="2025-12",
                account_name="Example Card A",
                total_interest=Decimal("50.00"),
            ),
            # Savings account interest would be filtered by SQL WHERE clause
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_cc_interest_from_transactions
        interest_by_month = get_cc_interest_from_transactions(mock_session)

        # Assert: Only credit card interest in results
        assert len(interest_by_month) == 1
        assert "2025-12" in interest_by_month
        assert interest_by_month["2025-12"]["Example Card A"] == 50.00

    def test_get_cc_interest_from_transactions_respects_month_limit(self):
        """Respects the months parameter to limit results."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock: Only 2 months returned (SQL filters by date range)
        mock_rows = [
            Mock(
                year_month="2025-12",
                account_name="Card",
                total_interest=Decimal("100.00"),
            ),
            Mock(
                year_month="2025-11",
                account_name="Card",
                total_interest=Decimal("100.00"),
            ),
            # October would be filtered out by SQL WHERE date >= cutoff
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call with months=2
        interest_by_month = get_cc_interest_from_transactions(mock_session, months=2)

        # Assert: Only 2 months returned
        assert len(interest_by_month) == 2
        assert "2025-12" in interest_by_month
        assert "2025-11" in interest_by_month
        assert "2025-10" not in interest_by_month

    def test_get_cc_interest_from_transactions_multiple_cards_per_month(self):
        """Handles multiple credit cards with interest in the same month."""
        # Mock session
        mock_session = Mock()
        mock_result = Mock()

        # Mock: Multiple cards in same month
        mock_rows = [
            Mock(
                year_month="2025-12",
                account_name="Example Card A",
                total_interest=Decimal("75.00"),
            ),
            Mock(
                year_month="2025-12",
                account_name="Example Card B",
                total_interest=Decimal("150.00"),
            ),
        ]

        mock_result.fetchall.return_value = mock_rows
        mock_session.execute.return_value = mock_result

        # Execute: Call get_cc_interest_from_transactions
        interest_by_month = get_cc_interest_from_transactions(mock_session)

        # Assert: Both cards in same month
        assert len(interest_by_month) == 1
        assert "2025-12" in interest_by_month
        assert interest_by_month["2025-12"]["Example Card A"] == 75.00
        assert interest_by_month["2025-12"]["Example Card B"] == 150.00
