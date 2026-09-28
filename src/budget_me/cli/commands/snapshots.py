"""Review, initialize, and safely close monthly snapshots."""

import json
import os
import stat
from decimal import Decimal
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.models.monthly_snapshot import MonthlySnapshot
from budget_me.snapshots.initialization import (
    build_initialization_preview,
    initialize_snapshot,
)
from budget_me.snapshots.reconciliation import (
    apply_reconciliation,
    build_reconciliation_draft,
    build_reconciliation_preview,
)
from budget_me.snapshots.reconciliation_manifest import (
    ReconciliationManifest,
    parse_reconciliation_manifest,
)
from budget_me.snapshots.service import (
    SnapshotClosePreview,
    build_close_preview,
    close_snapshot,
    get_account_transaction_counts,
    get_read_only_session,
    list_included_depository_accounts,
)
from budget_me.streamlit_app.db import get_session

snapshots_app = typer.Typer(
    name="snapshots",
    help="Initialize, reconcile, review, and safely close monthly snapshots.",
)
console = Console()


def _money(value: Decimal | None) -> str:
    """Serialize an aggregate currency value without converting through float."""
    return format(value if value is not None else Decimal("0.00"), ".2f")


def _initialization_result(
    snapshot: MonthlySnapshot, *, audit_hash: str
) -> dict[str, object]:
    """Build an aggregate-only result before the write session commits and closes."""
    status = getattr(snapshot.status, "value", snapshot.status)
    return {
        "year_month": snapshot.year_month,
        "account_id": snapshot.account_id,
        "status": status,
        "initialized": True,
        "totals": {
            "income_total": _money(snapshot.income_total),
            "expense_total": _money(snapshot.expense_total),
            "transfer_in_total": _money(snapshot.transfer_in_total),
            "transfer_out_total": _money(snapshot.transfer_out_total),
            "reimbursement_in_total": _money(snapshot.reimbursement_in_total),
            "reimbursement_out_total": _money(snapshot.reimbursement_out_total),
            "credit_card_total": _money(snapshot.credit_card_total),
            "net": _money(snapshot.net),
        },
        "last_synced_at": (
            snapshot.last_synced_at.isoformat() if snapshot.last_synced_at else None
        ),
        "audit_hash": audit_hash,
    }


def _emit_initialization_error(
    month: str, account_id: str, message: str, *, blocker: bool = False
) -> None:
    """Emit initialization failures as aggregate JSON, including blocker state."""
    payload: dict[str, object] = {
        "year_month": month,
        "account_id": account_id,
        "can_initialize": False,
        "error": message,
    }
    if blocker:
        payload["blockers"] = [message.removeprefix("Cannot initialize snapshot: ")]
    typer.echo(json.dumps(payload, sort_keys=True))


def _render_preview(preview: SnapshotClosePreview) -> None:
    """Render a close preview without transaction-level financial detail."""
    table = Table(title=f"{preview.year_month} — {preview.account_name}")
    table.add_column("Metric")
    table.add_column("Amount", justify="right")
    rows = (
        ("Income", preview.totals.income_total),
        ("Expenses", preview.totals.expense_total),
        ("Transfers in", preview.totals.transfer_in_total),
        ("Transfers out", preview.totals.transfer_out_total),
        ("Reimbursements in", preview.totals.reimbursement_in_total),
        ("Reimbursements out", preview.totals.reimbursement_out_total),
        ("Card payments (planned)", preview.planned_credit_card_total),
        ("Card payments (posted)", preview.actual_credit_card_total),
        ("Card payments (remaining)", preview.remaining_credit_card_total),
        ("Net actual cash flow", preview.totals.net),
        ("Starting balance", preview.starting_balance),
        ("Captured month-end balance", preview.captured_closing_balance),
        ("Projected close", preview.projected_closing_balance),
        ("Close to freeze", preview.closing_balance_to_freeze),
        ("Captured difference", preview.captured_difference),
    )
    for label, value in rows:
        table.add_row(label, f"${value:,.2f}" if value is not None else "—")
    console.print(table)
    synced = preview.last_synced_at.isoformat() if preview.last_synced_at else "never"
    console.print(f"Last reconciled: {synced}")
    counts = preview.transaction_counts
    console.print(
        f"Posted: {counts.posted} · Unreviewed: {counts.unreviewed} · "
        f"Uncategorized: {counts.uncategorized} · "
        f"Reimbursable: {counts.reimbursable} · Pending: {counts.pending} · "
        f"Cards missing actuals: {preview.missing_actual_credit_card_count}"
    )
    console.print(f"Audit hash: {preview.audit_hash}")
    if preview.blockers:
        console.print("[bold red]Close blockers:[/bold red]")
        for blocker in preview.blockers:
            console.print(f"  - {blocker}")
    else:
        console.print("[green]Ready to close with explicit confirmation.[/green]")


