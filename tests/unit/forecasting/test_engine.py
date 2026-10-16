"""Tests for forecasting projection engine."""

from dataclasses import dataclass
from decimal import Decimal

from budget_me.forecasting.engine import (
    CardPayment,
    MonthActuals,
    calculate_projection,
    expand_anticipated_items,
    get_item_months_in_range,
    is_item_active_in_month,
)


# Mock AnticipatedItem for testing
@dataclass
class MockItem:
    name: str
    amount: Decimal
    item_type: str
    frequency: str
    category: str | None = None
    start_month: str | None = None
    end_month: str | None = None


def test_is_item_active_in_month_no_bounds():
    """Test item with no date bounds is always active."""
    item = MockItem(
        name="Example Income",
        amount=Decimal("1000.00"),
        item_type="income",
        frequency="monthly",
    )
    assert is_item_active_in_month(item, "2026-01") is True
    assert is_item_active_in_month(item, "2030-12") is True


def test_is_item_active_in_month_with_start():
    """Test item becomes active at start_month."""
    item = MockItem(
        name="New Income",
        amount=Decimal("1000.00"),
        item_type="income",
        frequency="monthly",
        start_month="2026-06",
    )
    assert is_item_active_in_month(item, "2026-05") is False
    assert is_item_active_in_month(item, "2026-06") is True
    assert is_item_active_in_month(item, "2026-07") is True


def test_is_item_active_in_month_with_end():
    """Test item stops at end_month."""
    item = MockItem(
        name="Example Expense",
        amount=Decimal("100.00"),
        item_type="expense",
        frequency="monthly",
        start_month="2099-01",
        end_month="2099-06",
    )
    assert is_item_active_in_month(item, "2099-06") is True
    assert is_item_active_in_month(item, "2099-07") is False


def test_get_item_months_monthly():
    """Test monthly item expands to all months in range."""
    item = MockItem(
        name="Example Expense",
        amount=Decimal("500.00"),
        item_type="expense",
        frequency="monthly",
    )
    months = get_item_months_in_range(item, "2026-01", "2026-03")
    assert months == ["2026-01", "2026-02", "2026-03"]


def test_get_item_months_quarterly():
    """Test quarterly item appears every 3 months."""
    item = MockItem(
        name="Quarterly Tax",
        amount=Decimal("1200.00"),
        item_type="expense",
        frequency="quarterly",
        start_month="2026-01",
    )
    # Quarterly: Jan, Apr, Jul, Oct
    months = get_item_months_in_range(item, "2026-01", "2026-12")
    assert "2026-01" in months
    assert "2026-04" in months
    assert "2026-07" in months
    assert "2026-10" in months
    assert len(months) == 4


def test_get_item_months_quarterly_uses_start_month_as_cadence_anchor():
    """Quarterly items can follow a non-calendar-quarter billing cadence."""
    item = MockItem(
        name="Quarterly Water",
        amount=Decimal("359.00"),
        item_type="expense",
        frequency="quarterly",
        start_month="2026-06",
    )

    months = get_item_months_in_range(item, "2026-01", "2027-05")

    assert months == ["2026-06", "2026-09", "2026-12", "2027-03"]


def test_get_item_months_one_time():
    """Test one-time item appears only once."""
    item = MockItem(
        name="Example Event",
        amount=Decimal("200.00"),
        item_type="expense",
        frequency="one_time",
        start_month="2099-07",
        end_month="2099-07",
    )
    months = get_item_months_in_range(item, "2099-01", "2099-12")
    assert months == ["2099-07"]


def test_expand_anticipated_items_basic():
    """Test expanding items for a date range."""
    items = [
        MockItem(
            name="Example Income",
            amount=Decimal("1000.00"),
            item_type="income",
            frequency="monthly",
        ),
        MockItem(
            name="Example Expense",
            amount=Decimal("500.00"),
            item_type="expense",
            frequency="monthly",
        ),
    ]

    expanded = expand_anticipated_items(items, "2026-01", "2026-03")

    # Each month should have both items
    assert "2026-01" in expanded
    assert len(expanded["2026-01"]) == 2
    assert "2026-02" in expanded
    assert len(expanded["2026-02"]) == 2


