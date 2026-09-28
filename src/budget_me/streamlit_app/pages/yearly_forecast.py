"""Yearly Financial Forecast page."""

from datetime import datetime

import streamlit as st

from budget_me.streamlit_app.auth import require_auth
from budget_me.streamlit_app.db import (
    calculate_plan_vs_actual,
    calculate_yearly_projection,
    create_project,
    delete_project,
    get_projects,
    get_session,
)


def _render_summary(result: dict) -> None:
    """Render summary metrics at top of page."""
    st.subheader("Summary")
    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("Total Income", f"${result['total_income']:,.2f}")
    with col2:
        st.metric("Total Expenses", f"${result['total_expenses']:,.2f}")
    with col3:
        st.metric("Net", f"${result['total_net']:,.2f}")
    with col4:
        st.metric("Runway", f"{result['runway_months']} months")

    # Funding Summary
    col1, col2 = st.columns(2)
    with col1:
        st.metric("Funding Required", f"${result['total_funding_required']:,.2f}")
    with col2:
        total_available = sum(
            fs["available_amount"] for fs in result["funding_sources"]
        )
        remaining = total_available - result["total_funding_required"]
        st.metric(
            "Funding Available",
            f"${total_available:,.2f}",
            delta=f"${remaining:,.2f} remaining",
            delta_color="normal" if remaining >= 0 else "inverse",
        )


def _render_planned_projects(session, projects: list) -> None:
    """Render planned projects section with collapse/expand."""
    total_projects = sum(p["amount"] for p in projects) if projects else 0
    header = f"Planned Projects (Total: ${total_projects:,.0f})"

    with st.expander(header, expanded=False):
        if projects:
            for project in projects:
                col1, col2, col3, col4 = st.columns([3, 1, 1, 1])
                with col1:
                    st.text(project["name"])
                with col2:
                    st.text(project["month"])
                with col3:
                    st.text(f"${project['amount']:,.2f}")
                with col4:
                    if st.button("Delete", key=f"del_{project['id']}"):
                        if delete_project(session, project["id"]):
                            st.success("Project deleted")
                            st.rerun()
        else:
            st.info("No projects planned")

        # Add project form
        st.markdown("---")
        st.markdown("**Add New Project**")
        proj_name = st.text_input("Project Name")
        proj_col1, proj_col2 = st.columns(2)
        with proj_col1:
            proj_month = st.text_input("Month (YYYY-MM)")
        with proj_col2:
            proj_amount = st.number_input("Amount", min_value=0.0, step=100.0)

        if st.button("Add Project"):
            if proj_name and proj_month and proj_amount > 0:
                create_project(session, proj_name, proj_amount, proj_month)
                st.success(f"Added project: {proj_name}")
                st.rerun()
            else:
                st.error("Please fill all fields")


def _render_cc_projections(result: dict) -> None:
    """Render credit card projections with collapse/expand."""
    cc_projections = result.get("cc_projections", [])

    if cc_projections:
        total_cc = sum(cc["projected_payment"] for cc in cc_projections)
        avg_cc = total_cc  # Already monthly
        header = f"Credit Card Projections (Monthly: ${avg_cc:,.0f})"
    else:
        header = "Credit Card Projections"

    with st.expander(header, expanded=False):
        if cc_projections:
            cc_data = []
            for cc in cc_projections:
                cc_data.append(
                    {
                        "Card": cc["card_name"],
                        "Current Balance": f"${cc['current_balance']:,.2f}",
                        "Projected Payment": f"${cc['projected_payment']:,.2f}",
                        "Source": cc["projection_source"],
                    }
                )
            st.dataframe(cc_data, use_container_width=True, hide_index=True)
        else:
            st.info("No credit card projections available")


def _render_funding_sources(result: dict) -> None:
    """Render funding sources section."""
    if result["funding_sources"]:
        st.subheader("Funding Sources")
        for source in result["funding_sources"]:
            col1, col2, col3 = st.columns([3, 1, 1])
            with col1:
                st.text(source["name"])
                if source["notes"]:
                    st.caption(source["notes"])
            with col2:
                st.text(source["source_type"].title())
            with col3:
                st.text(f"${source['available_amount']:,.2f}")


def _render_monthly_breakdown(result: dict) -> None:
    """Render monthly breakdown table."""
    st.subheader("Monthly Breakdown")
    breakdown_data = []
    for month in result["monthly_breakdown"]:
        breakdown_data.append(
            {
                "Month": month["year_month"],
                "Income": f"${month['income']:,.0f}",
                "Fixed Exp": f"${month['fixed_expenses']:,.0f}",
                "CC Payments": f"${month['cc_payments']:,.0f}",
                "Total Exp": f"${month['total_expenses']:,.0f}",
                "Net": f"${month['net']:,.0f}",
                "Balance": f"${month['ending_balance']:,.0f}",
                "Funding": f"${month['funding_needed']:,.0f}",
            }
        )

    st.dataframe(breakdown_data, use_container_width=True, hide_index=True)


