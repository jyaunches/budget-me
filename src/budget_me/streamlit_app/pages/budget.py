"""Budget Page - Set monthly budget targets and view actuals vs budget."""

from datetime import date
from decimal import Decimal

import streamlit as st

from budget_me.streamlit_app.db import (
    copy_budgets_from_month,
    get_available_budget_months,
    get_budget_categories_from_yaml,
    get_category_actuals,
    get_category_budgets,
    get_category_transactions,
    get_depository_accounts,
    get_previous_month,
    get_session,
    is_budget_month_locked,
    upsert_category_budget,
)

# Compact CSS
st.markdown(
    """
<style>
    .block-container { padding-top: 1rem; padding-bottom: 0rem; }
    div[data-testid="stMetric"] { padding: 0.3rem 0; }
    div[data-testid="stMetric"] label { font-size: 0.8rem; }
    div[data-testid="stMetric"] > div { font-size: 1.2rem; }
    h1 { font-size: 1.5rem !important; margin-bottom: 0.5rem !important; }
    h2 { font-size: 1.1rem !important; margin: 0.5rem 0 0.25rem 0 !important; }
    .budget-card {
        background: rgba(128,128,128,0.1);
        border-radius: 8px;
        padding: 0.75rem;
        margin-bottom: 0.5rem;
    }
    .budget-card-header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        margin-bottom: 0.5rem;
    }
    .category-name {
        font-weight: 600;
        font-size: 0.95rem;
        text-transform: capitalize;
    }
    .budget-amounts {
        font-size: 0.85rem;
        color: #aaa;
    }
    .progress-container {
        background: rgba(128,128,128,0.2);
        border-radius: 4px;
        height: 24px;
        position: relative;
        overflow: hidden;
    }
    .progress-fill {
        height: 100%;
        border-radius: 4px;
        transition: width 0.3s ease;
    }
    .progress-fill.green { background: #2e7d32; }
    .progress-fill.yellow { background: #f9a825; }
    .progress-fill.red { background: #c62828; }
    .progress-text {
        position: absolute;
        right: 8px;
        top: 50%;
        transform: translateY(-50%);
        font-weight: 600;
        font-size: 0.85rem;
        color: white;
        text-shadow: 1px 1px 2px rgba(0,0,0,0.5);
    }
    .budget-status {
        font-size: 0.8rem;
        color: #888;
        margin-top: 0.5rem;
        text-align: right;
    }
    .budget-status.over { color: #c62828; }
    .budget-status.under { color: #2e7d32; }
</style>
""",
    unsafe_allow_html=True,
)


def format_category_name(category: str) -> str:
    """Convert snake_case category to Title Case display name."""
    return category.replace("_", " ").title()


def render_account_selector(session) -> str:
    """Render account selector and return selected account_id string."""
    accounts = get_depository_accounts(session, include_excluded=False)

    if not accounts:
        st.error("No depository accounts found. Please connect an account first.")
        st.stop()

    # Sort accounts alphabetically
    accounts = sorted(
        accounts,
        key=lambda a: (a.get("display_name") or a["name"]).lower(),
        reverse=True,
    )

    options = []
    for account in accounts:
        display_name = account.get("display_name") or account["name"]
        options.append(display_name)

    values = [account["account_id"] for account in accounts]

    if "budget_account_index" not in st.session_state:
        st.session_state.budget_account_index = 0

    selected_index = st.selectbox(
        "Account",
        range(len(options)),
        format_func=lambda i: options[i],
        index=st.session_state.budget_account_index,
        key="budget_account_selector",
    )

    st.session_state.budget_account_index = selected_index
    return values[selected_index]