@snapshots_app.command("review")
def review_command(
    month: str = typer.Option(..., "--month", "-m", help="Month as YYYY-MM."),
    account_id: str | None = typer.Option(
        None,
        "--account",
        "-a",
        help="Depository account id; omit to review every included account.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Emit a stable machine-readable preview."
    ),
) -> None:
    """Review one or every included account without creating snapshots."""
    try:
        with get_read_only_session() as session:
            if account_id:
                preview = build_close_preview(session, month, account_id)
                entries = [preview.to_dict()]
                previews = [preview]
            else:
                accounts = list_included_depository_accounts(session)
                if not accounts:
                    raise ValueError("No included depository accounts found")
                entries = []
                previews = []
                for account in accounts:
                    counts = get_account_transaction_counts(
                        session, month, account.account_id
                    )
                    try:
                        preview = build_close_preview(
                            session, month, account.account_id
                        )
                    except ValueError as exc:
                        entries.append(
                            {
                                "year_month": month,
                                "account_id": account.account_id,
                                "account_name": account.display_name or account.name,
                                "status": "missing",
                                "transaction_counts": counts.to_dict(),
                                "blockers": [str(exc)],
                                "can_close": False,
                            }
                        )
                    else:
                        previews.append(preview)
                        entries.append(preview.to_dict())
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if account_id:
        payload: dict | list = entries[0]
    else:
        payload = {
            "year_month": month,
            "accounts": entries,
            "can_close": all(entry["can_close"] for entry in entries),
        }

    if json_output:
        typer.echo(json.dumps(payload, sort_keys=True))
    else:
        rendered_ids = set()
        for preview in previews:
            _render_preview(preview)
            rendered_ids.add(preview.account_id)
        for entry in entries:
            if entry["account_id"] in rendered_ids:
                continue
            counts = entry["transaction_counts"]
            console.print(
                f"[bold red]{entry['account_name']} — snapshot missing[/bold red]"
            )
            console.print(
                f"Posted: {counts['posted']} · Unreviewed: {counts['unreviewed']} · "
                f"Uncategorized: {counts['uncategorized']} · Pending: {counts['pending']}"
            )
            for blocker in entry["blockers"]:
                console.print(f"  - {blocker}")

    if any(not entry["can_close"] for entry in entries):
        raise typer.Exit(2)


@snapshots_app.command("initialize")
def initialize_command(
    month: str = typer.Option(..., "--month", "-m", help="Month as YYYY-MM."),
    account_id: str = typer.Option(
        ..., "--account", "-a", help="Depository account id."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Create the snapshot after every guard succeeds."
    ),
    confirm_month: str | None = typer.Option(
        None,
        "--confirm-month",
        help="Required with --apply; must exactly match --month.",
    ),
    audit_hash: str | None = typer.Option(
        None,
        "--audit-hash",
        help="Required with --apply; copy it from a fresh preview.",
    ),
) -> None:
    """Preview a missing snapshot by default; initialize only with explicit proofs."""
    if not apply:
        try:
            with get_read_only_session() as session:
                preview = build_initialization_preview(session, month, account_id)
        except Exception as exc:
            _emit_initialization_error(month, account_id, str(exc))
            raise typer.Exit(1) from exc

        typer.echo(json.dumps(preview.to_dict(), sort_keys=True))
        if preview.blockers:
            raise typer.Exit(2)
        return

    if not confirm_month or not audit_hash:
        _emit_initialization_error(
            month,
            account_id,
            "--apply requires --confirm-month and --audit-hash",
        )
        raise typer.Exit(1)
    if confirm_month != month:
        _emit_initialization_error(
            month,
            account_id,
            "--confirm-month must exactly match --month",
        )
        raise typer.Exit(1)

    try:
        with get_session() as session:
            snapshot = initialize_snapshot(
                session,
                month,
                account_id,
                confirm_month=confirm_month,
                audit_hash=audit_hash,
            )
            result = _initialization_result(snapshot, audit_hash=audit_hash)
    except ValueError as exc:
        message = str(exc)
        is_blocker = message.startswith("Cannot initialize snapshot: ")
        _emit_initialization_error(
            month,
            account_id,
            message,
            blocker=is_blocker,
        )
        raise typer.Exit(2 if is_blocker else 1) from exc
    except Exception as exc:
        _emit_initialization_error(month, account_id, str(exc))
        raise typer.Exit(1) from exc

    typer.echo(json.dumps(result, sort_keys=True))


