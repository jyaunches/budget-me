"""Behavioral tests for immutable closed-snapshot reporting."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.forecasting.engine import ProjectionResult
from budget_me.streamlit_app import db


def _closed_snapshot(**overrides) -> MonthlySnapshot:
    values = {
        "id": uuid4(),
        "year_month": "2025-12",
        "account_id": "checking-1",
        "status": SnapshotStatus.CLOSED,
        "income_total": Decimal("100.00"),
        "expense_total": Decimal("50.00"),
        "transfer_in_total": Decimal("20.00"),
        "transfer_out_total": Decimal("10.00"),
        "reimbursement_in_total": Decimal("7.00"),
        "reimbursement_out_total": Decimal("3.00"),
        "credit_card_total": Decimal("15.00"),
        "net": Decimal("49.00"),
        "closing_balance": Decimal("1049.00"),
        "closing_balance_frozen": True,
    }
    values.update(overrides)
    return MonthlySnapshot(**values)


def _scalar_result(snapshot):
    result = MagicMock()
    result.scalar_one_or_none.return_value = snapshot
    return result


def _scalars_result(snapshots):
    result = MagicMock()
    result.scalars.return_value.all.return_value = snapshots
    return result


def test_closed_account_and_household_reports_never_read_mutable_children() -> None:
    """Line-item/card edits and skipped rows cannot affect a closed header."""
    snapshot = _closed_snapshot()

    account_session = MagicMock()
    account_session.execute.side_effect = [
        _scalar_result(snapshot),
        AssertionError("closed account report queried mutable child rows"),
    ]
    account_totals = db.calculate_snapshot_totals(
        account_session, "2025-12", "checking-1"
    )
    assert account_totals == {
        "income_total": 100.0,
        "expense_total": 50.0,
        "transfer_in_total": 20.0,
        "transfer_out_total": 10.0,
        "reimbursement_in_total": 7.0,
        "reimbursement_out_total": 3.0,
        "credit_card_total": 15.0,
        "net": 49.0,
        "closing_balance": 1049.0,
    }
    account_session.execute.assert_called_once()

    household_session = MagicMock()
    household_session.execute.side_effect = [
        _scalars_result([snapshot]),
        AssertionError("closed household report queried mutable child rows"),
    ]
    household = db.get_snapshot_totals(household_session, "2025-12", include_open=False)
    assert household == db.SnapshotTotals(
        income=Decimal("100.00"),
        expenses=Decimal("50.00"),
        cc_payments=Decimal("15.00"),
        closing_balance=Decimal("1049.00"),
        transfer_in=Decimal("20.00"),
        transfer_out=Decimal("10.00"),
        net=Decimal("49.00"),
        reimbursement_in=Decimal("7.00"),
        reimbursement_out=Decimal("3.00"),
    )
    household_session.execute.assert_called_once()


def test_incomplete_or_incoherent_closed_headers_fail_closed() -> None:
    """Missing actuals and contradictory cached net are never zero-filled."""
    for snapshot in (
        _closed_snapshot(credit_card_total=None),
        _closed_snapshot(reimbursement_in_total=None),
        _closed_snapshot(reimbursement_out_total=None),
        _closed_snapshot(net=Decimal("999.00")),
        _closed_snapshot(closing_balance_frozen=False),
    ):
        household_session = MagicMock()
        household_session.execute.return_value = _scalars_result([snapshot])
        assert (
            db.get_snapshot_totals(household_session, "2025-12", include_open=False)
            is None
        )

        account_session = MagicMock()
        account_session.execute.return_value = _scalar_result(snapshot)
        with pytest.raises(ValueError, match="complete, coherent cached header"):
            db.calculate_snapshot_totals(account_session, "2025-12", "checking-1")


def test_historical_card_average_uses_closed_cached_monthly_totals() -> None:
    """A complete household month sums cached card actuals."""
    snapshots = [
        _closed_snapshot(
            account_id="checking-1",
            credit_card_total=Decimal("10.00"),
            net=Decimal("54.00"),
        ),
        _closed_snapshot(
            account_id="checking-2",
            credit_card_total=Decimal("20.00"),
            net=Decimal("44.00"),
        ),
    ]
    session = MagicMock()
    session.execute.return_value = _scalars_result(snapshots)

    # Fewer than the requested three complete months preserves the established
    # behavior of returning the newest complete month rather than averaging.
    assert db.get_historical_cc_average(session, months=3) == Decimal("30.00")

    statement = str(session.execute.call_args.args[0])
    assert "monthly_snapshots" in statement
    assert "snapshot_credit_cards" not in statement


def test_historical_card_average_excludes_partially_closed_household_month() -> None:
    """A mixed open/closed household month is not historical actual data."""
    session = MagicMock()
    session.execute.return_value = _scalars_result(
        [
            _closed_snapshot(account_id="checking-1"),
            _closed_snapshot(
                account_id="checking-2",
                status=SnapshotStatus.OPEN,
                closing_balance_frozen=False,
            ),
        ]
    )

    assert db.get_historical_cc_average(session, months=3) is None


@pytest.mark.parametrize(
    "overrides",
    [
        {"credit_card_total": None},
        {"reimbursement_in_total": None},
        {"reimbursement_out_total": None},
        {"net": Decimal("999.00")},
        {"closing_balance_frozen": False},
    ],
    ids=[
        "missing-card",
        "missing-reimbursement-in",
        "missing-reimbursement-out",
        "incoherent",
        "not-frozen",
    ],
)
def test_historical_card_average_excludes_invalid_closed_header(overrides) -> None:
    """Every closed row must pass the full frozen-header coherence check."""
    session = MagicMock()
    session.execute.return_value = _scalars_result([_closed_snapshot(**overrides)])

    assert db.get_historical_cc_average(session, months=3) is None


def _empty_projection_result() -> ProjectionResult:
    zero = Decimal("0.00")
    return ProjectionResult(
        monthly_breakdown=[],
        total_income=zero,
        total_fixed_expenses=zero,
        total_cc_payments=zero,
        total_expenses=zero,
        total_net=zero,
        total_funding_required=zero,
        runway_months=0,
    )


def test_yearly_projection_preserves_closed_cash_flow_net() -> None:
    """Transfers map into engine flows while cached cards stay separate."""
    totals = db.SnapshotTotals(
        income=Decimal("100.00"),
        expenses=Decimal("50.00"),
        cc_payments=Decimal("15.00"),
        closing_balance=Decimal("1049.00"),
        transfer_in=Decimal("20.00"),
        transfer_out=Decimal("10.00"),
        net=Decimal("49.00"),
        reimbursement_in=Decimal("7.00"),
        reimbursement_out=Decimal("3.00"),
    )
    session = MagicMock()
    captured = {}

    def calculate_projection(**kwargs):
        captured.update(kwargs)
        return _empty_projection_result()

    with (
        patch.object(db, "get_anticipated_items_for_forecast", return_value=[]),
        patch.object(db, "get_historical_cc_average", return_value=None),
        patch.object(db, "get_credit_card_projections", return_value=[]),
        patch.object(db, "get_funding_sources", return_value=[]),
        patch.object(
            db, "get_aggregate_checking_balance", return_value=Decimal("1000.00")
        ),
        patch.object(db, "get_snapshot_totals", return_value=totals) as get_totals,
        patch(
            "budget_me.forecasting.engine.calculate_projection",
            side_effect=calculate_projection,
        ),
    ):
        db.calculate_yearly_projection(session, start_month="2025-12", months=1)

    actual = captured["actuals_by_month"]["2025-12"]
    assert actual.income == Decimal("127.00")
    assert actual.expenses == Decimal("63.00")
    assert actual.cc_payments == Decimal("15.00")
    assert actual.income - actual.expenses - actual.cc_payments == totals.net
    assert actual.closing_balance == Decimal("1049.00")
    get_totals.assert_called_once_with(session, "2025-12", include_open=False)


def test_plan_vs_actual_reports_inclusive_flows_and_cached_net() -> None:
    """Compatibility totals are inclusive and granular fields explain them."""
    snapshot = _closed_snapshot()
    totals = db.SnapshotTotals(
        income=Decimal("100.00"),
        expenses=Decimal("50.00"),
        cc_payments=Decimal("15.00"),
        closing_balance=Decimal("1049.00"),
        transfer_in=Decimal("20.00"),
        transfer_out=Decimal("10.00"),
        net=Decimal("49.00"),
        reimbursement_in=Decimal("7.00"),
        reimbursement_out=Decimal("3.00"),
    )
    session = MagicMock()
    session.execute.return_value = _scalars_result([snapshot])

    with (
        patch.object(db, "get_anticipated_items_for_forecast", return_value=[]),
        patch.object(db, "get_snapshot_totals", return_value=totals),
    ):
        report = db.calculate_plan_vs_actual(session, start_month="2025-12", months=1)

    month = report["months"][0]
    assert month["actual_base_income"] == 100.0
    assert month["actual_transfer_in"] == 20.0
    assert month["actual_reimbursement_in"] == 7.0
    assert month["actual_inflows"] == month["actual_income"] == 127.0
    assert month["actual_base_expenses"] == 50.0
    assert month["actual_transfer_out"] == 10.0
    assert month["actual_reimbursement_out"] == 3.0
    assert month["actual_cc_payments"] == 15.0
    assert month["actual_outflows"] == month["actual_expenses"] == 78.0
    assert month["actual_net"] == 49.0

    summary = report["summary"]
    assert summary["total_actual_inflows"] == 127.0
    assert summary["total_actual_outflows"] == 78.0
    assert summary["total_actual_reimbursement_in"] == 7.0
    assert summary["total_actual_reimbursement_out"] == 3.0
    assert summary["total_actual_cc_payments"] == 15.0
    assert summary["total_actual_net"] == 49.0


def test_unsynced_open_snapshot_uses_planned_children_and_zero_reimbursements() -> None:
    """An ordinary plan ignores stale cached actuals until reconciliation."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="checking-1",
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("1000.00"),
        reimbursement_in_total=Decimal("7.00"),
        reimbursement_out_total=Decimal("3.00"),
        last_synced_at=None,
    )
    items = [
        SimpleNamespace(item_type="income", amount=Decimal("100.00")),
        SimpleNamespace(item_type="expense", amount=Decimal("50.00")),
        SimpleNamespace(item_type="transfer_in", amount=Decimal("20.00")),
        SimpleNamespace(item_type="transfer_out", amount=Decimal("10.00")),
    ]
    cards = [SimpleNamespace(calculated_payment=Decimal("15.00"))]
    session = MagicMock()
    session.execute.side_effect = [
        _scalar_result(snapshot),
        _scalars_result(items),
        _scalars_result(cards),
    ]

    totals = db.calculate_snapshot_totals(session, "2025-12", "checking-1")

    assert totals == {
        "income_total": 100.0,
        "expense_total": 50.0,
        "transfer_in_total": 20.0,
        "transfer_out_total": 10.0,
        "reimbursement_in_total": 0.0,
        "reimbursement_out_total": 0.0,
        "credit_card_total": 15.0,
        "net": 45.0,
        "closing_balance": 1045.0,
    }


