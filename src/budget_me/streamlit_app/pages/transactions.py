"""Streamlit page for reviewing transactions."""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from budget_me.streamlit_app.db import (
    get_accounts,
    get_budget_categories,
    get_project_tags,
    get_session,
    get_transaction_stats,
    get_transactions,
    mark_reviewed,
    set_project_tags,
)

st.title("Transaction Review")


# Sidebar filters
st.sidebar.header("Filters")

# Date range filter
default_start = date.today() - timedelta(days=30)
default_end = date.today()

col1, col2 = st.sidebar.columns(2)
with col1:
    start_date = st.date_input("From", value=default_start)
with col2:
    end_date = st.date_input("To", value=default_end)

# Show excluded accounts toggle
show_excluded = st.sidebar.checkbox("Show excluded accounts", value=False)

# Account filter
with get_session() as session:
    accounts = get_accounts(session, include_excluded=show_excluded)

account_options = {"All Accounts": None}
account_options.update({acc["display"]: acc["account_id"] for acc in accounts})

selected_account_display = st.sidebar.selectbox(
    "Account",
    options=list(account_options.keys()),
)
selected_account = account_options[selected_account_display]

# Reviewed status filter
review_filter = st.sidebar.radio(
    "Review Status",
    options=["All", "Unreviewed", "Reviewed"],
    index=1,  # Default to Unreviewed
)

reviewed_filter = {
    "All": None,
    "Unreviewed": False,
    "Reviewed": True,
}[review_filter]

# Budget category filter
with get_session() as session:
    categories = get_budget_categories(session)

category_options = {"All Categories": None, "Uncategorized": "__uncategorized__"}
category_options.update({cat: cat for cat in categories})

selected_category_display = st.sidebar.selectbox(
    "Budget Category",
    options=list(category_options.keys()),
)
selected_category = category_options[selected_category_display]

# Handle special "Uncategorized" option
categorized_filter = None
budget_category_filter = None
if selected_category == "__uncategorized__":
    categorized_filter = False
else:
    budget_category_filter = selected_category

# Project tag filter
with get_session() as session:
    project_tags = get_project_tags(session)

project_options = {"All Projects": None}
project_options.update({tag: tag for tag in project_tags})
selected_project_display = st.sidebar.selectbox(
    "Project", options=list(project_options.keys())
)
project_tag_filter = project_options[selected_project_display]

# Limit (per tab)
limit = st.sidebar.slider(
    "Max per Tab", min_value=50, max_value=500, value=250, step=50
)

# Stats in sidebar
st.sidebar.divider()
st.sidebar.subheader("Statistics")
with get_session() as session:
    stats = get_transaction_stats(session)
    st.sidebar.metric("Total Transactions", stats["total"])
    st.sidebar.metric("Reviewed", stats["reviewed"])
    st.sidebar.metric("Unreviewed", stats["unreviewed"])


