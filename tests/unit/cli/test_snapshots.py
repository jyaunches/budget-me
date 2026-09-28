"""CLI guard tests for snapshot review, initialization, and close commands."""

import json
import stat
from contextlib import contextmanager
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from typer.testing import CliRunner

from budget_me.cli.main import app
from budget_me.snapshots.initialization import (
    SnapshotInitializationPreview,
    SnapshotInitializationTotals,
)
from budget_me.snapshots.reconciliation import (
    ReconciliationTotals,
    SnapshotReconciliationPreview,
)
from budget_me.snapshots.reconciliation_manifest import ReconciliationManifest
from budget_me.snapshots.service import (
    PlaidItemSyncEvidence,
    SnapshotClosePreview,
    SnapshotCloseTotals,
    SnapshotTransactionCounts,
)

runner = CliRunner()

_PRIVATE_TRANSACTION_HINT = "Private Merchant 8675309"
_PRIVATE_LINE_ITEM_HINT = "Private Mortgage 4242"


def _preview() -> SnapshotClosePreview:
    totals = SnapshotCloseTotals(
        income_total=Decimal("100.00"),
        expense_total=Decimal("25.00"),
        transfer_in_total=Decimal("5.00"),
        transfer_out_total=Decimal("10.00"),
        credit_card_total=Decimal("20.00"),
        net=Decimal("50.00"),
    )
    return SnapshotClosePreview(
        year_month="2026-07",
        account_id="checking-1",
        account_name="Primary Checking",
        snapshot_id="00000000-0000-0000-0000-000000000001",
        status="open",
        last_synced_at=datetime(2026, 8, 10, tzinfo=UTC),
        starting_balance=Decimal("1000.00"),
        captured_closing_balance=Decimal("1050.00"),
        projected_closing_balance=Decimal("1050.00"),
        closing_balance_to_freeze=Decimal("1050.00"),
        captured_difference=Decimal("0.00"),
        planned_credit_card_total=Decimal("30.00"),
        actual_credit_card_total=Decimal("20.00"),
        remaining_credit_card_total=Decimal("10.00"),
        missing_actual_credit_card_count=0,
        transaction_counts=SnapshotTransactionCounts(
            posted=3,
            pending=0,
            unreviewed=0,
            uncategorized=0,
            reimbursable=1,
        ),
        totals=totals,
        blockers=(),
        audit_hash="a" * 64,
        direct_starting_balance=Decimal("1000.00"),
        starting_balance_provenance="prior_frozen_close",
        prior_year_month="2026-06",
        prior_snapshot_id="00000000-0000-0000-0000-000000000000",
        prior_snapshot_status="closed",
        prior_direct_starting_balance=Decimal("900.00"),
        prior_closing_balance=Decimal("1000.00"),
        prior_closing_balance_frozen=True,
        prior_snapshot_updated_at=datetime(2026, 7, 1, tzinfo=UTC),
        plaid_item_sync_evidence=(
            PlaidItemSyncEvidence(
                plaid_item_id="00000000-0000-0000-0000-000000000010",
                ingest_run_id="00000000-0000-0000-0000-000000000011",
                ingest_run_item_id="00000000-0000-0000-0000-000000000012",
                item_status="success",
                run_status="completed",
                started_at=datetime(2026, 8, 9, 22, 0, tzinfo=UTC),
                ended_at=datetime(2026, 8, 9, 22, 1, tzinfo=UTC),
                items_total=1,
                items_ok=1,
                items_failed=0,
                item_tx_added=2,
                item_tx_modified=1,
                item_tx_removed=0,
            ),
        ),
    )


def _initialization_preview(
    *, blockers: tuple[str, ...] = ()
) -> SnapshotInitializationPreview:
    return SnapshotInitializationPreview(
        year_month="2026-07",
        account_id="checking-1",
        anticipated_item_count=3,
        income_item_count=1,
        expense_item_count=2,
        credit_card_count=1,
        totals=SnapshotInitializationTotals(
            income_total=Decimal("5000.00"),
            expense_total=Decimal("2400.00"),
            transfer_in_total=Decimal("0.00"),
            transfer_out_total=Decimal("0.00"),
            reimbursement_in_total=Decimal("0.00"),
            reimbursement_out_total=Decimal("0.00"),
            credit_card_total=Decimal("600.00"),
            net=Decimal("2000.00"),
        ),
        blockers=blockers,
        warnings=("Review every seeded row before reconciliation or close.",),
        audit_hash="b" * 64,
    )


