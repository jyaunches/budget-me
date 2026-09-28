"""Tests for extended AnticipatedItem model with frequency and date bounds."""

from decimal import Decimal

from budget_me.db.models.anticipated_item import (
    AnticipatedItem,
    ItemFrequency,
    ItemType,
)


def test_item_frequency_enum_values():
    """Test that ItemFrequency enum has correct values."""
    assert ItemFrequency.MONTHLY.value == "monthly"
    assert ItemFrequency.QUARTERLY.value == "quarterly"
    assert ItemFrequency.ANNUAL.value == "annual"
    assert ItemFrequency.ONE_TIME.value == "one_time"


def test_anticipated_item_with_date_range():
    """Test creating item with start_month and end_month."""
    item = AnticipatedItem(
        name="Example Expense",
        amount=Decimal("100.00"),
        item_type=ItemType.EXPENSE.value,
        category="Example",
        active=True,
        frequency=ItemFrequency.MONTHLY.value,
        start_month="2099-01",
        end_month="2099-06",
    )
    assert item.frequency == "monthly"
    assert item.start_month == "2099-01"
    assert item.end_month == "2099-06"


def test_anticipated_item_one_time():
    """Test creating one-time item."""
    item = AnticipatedItem(
        name="Example Event",
        amount=Decimal("200.00"),
        item_type=ItemType.EXPENSE.value,
        category="Example",
        active=True,
        frequency=ItemFrequency.ONE_TIME.value,
        start_month="2099-07",
        end_month="2099-07",
    )
    assert item.frequency == "one_time"
    assert item.start_month == "2099-07"
    assert item.end_month == "2099-07"


def test_anticipated_item_quarterly():
    """Test creating quarterly item."""
    item = AnticipatedItem(
        name="Quarterly Insurance",
        amount=Decimal("600.00"),
        item_type=ItemType.EXPENSE.value,
        category="Insurance",
        active=True,
        frequency=ItemFrequency.QUARTERLY.value,
        start_month="2026-01",
    )
    assert item.frequency == "quarterly"
    assert item.start_month == "2026-01"
    assert item.end_month is None


def test_anticipated_item_annual():
    """Test creating annual item."""
    item = AnticipatedItem(
        name="Annual Membership",
        amount=Decimal("200.00"),
        item_type=ItemType.EXPENSE.value,
        category="Subscriptions",
        active=True,
        frequency=ItemFrequency.ANNUAL.value,
        start_month="2026-03",
    )
    assert item.frequency == "annual"
    assert item.start_month == "2026-03"


def test_anticipated_item_date_fields_nullable():
    """Test that start_month and end_month are optional."""
    item = AnticipatedItem(
        name="Example Income",
        amount=Decimal("1000.00"),
        item_type=ItemType.INCOME.value,
        category="Example",
        active=True,
        frequency=ItemFrequency.MONTHLY.value,
    )
    assert item.frequency == "monthly"
    assert item.start_month is None
    assert item.end_month is None


def test_anticipated_item_with_explicit_frequency():
    """Test that frequency can be explicitly set."""
    item = AnticipatedItem(
        name="Example Expense",
        amount=Decimal("500.00"),
        item_type=ItemType.EXPENSE.value,
        category="Example",
        active=True,
        frequency="monthly",
    )
    assert item.frequency == "monthly"
