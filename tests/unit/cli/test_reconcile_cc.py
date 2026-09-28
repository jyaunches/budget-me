"""Behavioral tests for credit-card payment reconciliation."""

from contextlib import asynccontextmanager
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from budget_me.cli.commands import reconcile_cc
from budget_me.cli.main import app

runner = CliRunner()


def _runtime_dependencies(payments, *, old_amount, old_date):
    session = SimpleNamespace(commit=AsyncMock(), rollback=AsyncMock())
    snapshot = SimpleNamespace(
        id=uuid4(),
        year_month="2026-07",
        account_id="checking-account",
    )
    card = SimpleNamespace(
        id=uuid4(),
        account_id="card-account",
        actual_payment_amount=old_amount,
        actual_payment_date=old_date,
    )

    snapshot_repo = Mock()
    snapshot_repo.get_open_snapshots = AsyncMock(return_value=[snapshot])
    snapshot_repo.get_credit_cards = AsyncMock(return_value=[card])
    snapshot_repo.update_credit_card = AsyncMock()

    transaction_repo = Mock()
    transaction_repo.get_card_payments = AsyncMock(return_value=payments)
    transaction_repo.get_pending_card_payments = AsyncMock(return_value=[])

    accounts_repo = Mock()
    accounts_repo.get_all = AsyncMock(
        return_value=[
            SimpleNamespace(
                account_id="checking-account",
                display_name="Example Checking",
                name="Checking",
                mask="0001",
            ),
            SimpleNamespace(
                account_id="card-account",
                display_name="Example Card",
                name="Card",
                mask="0002",
            ),
        ]
    )
    return session, snapshot_repo, transaction_repo, accounts_repo, card


@pytest.mark.asyncio
async def test_reconcile_uses_posted_total_and_latest_payment_date() -> None:
    """A confirmed apply persists the posted total and latest payment date."""
    payments = [
        SimpleNamespace(amount=Decimal("-20.00"), date=date(2026, 7, 5), pending=False),
        SimpleNamespace(
            amount=Decimal("-900.00"), date=date(2026, 7, 31), pending=True
        ),
        SimpleNamespace(
            amount=Decimal("-30.00"), date=date(2026, 7, 20), pending=False
        ),
    ]
    session, snapshot_repo, transaction_repo, accounts_repo, card = (
        _runtime_dependencies(
            payments,
            old_amount=Decimal("50.00"),
            old_date=date(2026, 7, 5),
        )
    )

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07",
            "checking-account",
            apply=True,
            confirm_month="2026-07",
        )

    assert exit_code == 0
    snapshot_repo.update_credit_card.assert_awaited_once_with(
        card.id,
        actual_payment_amount=Decimal("50.00"),
        actual_payment_date=date(2026, 7, 20),
    )
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_dry_run_rolls_back_without_writing() -> None:
    """Dry-run computes changes but never persists them."""
    payments = [
        SimpleNamespace(amount=Decimal("-25.00"), date=date(2026, 7, 12), pending=False)
    ]
    session, snapshot_repo, transaction_repo, accounts_repo, _ = _runtime_dependencies(
        payments,
        old_amount=Decimal("10.00"),
        old_date=date(2026, 7, 1),
    )

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07", "checking-account", dry_run=True
        )

    assert exit_code == 0
    snapshot_repo.update_credit_card.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reconcile_defaults_to_preview_and_rolls_back() -> None:
    """Omitting --dry-run still leaves every proposed change unpersisted."""
    payments = [
        SimpleNamespace(amount=Decimal("-25.00"), date=date(2026, 7, 12), pending=False)
    ]
    session, snapshot_repo, transaction_repo, accounts_repo, _ = _runtime_dependencies(
        payments,
        old_amount=Decimal("10.00"),
        old_date=date(2026, 7, 1),
    )

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async("2026-07", "checking-account")

    assert exit_code == 0
    snapshot_repo.update_credit_card.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_reconcile_records_zero_when_no_payment_posted() -> None:
    """A completed zero-payment review is stored as zero rather than NULL."""
    session, snapshot_repo, transaction_repo, accounts_repo, card = (
        _runtime_dependencies([], old_amount=None, old_date=None)
    )

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07",
            "checking-account",
            apply=True,
            confirm_month="2026-07",
        )

    assert exit_code == 0
    snapshot_repo.update_credit_card.assert_awaited_once_with(
        card.id,
        actual_payment_amount=Decimal("0"),
        actual_payment_date=None,
    )
    session.commit.assert_awaited_once_with()
    session.rollback.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_refuses_pending_payment_without_storing_zero() -> None:
    """A pending-only card blocks the transaction instead of becoming zero."""
    session, snapshot_repo, transaction_repo, accounts_repo, _ = _runtime_dependencies(
        [], old_amount=None, old_date=None
    )
    transaction_repo.get_pending_card_payments.return_value = [
        SimpleNamespace(
            amount=Decimal("-75.00"),
            date=date(2026, 7, 30),
            pending=True,
        )
    ]

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07",
            "checking-account",
            apply=True,
            confirm_month="2026-07",
        )

    assert exit_code == 2
    transaction_repo.get_pending_card_payments.assert_awaited_once_with(
        "card-account", date(2026, 7, 1), date(2026, 7, 31)
    )
    transaction_repo.get_card_payments.assert_not_awaited()
    snapshot_repo.update_credit_card.assert_not_awaited()
    session.commit.assert_not_awaited()
    session.rollback.assert_awaited_once_with()


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("dry_run", "apply", "confirm_month", "message"),
    [
        (True, True, "2026-07", "choose --dry-run or --apply"),
        (False, True, None, "requires --confirm-month"),
        (False, True, "2026-06", "exactly match"),
    ],
)
async def test_invalid_apply_options_never_open_a_database_session(
    dry_run: bool,
    apply: bool,
    confirm_month: str | None,
    message: str,
    capsys,
) -> None:
    """Usage errors stop before any database read, mutation, or commit."""
    session_scope = Mock()

    with patch.object(reconcile_cc, "_reconcile_session", session_scope):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07",
            "checking-account",
            dry_run=dry_run,
            apply=apply,
            confirm_month=confirm_month,
        )

    assert exit_code == 1
    assert message in capsys.readouterr().out
    session_scope.assert_not_called()