def _reconciliation_manifest(
    *,
    year_month: str = "2026-07",
    account_id: str = "checking-1",
) -> ReconciliationManifest:
    return ReconciliationManifest.model_validate(
        {
            "version": 1,
            "year_month": year_month,
            "account_id": account_id,
            "transaction_decisions": [
                {
                    "transaction_id": "00000000-0000-0000-0000-000000000101",
                    "manual_locked": False,
                    "allocations": [
                        {
                            "flow_type": "expense",
                            "amount": "12.34",
                            "category": "Dining",
                        }
                    ],
                    "source_date": "2026-07-15",
                    "source_amount": "12.34",
                    "source_description": _PRIVATE_TRANSACTION_HINT,
                    "source_budget_category": "Private category",
                    "source_reviewed": True,
                }
            ],
            "line_item_decisions": [
                {
                    "line_item_id": "00000000-0000-0000-0000-000000000201",
                    "resolution": "remaining",
                    "remaining_amount": "12.34",
                    "matches": [],
                    "source_name": _PRIVATE_LINE_ITEM_HINT,
                    "source_item_type": "expense",
                    "source_planned_amount": "12.34",
                }
            ],
        }
    )


def _reconciliation_preview(
    *,
    blockers: tuple[str, ...] = (),
    is_idempotent: bool = False,
) -> SnapshotReconciliationPreview:
    return SnapshotReconciliationPreview(
        year_month="2026-07",
        account_id="checking-1",
        snapshot_id="00000000-0000-0000-0000-000000000001",
        manifest_hash="c" * 64,
        input_hash="d" * 64,
        totals=ReconciliationTotals(
            expense_total=Decimal("12.34"),
            net=Decimal("-12.34"),
        ),
        posted_transaction_count=1,
        allocation_count=1,
        line_item_count=1,
        remaining_item_count=1,
        remaining_item_total=Decimal("12.34"),
        pending_transaction_count=0,
        blockers=blockers,
        warnings=("Every decision requires private operator review.",),
        current_run_id=None,
        is_idempotent=is_idempotent,
    )


def _write_private_manifest(
    directory: Path,
    manifest: ReconciliationManifest | None = None,
    *,
    name: str = "reconciliation.json",
) -> Path:
    path = directory / name
    document = (manifest or _reconciliation_manifest()).model_dump(
        mode="json", exclude_none=True
    )
    path.write_text(json.dumps(document), encoding="utf-8")
    path.chmod(0o600)
    return path


@contextmanager
def _session_context():
    yield MagicMock()


def test_snapshots_review_json_is_read_only(monkeypatch):
    """Review uses the read-only session and emits the audit hash."""
    from budget_me.cli.commands import snapshots

    preview = _preview()
    readonly = MagicMock(side_effect=_session_context)
    close = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_close_preview", lambda *args: preview)
    monkeypatch.setattr(snapshots, "close_snapshot", close)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "review",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--json",
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload["audit_hash"] == preview.audit_hash
    assert payload["starting_balance_provenance"] == "prior_frozen_close"
    assert payload["prior_year_month"] == "2026-06"
    assert payload["prior_snapshot_status"] == "closed"
    assert payload["prior_direct_starting_balance"] == "900.00"
    assert payload["prior_closing_balance"] == "1000.00"
    assert payload["prior_closing_balance_frozen"] is True
    sync_evidence = payload["plaid_item_sync_evidence"][0]
    assert sync_evidence["item_status"] == "success"
    assert sync_evidence["item_tx_added"] == 2
    assert "error_message" not in sync_evidence
    readonly.assert_called_once_with()
    close.assert_not_called()


