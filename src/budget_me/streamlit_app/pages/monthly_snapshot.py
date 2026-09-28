"""Monthly Financial Snapshot - Budget overview dashboard."""

from datetime import datetime
from decimal import Decimal

import streamlit as st

from budget_me.snapshots.service import build_close_preview, get_read_only_session
from budget_me.streamlit_app.db import (
    add_one_time_item,
    calculate_snapshot_totals,
    close_snapshot,
    get_available_months,
    get_closing_balance,
    get_depository_accounts,
    get_or_create_snapshot,
    get_session,
    get_snapshot_credit_cards,
    get_snapshot_line_items,
    get_starting_balance,
    skip_snapshot_line_item,
    update_snapshot_credit_card,
    update_snapshot_line_item,
    update_snapshot_notes,
)

# Compact CSS to reduce padding and spacing
st.markdown(
    """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    div[data-testid="stMetric"] { padding: 0.3rem 0; }
    div[data-testid="stMetric"] label { font-size: 0.8rem; }
    div[data-testid="stMetric"] > div { font-size: 1.2rem; }
    .stExpander { margin-bottom: 0.25rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1.1rem !important; margin: 0.5rem 0 0.25rem 0 !important; }
    h3 { font-size: 0.95rem !important; margin: 0.25rem 0 !important; }
    .row-widget { margin-bottom: 0 !important; }
    hr { margin: 0.5rem 0 !important; }
</style>
""",
    unsafe_allow_html=True,
)


def render_account_selector(session) -> str:
    """Render account selector and return selected account_id string."""
    # Get only non-excluded depository accounts
    accounts = get_depository_accounts(session, include_excluded=False)

    if not accounts:
        st.error("No depository accounts found. Please connect an account first.")
        st.stop()

    # Sort accounts alphabetically descending (Z-A) by display name
    accounts = sorted(
        accounts,
        key=lambda a: (a.get("display_name") or a["name"]).lower(),
        reverse=True,
    )

    # Build display options
    options = []
    for account in accounts:
        display_name = account.get("display_name") or account["name"]
        options.append(display_name)

    values = [account["account_id"] for account in accounts]

    # Use session state to preserve selection
    if "selected_account_index" not in st.session_state:
        st.session_state.selected_account_index = 0

    selected_index = st.selectbox(
        "Account",
        range(len(options)),
        format_func=lambda i: options[i],
        index=st.session_state.selected_account_index,
        key="account_selector",
    )

    # Update session state
    st.session_state.selected_account_index = selected_index

    return values[selected_index]


def render_month_selector(session, account_id: str) -> str:
    """Render month selector and return selected year_month string."""
    # Get available months from snapshots for this account
    available_months = get_available_months(session, account_id)

    # Extract year_month and display_label
    options = [month["display_label"] for month in available_months]
    values = [month["year_month"] for month in available_months]

    # Find oldest open month (last open in the desc-sorted list)
    # Months are sorted newest-first, so iterate to find last open
    default_index = 0
    for i, month in enumerate(available_months):
        status = month["status"]
        status_value = status.value if hasattr(status, "value") else str(status)
        if status_value == "open":
            default_index = i  # Keep updating to get the oldest (last) open

    col1, col2 = st.columns([1, 3])
    with col1:
        selected_index = st.selectbox(
            "Month",
            range(len(options)),
            format_func=lambda i: options[i],
            index=default_index,
            label_visibility="collapsed",
        )
    return values[selected_index]


def render_balance_display(session, account_id: str, year_month: str):
    """Display starting and closing balances with frozen/estimate indicators."""
    col1, col2 = st.columns(2)

    with col1:
        starting, is_frozen = get_starting_balance(session, account_id, year_month)
        if starting is None:
            st.markdown("**Starting Balance:** *Not available*")
        elif is_frozen:
            st.metric(
                "Starting Balance",
                f"${starting:,.2f}",
                help="Final - from closed month",
            )
        else:
            st.markdown(
                f"**Starting Balance:** ${starting:,.2f} *(estimate)*",
                help="Estimated from balance snapshot",
            )

    with col2:
        closing, is_frozen = get_closing_balance(session, account_id, year_month)
        if closing is None:
            st.markdown("**Closing Balance:** *Not available*")
        elif is_frozen:
            st.metric(
                "Closing Balance", f"${closing:,.2f}", help="Final - month closed"
            )
        else:
            st.markdown(
                f"**Closing Balance:** ${closing:,.2f} *(estimate)*",
                help="Calculated from starting balance + net",
            )

    st.markdown("---")


