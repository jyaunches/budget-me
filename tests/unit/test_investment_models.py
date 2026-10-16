"""Model coverage for persisted Plaid Investments data."""

from budget_me.db.models import (
    InvestmentHolding,
    InvestmentHoldingSnapshot,
    InvestmentSecurity,
    InvestmentTransaction,
)


def test_investment_models_expose_provider_keys_and_values():
    assert InvestmentSecurity.__table__.primary_key.columns.keys() == ["security_id"]
    assert "institution_value" in InvestmentHolding.__table__.columns
    assert "cost_basis" in InvestmentHolding.__table__.columns
    assert "snapshot_date" in InvestmentHoldingSnapshot.__table__.columns
    assert InvestmentTransaction.__table__.c.investment_transaction_id.unique is True


def test_holdings_have_one_current_row_per_account_and_security():
    constraints = {
        constraint.name for constraint in InvestmentHolding.__table__.constraints
    }
    assert "uq_investment_holdings_account_security" in constraints


def test_daily_snapshots_are_idempotent():
    constraints = {
        constraint.name
        for constraint in InvestmentHoldingSnapshot.__table__.constraints
    }
    assert "uq_investment_holding_snapshots_account_security_date" in constraints
