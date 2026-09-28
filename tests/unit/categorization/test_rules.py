"""Unit tests for categorization rules module."""

from pathlib import Path
from tempfile import NamedTemporaryFile

import pytest

from budget_me.categorization.rules import (
    is_special_merchant,
    load_rules,
    match_merchant,
    match_reimbursable,
    should_skip,
)


class TestLoadRules:
    """Tests for load_rules function."""

    def test_load_rules_returns_merchants_and_categories(self):
        """Test loading valid YAML returns merchants and categories."""
        # Use actual rules file
        rules_path = Path("src/budget_me/data/categorization-rules.yaml")
        merchants, categories, reimbursable = load_rules(rules_path)

        # Verify structure
        assert isinstance(merchants, dict)
        assert isinstance(categories, list)
        assert isinstance(reimbursable, dict)

        # Verify content
        assert len(merchants) > 0
        assert len(categories) > 0
        assert "groceries" in categories
        assert "Costco" in merchants
        assert merchants["Costco"] == "groceries"

    def test_load_rules_raises_on_missing_file(self):
        """Test that missing file raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Rules file not found"):
            load_rules(Path("/nonexistent/path.yaml"))

    def test_load_rules_with_minimal_yaml(self):
        """Test loading minimal valid YAML structure."""
        yaml_content = """
categories:
  test_category:
    description: "Test"
    examples: []

merchants:
  TestMerchant: test_category
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)

        try:
            merchants, categories, reimbursable = load_rules(temp_path)
            assert merchants == {"TestMerchant": "test_category"}
            assert categories == ["test_category"]
            assert reimbursable == {}  # Empty when not in YAML
        finally:
            temp_path.unlink()

    def test_load_rules_returns_three_tuple(self):
        """Test load_rules returns three-tuple structure."""
        rules_path = Path("src/budget_me/data/categorization-rules.yaml")
        result = load_rules(rules_path)

        assert isinstance(result, tuple)
        assert len(result) == 3
        merchants, categories, reimbursable = result
        assert isinstance(merchants, dict)
        assert isinstance(categories, list)
        assert isinstance(reimbursable, dict)

    def test_packaged_rules_keep_reimbursable_mappings_empty(self):
        """Household-specific reimbursable mappings are never shipped."""
        rules_path = Path("src/budget_me/data/categorization-rules.yaml")
        _, _, reimbursable = load_rules(rules_path)

        assert reimbursable == {}

    def test_load_rules_reimbursable_merchants_empty_when_missing(self):
        """Test graceful handling when reimbursable_merchants section is missing."""
        yaml_content = """
categories:
  test_category:
    description: "Test"
    examples: []

merchants:
  TestMerchant: test_category
"""
        with NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
            f.write(yaml_content)
            temp_path = Path(f.name)

        try:
            merchants, categories, reimbursable = load_rules(temp_path)
            assert reimbursable == {}  # Empty dict when section missing
            assert isinstance(reimbursable, dict)
        finally:
            temp_path.unlink()


