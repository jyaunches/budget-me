"""Tests for the debt page's 0% promotional payoff schedule query."""

from datetime import date
from decimal import Decimal
from unittest.mock import Mock

from budget_me.streamlit_app.db import get_zero_percent_balance_schedule


def test_zero_percent_schedule_returns_each_promotional_balance():
    session = Mock()
    result = Mock()
    result.fetchall.return_value = [
        Mock(
            account_name="Example Card",
            mask="1234",
            balance_subject_to_apr=Decimal("2500.00"),
            promo_rate_end_date=date(2027, 1, 15),
            promo_offer_id="offer-1",
        ),
        Mock(
            account_name="Example Card",
            mask="1234",
            balance_subject_to_apr=Decimal("900.50"),
            promo_rate_end_date=date(2027, 8, 1),
            promo_offer_id="offer-2",
        ),
    ]
    session.execute.return_value = result

    schedule = get_zero_percent_balance_schedule(session)

    assert schedule == [
        {
            "account_name": "Example Card",
            "mask": "1234",
            "balance": 2500.0,
            "promo_rate_end_date": date(2027, 1, 15),
            "promo_offer_id": "offer-1",
        },
        {
            "account_name": "Example Card",
            "mask": "1234",
            "balance": 900.5,
            "promo_rate_end_date": date(2027, 8, 1),
            "promo_offer_id": "offer-2",
        },
    ]


def test_debt_page_displays_zero_percent_payoff_schedule():
    source = open("src/budget_me/streamlit_app/pages/debt.py", encoding="utf-8").read()

    assert "get_zero_percent_balance_schedule" in source
    assert "0% Balance Payoff Schedule" in source
    assert "Pay By (0% Ends)" in source
