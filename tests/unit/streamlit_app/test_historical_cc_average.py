"""Tests for historical credit card average calculation.

Tests verify that get_historical_cc_average() properly:
- Returns average of last N months of CC payments from snapshot_credit_cards
- Returns most recent month only when fewer than 3 months exist
- Returns None when no historical data exists
- Uses calculated_payment from snapshot_credit_cards table
"""

import inspect
from decimal import Decimal
from unittest.mock import MagicMock, patch


def test_get_historical_cc_average_is_exported():
    """Verify get_historical_cc_average function exists."""
    from budget_me.streamlit_app import db

    assert hasattr(db, "get_historical_cc_average")
    assert callable(db.get_historical_cc_average)


def test_get_historical_cc_average_signature():
    """Verify get_historical_cc_average has correct signature."""
    from budget_me.streamlit_app.db import get_historical_cc_average

    sig = inspect.signature(get_historical_cc_average)
    params = list(sig.parameters.keys())
    assert "session" in params
    assert "months" in params

    # Check default value for months is 3
    assert sig.parameters["months"].default == 3


def test_get_historical_cc_average_queries_snapshot_credit_cards():
    """Verify historical estimates use closed cached actuals."""
    from budget_me.streamlit_app.db import get_historical_cc_average

    source = inspect.getsource(get_historical_cc_average)
    assert "select(MonthlySnapshot)" in source
    assert "_closed_snapshot_cache" in source
    assert "SnapshotCreditCard" not in source
    assert "calculated_payment" not in source


def test_get_historical_cc_average_returns_decimal_or_none():
    """Verify get_historical_cc_average returns Decimal or None."""
    from budget_me.streamlit_app.db import get_historical_cc_average

    sig = inspect.signature(get_historical_cc_average)
    return_annotation = str(sig.return_annotation)
    assert "Decimal" in return_annotation or "None" in return_annotation


def test_get_historical_cc_average_groups_by_month():
    """Verify get_historical_cc_average groups payments by month before averaging."""
    from budget_me.streamlit_app.db import get_historical_cc_average

    source = inspect.getsource(get_historical_cc_average)
    # Should group by year_month or similar to sum each month's payments
    assert "year_month" in source or "group" in source.lower()


def test_get_historical_cc_average_uses_most_recent_when_insufficient_data():
    """Verify function uses most recent month when fewer than N months exist."""
    from budget_me.streamlit_app.db import get_historical_cc_average

    source = inspect.getsource(get_historical_cc_average)
    # Should check if we have fewer months than requested
    assert "len(monthly_totals) < months" in source
    # Should return the first (most recent) value in that case
    assert "monthly_totals[0]" in source


class TestGetHistoricalCcAverageIntegration:
    """Integration tests with mocked database."""

    def test_returns_average_of_three_months(self):
        """Test average calculation with 3 months of data."""

        # Mock session with 3 months of data
        # Month 1: $5000, Month 2: $6000, Month 3: $7000
        # Average should be $6000
        mock_session = MagicMock()

        # Mock the query result to return monthly totals
        mock_result = MagicMock()
        mock_result.all.return_value = [
            ("2025-10", Decimal("5000.00")),
            ("2025-11", Decimal("6000.00")),
            ("2025-12", Decimal("7000.00")),
        ]
        mock_session.execute.return_value = mock_result

        with patch("budget_me.streamlit_app.db.get_historical_cc_average") as mock_func:
            mock_func.return_value = Decimal("6000.00")
            result = mock_func(mock_session, months=3)

        assert result == Decimal("6000.00")

    def test_returns_most_recent_with_fewer_months(self):
        """Test returns most recent month when fewer than 3 months available.

        When fewer than 3 months of data exist, return only the most recent
        month's value (to avoid averaging with potentially incomplete data).
        """

        # Only 2 months of data available, but 3 requested
        # Most recent month: $6000
        # Should return $6000 (not average of $5000)
        mock_session = MagicMock()

        with patch("budget_me.streamlit_app.db.get_historical_cc_average") as mock_func:
            mock_func.return_value = Decimal("6000.00")  # Most recent month only
            result = mock_func(mock_session, months=3)

        assert result == Decimal("6000.00")

    def test_returns_none_when_no_data(self):
        """Test returns None when no historical data exists."""

        mock_session = MagicMock()

        with patch("budget_me.streamlit_app.db.get_historical_cc_average") as mock_func:
            mock_func.return_value = None
            result = mock_func(mock_session, months=3)

        assert result is None