def render_month_selector(session, account_id: str) -> str:
    """Render month selector and return selected year_month string."""
    # Get available months
    available_months = get_available_budget_months(session, account_id)

    # Always include current month
    current_month = date.today().strftime("%Y-%m")
    month_values = [m["year_month"] for m in available_months]

    if current_month not in month_values:
        month_values.insert(0, current_month)

    # Sort newest first
    month_values = sorted(month_values, reverse=True)

    # Format for display
    def format_month(ym: str) -> str:
        year, month = ym.split("-")
        month_names = [
            "",
            "January",
            "February",
            "March",
            "April",
            "May",
            "June",
            "July",
            "August",
            "September",
            "October",
            "November",
            "December",
        ]
        locked = is_budget_month_locked(ym)
        lock_icon = " 🔒" if locked else ""
        return f"{month_names[int(month)]} {year}{lock_icon}"

    # Default to current month
    default_index = 0
    if current_month in month_values:
        default_index = month_values.index(current_month)

    col1, col2 = st.columns([1, 3])
    with col1:
        selected_index = st.selectbox(
            "Month",
            range(len(month_values)),
            format_func=lambda i: format_month(month_values[i]),
            index=default_index,
            key="budget_month_selector",
            label_visibility="collapsed",
        )

    return month_values[selected_index]


def render_configure_view(session, account_id: str, year_month: str, is_locked: bool):
    """Render the Configure Budgets view."""
    # Check for inheritance on first access
    budgets = get_category_budgets(session, account_id, year_month)
    inherited_from = None

    if not budgets and not is_locked:
        # Try to inherit from previous month
        prev_month = get_previous_month(year_month)
        prev_budgets = get_category_budgets(session, account_id, prev_month)

        if prev_budgets:
            copy_budgets_from_month(session, account_id, year_month, prev_month)
            session.commit()
            budgets = get_category_budgets(session, account_id, year_month)
            inherited_from = prev_month

    if inherited_from:
        month_name = format_month_display(inherited_from)
        st.info(f"Budgets inherited from {month_name}. You can edit them below.")

    # Get all categories
    categories = get_budget_categories_from_yaml()

    # Build budget lookup
    budget_lookup = {b["category"]: b["budget_amount"] for b in budgets}

    # Display header
    if is_locked:
        st.caption("🔒 This month is locked (read-only)")
    else:
        st.caption("Set your monthly budget targets for each category")

    # Calculate total
    total_budget = sum(Decimal(str(budget_lookup.get(cat, 0))) for cat in categories)

    # Show total at top
    st.metric("Total Monthly Budget", f"${total_budget:,.2f}")
    st.markdown("---")

    # Store pending changes
    if "pending_budgets" not in st.session_state:
        st.session_state.pending_budgets = {}

    # Table header
    cols = st.columns([3, 2])
    cols[0].markdown("**Category**")
    cols[1].markdown("**Monthly Budget**")

    # Render each category
    for category in categories:
        current_amount = budget_lookup.get(category, Decimal("0"))

        cols = st.columns([3, 2])
        cols[0].markdown(format_category_name(category))

        if is_locked:
            cols[1].text(f"${current_amount:,.2f}")
        else:
            # Use number input for editing
            key = f"budget_{account_id}_{year_month}_{category}"
            new_amount = cols[1].number_input(
                f"Budget for {category}",
                min_value=0.0,
                value=float(current_amount),
                step=10.0,
                key=key,
                label_visibility="collapsed",
            )

            # Track changes
            if Decimal(str(new_amount)) != current_amount:
                st.session_state.pending_budgets[(account_id, year_month, category)] = (
                    Decimal(str(new_amount))
                )

    # Save button
    if not is_locked:
        st.markdown("---")

        # Calculate new total from pending changes
        new_total = Decimal("0")
        for category in categories:
            key = (account_id, year_month, category)
            if key in st.session_state.pending_budgets:
                new_total += st.session_state.pending_budgets[key]
            else:
                new_total += Decimal(str(budget_lookup.get(category, 0)))

        col1, col2 = st.columns([1, 1])
        with col1:
            st.metric("New Total", f"${new_total:,.2f}")

        with col2:
            if st.button("💾 Save Changes", type="primary"):
                with st.spinner("Saving..."):
                    # Save all pending changes
                    for (
                        acc_id,
                        ym,
                        cat,
                    ), amount in st.session_state.pending_budgets.items():
                        if acc_id == account_id and ym == year_month:
                            upsert_category_budget(session, acc_id, ym, cat, amount)

                    session.commit()
                    st.session_state.pending_budgets = {}
                    st.success("Budgets saved!")
                    st.rerun()


