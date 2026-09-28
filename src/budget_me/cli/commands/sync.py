"""Sync command - synchronize transactions from Plaid.

Exit Codes:
    0: Full success - all items synced successfully
    1: Partial success - some items failed but at least one succeeded
    2: Failure - all items failed, no items to sync, or critical error
"""

import asyncio
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.models.ingest_run import IngestRunStatus, IngestRunType
from budget_me.services.sync_service import SyncService

console = Console()


def sync_command(
    item_id: str | None = typer.Option(
        None,
        "--item-id",
        help="Sync only a specific item (UUID). If not provided, syncs all active items.",
    ),
    run_type: str = typer.Option(
        "manual",
        "--run-type",
        help="Type of sync run: scheduled, manual, or webhook.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON instead of rich table.",
    ),
    include_transactions: bool = typer.Option(
        False,
        "--include-transactions",
        help="Include transaction details in JSON output (limited to 100 per category).",
    ),
):
    """Sync transactions from Plaid.

    This will fetch the latest transactions from Plaid for all active items
    or for a specific item if --item-id is provided.

    The sync is incremental - only new/modified/deleted transactions since
    the last sync will be processed.

    Exit Codes:
        0: Full success - all items synced successfully
        1: Partial success - some items failed
        2: Failure - all items failed or critical error
    """
    try:
        exit_code = asyncio.run(
            _sync_command_async(item_id, run_type, json_output, include_transactions)
        )
        raise typer.Exit(exit_code)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(2)


def _parse_run_type(run_type_str: str) -> IngestRunType:
    """Parse run type string to enum."""
    run_type_map = {
        "scheduled": IngestRunType.SCHEDULED,
        "manual": IngestRunType.MANUAL,
        "webhook": IngestRunType.WEBHOOK,
    }
    if run_type_str.lower() not in run_type_map:
        raise ValueError(
            f"Invalid run type '{run_type_str}'. "
            f"Valid options: {', '.join(run_type_map.keys())}"
        )
    return run_type_map[run_type_str.lower()]


async def _sync_command_async(
    item_id_str: str | None,
    run_type_str: str,
    json_output: bool,
    include_transactions: bool = False,
) -> int:
    """Async implementation of sync command.

    Returns:
        Exit code: 0 for success, 1 for partial, 2 for failure.
    """
    # Validate run type
    try:
        run_type = _parse_run_type(run_type_str)
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        return 2

    # Parse item_id if provided
    item_id = None
    if item_id_str:
        try:
            item_id = UUID(item_id_str)
        except ValueError:
            console.print(f"[bold red]Error:[/bold red] Invalid UUID: {item_id_str}")
            return 2

    async with get_async_session() as session:
        service = SyncService(session)
        result = await service.run_sync(
            run_type=run_type,
            item_id=item_id,
            include_transactions=include_transactions,
        )

    # Output results
    if json_output:
        _output_json(result)
    else:
        _output_rich(result)

    # Determine exit code based on status
    if result.status == IngestRunStatus.COMPLETED:
        return 0
    elif result.status == IngestRunStatus.PARTIAL:
        return 1
    else:  # FAILED
        return 2


def _output_json(result):
    """Output results as JSON."""
    import json
    from datetime import date
    from decimal import Decimal

    def serialize_transactions(transactions):
        """Serialize transaction details to JSON-safe format."""
        if transactions is None:
            return None
        return {
            "added": [
                {
                    "id": str(t.id),
                    "plaid_transaction_id": t.plaid_transaction_id,
                    "date": t.date.isoformat() if isinstance(t.date, date) else t.date,
                    "amount": float(t.amount)
                    if isinstance(t.amount, Decimal)
                    else t.amount,
                    "name": t.name,
                    "account_id": t.account_id,
                }
                for t in transactions.added
            ],
            "modified": [
                {
                    "id": str(t.id),
                    "plaid_transaction_id": t.plaid_transaction_id,
                    "date": t.date.isoformat() if isinstance(t.date, date) else t.date,
                    "amount": float(t.amount)
                    if isinstance(t.amount, Decimal)
                    else t.amount,
                    "name": t.name,
                    "account_id": t.account_id,
                    "changes": t.changes,
                }
                for t in transactions.modified
            ],
            "removed": transactions.removed,
        }

    output = {
        "run_id": str(result.run_id),
        "status": result.status.value,
        "items_total": result.items_total,
        "items_ok": result.items_ok,
        "items_failed": result.items_failed,
        "tx_added": result.tx_added,
        "tx_modified": result.tx_modified,
        "tx_removed": result.tx_removed,
        "duration_ms": result.duration_ms,
        "items": [
            {
                "item_id": str(item.item_id),
                "institution_id": item.institution_id,
                "institution_name": item.institution_name,
                "success": item.success,
                "added": item.added,
                "modified": item.modified,
                "removed": item.removed,
                "duration_ms": item.duration_ms,
                "error_code": item.error_code,
                "error_message": item.error_message,
                "transactions": serialize_transactions(item.transactions),
            }
            for item in result.item_results
        ],
    }
    if result.error_summary:
        output["error_summary"] = result.error_summary

    # Use print() instead of console.print() to avoid Rich word-wrapping
    # which would insert literal newlines and break JSON output
    print(json.dumps(output, indent=2))


def _output_rich(result):
    """Output results as rich formatted table."""
    if result.items_total == 0:
        console.print("[yellow]No active items to sync.[/yellow]")
        console.print("\nUse [bold]budget-me link[/bold] to connect a bank account.")
        return

    console.print(f"\n[bold]Synced {result.items_total} item(s)[/bold]\n")

    # Results table
    results_table = Table(title="Sync Results")
    results_table.add_column("Institution", style="cyan")
    results_table.add_column("Status", justify="center")
    results_table.add_column("Added", style="green", justify="right")
    results_table.add_column("Modified", style="yellow", justify="right")
    results_table.add_column("Removed", style="red", justify="right")
    results_table.add_column("Duration", justify="right")

    for item in result.item_results:
        institution = (
            item.institution_name or item.institution_id or str(item.item_id)[:8]
        )
        status = "[green]✓[/green]" if item.success else "[red]✗[/red]"
        duration = f"{item.duration_ms}ms"

        if item.success:
            results_table.add_row(
                institution,
                status,
                str(item.added),
                str(item.modified),
                str(item.removed),
                duration,
            )
        else:
            results_table.add_row(
                institution,
                status,
                "-",
                "-",
                "-",
                duration,
            )

    console.print(results_table)

    # Summary
    console.print()
    console.print("[bold]Summary:[/bold]")
    console.print(
        f"  Transactions: +{result.tx_added} ~{result.tx_modified} -{result.tx_removed}"
    )
    console.print(f"  Items: {result.items_ok} ok, {result.items_failed} failed")
    console.print(f"  Duration: {result.duration_ms}ms")

    # Final status
    if result.status == IngestRunStatus.COMPLETED:
        console.print("\n[bold green]✓[/bold green] Sync complete!\n")
    elif result.status == IngestRunStatus.PARTIAL:
        console.print("\n[bold yellow]![/bold yellow] Sync completed with errors\n")
        if result.error_summary:
            console.print(f"[yellow]Errors: {result.error_summary}[/yellow]\n")
    else:
        console.print("\n[bold red]✗[/bold red] Sync failed\n")
        if result.error_summary:
            console.print(f"[red]Errors: {result.error_summary}[/red]\n")
