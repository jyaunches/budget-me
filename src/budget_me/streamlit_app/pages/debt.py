"""Unified Debt Dashboard - All debt (mortgage, auto, credit cards) with interest analysis."""

from datetime import date

import pandas as pd
import streamlit as st

from budget_me.streamlit_app.db import (
    get_cc_calculated_interest,
    get_cc_interest_from_transactions,
    get_expiring_promos,
    get_loans_with_interest,
    get_session,
    get_zero_percent_balance_schedule,
)

st.title("Debt Overview")

# Fetch all debt data
with get_session() as session:
    loans = get_loans_with_interest(session)
    credit_cards = get_cc_calculated_interest(session)
    cc_interest_history = get_cc_interest_from_transactions(session, months=2)
    zero_percent_schedule = get_zero_percent_balance_schedule(session)

# Check if we have any debt data
if not loans and not credit_cards:
    st.info("No debt data found. Add loans or credit cards to see debt overview.")
    st.stop()

# Calculate totals for summary metrics
total_debt = sum(loan["balance"] for loan in loans) + sum(
    card["balance"] for card in credit_cards
)
total_monthly_payment = sum(loan["monthly_payment"] for loan in loans)
total_monthly_interest = sum(loan["monthly_interest"] for loan in loans) + sum(
    card["calculated_interest"] for card in credit_cards
)
total_annual_interest = total_monthly_interest * 12

# Display summary metrics
col1, col2, col3, col4 = st.columns(4)
with col1:
    st.metric("Total Debt", f"${total_debt:,.2f}")
with col2:
    st.metric("Monthly Payments", f"${total_monthly_payment:,.2f}")
with col3:
    st.metric("Monthly Interest", f"${total_monthly_interest:,.2f}")
with col4:
    st.metric("Annual Interest", f"${total_annual_interest:,.2f}")

st.divider()

# DEBT BY CATEGORY section header
st.header("Debt by Category")

# --- MORTGAGE SECTION ---
mortgage_loans = [loan for loan in loans if loan["loan_type"] == "mortgage"]
if mortgage_loans:
    mortgage_total = sum(loan["balance"] for loan in mortgage_loans)
    mortgage_pct = (mortgage_total / total_debt * 100) if total_debt > 0 else 0

    with st.expander(
        f"**Mortgage** (${mortgage_total:,.2f} - {mortgage_pct:.1f}%)", expanded=True
    ):
        for loan in mortgage_loans:
            # Account name with mask
            account_display = (
                f"{loan['account_name']} (...{loan['mask']})"
                if loan["mask"]
                else loan["account_name"]
            )
            if loan["lender_name"]:
                account_display = (
                    f"{loan['lender_name']} (...{loan['mask']})"
                    if loan["mask"]
                    else loan["lender_name"]
                )

            st.markdown(f"**{account_display}**")

            # Details in columns
            detail_col1, detail_col2, detail_col3 = st.columns(3)
            with detail_col1:
                st.write(f"Balance: **${loan['balance']:,.2f}**")
                st.write(f"Rate: **{loan['interest_rate']:.2f}%**")
            with detail_col2:
                st.write(f"Payment: **${loan['monthly_payment']:,.2f}/mo**")
                st.write(
                    f"Monthly Interest: **${loan['monthly_interest']:,.2f}** (calculated)"
                )
            with detail_col3:
                if loan["maturity_date"]:
                    st.write(f"Maturity: **{loan['maturity_date'].strftime('%b %Y')}**")

            st.divider()

