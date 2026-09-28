"""Unit tests for categorization models."""

from datetime import date
from decimal import Decimal
from uuid import uuid4

import pytest

from budget_me.categorization.models import (
    CategorizationResult,
    CategorizationStats,
    InferenceResult,
    UnknownMerchant,
)


class TestInferenceResult:
    """Tests for InferenceResult value object."""

    def test_inference_result_is_frozen(self):
        """Test that InferenceResult is immutable."""
        result = InferenceResult(category="dining", confidence="high")
        with pytest.raises(Exception):  # dataclass frozen raises FrozenInstanceError
            result.category = "groceries"

    def test_inference_result_with_none_category(self):
        """Test InferenceResult can have None category."""
        result = InferenceResult(category=None, confidence="none")
        assert result.category is None
        assert result.confidence == "none"


class TestUnknownMerchant:
    """Tests for UnknownMerchant value object."""

    def test_unknown_merchant_is_frozen(self):
        """Test that UnknownMerchant is immutable."""
        merchant = UnknownMerchant(
            name="Unknown Shop",
            amount=Decimal("42.50"),
            date=date(2026, 1, 5),
            reason="No search results",
        )
        with pytest.raises(Exception):
            merchant.name = "Different"

    def test_unknown_merchant_attributes(self):
        """Test UnknownMerchant has correct attributes."""
        merchant = UnknownMerchant(
            name="VUYNRP",
            amount=Decimal("66.98"),
            date=date(2026, 1, 4),
            reason="No search results",
        )
        assert merchant.name == "VUYNRP"
        assert merchant.amount == Decimal("66.98")
        assert merchant.date == date(2026, 1, 4)
        assert merchant.reason == "No search results"


class TestCategorizationStats:
    """Tests for CategorizationStats."""

    def test_stats_defaults_to_zero(self):
        """Test stats default to zero."""
        stats = CategorizationStats()
        assert stats.total_processed == 0
        assert stats.from_rules == 0
        assert stats.from_inference == 0
        assert stats.from_search == 0
        assert stats.skipped == 0
        assert stats.unknown == 0

    def test_stats_can_be_updated(self):
        """Test stats can be modified (mutable)."""
        stats = CategorizationStats()
        stats.total_processed = 10
        stats.from_rules = 7
        stats.from_inference = 2
        stats.unknown = 1
        assert stats.total_processed == 10
        assert stats.from_rules == 7


class TestCategorizationResult:
    """Tests for CategorizationResult."""

    def test_result_defaults_to_empty(self):
        """Test result defaults to empty collections."""
        result = CategorizationResult()
        assert result.categorized == {}
        assert result.new_rules == {}
        assert result.unknowns == []
        assert isinstance(result.stats, CategorizationStats)

    def test_result_can_store_categorized_transactions(self):
        """Test result can store categorized transactions."""
        tx_id1 = uuid4()
        tx_id2 = uuid4()
        result = CategorizationResult()
        result.categorized["dining"] = [tx_id1, tx_id2]
        assert len(result.categorized["dining"]) == 2

    def test_result_can_store_new_rules(self):
        """Test result can store new merchant rules."""
        result = CategorizationResult()
        result.new_rules["Starbucks"] = "dining"
        result.new_rules["Costco"] = "groceries"
        assert len(result.new_rules) == 2

    def test_result_can_store_unknowns(self):
        """Test result can store unknown merchants."""
        result = CategorizationResult()
        unknown = UnknownMerchant(
            name="VUYNRP",
            amount=Decimal("66.98"),
            date=date(2026, 1, 4),
            reason="No search results",
        )
        result.unknowns.append(unknown)
        assert len(result.unknowns) == 1
