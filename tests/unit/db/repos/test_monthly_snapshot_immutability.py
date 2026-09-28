"""Tests for closed-snapshot immutability at the repository boundary."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from budget_me.db.models.account import PaymentStrategy
from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.db.models.snapshot_line_item import SnapshotLineItem
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo


def _session() -> MagicMock:
    session = MagicMock()
    session.get = AsyncMock()
    session.execute = AsyncMock()
    session.flush = AsyncMock()
    session.delete = AsyncMock()
    session.add = MagicMock()
    return session


def _snapshot(status: SnapshotStatus) -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="checking-1",
        status=status,
        notes="original",
    )


def _line_item(snapshot_id) -> SnapshotLineItem:
    return SnapshotLineItem(
        id=uuid4(),
        snapshot_id=snapshot_id,
        item_type="expense",
        name="Rent",
        amount=Decimal("100.00"),
        skipped=False,
    )


def _credit_card(snapshot_id) -> SnapshotCreditCard:
    return SnapshotCreditCard(
        id=uuid4(),
        snapshot_id=snapshot_id,
        account_id="card-1",
        statement_balance=Decimal("50.00"),
        payment_strategy=PaymentStrategy.PAY_IN_FULL,
        calculated_payment=Decimal("1.00"),
    )


def _entity_result(entity) -> MagicMock:
    result = MagicMock()
    result.scalar_one_or_none.return_value = entity
    return result


async def _invoke(
    repo: MonthlySnapshotRepo,
    operation: str,
    snapshot: MonthlySnapshot,
    item: SnapshotLineItem,
    card: SnapshotCreditCard,
):
    if operation == "update":
        return await repo.update(snapshot, notes="changed")
    if operation == "update_totals":
        return await repo.update_totals(
            snapshot.id,
            income=Decimal("10.00"),
            expense=Decimal("2.00"),
            credit_card=Decimal("1.00"),
            net=Decimal("7.00"),
            transfer_in=Decimal("1.00"),
            transfer_out=Decimal("1.00"),
        )
    if operation == "delete":
        return await repo.delete(snapshot.id)
    if operation == "create_line_item":
        return await repo.create_line_item(
            snapshot.id, "expense", "Utilities", Decimal("20.00")
        )
    if operation == "update_line_item":
        return await repo.update_line_item(item.id, amount=Decimal("200.00"))
    if operation == "skip_line_item":
        return await repo.skip_line_item(item.id, skipped=True)
    if operation == "create_credit_card":
        return await repo.create_credit_card(
            snapshot.id,
            "card-2",
            Decimal("75.00"),
            PaymentStrategy.PAY_IN_FULL,
            None,
        )
    if operation == "update_credit_card":
        return await repo.update_credit_card(
            card.id, statement_balance=Decimal("500.00")
        )
    if operation == "recalculate_payment":
        return await repo.recalculate_payment(card.id)
    raise AssertionError(f"Unknown operation: {operation}")


MUTATION_OPERATIONS = [
    "update",
    "update_totals",
    "delete",
    "create_line_item",
    "update_line_item",
    "skip_line_item",
    "create_credit_card",
    "update_credit_card",
    "recalculate_payment",
]


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", MUTATION_OPERATIONS)
async def test_closed_snapshot_mutations_are_refused_without_write_side_effects(
    operation: str,
) -> None:
    """Every repository financial mutation refuses before add/delete/flush."""
    session = _session()
    snapshot = _snapshot(SnapshotStatus.CLOSED)
    item = _line_item(snapshot.id)
    card = _credit_card(snapshot.id)
    session.get.return_value = snapshot
    session.execute.return_value = _entity_result(
        item if "line_item" in operation else card
    )
    repo = MonthlySnapshotRepo(session)

    with pytest.raises(RuntimeError, match="closed and immutable"):
        await _invoke(repo, operation, snapshot, item, card)

    session.get.assert_awaited_once_with(
        MonthlySnapshot,
        snapshot.id,
        populate_existing=True,
        with_for_update=True,
    )
    session.add.assert_not_called()
    session.delete.assert_not_awaited()
    session.flush.assert_not_awaited()
    assert snapshot.notes == "original"
    assert item.amount == Decimal("100.00")
    assert item.skipped is False
    assert card.statement_balance == Decimal("50.00")
    assert card.calculated_payment == Decimal("1.00")


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", MUTATION_OPERATIONS)
async def test_open_snapshot_mutations_remain_available(operation: str) -> None:
    """Adding the close guard does not change existing open mutation behavior."""
    session = _session()
    snapshot = _snapshot(SnapshotStatus.OPEN)
    item = _line_item(snapshot.id)
    card = _credit_card(snapshot.id)
    session.get.return_value = snapshot
    session.execute.return_value = _entity_result(
        item if "line_item" in operation else card
    )
    repo = MonthlySnapshotRepo(session)

    result = await _invoke(repo, operation, snapshot, item, card)

    session.get.assert_awaited_once_with(
        MonthlySnapshot,
        snapshot.id,
        populate_existing=True,
        with_for_update=True,
    )
    session.flush.assert_awaited_once()
    if operation in {"create_line_item", "create_credit_card"}:
        session.add.assert_called_once_with(result)
    else:
        session.add.assert_not_called()
    if operation == "delete":
        session.delete.assert_awaited_once_with(snapshot)
    else:
        session.delete.assert_not_awaited()

    if operation == "update":
        assert snapshot.notes == "changed"
    elif operation == "update_totals":
        assert snapshot.net == Decimal("7.00")
    elif operation == "update_line_item":
        assert item.amount == Decimal("200.00")
    elif operation == "skip_line_item":
        assert item.skipped is True
    elif operation == "update_credit_card":
        assert card.statement_balance == Decimal("500.00")
    elif operation == "recalculate_payment":
        assert card.calculated_payment == Decimal("50.00")


@pytest.mark.asyncio
async def test_mutation_refreshes_a_stale_open_identity_under_lock() -> None:
    """A concurrent close wins over an OPEN object already in the identity map."""
    session = _session()
    stale_snapshot = _snapshot(SnapshotStatus.OPEN)
    refreshed_snapshot = _snapshot(SnapshotStatus.CLOSED)
    refreshed_snapshot.id = stale_snapshot.id
    session.get.return_value = refreshed_snapshot
    repo = MonthlySnapshotRepo(session)

    with pytest.raises(RuntimeError, match="closed and immutable"):
        await repo.update(stale_snapshot, notes="changed")

    session.get.assert_awaited_once_with(
        MonthlySnapshot,
        stale_snapshot.id,
        populate_existing=True,
        with_for_update=True,
    )
    assert stale_snapshot.notes == "original"
    assert refreshed_snapshot.notes == "original"
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("status", SnapshotStatus.CLOSED),
        ("closing_balance", Decimal("10.00")),
        ("closing_balance_frozen", True),
        ("closed_at", datetime.now(UTC)),
    ],
)
async def test_generic_update_cannot_set_guarded_close_fields(
    field: str, value
) -> None:
    """Generic updates cannot bypass the guarded close service on open rows."""
    session = _session()
    snapshot = _snapshot(SnapshotStatus.OPEN)
    original = getattr(snapshot, field)

    with pytest.raises(
        RuntimeError,
        match=r"budget_me\.snapshots\.service\.close_snapshot\(\)",
    ):
        await MonthlySnapshotRepo(session).update(snapshot, **{field: value})

    assert getattr(snapshot, field) == original
    session.add.assert_not_called()
    session.delete.assert_not_awaited()
    session.flush.assert_not_awaited()


@pytest.mark.asyncio
@pytest.mark.parametrize("method", ["close", "freeze_closing_balance"])
async def test_unguarded_close_methods_are_disabled(method: str) -> None:
    """Both legacy close entry points direct callers to the guarded service."""
    session = _session()
    with pytest.raises(
        RuntimeError,
        match=r"budget_me\.snapshots\.service\.close_snapshot\(\)",
    ):
        await getattr(MonthlySnapshotRepo(session), method)(uuid4())

    assert session.mock_calls == []
