"""Streamlit page for managing account display names."""

import pandas as pd
import streamlit as st

from budget_me.streamlit_app.db import (
    get_all_accounts_with_details,
    get_session,
    update_account_display_name,
    update_account_excluded_status,
)

st.title("Account Settings")

st.write(
    "Edit display names to give your accounts friendly names that persist across syncs."
)

# Fetch accounts
with get_session() as session:
    accounts = get_all_accounts_with_details(session)

if not accounts:
    st.info("No accounts found. Use the Link Account page to connect your bank.")
    if st.button("Go to Link Account"):
        st.switch_page("pages/link_account.py")
    st.stop()

# Create DataFrame for editing
df = pd.DataFrame(accounts)

# Format balances for display
df["balance_display"] = df["balance_current"].apply(
    lambda x: f"${x:,.2f}" if x is not None else "-"
)

# Prepare display DataFrame
display_df = df[
    ["name", "display_name", "type", "mask", "balance_display", "is_excluded"]
].copy()
display_df.columns = [
    "Plaid Name",
    "Display Name",
    "Type",
    "Mask",
    "Balance",
    "Excluded",
]

# Fill None display names with empty string for editing
display_df["Display Name"] = display_df["Display Name"].fillna("")
# Ensure is_excluded is bool (handle None)
display_df["Excluded"] = display_df["Excluded"].fillna(False).astype(bool)

st.write(f"**{len(accounts)} accounts connected**")

# Editable table
edited_df = st.data_editor(
    display_df,
    column_config={
        "Display Name": st.column_config.TextColumn(
            "Display Name",
            help="Enter a custom name for this account. Leave blank to use Plaid name.",
            max_chars=255,
        ),
        "Plaid Name": st.column_config.TextColumn(
            "Plaid Name",
            help="Original name from your bank via Plaid",
        ),
        "Type": st.column_config.TextColumn("Type"),
        "Mask": st.column_config.TextColumn("Mask", help="Last 4 digits"),
        "Balance": st.column_config.TextColumn("Balance"),
        "Excluded": st.column_config.CheckboxColumn(
            "Excluded",
            help="Exclude from new snapshots and debt calculations",
            default=False,
        ),
    },
    disabled=["Plaid Name", "Type", "Mask", "Balance"],
    hide_index=True,
    use_container_width=True,
    key="accounts_editor",
)

# Detect changes
original_display_names = display_df["Display Name"].tolist()
edited_display_names = edited_df["Display Name"].tolist()
original_excluded = display_df["Excluded"].tolist()
edited_excluded = edited_df["Excluded"].tolist()

# Find changed accounts
changes = []
for i in range(len(df)):
    display_name_changed = original_display_names[i] != edited_display_names[i]
    excluded_changed = original_excluded[i] != edited_excluded[i]

    if display_name_changed or excluded_changed:
        account_id = df.iloc[i]["account_id"]
        new_name = (
            edited_display_names[i].strip()
            if edited_display_names[i].strip()
            else None  # Empty string -> None
        )
        changes.append(
            {
                "account_id": account_id,
                "plaid_name": df.iloc[i]["name"],
                "old_display_name": original_display_names[i]
                if original_display_names[i]
                else None,
                "new_display_name": new_name,
                "display_name_changed": display_name_changed,
                "old_excluded": original_excluded[i],
                "new_excluded": edited_excluded[i],
                "excluded_changed": excluded_changed,
            }
        )

# Show save button if there are changes
if changes:
    st.divider()
    st.subheader("Pending Changes")

    for change in changes:
        change_parts = []

        if change["display_name_changed"]:
            old_name = (
                change["old_display_name"]
                or f"(using Plaid name: {change['plaid_name']})"
            )
            new_name = (
                change["new_display_name"]
                or f"(using Plaid name: {change['plaid_name']})"
            )
            change_parts.append(f"Display name: {old_name} → {new_name}")

        if change["excluded_changed"]:
            status = "excluded" if change["new_excluded"] else "included"
            change_parts.append(f"Status: {status}")

        st.write(f"- **{change['plaid_name']}**: {', '.join(change_parts)}")

    col1, col2 = st.columns([1, 4])
    with col1:
        if st.button("Save Changes", type="primary"):
            with get_session() as session:
                for change in changes:
                    if change["display_name_changed"]:
                        update_account_display_name(
                            session,
                            change["account_id"],
                            change["new_display_name"],
                        )
                    if change["excluded_changed"]:
                        update_account_excluded_status(
                            session,
                            change["account_id"],
                            change["new_excluded"],
                        )
            st.success(f"Saved {len(changes)} change(s)!")
            st.rerun()

    with col2:
        if st.button("Discard"):
            st.rerun()
else:
    st.divider()
    st.caption("Edit display names above and click Save to persist changes.")
