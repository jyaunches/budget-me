"""Tests for transactional guards on direct Streamlit snapshot mutations."""

import inspect
from pathlib import Path
from unittest.mock import MagicMock
from uuid import uuid4

import pytest

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.streamlit_app import db


def _scalar_result(value):
    result = MagicMock()
    result.scalar_one_or_none.return_value = value
    return result


def test_direct_mutation_guard_locks_and_refreshes_before_status_check() -> None:
    """The UI boundary must not trust a stale OPEN identity-map value."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2026-07",
        account_id="checking-1",
        status=SnapshotStatus.CLOSED,
    )
    session = MagicMock()
    session.get.return_value = snapshot

    with pytest.raises(ValueError, match="closed snapshot"):
        db._require_open_snapshot_for_update(session, snapshot.id)

    session.get.assert_called_once_with(
        MonthlySnapshot,
        snapshot.id,
        populate_existing=True,
        with_for_update=True,
    )


def test_closed_snapshot_notes_are_rejected_before_flush() -> None:
    """Notes follow the same immutable CLOSED boundary as financial fields."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2026-07",
        account_id="checking-1",
        status=SnapshotStatus.CLOSED,
        notes="frozen",
    )
    session = MagicMock()
    session.execute.return_value = _scalar_result(snapshot)
    session.get.return_value = snapshot

    with pytest.raises(ValueError, match="closed snapshot"):
        db.update_snapshot_notes(
            session,
            snapshot.year_month,
            snapshot.account_id,
            "changed",
        )

    assert snapshot.notes == "frozen"
    session.flush.assert_not_called()


@pytest.mark.parametrize(
    "function_name",
    [
        "update_snapshot_line_item",
        "add_one_time_item",
        "update_snapshot_credit_card",
        "update_snapshot_notes",
    ],
)
def test_direct_snapshot_mutators_use_the_locked_parent_guard(
    function_name: str,
) -> None:
    """Every direct single-snapshot mutation routes through the row lock."""
    source = inspect.getsource(getattr(db, function_name))
    assert "_require_open_snapshot_for_update" in source


def test_bulk_snapshot_injection_locks_open_parents_deterministically() -> None:
    """Bulk child creation locks all qualifying parent headers in one order."""
    source = inspect.getsource(db.inject_anticipated_item_into_open_snapshots)
    assert ".order_by(" in source
    assert ".with_for_update()" in source
    assert ".execution_options(populate_existing=True)" in source


def test_closed_notes_ui_never_renders_an_enabled_save_path() -> None:
    """The page disables editing and gates Save Notes on the closed status."""
    repository_root = Path(__file__).resolve().parents[3]
    source = (
        repository_root / "src/budget_me/streamlit_app/pages/monthly_snapshot.py"
    ).read_text()
    assert "disabled=notes_read_only" in source
    assert "if not notes_read_only and notes_input != current_notes" in source
