"""Add Liabilities command - add liabilities product to existing Plaid items."""

import uuid
import warnings
import webbrowser

import typer
from rich.console import Console

from budget_me.db.engine import get_async_session, get_engine
from budget_me.db.repos import ItemsRepo
from budget_me.server.link_server import start_link_server

console = Console()


def add_liabilities_command(
    item_id: str | None = typer.Option(
        None,
        "--item-id",
        help="Specific item ID to add liabilities to. If not provided, processes all items.",
    ),
):
    """Add liabilities product to existing Plaid items.

    This command allows you to add the Liabilities product to existing bank
    connections without re-linking the account. This enables tracking of
    credit card APR information, promotional rates, and payment details.

    If --item-id is provided, only that item is upgraded.
    If no --item-id is provided, all active items are processed sequentially.

    Press Ctrl+C to stop when done.
    """
    warnings.warn(
        "The 'budget-me add-liabilities' command is deprecated. "
        "New bank connections via the Streamlit app's Link Account page "
        "automatically request liabilities data. Existing connections "
        "will need to be re-linked via the Streamlit app.",
        DeprecationWarning,
        stacklevel=2,
    )

    import asyncio

    async def process_items():
        """Load items and process upgrade flow."""
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)

            # Load items
            if item_id:
                # Specific item
                item = await items_repo.get_by_id(uuid.UUID(item_id))
                if not item:
                    console.print(
                        f"\n[bold red]Error:[/bold red] Item {item_id} not found."
                    )
                    raise typer.Exit(1)
                items = [item]
            else:
                # All active items
                items = await items_repo.find_active()
                if not items:
                    console.print("\n[yellow]No active items found.[/yellow]")
                    raise typer.Exit(0)

            return items

    # Run async function to get items
    items = asyncio.run(process_items())

    # Clear the engine cache to avoid event loop conflicts
    # The asyncio.run() above created and closed an event loop, but the engine
    # was cached with connections tied to that closed loop. Clearing the cache
    # ensures FastAPI gets a fresh engine for its own event loop.
    get_engine.cache_clear()

    # Process each item
    for idx, item in enumerate(items, 1):
        if len(items) > 1:
            console.print(
                f"\n[bold cyan]Processing item {idx}/{len(items)}...[/bold cyan]"
            )

        console.print(
            f"\n[bold green]Adding liabilities to item {item.id}...[/bold green]"
        )
        console.print(f"Institution ID: [bold]{item.institution_id}[/bold]")
        console.print("\nThe server will start on [bold]http://localhost:8080[/bold]")
        console.print("Opening your browser...")
        console.print("\n[dim]Press Ctrl+C to skip to next item or stop[/dim]\n")

        try:
            # Open browser to update mode URL
            url = f"http://localhost:8080?mode=update&item_id={item.id}"
            webbrowser.open(url)

            # Start the server (blocks until Ctrl+C)
            start_link_server()

            # If we get here, server stopped normally
            console.print(
                "\n[bold green]Success![/bold green] Liabilities product added."
            )

        except KeyboardInterrupt:
            console.print("\n\n[yellow]Stopped by user.[/yellow]")
            if idx < len(items):
                # Ask if user wants to continue with next item
                if len(items) > 1:
                    console.print("[dim]Moving to next item...[/dim]")
                    continue
            raise typer.Exit(0)
        except Exception as e:
            console.print(f"\n[bold red]Error:[/bold red] {e}")
            if idx < len(items):
                console.print("[yellow]Continuing to next item...[/yellow]")
                continue
            raise typer.Exit(1)

    console.print("\n[bold green]All items processed![/bold green]")
