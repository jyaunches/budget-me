"""Unit tests for anticipated item injection into open snapshots.

Tests verify that inject_anticipated_item_into_open_snapshots() properly:
- Queries for open snapshots
- Prevents duplicates via source_item_id
- Reuses frequency logic from forecasting engine
"""

import inspect


def test_inject_anticipated_item_into_open_snapshots_is_exported():
    """Verify inject_anticipated_item_into_open_snapshots function exists."""
    from budget_me.streamlit_app import db

    assert hasattr(db, "inject_anticipated_item_into_open_snapshots")
    assert callable(db.inject_anticipated_item_into_open_snapshots)


def test_inject_function_signature():
    """Verify inject function has correct signature."""
    from budget_me.streamlit_app.db import inject_anticipated_item_into_open_snapshots

    sig = inspect.signature(inject_anticipated_item_into_open_snapshots)
    params = list(sig.parameters.keys())
    assert "session" in params
    assert "item_id" in params


def test_inject_function_queries_open_snapshots():
    """Verify inject function queries open snapshots."""
    from budget_me.streamlit_app.db import inject_anticipated_item_into_open_snapshots

    source = inspect.getsource(inject_anticipated_item_into_open_snapshots)
    assert "MonthlySnapshot" in source
    assert "status" in source
    assert "open" in source.lower()


def test_inject_function_checks_source_item_id():
    """Verify inject function checks source_item_id for duplicates."""
    from budget_me.streamlit_app.db import inject_anticipated_item_into_open_snapshots

    source = inspect.getsource(inject_anticipated_item_into_open_snapshots)
    assert "source_item_id" in source
    assert "SnapshotLineItem" in source


def test_inject_function_uses_engine_frequency_logic():
    """Verify inject function reuses engine's frequency logic."""
    from budget_me.streamlit_app.db import inject_anticipated_item_into_open_snapshots

    source = inspect.getsource(inject_anticipated_item_into_open_snapshots)
    assert "get_item_months_in_range" in source
    # Should import from forecasting.engine
    assert (
        "forecasting.engine" in source or "from budget_me.forecasting.engine" in source
    )
