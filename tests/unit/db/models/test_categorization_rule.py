"""Tests for persistent categorization-rule metadata."""

from sqlalchemy import CheckConstraint, Index, UniqueConstraint

from budget_me.db.models import CategorizationRule
from budget_me.db.repos import CategorizationRulesRepo


def test_categorization_rule_is_exported_with_generated_normalized_pattern():
    table = CategorizationRule.__table__

    assert table.name == "categorization_rules"
    assert str(table.c.normalized_pattern.computed.sqltext) == ("lower(btrim(pattern))")
    assert table.c.normalized_pattern.computed.persisted is True
    assert table.c.enabled.default.arg is True
    assert table.c.source.default.arg == "manual"
    assert CategorizationRulesRepo.model is CategorizationRule


def test_categorization_rule_declares_private_rule_integrity_constraints():
    table_args = CategorizationRule.__table_args__
    named_constraints = {
        item.name: item
        for item in table_args
        if isinstance(item, (CheckConstraint, UniqueConstraint))
    }

    assert set(named_constraints) == {
        "uq_categorization_rules_type_pattern",
        "ck_categorization_rules_pattern_length",
        "ck_categorization_rules_type",
        "ck_categorization_rules_source",
        "ck_categorization_rules_confidence",
        "ck_categorization_rules_payload",
    }
    unique = named_constraints["uq_categorization_rules_type_pattern"]
    assert [column.name for column in unique.columns] == [
        "rule_type",
        "normalized_pattern",
    ]

    checks = {
        name: str(constraint.sqltext)
        for name, constraint in named_constraints.items()
        if isinstance(constraint, CheckConstraint)
    }
    assert checks["ck_categorization_rules_type"] == (
        "rule_type IN ('category', 'reimbursable')"
    )
    assert "enabled = false OR" in checks["ck_categorization_rules_payload"]

    indexes = {item.name for item in table_args if isinstance(item, Index)}
    assert indexes == {"ix_categorization_rules_enabled_type"}
