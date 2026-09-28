"""Main CLI application entry point."""

import typer

from budget_me.cli.commands import (
    add_liabilities,
    backfill,
    categorize,
    liabilities,
    link,
    projects,
    reconcile_cc,
    recurring,
    restore_target,
    rules,
    snapshots,
    status,
    sync,
)

app = typer.Typer(
    name="budget-me",
    help="Budget Me - Personal budget management with Plaid integration",
    add_completion=False,
)

# Register commands
app.command(name="add-liabilities")(add_liabilities.add_liabilities_command)
app.command(name="backfill-transactions")(backfill.backfill_command)
app.command(name="categorize")(categorize.categorize_command)
app.command(name="liabilities")(liabilities.liabilities_command)
app.command(name="link")(link.link_command)
app.command(name="projects")(projects.projects_command)
app.command(name="reconcile-cc")(reconcile_cc.reconcile_cc_command)
app.command(name="recurring")(recurring.recurring_command)
app.add_typer(restore_target.restore_target_app, name="restore-target")
app.add_typer(rules.rules_app, name="rules")
app.add_typer(snapshots.snapshots_app, name="snapshots")
app.command(name="status")(status.status_command)
app.command(name="sync")(sync.sync_command)


if __name__ == "__main__":
    app()
