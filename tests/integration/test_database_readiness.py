"""Disposable PostgreSQL migration, RLS, and rule-storage behavior checks."""

import stat
from pathlib import Path

import pytest
import yaml
from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import delete, func, select, text

from budget_me.categorization.store import PostgresCategorizationRuleStore
from budget_me.cli.commands import rules
from budget_me.db.engine import get_async_session
from budget_me.db.models.categorization_rule import CategorizationRule
from tests.integration.conftest import _validated_database_test_url

pytestmark = [pytest.mark.integration, pytest.mark.database_integration]


def _migration_heads() -> set[str]:
    config = Config()
    config.set_main_option(
        "script_location", str(Path(__file__).parents[2] / "alembic")
    )
    return set(ScriptDirectory.from_config(config).get_heads())


def test_database_target_is_disposable(database_test_target) -> None:
    """Exercise the target guard before Alembic is allowed to connect."""
    assert database_test_target.database == "budget_me_test"


def test_database_target_requires_explicit_opt_in(monkeypatch) -> None:
    """Reject the test URL when the dedicated write opt-in is absent."""
    monkeypatch.delenv("BUDGET_ME_ALLOW_DATABASE_TESTS")

    with pytest.raises(pytest.UsageError, match="Database tests are disabled"):
        _validated_database_test_url()


def test_database_target_never_falls_back_to_database_url(monkeypatch) -> None:
    """Ignore even a plausible DATABASE_URL when the test URL is absent."""
    monkeypatch.delenv("BUDGET_ME_TEST_DATABASE_URL")
    monkeypatch.setenv(
        "DATABASE_URL",
        "postgresql://ignored:ignored@127.0.0.1/budget_me_test",
    )

    with pytest.raises(pytest.UsageError, match="DATABASE_URL and dotenv"):
        _validated_database_test_url()


def test_database_target_requires_exact_database_name(monkeypatch) -> None:
    """Reject loopback PostgreSQL targets whose database is not disposable."""
    monkeypatch.setenv(
        "BUDGET_ME_TEST_DATABASE_URL",
        "postgresql://ignored:ignored@127.0.0.1/postgres",
    )

    with pytest.raises(pytest.UsageError, match="exact database name"):
        _validated_database_test_url()


@pytest.mark.parametrize("query", ["host=database.example", "dbname=postgres"])
def test_database_target_rejects_connection_query_overrides(
    monkeypatch, query: str
) -> None:
    """Reject URL query keys that can override validated connection fields."""
    monkeypatch.setenv(
        "BUDGET_ME_TEST_DATABASE_URL",
        f"postgresql://ignored:ignored@127.0.0.1/budget_me_test?{query}",
    )

    with pytest.raises(pytest.UsageError, match="must not include query parameters"):
        _validated_database_test_url()


def test_database_target_allows_service_host_only_in_ci(monkeypatch) -> None:
    """Keep Docker service DNS unavailable to ordinary local runs."""
    monkeypatch.setenv(
        "BUDGET_ME_TEST_DATABASE_URL",
        "postgresql://ignored:ignored@postgres/budget_me_test",
    )
    monkeypatch.delenv("CI", raising=False)

    with pytest.raises(pytest.UsageError, match="accepted only when CI=true"):
        _validated_database_test_url()

    monkeypatch.setenv("CI", "true")
    assert _validated_database_test_url().host == "postgres"


@pytest.mark.asyncio
async def test_migration_head_and_public_tables_have_rls(db_session) -> None:
    """Prove the migrated schema is current and has no exposed app tables."""
    session, _ = db_session

    revisions = set(
        (await session.execute(text("SELECT version_num FROM alembic_version")))
        .scalars()
        .all()
    )
    assert revisions == _migration_heads()

    unprotected = (
        (
            await session.execute(
                text(
                    """
                SELECT tablename
                FROM pg_catalog.pg_tables
                WHERE schemaname = 'public'
                  AND tablename <> 'alembic_version'
                  AND NOT rowsecurity
                ORDER BY tablename
                """
                )
            )
        )
        .scalars()
        .all()
    )
    assert unprotected == []

    policies = await session.scalar(
        text(
            """
            SELECT count(*)
            FROM pg_catalog.pg_policies
            WHERE schemaname = 'public'
              AND tablename = 'categorization_rules'
            """
        )
    )
    assert policies == 0

    legacy_table = await session.scalar(
        text("SELECT to_regclass('public.whatsapp_messages')")
    )
    assert legacy_table is None


async def _clear_rules() -> None:
    async with get_async_session() as session:
        await session.execute(delete(CategorizationRule))


async def _stored_rule_count() -> int:
    async with get_async_session() as session:
        count = await session.scalar(select(func.count(CategorizationRule.id)))
    assert count is not None
    return count


async def _effective_rules():
    async with get_async_session() as session:
        return await PostgresCategorizationRuleStore(session).load()


@pytest.mark.asyncio
async def test_rule_dry_run_full_snapshot_and_export_round_trip(tmp_path) -> None:
    """Exercise real PostgreSQL writes, rollback, masks, export, and restore."""
    source = tmp_path / "rules.yaml"
    exported = tmp_path / "exported-rules.yaml"
    source.write_text(
        yaml.safe_dump(
            {
                "categories": {"groceries": {"description": "Food"}},
                "merchants": {"OSS Integration Market": "groceries"},
                "reimbursable_merchants": {
                    "OSS Integration Hotel": "integration reimbursement"
                },
            },
            sort_keys=False,
        ),
        encoding="utf-8",
    )

    await _clear_rules()
    try:
        before = await _stored_rule_count()
        preview = await rules._import_rules_async(
            source,
            replace=True,
            full_snapshot=True,
            dry_run=True,
        )
        assert preview.category_rules == 1
        assert preview.reimbursement_rules == 1
        assert preview.disabled_rules > 0
        assert await _stored_rule_count() == before

        imported = await rules._import_rules_async(
            source,
            replace=True,
            full_snapshot=True,
            dry_run=False,
        )
        assert imported.category_rules == 1
        assert imported.reimbursement_rules == 1
        assert imported.disabled_rules == preview.disabled_rules

        effective_before = await _effective_rules()
        assert effective_before.merchants == {"OSS Integration Market": "groceries"}
        assert effective_before.reimbursable_merchants == {
            "OSS Integration Hotel": "integration reimbursement"
        }

        await rules._export_rules_async(exported, overwrite=False)
        assert stat.S_IMODE(exported.stat().st_mode) == 0o600

        await _clear_rules()
        await rules._import_rules_async(
            exported,
            replace=True,
            full_snapshot=True,
            dry_run=False,
        )
        effective_after = await _effective_rules()
        assert effective_after.merchants == effective_before.merchants
        assert (
            effective_after.reimbursable_merchants
            == effective_before.reimbursable_merchants
        )
    finally:
        await _clear_rules()
