"""Storage boundary for private categorization-rule overrides."""

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol

from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.categorization.rules import PACKAGED_RULES_PATH, load_rules
from budget_me.db.repos.categorization_rules import CategorizationRulesRepo


@dataclass(frozen=True)
class CategorizationRuleSet:
    """Effective rules after private database overrides are applied."""

    merchants: dict[str, str]
    categories: list[str]
    reimbursable_merchants: dict[str, str]


@dataclass(frozen=True)
class RuleImportSummary:
    """Counts from importing a legacy private rules file."""

    category_rules: int
    reimbursement_rules: int
    skipped_packaged_defaults: int
    disabled_rules: int


class CategorizationRuleStore(Protocol):
    """Persistence interface used by categorization workflows."""

    async def load(self) -> CategorizationRuleSet:
        """Load effective rules."""

    async def persist_learned(self, rules: Mapping[str, str]) -> int:
        """Persist newly learned category mappings."""


def normalize_rule_pattern(pattern: str) -> str:
    """Return the identity used by PostgreSQL's generated unique column."""
    if not isinstance(pattern, str):
        raise ValueError("Categorization rule patterns must be strings")
    normalized = pattern.strip().lower()
    if not normalized:
        raise ValueError("Categorization rule patterns cannot be blank")
    if len(normalized) > 255:
        raise ValueError("Categorization rule patterns cannot exceed 255 characters")
    return normalized


def _coalesce_rules(
    rules: Mapping[str, str], *, value_name: str, max_value_length: int
) -> dict[str, str]:
    """Coalesce case/whitespace aliases and reject conflicting duplicates."""
    coalesced: dict[str, tuple[str, str]] = {}
    for pattern, value in rules.items():
        normalized = normalize_rule_pattern(pattern)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"{value_name} values must be non-empty strings")
        clean_value = value.strip()
        if len(clean_value) > max_value_length:
            raise ValueError(
                f"{value_name} values cannot exceed {max_value_length} characters"
            )
        previous = coalesced.get(normalized)
        if previous and previous[1] != clean_value:
            raise ValueError(
                "Conflicting rules normalize to the same pattern: "
                f"{previous[0]!r} and {pattern!r}"
            )
        if previous is None:
            coalesced[normalized] = (pattern.strip(), clean_value)
    return {pattern: value for pattern, value in coalesced.values()}


def _remove_normalized(mapping: dict[str, str], normalized_pattern: str) -> None:
    """Remove a case-insensitive pattern from a display-keyed mapping."""
    for pattern in list(mapping):
        if normalize_rule_pattern(pattern) == normalized_pattern:
            del mapping[pattern]


def _normalized_values(mapping: Mapping[str, str]) -> dict[str, str]:
    """Return normalized-pattern to value for validated mappings."""
    return {
        normalize_rule_pattern(pattern): value
        for pattern, value in _coalesce_rules(
            mapping, value_name="Rule", max_value_length=255
        ).items()
    }