# --- AUTO LOAN SECTION ---
auto_loans = [loan for loan in loans if loan["loan_type"] == "auto"]
if auto_loans:
    auto_total = sum(loan["balance"] for loan in auto_loans)
    auto_pct = (auto_total / total_debt * 100) if total_debt > 0 else 0

    with st.expander(
        f"**Auto Loan** (${auto_total:,.2f} - {auto_pct:.1f}%)", expanded=True
    ):
        for loan in auto_loans:
            # Account name with mask and collateral
            account_display = (
                f"{loan['account_name']} (...{loan['mask']})"
                if loan["mask"]
                else loan["account_name"]
            )
            if loan["lender_name"]:
                account_display = (
                    f"{loan['lender_name']} (...{loan['mask']})"
                    if loan["mask"]
                    else loan["lender_name"]
                )

            if loan["collateral_description"]:
                account_display += f" - {loan['collateral_description']}"

            st.markdown(f"**{account_display}**")

            # Details in columns
            detail_col1, detail_col2, detail_col3 = st.columns(3)
            with detail_col1:
                st.write(f"Balance: **${loan['balance']:,.2f}**")
                st.write(f"Rate: **{loan['interest_rate']:.2f}%**")
            with detail_col2:
                st.write(f"Payment: **${loan['monthly_payment']:,.2f}/mo**")
                st.write(
                    f"Monthly Interest: **${loan['monthly_interest']:,.2f}** (calculated)"
                )
            with detail_col3:
                if loan["maturity_date"]:
                    st.write(f"Maturity: **{loan['maturity_date'].strftime('%b %Y')}**")

            st.divider()

# --- CREDIT CARDS SECTION ---
if credit_cards:
    cc_total = sum(card["balance"] for card in credit_cards)
    cc_pct = (cc_total / total_debt * 100) if total_debt > 0 else 0

    with st.expander(
        f"**Credit Cards** (${cc_total:,.2f} - {cc_pct:.1f}%)", expanded=True
    ):
        # Summary: 0% vs Interest-Bearing split
        promo_cards = [
            c for c in credit_cards if c["payment_strategy"] == "promotional_paydown"
        ]
        pay_full_cards = [
            c for c in credit_cards if c["payment_strategy"] == "pay_in_full"
        ]

        # Calculate 0% promotional balances (need to query APRs separately)
        # For now, show strategy-based summary
        st.markdown("**Summary:**")
        summary_col1, summary_col2 = st.columns(2)
        with summary_col1:
            promo_total = sum(c["balance"] for c in promo_cards)
            st.write(f"Promotional Paydown: **${promo_total:,.2f}**")
        with summary_col2:
            pay_full_total = sum(c["balance"] for c in pay_full_cards)
            st.write(f"Pay in Full: **${pay_full_total:,.2f}**")

        st.divider()

        # Credit card table
        st.markdown("**Credit Cards:**")
        cc_df = pd.DataFrame(credit_cards)

        # Format for display
        cc_display = cc_df[
            [
                "account_name",
                "mask",
                "balance",
                "payment_strategy",
                "calculated_interest",
            ]
        ].copy()
        cc_display["account"] = cc_display.apply(
            lambda row: f"{row['account_name']} (...{row['mask']})"
            if row["mask"]
            else row["account_name"],
            axis=1,
        )
        cc_display["strategy"] = (
            cc_display["payment_strategy"].str.replace("_", " ").str.title()
        )

        cc_final = cc_display[
            ["account", "balance", "strategy", "calculated_interest"]
        ].copy()
        cc_final.columns = ["Card", "Balance", "Strategy", "Monthly Interest"]

        st.dataframe(
            cc_final,
            column_config={
                "Balance": st.column_config.NumberColumn(format="$%.2f"),
                "Monthly Interest": st.column_config.NumberColumn(format="$%.2f"),
            },
            hide_index=True,
            use_container_width=True,
        )

        if zero_percent_schedule:
            st.markdown("**0% Balance Payoff Schedule:**")
            today = date.today()
            schedule_rows = []
            for promo in zero_percent_schedule:
                end_date = promo["promo_rate_end_date"]
                if end_date:
                    days_remaining = (end_date - today).days
                    timing = (
                        f"Expired {abs(days_remaining)} days ago"
                        if days_remaining < 0
                        else "Today"
                        if days_remaining == 0
                        else f"{days_remaining} days"
                    )
                    pay_by = end_date.strftime("%b %-d, %Y")
                else:
                    timing = "Date not recorded"
                    pay_by = "Not recorded"

                card_name = promo["account_name"]
                if promo["mask"]:
                    card_name = f"{card_name} (...{promo['mask']})"

                schedule_rows.append(
                    {
                        "Card": card_name,
                        "0% Balance": promo["balance"],
                        "Pay By (0% Ends)": pay_by,
                        "Time Remaining": timing,
                    }
                )

            schedule_df = pd.DataFrame(schedule_rows)
            st.dataframe(
                schedule_df,
                column_config={
                    "0% Balance": st.column_config.NumberColumn(format="$%.2f"),
                },
                hide_index=True,
                use_container_width=True,
            )
            st.caption(
                "Pay-by dates are the recorded promotional APR end dates; "
                "pay before these dates to avoid the post-promotion rate."
            )

