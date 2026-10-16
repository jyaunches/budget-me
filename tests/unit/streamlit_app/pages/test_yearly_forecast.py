"""Tests for the yearly forecast page."""

from contextlib import nullcontext
from decimal import Decimal
from unittest.mock import call, patch

from budget_me.streamlit_app.pages import yearly_forecast


def test_render_summary_handles_decimal_funding_sources() -> None:
    """Database Decimal values can be compared with float projection totals."""
    result = {
        "total_earned_income": 120_000.0,
        "total_equity_disbursements": 10_000.0,
        "total_expenses": 100_000.0,
        "total_net": 30_000.0,
        "actual_months_count": 8,
        "forecast_months_count": 5,
        "total_funding_required": 74_051.77,
        "funding_sources": [
            {
                "available_amount": Decimal("100000.00"),
                "notes": "Placeholder equity balance",
            }
        ],
    }

    column_groups = [
        [nullcontext() for _ in range(4)],
        [nullcontext() for _ in range(2)],
    ]
    with (
        patch.object(yearly_forecast.st, "subheader"),
        patch.object(yearly_forecast.st, "columns", side_effect=column_groups),
        patch.object(yearly_forecast.st, "metric") as metric,
        patch.object(yearly_forecast.st, "caption"),
        patch.object(yearly_forecast.st, "warning"),
    ):
        yearly_forecast._render_summary(result)

    assert (
        call(
            "Funding Available",
            "$100,000.00",
            delta="$25,948.23 remaining",
            delta_color="normal",
        )
        in metric.call_args_list
    )
