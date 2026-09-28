"""Manage PostgreSQL-backed categorization-rule overrides."""

import asyncio
import os
import tempfile
from collections.abc import Mapping
from pathlib import Path
from typing import Any

import typer
import yaml
from rich.console import Console
from rich.table import Table

from budget_me.categorization.rules import PACKAGED_RULES_PATH
from budget_me.categorization.store import (
    CategorizationRuleSet,
    PostgresCategorizationRuleStore,
    RuleImportSummary,
)
from budget_me.db.engine import get_async_session

console = Console()

rules_app = typer.Typer(
    help="Import, export, and inspect categorization rules stored in PostgreSQL.",
    no_args_is_help=True,
)


def _mapping_section(document: Mapping[str, Any], name: str) -> dict[str, str]:
    """Validate and return one string-to-string YAML mapping."""
    section = document.get(name)
    if not isinstance(section, Mapping):
        raise ValueError(f"'{name}' must be a YAML mapping")

    validated: dict[str, str] = {}
    for raw_pattern, raw_value in section.items():
        if not isinstance(raw_pattern, str) or not raw_pattern.strip():
            raise ValueError(f"'{name}' contains a blank or non-string pattern")
        if not isinstance(raw_value, str) or not raw_value.strip():
            raise ValueError(
                f"'{name}' entry {raw_pattern!r} has a blank or non-string value"
            )
        validated[raw_pattern] = raw_value
    return validated


def _load_import_file(path: Path) -> tuple[dict[str, str], dict[str, str]]:
    """Load and structurally validate a categorization-rules YAML file."""
    with path.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)

    if not isinstance(document, Mapping):
        raise ValueError("Rules file must contain a YAML mapping")

    categories = document.get("categories")
    if not isinstance(categories, Mapping) or not categories:
        raise ValueError("'categories' must be a non-empty YAML mapping")

    merchants = _mapping_section(document, "merchants")
    reimbursable = _mapping_section(document, "reimbursable_merchants")
    return merchants, reimbursable


def _packaged_document() -> dict[str, Any]:
    """Load category metadata from the packaged OSS defaults."""
    with PACKAGED_RULES_PATH.open(encoding="utf-8") as handle:
        document = yaml.safe_load(handle)
    if not isinstance(document, dict) or not isinstance(
        document.get("categories"), dict
    ):
        raise ValueError("Packaged categorization rules are malformed")
    return document


def _export_document(rule_set: CategorizationRuleSet) -> dict[str, Any]:
    """Build a portable YAML document from effective database-backed rules."""
    document = _packaged_document()
    document["merchants"] = dict(
        sorted(rule_set.merchants.items(), key=lambda item: item[0].lower())
    )
    document["reimbursable_merchants"] = dict(
        sorted(
            rule_set.reimbursable_merchants.items(),
            key=lambda item: item[0].lower(),
        )
    )
    return document


def _write_private_yaml(
    destination: Path,
    document: Mapping[str, Any],
    *,
    overwrite: bool,
) -> None:
    """Atomically write a private YAML file, refusing overwrite by default."""
    destination = destination.expanduser()
    destination_exists = os.path.lexists(destination)
    if destination_exists and not overwrite:
        raise FileExistsError(
            f"Refusing to overwrite existing file: {destination}. Use --overwrite."
        )
    if destination_exists and destination.is_dir():
        raise IsADirectoryError(f"Export destination is a directory: {destination}")

    destination.parent.mkdir(parents=True, exist_ok=True)
    file_descriptor, temporary_name = tempfile.mkstemp(
        dir=destination.parent,
        prefix=f".{destination.name}.",
        suffix=".tmp",
        text=True,
    )
    temporary_path = Path(temporary_name)
    try:
        os.fchmod(file_descriptor, 0o600)
        with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
            yaml.safe_dump(
                dict(document),
                handle,
                sort_keys=False,
                allow_unicode=True,
            )
            handle.flush()
            os.fsync(handle.fileno())
        if overwrite:
            os.replace(temporary_path, destination)
        else:
            # Linking fails if another process creates the destination after our
            # initial check, preserving the no-overwrite guarantee without a race.
            os.link(temporary_path, destination)
            temporary_path.unlink()
        destination.chmod(0o600)
    except Exception:
        try:
            os.close(file_descriptor)
        except OSError:
            pass
        temporary_path.unlink(missing_ok=True)
        raise


