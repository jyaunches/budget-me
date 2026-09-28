"""Backfill command - fetch historical transactions from Plaid.

This command uses Plaid's /transactions/get endpoint to backfill historical
transactions for accounts that are missing data from the incremental sync.
"""

import asyncio
from uuid import UUID

import typer
from rich.console import Console

from budget_me.plaid.historical_transactions import (
    fetch_historical_for_account_mask,
    fetch_historical_transactions,
)

console = Console()


def backfill_command(
    item_id: str = typer.Option(
        ...,
        "--item-id",
        help="Plaid item UUID to fetch transactions for.",
    ),
    days: int = typer.Option(
        180,
        "--days",
        help="Number of days of history to fetch (default: 180).",
    ),
    account_mask: str | None = typer.Option(
        None,
        "--account-mask",
        help="Optional: Only fetch for account with this mask (last 4 digits).",
    ),
):
    """Backfill historical transactions using Plaid /transactions/get.

    Unlike the regular sync (which is incremental), this fetches all transactions
    in a date range. Use this to backfill missing historical data.

    Examples:

        # Backfill 180 days for all accounts in an item
        budget-me backfill-transactions --item-id <uuid>

        # Backfill 365 days for a specific account by mask
        budget-me backfill-transactions --item-id <uuid> --account-mask 0000 --days 365
    """
    try:
        asyncio.run(_backfill_async(item_id, days, account_mask))
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(2)


async def _backfill_async(
    item_id_str: str,
    days: int,
    account_mask: str | None,
) -> None:
    """Async implementation of backfill command."""
    # Parse item_id
    try:
        item_id = UUID(item_id_str)
    except ValueError:
        console.print(f"[bold red]Error:[/bold red] Invalid UUID: {item_id_str}")
        raise typer.Exit(2)

    console.print("\n[bold]Backfilling transactions[/bold]")
    console.print(f"  Item ID: {item_id}")
    console.print(f"  Days: {days}")
    if account_mask:
        console.print(f"  Account mask: {account_mask}")
    console.print()

    try:
        if account_mask:
            result = await fetch_historical_for_account_mask(
                item_id=item_id,
                account_mask=account_mask,
                days=days,
            )
        else:
            result = await fetch_historical_transactions(
                item_id=item_id,
                days=days,
            )
    except ValueError as e:
        console.print(f"[bold red]Error:[/bold red] {e}")
        raise typer.Exit(2)

    # Display results
    console.print("[bold]Results:[/bold]")
    console.print(f"  Transactions fetched: {result.transactions_fetched}")
    console.print(f"  Transactions added: [green]{result.transactions_added}[/green]")
    console.print(
        f"  Transactions updated: [yellow]{result.transactions_updated}[/yellow]"
    )

    if result.oldest_date and result.newest_date:
        console.print(f"  Date range: {result.oldest_date} to {result.newest_date}")

    console.print("\n[bold green]✓[/bold green] Backfill complete!\n")