def test_cli_defaults_to_preview_mode(monkeypatch) -> None:
    """The public command delegates with apply disabled unless requested."""
    reconcile = AsyncMock(return_value=0)
    monkeypatch.setattr(reconcile_cc, "_reconcile_async", reconcile)

    result = runner.invoke(
        app,
        [
            "reconcile-cc",
            "--month",
            "2026-07",
            "--account",
            "checking-account",
        ],
    )

    assert result.exit_code == 0
    reconcile.assert_awaited_once_with(
        "2026-07",
        "checking-account",
        dry_run=False,
        apply=False,
        confirm_month=None,
    )


@pytest.mark.parametrize(
    "arguments",
    [
        ["--dry-run", "--apply", "--confirm-month", "2026-07"],
        ["--apply"],
        ["--apply", "--confirm-month", "2026-06"],
    ],
)
def test_cli_rejects_unsafe_apply_options_before_async_work(
    monkeypatch, arguments: list[str]
) -> None:
    """Typer exposes the same fail-closed validation as the async boundary."""
    reconcile = AsyncMock(return_value=0)
    monkeypatch.setattr(reconcile_cc, "_reconcile_async", reconcile)

    result = runner.invoke(
        app,
        ["reconcile-cc", "--month", "2026-07", *arguments],
    )

    assert result.exit_code == 1
    reconcile.assert_not_awaited()


@pytest.mark.asyncio
async def test_reconcile_preserves_checking_evidence_missing_from_card_feed() -> None:
    session, snapshot_repo, transaction_repo, accounts_repo, card = (
        _runtime_dependencies(
            [],
            old_amount=Decimal("180.00"),
            old_date=date(2026, 7, 23),
        )
    )
    card.actual_payment_source = "checking_account"
    card.actual_payment_transaction_id = uuid4()
    card.actual_payment_note = "Exact posted checking transaction."

    @asynccontextmanager
    async def session_context():
        yield session

    with (
        patch.object(reconcile_cc, "_reconcile_session", session_context),
        patch.object(reconcile_cc, "MonthlySnapshotRepo", return_value=snapshot_repo),
        patch.object(reconcile_cc, "TransactionsRepo", return_value=transaction_repo),
        patch.object(reconcile_cc, "AccountsRepo", return_value=accounts_repo),
    ):
        exit_code = await reconcile_cc._reconcile_async(
            "2026-07",
            "checking-account",
            apply=True,
            confirm_month="2026-07",
        )

    assert exit_code == 0
    snapshot_repo.update_credit_card.assert_not_awaited()
    session.commit.assert_awaited_once_with()
