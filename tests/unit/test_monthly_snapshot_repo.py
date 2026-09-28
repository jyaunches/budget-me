"""Unit tests for MonthlySnapshotRepo."""

import inspect
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo


class TestMonthlySnapshotRepoStructure:
    """Test repository structure and method signatures."""

    def test_monthly_snapshot_repo_has_required_methods(self):
        """Test all required methods exist on single repo."""
        mock_session = MagicMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Snapshot methods
        assert hasattr(repo, "get_by_year_month")
        assert hasattr(repo, "get_all")
        assert hasattr(repo, "get_open_snapshots")
        assert hasattr(repo, "create")
        assert hasattr(repo, "create_with_defaults")
        assert hasattr(repo, "close")
        assert hasattr(repo, "update_totals")
        assert hasattr(repo, "delete")

        # Account-scoped methods
        assert hasattr(repo, "get_all_for_account")

        # Line item methods
        assert hasattr(repo, "get_line_items")
        assert hasattr(repo, "create_line_item")
        assert hasattr(repo, "update_line_item")
        assert hasattr(repo, "skip_line_item")

        # Credit card methods
        assert hasattr(repo, "get_credit_cards")
        assert hasattr(repo, "create_credit_card")
        assert hasattr(repo, "update_credit_card")
        assert hasattr(repo, "recalculate_payment")

    def test_monthly_snapshot_repo_methods_are_async(self):
        """Test all methods are coroutine functions."""
        mock_session = MagicMock()
        repo = MonthlySnapshotRepo(mock_session)

        async_methods = [
            "get_by_year_month",
            "get_all",
            "get_open_snapshots",
            "create",
            "create_with_defaults",
            "close",
            "update_totals",
            "delete",
            "get_all_for_account",
            "get_line_items",
            "create_line_item",
            "update_line_item",
            "skip_line_item",
            "get_credit_cards",
            "create_credit_card",
            "update_credit_card",
            "recalculate_payment",
        ]

        for method_name in async_methods:
            method = getattr(repo, method_name)
            assert inspect.iscoroutinefunction(method), f"{method_name} should be async"