def test_snapshots_close_defaults_to_preview(monkeypatch):
    """Omitting --apply cannot write, even when --dry-run is omitted."""
    from budget_me.cli.commands import snapshots

    preview = _preview()
    close = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(snapshots, "build_close_preview", lambda *args: preview)
    monkeypatch.setattr(snapshots, "close_snapshot", close)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "close",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
        ],
    )

    assert result.exit_code == 0
    assert "DRY RUN" in result.stdout
    close.assert_not_called()


def test_snapshots_month_review_surfaces_missing_snapshot(monkeypatch):
    """Month-level review lists included accounts without auto-creating rows."""
    from budget_me.cli.commands import snapshots

    preview = _preview()
    present = SimpleNamespace(
        account_id="checking-1",
        name="Primary Checking",
        display_name=None,
    )
    missing = SimpleNamespace(
        account_id="checking-2",
        name="Secondary Checking",
        display_name=None,
    )
    build = MagicMock(side_effect=[preview, ValueError("Snapshot not found")])
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(
        snapshots,
        "list_included_depository_accounts",
        lambda session: [present, missing],
    )
    monkeypatch.setattr(
        snapshots,
        "get_account_transaction_counts",
        lambda *args: SnapshotTransactionCounts(
            posted=5,
            pending=0,
            unreviewed=5,
            uncategorized=3,
            reimbursable=0,
        ),
    )
    monkeypatch.setattr(snapshots, "build_close_preview", build)

    result = runner.invoke(
        app,
        ["snapshots", "review", "--month", "2026-07", "--json"],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    missing_entry = next(
        entry for entry in payload["accounts"] if entry["account_id"] == "checking-2"
    )
    assert missing_entry["status"] == "missing"
    assert missing_entry["transaction_counts"]["unreviewed"] == 5
    assert build.call_count == 2


def test_snapshots_apply_requires_confirmation_and_hash(monkeypatch):
    """The write path stays unreachable without both explicit proofs."""
    from budget_me.cli.commands import snapshots

    close = MagicMock()
    monkeypatch.setattr(snapshots, "close_snapshot", close)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "close",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
        ],
    )

    assert result.exit_code == 1
    assert "requires --confirm-month and --audit-hash" in result.stdout
    close.assert_not_called()


def test_snapshots_apply_passes_confirmation_and_hash(monkeypatch):
    """A complete apply request delegates once inside the write session."""
    from budget_me.cli.commands import snapshots

    preview = _preview()
    close = MagicMock(return_value=preview)
    monkeypatch.setattr(snapshots, "get_session", _session_context)
    monkeypatch.setattr(snapshots, "close_snapshot", close)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "close",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
            "--confirm-month",
            "2026-07",
            "--audit-hash",
            preview.audit_hash,
        ],
    )

    assert result.exit_code == 0
    close.assert_called_once()
    assert close.call_args.kwargs == {
        "confirm_month": "2026-07",
        "audit_hash": preview.audit_hash,
    }


def test_snapshots_initialize_defaults_to_read_only_aggregate_preview(monkeypatch):
    """Initialization defaults to aggregate JSON through a read-only session."""
    from budget_me.cli.commands import snapshots

    preview = _initialization_preview()
    session = MagicMock()

    @contextmanager
    def readonly_context():
        yield session

    readonly = MagicMock(side_effect=readonly_context)
    build = MagicMock(return_value=preview)
    write_session = MagicMock()
    initialize = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_initialization_preview", build)
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
        ],
    )

    assert result.exit_code == 0
    assert json.loads(result.stdout) == preview.to_dict()
    readonly.assert_called_once_with()
    build.assert_called_once_with(session, "2026-07", "checking-1")
    write_session.assert_not_called()
    initialize.assert_not_called()


def test_snapshots_initialize_preview_blockers_exit_two(monkeypatch):
    """Aggregate preview blockers are machine-readable and use exit code two."""
    from budget_me.cli.commands import snapshots

    preview = _initialization_preview(
        blockers=("A snapshot already exists for this month and account.",)
    )
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(
        snapshots, "build_initialization_preview", lambda *args: preview
    )
    initialize = MagicMock()
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["can_initialize"] is False
    assert payload["blockers"] == list(preview.blockers)
    initialize.assert_not_called()


