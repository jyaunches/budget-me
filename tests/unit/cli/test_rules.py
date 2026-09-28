"""Tests for the PostgreSQL-backed categorization-rules CLI."""

import os
import stat
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest
import yaml
from typer.testing import CliRunner

from budget_me.categorization.store import CategorizationRuleSet
from budget_me.cli.commands import rules
from budget_me.cli.main import app

runner = CliRunner()


def _write_rules_file(path: Path) -> None:
    path.write_text(
        """\
categories:
  groceries:
    description: Food
merchants:
  Example Market: groceries
reimbursable_merchants:
  Example Hotel: work
""",
        encoding="utf-8",
    )


def test_rules_group_is_registered() -> None:
    result = runner.invoke(app, ["rules", "--help"])

    assert result.exit_code == 0
    assert "import" in result.stdout
    assert "export" in result.stdout
    assert "status" in result.stdout


def test_load_import_file_validates_required_mappings(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    _write_rules_file(path)

    merchants, reimbursable = rules._load_import_file(path)

    assert merchants == {"Example Market": "groceries"}
    assert reimbursable == {"Example Hotel": "work"}


def test_load_import_file_rejects_non_mapping_section(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    path.write_text(
        "categories: {groceries: {}}\nmerchants: []\nreimbursable_merchants: {}\n",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="'merchants' must be a YAML mapping"):
        rules._load_import_file(path)


def test_write_private_yaml_is_0600_and_refuses_overwrite(tmp_path: Path) -> None:
    destination = tmp_path / "nested" / "rules.yaml"
    document = {
        "categories": {"groceries": {"description": "Food"}},
        "merchants": {"Example Market": "groceries"},
        "reimbursable_merchants": {},
    }

    rules._write_private_yaml(destination, document, overwrite=False)

    assert yaml.safe_load(destination.read_text(encoding="utf-8")) == document
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600
    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        rules._write_private_yaml(destination, document, overwrite=False)


def test_write_private_yaml_refuses_dangling_symlink(tmp_path: Path) -> None:
    destination = tmp_path / "rules.yaml"
    destination.symlink_to(tmp_path / "missing-target.yaml")
    document = {
        "categories": {"groceries": {}},
        "merchants": {},
        "reimbursable_merchants": {},
    }

    with pytest.raises(FileExistsError, match="Refusing to overwrite"):
        rules._write_private_yaml(destination, document, overwrite=False)
    assert not (tmp_path / "missing-target.yaml").exists()


def test_write_private_yaml_overwrites_when_explicit(tmp_path: Path) -> None:
    destination = tmp_path / "rules.yaml"
    destination.write_text("old: true\n", encoding="utf-8")
    os.chmod(destination, 0o644)
    document = {
        "categories": {"groceries": {}},
        "merchants": {},
        "reimbursable_merchants": {},
    }

    rules._write_private_yaml(destination, document, overwrite=True)

    assert yaml.safe_load(destination.read_text(encoding="utf-8")) == document
    assert stat.S_IMODE(destination.stat().st_mode) == 0o600


def test_export_document_uses_effective_mappings_and_packaged_categories() -> None:
    rule_set = CategorizationRuleSet(
        merchants={"Private Merchant": "dining"},
        categories=["dining"],
        reimbursable_merchants={"Private Hotel": "work"},
    )

    document = rules._export_document(rule_set)

    assert "categories" in document
    assert document["merchants"] == {"Private Merchant": "dining"}
    assert document["reimbursable_merchants"] == {"Private Hotel": "work"}


@pytest.mark.asyncio
async def test_import_dry_run_explicitly_rolls_back(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    _write_rules_file(path)
    session = SimpleNamespace(rollback=AsyncMock())
    summary = SimpleNamespace(
        category_rules=1,
        reimbursement_rules=1,
        skipped_packaged_defaults=0,
        disabled_rules=0,
    )
    store = Mock()
    store.import_rules = AsyncMock(return_value=summary)

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(rules, "get_async_session", return_value=session_context()),
        patch.object(rules, "PostgresCategorizationRuleStore", return_value=store),
    ):
        result = await rules._import_rules_async(
            path,
            replace=False,
            full_snapshot=True,
            dry_run=True,
        )

    assert result is summary
    store.import_rules.assert_awaited_once_with(
        {"Example Market": "groceries"},
        {"Example Hotel": "work"},
        replace=False,
        full_snapshot=True,
    )
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_import_non_dry_run_leaves_commit_to_session_scope(
    tmp_path: Path,
) -> None:
    path = tmp_path / "rules.yaml"
    _write_rules_file(path)
    session = SimpleNamespace(rollback=AsyncMock())
    store = Mock()
    store.import_rules = AsyncMock(return_value=SimpleNamespace())

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(rules, "get_async_session", return_value=session_context()),
        patch.object(rules, "PostgresCategorizationRuleStore", return_value=store),
    ):
        await rules._import_rules_async(
            path,
            replace=True,
            full_snapshot=False,
            dry_run=False,
        )

    session.rollback.assert_not_awaited()


def test_import_command_reports_summary_without_rule_values(tmp_path: Path) -> None:
    path = tmp_path / "rules.yaml"
    _write_rules_file(path)
    summary = SimpleNamespace(
        category_rules=1,
        reimbursement_rules=1,
        skipped_packaged_defaults=2,
        disabled_rules=3,
    )

    with patch.object(
        rules,
        "_import_rules_async",
        new=AsyncMock(return_value=summary),
    ):
        result = runner.invoke(
            app,
            ["rules", "import", str(path), "--full-snapshot", "--dry-run"],
        )

    assert result.exit_code == 0
    assert "Would import categorization rules" in result.stdout
    assert "Rules disabled by snapshot: 3" in result.stdout
    assert "No database changes were saved" in result.stdout
    assert "Example Market" not in result.stdout