def test_reconciled_open_snapshot_uses_complete_cached_actual_header() -> None:
    """A receipt timestamp switches every reported flow to coherent actuals."""
    snapshot = _closed_snapshot(
        status=SnapshotStatus.OPEN,
        starting_balance=Decimal("1000.00"),
        closing_balance_frozen=False,
        last_synced_at=datetime(2026, 8, 10, tzinfo=UTC),
    )
    session = MagicMock()
    session.execute.side_effect = [
        _scalar_result(snapshot),
        AssertionError("reconciled open report queried mutable planned children"),
    ]

    totals = db.calculate_snapshot_totals(session, "2025-12", "checking-1")

    assert totals == {
        "income_total": 100.0,
        "expense_total": 50.0,
        "transfer_in_total": 20.0,
        "transfer_out_total": 10.0,
        "reimbursement_in_total": 7.0,
        "reimbursement_out_total": 3.0,
        "credit_card_total": 15.0,
        "net": 49.0,
        "closing_balance": 1049.0,
    }
    session.execute.assert_called_once()


def test_reconciled_open_snapshot_requires_coherent_cached_actual_header() -> None:
    """A timestamp cannot bless missing or contradictory cached actuals."""
    for snapshot in (
        _closed_snapshot(
            status=SnapshotStatus.OPEN,
            closing_balance_frozen=False,
            credit_card_total=None,
            last_synced_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
        _closed_snapshot(
            status=SnapshotStatus.OPEN,
            closing_balance_frozen=False,
            net=Decimal("999.00"),
            last_synced_at=datetime(2026, 8, 10, tzinfo=UTC),
        ),
    ):
        session = MagicMock()
        session.execute.return_value = _scalar_result(snapshot)

        with pytest.raises(ValueError, match="complete, coherent cached header"):
            db.calculate_snapshot_totals(session, "2025-12", "checking-1")


def test_existing_snapshot_read_shape_includes_reimbursement_cache() -> None:
    """The Streamlit snapshot header exposes both reimbursement directions."""
    snapshot = _closed_snapshot()
    session = MagicMock()
    session.execute.return_value = _scalar_result(snapshot)

    result = db.get_or_create_snapshot(session, "2025-12", "checking-1")

    assert result["reimbursement_in_total"] == 7.0
    assert result["reimbursement_out_total"] == 3.0


def test_close_wrapper_return_shape_includes_reimbursement_cache() -> None:
    """Guarded close results expose both reimbursement directions to the UI."""
    preview = SimpleNamespace(
        snapshot_id=str(uuid4()),
        year_month="2025-12",
        account_id="checking-1",
        totals=SimpleNamespace(
            income_total=Decimal("100.00"),
            expense_total=Decimal("50.00"),
            transfer_in_total=Decimal("20.00"),
            transfer_out_total=Decimal("10.00"),
            reimbursement_in_total=Decimal("7.00"),
            reimbursement_out_total=Decimal("3.00"),
            credit_card_total=Decimal("15.00"),
            net=Decimal("49.00"),
        ),
        closing_balance_to_freeze=Decimal("1049.00"),
        closed_at=datetime(2026, 8, 10, tzinfo=UTC),
    )

    with patch(
        "budget_me.snapshots.service.close_snapshot", return_value=preview
    ) as guarded_close:
        result = db.close_snapshot(
            MagicMock(),
            "2025-12",
            "checking-1",
            confirm_month="2025-12",
            audit_hash="a" * 64,
        )

    assert result["reimbursement_in_total"] == 7.0
    assert result["reimbursement_out_total"] == 3.0
    guarded_close.assert_called_once()


def test_open_closing_balance_uses_reimbursement_aware_net() -> None:
    """Estimated close delegates to the coherent net instead of rebuilding flows."""
    snapshot = MonthlySnapshot(
        id=uuid4(),
        year_month="2025-12",
        account_id="checking-1",
        status=SnapshotStatus.OPEN,
    )
    session = MagicMock()
    session.execute.return_value = _scalar_result(snapshot)
    totals = {
        "income_total": 100.0,
        "expense_total": 50.0,
        "transfer_in_total": 20.0,
        "transfer_out_total": 10.0,
        "reimbursement_in_total": 7.0,
        "reimbursement_out_total": 3.0,
        "credit_card_total": 15.0,
        "net": 49.0,
    }

    with (
        patch.object(
            db, "get_starting_balance", return_value=(Decimal("1000.00"), False)
        ),
        patch.object(db, "calculate_snapshot_totals", return_value=totals),
    ):
        closing, is_frozen = db.get_closing_balance(session, "checking-1", "2025-12")

    assert closing == Decimal("1049.00")
    assert is_frozen is False
