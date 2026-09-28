"""Tests for FundingSource model."""

from decimal import Decimal

from budget_me.db.models.funding_source import (
    FundingSource,
    FundingSourceType,
)


def test_funding_source_types():
    """Test that FundingSourceType enum has correct values."""
    assert FundingSourceType.INVESTMENT.value == "investment"
    assert FundingSourceType.SAVINGS.value == "savings"
    assert FundingSourceType.OTHER.value == "other"


def test_funding_source_creation():
    """Test creating a funding source with all fields."""
    source = FundingSource(
        name="Example Investment",
        source_type=FundingSourceType.INVESTMENT.value,
        available_amount=Decimal("12345.67"),
        notes="Example valuation as of 2099-01-01",
        active=True,
    )
    assert source.name == "Example Investment"
    assert source.source_type == "investment"
    assert source.available_amount == Decimal("12345.67")
    assert source.notes == "Example valuation as of 2099-01-01"
    assert source.active is True


def test_funding_source_active_default():
    """Test that active can be set to True (default behavior)."""
    source = FundingSource(
        name="Emergency Savings",
        source_type=FundingSourceType.SAVINGS.value,
        available_amount=Decimal("10000.00"),
        active=True,
    )
    assert source.active is True


def test_funding_source_notes_optional():
    """Test that notes field is optional."""
    source = FundingSource(
        name="Savings Account",
        source_type=FundingSourceType.SAVINGS.value,
        available_amount=Decimal("5000.00"),
    )
    assert source.notes is None


def test_funding_source_all_types():
    """Test creating sources with each type."""
    investment = FundingSource(
        name="Stock Portfolio",
        source_type=FundingSourceType.INVESTMENT.value,
        available_amount=Decimal("100000.00"),
    )
    assert investment.source_type == "investment"

    savings = FundingSource(
        name="High Yield Savings",
        source_type=FundingSourceType.SAVINGS.value,
        available_amount=Decimal("25000.00"),
    )
    assert savings.source_type == "savings"

    other = FundingSource(
        name="Example Contribution",
        source_type=FundingSourceType.OTHER.value,
        available_amount=Decimal("123.45"),
    )
    assert other.source_type == "other"