async def _status_async() -> CategorizationRuleSet:
    """Load effective rules from packaged defaults plus PostgreSQL overrides."""
    async with get_async_session() as session:
        return await PostgresCategorizationRuleStore(session).load()


async def _import_rules_async(
    path: Path,
    *,
    replace: bool,
    full_snapshot: bool,
    dry_run: bool,
) -> RuleImportSummary:
    """Validate and import a YAML file in one database transaction."""
    merchants, reimbursable = _load_import_file(path)

    async with get_async_session() as session:
        store = PostgresCategorizationRuleStore(session)
        summary = await store.import_rules(
            merchants,
            reimbursable,
            replace=replace,
            full_snapshot=full_snapshot,
        )
        if dry_run:
            # get_async_session commits on normal context exit, so a preview must
            # explicitly end the write transaction before yielding control.
            await session.rollback()
        return summary


async def _export_rules_async(destination: Path, *, overwrite: bool) -> int:
    """Export effective rules without exposing their values in command output."""
    async with get_async_session() as session:
        rule_set = await PostgresCategorizationRuleStore(session).load()

    _write_private_yaml(
        destination,
        _export_document(rule_set),
        overwrite=overwrite,
    )
    return len(rule_set.merchants) + len(rule_set.reimbursable_merchants)


@rules_app.command("status")
def status_command() -> None:
    """Show aggregate counts for the effective categorization rules."""
    try:
        rule_set = asyncio.run(_status_async())
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    table = Table(title="Effective categorization rules")
    table.add_column("Rule data")
    table.add_column("Count", justify="right")
    table.add_row("Categories", str(len(rule_set.categories)))
    table.add_row("Merchant mappings", str(len(rule_set.merchants)))
    table.add_row("Reimbursable mappings", str(len(rule_set.reimbursable_merchants)))
    console.print(table)
    console.print("[dim]Packaged defaults with PostgreSQL overrides applied[/dim]")


@rules_app.command("import")
def import_rules_command(
    path: Path = typer.Argument(
        ...,
        exists=True,
        file_okay=True,
        dir_okay=False,
        readable=True,
        resolve_path=True,
        help="Categorization-rules YAML file to import.",
    ),
    replace: bool = typer.Option(
        False,
        "--replace",
        help="Replace database rules with matching type and pattern.",
    ),
    full_snapshot: bool = typer.Option(
        False,
        "--full-snapshot",
        help="Disable existing/default rules absent from the imported snapshot.",
    ),
    dry_run: bool = typer.Option(
        False,
        "--dry-run",
        help="Validate and preview the import, then roll back all database writes.",
    ),
) -> None:
    """Import private rule overrides from YAML into PostgreSQL."""
    try:
        summary = asyncio.run(
            _import_rules_async(
                path,
                replace=replace,
                full_snapshot=full_snapshot,
                dry_run=dry_run,
            )
        )
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    verb = "Would import" if dry_run else "Imported"
    console.print(f"[green]{verb} categorization rules[/green]")
    console.print(f"  Category rules: {summary.category_rules}")
    console.print(f"  Reimbursement rules: {summary.reimbursement_rules}")
    console.print(
        f"  Unchanged packaged defaults skipped: {summary.skipped_packaged_defaults}"
    )
    if full_snapshot:
        console.print(f"  Rules disabled by snapshot: {summary.disabled_rules}")
    if dry_run:
        console.print("[yellow]DRY RUN - No database changes were saved[/yellow]")


@rules_app.command("export")
def export_rules_command(
    destination: Path = typer.Argument(
        ...,
        file_okay=True,
        dir_okay=False,
        help="Destination YAML file.",
    ),
    overwrite: bool = typer.Option(
        False,
        "--overwrite",
        help="Replace an existing destination file.",
    ),
) -> None:
    """Export effective rules to a private, portable YAML snapshot."""
    try:
        count = asyncio.run(_export_rules_async(destination, overwrite=overwrite))
    except Exception as exc:
        console.print(f"[bold red]Error:[/bold red] {exc}")
        raise typer.Exit(2) from exc

    console.print(
        f"[green]Exported {count} rules to {destination} (permissions: 0600)[/green]"
    )