class TestMatchMerchant:
    """Tests for match_merchant function."""

    def test_match_merchant_exact_match(self):
        """Test exact match returns category."""
        rules = {"Starbucks": "dining"}
        result = match_merchant("Starbucks", rules)
        assert result == ("dining", "Starbucks")

    def test_match_merchant_case_insensitive(self):
        """Test case-insensitive matching works."""
        rules = {"Starbucks": "dining"}
        result = match_merchant("STARBUCKS", rules)
        assert result == ("dining", "Starbucks")

    def test_match_merchant_whitespace_normalized(self):
        """Test whitespace is normalized in matching."""
        rules = {"Starbucks": "dining"}
        result = match_merchant("  Starbucks  ", rules)
        assert result == ("dining", "Starbucks")

    def test_match_merchant_no_match(self):
        """Test no match returns None."""
        rules = {"Starbucks": "dining"}
        result = match_merchant("Unknown Shop", rules)
        assert result is None

    def test_match_merchant_empty_rules(self):
        """Test empty rules dict returns None."""
        result = match_merchant("Starbucks", {})
        assert result is None

    def test_match_merchant_with_special_characters(self):
        """Test matching with special characters in merchant name."""
        rules = {"Trader Joe's": "groceries"}
        result = match_merchant("Trader Joe's", rules)
        assert result == ("groceries", "Trader Joe's")

    def test_match_merchant_substring_with_transaction_id(self):
        """Test merchant name matches when transaction has appended ID."""
        rules = {"eBay": "shopping"}
        result = match_merchant("eBay EXAMPLE-ORDER-0001", rules)
        assert result == ("shopping", "eBay")

    def test_match_merchant_substring_with_prefix(self):
        """Test merchant name matches when transaction has prefix."""
        rules = {"Example Merchant": "hobbyist_eng"}
        result = match_merchant("EXAMPLE-PREFIX* Example Merchant", rules)
        assert result == ("hobbyist_eng", "Example Merchant")

    def test_match_merchant_substring_amazon_variations(self):
        """Test Amazon matches its various transaction formats."""
        rules = {"Amazon": "shopping"}

        # Various Amazon transaction formats
        assert match_merchant("AMAZON MKTPLACE PMTS", rules) == ("shopping", "Amazon")
        assert match_merchant("Amazon.com*EXAMPLE-ORDER-A", rules) == (
            "shopping",
            "Amazon",
        )
        assert match_merchant("AMAZON MKTPL*EXAMPLE-ORDER-B", rules) == (
            "shopping",
            "Amazon",
        )

    def test_match_merchant_substring_instacart_variations(self):
        """Test Instacart matches with store suffixes."""
        rules = {"Instacart": "groceries"}

        # Instacart with store names
        assert match_merchant("IC* INSTACART", rules) == ("groceries", "Instacart")
        assert match_merchant("IC* INSTACART*ALDI", rules) == ("groceries", "Instacart")
        assert match_merchant("IC* INSTACART*COSTCO", rules) == (
            "groceries",
            "Instacart",
        )

    def test_match_merchant_substring_interest_charge_variations(self):
        """Test interest charges match despite variation in wording."""
        rules = {"INTEREST CHARGE": "fees"}

        assert match_merchant("PURCHASE INTEREST CHARGE", rules) == (
            "fees",
            "INTEREST CHARGE",
        )
        assert match_merchant("Interest Charge on Purchases", rules) == (
            "fees",
            "INTEREST CHARGE",
        )

    def test_match_merchant_substring_prefers_longer_match(self):
        """Test that longer/more specific matches are preferred over shorter ones."""
        rules = {"Target": "shopping", "Target Pharmacy": "health"}

        # Should match the more specific rule
        result = match_merchant("Target Pharmacy Store 1234", rules)
        assert result == ("health", "Target Pharmacy")

    def test_match_merchant_substring_case_insensitive(self):
        """Test substring matching is case-insensitive."""
        rules = {"eBay": "shopping"}

        assert match_merchant("EBAY EXAMPLE-ORDER-0002", rules) == ("shopping", "eBay")
        assert match_merchant("ebay example-order-0002", rules) == ("shopping", "eBay")

    def test_match_merchant_substring_example_prefix(self):
        """Test an example prefix transaction matches correctly."""
        rules = {"Example Merchant": "dining"}

        result = match_merchant("EXAMPLE-TST*Example Merchant", rules)
        assert result == ("dining", "Example Merchant")


class TestShouldSkip:
    """Tests for should_skip function."""

    def test_should_skip_payroll(self):
        """Test payroll transaction is skipped."""
        assert should_skip("PAYROLL DEPOSIT") is True

    def test_should_skip_transfer(self):
        """Test transfer transaction is skipped."""
        assert should_skip("FUNDS TRANSFER TO SAVINGS") is True

    def test_should_skip_false_for_merchant(self):
        """Test merchant name is not skipped."""
        assert should_skip("Starbucks") is False

    def test_should_skip_credit_card_autopay(self):
        """Test credit card autopay is skipped."""
        assert should_skip("CREDIT CRD AUTOPAY") is True

    def test_should_skip_online_payment(self):
        """Test online payment is skipped."""
        assert should_skip("ONLINE PAYMENT - THANK YOU") is True

    def test_should_skip_check(self):
        """Test check transactions are skipped."""
        assert should_skip("CHECK #1234") is True

    def test_should_skip_case_insensitive(self):
        """Test skip matching is case-insensitive."""
        assert should_skip("payroll deposit") is True
        assert should_skip("Payroll Deposit") is True

    def test_should_skip_partial_match(self):
        """Test skip patterns match partial strings."""
        assert should_skip("AUTOMATIC PAYMENT TO SAVINGS") is True

    def test_should_skip_autopay_payment(self):
        """Test autopay payment is skipped."""
        assert should_skip("AUTOPAY PAYMENT") is True

    def test_should_skip_benefit_payment(self):
        """Test benefit payment is skipped."""
        assert should_skip("BENEFIT PAYMENT EDI PYMNTS") is True

    def test_should_skip_payment_received(self):
        """Test payment received transactions are skipped."""
        assert should_skip("Payment Received") is True
        assert should_skip("PAYMENT RECEIVED") is True

    def test_should_skip_electronic_payment_received(self):
        """Test electronic payment received transactions are skipped."""
        assert should_skip("ELECTRONIC PAYMENT RECEIVED-THANK") is True
        assert should_skip("Electronic Payment Received") is True


