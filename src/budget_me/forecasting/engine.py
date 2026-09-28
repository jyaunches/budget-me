"""Pure-function projection engine for multi-month cash flow forecasting."""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass
class CardPayment:
    """Credit card payment projection for forecast."""

    account_id: str
    card_name: str
    projected_payment: Decimal
    source: str  # "fixed", "historical_3mo_avg", "manual", "current_balance"


@dataclass
class MonthActuals:
    """Actual data from closed monthly snapshots."""

    income: Decimal
    expenses: Decimal
    cc_payments: Decimal
    closing_balance: Decimal  # Used as next month's starting balance


@dataclass
class MonthProjection:
    """Single month's projection data."""

    year_month: str
    income: Decimal
    fixed_expenses: Decimal  # From anticipated_items
    cc_payments: Decimal  # From credit card projections
    total_expenses: Decimal  # fixed_expenses + cc_payments
    net: Decimal
    starting_balance: Decimal
    ending_balance: Decimal
    funding_needed: Decimal  # How much to draw from sources this month
    cumulative_funding: Decimal  # Total drawn so far
    notes: list[str] = field(default_factory=list)  # Inflection points, one-time items


@dataclass
class ProjectionResult:
    """Complete projection output."""

    monthly_breakdown: list[MonthProjection]
    total_income: Decimal
    total_fixed_expenses: Decimal
    total_cc_payments: Decimal
    total_expenses: Decimal
    total_net: Decimal
    total_funding_required: Decimal
    runway_months: int  # Months until balance hits zero (without funding)
    inflection_points: list[dict] = field(default_factory=list)  # {month, description}


def parse_year_month(year_month: str) -> tuple[int, int]:
    """Parse 'YYYY-MM' string into (year, month) tuple."""
    parts = year_month.split("-")
    return int(parts[0]), int(parts[1])


def format_year_month(year: int, month: int) -> str:
    """Format year and month into 'YYYY-MM' string."""
    return f"{year:04d}-{month:02d}"


def add_months(year_month: str, months: int) -> str:
    """Add months to a year-month string."""
    year, month = parse_year_month(year_month)
    month += months
    while month > 12:
        month -= 12
        year += 1
    while month < 1:
        month += 12
        year -= 1
    return format_year_month(year, month)


def is_item_active_in_month(item: Any, year_month: str) -> bool:
    """Check if item should be included in given month."""
    # If start_month is set and we're before it, not active
    if hasattr(item, "start_month") and item.start_month:
        if year_month < item.start_month:
            return False

    # If end_month is set and we're after it, not active
    if hasattr(item, "end_month") and item.end_month:
        if year_month > item.end_month:
            return False

    return True


def get_item_months_in_range(item: Any, start: str, end: str) -> list[str]:
    """Get all months where item occurs within range."""
    frequency = item.frequency
    months = []

    # Generate all months in range
    current = start
    all_months = []
    while current <= end:
        all_months.append(current)
        current = add_months(current, 1)

    if frequency == "monthly":
        # Appears in all active months
        for month in all_months:
            if is_item_active_in_month(item, month):
                months.append(month)

    elif frequency == "quarterly":
        # Appears in Jan, Apr, Jul, Oct (months 1, 4, 7, 10)
        for month in all_months:
            if is_item_active_in_month(item, month):
                _, m = parse_year_month(month)
                if m in [1, 4, 7, 10]:
                    months.append(month)

    elif frequency == "annual":
        # Appears only in the month specified by start_month
        if hasattr(item, "start_month") and item.start_month:
            _, start_m = parse_year_month(item.start_month)
            for month in all_months:
                if is_item_active_in_month(item, month):
                    _, m = parse_year_month(month)
                    if m == start_m:
                        months.append(month)

    elif frequency == "one_time":
        # Appears only in start_month
        if hasattr(item, "start_month") and item.start_month:
            if item.start_month in all_months:
                if is_item_active_in_month(item, item.start_month):
                    months.append(item.start_month)

    return months


def expand_anticipated_items(
    items: list[Any], start_month: str, end_month: str
) -> dict[str, list[dict]]:
    """Expand items into month-by-month occurrences.

    Returns {year_month: [item_dicts]}
    """
    expanded = {}

    for item in items:
        # Get months where this item occurs
        item_months = get_item_months_in_range(item, start_month, end_month)

        for month in item_months:
            if month not in expanded:
                expanded[month] = []

            expanded[month].append(
                {
                    "name": item.name,
                    "amount": item.amount,
                    "item_type": item.item_type,
                    "frequency": item.frequency,
                }
            )

    return expanded


