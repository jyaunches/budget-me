"""Status command - show Plaid items and sync status."""

import asyncio
from datetime import UTC, datetime

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.models.plaid_item import PlaidItemStatus
from budget_me.db.repos.items import ItemsRepo
from budget_me.notifications.telegram import is_configured as telegram_is_configured

console = Console()


def status_command():
    """Show status of connected bank accounts and sync state.

    Displays:
    - Connected institutions
    - Item status (active, error, relink required)
    - Last successful sync time
    - Any error messages
    """
    try:
        asyncio.run(_status_command_async())
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


async def _status_command_async():
    """Async implementation of status command."""
    async with get_async_session() as session:
        items_repo = ItemsRepo(session)
        items = await items_repo.get_all()

        if not items:
            console.print("\n[yellow]No connected bank accounts.[/yellow]")
            console.print(
                "\nUse [bold]budget-me link[/bold] to connect a bank account.\n"
            )
            return

        # Create status table
        table = Table(title="Connected Bank Accounts")
        table.add_column("Institution", style="cyan")
        table.add_column("Status", style="bold")
        table.add_column("Last Sync", style="dim")
        table.add_column("Notes", style="yellow")

        for item in items:
            # Format status with color
            if item.status == PlaidItemStatus.ACTIVE:
                status_display = "[green]Active[/green]"
            elif item.status == PlaidItemStatus.RELINK_REQUIRED:
                status_display = "[yellow]Relink Required[/yellow]"
            elif item.status == PlaidItemStatus.REVOKED:
                status_display = "[red]Revoked[/red]"
            elif item.status == PlaidItemStatus.PENDING:
                status_display = "[yellow]Pending[/yellow]"
            else:
                status_display = str(item.status.value)

            # Format last sync time
            if item.last_success_at:
                now = datetime.now(UTC)
                delta = now - item.last_success_at
                if delta.days > 0:
                    last_sync = f"{delta.days}d ago"
                elif delta.seconds > 3600:
                    last_sync = f"{delta.seconds // 3600}h ago"
                elif delta.seconds > 60:
                    last_sync = f"{delta.seconds // 60}m ago"
                else:
                    last_sync = "just now"
            else:
                last_sync = "Never"

            # Format notes/errors
            notes = ""
            if item.status == PlaidItemStatus.RELINK_REQUIRED:
                notes = "Login required - run 'budget-me link' again"
            elif item.last_error_message:
                notes = f"{item.last_error_code or 'ERROR'}: {item.last_error_message}"

            table.add_row(
                item.institution_id or item.item_id,
                status_display,
                last_sync,
                notes,
            )

        console.print()
        console.print(table)
        console.print()

        # Show notification platform status
        notification_table = Table(title="Notification Platform")
        notification_table.add_column("Platform", style="cyan")
        notification_table.add_column("Status", style="bold")
        notification_table.add_column("Configuration", style="dim")

        # Telegram status
        if telegram_is_configured():
            notification_table.add_row(
                "Telegram",
                "[green]Enabled[/green]",
                "Configured",
            )
        else:
            notification_table.add_row(
                "Telegram",
                "[dim]Not configured[/dim]",
                "Set TELEGRAM_* env vars",
            )

        console.print(notification_table)
        console.print()
