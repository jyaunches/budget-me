"""Reconcile credit-card payment actuals from each card's own transactions.

For every credit card in a month's open snapshot(s), this reads the card
account's OWN payment transactions (Plaid detailed category
``LOAN_PAYMENTS_CREDIT_CARD_PAYMENT``) and fills in
``actual_payment_amount`` / ``actual_payment_date``.

Because each payment is recorded against its own card account, this removes
the need to guess which card a shared "CARD AUTOPAY" belongs to —
no institution keyword lists, no multi-card prompts.
"""

import asyncio
from calendar import monthrange
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal

import typer
from rich.console import Console
from rich.table import Table
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.engine import get_session_factory
from budget_me.db.repos.accounts_repo import AccountsRepo
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo
from budget_me.db.repos.transactions import TransactionsRepo
from budget_me.snapshots.card_payment_evidence import has_checking_account_marker

console = Console()


def reconcile_cc_command(
    month: str = typer.Option(
        ...,
        "--month",
        "-m",
        help="Month to reconcile, as YYYY-MM (e.g. 2026-03).",
    ),
    account_id: str | None = typer.Option(
        None,
        "--account",
        "-a",
        help="Only reconcile the snapshot for this checking account id.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Compatibility alias for the default no-write preview.",
    ),
    apply: bool = typer.Option(
        False,
        "--apply",
        help="Save reconciled card actuals after every guard succeeds.",
    ),
    confirm_month: str | None = typer.Option(
        None,
        "--confirm-month",
        help="Required with --apply; must exactly match --month.",
    ),
):
    """Preview card-payment actuals; write only with explicit confirmation.

    Attribution is deterministic: each card's payment lives in that card
    account's own feed, so the correct amount is matched without guessing.
    """
    validation_error = _write_option_error(
        month,
        dry_run=dry_run,
        apply=apply,
        confirm_month=confirm_month,
    )
    if validation_error:
        console.print(f"[bold red]Error:[/bold red] {validation_error}")
        raise typer.Exit(1)

    try:
        exit_code = asyncio.run(
            _reconcile_async(
                month,
                account_id,
                dry_run=dry_run,
                apply=apply,
                confirm_month=confirm_month,
            )
        )
        raise typer.Exit(exit_code)
    except typer.Exit:
        raise
    except Exception as e:
        console.print(f"\n[bold red]Error:[/bold red] {e}")
        raise typer.Exit(1)


def _write_option_error(
    month: str,
    *,
    dry_run: bool,
    apply: bool,
    confirm_month: str | None,
) -> str | None:
    """Return a fail-closed usage error before any database session is opened."""
    if dry_run and apply:
        return "choose --dry-run or --apply, not both"
    if apply and confirm_month != month:
        return "--apply requires --confirm-month to exactly match --month"
    return None


@asynccontextmanager
async def _reconcile_session() -> AsyncIterator[AsyncSession]:
    """Own transaction completion so previews can never auto-commit."""
    session = get_session_factory()()
    try:
        yield session
    except BaseException:
        await session.rollback()
        raise
    finally:
        await session.close()


