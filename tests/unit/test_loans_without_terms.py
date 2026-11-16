"""Synced loan balances remain visible before statement terms are entered."""

from contextlib import contextmanager
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from streamlit.testing.v1 import AppTest

from budget_me.streamlit_app import db


@pytest.fixture
def loan_session():
    engine = create_engine("sqlite://")
    with engine.begin() as connection:
        for ddl in (
            "CREATE TABLE plaid_items (id TEXT PRIMARY KEY, institution_name TEXT, status TEXT)",
            "CREATE TABLE accounts (account_id TEXT PRIMARY KEY, plaid_item_id TEXT, "
            "name TEXT, display_name TEXT, mask TEXT, type TEXT, subtype TEXT, "
            "balance_current NUMERIC, is_excluded BOOLEAN, updated_at DATETIME)",
            "CREATE TABLE loan_details (account_id TEXT, loan_type TEXT, interest_rate NUMERIC, "
            "monthly_payment NUMERIC, maturity_date DATE, lender_name TEXT, "
            "collateral_description TEXT, source TEXT, updated_at DATETIME)",
        ):
            connection.execute(text(ddl))
        connection.execute(
            text(
                "INSERT INTO plaid_items VALUES ('test-item', 'Example Lender', 'active')"
            )
        )
        connection.execute(
            text(
                "INSERT INTO accounts VALUES ('test-auto', 'test-item', 'Example Auto Loan', "
                "NULL, '0000', 'loan', 'auto', 10000, false, '2026-01-01 00:00:00')"
            )
        )
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_synced_loan_without_terms_retains_balance_and_unknowns(loan_session):
    loans = db.get_loans_with_interest(loan_session)
    assert len(loans) == 1
    assert loans[0]["balance"] == 10000
    assert loans[0]["loan_type"] == "auto"
    assert loans[0]["lender_name"] == "Example Lender"
    for field in (
        "interest_rate",
        "monthly_payment",
        "monthly_interest",
        "maturity_date",
    ):
        assert loans[0][field] is None


@pytest.mark.parametrize(
    "change",
    [
        "UPDATE accounts SET is_excluded = true",
        "UPDATE plaid_items SET status = 'revoked'",
        "UPDATE accounts SET type = 'credit'",
    ],
)
def test_hidden_and_nonloan_accounts_stay_out(loan_session, change):
    loan_session.execute(text(change))
    assert db.get_loans_with_interest(loan_session) == []


def test_recorded_zero_rate_is_known_not_missing(loan_session):
    loan_session.execute(
        text(
            "INSERT INTO loan_details (account_id, loan_type, interest_rate, monthly_payment) "
            "VALUES ('test-auto', 'auto', 0, 200)"
        )
    )
    loan = db.get_loans_with_interest(loan_session)[0]
    assert loan["interest_rate"] == 0
    assert loan["monthly_interest"] == 0
    assert loan["monthly_payment"] == 200


def test_debt_page_renders_missing_terms_and_counts_balance(loan_session, monkeypatch):
    @contextmanager
    def session_scope():
        yield loan_session

    loans = db.get_loans_with_interest(loan_session)
    monkeypatch.setattr(db, "get_loans_with_interest", lambda session: loans)
    monkeypatch.setattr(db, "get_session", session_scope)
    for name in (
        "get_cc_calculated_interest",
        "get_cc_interest_from_transactions",
        "get_zero_percent_balance_schedule",
        "get_expiring_promos",
    ):
        monkeypatch.setattr(db, name, lambda *args, **kwargs: [])
    app = AppTest.from_file(
        Path("src/budget_me/streamlit_app/pages/debt.py").resolve()
    ).run()
    assert not app.exception
    assert (
        next(metric for metric in app.metric if metric.label == "Total Debt").value
        == "$10,000.00"
    )
    assert any("Auto Loan" in expander.label for expander in app.expander)
    assert any("terms are missing" in message.value for message in app.info)
    assert any("Rate: **Not provided**" in value.value for value in app.markdown)
