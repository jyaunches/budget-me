"""Structural tests for the retirement planner page."""

from pathlib import Path


def test_retirement_page_is_registered_in_navigation():
    source = Path("src/budget_me/streamlit_app/app.py").read_text()

    assert 'st.Page("pages/retirement.py"' in source
    assert 'title="Retirement Planner"' in source


def test_retirement_page_contains_editable_holdings_and_projection_chart():
    source = Path("src/budget_me/streamlit_app/pages/retirement.py").read_text()

    assert "st.data_editor" in source
    assert "project_retirement" in source
    assert "st.plotly_chart" in source
    assert "get_investment_holdings_summary" in source
    assert "Plaid Investments holdings" in source
    assert "Reload stored Plaid holdings" in source


def test_retirement_page_uses_synthetic_manual_defaults():
    source = Path("src/budget_me/streamlit_app/pages/retirement.py").read_text()

    assert '"Institution": "Example Brokerage"' in source
    assert '"Include": False' in source
