"""Tests for deterministic retirement projection calculations."""

import pytest

from budget_me.retirement.projection import (
    RetirementAssumptions,
    project_retirement,
)


def test_zero_year_projection_returns_current_net_worth():
    result = project_retirement(
        RetirementAssumptions(
            current_year=2036,
            retirement_year=2036,
            current_investments=500_000,
            home_value=400_000,
            mortgage_balance=100_000,
        )
    )

    assert result.years_to_retirement == 0
    assert len(result.points) == 1
    assert result.retirement_investments == 500_000
    assert result.retirement_home_equity == 300_000
    assert result.retirement_net_worth == 800_000


def test_salary_contributions_and_growth_compound():
    result = project_retirement(
        RetirementAssumptions(
            current_year=2026,
            retirement_year=2028,
            current_investments=100_000,
            annual_salary=100_000,
            employee_contribution_rate=0.10,
            employer_contribution_rate=0.05,
            salary_growth_rate=0.10,
            investment_growth_rate=0.08,
        )
    )

    assert result.points[1].annual_contribution == pytest.approx(15_000)
    assert result.points[2].annual_contribution == pytest.approx(16_500)
    assert result.total_contributions == pytest.approx(31_500)
    assert result.retirement_investments == pytest.approx(150_648)


def test_equity_awards_only_count_invested_fraction():
    result = project_retirement(
        RetirementAssumptions(
            current_year=2026,
            retirement_year=2027,
            annual_equity_awards=40_000,
            equity_investment_rate=0.5,
            investment_growth_rate=0.10,
        )
    )

    assert result.total_contributions == 20_000
    assert result.retirement_investments == pytest.approx(21_000)


def test_home_appreciation_and_mortgage_amortization_build_equity():
    result = project_retirement(
        RetirementAssumptions(
            current_year=2026,
            retirement_year=2027,
            home_value=500_000,
            home_appreciation_rate=0.03,
            mortgage_balance=120_000,
            mortgage_interest_rate=0.0,
            monthly_mortgage_payment=1_000,
        )
    )

    assert result.points[-1].home_value == pytest.approx(515_000)
    assert result.points[-1].mortgage_balance == pytest.approx(108_000)
    assert result.retirement_home_equity == pytest.approx(407_000)


def test_inflation_adjusts_net_worth_and_retirement_income():
    result = project_retirement(
        RetirementAssumptions(
            current_year=2026,
            retirement_year=2027,
            current_investments=100_000,
            inflation_rate=0.05,
            withdrawal_rate=0.04,
        )
    )

    assert result.retirement_net_worth_today == pytest.approx(100_000 / 1.05)
    assert result.annual_retirement_income == 4_000
    assert result.annual_retirement_income_today == pytest.approx(4_000 / 1.05)


@pytest.mark.parametrize(
    "changes",
    [
        {"retirement_year": 2025},
        {"current_investments": -1},
        {"investment_growth_rate": -0.01},
        {"equity_investment_rate": 1.01},
    ],
)
def test_invalid_assumptions_are_rejected(changes):
    defaults = {"current_year": 2026, "retirement_year": 2036}
    defaults.update(changes)

    with pytest.raises(ValueError):
        project_retirement(RetirementAssumptions(**defaults))
