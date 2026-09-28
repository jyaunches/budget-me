"""Unit tests for PostgreSQL-backed categorization-rule composition."""

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from budget_me.categorization import store as store_module
from budget_me.categorization.store import PostgresCategorizationRuleStore


class FakeRulesRepo:
    """In-memory call recorder for the rule-store persistence boundary."""

    def __init__(self, overrides: list[SimpleNamespace] | None = None) -> None:
        self.get_all_overrides = AsyncMock(return_value=list(overrides or []))
        self.upsert_category_rules = AsyncMock(
            side_effect=lambda rules, **_kwargs: len(rules)
        )
        self.upsert_reimbursement_rules = AsyncMock(
            side_effect=lambda rules, **_kwargs: len(rules)
        )
        self.upsert_disabled_rules = AsyncMock(
            side_effect=lambda _rule_type, patterns, **_kwargs: len(patterns)
        )


def _rule(
    rule_type: str,
    pattern: str,
    *,
    enabled: bool = True,
    category: str | None = None,
    reimbursement_note: str | None = None,
) -> SimpleNamespace:
    return SimpleNamespace(
        rule_type=rule_type,
        pattern=pattern,
        enabled=enabled,
        category=category,
        reimbursement_note=reimbursement_note,
    )


def _install_packaged_rules(
    monkeypatch: pytest.MonkeyPatch,
    *,
    merchants: dict[str, str] | None = None,
    reimbursable: dict[str, str] | None = None,
) -> None:
    """Return fresh copies because loading applies overrides in place."""
    packaged_merchants = merchants or {}
    packaged_reimbursable = reimbursable or {}
    categories = ["groceries", "dining", "shopping", "health"]

    def fake_load_rules(_path):
        return (
            dict(packaged_merchants),
            list(categories),
            dict(packaged_reimbursable),
        )

    monkeypatch.setattr(store_module, "load_rules", fake_load_rules)


def _normalized(mapping: dict[str, str]) -> dict[str, str]:
    return {key.strip().lower(): value for key, value in mapping.items()}


@pytest.mark.asyncio
async def test_load_overlays_each_rule_type_without_cross_type_masks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(
        monkeypatch,
        merchants={
            "Both Enabled": "shopping",
            "Category Mask": "dining",
            "Reimb Mask": "health",
        },
        reimbursable={
            "Both Enabled": "work",
            "Category Mask": "client",
            "Reimb Mask": "travel",
        },
    )
    repo = FakeRulesRepo(
        [
            _rule("category", "both enabled", category="groceries"),
            _rule("category", "category mask", enabled=False),
            _rule("reimbursable", "reimb mask", enabled=False),
        ]
    )

    effective = await PostgresCategorizationRuleStore(
        SimpleNamespace(), repo=repo
    ).load()

    merchants = _normalized(effective.merchants)
    reimbursements = _normalized(effective.reimbursable_merchants)
    assert merchants == {
        "both enabled": "groceries",
        "reimb mask": "health",
    }
    assert reimbursements == {
        "both enabled": "work",
        "category mask": "client",
    }


@pytest.mark.asyncio
async def test_persist_learned_coalesces_aliases_without_replacing_existing_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(monkeypatch)
    repo = FakeRulesRepo()
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    count = await rule_store.persist_learned(
        {"  Example Cafe  ": "dining", "example cafe": "dining"}
    )

    assert count == 1
    repo.upsert_category_rules.assert_awaited_once_with(
        {"Example Cafe": "dining"},
        source="learned",
        replace=False,
    )


@pytest.mark.asyncio
async def test_import_coalesces_case_and_whitespace_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(monkeypatch)
    repo = FakeRulesRepo()
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    summary = await rule_store.import_rules(
        {"  Example Market  ": "groceries", "example market": "groceries"},
        {" Example Hotel ": "work", "EXAMPLE HOTEL": "work"},
    )

    assert summary.category_rules == 1
    assert summary.reimbursement_rules == 1
    repo.upsert_category_rules.assert_awaited_once_with(
        {"Example Market": "groceries"},
        source="import",
        replace=False,
    )
    repo.upsert_reimbursement_rules.assert_awaited_once_with(
        {"Example Hotel": "work"},
        source="import",
        replace=False,
    )


@pytest.mark.asyncio
async def test_import_rejects_conflicting_normalized_aliases(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(monkeypatch)
    repo = FakeRulesRepo()
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    with pytest.raises(ValueError, match="Conflicting rules normalize"):
        await rule_store.import_rules(
            {"Example Market": "groceries", " example market ": "dining"},
            {},
        )

    repo.upsert_category_rules.assert_not_awaited()
    repo.upsert_reimbursement_rules.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_rejects_unknown_categories_before_writing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(monkeypatch)
    repo = FakeRulesRepo()
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    with pytest.raises(ValueError, match="unsupported categories: not-a-category"):
        await rule_store.import_rules(
            {"Example Market": "not-a-category"},
            {},
        )

    repo.upsert_category_rules.assert_not_awaited()
    repo.upsert_reimbursement_rules.assert_not_awaited()


@pytest.mark.asyncio
async def test_import_skips_unchanged_packaged_defaults(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(
        monkeypatch,
        merchants={"Default Shop": "shopping"},
        reimbursable={"Default Hotel": "work"},
    )
    repo = FakeRulesRepo()
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    summary = await rule_store.import_rules(
        {
            " default shop ": "shopping",
            "Private Market": "groceries",
        },
        {"DEFAULT HOTEL": "work"},
    )

    assert summary.category_rules == 1
    assert summary.reimbursement_rules == 0
    assert summary.skipped_packaged_defaults == 2
    repo.upsert_category_rules.assert_awaited_once_with(
        {"Private Market": "groceries"},
        source="import",
        replace=False,
    )
    repo.upsert_reimbursement_rules.assert_awaited_once_with(
        {},
        source="import",
        replace=False,
    )


@pytest.mark.asyncio
async def test_full_snapshot_disables_missing_packaged_and_database_rules(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_packaged_rules(
        monkeypatch,
        merchants={"Keep Category": "groceries", "Packaged Missing": "dining"},
        reimbursable={"Keep Reimbursement": "client", "Reimb Missing": "work"},
    )
    repo = FakeRulesRepo(
        [
            _rule("category", "Private Missing", category="shopping"),
            _rule(
                "reimbursable",
                "Private Reimb Missing",
                reimbursement_note="travel",
            ),
            _rule("category", "Already Disabled", enabled=False),
        ]
    )
    rule_store = PostgresCategorizationRuleStore(SimpleNamespace(), repo=repo)

    summary = await rule_store.import_rules(
        {"Keep Category": "groceries"},
        {"Keep Reimbursement": "client"},
        full_snapshot=True,
    )

    assert summary.disabled_rules == 4
    assert repo.upsert_disabled_rules.await_count == 2
    category_call, reimbursement_call = repo.upsert_disabled_rules.await_args_list
    assert category_call.args[0] == "category"
    assert set(category_call.args[1]) == {"Packaged Missing", "Private Missing"}
    assert category_call.kwargs == {"source": "import"}
    assert reimbursement_call.args[0] == "reimbursable"
    assert set(reimbursement_call.args[1]) == {
        "Reimb Missing",
        "Private Reimb Missing",
    }
    assert reimbursement_call.kwargs == {"source": "import"}