async def _reconcile_async(
    month: str,
    account_id: str | None,
    dry_run: bool = False,
    apply: bool = False,
    confirm_month: str | None = None,
) -> int:
    validation_error = _write_option_error(
        month,
        dry_run=dry_run,
        apply=apply,
        confirm_month=confirm_month,
    )
    if validation_error:
        console.print(f"[bold red]Error:[/bold red] {validation_error}")
        return 1

    try:
        year, mon = (int(p) for p in month.split("-"))
        start = date(year, mon, 1)
        end = date(year, mon, monthrange(year, mon)[1])
    except (ValueError, TypeError):
        console.print(
            f"[bold red]Error:[/bold red] invalid --month '{month}' (use YYYY-MM)"
        )
        return 1

    async with _reconcile_session() as session:
        snap_repo = MonthlySnapshotRepo(session)
        txn_repo = TransactionsRepo(session)
        accounts_repo = AccountsRepo(session)

        snapshots = [
            s for s in await snap_repo.get_open_snapshots() if s.year_month == month
        ]
        if account_id:
            snapshots = [s for s in snapshots if s.account_id == account_id]

        if not snapshots:
            console.print(
                f"\n[yellow]No open snapshot found for {month}"
                f"{' / ' + account_id if account_id else ''}.[/yellow]\n"
            )
            await session.rollback()
            return 1

        all_accounts = await accounts_repo.get_all()
        names = {a.account_id: (a.display_name or a.name, a.mask) for a in all_accounts}

        snapshot_cards = [
            (snapshot, await snap_repo.get_credit_cards(snapshot.id))
            for snapshot in snapshots
        ]
        pending_by_card = []
        for snapshot, cards in snapshot_cards:
            for card in cards:
                pending = await txn_repo.get_pending_card_payments(
                    card.account_id, start, end
                )
                if pending:
                    pending_by_card.append((snapshot, card, pending))

        if pending_by_card:
            console.print(
                "\n[bold red]Reconciliation blocked:[/bold red] "
                "card payments are still pending."
            )
            pending_table = Table()
            pending_table.add_column("Account")
            pending_table.add_column("Card")
            pending_table.add_column("Pending payments", justify="right")
            pending_table.add_column("Pending amount", justify="right")
            for snapshot, card, pending in pending_by_card:
                acct_name = names.get(snapshot.account_id, (snapshot.account_id, ""))[0]
                cname, cmask = names.get(card.account_id, ("?", "?"))
                pending_total = sum(
                    (abs(payment.amount) for payment in pending), Decimal("0")
                )
                pending_table.add_row(
                    acct_name,
                    f"{cname} ({cmask})",
                    str(len(pending)),
                    f"${pending_total:,.2f}",
                )
            console.print(pending_table)
            console.print(
                "[yellow]Wait for pending payments to post or disappear, sync, "
                "then reconcile again. No actuals were saved.[/yellow]\n"
            )
            await session.rollback()
            return 2

        for snapshot, cards in snapshot_cards:
            acct_name = names.get(snapshot.account_id, (snapshot.account_id, ""))[0]
            console.print(f"\n[bold]{month} — {acct_name}[/bold]")

            table = Table()
            table.add_column("Card")
            table.add_column("Old actual", justify="right")
            table.add_column("Card-side", justify="right")
            table.add_column("Payments")

            for card in cards:
                cname, cmask = names.get(card.account_id, ("?", "?"))
                payments = await txn_repo.get_card_payments(card.account_id, start, end)
                # The repository selects posted rows only. Keep this defensive
                # filter at the aggregation boundary so a pending row can never
                # be counted if an alternate repository implementation is used.
                posted_payments = [
                    payment for payment in payments if not payment.pending
                ]
                total = sum(
                    (abs(payment.amount) for payment in posted_payments),
                    Decimal("0"),
                )
                # Zero is a reviewed result: it distinguishes a card with no
                # posted or pending payment from a card whose actuals were never
                # reconciled (NULL).
                new_amount = total
                new_date = max(
                    (payment.date for payment in posted_payments), default=None
                )

                old = card.actual_payment_amount
                old_date = card.actual_payment_date
                if has_checking_account_marker(card) and (
                    old != new_amount or old_date != new_date
                ):
                    # A normal card-feed refresh must not erase a separately
                    # verified checking-side payment that the feed still omits.
                    new_amount = old
                    new_date = old_date
                old_str = f"${old:,.2f}" if old is not None else "—"
                new_str = f"${new_amount:,.2f}" if new_amount is not None else "—"
                changed = old != new_amount or old_date != new_date
                marker = " [yellow]→[/yellow]" if changed else ""
                table.add_row(
                    f"{cname} ({cmask})",
                    old_str,
                    new_str + marker,
                    str(len(posted_payments)),
                )

                if apply and changed:
                    await snap_repo.update_credit_card(
                        card.id,
                        actual_payment_amount=new_amount,
                        actual_payment_date=new_date,
                    )

            console.print(table)

        if apply:
            await session.commit()
            console.print(
                "\n[green]✓[/green] Reconciled from card-side transactions.\n"
            )
        else:
            await session.rollback()
            console.print(
                "\n[yellow]PREVIEW / DRY RUN — no changes saved. "
                f"Apply only with --apply --confirm-month {month}.[/yellow]\n"
            )

    return 0