def render_overview_metrics(totals: dict, reconciliation_complete: bool = False):
    """Render overview with two-column Money In / Money Out layout."""
    income = Decimal(str(totals.get("income_total", 0)))
    expenses = Decimal(str(totals.get("expense_total", 0)))
    transfer_in = Decimal(str(totals.get("transfer_in_total", 0)))
    transfer_out = Decimal(str(totals.get("transfer_out_total", 0)))
    reimbursement_in = Decimal(str(totals.get("reimbursement_in_total", 0)))
    reimbursement_out = Decimal(str(totals.get("reimbursement_out_total", 0)))
    credit_cards = Decimal(str(totals.get("credit_card_total", 0)))
    net = Decimal(str(totals.get("net", 0)))

    # Calculate totals
    total_in = income + transfer_in + reimbursement_in
    total_out = expenses + transfer_out + reimbursement_out + credit_cards
    expense_label = "Expenses" if reconciliation_complete else "Fixed Expenses"
    card_payment_label = (
        "Card Payments" if reconciliation_complete else "Card Payments (planned)"
    )

    # Determine colors based on financial health
    if net >= 0:
        net_color = "#28a745"  # Green
        net_bg = "rgba(40, 167, 69, 0.1)"
    else:
        net_color = "#dc3545"  # Red
        net_bg = "rgba(220, 53, 69, 0.1)"

    # Overview container with two-column layout
    st.markdown(
        f"""
    <div style="background: rgba(128,128,128,0.1);
                border: 1px solid rgba(128,128,128,0.2);
                border-radius: 12px;
                padding: 1.25rem;
                margin-bottom: 1rem;">
        <div style="display: flex; gap: 2rem;">
            <!-- Money In Column -->
            <div style="flex: 1; padding-right: 1rem; border-right: 1px solid rgba(128,128,128,0.2);">
                <div style="color: #2e7d32; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.75rem;">
                    Money In
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #888;">Income</span>
                    <span style="color: #2e7d32; font-weight: 500;">${income:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #888;">Transfers In</span>
                    <span style="color: #2e7d32; font-weight: 500;">${transfer_in:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.75rem;">
                    <span style="color: #888;">Reimbursements In</span>
                    <span style="color: #2e7d32; font-weight: 500;">${reimbursement_in:,.2f}</span>
                </div>
                <div style="border-top: 1px solid rgba(128,128,128,0.3); padding-top: 0.5rem; display: flex; justify-content: space-between;">
                    <span style="font-weight: 600;">Total In</span>
                    <span style="color: #2e7d32; font-weight: 700; font-size: 1.1rem;">${total_in:,.2f}</span>
                </div>
            </div>
            <!-- Money Out Column -->
            <div style="flex: 1; padding-left: 1rem;">
                <div style="color: #dc3545; font-size: 0.85rem; font-weight: 600; text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 0.75rem;">
                    Money Out
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #888;">{expense_label}</span>
                    <span style="color: #1565c0; font-weight: 500;">${expenses:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #888;">Transfers Out</span>
                    <span style="color: #dc3545; font-weight: 500;">${transfer_out:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.5rem;">
                    <span style="color: #888;">Reimbursements Out</span>
                    <span style="color: #dc3545; font-weight: 500;">${reimbursement_out:,.2f}</span>
                </div>
                <div style="display: flex; justify-content: space-between; margin-bottom: 0.75rem;">
                    <span style="color: #888;">{card_payment_label}</span>
                    <span style="color: #dc3545; font-weight: 500;">${credit_cards:,.2f}</span>
                </div>
                <div style="border-top: 1px solid rgba(128,128,128,0.3); padding-top: 0.5rem; display: flex; justify-content: space-between;">
                    <span style="font-weight: 600;">Total Out</span>
                    <span style="color: #dc3545; font-weight: 700; font-size: 1.1rem;">${total_out:,.2f}</span>
                </div>
            </div>
        </div>
        <!-- Net Section -->
        <div style="margin-top: 1rem; padding-top: 1rem; border-top: 2px solid rgba(128,128,128,0.3);
                    background: {net_bg}; border-radius: 8px; padding: 0.75rem; margin-top: 1rem;">
            <div style="display: flex; justify-content: center; align-items: center; gap: 1rem;">
                <span style="color: #888; font-size: 0.9rem;">Total In - Total Out =</span>
                <span style="font-size: 1.5rem; font-weight: 700; color: {net_color};">NET: ${net:,.2f}</span>
            </div>
        </div>
    </div>
    """,
        unsafe_allow_html=True,
    )