class PostgresCategorizationRuleStore:
    """Layer private PostgreSQL overrides over packaged OSS defaults."""

    def __init__(
        self,
        session: AsyncSession,
        *,
        repo: CategorizationRulesRepo | None = None,
    ) -> None:
        self.repo = repo or CategorizationRulesRepo(session)

    async def load(self) -> CategorizationRuleSet:
        """Load packaged defaults and apply database overrides."""
        merchants, categories, reimbursable = load_rules(PACKAGED_RULES_PATH)

        for rule in await self.repo.get_all_overrides():
            normalized = normalize_rule_pattern(rule.pattern)
            if rule.rule_type == "category":
                target = merchants
                value = rule.category
            elif rule.rule_type == "reimbursable":
                target = reimbursable
                value = rule.reimbursement_note
            else:
                raise ValueError(
                    f"Unsupported categorization rule type: {rule.rule_type}"
                )

            _remove_normalized(target, normalized)
            if rule.enabled:
                if value is None:
                    raise ValueError(
                        f"Enabled {rule.rule_type} rule has no value: {rule.pattern!r}"
                    )
                target[rule.pattern] = value

        return CategorizationRuleSet(
            merchants=merchants,
            categories=categories,
            reimbursable_merchants=reimbursable,
        )

    async def persist_learned(self, rules: Mapping[str, str]) -> int:
        """Persist learned mappings without replacing manual or imported rules."""
        self._validate_categories(rules)
        coalesced = _coalesce_rules(rules, value_name="Category", max_value_length=50)
        return await self.repo.upsert_category_rules(
            coalesced,
            source="learned",
            replace=False,
        )

    async def import_rules(
        self,
        merchants: Mapping[str, str],
        reimbursable_merchants: Mapping[str, str],
        *,
        replace: bool = False,
        full_snapshot: bool = False,
    ) -> RuleImportSummary:
        """Import private YAML rules as database-only overrides.

        Packaged mappings that are unchanged are intentionally not copied into
        PostgreSQL. With full_snapshot, omitted packaged or existing database
        rules are represented by disabled rows so the effective result matches
        the imported file, subject to the requested conflict behavior.
        """
        self._validate_categories(merchants)
        imported_categories = _coalesce_rules(
            merchants, value_name="Category", max_value_length=50
        )
        imported_reimbursements = _coalesce_rules(
            reimbursable_merchants,
            value_name="Reimbursement note",
            max_value_length=255,
        )

        packaged_categories, _, packaged_reimbursements = load_rules(
            PACKAGED_RULES_PATH
        )
        packaged_category_values = _normalized_values(packaged_categories)
        packaged_reimbursement_values = _normalized_values(packaged_reimbursements)

        category_overrides: dict[str, str] = {}
        reimbursement_overrides: dict[str, str] = {}
        skipped = 0
        for pattern, category in imported_categories.items():
            if (
                not replace
                and packaged_category_values.get(normalize_rule_pattern(pattern))
                == category
            ):
                skipped += 1
            else:
                category_overrides[pattern] = category
        for pattern, note in imported_reimbursements.items():
            if (
                not replace
                and packaged_reimbursement_values.get(normalize_rule_pattern(pattern))
                == note
            ):
                skipped += 1
            else:
                reimbursement_overrides[pattern] = note

        category_count = await self.repo.upsert_category_rules(
            category_overrides,
            source="import",
            replace=replace,
        )
        reimbursement_count = await self.repo.upsert_reimbursement_rules(
            reimbursement_overrides,
            source="import",
            replace=replace,
        )

        disabled_count = 0
        if full_snapshot:
            category_patterns, reimbursement_patterns = await self._missing_patterns(
                imported_categories,
                imported_reimbursements,
                packaged_categories,
                packaged_reimbursements,
            )
            disabled_count += await self.repo.upsert_disabled_rules(
                "category", category_patterns, source="import"
            )
            disabled_count += await self.repo.upsert_disabled_rules(
                "reimbursable", reimbursement_patterns, source="import"
            )

        return RuleImportSummary(
            category_rules=category_count,
            reimbursement_rules=reimbursement_count,
            skipped_packaged_defaults=skipped,
            disabled_rules=disabled_count,
        )

    async def _missing_patterns(
        self,
        imported_categories: Mapping[str, str],
        imported_reimbursements: Mapping[str, str],
        packaged_categories: Mapping[str, str],
        packaged_reimbursements: Mapping[str, str],
    ) -> tuple[list[str], list[str]]:
        """Find active rules omitted from an explicit full-snapshot import."""
        imported_category_keys = {
            normalize_rule_pattern(pattern) for pattern in imported_categories
        }
        imported_reimbursement_keys = {
            normalize_rule_pattern(pattern) for pattern in imported_reimbursements
        }
        missing_categories = {
            normalize_rule_pattern(pattern): pattern
            for pattern in packaged_categories
            if normalize_rule_pattern(pattern) not in imported_category_keys
        }
        missing_reimbursements = {
            normalize_rule_pattern(pattern): pattern
            for pattern in packaged_reimbursements
            if normalize_rule_pattern(pattern) not in imported_reimbursement_keys
        }

        for rule in await self.repo.get_all_overrides():
            if not rule.enabled:
                continue
            normalized = normalize_rule_pattern(rule.pattern)
            if (
                rule.rule_type == "category"
                and normalized not in imported_category_keys
            ):
                missing_categories[normalized] = rule.pattern
            elif (
                rule.rule_type == "reimbursable"
                and normalized not in imported_reimbursement_keys
            ):
                missing_reimbursements[normalized] = rule.pattern

        return list(missing_categories.values()), list(missing_reimbursements.values())

    @staticmethod
    def _validate_categories(rules: Mapping[str, str]) -> None:
        _, categories, _ = load_rules(PACKAGED_RULES_PATH)
        values = list(rules.values())
        if any(not isinstance(value, str) for value in values):
            raise ValueError("Category values must be strings")
        invalid = sorted(set(values) - set(categories))
        if invalid:
            raise ValueError(
                "Rules reference unsupported categories: " + ", ".join(invalid)
            )
