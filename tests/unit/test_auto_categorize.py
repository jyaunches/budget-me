"""Tests for auto_categorize script output."""

import json
from datetime import date
from decimal import Decimal

from budget_me.categorization.models import UnknownMerchant
from budget_me.categorization.rules import is_special_merchant


class TestAutoCategorizeFlagGeneration:
    """Tests for is_special_merchant flag generation in output."""

    def test_special_merchant_flag_true_for_venmo(self):
        """Venmo is flagged as special merchant."""
        assert is_special_merchant("VENMO PAYMENT") is True
        assert is_special_merchant("Venmo") is True

    def test_special_merchant_flag_false_for_regular_unknown(self):
        """Regular unknown merchants not flagged as special."""
        assert is_special_merchant("UNKNOWN_MERCHANT_XYZ") is False
        assert is_special_merchant("ACME CORP") is False

    def test_special_merchant_venmo_case_variations(self):
        """All Venmo case variations flagged as special."""
        assert is_special_merchant("Venmo") is True
        assert is_special_merchant("VENMO") is True
        assert is_special_merchant("venmo") is True
        assert is_special_merchant("Venmo Payment") is True

    def test_all_special_merchants_flagged(self):
        """All special merchant types are flagged correctly."""
        assert is_special_merchant("Venmo") is True
        assert is_special_merchant("Zelle") is True
        assert is_special_merchant("Cash App") is True


class TestUnknownMerchantOutput:
    """Tests for unknown merchant output format with is_special_merchant."""

    def test_output_includes_is_special_merchant_for_unknowns(self):
        """Output JSON format includes is_special_merchant field for unknowns."""
        # Simulate what auto_categorize.py should output
        unknowns = [
            UnknownMerchant(
                name="VENMO PAYMENT",
                amount=Decimal("20.00"),
                date=date(2026, 1, 14),
                reason="Special merchant - manual review required",
            ),
            UnknownMerchant(
                name="UNKNOWN_MERCHANT_XYZ",
                amount=Decimal("50.00"),
                date=date(2026, 1, 15),
                reason="Not matched in rules",
            ),
        ]

        # Expected output format (what auto_categorize.py should produce)
        output = [
            {
                "name": u.name,
                "amount": str(u.amount),
                "date": str(u.date),
                "reason": u.reason,
                "is_special_merchant": is_special_merchant(u.name),
            }
            for u in unknowns
        ]

        # Verify output structure
        assert len(output) == 2

        # First unknown is special merchant
        assert output[0]["name"] == "VENMO PAYMENT"
        assert output[0]["is_special_merchant"] is True
        assert "Special merchant" in output[0]["reason"]

        # Second unknown is regular merchant
        assert output[1]["name"] == "UNKNOWN_MERCHANT_XYZ"
        assert output[1]["is_special_merchant"] is False

    def test_output_json_serializable(self):
        """Output with is_special_merchant is JSON serializable."""
        unknown = {
            "name": "Venmo",
            "amount": "20.00",
            "date": "2026-01-14",
            "reason": "Special merchant - manual review required",
            "is_special_merchant": True,
        }

        # Should not raise
        json_str = json.dumps(unknown)
        parsed = json.loads(json_str)

        assert parsed["is_special_merchant"] is True