def _render_inflection_points(result: dict) -> None:
    """Render inflection points if any."""
    if result["inflection_points"]:
        st.subheader("Inflection Points")
        for point in result["inflection_points"]:
            st.warning(f"**{point['month']}:** {point['description']}")


def _render_budget_performance(session, start_month: str, months: int) -> None:
    """Render budget performance section comparing plan vs actual."""
    try:
        pva = calculate_plan_vs_actual(session, start_month, months)
    except Exception as e:
        st.error(f"Error calculating budget performance: {e}")
        return

    summary = pva["summary"]
    closed_count = summary["closed_months_count"]

    if closed_count == 0:
        st.info(
            "No closed months yet. Close monthly snapshots to see performance data."
        )
        return

    # Performance indicator
    variance = summary["total_variance_net"]
    pct = summary["performance_pct"]

    if variance > 0:
        indicator = "better"
        arrow = "↑"
    elif variance < 0:
        indicator = "worse"
        arrow = "↓"
    else:
        indicator = "on track"
        arrow = "→"

    st.markdown(
        f"**Overall:** {arrow} ${abs(variance):,.0f} {indicator} than planned "
        f"({abs(pct):.1f}% {'over' if pct > 0 else 'under'}) "
        f"across {closed_count} closed month(s)"
    )

    # Summary metrics
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric(
            "Planned Net",
            f"${summary['total_planned_net']:,.0f}",
        )
    with col2:
        st.metric(
            "Actual Net",
            f"${summary['total_actual_net']:,.0f}",
        )
    with col3:
        st.metric(
            "Variance",
            f"${variance:,.0f}",
            delta=f"{pct:+.1f}%",
            delta_color="normal" if variance >= 0 else "inverse",
        )

    # Month-by-month breakdown (closed and partial months)
    closed_months = [m for m in pva["months"] if m["status"] in ("closed", "partial")]
    if closed_months:
        breakdown_data = []
        for month in closed_months:
            # Format variance with color indicator
            var_net = month["variance_net"]
            var_exp = month["variance_expenses"]

            breakdown_data.append(
                {
                    "Month": month["year_month"],
                    "Plan Income": f"${month['planned_income']:,.0f}",
                    "Actual Income": f"${month['actual_income']:,.0f}",
                    "Plan Exp": f"${month['planned_expenses']:,.0f}",
                    "Actual Exp": f"${month['actual_expenses']:,.0f}",
                    "Exp Var": f"${var_exp:+,.0f}" if var_exp else "-",
                    "Net Var": f"${var_net:+,.0f}" if var_net else "-",
                }
            )

        st.dataframe(breakdown_data, use_container_width=True, hide_index=True)


def main():
    """Main yearly forecast page."""
    require_auth()

    st.title("Yearly Financial Forecast")
    st.markdown(
        "Multi-month cash flow projection with anticipated items and credit card payments"
    )

    # Initialize session state for projection result
    if "forecast_result" not in st.session_state:
        st.session_state.forecast_result = None
    if "forecast_start_month" not in st.session_state:
        st.session_state.forecast_start_month = None
    if "forecast_months" not in st.session_state:
        st.session_state.forecast_months = None

    # Summary at the top (if we have a result)
    if st.session_state.forecast_result:
        _render_summary(st.session_state.forecast_result)
        st.divider()

    # Controls
    col1, col2 = st.columns(2)
    with col1:
        now = datetime.now()
        default_month = f"{now.year:04d}-{now.month:02d}"
        start_month = st.text_input("Start Month (YYYY-MM)", value=default_month)
    with col2:
        months = st.slider("Projection Months", min_value=1, max_value=24, value=12)

    # Calculate projection button
    if st.button("Calculate Projection", type="primary"):
        with st.spinner("Calculating projection..."):
            with get_session() as session:
                try:
                    result = calculate_yearly_projection(
                        session, start_month=start_month, months=months
                    )
                    st.session_state.forecast_result = result
                    st.session_state.forecast_start_month = start_month
                    st.session_state.forecast_months = months
                    st.rerun()
                except Exception as e:
                    st.error(f"Error calculating projection: {e}")
                    import traceback

                    st.code(traceback.format_exc())

    # Collapsible sections (Planned Projects and CC Projections)
    with get_session() as session:
        projects = get_projects(session)
        _render_planned_projects(session, projects)

    if st.session_state.forecast_result:
        _render_cc_projections(st.session_state.forecast_result)

    st.divider()

    # Remaining sections (only if we have results)
    if st.session_state.forecast_result:
        _render_funding_sources(st.session_state.forecast_result)
        _render_monthly_breakdown(st.session_state.forecast_result)
        _render_inflection_points(st.session_state.forecast_result)

        # Budget Performance section (collapsible)
        if st.session_state.forecast_start_month and st.session_state.forecast_months:
            with st.expander("Budget Performance (Plan vs Actual)", expanded=False):
                with get_session() as session:
                    _render_budget_performance(
                        session,
                        st.session_state.forecast_start_month,
                        st.session_state.forecast_months,
                    )


if __name__ == "__main__":
    main()