def test_calculate_projection_basic():
    """Test basic projection calculation."""
    items = [
        MockItem(
            name="Salary",
            amount=Decimal("10000.00"),
            item_type="income",
            frequency="monthly",
        ),
        MockItem(
            name="Expenses",
            amount=Decimal("8000.00"),
            item_type="expense",
            frequency="monthly",
        ),
    ]

    cc_payments = []

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=cc_payments,
        starting_balance=Decimal("5000.00"),
        start_month="2026-01",
        months=3,
    )

    assert len(result.monthly_breakdown) == 3
    assert result.total_income == Decimal("30000.00")
    assert result.total_fixed_expenses == Decimal("24000.00")
    assert result.total_cc_payments == Decimal("0.00")

    # Check first month
    first_month = result.monthly_breakdown[0]
    assert first_month.year_month == "2026-01"
    assert first_month.income == Decimal("10000.00")
    assert first_month.fixed_expenses == Decimal("8000.00")
    assert first_month.net == Decimal("2000.00")
    assert first_month.starting_balance == Decimal("5000.00")
    assert first_month.ending_balance == Decimal("7000.00")


def test_calculate_projection_with_cc_payments():
    """Test projection includes credit card payments."""
    items = [
        MockItem(
            name="Salary",
            amount=Decimal("10000.00"),
            item_type="income",
            frequency="monthly",
        ),
    ]

    cc_payments = [
        CardPayment(
            account_id="card1",
            card_name="Example Card A",
            projected_payment=Decimal("5000.00"),
            source="historical_3mo_avg",
        ),
    ]

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=cc_payments,
        starting_balance=Decimal("1000.00"),
        start_month="2026-01",
        months=2,
    )

    assert result.total_cc_payments == Decimal("10000.00")  # 5000 * 2 months

    first_month = result.monthly_breakdown[0]
    assert first_month.cc_payments == Decimal("5000.00")
    assert first_month.total_expenses == Decimal("5000.00")
    assert first_month.net == Decimal("5000.00")  # 10000 income - 5000 cc


def test_scheduled_card_payment_is_reported_as_card_cash_flow() -> None:
    """Dated promo payments do not appear as ordinary direct expenses."""
    items = [
        MockItem(
            name="Promo payoff",
            amount=Decimal("750.00"),
            item_type="expense",
            category="credit_card_payment",
            frequency="one_time",
            start_month="2026-12",
            end_month="2026-12",
        )
    ]

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=[],
        starting_balance=Decimal("1000.00"),
        start_month="2026-12",
        months=1,
    )

    month = result.monthly_breakdown[0]
    assert month.fixed_expenses == Decimal("0.00")
    assert month.cc_payments == Decimal("750.00")
    assert month.total_expenses == Decimal("750.00")


def test_calculate_projection_funding_needed():
    """Test that funding is needed when balance goes negative."""
    items = [
        MockItem(
            name="Income",
            amount=Decimal("5000.00"),
            item_type="income",
            frequency="monthly",
        ),
        MockItem(
            name="Expenses",
            amount=Decimal("8000.00"),
            item_type="expense",
            frequency="monthly",
        ),
    ]

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=[],
        starting_balance=Decimal("2000.00"),
        start_month="2026-01",
        months=2,
    )

    # Month 1: Start 2000, income 5000, expense 8000, net -3000, end 0 (need 1000 funding)
    # Month 2: Start 0, income 5000, expense 8000, net -3000, end 0 (need 3000 funding)
    assert result.monthly_breakdown[0].funding_needed == Decimal("1000.00")
    assert result.monthly_breakdown[0].ending_balance == Decimal("0.00")
    assert result.monthly_breakdown[1].funding_needed == Decimal("3000.00")
    assert result.total_funding_required == Decimal("4000.00")


