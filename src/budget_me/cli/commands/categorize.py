"""Categorize command - automatically categorize uncategorized transactions.

Exit Codes:
    0: Success - transactions categorized
    1: Partial success - some transactions categorized
    2: Failure - error occurred
"""

import asyncio

import typer
from rich.console import Console
from rich.table import Table

from budget_me.categorization.inference import MerchantInferenceClient
from budget_me.categorization.search import MerchantSearchClient
from budget_me.categorization.service import CategorizationService
from budget_me.categorization.store import PostgresCategorizationRuleStore
from budget_me.config import get_settings
from budget_me.db.engine import get_async_session
from budget_me.db.repos.accounts_repo import AccountsRepo

console = Console()


def categorize_command(
    days: int = typer.Option(
        1,
        "--days",
        "-d",
        help="Number of days to look back for uncategorized transactions.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Don't update database, just show what would be categorized.",
    ),
):
    """Categorize uncategorized transactions.

    Uses a three-tier approach:
    1. Packaged defaults plus PostgreSQL rule overrides
    2. Claude API inference for national brands
    3. Tavily web search for unknown merchants

    New high-confidence merchant rules are learned in PostgreSQL.

    Exit Codes:
        0: Success - transactions categorized
        1: Partial success - some transactions failed
        2: Failure - error occurred
    """
    try:
        exit_code = asyncio.run(_categorize_async(days, dry_run))
        raise typer.Exit(exit_code)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(2)


async def _categorize_async(days: int, dry_run: bool) -> int:
    """Run categorization workflow asynchronously."""
    settings = get_settings()

    # Create API clients (optional - graceful degradation)
    inference = None
    search = None

    if settings.anthropic_api_key:
        inference = MerchantInferenceClient(settings.anthropic_api_key)
        console.print("[green]✓[/green] Claude inference enabled")
    else:
        console.print("[yellow]![/yellow] Claude inference disabled (no API key)")

    if settings.tavily_api_key:
        search = MerchantSearchClient(settings.tavily_api_key)
        console.print("[green]✓[/green] Tavily search enabled")
    else:
        console.print("[yellow]![/yellow] Tavily search disabled (no API key)")

    console.print(f"\nCategorizing transactions from last {days} day(s)...\n")

    # Get excluded accounts and build account names map
    async with get_async_session() as session:
        rule_store = PostgresCategorizationRuleStore(session)
        rule_set = await rule_store.load()
        console.print(
            f"Loaded {len(rule_set.merchants)} merchant rules, "
            f"{len(rule_set.categories)} categories, "
            f"{len(rule_set.reimbursable_merchants)} reimbursable merchants "
            "from packaged defaults and PostgreSQL"
        )
        accounts_repo = AccountsRepo(session)
        excluded_accounts = await accounts_repo.get_excluded()
        excluded_ids = {acc.account_id for acc in excluded_accounts}

        if excluded_ids:
            console.print(
                f"[dim]Excluding {len(excluded_ids)} excluded account(s)[/dim]"
            )

        # Build account names map (display_name or name)
        all_accounts = await accounts_repo.get_all()
        account_names = {
            acc.account_id: acc.display_name or acc.name for acc in all_accounts
        }

        # Run categorization
        service = CategorizationService(
            session,
            rule_set.merchants,
            rule_set.categories,
            inference_client=inference,
            search_client=search,
            reimbursable_rules=rule_set.reimbursable_merchants,
            rule_store=rule_store,
        )
        result = await service.categorize_transactions(
            days=days,
            excluded_account_ids=excluded_ids,
            account_names=account_names,
        )

        # Close search client if used
        if search:
            await search.close()

        if dry_run:
            console.print("\n[yellow]DRY RUN - Rolling back changes[/yellow]")
            await session.rollback()

    # Display results
    _display_results(result, dry_run)

    # Determine exit code
    if result.stats.total_processed == 0:
        return 0  # Nothing to do is success
    elif result.stats.unknown > 0:
        return 1  # Partial success (some unknowns)
    else:
        return 0  # Full success


def _display_results(result, dry_run: bool) -> None:
    """Display categorization results to console."""
    # Stats summary
    console.print("\n[bold]Categorization Results[/bold]")
    console.print(f"  Total processed: {result.stats.total_processed}")
    console.print(f"  From rules: [green]{result.stats.from_rules}[/green]")
    console.print(f"  From inference: [blue]{result.stats.from_inference}[/blue]")
    console.print(f"  From search: [cyan]{result.stats.from_search}[/cyan]")
    console.print(
        f"  Reimbursable flagged: [magenta]{result.stats.reimbursable_flagged}[/magenta]"
    )
    console.print(f"  Skipped: [dim]{result.stats.skipped}[/dim]")
    console.print(f"  Unknown: [yellow]{result.stats.unknown}[/yellow]")

    # New rules learned
    if result.new_rules:
        console.print("\n[bold]New Merchant Rules Learned[/bold]")
        table = Table(show_header=True)
        table.add_column("Merchant", style="cyan")
        table.add_column("Category", style="green")

        for merchant, category in sorted(result.new_rules.items()):
            table.add_row(merchant, category)

        console.print(table)

        if not dry_run:
            console.print("\n[dim]Saved to PostgreSQL for future runs[/dim]")

    # Unknown merchants
    if result.unknowns:
        console.print(
            "\n[bold yellow]Unknown Merchants (Manual Review Needed)[/bold yellow]"
        )
        table = Table(show_header=True)
        table.add_column("Account", style="cyan")
        table.add_column("Date")
        table.add_column("Merchant")
        table.add_column("Amount", justify="right")
        table.add_column("Reason", style="dim")

        for unknown in result.unknowns:
            table.add_row(
                unknown.account_name,
                str(unknown.date),
                unknown.name,
                f"${unknown.amount:.2f}",
                unknown.reason,
            )

        console.print(table)

    if dry_run:
        console.print("\n[yellow]DRY RUN - No changes were saved[/yellow]")
    elif result.stats.total_processed > 0:
        categorized_count = (
            result.stats.from_rules
            + result.stats.from_inference
            + result.stats.from_search
        )
        console.print(
            f"\n[green]✓[/green] Categorized {categorized_count} transaction(s)"
        )