def format_month_display(year_month: str) -> str:
    """Format year_month to display string."""
    year, month = year_month.split("-")
    month_names = [
        "",
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
    ]
    return f"{month_names[int(month)]} {year}"


def create_progress_bar_html(percentage: float) -> str:
    """Create HTML for a horizontal progress bar showing budget usage.

    Args:
        percentage: Budget usage percentage (0-150+ supported)

    Returns:
        HTML string for the progress bar
    """
    # Determine color class based on percentage
    if percentage >= 100:
        color_class = "red"
    elif percentage >= 80:
        color_class = "yellow"
    else:
        color_class = "green"

    # Cap display width at 100% (but show actual percentage in text)
    display_width = min(percentage, 100)
    display_pct = f"{percentage:.0f}%"

    return f'<div class="progress-container"><div class="progress-fill {color_class}" style="width: {display_width}%"></div><span class="progress-text">{display_pct}</span></div>'


def render_actuals_view(session, account_id: str, year_month: str):
    """Render the View Actuals view with progress bars."""
    # Get budgets and actuals
    budgets = get_category_budgets(session, account_id, year_month)
    actuals = get_category_actuals(session, account_id, year_month)

    # Build lookups
    budget_lookup = {b["category"]: Decimal(str(b["budget_amount"])) for b in budgets}
    actuals_lookup = {a["category"]: Decimal(str(a["total_spent"])) for a in actuals}

    # Get all categories that have either a budget or spending
    all_categories = set(budget_lookup.keys()) | set(actuals_lookup.keys())

    if not all_categories:
        st.info("No budget data or spending for this month yet.")
        return

    # Calculate summary metrics
    total_budget = sum(budget_lookup.values())
    total_spent = sum(actuals_lookup.values())
    remaining = total_budget - total_spent

    # Count over-budget categories (only those with budgets set)
    over_budget_count = sum(
        1
        for cat in budget_lookup
        if cat in actuals_lookup and actuals_lookup[cat] > budget_lookup[cat]
    )

    # Summary metrics row
    col1, col2, col3, col4 = st.columns(4)

    with col1:
        st.metric("Total Budget", f"${total_budget:,.2f}")

    with col2:
        pct = (total_spent / total_budget * 100) if total_budget > 0 else 0
        st.metric("Total Spent", f"${total_spent:,.2f}", delta=f"{pct:.0f}%")

    with col3:
        st.metric("Remaining", f"${remaining:,.2f}")

    with col4:
        st.metric("Over Budget", f"{over_budget_count} categories")

    st.markdown("---")

    # Sorting options
    sort_option = st.radio(
        "Sort by",
        ["Over Budget First", "Alphabetical"],
        horizontal=True,
        key="budget_sort",
    )

    # Build category data with percentages
    category_data = []
    for category in all_categories:
        budget = budget_lookup.get(category, Decimal("0"))
        spent = actuals_lookup.get(category, Decimal("0"))
        percentage = (float(spent) / float(budget) * 100) if budget > 0 else 0
        category_data.append(
            {
                "category": category,
                "budget": budget,
                "spent": spent,
                "percentage": percentage,
                "has_budget": budget > 0,
            }
        )

    # Sort
    if sort_option == "Over Budget First":
        # Sort by percentage descending, then alphabetically
        category_data.sort(key=lambda x: (-x["percentage"], x["category"]))
    else:
        category_data.sort(key=lambda x: x["category"])

    # Render gauge cards in grid (3 per row)
    for i in range(0, len(category_data), 3):
        cols = st.columns(3)
        for j, col in enumerate(cols):
            idx = i + j
            if idx >= len(category_data):
                break

            data = category_data[idx]
            with col:
                render_category_card(data, session, account_id, year_month)


