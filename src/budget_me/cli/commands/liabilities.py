"""Liabilities command - show credit card APR and payment information."""

import asyncio
import json
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table

from budget_me.db.engine import get_async_session
from budget_me.db.models.credit_liability import AprType
from budget_me.db.repos.liabilities_repo import LiabilitiesRepo

console = Console()


def liabilities_command(
    account: str | None = typer.Option(
        None,
        "--account",
        help="Filter by account name or mask (last 4 digits).",
    ),
    json_output: bool = typer.Option(
        False,
        "--json",
        help="Output results as JSON instead of rich table.",
    ),
):
    """Show credit card liabilities with APR and payment information.

    Displays:
    - Account names and balances
    - APR details including promotional rates
    - Payment due dates and minimum amounts
    - Overdue status
    """
    try:
        asyncio.run(_liabilities_command_async(account, json_output))
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


async def _liabilities_command_async(account_filter: str | None, json_output: bool):
    """Async implementation of liabilities command."""
    async with get_async_session() as session:
        liabilities_repo = LiabilitiesRepo(session)
        liabilities = await liabilities_repo.get_all_with_details()

        if not liabilities:
            if json_output:
                print("[]")
            else:
                console.print("\n[yellow]No liability data found.[/yellow]")
                console.print(
                    "\nRun [bold]budget-me add-liabilities[/bold] to enable Liabilities "
                    "product for your connected accounts.\n"
                )
            return

        # Filter by account name or mask if provided
        if account_filter:
            liabilities = [
                liability
                for liability in liabilities
                if liability.account
                and (
                    account_filter.lower() in liability.account.name.lower()
                    or (
                        liability.account.mask
                        and account_filter in liability.account.mask
                    )
                )
            ]

            if not liabilities:
                if json_output:
                    print("[]")
                else:
                    console.print(
                        f"\n[yellow]No liabilities found matching '{account_filter}'.[/yellow]\n"
                    )
                return

        if json_output:
            _output_json(liabilities)
        else:
            _output_table(liabilities)


def _output_json(liabilities):
    """Output liabilities as JSON."""
    data = []
    for liability in liabilities:
        account = liability.account
        liability_data = {
            "account_name": account.name if account else None,
            "account_mask": account.mask if account else None,
            "balance": (
                str(account.balance_current)
                if account and account.balance_current
                else None
            ),
            "is_overdue": liability.is_overdue,
            "last_payment_amount": (
                str(liability.last_payment_amount)
                if liability.last_payment_amount
                else None
            ),
            "last_payment_date": (
                liability.last_payment_date.isoformat()
                if liability.last_payment_date
                else None
            ),
            "last_statement_balance": (
                str(liability.last_statement_balance)
                if liability.last_statement_balance
                else None
            ),
            "last_statement_issue_date": (
                liability.last_statement_issue_date.isoformat()
                if liability.last_statement_issue_date
                else None
            ),
            "minimum_payment_amount": (
                str(liability.minimum_payment_amount)
                if liability.minimum_payment_amount
                else None
            ),
            "next_payment_due_date": (
                liability.next_payment_due_date.isoformat()
                if liability.next_payment_due_date
                else None
            ),
            "aprs": [
                {
                    "apr_type": apr.apr_type,
                    "apr_percentage": str(apr.apr_percentage),
                    "balance_subject_to_apr": (
                        str(apr.balance_subject_to_apr)
                        if apr.balance_subject_to_apr
                        else None
                    ),
                    "interest_charge_amount": (
                        str(apr.interest_charge_amount)
                        if apr.interest_charge_amount
                        else None
                    ),
                }
                for apr in liability.aprs
            ],
        }
        data.append(liability_data)

    print(json.dumps(data, indent=2))


def _output_table(liabilities):
    """Output liabilities as Rich table."""
    # Create APR table
    table = Table(title="Credit Card Liabilities")
    table.add_column("Account", style="cyan", no_wrap=True)
    table.add_column("Balance", style="bold", justify="right")
    table.add_column("APRs", style="")

    payment_info_lines = []

    for liability in liabilities:
        account = liability.account
        if not account:
            continue

        # Format account name
        account_display = f"{account.name}"
        if account.mask:
            account_display += f" (****{account.mask})"

        # Format balance
        balance_display = (
            f"${account.balance_current:,.2f}" if account.balance_current else "N/A"
        )

        # Format APRs
        apr_lines = []
        for apr in liability.aprs:
            apr_type_display = _format_apr_type(apr.apr_type)
            apr_pct = apr.apr_percentage or Decimal("0")

            apr_line = f"{apr_type_display}: {apr_pct:.2f}%"

            # Add balance subject to APR for special/promotional rates
            if (
                apr.apr_type == AprType.SPECIAL.value
                and apr.balance_subject_to_apr
                and apr.balance_subject_to_apr > 0
            ):
                apr_line += f"\n  ↳ ${apr.balance_subject_to_apr:,.2f} at promo rate"

            apr_lines.append(apr_line)

        apr_display = "\n".join(apr_lines) if apr_lines else "N/A"

        table.add_row(account_display, balance_display, apr_display)

        # Collect payment info
        if (
            liability.minimum_payment_amount
            or liability.next_payment_due_date
            or liability.is_overdue
        ):
            payment_line = f"  {account.name}: "
            parts = []

            if liability.minimum_payment_amount:
                parts.append(f"Min payment ${liability.minimum_payment_amount:,.2f}")

            if liability.next_payment_due_date:
                due_date = liability.next_payment_due_date
                parts.append(f"due {due_date.isoformat()}")

            if liability.is_overdue:
                parts.append("[red bold][OVERDUE][/red bold]")

            payment_line += ", ".join(parts)
            payment_info_lines.append(payment_line)

    # Display table
    console.print()
    console.print(table)

    # Display payment info section
    if payment_info_lines:
        console.print("\n[bold]Payment Info:[/bold]")
        for line in payment_info_lines:
            console.print(line)

    console.print()


def _format_apr_type(apr_type: str) -> str:
    """Format APR type for display."""
    type_map = {
        AprType.PURCHASE.value: "Purchase",
        AprType.CASH.value: "Cash",
        AprType.BALANCE_TRANSFER.value: "Balance Transfer",
        AprType.SPECIAL.value: "Special",
    }
    return type_map.get(apr_type, apr_type.replace("_", " ").title())
