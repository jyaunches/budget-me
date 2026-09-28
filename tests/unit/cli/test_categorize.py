"""Runtime integration tests for the categorize CLI command."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import pytest

from budget_me.categorization.models import CategorizationResult
from budget_me.categorization.store import CategorizationRuleSet
from budget_me.cli.commands import categorize


def _runtime_dependencies():
    session = SimpleNamespace(rollback=AsyncMock())
    rule_set = CategorizationRuleSet(
        merchants={"Example Cafe": "dining"},
        categories=["dining"],
        reimbursable_merchants={"Example Hotel": "work"},
    )
    rule_store = Mock()
    rule_store.load = AsyncMock(return_value=rule_set)
    accounts_repo = Mock()
    accounts_repo.get_excluded = AsyncMock(return_value=[])
    accounts_repo.get_all = AsyncMock(return_value=[])
    service = Mock()
    service.categorize_transactions = AsyncMock(return_value=CategorizationResult())
    return session, rule_set, rule_store, accounts_repo, service


@pytest.mark.asyncio
@pytest.mark.parametrize("dry_run", [False, True])
async def test_categorize_uses_postgres_rule_store_and_rolls_back_only_dry_run(
    dry_run: bool,
) -> None:
    """The CLI shares one DB store/session and makes dry-run rollback real."""
    session, rule_set, rule_store, accounts_repo, service = _runtime_dependencies()

    @asynccontextmanager
    async def session_context():
        yield session

    settings = SimpleNamespace(anthropic_api_key=None, tavily_api_key=None)
    with (
        patch.object(categorize, "get_settings", return_value=settings),
        patch.object(categorize, "get_async_session", return_value=session_context()),
        patch.object(
            categorize,
            "PostgresCategorizationRuleStore",
            return_value=rule_store,
        ) as store_factory,
        patch.object(categorize, "AccountsRepo", return_value=accounts_repo),
        patch.object(
            categorize, "CategorizationService", return_value=service
        ) as service_factory,
        patch.object(categorize, "_display_results"),
    ):
        exit_code = await categorize._categorize_async(days=7, dry_run=dry_run)

    assert exit_code == 0
    store_factory.assert_called_once_with(session)
    rule_store.load.assert_awaited_once_with()
    service_factory.assert_called_once_with(
        session,
        rule_set.merchants,
        rule_set.categories,
        inference_client=None,
        search_client=None,
        reimbursable_rules=rule_set.reimbursable_merchants,
        rule_store=rule_store,
    )
    service.categorize_transactions.assert_awaited_once_with(
        days=7,
        excluded_account_ids=set(),
        account_names={},
    )
    if dry_run:
        session.rollback.assert_awaited_once_with()
    else:
        session.rollback.assert_not_awaited()