@st.dialog("Category Transactions")
def show_category_transactions_dialog(
    session,
    account_id: str,
    year_month: str,
    category: str,
    budget: Decimal,
    spent: Decimal,
):
    """Display transaction drill-down modal for a category.

    Args:
        session: Database session
        account_id: The depository account ID
        year_month: Year-month string (e.g., "2025-01")
        category: The budget category to show transactions for
        budget: The budgeted amount for this category
        spent: The actual amount spent in this category
    """
    # Header with category name
    st.markdown(f"### {format_category_name(category)}")

    # Summary metrics row
    remaining = budget - spent
    col1, col2, col3 = st.columns(3)

    with col1:
        st.metric("Budget", f"${budget:,.2f}")

    with col2:
        st.metric("Spent", f"${spent:,.2f}")

    with col3:
        if remaining >= 0:
            st.metric("Remaining", f"${remaining:,.2f}", delta=None)
        else:
            st.metric(
                "Over Budget",
                f"${abs(remaining):,.2f}",
                delta=None,
                delta_color="inverse",
            )

    st.markdown("---")

    # Fetch transactions
    transactions = get_category_transactions(session, account_id, year_month, category)

    if not transactions:
        st.info("No transactions found for this category.")
        return

    # Display transaction count
    st.caption(f"Showing {len(transactions)} transaction(s)")

    # Convert to DataFrame for display
    import pandas as pd

    df = pd.DataFrame(transactions)

    # Format date column
    df["date"] = pd.to_datetime(df["date"]).dt.strftime("%m/%d/%Y")

    # Format amount as currency
    df["amount"] = df["amount"].apply(lambda x: f"${x:,.2f}")

    # Rename columns for display
    df = df.rename(
        columns={
            "date": "Date",
            "merchant_name": "Merchant",
            "amount": "Amount",
            "account_name": "Account",
        }
    )

    # Display table
    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True,
    )


def render_category_card(data: dict, session, account_id: str, year_month: str):
    """Render a single category card with progress bar and View Transactions button."""
    category = data["category"]
    budget = data["budget"]
    spent = data["spent"]
    percentage = data["percentage"]
    has_budget = data["has_budget"]

    remaining = budget - spent
    if has_budget:
        # Status text for under/over budget
        if remaining >= 0:
            status_text = f"${remaining:,.2f} left"
            status_class = "under"
        else:
            status_text = f"${abs(remaining):,.2f} over"
            status_class = "over"

        # Unified card with header, progress bar, and status
        progress_bar = create_progress_bar_html(percentage)
        st.markdown(
            f"""
        <div class="budget-card">
            <div class="budget-card-header">
                <span class="category-name">{format_category_name(category)}</span>
                <span class="budget-amounts">${spent:,.2f} / ${budget:,.2f}</span>
            </div>
            {progress_bar}
            <div class="budget-status {status_class}">{status_text}</div>
        </div>
        """,
            unsafe_allow_html=True,
        )
    else:
        # No budget set - simpler card
        st.markdown(
            f"""
        <div class="budget-card">
            <div class="budget-card-header">
                <span class="category-name">{format_category_name(category)}</span>
                <span class="budget-amounts">No budget</span>
            </div>
            <div style="text-align: center; padding: 0.5rem; color: #888;">
                <div>Spent: ${spent:,.2f}</div>
            </div>
        </div>
        """,
            unsafe_allow_html=True,
        )

    # Add View Transactions button if there is spending
    if spent > 0:
        if st.button(
            "View Transactions",
            key=f"view_txns_{category}",
            use_container_width=True,
        ):
            show_category_transactions_dialog(
                session, account_id, year_month, category, budget, spent
            )


# Main page layout
st.title("Budget")

# View toggle
view = st.radio(
    "View",
    ["View Actuals", "Configure Budgets"],
    horizontal=True,
    key="budget_view_toggle",
)

st.markdown("---")

# Get selected account and month
with get_session() as session:
    account_id = render_account_selector(session)
    year_month = render_month_selector(session, account_id)
    is_locked = is_budget_month_locked(year_month)

    st.markdown("---")

    # Render appropriate view
    if view == "View Actuals":
        render_actuals_view(session, account_id, year_month)
    else:
        render_configure_view(session, account_id, year_month, is_locked)
