"""Streamlit app entry point with multi-page navigation."""

import streamlit as st

from budget_me.streamlit_app.auth import require_auth, show_login_button, show_user_info

# MUST be called first (Streamlit requirement)
st.set_page_config(
    page_title="Budget Me",
    page_icon="💰",
    layout="wide",
)

# Check authentication
user = require_auth()

if not user:
    st.session_state.pop("user", None)
    # User not authenticated - show login
    show_login_button()
    st.stop()  # Prevent rest of app from rendering

# User is authenticated - show app
st.session_state["user"] = user

with st.sidebar:
    show_user_info()

pg = st.navigation(
    [
        st.Page("pages/link_account.py", title="Link Account", icon="🔗"),
        st.Page("pages/monthly_snapshot.py", title="Monthly Snapshot", icon="📊"),
        st.Page("pages/yearly_forecast.py", title="Yearly Forecast", icon="📈"),
        st.Page("pages/budget.py", title="Budget", icon="🎯"),
        st.Page("pages/transactions.py", title="Transactions", icon="💳"),
        st.Page("pages/accounts.py", title="Accounts", icon="🏦"),
        st.Page("pages/credit_cards.py", title="Credit Cards", icon="💳"),
        st.Page("pages/debt.py", title="Debt", icon="💳"),
    ]
)
pg.run()