class TestMatchReimbursable:
    """Tests for match_reimbursable function."""

    def test_match_reimbursable_exact_match(self):
        """Test exact match returns group tag."""
        rules = {"Example Vendor A": "example_group"}
        result = match_reimbursable("Example Vendor A", rules)
        assert result == "example_group"

    def test_match_reimbursable_case_insensitive(self):
        """Test case-insensitive matching works."""
        rules = {"Example Vendor A": "example_group"}
        result = match_reimbursable("EXAMPLE VENDOR A", rules)
        assert result == "example_group"

    def test_match_reimbursable_with_whitespace(self):
        """Test whitespace normalization."""
        rules = {"Example Vendor A": "example_group"}
        result = match_reimbursable("  Example Vendor A  ", rules)
        assert result == "example_group"

    def test_match_reimbursable_no_match(self):
        """Test no match returns None."""
        rules = {"Example Vendor A": "example_group"}
        result = match_reimbursable("Unknown Merchant", rules)
        assert result is None

    def test_match_reimbursable_returns_group_tag_not_category(self):
        """Test returns group tag value, not category."""
        rules = {"Example Vendor B": "example_group"}
        result = match_reimbursable("Example Vendor B", rules)
        # Returns "example_group" which is the group tag (may or may not match a category)
        assert result == "example_group"
        assert isinstance(result, str)

    def test_match_reimbursable_with_empty_rules(self):
        """Test empty rules dict returns None."""
        result = match_reimbursable("Example Vendor A", {})
        assert result is None

    def test_match_reimbursable_multiple_merchants(self):
        """Test matching with multiple merchants in rules."""
        rules = {
            "Example Vendor A": "example_group",
            "Example Vendor B": "example_group",
        }

        assert match_reimbursable("Example Vendor A", rules) == "example_group"
        assert match_reimbursable("Example Vendor B", rules) == "example_group"
        assert match_reimbursable("Unknown", rules) is None


class TestIsSpecialMerchant:
    """Tests for is_special_merchant function."""

    def test_is_special_merchant_venmo(self):
        """Test Venmo is recognized as special merchant."""
        assert is_special_merchant("Venmo") is True

    def test_is_special_merchant_venmo_payment(self):
        """Test 'Venmo Payment' is recognized as special merchant."""
        assert is_special_merchant("Venmo Payment") is True

    def test_is_special_merchant_case_insensitive(self):
        """Test case-insensitive matching works."""
        assert is_special_merchant("VENMO") is True
        assert is_special_merchant("venmo") is True
        assert is_special_merchant("VeNmO") is True

    def test_is_special_merchant_with_whitespace(self):
        """Test whitespace normalization."""
        assert is_special_merchant("  Venmo  ") is True
        assert is_special_merchant("  Venmo Payment  ") is True

    def test_is_special_merchant_zelle(self):
        """Test Zelle is recognized as special merchant."""
        assert is_special_merchant("Zelle") is True

    def test_is_special_merchant_cash_app(self):
        """Test Cash App is recognized as special merchant."""
        assert is_special_merchant("Cash App") is True

    def test_is_special_merchant_false_for_regular_merchant(self):
        """Test regular merchants return False."""
        assert is_special_merchant("Starbucks") is False
        assert is_special_merchant("Target") is False
        assert is_special_merchant("Costco") is False

    def test_is_special_merchant_false_for_empty_string(self):
        """Test empty string returns False."""
        assert is_special_merchant("") is False

    def test_is_special_merchant_partial_match_not_allowed(self):
        """Test partial matches don't count as special merchants."""
        assert is_special_merchant("Venmo Inc") is False
        assert is_special_merchant("My Venmo Store") is False