st.divider()

# --- INTEREST ANALYSIS SECTION ---
st.header("Interest Analysis")

# Calculate interest breakdown by category
mortgage_interest = sum(
    loan["monthly_interest"] for loan in loans if loan["loan_type"] == "mortgage"
)
auto_interest = sum(
    loan["monthly_interest"] for loan in loans if loan["loan_type"] == "auto"
)
cc_interest = sum(card["calculated_interest"] for card in credit_cards)

# Calculate percentages
total_interest = mortgage_interest + auto_interest + cc_interest
if total_interest > 0:
    mortgage_pct = mortgage_interest / total_interest * 100
    auto_pct = auto_interest / total_interest * 100
    cc_pct = cc_interest / total_interest * 100

    st.markdown("**Monthly Breakdown:**")

    # Visual breakdown with progress bars
    if mortgage_interest > 0:
        st.markdown(f"Mortgage: **${mortgage_interest:,.2f}** ({mortgage_pct:.0f}%)")
        st.progress(mortgage_pct / 100)

    if auto_interest > 0:
        st.markdown(f"Auto: **${auto_interest:,.2f}** ({auto_pct:.0f}%)")
        st.progress(auto_pct / 100)

    if cc_interest > 0:
        st.markdown(f"Credit Cards: **${cc_interest:,.2f}** ({cc_pct:.0f}%)")
        st.progress(cc_pct / 100)

    st.divider()

# Credit Card Interest - Actual vs Calculated
if cc_interest_history and credit_cards:
    st.markdown("**Credit Card Interest - Actual vs Calculated (last 2 months):**")

    # Build comparison table
    comparison_rows = []
    for month in sorted(cc_interest_history.keys(), reverse=True):
        # Sum actual interest for all cards in this month
        actual_total = sum(cc_interest_history[month].values())

        # Use current calculated interest (approximation - would be same for recent months)
        calculated_total = sum(card["calculated_interest"] for card in credit_cards)

        difference = actual_total - calculated_total

        comparison_rows.append(
            {
                "Month": month,
                "Calculated": calculated_total,
                "Actual": actual_total,
                "Difference": difference,
            }
        )

    if comparison_rows:
        comparison_df = pd.DataFrame(comparison_rows)

        st.dataframe(
            comparison_df,
            column_config={
                "Month": st.column_config.TextColumn("Month"),
                "Calculated": st.column_config.NumberColumn(format="$%.2f"),
                "Actual": st.column_config.NumberColumn(
                    "Actual (Transactions)", format="$%.2f"
                ),
                "Difference": st.column_config.NumberColumn(format="$%.2f"),
            },
            hide_index=True,
            use_container_width=True,
        )

        st.caption(
            "Actual interest may differ due to cash advances, timing differences, "
            "or balances carried on pay-in-full cards."
        )

# Check for expiring promo rates
# Query for promotional cards with expiring rates
with get_session() as session:
    expiring_promos = get_expiring_promos(session, within_days=60)

if expiring_promos:
    # Count promos expiring soon (within 30 days) vs later
    expiring_soon = [p for p in expiring_promos if p["days_until_expiration"] <= 30]
    expiring_later = [p for p in expiring_promos if p["days_until_expiration"] > 30]

    if expiring_soon:
        promo_count = len(expiring_soon)
        st.warning(
            f"⚠️ {promo_count} promotional APR rate(s) expiring within 30 days! "
            f"[View details →](promo_cards)"
        )
    elif expiring_later:
        promo_count = len(expiring_later)
        st.info(
            f"💡 {promo_count} promotional APR rate(s) expiring within 60 days. "
            f"[View details →](promo_cards)"
        )