def test_snapshots_initialize_apply_requires_both_proofs(monkeypatch):
    """Apply cannot open a write session without confirmation and an audit hash."""
    from budget_me.cli.commands import snapshots

    write_session = MagicMock()
    initialize = MagicMock()
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"] == "--apply requires --confirm-month and --audit-hash"
    write_session.assert_not_called()
    initialize.assert_not_called()


def test_snapshots_initialize_apply_requires_exact_month(monkeypatch):
    """A mismatched confirmation is rejected before opening a write session."""
    from budget_me.cli.commands import snapshots

    write_session = MagicMock()
    initialize = MagicMock()
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
            "--confirm-month",
            "2026-7",
            "--audit-hash",
            "b" * 64,
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert payload["error"] == "--confirm-month must exactly match --month"
    write_session.assert_not_called()
    initialize.assert_not_called()


def test_snapshots_initialize_apply_uses_owned_write_transaction(monkeypatch):
    """Successful apply delegates once and lets the session owner commit."""
    from budget_me.cli.commands import snapshots

    preview = _initialization_preview()
    session = MagicMock()
    snapshot = SimpleNamespace(
        year_month="2026-07",
        account_id="checking-1",
        status="open",
        income_total=Decimal("5000.00"),
        expense_total=Decimal("2400.00"),
        transfer_in_total=Decimal("0.00"),
        transfer_out_total=Decimal("0.00"),
        reimbursement_in_total=Decimal("0.00"),
        reimbursement_out_total=Decimal("0.00"),
        credit_card_total=Decimal("600.00"),
        net=Decimal("2000.00"),
        last_synced_at=None,
    )

    @contextmanager
    def owned_write_context():
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()

    initialize = MagicMock(return_value=snapshot)
    readonly = MagicMock()
    monkeypatch.setattr(snapshots, "get_session", owned_write_context)
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
            "--confirm-month",
            "2026-07",
            "--audit-hash",
            preview.audit_hash,
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "account_id": "checking-1",
        "audit_hash": preview.audit_hash,
        "initialized": True,
        "last_synced_at": None,
        "status": "open",
        "totals": preview.totals.to_dict(),
        "year_month": "2026-07",
    }
    initialize.assert_called_once_with(
        session,
        "2026-07",
        "checking-1",
        confirm_month="2026-07",
        audit_hash=preview.audit_hash,
    )
    session.commit.assert_called_once_with()
    session.rollback.assert_not_called()
    readonly.assert_not_called()


def test_snapshots_initialize_apply_blocker_rolls_back_and_exits_two(monkeypatch):
    """Revalidated apply blockers roll back and retain the blocker exit contract."""
    from budget_me.cli.commands import snapshots

    session = MagicMock()

    @contextmanager
    def owned_write_context():
        try:
            yield session
        except Exception:
            session.rollback()
            raise
        else:
            session.commit()

    initialize = MagicMock(
        side_effect=ValueError(
            "Cannot initialize snapshot: A snapshot already exists for this month "
            "and account."
        )
    )
    monkeypatch.setattr(snapshots, "get_session", owned_write_context)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
            "--confirm-month",
            "2026-07",
            "--audit-hash",
            "b" * 64,
        ],
    )

    assert result.exit_code == 2
    payload = json.loads(result.stdout)
    assert payload["blockers"] == [
        "A snapshot already exists for this month and account."
    ]
    assert payload["can_initialize"] is False
    session.rollback.assert_called_once_with()
    session.commit.assert_not_called()


def test_snapshots_initialize_stale_hash_is_not_reported_as_a_blocker(monkeypatch):
    """A stale audit proof exits one so callers know to request a fresh preview."""
    from budget_me.cli.commands import snapshots

    initialize = MagicMock(
        side_effect=ValueError(
            "Audit hash mismatch; run a fresh initialization preview"
        )
    )
    monkeypatch.setattr(snapshots, "get_session", _session_context)
    monkeypatch.setattr(snapshots, "initialize_snapshot", initialize)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "initialize",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--apply",
            "--confirm-month",
            "2026-07",
            "--audit-hash",
            "b" * 64,
        ],
    )

    assert result.exit_code == 1
    payload = json.loads(result.stdout)
    assert "fresh initialization preview" in payload["error"]
    assert "blockers" not in payload


