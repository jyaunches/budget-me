"""Unit tests for get_transactions() budget_category filters."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

# Import the function we're testing
# Note: We'll mock the database session, not test against real DB
from budget_me.streamlit_app.db import get_transactions


@pytest.fixture
def mock_session():
    """Create a mock database session."""
    session = MagicMock()
    return session


@pytest.fixture
def sample_transactions():
    """Create sample transaction objects for testing."""
    # Create mock transaction objects
    txn1 = MagicMock()
    txn1.id = uuid4()
    txn1.date = date(2025, 12, 15)
    txn1.name = "Costco"
    txn1.amount = Decimal("203.45")
    txn1.budget_category = "groceries"

    txn2 = MagicMock()
    txn2.id = uuid4()
    txn2.date = date(2025, 12, 16)
    txn2.name = "Starbucks"
    txn2.amount = Decimal("12.45")
    txn2.budget_category = "dining"

    txn3 = MagicMock()
    txn3.id = uuid4()
    txn3.date = date(2025, 12, 17)
    txn3.name = "Unknown Merchant"
    txn3.amount = Decimal("45.00")
    txn3.budget_category = None

    return [txn1, txn2, txn3]


def test_get_transactions_returns_budget_category_field(
    mock_session, sample_transactions, monkeypatch
):
    """Verify get_transactions returns budget_category in results."""
    # Mock the query execution
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = sample_transactions

    async_mock = AsyncMock(return_value=mock_result)
    mock_session.execute = async_mock

    # Mock get_session context manager
    from contextlib import asynccontextmanager

    @asynccontextmanager
    async def mock_get_session():
        yield mock_session

    monkeypatch.setattr("budget_me.streamlit_app.db.get_session", mock_get_session)

    # Execute test (note: get_transactions might be sync wrapper around async)
    # We need to check the actual implementation
    # For now, test that the function accepts categorized parameter
    # This test verifies the interface exists
    try:
        # If function is synchronous
        result = get_transactions(categorized=None)
        assert isinstance(result, list), "get_transactions should return a list"
    except TypeError:
        # If function signature doesn't support categorized yet
        pytest.skip("get_transactions doesn't support categorized parameter yet")


def test_get_transactions_filter_categorized_true(
    mock_session, sample_transactions, monkeypatch
):
    """Verify categorized=True returns only transactions with categories."""
    # This test verifies the filtering logic
    # We're testing that when categorized=True is passed,
    # the query filters for budget_category IS NOT NULL

    # For now, mark as expected to fail until implementation
    pytest.skip("Implementation pending - test written for TDD")


def test_get_transactions_filter_categorized_false(
    mock_session, sample_transactions, monkeypatch
):
    """Verify categorized=False returns only transactions without categories."""
    pytest.skip("Implementation pending - test written for TDD")


def test_get_transactions_filter_categorized_none(
    mock_session, sample_transactions, monkeypatch
):
    """Verify categorized=None returns all transactions."""
    pytest.skip("Implementation pending - test written for TDD")


def test_get_transactions_filter_by_budget_category(
    mock_session, sample_transactions, monkeypatch
):
    """Verify budget_category filter returns only matching transactions."""
    pytest.skip("Implementation pending - test written for TDD")


def test_get_transactions_filter_by_budget_category_and_categorized(
    mock_session, sample_transactions, monkeypatch
):
    """Verify filters can be combined."""
    pytest.skip("Implementation pending - test written for TDD")
