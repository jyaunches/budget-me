"""Synchronize Plaid investment holdings and transaction history."""

import asyncio
import json
from dataclasses import asdict
from uuid import UUID

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.repos import ItemsRepo
from budget_me.plaid.investments_sync import sync_investments

console = Console()


def investments_command(
    item_id: str | None = typer.Option(
        None, "--item-id", help="Sync one internal Plaid Item UUID."
    ),
    holdings_only: bool = typer.Option(
        False,
        "--holdings-only",
        help="Skip the up-to-24-month investment transaction history.",
    ),
    json_output: bool = typer.Option(False, "--json", help="Output JSON."),
) -> None:
    """Pull investment holdings, securities, and contribution history."""
    try:
        asyncio.run(
            _investments_command_async(
                item_id=item_id,
                holdings_only=holdings_only,
                json_output=json_output,
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(1) from exc


async def _investments_command_async(
    *, item_id: str | None, holdings_only: bool, json_output: bool
) -> None:
    requested_id = UUID(item_id) if item_id else None
    async with get_async_session() as session:
        items_repo = ItemsRepo(session)
        if requested_id:
            item = await items_repo.get_by_id(requested_id)
            items = [item] if item else []
        else:
            items = await items_repo.find_active()

    investment_items = [
        item for item in items if item and "investments" in (item.products or [])
    ]
    if requested_id and not investment_items:
        raise ValueError("The requested Item does not have Investments enabled")

    results = []
    for item in investment_items:
        result = await sync_investments(item.id, include_transactions=not holdings_only)
        results.append(
            {
                "item_id": str(item.id),
                "institution": item.institution_name or item.institution_id,
                **asdict(result),
            }
        )

    if json_output:
        print(json.dumps(results, indent=2))
        return

    if not results:
        console.print("[yellow]No active Investments-enabled Items found.[/yellow]")
        return

    table = Table(title="Investment Sync Results")
    table.add_column("Institution")
    table.add_column("Holdings", justify="right")
    table.add_column("Transactions added", justify="right")
    table.add_column("Transactions updated", justify="right")
    for result in results:
        table.add_row(
            result["institution"] or result["item_id"],
            str(result["holdings_updated"]),
            str(result["transactions_added"]),
            str(result["transactions_updated"]),
        )
    console.print(table)
