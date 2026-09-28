"""Streamlit page for comprehensive credit card management."""

from datetime import date

import pandas as pd
import streamlit as st

from budget_me.streamlit_app.db import (
    get_all_credit_cards_with_full_details,
    get_depository_accounts,
    get_session,
    update_account_display_name,
    update_account_excluded_status,
    update_account_payment_strategy,
    update_paying_account,
)

st.title("Credit Cards")

# Fetch all credit cards with full details
with get_session() as session:
    cards = get_all_credit_cards_with_full_details(session)
    checking_accounts = get_depository_accounts(session, include_excluded=False)

if not cards:
    st.info("No credit cards found. Use the Link Account page to connect your bank.")
    if st.button("Go to Link Account"):
        st.switch_page("pages/link_account.py")
    st.stop()

# Calculate overview metrics
total_balance = sum(card["balance_current"] for card in cards)
promo_cards_count = sum(
    1 for card in cards if card["payment_strategy"] == "promotional_paydown"
)

# Calculate monthly obligations based on strategy
monthly_obligations = 0.0
for card in cards:
    if card["payment_strategy"] == "pay_in_full":
        # For pay_in_full, use current balance (simplified - would use last_statement_balance in production)
        monthly_obligations += card["balance_current"]
    elif (
        card["payment_strategy"] == "promotional_paydown"
        and card["fixed_payment_amount"]
    ):
        monthly_obligations += card["fixed_payment_amount"]

# Overview metrics row
col1, col2, col3 = st.columns(3)
with col1:
    st.metric("Total Balance", f"${total_balance:,.2f}")
with col2:
    st.metric("Monthly Obligations", f"${monthly_obligations:,.2f}")
with col3:
    st.metric("Promotional Cards", promo_cards_count)

st.divider()

# Check for expiring/expired promotional rates
expiring_aprs = []
expired_aprs = []
today = date.today()

for card in cards:
    for apr in card["aprs"]:
        if apr["promo_rate_end_date"]:
            days_until = (apr["promo_rate_end_date"] - today).days
            apr_with_card = {
                **apr,
                "card_name": card["display_name"] or card["name"],
                "card_mask": card["mask"],
                "days_until_expiration": days_until,
            }
            if days_until < 0:
                expired_aprs.append(apr_with_card)
            elif days_until <= 30:
                expiring_aprs.append(apr_with_card)

# Alert banners
if expired_aprs:
    total_expired_balance = sum(apr["balance"] for apr in expired_aprs)
    st.error(
        f"Warning: {len(expired_aprs)} promotional rate(s) expired "
        f"with ${total_expired_balance:,.2f} remaining balance. "
        f"These balances may now be accruing interest at standard rates."
    )

if expiring_aprs:
    total_expiring_balance = sum(apr["balance"] for apr in expiring_aprs)
    st.warning(
        f"Notice: {len(expiring_aprs)} promotional rate(s) expiring within 30 days "
        f"(${total_expiring_balance:,.2f} total). "
        f"Plan your paydown strategy."
    )

st.write(f"**{len(cards)} credit cards connected**")
st.divider()

# Build dropdown options for paying accounts
checking_options = {None: "-- Not Set --"}
for acc in checking_accounts:
    checking_options[acc["account_id"]] = acc["display"]