def test_calculate_projection_with_actuals_for_one_month():
    """Test projection uses actual data for closed months."""

    # Set up anticipated items
    items = [
        MockItem(
            name="Salary",
            amount=Decimal("10000.00"),
            item_type="income",
            frequency="monthly",
        ),
        MockItem(
            name="Rent",
            amount=Decimal("2000.00"),
            item_type="expense",
            frequency="monthly",
        ),
    ]

    cc_payments = [
        CardPayment(
            account_id="card1",
            card_name="Example Card B",
            projected_payment=Decimal("1000.00"),
            source="manual",
        ),
    ]

    # Create actuals for January 2026 (closed month)
    # Actual income was higher, expenses lower than anticipated
    actuals_by_month = {
        "2026-01": MonthActuals(
            income=Decimal("14500.00"),  # Includes actual transfers/reimbursements
            expenses=Decimal("1850.00"),  # Includes actual transfers/reimbursements
            cc_payments=Decimal("1200.00"),  # Actual CC payment
            closing_balance=Decimal("14300.00"),  # Actual ending balance
            starting_balance=Decimal("2850.00"),
            earned_income=Decimal("12000.00"),
            transfer_in=Decimal("2000.00"),
            equity_disbursements=Decimal("1750.00"),
            reimbursement_in=Decimal("500.00"),
            direct_expenses=Decimal("1500.00"),
            transfer_out=Decimal("250.00"),
            reimbursement_out=Decimal("100.00"),
        ),
    }

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=cc_payments,
        starting_balance=Decimal("5000.00"),
        start_month="2026-01",
        months=3,
        actuals_by_month=actuals_by_month,
    )

    # Check first month uses actuals
    jan = result.monthly_breakdown[0]
    assert jan.year_month == "2026-01"
    assert jan.data_source == "closed_actual"
    assert jan.income == Decimal("14500.00")  # All actual inflows
    assert jan.earned_income == Decimal("12000.00")
    assert jan.transfer_in == Decimal("2000.00")
    assert jan.equity_disbursements == Decimal("1750.00")
    assert jan.reimbursement_in == Decimal("500.00")
    assert jan.fixed_expenses == Decimal("1850.00")  # All non-card outflows
    assert jan.direct_expenses == Decimal("1500.00")
    assert jan.transfer_out == Decimal("250.00")
    assert jan.reimbursement_out == Decimal("100.00")
    assert jan.cc_payments == Decimal("1200.00")  # From actuals
    assert jan.starting_balance == Decimal("2850.00")
    assert jan.ending_balance == Decimal("14300.00")  # From actuals

    # Check second month uses anticipated (no actuals provided)
    feb = result.monthly_breakdown[1]
    assert feb.data_source == "forecast"
    assert feb.year_month == "2026-02"
    assert feb.income == Decimal("10000.00")  # From anticipated
    assert feb.fixed_expenses == Decimal("2000.00")  # From anticipated
    assert feb.cc_payments == Decimal("1000.00")  # From projections
    # Starting balance should be Jan's closing balance
    assert feb.starting_balance == Decimal("14300.00")

    # Totals should include both actual and projected months
    assert result.total_income == Decimal("34500.00")  # 14500 + 10000 + 10000


def test_calculate_projection_with_actuals_for_multiple_months():
    """Test projection uses actuals for multiple closed months."""

    items = [
        MockItem(
            name="Salary",
            amount=Decimal("10000.00"),
            item_type="income",
            frequency="monthly",
        ),
    ]

    # Actuals for Jan and Feb
    actuals_by_month = {
        "2026-01": MonthActuals(
            income=Decimal("11000.00"),
            expenses=Decimal("5000.00"),
            cc_payments=Decimal("2000.00"),
            closing_balance=Decimal("9000.00"),
        ),
        "2026-02": MonthActuals(
            income=Decimal("12000.00"),
            expenses=Decimal("6000.00"),
            cc_payments=Decimal("2500.00"),
            closing_balance=Decimal("12500.00"),
        ),
    }

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=[],
        starting_balance=Decimal("5000.00"),
        start_month="2026-01",
        months=3,
        actuals_by_month=actuals_by_month,
    )

    # Jan uses actuals
    jan = result.monthly_breakdown[0]
    assert jan.income == Decimal("11000.00")
    assert jan.ending_balance == Decimal("9000.00")

    # Feb uses actuals and Jan's closing as starting
    feb = result.monthly_breakdown[1]
    assert feb.income == Decimal("12000.00")
    assert feb.starting_balance == Decimal("9000.00")
    assert feb.ending_balance == Decimal("12500.00")

    # Mar uses anticipated and Feb's closing as starting
    mar = result.monthly_breakdown[2]
    assert mar.income == Decimal("10000.00")  # From anticipated
    assert mar.starting_balance == Decimal("12500.00")  # From Feb actuals


def test_calculate_projection_actuals_none_uses_anticipated():
    """Test that passing None for actuals_by_month uses anticipated items."""
    items = [
        MockItem(
            name="Salary",
            amount=Decimal("10000.00"),
            item_type="income",
            frequency="monthly",
        ),
    ]

    result = calculate_projection(
        anticipated_items=items,
        credit_card_payments=[],
        starting_balance=Decimal("5000.00"),
        start_month="2026-01",
        months=2,
        actuals_by_month=None,
    )

    # All months should use anticipated items
    assert result.monthly_breakdown[0].income == Decimal("10000.00")
    assert result.monthly_breakdown[1].income == Decimal("10000.00")