@pytest.mark.asyncio
class TestMonthlySnapshotRepoAccountScoped:
    """Test repository account-scoped operations - unit tests with mocks."""

    async def test_get_by_year_month_requires_account_id(self):
        """Test get_by_year_month filters by account_id."""
        from unittest.mock import AsyncMock, MagicMock

        # Create mock session
        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Mock the execute result
        mock_result = AsyncMock()
        mock_snapshot = MonthlySnapshot(
            year_month="2025-12", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        mock_result.scalar_one_or_none = MagicMock(return_value=mock_snapshot)
        mock_session.execute = AsyncMock(return_value=mock_result)

        # Call method
        snapshot = await repo.get_by_year_month("2025-12", "acc-1")

        # Verify session.execute was called
        assert mock_session.execute.called
        # Verify result
        assert snapshot.account_id == "acc-1"
        assert snapshot.year_month == "2025-12"

    async def test_get_by_year_month_returns_none_for_wrong_account(self):
        """Test get_by_year_month returns None for wrong account."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Mock empty result
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none = MagicMock(return_value=None)
        mock_session.execute = AsyncMock(return_value=mock_result)

        snapshot = await repo.get_by_year_month("2025-12", "acc-2")

        assert snapshot is None

    async def test_create_snapshot_with_account_id(self):
        """Test create method accepts account_id parameter."""
        from unittest.mock import AsyncMock

        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        snapshot = await repo.create("2025-12", "acc-1")

        assert snapshot.year_month == "2025-12"
        assert snapshot.account_id == "acc-1"
        assert snapshot.status == SnapshotStatus.OPEN
        # Verify session.add and flush were called
        assert mock_session.add.called
        assert mock_session.flush.called

    async def test_get_all_for_account(self):
        """Test get_all_for_account returns only specified account's snapshots."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Mock result with 2 snapshots for account1
        mock_result = AsyncMock()
        snap1 = MonthlySnapshot(
            year_month="2025-11", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        snap2 = MonthlySnapshot(
            year_month="2025-12", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[snap2, snap1])  # Already sorted desc
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        snapshots = await repo.get_all_for_account("acc-1")

        assert len(snapshots) == 2
        assert all(s.account_id == "acc-1" for s in snapshots)

    async def test_get_all_for_account_orders_by_year_month_desc(self):
        """Test get_all_for_account orders by year_month descending."""
        from unittest.mock import AsyncMock, MagicMock

        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Mock result with snapshots in descending order
        mock_result = AsyncMock()
        snap1 = MonthlySnapshot(
            year_month="2025-12", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        snap2 = MonthlySnapshot(
            year_month="2025-11", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        snap3 = MonthlySnapshot(
            year_month="2025-10", account_id="acc-1", status=SnapshotStatus.OPEN
        )
        mock_scalars = MagicMock()
        mock_scalars.all = MagicMock(return_value=[snap1, snap2, snap3])
        mock_result.scalars = MagicMock(return_value=mock_scalars)
        mock_session.execute = AsyncMock(return_value=mock_result)

        snapshots = await repo.get_all_for_account("acc-1")

        # Verify descending order
        assert snapshots[0].year_month == "2025-12"
        assert snapshots[1].year_month == "2025-11"
        assert snapshots[2].year_month == "2025-10"

    async def test_create_with_defaults_uses_account_id(self):
        """Test create_with_defaults accepts account_id parameter."""
        from unittest.mock import AsyncMock, patch

        mock_session = AsyncMock()
        repo = MonthlySnapshotRepo(mock_session)

        # Mock update_totals to avoid needing get_by_id
        with patch.object(repo, "update_totals", new_callable=AsyncMock):
            snapshot = await repo.create_with_defaults("2025-12", "acc-1")

        assert snapshot.year_month == "2025-12"
        assert snapshot.account_id == "acc-1"
        assert snapshot.status == SnapshotStatus.OPEN


@pytest.mark.asyncio
async def test_update_totals_accepts_optional_reimbursement_flows() -> None:
    """Callers can cache both reimbursement directions without changing old args."""
    session = MagicMock()
    session.flush = AsyncMock()
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="acc-1",
        status=SnapshotStatus.OPEN,
    )
    repo = MonthlySnapshotRepo(session)
    repo._require_open_snapshot = AsyncMock(return_value=snapshot)

    await repo.update_totals(
        snapshot.id,
        income=Decimal("100.00"),
        expense=Decimal("50.00"),
        credit_card=Decimal("15.00"),
        net=Decimal("49.00"),
        transfer_in=Decimal("20.00"),
        transfer_out=Decimal("10.00"),
        reimbursement_in=Decimal("7.00"),
        reimbursement_out=Decimal("3.00"),
    )

    assert snapshot.reimbursement_in_total == Decimal("7.00")
    assert snapshot.reimbursement_out_total == Decimal("3.00")
    session.flush.assert_awaited_once_with()


@pytest.mark.asyncio
async def test_update_totals_omitted_reimbursements_default_to_plan_zero() -> None:
    """Legacy planned-total callers receive zero reimbursement defaults."""
    session = MagicMock()
    session.flush = AsyncMock()
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="acc-1",
        status=SnapshotStatus.OPEN,
        reimbursement_in_total=Decimal("7.00"),
        reimbursement_out_total=Decimal("3.00"),
    )
    repo = MonthlySnapshotRepo(session)
    repo._require_open_snapshot = AsyncMock(return_value=snapshot)

    await repo.update_totals(
        snapshot.id,
        income=Decimal("100.00"),
        expense=Decimal("50.00"),
        credit_card=Decimal("15.00"),
        net=Decimal("45.00"),
    )

    assert snapshot.reimbursement_in_total == Decimal("0.00")
    assert snapshot.reimbursement_out_total == Decimal("0.00")


def _reimbursed_open_snapshot() -> MonthlySnapshot:
    return MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="acc-1",
        status=SnapshotStatus.OPEN,
        income_total=Decimal("100.00"),
        expense_total=Decimal("50.00"),
        transfer_in_total=Decimal("20.00"),
        transfer_out_total=Decimal("10.00"),
        reimbursement_in_total=Decimal("7.00"),
        reimbursement_out_total=Decimal("3.00"),
        credit_card_total=Decimal("15.00"),
        net=Decimal("49.00"),
    )


@pytest.mark.asyncio
async def test_repo_closing_balance_includes_reimbursement_flows() -> None:
    """Current-month estimated close includes both reimbursement directions."""
    session = MagicMock()
    session.execute = AsyncMock()
    repo = MonthlySnapshotRepo(session)
    repo.get_by_year_month = AsyncMock(return_value=_reimbursed_open_snapshot())
    repo.get_starting_balance = AsyncMock(return_value=(Decimal("1000.00"), False))

    balance, is_frozen = await MonthlySnapshotRepo.get_closing_balance(
        repo, "acc-1", "2025-12"
    )

    assert balance == Decimal("1049.00")
    assert is_frozen is False
    session.execute.assert_not_awaited()


@pytest.mark.asyncio
async def test_repo_next_month_rollover_includes_reimbursement_flows() -> None:
    """An open prior month rolls its reimbursement-aware calculated close forward."""
    session = MagicMock()
    session.execute = AsyncMock()
    repo = MonthlySnapshotRepo(session)
    repo.get_by_year_month = AsyncMock(side_effect=[None, _reimbursed_open_snapshot()])
    repo.get_starting_balance = AsyncMock(return_value=(Decimal("1000.00"), False))

    balance, is_frozen = await MonthlySnapshotRepo.get_starting_balance(
        repo, "acc-1", "2026-01"
    )

    assert balance == Decimal("1049.00")
    assert is_frozen is False
    session.execute.assert_not_awaited()
