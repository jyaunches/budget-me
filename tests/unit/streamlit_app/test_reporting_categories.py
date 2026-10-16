"""Tests for presentation-only historical category corrections."""

from sqlalchemy.dialects import postgresql

from budget_me.streamlit_app.db import _reporting_budget_category_expression


def test_reporting_category_uses_manual_equity_rules_only():
    expression = _reporting_budget_category_expression()
    sql = str(
        expression.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert "categorization_rules" in sql
    assert "categorization_rules.source = 'manual'" in sql
    assert "categorization_rules.category = 'equity_disbursement'" in sql
    assert "coalesce" in sql.lower()


def test_reporting_category_prefers_the_longest_matching_pattern():
    expression = _reporting_budget_category_expression()
    sql = str(expression.compile(dialect=postgresql.dialect()))

    assert "strpos" in sql.lower()
    assert "length(categorization_rules.normalized_pattern) DESC" in sql
