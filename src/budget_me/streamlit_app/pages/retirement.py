"""Interactive retirement planning projection."""

import math
from datetime import datetime

import plotly.graph_objects as go
import streamlit as st

from budget_me.retirement import RetirementAssumptions, project_retirement
from budget_me.streamlit_app.auth import require_auth
from budget_me.streamlit_app.db import (
    get_investment_holdings_summary,
    get_session,
)

MANUAL_HOLDING_ROWS = (
    {
        "Include": False,
        "Institution": "Example Brokerage",
        "Account": "Example retirement account",
        "Type": "Retirement",
        "Currency": "USD",
        "Current value": 0.0,
        "FX to USD": 1.0,
        "Source": "Example manual row",
    },
)

FX_TO_USD_DEFAULTS = {
    "USD": 1.0,
    "GBP": 1.25,
    "EUR": 1.10,
    "CAD": 0.74,
    "Other": 1.0,
}


def _money(value: float) -> str:
    return f"${value:,.0f}"


def _nonnegative_number(value: object) -> float:
    """Return a safe non-negative float for an editable table value."""
    try:
        number = float(value)
    except (TypeError, ValueError):
        return 0.0
    return number if math.isfinite(number) and number >= 0 else 0.0


def _load_starting_holdings() -> tuple[list[dict], str | None]:
    """Seed the editor from Plaid holdings and a synthetic manual example."""
    linked_rows: list[dict] = []
    load_error = None
    try:
        with get_session() as session:
            holdings = get_investment_holdings_summary(session)
    except Exception as exc:  # The planner remains useful without a database.
        holdings = []
        load_error = str(exc)

    for holding in holdings:
        raw_currency = (holding.get("currency") or "USD").upper()
        currency = raw_currency if raw_currency in FX_TO_USD_DEFAULTS else "Other"
        linked_rows.append(
            {
                "Include": not holding.get("is_excluded", False),
                "Institution": holding.get("institution_name") or "Linked account",
                "Account": holding.get("display_name") or holding.get("name"),
                "Type": holding.get("subtype") or holding.get("type") or "Investment",
                "Currency": currency,
                "Current value": holding.get("current_value") or 0.0,
                "FX to USD": FX_TO_USD_DEFAULTS[currency],
                "Source": "Plaid Investments holdings",
            }
        )

    linked_institutions = {(row["Institution"] or "").casefold() for row in linked_rows}
    manual_rows = []
    for configured_row in MANUAL_HOLDING_ROWS:
        row = dict(configured_row)
        institution = row["Institution"].casefold()
        if any(
            institution in linked_name or linked_name in institution
            for linked_name in linked_institutions
        ):
            row["Include"] = False
            row["Source"] = "Manual fallback (Plaid holdings loaded)"
        manual_rows.append(row)

    return linked_rows + manual_rows, load_error


def _render_projection_chart(projection) -> None:
    years = [point.year for point in projection.points]
    investments = [point.investments for point in projection.points]
    home_equity = [point.home_equity for point in projection.points]
    real_net_worth = [point.real_total_net_worth for point in projection.points]

    figure = go.Figure()
    figure.add_trace(
        go.Scatter(
            x=years,
            y=investments,
            name="Investments",
            mode="lines",
            stackgroup="assets",
            line={"color": "#34A853"},
            hovertemplate="$%{y:,.0f}<extra>Investments</extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=years,
            y=home_equity,
            name="Home equity",
            mode="lines",
            stackgroup="assets",
            line={"color": "#4285F4"},
            hovertemplate="$%{y:,.0f}<extra>Home equity</extra>",
        )
    )
    figure.add_trace(
        go.Scatter(
            x=years,
            y=real_net_worth,
            name="Net worth in today's dollars",
            mode="lines",
            line={"color": "#5F6368", "dash": "dash", "width": 3},
            hovertemplate="$%{y:,.0f}<extra>Today's dollars</extra>",
        )
    )
    figure.update_layout(
        height=470,
        hovermode="x unified",
        margin={"l": 10, "r": 10, "t": 30, "b": 10},
        legend={"orientation": "h", "y": 1.08},
        xaxis_title=None,
        yaxis_title="USD",
        yaxis_tickprefix="$",
        yaxis_tickformat=",.0f",
    )
    st.plotly_chart(figure, use_container_width=True)


def _render_yearly_table(projection) -> None:
    table_rows = [
        {
            "Year": point.year,
            "Salary": point.salary,
            "Contributions": point.annual_contribution,
            "Investments": point.investments,
            "Home value": point.home_value,
            "Mortgage": point.mortgage_balance,
            "Home equity": point.home_equity,
            "Net worth": point.total_net_worth,
            "Today's dollars": point.real_total_net_worth,
        }
        for point in projection.points
    ]
    money_column = st.column_config.NumberColumn(format="$%.0f")
    st.dataframe(
        table_rows,
        column_config={
            column: money_column for column in table_rows[0] if column != "Year"
        },
        hide_index=True,
        use_container_width=True,
    )


