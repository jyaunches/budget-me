"""SQL-construction tests for persistent categorization-rule upserts."""

from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from budget_me.db.repos.categorization_rules import CategorizationRulesRepo


def _session_with_returned_ids(*returned_ids):
    session = MagicMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()

    result = MagicMock()
    result.scalars.return_value.all.return_value = list(returned_ids)
    session.execute.return_value = result
    return session


def _compiled_execute(session: MagicMock):
    statement = session.execute.await_args.args[0]
    compiled = statement.compile(dialect=postgresql.dialect())
    return str(compiled), compiled.params


@pytest.mark.asyncio
async def test_learned_category_rule_does_not_replace_and_counts_returned_rows():
    inserted_id = uuid4()
    session = _session_with_returned_ids(inserted_id)
    repo = CategorizationRulesRepo(session)

    count = await repo.upsert_category_rules(
        {" Example Cafe ": "dining", "Existing Market": "groceries"},
        source="learned",
        confidence="high",
        replace=False,
    )

    sql, params = _compiled_execute(session)
    assert "ON CONFLICT ON CONSTRAINT uq_categorization_rules_type_pattern" in sql
    assert "DO NOTHING" in sql
    assert "RETURNING categorization_rules.id" in sql
    assert "category" in params.values()
    assert "learned" in params.values()
    assert count == 1
    session.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_replacing_category_rule_clears_reimbursement_payload():
    session = _session_with_returned_ids(uuid4())
    repo = CategorizationRulesRepo(session)

    await repo.upsert_category_rules(
        {"Example Cafe": "dining"}, source="manual", replace=True
    )

    sql, params = _compiled_execute(session)
    assert "DO UPDATE SET" in sql
    assert "reimbursement_note = %(param_1)s" in sql
    assert params["param_1"] is None
    assert "category" in params.values()
    assert "reimbursable" not in params.values()


@pytest.mark.asyncio
async def test_reimbursement_rule_uses_separate_type_and_clears_category_payload():
    session = _session_with_returned_ids(uuid4())
    repo = CategorizationRulesRepo(session)

    await repo.upsert_reimbursement_rules(
        {"Example Hotel": "work trip"}, source="import", replace=True
    )

    sql, params = _compiled_execute(session)
    assert "ON CONFLICT ON CONSTRAINT uq_categorization_rules_type_pattern" in sql
    assert "DO UPDATE SET" in sql
    assert "category = %(param_1)s" in sql
    assert params["rule_type_m0"] == "reimbursable"
    assert params["reimbursement_note_m0"] == "work trip"
    assert params["param_1"] is None


@pytest.mark.asyncio
async def test_disabled_rule_validates_type_and_compiles_conflict_update():
    session = _session_with_returned_ids(uuid4())
    repo = CategorizationRulesRepo(session)

    with pytest.raises(ValueError, match="Unsupported categorization rule type"):
        await repo.upsert_disabled_rules(
            "unsupported", ["Example Merchant"], source="import"
        )

    session.execute.assert_not_awaited()

    count = await repo.upsert_disabled_rules(
        "category", [" Example Merchant "], source="import"
    )

    sql, params = _compiled_execute(session)
    assert "ON CONFLICT ON CONSTRAINT uq_categorization_rules_type_pattern" in sql
    assert "DO UPDATE SET" in sql
    assert params["rule_type_m0"] == "category"
    assert params["enabled_m0"] is False
    assert params["category_m0"] is None
    assert params["reimbursement_note_m0"] is None
    assert False in params.values()
    assert count == 1