# Display each credit card with expandable settings
for card in cards:
    card_name = card["display_name"] or card["name"]
    card_label = f"{card_name} (...{card['mask']})" if card["mask"] else card_name

    # Summary row with key info
    col1, col2, col3, col4 = st.columns([3, 2, 2, 2])
    with col1:
        st.write(f"**{card_label}**")
    with col2:
        st.write(f"${card['balance_current']:,.2f}")
    with col3:
        strategy_display = (
            "Pay in Full"
            if card["payment_strategy"] == "pay_in_full"
            else f"Promo (${card['fixed_payment_amount']:,.2f})"
            if card["fixed_payment_amount"]
            else "Promotional"
        )
        st.write(strategy_display)
    with col4:
        paying_display = card.get("paying_account_display") or "Not Set"
        st.write(paying_display)

    # Expandable section for editing settings
    with st.expander("Settings", expanded=False):
        # Initialize session state for this card's edit mode
        edit_key = f"edit_{card['account_id']}"
        if edit_key not in st.session_state:
            st.session_state[edit_key] = False

        # Edit/Cancel button
        col1, col2 = st.columns([1, 5])
        with col1:
            if not st.session_state[edit_key]:
                if st.button("Edit", key=f"edit_btn_{card['account_id']}"):
                    st.session_state[edit_key] = True
                    st.rerun()
            else:
                if st.button("Cancel", key=f"cancel_btn_{card['account_id']}"):
                    st.session_state[edit_key] = False
                    st.rerun()

        if st.session_state[edit_key]:
            # Editable fields
            st.subheader("Account Settings")

            # Display name
            new_display_name = st.text_input(
                "Display Name",
                value=card["display_name"] or "",
                help="Custom name for this card (optional)",
                key=f"display_name_{card['account_id']}",
            )

            # Payment strategy
            strategy_options = ["pay_in_full", "promotional_paydown"]
            strategy_labels = ["Pay in Full", "Promotional Paydown"]
            current_strategy_index = strategy_options.index(card["payment_strategy"])

            new_strategy = st.selectbox(
                "Payment Strategy",
                options=strategy_options,
                index=current_strategy_index,
                format_func=lambda x: strategy_labels[strategy_options.index(x)],
                key=f"strategy_{card['account_id']}",
            )

            # Fixed payment amount (shown if promotional strategy)
            new_fixed_amount = None
            if new_strategy == "promotional_paydown":
                new_fixed_amount = st.number_input(
                    "Fixed Payment Amount",
                    min_value=0.0,
                    value=float(card["fixed_payment_amount"])
                    if card["fixed_payment_amount"]
                    else 0.0,
                    step=10.0,
                    format="%.2f",
                    key=f"fixed_amount_{card['account_id']}",
                )

            # Paying account
            current_paying_index = (
                list(checking_options.keys()).index(card["paying_account_id"])
                if card["paying_account_id"] in checking_options
                else 0
            )
            new_paying_account = st.selectbox(
                "Paying Account",
                options=list(checking_options.keys()),
                index=current_paying_index,
                format_func=lambda x: checking_options[x],
                key=f"paying_{card['account_id']}",
            )

            # Excluded status
            new_excluded = st.checkbox(
                "Exclude from snapshots and calculations",
                value=card["is_excluded"],
                key=f"excluded_{card['account_id']}",
            )

            # Save button
            if st.button(
                "Save Changes", key=f"save_{card['account_id']}", type="primary"
            ):
                changes_made = False

                with get_session() as session:
                    # Update display name if changed
                    if new_display_name != (card["display_name"] or ""):
                        update_account_display_name(
                            session,
                            card["account_id"],
                            new_display_name.strip() or None,
                        )
                        changes_made = True

                    # Update payment strategy if changed
                    if new_strategy != card["payment_strategy"] or (
                        new_strategy == "promotional_paydown"
                        and new_fixed_amount != card["fixed_payment_amount"]
                    ):
                        update_account_payment_strategy(
                            session,
                            card["account_id"],
                            new_strategy,
                            new_fixed_amount
                            if new_strategy == "promotional_paydown"
                            else None,
                        )
                        changes_made = True

                    # Update paying account if changed
                    if new_paying_account != card["paying_account_id"]:
                        update_paying_account(
                            session,
                            card["account_id"],
                            new_paying_account,
                        )
                        changes_made = True

                    # Update excluded status if changed
                    if new_excluded != card["is_excluded"]:
                        update_account_excluded_status(
                            session,
                            card["account_id"],
                            new_excluded,
                        )
                        changes_made = True

                if changes_made:
                    st.success(f"Saved changes for {card_name}")
                    st.session_state[edit_key] = False
                    st.rerun()
                else:
                    st.info("No changes to save")
        else:
            # Read-only view
            st.write(
                f"**Display Name:** {card['display_name'] or '(using Plaid name)'}"
            )
            st.write(f"**Strategy:** {strategy_display}")
            if (
                card["payment_strategy"] == "promotional_paydown"
                and card["fixed_payment_amount"]
            ):
                st.write(f"**Fixed Payment:** ${card['fixed_payment_amount']:,.2f}")
            st.write(f"**Paying Account:** {paying_display}")
            st.write(f"**Excluded:** {'Yes' if card['is_excluded'] else 'No'}")

        # APR Breakdown (shown for all cards with APR data)
        if card["aprs"]:
            st.subheader("APR Breakdown")

            apr_data = []
            for apr in card["aprs"]:
                # Determine status based on expiration
                status = "N/A"
                if apr["promo_rate_end_date"]:
                    days_until = (apr["promo_rate_end_date"] - today).days
                    if days_until < 0:
                        status = "Expired"
                    elif days_until <= 30:
                        status = "Expiring Soon"
                    else:
                        status = "Active"

                apr_data.append(
                    {
                        "Balance": apr["balance"],
                        "APR": apr["apr_percentage"],
                        "Type": apr["apr_type"].replace("_", " ").title(),
                        "Expires": apr["promo_rate_end_date"].strftime("%m/%d/%Y")
                        if apr["promo_rate_end_date"]
                        else "N/A",
                        "Offer ID": apr["promo_offer_id"] or "N/A",
                        "Status": status,
                        "Source": apr["source"].title(),
                    }
                )

            df = pd.DataFrame(apr_data)

            # Apply color styling to Status column
            def color_status(val):
                if val == "Expired":
                    return "background-color: #ffcccc"  # Light red
                elif val == "Expiring Soon":
                    return "background-color: #fff4cc"  # Light yellow
                elif val == "Active":
                    return "background-color: #ccffcc"  # Light green
                return ""

            styled_df = df.style.map(color_status, subset=["Status"])

            st.dataframe(
                styled_df,
                column_config={
                    "Balance": st.column_config.NumberColumn(format="$%.2f"),
                    "APR": st.column_config.NumberColumn(format="%.2f%%"),
                },
                hide_index=True,
                use_container_width=True,
            )

    st.divider()
