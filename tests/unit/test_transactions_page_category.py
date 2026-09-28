"""Test that transactions page displays budget_category, not Plaid category."""

import pandas as pd
import pytest


def test_transactions_display_uses_budget_category_not_plaid_category():
    """Verify the Category column shows budget_category, not category_primary.

    The transactions page should display the Claude-assigned budget_category
    field, not the Plaid-provided category_primary. If budget_category is null,
    it should show empty (not fall back to Plaid category).
    """
    # Simulate transaction data as returned by get_transactions()
    transactions = [
        {
            "id": "txn_1",
            "reviewed": False,
            "date": "2026-01-01",
            "name": "COSTCO WHOLESALE",
            "merchant_name": "Costco",
            "amount": 150.00,
            "category_primary": "FOOD_AND_DRINK",  # Plaid category
            "budget_category": "groceries",  # Claude-assigned category
            "account_name": "Checking",
        },
        {
            "id": "txn_2",
            "reviewed": False,
            "date": "2026-01-02",
            "name": "AMAZON.COM",
            "merchant_name": "Amazon",
            "amount": 50.00,
            "category_primary": "GENERAL_MERCHANDISE",  # Plaid category
            "budget_category": None,  # Not yet categorized
            "account_name": "Checking",
        },
    ]

    df = pd.DataFrame(transactions)
    df["amount_display"] = df["amount"].apply(lambda x: f"${x:,.2f}")

    # This is the column selection from transactions.py - it should use budget_category
    # Currently it uses category_primary (the bug)
    display_df = df[
        [
            "reviewed",
            "date",
            "name",
            "merchant_name",
            "amount_display",
            "budget_category",  # Should be this, not category_primary
            "account_name",
        ]
    ].copy()
    display_df.columns = [
        "Reviewed",
        "Date",
        "Description",
        "Merchant",
        "Amount",
        "Category",
        "Account",
    ]

    # Verify the Category column contains budget_category values
    assert display_df.iloc[0]["Category"] == "groceries", (
        "First transaction should show budget_category 'groceries'"
    )

    # Verify null budget_category shows as None/NaN, not Plaid category
    assert (
        pd.isna(display_df.iloc[1]["Category"])
        or display_df.iloc[1]["Category"] is None
    ), "Uncategorized transaction should show empty, not Plaid category"


def test_transactions_page_source_uses_budget_category():
    """Verify the actual transactions.py source code uses budget_category.

    This test reads the source file to ensure budget_category is used
    for the Category column display, not category_primary.
    """
    from pathlib import Path

    transactions_page = Path("src/budget_me/streamlit_app/pages/transactions.py")
    source = transactions_page.read_text()

    # The display_df column selection should include budget_category
    # and NOT category_primary for the Category display

    # Find the display_df column selection block
    # It should contain budget_category in the column list that maps to "Category"

    # Check that budget_category is in the column selection (after the fix)
    assert '"budget_category"' in source or "'budget_category'" in source, (
        "transactions.py should use budget_category for Category display"
    )

    # The category_primary should NOT be used for display
    # (it may still exist in other contexts, but not in the display_df selection)
    lines = source.split("\n")
    in_display_df_block = False
    for i, line in enumerate(lines):
        if "display_df = df[" in line:
            in_display_df_block = True
        if in_display_df_block:
            if "category_primary" in line:
                pytest.fail(
                    f"Line {i + 1}: category_primary should not be used in display_df selection. "
                    "Use budget_category instead."
                )
            if "].copy()" in line:
                break