def calculate_projection(
    anticipated_items: list[Any],
    credit_card_payments: list[CardPayment],
    starting_balance: Decimal,
    start_month: str,
    months: int = 12,
    actuals_by_month: dict[str, MonthActuals] | None = None,
) -> ProjectionResult:
    """Calculate multi-month projection (combined household view).

    Algorithm:
    1. Expand anticipated_items for date range
    2. Sum credit card payments (same each month - projections are monthly)
    3. For each month:
       a. Check if actuals exist in actuals_by_month
       b. If actuals exist:
          - Use actual income/expenses/cc_payments
          - Use actual closing_balance as next month's starting_balance
       c. If no actuals:
          - Sum income items for month
          - Sum expense items for month (fixed_expenses)
          - Add credit card payments (cc_payments)
          - total_expenses = fixed_expenses + cc_payments
          - Calculate net = income - total_expenses
          - Calculate ending_balance = starting_balance + net
          - If ending_balance < 0:
            * funding_needed = abs(ending_balance)
            * ending_balance = 0
       d. Next month starting_balance = this month ending_balance
    4. Calculate runway: months until balance < 0 (if no funding)
    5. Identify inflection points from item end dates
    """
    # Calculate end month
    end_month = add_months(start_month, months - 1)

    # Expand anticipated items
    expanded = expand_anticipated_items(anticipated_items, start_month, end_month)

    # Sum CC payments per month (same amount each month)
    total_cc_per_month = sum(cc.projected_payment for cc in credit_card_payments)

    # Track totals
    total_income = Decimal("0.00")
    total_fixed_expenses = Decimal("0.00")
    total_cc_payments = Decimal("0.00")
    total_funding_required = Decimal("0.00")
    cumulative_funding = Decimal("0.00")

    # Calculate month by month
    monthly_breakdown = []
    current_balance = starting_balance
    runway_months = 0
    runway_calculated = False

    current_month = start_month
    for _ in range(months):
        # Check if we have actuals for this month
        month_actuals = (
            actuals_by_month.get(current_month) if actuals_by_month else None
        )

        if month_actuals:
            # Use actual data from closed snapshot
            month_income = month_actuals.income
            month_fixed_expenses = month_actuals.expenses
            month_cc_payments = month_actuals.cc_payments
            month_starting = current_balance
            month_ending = month_actuals.closing_balance
            month_total_expenses = month_fixed_expenses + month_cc_payments
            month_net = month_income - month_total_expenses
            month_funding = Decimal("0.00")  # Actuals don't need funding
        else:
            # Use anticipated items (current behavior)
            month_items = expanded.get(current_month, [])

            # Sum income and expenses
            month_income = sum(
                item["amount"] for item in month_items if item["item_type"] == "income"
            )
            month_fixed_expenses = sum(
                item["amount"] for item in month_items if item["item_type"] == "expense"
            )

            # Add CC payments
            month_cc_payments = total_cc_per_month

            # Calculate totals
            month_total_expenses = month_fixed_expenses + month_cc_payments
            month_net = month_income - month_total_expenses

            # Calculate ending balance
            month_starting = current_balance
            month_ending = month_starting + month_net

            # Check if funding needed
            month_funding = Decimal("0.00")
            if month_ending < 0:
                month_funding = abs(month_ending)
                month_ending = Decimal("0.00")
                cumulative_funding += month_funding
                total_funding_required += month_funding

        # Calculate runway (first month balance goes to zero)
        if not runway_calculated:
            if month_ending == 0 and month_funding > 0:
                runway_calculated = True
            else:
                runway_months += 1

        # Track totals
        total_income += month_income
        total_fixed_expenses += month_fixed_expenses
        total_cc_payments += month_cc_payments

        # Create month projection
        projection = MonthProjection(
            year_month=current_month,
            income=month_income,
            fixed_expenses=month_fixed_expenses,
            cc_payments=month_cc_payments,
            total_expenses=month_total_expenses,
            net=month_net,
            starting_balance=month_starting,
            ending_balance=month_ending,
            funding_needed=month_funding,
            cumulative_funding=cumulative_funding,
            notes=[],
        )
        monthly_breakdown.append(projection)

        # Move to next month
        current_balance = month_ending
        current_month = add_months(current_month, 1)

    # Calculate total net
    total_expenses = total_fixed_expenses + total_cc_payments
    total_net = total_income - total_expenses

    # Find inflection points (items ending)
    inflection_points = []
    for item in anticipated_items:
        if hasattr(item, "end_month") and item.end_month:
            # Check if end_month is in our range
            if start_month <= item.end_month <= end_month:
                inflection_points.append(
                    {
                        "month": item.end_month,
                        "description": f"{item.name} ends (${item.amount}/mo)",
                    }
                )

    return ProjectionResult(
        monthly_breakdown=monthly_breakdown,
        total_income=total_income,
        total_fixed_expenses=total_fixed_expenses,
        total_cc_payments=total_cc_payments,
        total_expenses=total_expenses,
        total_net=total_net,
        total_funding_required=total_funding_required,
        runway_months=runway_months,
        inflection_points=inflection_points,
    )