def _require_private_manifest(path: Path) -> Path:
    """Require an owned, regular manifest with no group/world permissions."""
    resolved = path.expanduser()
    try:
        metadata = resolved.lstat()
    except OSError as exc:
        raise ValueError("Manifest file is not accessible") from exc
    if not stat.S_ISREG(metadata.st_mode):
        raise ValueError("Manifest path must be a regular file, not a symlink")
    if metadata.st_uid != os.getuid():
        raise ValueError("Manifest file must be owned by the current user")
    if stat.S_IMODE(metadata.st_mode) & 0o077:
        raise ValueError("Manifest permissions must be private (0600 or stricter)")
    return resolved


def _load_private_manifest(path: Path) -> ReconciliationManifest:
    """Load a protected data-only manifest without rendering its contents."""
    protected_path = _require_private_manifest(path)
    flags = os.O_RDONLY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(protected_path, flags)
        metadata = os.fstat(descriptor)
        if (
            not stat.S_ISREG(metadata.st_mode)
            or metadata.st_uid != os.getuid()
            or stat.S_IMODE(metadata.st_mode) & 0o077
        ):
            raise ValueError("Manifest changed while it was being opened")
        if metadata.st_size > 10 * 1024 * 1024:
            raise ValueError("Manifest exceeds the 10 MiB local safety limit")
        with os.fdopen(descriptor, "r", encoding="utf-8") as handle:
            descriptor = -1
            content = handle.read()
        return parse_reconciliation_manifest(content)
    except Exception as exc:
        if "descriptor" in locals() and descriptor >= 0:
            os.close(descriptor)
        raise ValueError(
            "Manifest validation failed; inspect the protected file locally"
        ) from exc


def _write_private_manifest(path: Path, manifest: ReconciliationManifest) -> None:
    """Create a non-overwriting 0600 JSON draft without following symlinks."""
    destination = path.expanduser()
    if not destination.parent.is_dir():
        raise ValueError("Manifest destination parent does not exist")
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    try:
        descriptor = os.open(destination, flags, 0o600)
    except FileExistsError as exc:
        raise ValueError(
            "Manifest destination already exists; refusing overwrite"
        ) from exc
    except OSError as exc:
        raise ValueError("Manifest destination could not be created") from exc
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(
                manifest.model_dump(mode="json", exclude_none=True),
                handle,
                indent=2,
                sort_keys=True,
            )
            handle.write("\n")
    except Exception:
        try:
            destination.unlink()
        except OSError:
            pass
        raise


@snapshots_app.command("reconcile-draft")
def reconcile_draft_command(
    month: str = typer.Option(..., "--month", "-m", help="Month as YYYY-MM."),
    account_id: str = typer.Option(
        ..., "--account", "-a", help="Depository account id."
    ),
    output: Path = typer.Option(
        ...,
        "--output",
        "-o",
        help="New private JSON manifest path; must not already exist.",
    ),
) -> None:
    """Create a protected draft; every suggested transaction remains unlocked."""
    try:
        with get_read_only_session() as session:
            manifest = build_reconciliation_draft(session, month, account_id)
    except Exception as exc:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "created": False,
                    "error": "Reconciliation draft could not be built",
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc
    try:
        _write_private_manifest(output, manifest)
    except Exception as exc:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "created": False,
                    "error": str(exc),
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc

    typer.echo(
        json.dumps(
            {
                "year_month": month,
                "account_id": account_id,
                "created": True,
                "output": str(output),
                "transaction_decision_count": len(manifest.transaction_decisions),
                "line_item_decision_count": len(manifest.line_item_decisions),
                "manual_review_required": True,
            },
            sort_keys=True,
        )
    )