def display_transaction_table(
    transactions: list[dict], tab_key: str, limit_reached: bool = False
) -> None:
    """Display an editable transaction table with review functionality.

    Args:
        transactions: List of transaction dictionaries
        tab_key: Unique key for this tab's widgets
        limit_reached: Whether the query hit the limit (may have more data)
    """
    if not transactions:
        st.info("No transactions found matching the filters.")
        return

    tab_total = sum(t["amount"] for t in transactions)
    if limit_reached:
        st.warning(
            f"Showing {len(transactions)} transactions · ${tab_total:,.2f} "
            "(limit reached - increase 'Max per Tab' to see more)"
        )
    else:
        st.write(f"Showing {len(transactions)} transactions · ${tab_total:,.2f}")

    df = pd.DataFrame(transactions)

    # Format amount as currency
    df["amount_display"] = df["amount"].apply(lambda x: f"${x:,.2f}")

    # project_tag may be absent on older cached payloads; default to empty string
    if "project_tag" not in df.columns:
        df["project_tag"] = None
    df["project_tag"] = df["project_tag"].fillna("")

    # Select and rename columns for display
    display_df = df[
        [
            "reviewed",
            "date",
            "name",
            "merchant_name",
            "amount_display",
            "budget_category",
            "project_tag",
            "account_name",
        ]
    ].copy()
    display_df.columns = [
        "Reviewed",
        "Date",
        "Description",
        "Merchant",
        "Amount",
        "Category",
        "Project",
        "Account",
    ]

    # Editable data editor
    edited_df = st.data_editor(
        display_df,
        column_config={
            "Reviewed": st.column_config.CheckboxColumn(
                "Reviewed",
                help="Check to mark as reviewed",
                default=False,
            ),
            "Date": st.column_config.DateColumn("Date", format="YYYY-MM-DD"),
            "Amount": st.column_config.TextColumn("Amount"),
            "Project": st.column_config.TextColumn(
                "Project",
                help="Cross-month project tag (e.g. landscaping). Budget-neutral.",
            ),
        },
        disabled=["Date", "Description", "Merchant", "Amount", "Category", "Account"],
        hide_index=True,
        use_container_width=True,
        key=f"transaction_editor_{tab_key}",
    )

    # Detect changes
    original_reviewed = display_df["Reviewed"].tolist()
    edited_reviewed = edited_df["Reviewed"].tolist()

    # Find which rows changed
    changed_to_reviewed = []
    changed_to_unreviewed = []

    for i, (orig, edited) in enumerate(zip(original_reviewed, edited_reviewed)):
        if orig != edited:
            transaction_id = df.iloc[i]["id"]
            if edited:
                changed_to_reviewed.append(transaction_id)
            else:
                changed_to_unreviewed.append(transaction_id)

    # Detect project tag changes (free-text column)
    original_projects = display_df["Project"].tolist()
    edited_projects = edited_df["Project"].tolist()
    project_changes: dict[str, str | None] = {}
    for i, (orig, edited) in enumerate(zip(original_projects, edited_projects)):
        if (orig or "") != (edited or ""):
            project_changes[df.iloc[i]["id"]] = edited

    # Show save button if there are changes
    if changed_to_reviewed or changed_to_unreviewed or project_changes:
        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            changes_text = []
            if changed_to_reviewed:
                changes_text.append(f"{len(changed_to_reviewed)} to mark reviewed")
            if changed_to_unreviewed:
                changes_text.append(f"{len(changed_to_unreviewed)} to unmark")
            if project_changes:
                changes_text.append(f"{len(project_changes)} project tag(s)")
            st.info(f"Pending changes: {', '.join(changes_text)}")

        with col2:
            if st.button("Save Changes", type="primary", key=f"save_{tab_key}"):
                with get_session() as session:
                    if changed_to_reviewed:
                        mark_reviewed(session, changed_to_reviewed, reviewed=True)
                    if changed_to_unreviewed:
                        mark_reviewed(session, changed_to_unreviewed, reviewed=False)
                    if project_changes:
                        set_project_tags(session, project_changes)
                st.success("Changes saved!")
                st.rerun()

        with col3:
            if st.button("Discard", key=f"discard_{tab_key}"):
                st.rerun()

    # Bulk action buttons
    st.divider()
    col1, col2 = st.columns(2)

    with col1:
        if st.button("Mark All Visible as Reviewed", key=f"mark_all_{tab_key}"):
            unreviewed_ids = [
                df.iloc[i]["id"]
                for i, row in display_df.iterrows()
                if not row["Reviewed"]
            ]
            if unreviewed_ids:
                with get_session() as session:
                    count = mark_reviewed(session, unreviewed_ids, reviewed=True)
                st.success(f"Marked {count} transactions as reviewed!")
                st.rerun()
            else:
                st.info("All visible transactions are already reviewed.")

    with col2:
        if st.button("Unmark All Visible", key=f"unmark_all_{tab_key}"):
            reviewed_ids = [
                df.iloc[i]["id"] for i, row in display_df.iterrows() if row["Reviewed"]
            ]
            if reviewed_ids:
                with get_session() as session:
                    count = mark_reviewed(session, reviewed_ids, reviewed=False)
                st.success(f"Unmarked {count} transactions!")
                st.rerun()
            else:
                st.info("No reviewed transactions to unmark.")


# Main content - Tabs for different transaction types
st.divider()

# Fetch transactions by type (limit applied per type, not globally)
with get_session() as session:
    spending = get_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=selected_account,
        reviewed=reviewed_filter,
        transaction_type="spending",
        categorized=categorized_filter,
        budget_category=budget_category_filter,
        project_tag=project_tag_filter,
        limit=limit,
    )
    transfers = get_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=selected_account,
        reviewed=reviewed_filter,
        transaction_type="transfers",
        categorized=categorized_filter,
        budget_category=budget_category_filter,
        project_tag=project_tag_filter,
        limit=limit,
    )
    payments = get_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=selected_account,
        reviewed=reviewed_filter,
        transaction_type="payments",
        categorized=categorized_filter,
        budget_category=budget_category_filter,
        project_tag=project_tag_filter,
        limit=limit,
    )
    income = get_transactions(
        session,
        start_date=start_date,
        end_date=end_date,
        account_id=selected_account,
        reviewed=reviewed_filter,
        transaction_type="income",
        categorized=categorized_filter,
        budget_category=budget_category_filter,
        project_tag=project_tag_filter,
        limit=limit,
    )

# Filtered total across all tabs (useful when filtering by project tag)
all_filtered = spending + transfers + payments + income
filtered_count = len(all_filtered)
filtered_total = sum(t["amount"] for t in all_filtered)
mcol1, mcol2 = st.columns(2)
mcol1.metric("Filtered Transactions", filtered_count)
mcol2.metric("Filtered Total", f"${filtered_total:,.2f}")

# Create tabs
tab_spending, tab_transfers, tab_payments, tab_income = st.tabs(
    [
        f"Spending ({len(spending)})",
        f"Transfers ({len(transfers)})",
        f"Payments ({len(payments)})",
        f"Income ({len(income)})",
    ]
)

with tab_spending:
    display_transaction_table(
        spending, "spending", limit_reached=len(spending) >= limit
    )

with tab_transfers:
    display_transaction_table(
        transfers, "transfers", limit_reached=len(transfers) >= limit
    )

with tab_payments:
    display_transaction_table(
        payments, "payments", limit_reached=len(payments) >= limit
    )

with tab_income:
    display_transaction_table(income, "income", limit_reached=len(income) >= limit)
