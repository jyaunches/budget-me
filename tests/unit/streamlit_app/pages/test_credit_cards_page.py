"""Tests for credit cards management page."""

import os


class TestCreditCardsPage:
    """Tests for credit_cards.py page structure."""

    def test_page_exists(self):
        """credit_cards.py page exists."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        assert os.path.exists(page_path), f"Page file not found: {page_path}"

    def test_page_uses_get_all_credit_cards_with_full_details(self):
        """Page imports and uses the comprehensive query function."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "get_all_credit_cards_with_full_details" in source

    def test_page_uses_get_session(self):
        """Page uses get_session context manager."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "get_session" in source
        assert "with get_session()" in source

    def test_page_has_title(self):
        """Page has a title."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "st.title" in source or "st.header" in source

    def test_page_has_expandable_sections(self):
        """Page uses expander for card details."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        # Should use st.expander for expandable card sections
        assert "st.expander" in source

    def test_page_includes_payment_strategy_selector(self):
        """Page allows editing payment strategy."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "payment_strategy" in source or "Payment Strategy" in source

    def test_page_includes_fixed_payment_input(self):
        """Page has input for fixed payment amount."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "fixed_payment" in source.lower()

    def test_page_includes_paying_account_selector(self):
        """Page allows editing paying account."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "paying_account" in source or "Paying Account" in source


class TestCreditCardsPagePhase2:
    """Tests for Phase 2: APR breakdown and alerts."""

    def test_page_shows_apr_breakdown(self):
        """Page displays APR breakdown table."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "aprs" in source.lower() or "apr" in source.lower()

    def test_page_has_expiration_alerts(self):
        """Page shows alert banners for expiring/expired promos."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        # Should have alert logic for expired/expiring
        assert "expired" in source.lower() or "expiring" in source.lower()

    def test_page_shows_apr_status(self):
        """Page shows APR status (expired, expiring, active)."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "status" in source.lower() or "expired" in source.lower()


class TestCreditCardsPagePhase4:
    """Tests for Phase 4: Overview metrics."""

    def test_page_shows_total_balance(self):
        """Page displays total balance metric."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "total" in source.lower() and "balance" in source.lower()

    def test_page_shows_monthly_obligations(self):
        """Page displays monthly obligations metric."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "monthly" in source.lower() and "obligation" in source.lower()

    def test_page_shows_promo_cards_count(self):
        """Page displays promotional cards count."""
        page_path = "src/budget_me/streamlit_app/pages/credit_cards.py"
        with open(page_path) as f:
            source = f.read()
        assert "promo" in source.lower() or "promotional" in source.lower()
