"""Focused tests for card-side payment selection."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.dialects import postgresql

from budget_me.db.repos.transactions import TransactionsRepo


def _provider_transaction_values() -> dict:
    """Return a minimal provider transaction accepted by every upsert path."""
    return {
        "plaid_transaction_id": "provider-transaction",
        "plaid_item_id": uuid4(),
        "account_id": "checking-account",
        "date": date(2026, 7, 15),
        "amount": Decimal("12.34"),
        "name": "Provider transaction",
        "raw": {},
    }


def _compiled_conflict_statement(session) -> str:
    """Return the PostgreSQL ON CONFLICT statement issued to the fake session."""
    for call in session.execute.await_args_list:
        statement = call.args[0]
        compiled = str(statement.compile(dialect=postgresql.dialect()))
        if "ON CONFLICT" in compiled:
            return compiled
    raise AssertionError("No ON CONFLICT statement was executed")


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "method_name",
    ["upsert", "bulk_upsert", "bulk_upsert_with_details"],
)
async def test_provider_upserts_explicitly_advance_updated_at(method_name: str) -> None:
    """Core PostgreSQL upserts must not rely on the ORM onupdate hook."""
    values = _provider_transaction_values()
    empty_result = MagicMock()
    empty_result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(execute=AsyncMock(), flush=AsyncMock())
    repo = TransactionsRepo(session)

    if method_name == "upsert":
        repo.find_by_plaid_transaction_id = AsyncMock(
            side_effect=[MagicMock(), MagicMock()]
        )
        await repo.upsert(
            values["plaid_transaction_id"],
            values["plaid_item_id"],
            values["account_id"],
            values["date"],
            values["amount"],
            values["name"],
            raw=values["raw"],
        )
    elif method_name == "bulk_upsert":
        session.execute.side_effect = [empty_result, MagicMock()]
        await repo.bulk_upsert([values])
    else:
        session.execute.side_effect = [empty_result, MagicMock(), empty_result]
        await repo.bulk_upsert_with_details([values])

    compiled = _compiled_conflict_statement(session)
    assert "updated_at = clock_timestamp()" in compiled


@pytest.mark.asyncio
async def test_get_card_payments_query_excludes_pending_transactions() -> None:
    """Only posted card-side payments are eligible for reconciliation."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    payments = await TransactionsRepo(session).get_card_payments(
        "card-account",
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert payments == []
    assert "transactions.pending IS false" in compiled
    assert "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT" in compiled
    assert (
        "transactions.category_detailed = 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT'"
        in compiled
    )
    assert "transactions.category_detailed = 'Payment, Credit Card'" in compiled
    assert " OR " in compiled


@pytest.mark.asyncio
async def test_get_pending_card_payments_query_selects_only_pending_transactions() -> (
    None
):
    """Pending payment detection is separate from posted actuals."""
    result = MagicMock()
    result.scalars.return_value.all.return_value = []
    session = SimpleNamespace(execute=AsyncMock(return_value=result))

    payments = await TransactionsRepo(session).get_pending_card_payments(
        "card-account",
        date(2026, 7, 1),
        date(2026, 7, 31),
    )

    statement = session.execute.await_args.args[0]
    compiled = str(
        statement.compile(
            dialect=postgresql.dialect(),
            compile_kwargs={"literal_binds": True},
        )
    )

    assert payments == []
    assert "transactions.pending IS true" in compiled
    assert "LOAN_PAYMENTS_CREDIT_CARD_PAYMENT" in compiled
    assert (
        "transactions.category_detailed = 'LOAN_PAYMENTS_CREDIT_CARD_PAYMENT'"
        in compiled
    )
    assert "transactions.category_detailed = 'Payment, Credit Card'" in compiled
    assert " OR " in compiled