def test_snapshots_reconcile_draft_is_read_only_and_writes_private_hints(
    monkeypatch, tmp_path
):
    """Draft creation reads only and keeps transaction detail in a 0600 file."""
    from budget_me.cli.commands import snapshots

    manifest = _reconciliation_manifest()
    session = MagicMock()

    @contextmanager
    def readonly_context():
        yield session

    readonly = MagicMock(side_effect=readonly_context)
    build = MagicMock(return_value=manifest)
    write_session = MagicMock()
    output = tmp_path / "july-reconciliation.json"
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_reconciliation_draft", build)
    monkeypatch.setattr(snapshots, "get_session", write_session)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile-draft",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 0
    payload = json.loads(result.stdout)
    assert payload == {
        "account_id": "checking-1",
        "created": True,
        "line_item_decision_count": 1,
        "manual_review_required": True,
        "output": str(output),
        "transaction_decision_count": 1,
        "year_month": "2026-07",
    }
    assert stat.S_IMODE(output.stat().st_mode) == 0o600
    protected_contents = output.read_text(encoding="utf-8")
    assert _PRIVATE_TRANSACTION_HINT in protected_contents
    assert _PRIVATE_LINE_ITEM_HINT in protected_contents
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout
    assert _PRIVATE_LINE_ITEM_HINT not in result.stdout
    readonly.assert_called_once_with()
    build.assert_called_once_with(session, "2026-07", "checking-1")
    write_session.assert_not_called()


def test_snapshots_reconcile_draft_refuses_to_overwrite(monkeypatch, tmp_path):
    """An existing artifact is never replaced, even by another valid draft."""
    from budget_me.cli.commands import snapshots

    output = tmp_path / "existing.json"
    output.write_text("do-not-overwrite", encoding="utf-8")
    output.chmod(0o600)
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(
        snapshots,
        "build_reconciliation_draft",
        lambda *args: _reconciliation_manifest(),
    )

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile-draft",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == (
        "Manifest destination already exists; refusing overwrite"
    )
    assert output.read_text(encoding="utf-8") == "do-not-overwrite"
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout


def test_snapshots_reconcile_rejects_insecure_manifest_without_echoing_it(
    monkeypatch, tmp_path
):
    """Group-readable input is rejected before its private contents are loaded."""
    from budget_me.cli.commands import snapshots

    manifest_path = _write_private_manifest(tmp_path)
    manifest_path.chmod(0o640)
    readonly = MagicMock()
    build = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_reconciliation_preview", build)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "can_apply": False,
        "error": "Manifest permissions must be private (0600 or stricter)",
    }
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout
    assert _PRIVATE_LINE_ITEM_HINT not in result.stdout
    readonly.assert_not_called()
    build.assert_not_called()


def test_snapshots_reconcile_rejects_manifest_symlink_without_echoing_target(
    monkeypatch, tmp_path
):
    """A symlink is rejected based on lstat without reading its private target."""
    from budget_me.cli.commands import snapshots

    target = _write_private_manifest(tmp_path, name="private-target.json")
    manifest_path = tmp_path / "manifest-link.json"
    manifest_path.symlink_to(target)
    readonly = MagicMock()
    build = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_reconciliation_preview", build)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "can_apply": False,
        "error": "Manifest path must be a regular file, not a symlink",
    }
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout
    assert _PRIVATE_LINE_ITEM_HINT not in result.stdout
    readonly.assert_not_called()
    build.assert_not_called()


def test_snapshots_reconcile_rejects_invalid_manifest_without_echoing_values(
    monkeypatch, tmp_path
):
    """Parser and schema details are replaced with one safe validation message."""
    from budget_me.cli.commands import snapshots

    private_value = "Invalid Private Merchant 9999"
    manifest_path = tmp_path / "invalid.json"
    manifest_path.write_text(
        json.dumps({"source_description": private_value}), encoding="utf-8"
    )
    manifest_path.chmod(0o600)
    readonly = MagicMock()
    build = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_reconciliation_preview", build)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "can_apply": False,
        "error": "Manifest validation failed; inspect the protected file locally",
    }
    assert private_value not in result.stdout
    readonly.assert_not_called()
    build.assert_not_called()


