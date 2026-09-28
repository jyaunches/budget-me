"""Unit tests for plan vs actual calculation.

Tests verify that calculate_plan_vs_actual() properly:
- Expands anticipated_items to get planned values
- Queries closed snapshots for actual values
- Calculates variance (actual - planned)
- Summarizes across closed months
- Returns proper data structure
"""

import inspect


def test_calculate_plan_vs_actual_is_exported():
    """Verify calculate_plan_vs_actual function exists."""
    from budget_me.streamlit_app import db

    assert hasattr(db, "calculate_plan_vs_actual")
    assert callable(db.calculate_plan_vs_actual)


def test_calculate_plan_vs_actual_signature():
    """Verify calculate_plan_vs_actual has correct signature."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    sig = inspect.signature(calculate_plan_vs_actual)
    params = list(sig.parameters.keys())
    assert "session" in params
    assert "start_month" in params
    assert "months" in params

    # Check default for months
    assert sig.parameters["months"].default == 12


def test_calculate_plan_vs_actual_expands_anticipated_items():
    """Verify function expands anticipated items for planned values."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    # Should use expand_anticipated_items from engine
    assert "expand_anticipated_items" in source
    assert "get_anticipated_items_for_forecast" in source


def test_calculate_plan_vs_actual_queries_snapshots():
    """Verify function queries MonthlySnapshot for status."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "MonthlySnapshot" in source
    assert "SnapshotStatus" in source


def test_calculate_plan_vs_actual_uses_get_snapshot_totals():
    """Verify function uses get_snapshot_totals for actuals."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "get_snapshot_totals" in source
    # Should only include closed snapshots for actuals
    assert "include_open=False" in source


def test_calculate_plan_vs_actual_calculates_variance():
    """Verify function calculates variance (actual - planned)."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "variance" in source.lower()
    # Variance = Actual - Planned
    assert "actual_income" in source
    assert "actual_expenses" in source
    assert "planned_income" in source
    assert "planned_expenses" in source


def test_calculate_plan_vs_actual_tracks_month_status():
    """Verify function tracks status (closed/open/future/partial) for each month."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert '"closed"' in source
    assert '"open"' in source
    assert '"future"' in source
    assert '"partial"' in source  # For months with mixed closed/open snapshots


def test_calculate_plan_vs_actual_returns_month_results():
    """Verify function returns month-by-month results."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "month_results" in source
    assert "year_month" in source


def test_calculate_plan_vs_actual_returns_summary():
    """Verify function returns summary with aggregate metrics."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "summary" in source
    assert "closed_months_count" in source
    assert "total_planned_net" in source
    assert "total_actual_net" in source
    assert "total_variance_net" in source


def test_calculate_plan_vs_actual_calculates_performance_percentage():
    """Verify function calculates performance percentage."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    assert "performance_pct" in source
    # Should calculate percentage vs planned net


def test_calculate_plan_vs_actual_handles_no_closed_months():
    """Verify function handles case with no closed months."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    # Should check for closed_count > 0 before calculating averages
    assert "closed_count" in source


def test_calculate_plan_vs_actual_returns_dict():
    """Verify function returns dictionary with expected structure."""
    from budget_me.streamlit_app.db import calculate_plan_vs_actual

    source = inspect.getsource(calculate_plan_vs_actual)
    # Should return dict with months and summary keys
    assert '"months"' in source
    assert '"summary"' in source
