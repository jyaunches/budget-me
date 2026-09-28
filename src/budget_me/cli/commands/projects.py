"""Projects command - roll up spending by cross-month project tag."""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.repos.transactions import TransactionsRepo

console = Console()


def projects_command(
    tag: str | None = typer.Option(
        None,
        "--tag",
        "-t",
        help="Show only this project tag (with a per-month breakdown).",
    ),
):
    """Show total spending for each project tag across all months.

    Project tags are budget-neutral labels (e.g. "example_project_2027", "landscaping")
    that link transactions across different months, accounts, and categories so
    you can see the full cost of a trip or job in one place.
    """
    try:
        asyncio.run(_projects_async(tag))
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


async def _projects_async(tag: str | None) -> None:
    async with get_async_session() as session:
        repo = TransactionsRepo(session)
        summaries = await repo.get_project_summary(project_tag=tag)

    if not summaries:
        if tag:
            console.print(f"\n[yellow]No transactions tagged '{tag}'.[/yellow]\n")
        else:
            console.print("\n[yellow]No project-tagged transactions yet.[/yellow]")
            console.print(
                "Tag transactions on the Streamlit Transactions page to start "
                "tracking a project.\n"
            )
        return

    # Detail view (single tag, or whenever a specific tag was requested)
    if tag or len(summaries) == 1:
        for s in summaries:
            table = Table(title=f"Project: {s['project_tag']}")
            table.add_column("Month")
            table.add_column("Spend", justify="right")
            table.add_column("Txns", justify="right")
            for m in s["months"]:
                table.add_row(m["month"], f"${m['total']:,.2f}", str(m["count"]))
            table.add_section()
            table.add_row(
                "[bold]Total[/bold]",
                f"[bold]${s['total']:,.2f}[/bold]",
                f"[bold]{s['count']}[/bold]",
            )
            console.print(table)
        return

    # Overview (all tags)
    table = Table(title="Project Spending (all months)")
    table.add_column("Project")
    table.add_column("Total Spend", justify="right")
    table.add_column("Txns", justify="right")
    table.add_column("Months", justify="right")
    for s in sorted(summaries, key=lambda x: x["total"], reverse=True):
        table.add_row(
            s["project_tag"],
            f"${s['total']:,.2f}",
            str(s["count"]),
            str(len(s["months"])),
        )
    console.print(table)
    console.print(
        "\nUse [bold]budget-me projects --tag <name>[/bold] for a monthly breakdown.\n"
    )