def test_snapshots_reconcile_requires_exact_manifest_target(monkeypatch, tmp_path):
    """A private manifest cannot be redirected to another CLI target."""
    from budget_me.cli.commands import snapshots

    private_target = "private-other-account-777"
    manifest_path = _write_private_manifest(
        tmp_path,
        _reconciliation_manifest(account_id=private_target),
    )
    readonly = MagicMock()
    build = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "build_reconciliation_preview", build)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout) == {
        "account_id": "checking-1",
        "can_apply": False,
        "error": "Manifest target must exactly match --month and --account",
        "year_month": "2026-07",
    }
    assert private_target not in result.stdout
    readonly.assert_not_called()
    build.assert_not_called()


def test_snapshots_reconcile_preview_is_read_only_and_blockers_exit_two(
    monkeypatch, tmp_path
):
    """Default reconciliation previews never write and blockers use exit two."""
    from budget_me.cli.commands import snapshots

    manifest = _reconciliation_manifest()
    manifest_path = _write_private_manifest(tmp_path, manifest)
    preview = _reconciliation_preview(
        blockers=("One or more transaction decisions are not manually locked.",)
    )
    session = MagicMock()

    @contextmanager
    def readonly_context():
        yield session

    readonly = MagicMock(side_effect=readonly_context)
    write_session = MagicMock()
    build = MagicMock(return_value=preview)
    apply_reconciliation = MagicMock()
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "build_reconciliation_preview", build)
    monkeypatch.setattr(snapshots, "apply_reconciliation", apply_reconciliation)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout) == preview.to_dict()
    readonly.assert_called_once_with()
    build.assert_called_once_with(session, manifest)
    write_session.assert_not_called()
    apply_reconciliation.assert_not_called()


@pytest.mark.parametrize(
    "proof_args",
    [
        [],
        ["--confirm-month", "2026-07"],
        ["--input-hash", "d" * 64],
    ],
)
def test_snapshots_reconcile_apply_requires_both_proofs(
    monkeypatch, tmp_path, proof_args
):
    """No write session opens unless both independent apply proofs are present."""
    from budget_me.cli.commands import snapshots

    manifest_path = _write_private_manifest(tmp_path)
    write_session = MagicMock()
    apply_reconciliation = MagicMock()
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "apply_reconciliation", apply_reconciliation)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
            "--apply",
            *proof_args,
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == (
        "--apply requires --confirm-month and --input-hash"
    )
    write_session.assert_not_called()
    apply_reconciliation.assert_not_called()


def test_snapshots_reconcile_apply_requires_exact_confirmation_month(
    monkeypatch, tmp_path
):
    """A near-match confirmation is rejected before acquiring write access."""
    from budget_me.cli.commands import snapshots

    manifest_path = _write_private_manifest(tmp_path)
    write_session = MagicMock()
    apply_reconciliation = MagicMock()
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "apply_reconciliation", apply_reconciliation)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
            "--apply",
            "--confirm-month",
            "2026-7",
            "--input-hash",
            "d" * 64,
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == (
        "--confirm-month must exactly match --month"
    )
    write_session.assert_not_called()
    apply_reconciliation.assert_not_called()


