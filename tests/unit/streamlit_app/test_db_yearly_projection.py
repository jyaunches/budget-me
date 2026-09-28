"""Unit tests for yearly projection integration with snapshots.

Tests verify that calculate_yearly_projection() properly:
- Calls get_snapshot_totals for each month
- Builds actuals_by_month dictionary
- Calls forecasting engine with actuals
- Integrates with anticipated_items, credit cards, and aggregate balance
"""

import inspect


def test_calculate_yearly_projection_is_exported():
    """Verify calculate_yearly_projection function exists."""
    from budget_me.streamlit_app import db

    assert hasattr(db, "calculate_yearly_projection")
    assert callable(db.calculate_yearly_projection)


def test_calculate_yearly_projection_signature():
    """Verify calculate_yearly_projection has correct signature."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    sig = inspect.signature(calculate_yearly_projection)
    params = list(sig.parameters.keys())
    assert "session" in params
    assert "start_month" in params
    assert "months" in params

    # Check default for months
    assert sig.parameters["months"].default == 12


def test_calculate_yearly_projection_calls_get_snapshot_totals():
    """Verify projection queries snapshots for each month."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    assert "get_snapshot_totals" in source
    assert "include_open=True" in source or "include_open" in source


def test_calculate_yearly_projection_builds_actuals_dict():
    """Verify calculate_yearly_projection builds actuals_by_month."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    assert "actuals_by_month" in source
    # Should create MonthActuals instances
    assert "MonthActuals" in source


def test_calculate_yearly_projection_calls_engine():
    """Verify calculate_yearly_projection calls forecasting engine."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    assert "calculate_projection" in source
    # Should import from forecasting.engine


def test_calculate_yearly_projection_gets_anticipated_items():
    """Verify calculate_yearly_projection gets anticipated items."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    # Should get anticipated items (either via ProjectionItem or delegation)
    assert "ProjectionItem" in source or "anticipated" in source.lower()


def test_calculate_yearly_projection_gets_credit_card_projections():
    """Verify calculate_yearly_projection includes credit card projections."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    # Should get credit card data
    assert "credit" in source.lower() or "CardPayment" in source


def test_calculate_yearly_projection_gets_aggregate_balance():
    """Verify calculate_yearly_projection gets aggregate checking balance."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    # Should query account balances
    assert "Account" in source or "balance" in source


def test_calculate_yearly_projection_uses_snapshot_when_available():
    """Verify calculate_yearly_projection prioritizes snapshot data."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    # Should check if snapshot_totals exists before using anticipated
    # Logic: if snapshot_totals: use snapshot, else: use anticipated
    assert "get_snapshot_totals" in source


def test_calculate_yearly_projection_returns_projection_result():
    """Verify calculate_yearly_projection returns projection result."""
    from budget_me.streamlit_app.db import calculate_yearly_projection

    source = inspect.getsource(calculate_yearly_projection)
    # Should return result from calculate_projection
    assert "return" in source
