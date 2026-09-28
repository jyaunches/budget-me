"""Recurring transactions command - show recurring payment streams."""

import asyncio
import json

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.repos import ItemsRepo
from budget_me.plaid.recurring_transactions import get_recurring_transactions

console = Console()


def recurring_command(
    item_id: str | None = typer.Option(
        None,
        "--item-id",
        help="Filter by specific Plaid item ID.",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON instead of rich table.",
    ),
):
    """Show recurring transaction streams detected by Plaid.

    Displays:
    - Recurring payment streams (outflows)
    - Merchant names and descriptions
    - Average amounts and frequencies
    - Status (active/inactive)
    - Account associations
    """
    try:
        asyncio.run(_recurring_command_async(item_id, json_output))
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


async def _recurring_command_async(item_id_str: str | None, json_output: bool):
    """Async implementation of recurring command."""
    async with get_async_session() as session:
        items_repo = ItemsRepo(session)

        # Get items to process
        if item_id_str:
            import uuid

            item_id = uuid.UUID(item_id_str)
            item = await items_repo.get_by_id(item_id)
            if not item:
                console.print(
                    f"\n[bold red]Error:[/bold red] Item {item_id} not found\n"
                )
                raise typer.Exit(1)
            items = [item]
        else:
            items = await items_repo.find_active()

        if not items:
            if json_output:
                print("[]")
            else:
                console.print("\n[yellow]No active Plaid items found.[/yellow]")
                console.print(
                    "\nRun [bold]budget-me link[/bold] to connect a bank account.\n"
                )
            return

        # Fetch recurring transactions for each item
        all_streams = []
        for item in items:
            try:
                streams = await get_recurring_transactions(item.id)
                for stream in streams:
                    # Attach item info for display
                    all_streams.append((item, stream))
            except Exception as e:
                if not json_output:
                    console.print(
                        f"[yellow]Warning:[/yellow] Failed to fetch recurring "
                        f"transactions for {item.institution_id or item.item_id}: {e}"
                    )

        if not all_streams:
            if json_output:
                print("[]")
            else:
                console.print(
                    "\n[yellow]No recurring transaction streams found.[/yellow]\n"
                )
            return

        if json_output:
            _output_json(all_streams)
        else:
            _output_table(all_streams)


def _output_json(streams_with_items):
    """Output recurring streams as JSON."""
    data = []
    for item, stream in streams_with_items:
        stream_data = {
            "institution": item.institution_id or item.item_id,
            "stream_id": stream.stream_id,
            "account_id": stream.account_id,
            "description": stream.description,
            "merchant_name": stream.merchant_name,
            "average_amount": str(stream.average_amount),
            "last_amount": str(stream.last_amount) if stream.last_amount else None,
            "frequency": stream.frequency,
            "status": stream.status,
            "is_active": stream.is_active,
            "category": stream.category,
            "first_date": str(stream.first_date) if stream.first_date else None,
            "last_date": str(stream.last_date) if stream.last_date else None,
        }
        data.append(stream_data)

    print(json.dumps(data, indent=2))


def _output_table(streams_with_items):
    """Output recurring streams as Rich table."""
    # Group by institution
    by_institution = {}
    for item, stream in streams_with_items:
        institution_display = item.institution_id or item.item_id
        if institution_display not in by_institution:
            by_institution[institution_display] = []
        by_institution[institution_display].append(stream)

    for institution, streams in by_institution.items():
        # Create table for this institution
        table = Table(title=f"Recurring Payments - {institution}")
        table.add_column("Description", style="cyan")
        table.add_column("Merchant", style="yellow")
        table.add_column("Amount", justify="right", style="bold")
        table.add_column("Frequency", style="")
        table.add_column("Status", style="")
        table.add_column("Category", style="dim")

        for stream in streams:
            # Format amount
            amount_display = f"${stream.average_amount:,.2f}"
            if stream.last_amount and stream.last_amount != stream.average_amount:
                amount_display += f"\n(last: ${stream.last_amount:,.2f})"

            # Format status
            status_display = stream.status
            if stream.is_active:
                status_display = f"[green]{status_display}[/green]"
            else:
                status_display = f"[red]{status_display}[/red]"

            # Format category
            category_display = " > ".join(stream.category) if stream.category else "N/A"

            # Format merchant
            merchant_display = stream.merchant_name or "N/A"

            table.add_row(
                stream.description,
                merchant_display,
                amount_display,
                stream.frequency,
                status_display,
                category_display,
            )

        console.print()
        console.print(table)

        # Show date range
        console.print(
            f"[dim]Showing {len(streams)} recurring payment stream(s) "
            f"for {institution}[/dim]"
        )
        console.print()
