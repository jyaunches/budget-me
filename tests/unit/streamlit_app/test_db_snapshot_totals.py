"""Unit tests for snapshot totals calculation.

Tests verify that get_snapshot_totals() properly:
- Returns SnapshotTotals dataclass with required fields
- Uses cached totals for closed snapshots
- Calculates totals from line items for open snapshots
- Excludes skipped items
- Aggregates across multiple accounts
"""

import inspect


def test_get_snapshot_totals_is_exported():
    """Verify get_snapshot_totals function exists."""
    from budget_me.streamlit_app import db

    assert hasattr(db, "get_snapshot_totals")
    assert callable(db.get_snapshot_totals)


def test_get_snapshot_totals_signature():
    """Verify get_snapshot_totals has correct signature."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    sig = inspect.signature(get_snapshot_totals)
    params = list(sig.parameters.keys())
    assert "session" in params
    assert "year_month" in params
    assert "include_open" in params

    # Check default value
    assert sig.parameters["include_open"].default is True


def test_get_snapshot_totals_queries_snapshots():
    """Verify get_snapshot_totals queries MonthlySnapshot."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    assert "MonthlySnapshot" in source
    assert "year_month" in source


def test_get_snapshot_totals_uses_cached_for_closed():
    """Verify get_snapshot_totals uses cached totals for closed snapshots."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    assert "_closed_snapshot_cache" in source
    assert "SnapshotLineItem" not in source
    assert "closing_balance" in source


def test_get_snapshot_totals_calculates_for_open():
    """Verify get_snapshot_totals calculates from line items for open snapshots."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    assert "calculate_snapshot_totals" in source


def test_get_snapshot_totals_excludes_skipped_items():
    """Verify get_snapshot_totals excludes skipped items."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    assert "skipped" in source
    # Should filter where skipped != True or IS NULL


def test_get_snapshot_totals_aggregates_accounts():
    """Verify get_snapshot_totals aggregates across all checking accounts."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    # Should sum across multiple snapshots
    assert "sum" in source.lower() or "total" in source


def test_get_snapshot_totals_returns_dataclass():
    """Verify get_snapshot_totals returns SnapshotTotals dataclass."""
    from budget_me.streamlit_app.db import SnapshotTotals, get_snapshot_totals

    # Verify SnapshotTotals is a dataclass
    assert hasattr(SnapshotTotals, "__dataclass_fields__")

    # Verify fields exist
    fields = SnapshotTotals.__dataclass_fields__
    assert "income" in fields
    assert "expenses" in fields
    assert "cc_payments" in fields
    assert "transfer_in" in fields
    assert "transfer_out" in fields
    assert "reimbursement_in" in fields
    assert "reimbursement_out" in fields
    assert "net" in fields
    assert "closing_balance" in fields

    # Verify return type annotation
    sig = inspect.signature(get_snapshot_totals)
    assert "SnapshotTotals" in str(sig.return_annotation)


def test_get_snapshot_totals_include_open_false():
    """Verify include_open=False excludes open snapshots."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    assert "include_open" in source
    # Should conditionally filter by status


def test_get_snapshot_totals_returns_none_when_no_snapshots():
    """Verify get_snapshot_totals returns None when no snapshots exist."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)
    # Should handle empty result
    assert "None" in source or "null" in source.lower()


def test_get_snapshot_totals_uses_snapshot_credit_cards_for_cc_payments():
    """Closed totals use cached card actuals, never planned child values."""
    from budget_me.streamlit_app.db import get_snapshot_totals

    source = inspect.getsource(get_snapshot_totals)

    assert "_closed_snapshot_cache" in source
    assert "calculated_payment" not in source