def test_snapshots_reconcile_apply_delegates_in_write_session_and_is_aggregate(
    monkeypatch, tmp_path
):
    """A proven apply delegates once and emits only aggregate receipt fields."""
    from budget_me.cli.commands import snapshots

    manifest = _reconciliation_manifest()
    manifest_path = _write_private_manifest(tmp_path, manifest)
    preview = _reconciliation_preview()
    session = MagicMock()

    @contextmanager
    def write_context():
        yield session

    write_session = MagicMock(side_effect=write_context)
    readonly = MagicMock()
    apply_reconciliation = MagicMock(return_value=preview)
    monkeypatch.setattr(snapshots, "get_session", write_session)
    monkeypatch.setattr(snapshots, "get_read_only_session", readonly)
    monkeypatch.setattr(snapshots, "apply_reconciliation", apply_reconciliation)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
            "--apply",
            "--confirm-month",
            "2026-07",
            "--input-hash",
            preview.input_hash,
        ],
    )

    assert result.exit_code == 0
    expected = preview.to_dict()
    expected["applied"] = True
    assert json.loads(result.stdout) == expected
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout
    assert _PRIVATE_LINE_ITEM_HINT not in result.stdout
    write_session.assert_called_once_with()
    apply_reconciliation.assert_called_once_with(
        session,
        manifest,
        confirm_month="2026-07",
        input_hash=preview.input_hash,
    )
    readonly.assert_not_called()


def test_snapshots_reconcile_apply_blocker_exits_two(monkeypatch, tmp_path):
    """A blocker found under the write lock keeps the distinct exit-two contract."""
    from budget_me.cli.commands import snapshots

    manifest_path = _write_private_manifest(tmp_path)
    blocker = "Cannot apply reconciliation: input evidence changed."
    apply_reconciliation = MagicMock(side_effect=ValueError(blocker))
    monkeypatch.setattr(snapshots, "get_session", _session_context)
    monkeypatch.setattr(snapshots, "apply_reconciliation", apply_reconciliation)

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
            "--apply",
            "--confirm-month",
            "2026-07",
            "--input-hash",
            "d" * 64,
        ],
    )

    assert result.exit_code == 2
    assert json.loads(result.stdout) == {
        "account_id": "checking-1",
        "can_apply": False,
        "error": blocker,
        "year_month": "2026-07",
    }


def test_snapshots_reconcile_draft_unexpected_error_is_sanitized(monkeypatch, tmp_path):
    """Unexpected draft failures cannot expose private source details."""
    from budget_me.cli.commands import snapshots

    private_failure = "database failed near Private Merchant 1111"
    output = tmp_path / "draft.json"
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(
        snapshots,
        "build_reconciliation_draft",
        MagicMock(side_effect=RuntimeError(private_failure)),
    )

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile-draft",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--output",
            str(output),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == (
        "Reconciliation draft could not be built"
    )
    assert private_failure not in result.stdout
    assert not output.exists()


def test_snapshots_reconcile_preview_unexpected_error_is_sanitized(
    monkeypatch, tmp_path
):
    """Unexpected preview failures return no exception or manifest detail."""
    from budget_me.cli.commands import snapshots

    private_failure = "query failed for Private Merchant 2222"
    manifest_path = _write_private_manifest(tmp_path)
    monkeypatch.setattr(snapshots, "get_read_only_session", _session_context)
    monkeypatch.setattr(
        snapshots,
        "build_reconciliation_preview",
        MagicMock(side_effect=RuntimeError(private_failure)),
    )

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "Reconciliation preview failed"
    assert private_failure not in result.stdout
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout


def test_snapshots_reconcile_apply_unexpected_error_is_sanitized(monkeypatch, tmp_path):
    """Unexpected apply failures emit a fixed message rather than private context."""
    from budget_me.cli.commands import snapshots

    private_failure = "write failed for Private Merchant 3333"
    manifest_path = _write_private_manifest(tmp_path)
    monkeypatch.setattr(snapshots, "get_session", _session_context)
    monkeypatch.setattr(
        snapshots,
        "apply_reconciliation",
        MagicMock(side_effect=RuntimeError(private_failure)),
    )

    result = runner.invoke(
        app,
        [
            "snapshots",
            "reconcile",
            "--month",
            "2026-07",
            "--account",
            "checking-1",
            "--manifest",
            str(manifest_path),
            "--apply",
            "--confirm-month",
            "2026-07",
            "--input-hash",
            "d" * 64,
        ],
    )

    assert result.exit_code == 1
    assert json.loads(result.stdout)["error"] == "Reconciliation apply failed"
    assert private_failure not in result.stdout
    assert _PRIVATE_TRANSACTION_HINT not in result.stdout