def main() -> None:
    """Render the retirement planner."""
    require_auth()
    current_year = datetime.now().year

    st.title("Retirement Planner")
    st.caption(
        "Explore how retirement timing, contributions, equity awards, market growth, "
        "and home equity could change your projected holdings."
    )

    if "retirement_starting_holdings" not in st.session_state:
        rows, load_error = _load_starting_holdings()
        st.session_state.retirement_starting_holdings = rows
        st.session_state.retirement_holdings_load_error = load_error

    retirement_year = st.slider(
        "Retirement year",
        min_value=current_year,
        max_value=current_year + 50,
        value=min(current_year + 16, current_year + 50),
        help="Move this between years such as 2036 and 2042 to compare outcomes.",
    )
    st.caption(
        f"Projecting {retirement_year - current_year} years, from {current_year} "
        f"through {retirement_year}."
    )

    st.subheader("Starting investment holdings")
    st.write(
        "Edit balances, add accounts, or turn off rows. Non-USD holdings are "
        "converted using your editable FX rate."
    )
    if st.session_state.retirement_holdings_load_error:
        st.info(
            "Linked balances could not be loaded, so the manual placeholders are "
            "shown instead."
        )

    if st.button(
        "Reload stored Plaid holdings",
        help="Reload holdings already synchronized from Plaid.",
    ):
        rows, load_error = _load_starting_holdings()
        st.session_state.retirement_starting_holdings = rows
        st.session_state.retirement_holdings_load_error = load_error
        st.session_state.pop("retirement_holdings_editor", None)
        st.rerun()

    edited_holdings = st.data_editor(
        st.session_state.retirement_starting_holdings,
        num_rows="dynamic",
        hide_index=True,
        use_container_width=True,
        key="retirement_holdings_editor",
        column_config={
            "Include": st.column_config.CheckboxColumn(default=True),
            "Institution": st.column_config.TextColumn(required=True),
            "Account": st.column_config.TextColumn(required=True),
            "Type": st.column_config.TextColumn(),
            "Currency": st.column_config.SelectboxColumn(
                options=["USD", "GBP", "EUR", "CAD", "Other"],
                required=True,
            ),
            "Current value": st.column_config.NumberColumn(
                min_value=0.0, step=1_000.0, format="%.2f", required=True
            ),
            "FX to USD": st.column_config.NumberColumn(
                min_value=0.0, step=0.01, format="%.4f", required=True
            ),
            "Source": st.column_config.TextColumn(disabled=True),
        },
    )

    current_investments = 0.0
    for _, row in edited_holdings.iterrows():
        if bool(row.get("Include", False)):
            current_investments += _nonnegative_number(
                row.get("Current value")
            ) * _nonnegative_number(row.get("FX to USD"))

    st.metric("Starting investments (USD)", _money(current_investments))
    st.caption(
        "Rows labeled Plaid Investments holdings are pulled from the Investments "
        "product. Use Link Account to authorize an existing or new institution, "
        "then reload this table. Manual fallbacks remain editable."
    )

    income_tab, home_tab, model_tab = st.tabs(
        ["Income & contributions", "Home", "Growth assumptions"]
    )
    with income_tab:
        salary_col, employee_col, employer_col = st.columns(3)
        with salary_col:
            annual_salary = st.number_input(
                "Current annual salary",
                min_value=0.0,
                value=0.0,
                step=5_000.0,
                help="Gross annual salary used to calculate percentage contributions.",
            )
        with employee_col:
            employee_contribution_pct = st.number_input(
                "Your contribution rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=15.0,
                step=0.5,
            )
        with employer_col:
            employer_contribution_pct = st.number_input(
                "Employer contribution rate (%)",
                min_value=0.0,
                max_value=100.0,
                value=4.0,
                step=0.5,
            )

        equity_col, invested_col, other_col = st.columns(3)
        with equity_col:
            annual_equity_awards = st.number_input(
                "Annual equity awards",
                min_value=0.0,
                value=0.0,
                step=5_000.0,
                help="Use the expected annual value at vest. Existing vested shares belong above.",
            )
        with invested_col:
            equity_investment_pct = st.number_input(
                "Equity awards retained/invested (%)",
                min_value=0.0,
                max_value=100.0,
                value=100.0,
                step=5.0,
            )
        with other_col:
            other_annual_contributions = st.number_input(
                "Other annual contributions",
                min_value=0.0,
                value=0.0,
                step=1_000.0,
            )

    with home_tab:
        home_col, mortgage_col = st.columns(2)
        with home_col:
            home_value = st.number_input(
                "Current home value", min_value=0.0, value=0.0, step=10_000.0
            )
        with mortgage_col:
            mortgage_balance = st.number_input(
                "Current mortgage balance",
                min_value=0.0,
                value=0.0,
                step=10_000.0,
            )
        rate_col, payment_col = st.columns(2)
        with rate_col:
            mortgage_interest_pct = st.number_input(
                "Mortgage interest rate (%)",
                min_value=0.0,
                max_value=30.0,
                value=0.0,
                step=0.125,
            )
        with payment_col:
            monthly_mortgage_payment = st.number_input(
                "Monthly principal & interest payment",
                min_value=0.0,
                value=0.0,
                step=100.0,
                help="Exclude taxes, insurance, and HOA fees.",
            )

    with model_tab:
        growth_col, salary_growth_col, equity_growth_col = st.columns(3)
        with growth_col:
            investment_growth_pct = st.number_input(
                "Investment growth (%)",
                min_value=0.0,
                max_value=30.0,
                value=7.0,
                step=0.25,
            )
        with salary_growth_col:
            salary_growth_pct = st.number_input(
                "Salary growth (%)",
                min_value=0.0,
                max_value=20.0,
                value=3.0,
                step=0.25,
            )
        with equity_growth_col:
            equity_award_growth_pct = st.number_input(
                "Equity award growth (%)",
                min_value=0.0,
                max_value=30.0,
                value=3.0,
                step=0.25,
            )

        home_growth_col, inflation_col, withdrawal_col = st.columns(3)
        with home_growth_col:
            home_appreciation_pct = st.number_input(
                "Home appreciation (%)",
                min_value=0.0,
                max_value=20.0,
                value=3.0,
                step=0.25,
            )
        with inflation_col:
            inflation_pct = st.number_input(
                "Inflation (%)",
                min_value=0.0,
                max_value=20.0,
                value=2.5,
                step=0.25,
            )
        with withdrawal_col:
            withdrawal_pct = st.number_input(
                "Illustrative withdrawal rate (%)",
                min_value=0.0,
                max_value=20.0,
                value=4.0,
                step=0.25,
            )

    projection = project_retirement(
        RetirementAssumptions(
            current_year=current_year,
            retirement_year=retirement_year,
            current_investments=current_investments,
            annual_salary=annual_salary,
            employee_contribution_rate=employee_contribution_pct / 100,
            employer_contribution_rate=employer_contribution_pct / 100,
            annual_equity_awards=annual_equity_awards,
            equity_investment_rate=equity_investment_pct / 100,
            other_annual_contributions=other_annual_contributions,
            salary_growth_rate=salary_growth_pct / 100,
            equity_award_growth_rate=equity_award_growth_pct / 100,
            investment_growth_rate=investment_growth_pct / 100,
            home_value=home_value,
            mortgage_balance=mortgage_balance,
            home_appreciation_rate=home_appreciation_pct / 100,
            mortgage_interest_rate=mortgage_interest_pct / 100,
            monthly_mortgage_payment=monthly_mortgage_payment,
            inflation_rate=inflation_pct / 100,
            withdrawal_rate=withdrawal_pct / 100,
        )
    )

    st.divider()
    st.subheader(f"Estimated position in {retirement_year}")
    metric_one, metric_two, metric_three, metric_four = st.columns(4)
    with metric_one:
        st.metric("Investment holdings", _money(projection.retirement_investments))
    with metric_two:
        st.metric("Home equity", _money(projection.retirement_home_equity))
    with metric_three:
        st.metric("Total net worth", _money(projection.retirement_net_worth))
    with metric_four:
        st.metric(
            "Net worth in today's dollars",
            _money(projection.retirement_net_worth_today),
        )

    income_one, income_two, contribution_metric = st.columns(3)
    with income_one:
        st.metric(
            f"Annual income at {withdrawal_pct:g}%",
            _money(projection.annual_retirement_income),
        )
    with income_two:
        st.metric(
            "Annual income in today's dollars",
            _money(projection.annual_retirement_income_today),
        )
    with contribution_metric:
        st.metric(
            "Contributions through retirement", _money(projection.total_contributions)
        )

    _render_projection_chart(projection)

    with st.expander("Year-by-year projection"):
        _render_yearly_table(projection)

    with st.expander("How this projection works"):
        st.markdown(
            """
            - Annual contributions = salary × (your rate + employer rate) + equity
              awards × retained/invested percentage + other contributions.
            - Existing investments grow for a full year. New contributions are
              treated as arriving mid-year and receive half a year's return.
            - Salary and equity awards grow at their own editable rates.
            - Home value appreciates annually and the mortgage amortizes monthly.
            - Today's-dollar figures discount nominal results by the inflation rate.

            This is a deterministic planning estimate, not financial advice. It does
            not yet model taxes, investment fees, vesting cliffs, contribution limits,
            Social Security, pensions as income streams, or post-retirement spending.
            """
        )


main()