def render_income_section(
    session, year_month: str, account_id: str, snapshot_status: str
):
    """Render compact Income section."""
    is_closed = snapshot_status == "closed"

    # Get snapshot line items instead of anticipated items
    income_items = get_snapshot_line_items(
        session, year_month, account_id, item_type="income"
    )

    if income_items:
        total = Decimal("0")
        # Table header with conditional columns
        if is_closed:
            cols = st.columns([4, 2, 2])
        else:
            cols = st.columns([4, 2, 1, 1, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Amount**")

        for item in income_items:
            item_id = item["id"]
            name = item["name"]
            amount = Decimal(str(item["amount"]))
            is_skipped = item.get("skipped", False)
            is_one_time = item.get("is_one_time", False)

            # Skip items don't count toward total
            if not is_skipped:
                total += amount

            # Display name with indicators
            display_name = name
            if is_one_time:
                display_name += " (one-time)"
            if is_skipped:
                display_name = f"~~{display_name}~~"

            if is_closed:
                cols = st.columns([4, 2, 2])
                cols[0].markdown(display_name)
                cols[1].write(f"${amount:,.2f}")
            else:
                cols = st.columns([4, 2, 1, 1, 1])
                cols[0].markdown(display_name)
                cols[1].write(f"${amount:,.2f}")

                # Skip toggle
                skip_label = "⚪" if is_skipped else "✓"
                if cols[2].button(skip_label, key=f"si_{item_id}", help="Skip"):
                    skip_snapshot_line_item(session, item_id, not is_skipped)
                    session.commit()
                    st.rerun()

                # Edit and delete buttons for open snapshots only
                if cols[3].button("✏️", key=f"ei_{item_id}", help="Edit"):
                    st.session_state[f"editing_income_{item_id}"] = True
                    st.rerun()
                if cols[4].button("🗑️", key=f"di_{item_id}", help="Delete"):
                    skip_snapshot_line_item(session, item_id, True)
                    session.commit()
                    st.rerun()

            if not is_closed and st.session_state.get(
                f"editing_income_{item_id}", False
            ):
                with st.form(key=f"ef_i_{item_id}"):
                    c1, c2, c3 = st.columns([3, 2, 2])
                    new_name = c1.text_input(
                        "Name", value=name, label_visibility="collapsed"
                    )
                    new_amount = c2.number_input(
                        "Amt",
                        value=float(amount),
                        min_value=0.0,
                        label_visibility="collapsed",
                    )
                    if c3.form_submit_button("Save"):
                        update_snapshot_line_item(
                            session, item_id, name=new_name, amount=new_amount
                        )
                        session.commit()
                        st.session_state[f"editing_income_{item_id}"] = False
                        st.rerun()

        st.markdown(f"**Total: ${total:,.2f}**")
    else:
        st.caption("No income items.")

    # Add form only for open snapshots
    if not is_closed:
        with st.expander("➕ Add Income"):
            with st.form(key="add_income_form"):
                c1, c2 = st.columns([3, 2])
                new_name = c1.text_input(
                    "Name", label_visibility="collapsed", placeholder="Name"
                )
                new_amount = c2.number_input(
                    "Amount", min_value=0.0, step=0.01, label_visibility="collapsed"
                )
                if st.form_submit_button("Add"):
                    if new_name and new_amount > 0:
                        add_one_time_item(
                            session,
                            year_month,
                            account_id,
                            "income",
                            new_name,
                            new_amount,
                            None,
                        )
                        session.commit()
                        st.rerun()


def render_expenses_section(
    session, year_month: str, account_id: str, snapshot_status: str
):
    """Render compact Expenses section as flat table."""
    is_closed = snapshot_status == "closed"

    # Get snapshot line items instead of anticipated items
    expense_items = get_snapshot_line_items(
        session, year_month, account_id, item_type="expense"
    )

    if expense_items:
        total = Decimal("0")

        # Table header with conditional columns
        if is_closed:
            cols = st.columns([3, 2, 2, 2])
        else:
            cols = st.columns([3, 2, 2, 1, 1, 1])
        cols[0].markdown("**Item**")
        cols[1].markdown("**Category**")
        cols[2].markdown("**Amount**")

        # Sort by category, then name (handle None category values)
        sorted_items = sorted(
            expense_items, key=lambda x: (x.get("category") or "ZZZ", x["name"])
        )

        # Subscriptions in collapsible
        subs = [
            i
            for i in sorted_items
            if (i.get("category") or "").lower() == "subscriptions"
        ]
        non_subs = [
            i
            for i in sorted_items
            if (i.get("category") or "").lower() != "subscriptions"
        ]

        for item in non_subs:
            total += render_expense_row(session, item, is_closed, show_category=True)

        # Subscriptions collapsed
        if subs:
            sub_total = sum(
                Decimal(str(i["amount"])) for i in subs if not i.get("skipped", False)
            )
            total += sub_total
            with st.expander(f"📺 Subscriptions ({len(subs)}) — ${sub_total:,.2f}"):
                for item in subs:
                    render_expense_row(session, item, is_closed, show_category=False)

        st.markdown(f"**Total: ${total:,.2f}**")
    else:
        st.caption("No expense items.")

    # Add form only for open snapshots
    if not is_closed:
        with st.expander("➕ Add Expense"):
            with st.form(key="add_expense_form"):
                c1, c2, c3 = st.columns([3, 2, 2])
                new_name = c1.text_input(
                    "Name", label_visibility="collapsed", placeholder="Name"
                )
                new_category = c2.selectbox(
                    "Cat",
                    [
                        "Housing",
                        "Utilities",
                        "Auto",
                        "Cellular",
                        "Childcare",
                        "Education",
                        "Home",
                        "Insurance",
                        "Fitness",
                        "Subscriptions",
                        "Other",
                    ],
                    label_visibility="collapsed",
                )
                new_amount = c3.number_input(
                    "Amount", min_value=0.0, step=0.01, label_visibility="collapsed"
                )
                if st.form_submit_button("Add"):
                    if new_name and new_amount > 0:
                        add_one_time_item(
                            session,
                            year_month,
                            account_id,
                            "expense",
                            new_name,
                            new_amount,
                            new_category,
                        )
                        session.commit()
                        st.rerun()


def render_expense_row(
    session, item: dict, is_closed: bool, show_category: bool = True
) -> Decimal:
    """Render a compact expense row. Returns the amount for totaling."""
    item_id = item["id"]
    name = item["name"]
    amount = Decimal(str(item["amount"]))
    category = item.get("category", "Other")
    is_skipped = item.get("skipped", False)
    is_one_time = item.get("is_one_time", False)

    # Display name with indicators
    display_name = name
    if is_one_time:
        display_name += " (one-time)"
    if is_skipped:
        display_name = f"~~{display_name}~~"

    if is_closed:
        cols = st.columns([3, 2, 2, 2])
        cols[0].markdown(display_name)
        if show_category:
            cols[1].caption(category)
        cols[2].write(f"${amount:,.2f}")
    else:
        cols = st.columns([3, 2, 2, 1, 1, 1])
        cols[0].markdown(display_name)
        if show_category:
            cols[1].caption(category)
        cols[2].write(f"${amount:,.2f}")

        # Skip toggle
        skip_label = "⚪" if is_skipped else "✓"
        if cols[3].button(skip_label, key=f"se_{item_id}", help="Skip"):
            skip_snapshot_line_item(session, item_id, not is_skipped)
            session.commit()
            st.rerun()

        # Edit and delete buttons for open snapshots only
        if cols[4].button("✏️", key=f"ee_{item_id}", help="Edit"):
            st.session_state[f"editing_expense_{item_id}"] = True
            st.rerun()
        if cols[5].button("🗑️", key=f"de_{item_id}", help="Delete"):
            skip_snapshot_line_item(session, item_id, True)
            session.commit()
            st.rerun()

    if not is_closed and st.session_state.get(f"editing_expense_{item_id}", False):
        cats = [
            "Housing",
            "Utilities",
            "Auto",
            "Cellular",
            "Childcare",
            "Education",
            "Home",
            "Insurance",
            "Fitness",
            "Subscriptions",
            "Other",
        ]
        with st.form(key=f"ef_e_{item_id}"):
            c1, c2, c3, c4 = st.columns([3, 2, 2, 1])
            new_name = c1.text_input("Name", value=name, label_visibility="collapsed")
            new_cat = c2.selectbox(
                "Cat",
                cats,
                index=cats.index(category) if category in cats else 10,
                label_visibility="collapsed",
            )
            new_amount = c3.number_input(
                "Amt", value=float(amount), min_value=0.0, label_visibility="collapsed"
            )
            if c4.form_submit_button("💾"):
                update_snapshot_line_item(
                    session, item_id, name=new_name, amount=new_amount, category=new_cat
                )
                session.commit()
                st.session_state[f"editing_expense_{item_id}"] = False
                st.rerun()

    # Return amount only if not skipped
    return Decimal("0") if is_skipped else amount


def render_transfers_section(
    session, year_month: str, account_id: str, snapshot_status: str
):
    """Render Transfers section showing both transfers in and out."""
    is_closed = snapshot_status == "closed"

    # Get transfer line items
    transfer_in_items = get_snapshot_line_items(
        session, year_month, account_id, item_type="transfer_in"
    )
    transfer_out_items = get_snapshot_line_items(
        session, year_month, account_id, item_type="transfer_out"
    )

    if not transfer_in_items and not transfer_out_items:
        st.caption("No transfers recorded.")
        return

    # Transfers In
    if transfer_in_items:
        st.markdown("**Transfers In**")
        total_in = Decimal("0")

        # Table header
        if is_closed:
            cols = st.columns([3, 2, 2])
        else:
            cols = st.columns([3, 2, 2, 1, 1])
        cols[0].markdown("**Source**")
        cols[1].markdown("**Category**")
        cols[2].markdown("**Amount**")

        for item in transfer_in_items:
            if not item.get("skipped", False):
                amount = Decimal(str(item["amount"]))
                total_in += amount

                if is_closed:
                    cols = st.columns([3, 2, 2])
                else:
                    cols = st.columns([3, 2, 2, 1, 1])

                cols[0].markdown(item["name"])
                cols[1].markdown(item.get("category", ""))
                cols[2].markdown(f"${amount:,.2f}")

                if not is_closed:
                    if cols[3].button("✏️", key=f"edit_transfer_in_{item['id']}"):
                        st.session_state[f"editing_transfer_in_{item['id']}"] = True
                    if cols[4].button("❌", key=f"skip_transfer_in_{item['id']}"):
                        skip_snapshot_line_item(session, item["id"], skipped=True)
                        session.commit()
                        st.rerun()

        st.markdown(f"**Subtotal In: ${total_in:,.2f}**")

    # Spacing
    if transfer_in_items and transfer_out_items:
        st.markdown("---")

    # Transfers Out
    if transfer_out_items:
        st.markdown("**Transfers Out**")
        total_out = Decimal("0")

        # Table header
        if is_closed:
            cols = st.columns([3, 2, 2])
        else:
            cols = st.columns([3, 2, 2, 1, 1])
        cols[0].markdown("**Destination**")
        cols[1].markdown("**Category**")
        cols[2].markdown("**Amount**")

        for item in transfer_out_items:
            if not item.get("skipped", False):
                amount = Decimal(str(item["amount"]))
                total_out += amount

                if is_closed:
                    cols = st.columns([3, 2, 2])
                else:
                    cols = st.columns([3, 2, 2, 1, 1])

                cols[0].markdown(item["name"])
                cols[1].markdown(item.get("category", ""))
                cols[2].markdown(f"${amount:,.2f}")

                if not is_closed:
                    if cols[3].button("✏️", key=f"edit_transfer_out_{item['id']}"):
                        st.session_state[f"editing_transfer_out_{item['id']}"] = True
                    if cols[4].button("❌", key=f"skip_transfer_out_{item['id']}"):
                        skip_snapshot_line_item(session, item["id"], skipped=True)
                        session.commit()
                        st.rerun()

        st.markdown(f"**Subtotal Out: ${total_out:,.2f}**")

    # Net transfers
    if transfer_in_items or transfer_out_items:
        net_transfers = sum(
            Decimal(str(i["amount"]))
            for i in transfer_in_items
            if not i.get("skipped", False)
        ) - sum(
            Decimal(str(i["amount"]))
            for i in transfer_out_items
            if not i.get("skipped", False)
        )
        st.markdown(f"**Net Transfers: ${net_transfers:,.2f}**")


def render_credit_cards_section(
    session,
    year_month: str,
    account_id: str,
    snapshot_status: str,
    reconciliation_complete: bool = False,
):
    """Render compact Credit Cards section as table."""
    is_closed = snapshot_status == "closed"

    # Get snapshot credit cards instead of live data
    credit_cards = get_snapshot_credit_cards(session, year_month, account_id)

    if not credit_cards:
        st.caption("No credit cards found.")
        return

    if reconciliation_complete:
        posted_cards = [
            card
            for card in credit_cards
            if Decimal(str(card.get("actual_payment_amount") or 0)) > 0
        ]
        posted_cards.sort(
            key=lambda card: Decimal(str(card.get("actual_payment_amount") or 0)),
            reverse=True,
        )
        if not posted_cards:
            st.caption("No posted card payments.")
            return

        cols = st.columns([4, 2, 2])
        cols[0].markdown("**Card**")
        cols[1].markdown("**Paid**")
        cols[2].markdown("**Paid On**")
        total_paid = Decimal("0")
        for card in posted_cards:
            card_name = card.get("display_name") or card.get("name", "Unknown")
            mask = card.get("mask", "")
            display_name = f"{card_name} ({mask})" if mask else card_name
            paid_amount = Decimal(str(card.get("actual_payment_amount") or 0))
            total_paid += paid_amount
            paid_date = card.get("actual_payment_date")
            paid_date_str = (
                paid_date.strftime("%m/%d")
                if hasattr(paid_date, "strftime")
                else str(paid_date)[:5]
                if paid_date
                else "—"
            )
            cols = st.columns([4, 2, 2])
            cols[0].write(display_name)
            cols[1].write(f"${paid_amount:,.2f}")
            cols[2].write(paid_date_str)

        st.metric("Posted card payments", f"${total_paid:,.2f}")
        return

    # Pre-calculate monthly expense for sorting using snapshot calculated_payment
    def calc_monthly_expense(card):
        return Decimal(str(card.get("calculated_payment", 0)))

    # Sort by amount due (highest first)
    credit_cards = sorted(credit_cards, key=calc_monthly_expense, reverse=True)

    total_planned = Decimal("0")
    total_paid = Decimal("0")
    out_of_month_full_payments = []

    # Table header with conditional columns
    if is_closed:
        cols = st.columns([3, 2, 2, 2, 2, 2, 2, 1])
    else:
        cols = st.columns([3, 2, 2, 2, 2, 2, 2, 1, 1])
    cols[0].markdown("**Card**")
    cols[1].markdown("**Planned**")
    cols[2].markdown("**Due Date**")
    cols[3].markdown("**Statement**")
    cols[4].markdown("**Paid**")
    cols[5].markdown("**Remaining**")
    cols[6].markdown("**Paid On**")
    cols[7].markdown("**Strat**")

    for card in credit_cards:
        card_name = card.get("display_name") or card.get("name", "Unknown")
        mask = card.get("mask", "")
        statement_balance = card.get("statement_balance")
        payment_strategy = card.get("payment_strategy", "pay_in_full")
        fixed_payment_amount = card.get("fixed_payment_amount")
        calculated_payment = card.get("calculated_payment", 0)
        actual_payment_amount = card.get("actual_payment_amount")
        actual_payment_date = card.get("actual_payment_date")
        card_id = card["id"]
        account_id = card["account_id"]

        # Use the snapshot's calculated payment
        monthly_expense = (
            Decimal(str(calculated_payment)) if calculated_payment else Decimal("0")
        )
        paid_amount = (
            Decimal(str(actual_payment_amount))
            if actual_payment_amount
            else Decimal("0")
        )
        remaining_payment = max(monthly_expense - paid_amount, Decimal("0"))
        total_planned += monthly_expense
        total_paid += paid_amount

        # Short name for display
        short_name = f"{card_name[:18]}..." if len(card_name) > 20 else card_name
        display_name = f"{short_name} ({mask})" if mask else short_name
        strategy_label = "💳" if payment_strategy == "pay_in_full" else "🎁"

        # Format due date
        due_date = card.get("due_date")
        if due_date:
            due_date_str = (
                due_date.strftime("%m/%d")
                if hasattr(due_date, "strftime")
                else str(due_date)[:5]
            )
        else:
            due_date_str = "—"
        if (
            payment_strategy == "pay_in_full"
            and due_date
            and str(due_date)[:7] != year_month
            and monthly_expense > 0
        ):
            out_of_month_full_payments.append((display_name, monthly_expense, due_date))

        # Format actual payment amount
        paid_str = f"${paid_amount:,.2f}" if actual_payment_amount is not None else "—"

        # Format actual payment date
        if actual_payment_date:
            paid_date_str = (
                actual_payment_date.strftime("%m/%d")
                if hasattr(actual_payment_date, "strftime")
                else str(actual_payment_date)[:5]
            )
        else:
            paid_date_str = "—"

        if is_closed:
            cols = st.columns([3, 2, 2, 2, 2, 2, 2, 1])
            cols[0].write(display_name)
            cols[1].write(f"${monthly_expense:,.2f}")
            cols[2].write(due_date_str)
            cols[3].write(f"${statement_balance:,.2f}" if statement_balance else "—")
            cols[4].write(paid_str)
            cols[5].write(f"${remaining_payment:,.2f}")
            cols[6].write(paid_date_str)
            cols[7].write(strategy_label)
        else:
            cols = st.columns([3, 2, 2, 2, 2, 2, 2, 1, 1])
            cols[0].write(display_name)
            cols[1].write(f"${monthly_expense:,.2f}")
            cols[2].write(due_date_str)
            cols[3].write(f"${statement_balance:,.2f}" if statement_balance else "—")
            cols[4].write(paid_str)
            cols[5].write(f"${remaining_payment:,.2f}")
            cols[6].write(paid_date_str)
            cols[7].write(strategy_label)
            if cols[8].button("⚙️", key=f"cs_{card_id}", help="Change strategy"):
                st.session_state[f"editing_strategy_{card_id}"] = True
                st.rerun()

            # Inline strategy editor
            if st.session_state.get(f"editing_strategy_{card_id}", False):
                with st.form(key=f"sf_{card_id}"):
                    c1, c2, c3 = st.columns([2, 2, 1])
                    new_strat = c1.selectbox(
                        "Strategy",
                        ["pay_in_full", "promotional_paydown"],
                        index=0 if payment_strategy == "pay_in_full" else 1,
                        label_visibility="collapsed",
                    )
                    new_fixed = c2.number_input(
                        "Fixed $",
                        value=float(fixed_payment_amount or 0),
                        min_value=0.0,
                        label_visibility="collapsed",
                    )
                    if c3.form_submit_button("💾"):
                        update_snapshot_credit_card(
                            session,
                            card_id,
                            new_strat,
                            new_fixed if new_strat == "promotional_paydown" else None,
                        )
                        session.commit()
                        st.session_state[f"editing_strategy_{card_id}"] = False
                        # Form submission triggers automatic rerun - no need for explicit st.rerun()

    total_remaining = max(total_planned - total_paid, Decimal("0"))
    planned_col, paid_col, remaining_col = st.columns(3)
    planned_col.metric("Planned card payments", f"${total_planned:,.2f}")
    paid_col.metric("Actually paid", f"${total_paid:,.2f}")
    remaining_col.metric("Remaining planned", f"${total_remaining:,.2f}")
    if out_of_month_full_payments:
        stale_total = sum(
            (amount for _, amount, _ in out_of_month_full_payments), Decimal("0")
        )
        st.warning(
            f"${stale_total:,.2f} of this plan comes from pay-in-full statements "
            f"due outside {year_month}. Treat these as estimates until new statements sync."
        )
    st.caption("💳 = Pay Full (statement due) · 🎁 = Promo (fixed payment)")


# Main page layout
st.title("Monthly Snapshot")

# Get selected account and month
with get_session() as session:
    account_id = render_account_selector(session)
    year_month = render_month_selector(session, account_id)
    snapshot = get_or_create_snapshot(session, year_month, account_id)
    snapshot_status = snapshot.get("status", "open")

reconciliation_complete = snapshot_status == "closed"

# Show status indicator and guarded Close Month preview
if snapshot_status == "open":
    st.caption("📝 This month is open for editing")
    try:
        with get_read_only_session() as preview_session:
            close_preview = build_close_preview(preview_session, year_month, account_id)
    except Exception as exc:
        close_preview = None
        st.error(f"Close preview unavailable: {exc}")

    if close_preview is not None:
        reconciliation_evidence = close_preview.reconciliation_evidence
        reconciliation_complete = bool(
            reconciliation_evidence
            and reconciliation_evidence.is_valid
            and reconciliation_evidence.has_remaining_items is False
        )
        with st.expander(
            "🔎 Review close readiness", expanded=bool(close_preview.blockers)
        ):
            c1, c2, c3 = st.columns(3)
            c1.metric(
                "Projected close",
                f"${close_preview.projected_closing_balance:,.2f}"
                if close_preview.projected_closing_balance is not None
                else "—",
            )
            c2.metric(
                "Posted card payments",
                f"${close_preview.actual_credit_card_total:,.2f}",
            )
            if reconciliation_complete:
                c3.metric("Net change", f"${close_preview.totals.net:,.2f}")
            else:
                c3.metric(
                    "Remaining card plan",
                    f"${close_preview.remaining_credit_card_total:,.2f}",
                )
            counts = close_preview.transaction_counts
            st.caption(
                f"Posted: {counts.posted} · Unreviewed: {counts.unreviewed} · "
                f"Uncategorized: {counts.uncategorized} · "
                f"Reimbursable: {counts.reimbursable} · Pending: {counts.pending} · "
                f"Cards missing actuals: {close_preview.missing_actual_credit_card_count}"
            )
            st.caption(f"Audit hash: {close_preview.audit_hash}")
            if close_preview.blockers:
                for blocker in close_preview.blockers:
                    st.error(blocker)
            else:
                st.success("All automated close guards passed.")

            confirmation = st.text_input(
                f"Type {year_month} to confirm this irreversible close",
                key=f"close_confirmation_{account_id}_{year_month}",
            )
            if st.button(
                "🔒 Close Month",
                help="Freeze reconciled actual cash flow and closing balance",
                disabled=bool(close_preview.blockers) or confirmation != year_month,
            ):
                try:
                    with get_session() as session:
                        close_snapshot(
                            session,
                            year_month,
                            account_id,
                            confirm_month=confirmation,
                            audit_hash=close_preview.audit_hash,
                        )
                    st.success(f"Month {year_month} closed!")
                    st.rerun()
                except Exception as exc:
                    st.error(f"Close refused: {exc}")
else:
    st.caption("🔒 This month is closed (read-only)")

# Show sync status indicator
last_synced_at = snapshot.get("last_synced_at")
if last_synced_at:
    # Format datetime for display
    if isinstance(last_synced_at, datetime):
        sync_time = last_synced_at.strftime("%m/%d/%Y %I:%M %p")
    else:
        sync_time = str(last_synced_at)
    st.caption(f"🔄 Last reconciled with transactions: {sync_time}")
else:
    st.caption("⚠️ Not yet reconciled with actual transactions")

# Balance display section
with get_session() as session:
    render_balance_display(session, account_id, year_month)

# Calculate snapshot totals
with get_session() as session:
    totals = calculate_snapshot_totals(session, year_month, account_id)

# Overview section - compact
render_overview_metrics(totals, reconciliation_complete=reconciliation_complete)


def render_planning_history(display_status: str) -> None:
    """Render the original monthly plan without changing actual reporting."""
    col_left, col_right = st.columns(2)
    with col_left:
        st.header("Income")
        with get_session() as session:
            render_income_section(session, year_month, account_id, display_status)
    with col_right:
        st.header("Expenses")
        with get_session() as session:
            render_expenses_section(session, year_month, account_id, display_status)
    st.header("Transfers")
    with get_session() as session:
        render_transfers_section(session, year_month, account_id, display_status)


if reconciliation_complete:
    st.caption("Showing reconciled actuals. Original planning entries are hidden.")
    with st.expander("Planning history"):
        st.caption("Read-only record of the plan; crossed-out items were skipped.")
        render_planning_history("closed")
else:
    render_planning_history(snapshot_status)

# Credit Cards section - full width
st.header("Credit Cards")
with get_session() as session:
    render_credit_cards_section(
        session,
        year_month,
        account_id,
        snapshot_status,
        reconciliation_complete=reconciliation_complete,
    )

# Notes section - full width
st.header("Notes")
st.caption("Record discrepancies, context, or reminders for future reference")
notes_read_only = snapshot_status == "closed"
if notes_read_only:
    st.caption("Closed-month notes are read-only.")

# Get current notes from snapshot
current_notes = snapshot.get("notes", "") or ""

# Use expander for notes to keep it compact
with st.expander(
    "📝 View Notes" if notes_read_only else "📝 View/Edit Notes",
    expanded=bool(current_notes),
):
    notes_input = st.text_area(
        "Notes",
        value=current_notes,
        height=100,
        label_visibility="collapsed",
        placeholder="Add notes about discrepancies, one-time adjustments, or context for this month...",
        key="snapshot_notes",
        disabled=notes_read_only,
    )

    # Show save button only if notes changed
    if not notes_read_only and notes_input != current_notes:
        if st.button("💾 Save Notes"):
            with get_session() as session:
                update_snapshot_notes(
                    session, year_month, account_id, notes_input or None
                )
                session.commit()
                st.success("Notes saved!")
                st.rerun()
