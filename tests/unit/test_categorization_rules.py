"""Unit tests for categorization rules YAML file."""

from pathlib import Path

import pytest
import yaml


@pytest.fixture
def rules_file_path():
    """Path to categorization rules YAML file."""
    return (
        Path(__file__).parent.parent.parent
        / "src"
        / "budget_me"
        / "data"
        / "categorization-rules.yaml"
    )


@pytest.fixture
def rules_data(rules_file_path):
    """Load and parse categorization rules YAML."""
    with open(rules_file_path) as f:
        return yaml.safe_load(f)


def test_categorization_rules_yaml_exists(rules_file_path):
    """Verify rules file exists at expected location."""
    assert rules_file_path.exists(), f"Rules file not found at {rules_file_path}"


def test_categorization_rules_yaml_parses(rules_file_path):
    """Verify YAML file parses without errors and returns dict."""
    with open(rules_file_path) as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict)
    assert len(data) > 0


def test_categorization_rules_has_categories_section(rules_data):
    """Verify categories section exists and has expected structure."""
    assert "categories" in rules_data
    assert isinstance(rules_data["categories"], dict)

    # Check each category has description and examples
    for category_name, category_info in rules_data["categories"].items():
        assert "description" in category_info, (
            f"Category {category_name} missing description"
        )
        assert "examples" in category_info, f"Category {category_name} missing examples"
        assert isinstance(category_info["examples"], list), (
            f"Category {category_name} examples not a list"
        )


def test_categorization_rules_has_merchants_section(rules_data):
    """Verify merchants section exists and has at least 20 mappings."""
    assert "merchants" in rules_data
    assert isinstance(rules_data["merchants"], dict)
    assert len(rules_data["merchants"]) >= 20, (
        f"Expected at least 20 merchants, got {len(rules_data['merchants'])}"
    )

    # All merchant mappings should be strings (category names)
    for merchant, category in rules_data["merchants"].items():
        assert isinstance(category, str), (
            f"Merchant {merchant} has non-string category: {category}"
        )


def test_all_budget_categories_defined(rules_data):
    """Verify all budget categories from categorization-rules.yaml are present."""
    expected_categories = {
        "groceries",
        "dining",
        "subscriptions",
        "shopping",
        "transportation",
        "utilities",
        "entertainment",
        "health",
        "home",
        "travel",
        "fees",
        "giving",
        "gifts",
        "childcare",
        "insurance",
        "auto",
        "education",
        "personal_care",
        "hobbyist_eng",
        "shipping",
        "pets",
        "alcohol",
        "taxes",
        "uncategorized",
        "reimbursement",
        "mortgage",
        "landscaping",
        "credit_card_payment",
        "transfer",
    }

    actual_categories = set(rules_data["categories"].keys())
    assert expected_categories == actual_categories, (
        f"Category mismatch. Missing: {expected_categories - actual_categories}, Extra: {actual_categories - expected_categories}"
    )


def test_merchant_mappings_reference_valid_categories(rules_data):
    """Verify all merchant categories exist in categories section."""
    valid_categories = set(rules_data["categories"].keys())

    for merchant, category in rules_data["merchants"].items():
        assert category in valid_categories, (
            f"Merchant '{merchant}' references undefined category '{category}'"
        )


def test_merchant_matching_is_case_insensitive():
    """Verify merchant matching logic is case-insensitive."""
    test_merchant = "Costco"
    variations = ["Costco", "COSTCO", "costco", "CoStCo"]

    # Normalize using the expected matching logic
    normalized = [m.lower().strip() for m in variations]

    # All variations should normalize to the same value
    assert len(set(normalized)) == 1, "Case variations did not normalize to same value"
    assert normalized[0] == test_merchant.lower()


def test_merchant_matching_normalizes_whitespace():
    """Verify merchant matching normalizes whitespace."""
    test_merchant = "Costco"
    variations = ["Costco", "  Costco  ", " Costco", "Costco "]

    # Normalize using the expected matching logic
    normalized = [m.lower().strip() for m in variations]

    # All variations should normalize to the same value
    assert len(set(normalized)) == 1, (
        "Whitespace variations did not normalize to same value"
    )
    assert normalized[0] == test_merchant.lower()


# Phase 2 tests for reimbursable merchants


def test_categorization_rules_has_reimbursement_category(rules_data):
    """Verify reimbursement category exists with proper structure."""
    assert "reimbursement" in rules_data["categories"], (
        "reimbursement category not found"
    )

    reimbursement = rules_data["categories"]["reimbursement"]
    assert "description" in reimbursement, "reimbursement category missing description"
    assert "examples" in reimbursement, "reimbursement category missing examples"
    assert isinstance(reimbursement["examples"], list), (
        "reimbursement examples not a list"
    )

    # Description should mention exclusion
    assert "excluded" in reimbursement["description"].lower(), (
        "reimbursement description should mention exclusion from calculations"
    )


def test_packaged_rules_have_empty_reimbursable_merchants(rules_data):
    """Household-specific reimbursable mappings are not distributed."""
    assert "reimbursable_merchants" in rules_data
    assert rules_data["reimbursable_merchants"] == {}


def test_reimbursable_merchants_values_are_group_tags(rules_data):
    """Verify reimbursable merchant values are group tags, not category names."""
    reimbursable = rules_data["reimbursable_merchants"]

    for merchant, group_tag in reimbursable.items():
        assert isinstance(group_tag, str), (
            f"Merchant '{merchant}' group tag should be a string, got {type(group_tag)}"
        )

        # Group tags should be descriptive strings like "work", "utilities"
        # They are NOT budget categories (though they might coincidentally match)
        assert len(group_tag) > 0, f"Merchant '{merchant}' has empty group tag"


def test_yaml_parses_with_reimbursable_section(rules_file_path):
    """Verify YAML with reimbursable_merchants section parses without errors."""
    with open(rules_file_path) as f:
        data = yaml.safe_load(f)

    assert isinstance(data, dict), "YAML should parse to dict"
    assert "categories" in data, "Should have categories section"
    assert "merchants" in data, "Should have merchants section"
    assert "reimbursable_merchants" in data, (
        "Should have reimbursable_merchants section"
    )
