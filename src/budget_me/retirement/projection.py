"""Pure retirement projection calculations used by the Streamlit UI."""

from dataclasses import dataclass


@dataclass(frozen=True)
class RetirementAssumptions:
    """Inputs for a deterministic retirement scenario.

    Rates are decimals (for example, ``0.07`` means 7%). Monetary values use
    the display currency selected by the caller.
    """

    current_year: int
    retirement_year: int
    current_investments: float = 0.0
    annual_salary: float = 0.0
    employee_contribution_rate: float = 0.0
    employer_contribution_rate: float = 0.0
    annual_equity_awards: float = 0.0
    equity_investment_rate: float = 1.0
    other_annual_contributions: float = 0.0
    salary_growth_rate: float = 0.0
    equity_award_growth_rate: float = 0.0
    investment_growth_rate: float = 0.0
    home_value: float = 0.0
    mortgage_balance: float = 0.0
    home_appreciation_rate: float = 0.0
    mortgage_interest_rate: float = 0.0
    monthly_mortgage_payment: float = 0.0
    inflation_rate: float = 0.0
    withdrawal_rate: float = 0.04


@dataclass(frozen=True)
class RetirementProjectionPoint:
    """Projected balances at the end of a calendar year."""

    year: int
    salary: float
    annual_contribution: float
    investments: float
    home_value: float
    mortgage_balance: float
    home_equity: float
    total_net_worth: float
    real_total_net_worth: float


@dataclass(frozen=True)
class RetirementProjection:
    """A complete retirement scenario and its headline results."""

    points: tuple[RetirementProjectionPoint, ...]
    years_to_retirement: int
    total_contributions: float
    retirement_investments: float
    retirement_home_equity: float
    retirement_net_worth: float
    retirement_net_worth_today: float
    annual_retirement_income: float
    annual_retirement_income_today: float


def _validate_assumptions(assumptions: RetirementAssumptions) -> None:
    if assumptions.retirement_year < assumptions.current_year:
        raise ValueError("Retirement year cannot be before the current year")

    monetary_fields = (
        "current_investments",
        "annual_salary",
        "annual_equity_awards",
        "other_annual_contributions",
        "home_value",
        "mortgage_balance",
        "monthly_mortgage_payment",
    )
    for field_name in monetary_fields:
        if getattr(assumptions, field_name) < 0:
            raise ValueError(f"{field_name} cannot be negative")

    rate_fields = (
        "employee_contribution_rate",
        "employer_contribution_rate",
        "equity_investment_rate",
        "salary_growth_rate",
        "equity_award_growth_rate",
        "investment_growth_rate",
        "home_appreciation_rate",
        "mortgage_interest_rate",
        "inflation_rate",
        "withdrawal_rate",
    )
    for field_name in rate_fields:
        if getattr(assumptions, field_name) < 0:
            raise ValueError(f"{field_name} cannot be negative")

    if assumptions.equity_investment_rate > 1:
        raise ValueError("equity_investment_rate cannot exceed 1")


def _project_mortgage_year(
    balance: float, annual_interest_rate: float, monthly_payment: float
) -> float:
    """Amortize a mortgage for up to twelve monthly payments."""
    monthly_rate = annual_interest_rate / 12
    for _ in range(12):
        if balance <= 0:
            return 0.0
        interest = balance * monthly_rate
        balance = max(0.0, balance + interest - monthly_payment)
    return balance


def project_retirement(
    assumptions: RetirementAssumptions,
) -> RetirementProjection:
    """Project holdings, contributions, and home equity through retirement.

    Contributions are modeled at mid-year, so they receive half a year of the
    assumed investment return in their contribution year. Existing holdings
    receive a full year's return. Salary contributions and equity awards grow
    independently. The mortgage is amortized monthly.
    """
    _validate_assumptions(assumptions)

    years = assumptions.retirement_year - assumptions.current_year
    investments = assumptions.current_investments
    salary = assumptions.annual_salary
    equity_awards = assumptions.annual_equity_awards
    home_value = assumptions.home_value
    mortgage_balance = assumptions.mortgage_balance
    total_contributions = 0.0

    initial_home_equity = home_value - mortgage_balance
    initial_net_worth = investments + initial_home_equity
    points = [
        RetirementProjectionPoint(
            year=assumptions.current_year,
            salary=salary,
            annual_contribution=0.0,
            investments=investments,
            home_value=home_value,
            mortgage_balance=mortgage_balance,
            home_equity=initial_home_equity,
            total_net_worth=initial_net_worth,
            real_total_net_worth=initial_net_worth,
        )
    ]

    for year_number in range(1, years + 1):
        annual_contribution = (
            salary
            * (
                assumptions.employee_contribution_rate
                + assumptions.employer_contribution_rate
            )
            + equity_awards * assumptions.equity_investment_rate
            + assumptions.other_annual_contributions
        )
        total_contributions += annual_contribution

        investments = investments * (
            1 + assumptions.investment_growth_rate
        ) + annual_contribution * (1 + assumptions.investment_growth_rate / 2)
        home_value *= 1 + assumptions.home_appreciation_rate
        mortgage_balance = _project_mortgage_year(
            mortgage_balance,
            assumptions.mortgage_interest_rate,
            assumptions.monthly_mortgage_payment,
        )
        home_equity = home_value - mortgage_balance
        total_net_worth = investments + home_equity
        inflation_factor = (1 + assumptions.inflation_rate) ** year_number

        points.append(
            RetirementProjectionPoint(
                year=assumptions.current_year + year_number,
                salary=salary,
                annual_contribution=annual_contribution,
                investments=investments,
                home_value=home_value,
                mortgage_balance=mortgage_balance,
                home_equity=home_equity,
                total_net_worth=total_net_worth,
                real_total_net_worth=total_net_worth / inflation_factor,
            )
        )

        salary *= 1 + assumptions.salary_growth_rate
        equity_awards *= 1 + assumptions.equity_award_growth_rate

    retirement_net_worth = points[-1].total_net_worth
    retirement_investments = points[-1].investments
    retirement_home_equity = points[-1].home_equity
    retirement_net_worth_today = points[-1].real_total_net_worth
    annual_retirement_income = retirement_investments * assumptions.withdrawal_rate
    retirement_inflation_factor = (1 + assumptions.inflation_rate) ** years

    return RetirementProjection(
        points=tuple(points),
        years_to_retirement=years,
        total_contributions=total_contributions,
        retirement_investments=retirement_investments,
        retirement_home_equity=retirement_home_equity,
        retirement_net_worth=retirement_net_worth,
        retirement_net_worth_today=retirement_net_worth_today,
        annual_retirement_income=annual_retirement_income,
        annual_retirement_income_today=(
            annual_retirement_income / retirement_inflation_factor
        ),
    )
