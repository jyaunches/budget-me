"""Tests for Unified Debt Dashboard page structure.

These tests verify the page has required components and logic.
Streamlit pages are difficult to unit test, so we use inspection-based
tests to verify key logic exists without running the Streamlit app.
"""

from pathlib import Path


class TestDebtPageStructure:
    """Tests for debt.py unified dashboard structure."""

    def test_debt_page_imports_required_modules(self):
        """Debt page imports necessary dependencies."""
        # Read page source file
        page_path = Path("src/budget_me/streamlit_app/pages/debt.py")
        source = page_path.read_text()

        # Verify required imports
        assert "import streamlit" in source or "from streamlit" in source
        assert "import pandas" in source or "from pandas" in source
        assert "get_loans_with_interest" in source
        assert "get_cc_calculated_interest" in source
        assert "get_cc_interest_from_transactions" in source
        assert "get_session" in source

    def test_debt_page_fetches_all_debt_data(self):
        """Debt page fetches loans, credit cards, and interest history."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify all data sources are queried
        assert "get_loans_with_interest" in source
        assert "get_cc_calculated_interest" in source
        assert "get_cc_interest_from_transactions" in source

    def test_debt_page_has_summary_metrics(self):
        """Debt page displays summary metrics with 4 columns."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify st.metric is used for summary display
        assert "st.metric" in source
        # Verify 4 columns
        assert "st.columns(4)" in source

    def test_debt_page_has_loan_sections(self):
        """Debt page has sections for mortgage and auto loans."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify loan sections exist
        assert "mortgage" in source.lower()
        assert "auto" in source.lower()
        assert "st.expander" in source

    def test_debt_page_has_credit_card_section(self):
        """Debt page has credit card section."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify credit card section exists
        assert "credit_cards" in source.lower()
        assert "st.dataframe" in source

    def test_debt_page_has_interest_analysis(self):
        """Debt page has interest analysis section."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify interest analysis exists
        assert "Interest Analysis" in source
        assert "st.progress" in source  # Progress bars for breakdown

    def test_debt_page_has_actual_vs_calculated_comparison(self):
        """Debt page compares actual vs calculated credit card interest."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify comparison logic exists
        assert "Actual vs Calculated" in source or "actual" in source.lower()
        assert "cc_interest_history" in source

    def test_debt_page_has_promo_alerts(self):
        """Debt page shows alerts for expiring promotional APRs."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify promo alert logic exists
        assert "get_expiring_promos" in source
        assert "st.warning" in source or "st.info" in source

    def test_debt_page_handles_empty_state(self):
        """Debt page handles empty data gracefully."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify empty state handling
        assert ("if not" in source) and ("st.info" in source or "st.warning" in source)

    def test_debt_page_formats_account_with_mask(self):
        """Debt page formats account names with mask."""
        source = Path("src/budget_me/streamlit_app/pages/debt.py").read_text()

        # Verify account formatting with mask
        assert "mask" in source and 'f"' in source