@snapshots_app.command("reconcile")
def reconcile_command(
    month: str = typer.Option(..., "--month", "-m", help="Month as YYYY-MM."),
    account_id: str = typer.Option(
        ..., "--account", "-a", help="Depository account id."
    ),
    manifest_path: Path = typer.Option(
        ..., "--manifest", help="Private 0600 YAML or JSON decision manifest."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Persist a receipt and refresh snapshot actuals."
    ),
    confirm_month: str | None = typer.Option(
        None,
        "--confirm-month",
        help="Required with --apply; must exactly match --month.",
    ),
    input_hash: str | None = typer.Option(
        None,
        "--input-hash",
        help="Required with --apply; copy it from a fresh preview.",
    ),
) -> None:
    """Preview a private manifest by default; apply only with exact proofs."""
    try:
        manifest = _load_private_manifest(manifest_path)
    except Exception as exc:
        typer.echo(json.dumps({"can_apply": False, "error": str(exc)}, sort_keys=True))
        raise typer.Exit(1) from exc
    if manifest.year_month != month or manifest.account_id != account_id:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "can_apply": False,
                    "error": "Manifest target must exactly match --month and --account",
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1)

    if not apply:
        try:
            with get_read_only_session() as session:
                preview = build_reconciliation_preview(session, manifest)
        except Exception as exc:
            typer.echo(
                json.dumps(
                    {
                        "year_month": month,
                        "account_id": account_id,
                        "can_apply": False,
                        "error": "Reconciliation preview failed",
                    },
                    sort_keys=True,
                )
            )
            raise typer.Exit(1) from exc
        typer.echo(json.dumps(preview.to_dict(), sort_keys=True))
        if preview.blockers:
            raise typer.Exit(2)
        return

    if not confirm_month or not input_hash:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "can_apply": False,
                    "error": "--apply requires --confirm-month and --input-hash",
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1)
    if confirm_month != month:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "can_apply": False,
                    "error": "--confirm-month must exactly match --month",
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1)

    try:
        with get_session() as session:
            preview = apply_reconciliation(
                session,
                manifest,
                confirm_month=confirm_month,
                input_hash=input_hash,
            )
            result = preview.to_dict()
    except ValueError as exc:
        message = str(exc)
        blocker = message.startswith("Cannot apply reconciliation: ")
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "can_apply": False,
                    "error": message,
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(2 if blocker else 1) from exc
    except Exception as exc:
        typer.echo(
            json.dumps(
                {
                    "year_month": month,
                    "account_id": account_id,
                    "can_apply": False,
                    "error": "Reconciliation apply failed",
                },
                sort_keys=True,
            )
        )
        raise typer.Exit(1) from exc

    result["applied"] = not preview.is_idempotent
    typer.echo(json.dumps(result, sort_keys=True))


@snapshots_app.command("close")
def close_command(
    month: str = typer.Option(..., "--month", "-m", help="Month as YYYY-MM."),
    account_id: str = typer.Option(
        ..., "--account", "-a", help="Depository account id."
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="Preview only; never save changes."
    ),
    apply: bool = typer.Option(
        False, "--apply", help="Apply the close after every guard succeeds."
    ),
    confirm_month: str | None = typer.Option(
        None,
        "--confirm-month",
        help="Required with --apply; must exactly match --month.",
    ),
    audit_hash: str | None = typer.Option(
        None,
        "--audit-hash",
        help="Required with --apply; copy it from a fresh preview.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Emit JSON output."),
) -> None:
    """Preview by default; write only with apply, confirmation, and audit hash."""
    if dry_run and apply:
        console.print("[bold red]Error:[/bold red] choose --dry-run or --apply")
        raise typer.Exit(1)

    if not apply:
        try:
            with get_read_only_session() as session:
                preview = build_close_preview(session, month, account_id)
        except Exception as exc:
            console.print(f"[bold red]Error:[/bold red] {exc}")
            raise typer.Exit(1) from exc
        if json_output:
            typer.echo(json.dumps(preview.to_dict(), sort_keys=True))
        else:
            _render_preview(preview)
            console.print("[yellow]DRY RUN — no changes saved.[/yellow]")
        if preview.blockers:
            raise typer.Exit(2)
        return

    if not confirm_month or not audit_hash:
        console.print(
            "[bold red]Error:[/bold red] --apply requires --confirm-month "
            "and --audit-hash"
        )
        raise typer.Exit(1)

    try:
        with get_session() as session:
            preview = close_snapshot(
                session,
                month,
                account_id,
                confirm_month=confirm_month,
                audit_hash=audit_hash,
            )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc

    if json_output:
        result = preview.to_dict()
        result["status"] = "closed"
        typer.echo(json.dumps(result, sort_keys=True))
    else:
        console.print(
            f"[green]Closed {month} for {preview.account_name} at "
            f"${preview.closing_balance_to_freeze:,.2f}.[/green]"
        )
