"""Streamlit page for linking bank accounts via Plaid Link."""

import asyncio
from collections.abc import Mapping

import streamlit as st
from loguru import logger

from budget_me.config import get_settings
from budget_me.plaid.errors import PlaidError
from budget_me.plaid.link_flow import create_link_token, exchange_public_token


def _get_session_user_id(user: object) -> str:
    """Return a non-empty stable identifier from the authenticated session user."""
    if not isinstance(user, Mapping):
        raise ValueError("Authenticated user is missing from the session")

    for claim in ("id", "sub", "email"):
        value = user.get(claim)
        if value is not None:
            user_id = str(value).strip()
            if user_id:
                return user_id

    raise ValueError("Authenticated user has no stable identifier")


def _exchange_public_token_sync(public_token: str, user_id: str) -> dict:
    """Run Plaid's async token exchange from Streamlit's synchronous script."""
    exchange = exchange_public_token(public_token=public_token, user_id=user_id)
    return asyncio.run(exchange)


def get_plaid_link_html(
    link_token: str, redirect_uri: str | None, is_oauth_resume: bool = False
) -> str:
    """Generate HTML with embedded Plaid Link JavaScript using popup mode.

    Uses window.open() to launch Plaid Link in a popup window, avoiding
    iframe sandboxing issues with Streamlit's st.components.v1.html().

    Args:
        link_token: Plaid link token for initializing Link
        redirect_uri: OAuth redirect URI (required for OAuth resume)
        is_oauth_resume: Whether this is resuming an OAuth flow

    Returns:
        HTML string with embedded Plaid Link script

    Raises:
        ValueError: If link_token is empty or OAuth resume without redirect_uri
    """
    if not link_token or not link_token.strip():
        raise ValueError("link_token cannot be empty")

    if is_oauth_resume and not redirect_uri:
        raise ValueError("redirect_uri required for OAuth resume")

    # Build Plaid Link handler configuration
    oauth_config = ""
    if is_oauth_resume and redirect_uri:
        oauth_config = f'receivedRedirectUri: "{redirect_uri}",'

    # Get the parent window's origin for redirecting after success
    # We use top.location to get the actual Streamlit app URL
    html = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"></script>
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                height: 100vh;
                margin: 0;
                background: transparent;
            }}
            #status {{
                padding: 20px;
                text-align: center;
                color: #333;
            }}
            .success {{
                color: #28a745;
                font-weight: bold;
            }}
            .error {{
                color: #dc3545;
            }}
            .loading {{
                color: #666;
            }}
        </style>
    </head>
    <body>
        <div id="status" class="loading">Opening Plaid Link...</div>

        <script>
            const statusEl = document.getElementById('status');

            const handler = Plaid.create({{
                token: "{link_token}",
                {oauth_config}
                onSuccess: function(public_token, metadata) {{
                    statusEl.className = 'success';
                    statusEl.innerHTML = 'Connection successful! Redirecting...';

                    // Redirect the top-level window (Streamlit app) with the token
                    const baseUrl = window.top.location.origin + window.top.location.pathname;
                    window.top.location.href = baseUrl + "?public_token=" + public_token + "&link_success=true";
                }},
                onExit: function(err, metadata) {{
                    if (err) {{
                        console.error('Plaid Link error:', err);
                        statusEl.className = 'error';
                        statusEl.innerHTML = 'Connection cancelled or failed. Please try again.';
                    }} else {{
                        statusEl.className = '';
                        statusEl.innerHTML = 'Connection cancelled. Click "Connect Bank Account" to try again.';
                    }}
                }},
                onLoad: function() {{
                    statusEl.innerHTML = 'Plaid Link ready. Please complete the connection in the popup.';
                }},
            }});

            // Open Plaid Link immediately
            handler.open();
        </script>
    </body>
    </html>
    """

    return html


# Main page logic
st.title("Link Bank Account")

st.write(
    "Connect your bank account to Budget Me using Plaid Link. "
    "This will allow you to sync transactions and account balances."
)

# Get settings for OAuth redirect URI
settings = get_settings()

# Check for query parameters (OAuth callback or success callback)
oauth_state_id = st.query_params.get("oauth_state_id")
public_token = st.query_params.get("public_token")
link_success = st.query_params.get("link_success")

# Initialize session state for tracking token exchange
if "token_exchanged" not in st.session_state:
    st.session_state.token_exchanged = False

# Handle public token exchange (success callback)
if public_token and link_success == "true" and not st.session_state.token_exchanged:
    st.info("Exchanging token and saving connection...")

    try:
        # Get user ID from session state (set by auth middleware)
        user = st.session_state.get("user")
        if not user:
            st.error("Authentication required. Please log in.")
            st.stop()

        user_id = _get_session_user_id(user)

        # Exchange public token for access token
        result = _exchange_public_token_sync(public_token=public_token, user_id=user_id)

        st.session_state.token_exchanged = True

        # Clear query params to prevent re-processing
        st.query_params.clear()

        st.success(
            f"Successfully linked bank account! Item ID: {result['plaid_item_id']}"
        )
        st.write("Your accounts will appear in the Accounts page after the next sync.")

        if st.button("View Accounts"):
            st.switch_page("pages/accounts.py")

    except PlaidError as e:
        st.error(f"Failed to link account: {e}")
        logger.error(f"Token exchange failed: {e}")
        st.session_state.token_exchanged = False
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        logger.error(f"Unexpected error during token exchange: {e}")
        st.session_state.token_exchanged = False

# Handle OAuth resume flow
elif oauth_state_id:
    st.info("Resuming OAuth flow...")

    try:
        # Get user ID from session state
        user = st.session_state.get("user")
        if not user:
            st.error("Authentication required. Please log in.")
            st.stop()

        user_id = _get_session_user_id(user)

        # Create new link token with receivedRedirectUri
        # The current URL is the redirect URI
        current_url = st.query_params.get("oauth_state_id")  # Full URL from OAuth
        redirect_uri = settings.plaid_redirect_uri

        if not redirect_uri:
            st.error(
                "OAuth redirect URI not configured. Set PLAID_REDIRECT_URI environment variable."
            )
            st.stop()

        # Create link token for OAuth resume
        link_token = create_link_token(user_id=user_id, redirect_uri=redirect_uri)

        # Generate HTML with OAuth resume configuration
        plaid_html = get_plaid_link_html(
            link_token=link_token, redirect_uri=redirect_uri, is_oauth_resume=True
        )

        # Embed Plaid Link with auto-open
        st.components.v1.html(plaid_html, height=600, scrolling=True)

    except PlaidError as e:
        st.error(f"Failed to resume OAuth flow: {e}")
        logger.error(f"OAuth resume failed: {e}")
    except Exception as e:
        st.error(f"Unexpected error: {e}")
        logger.error(f"Unexpected error during OAuth resume: {e}")

# Initial state - show Connect button
else:
    # Reset token exchange state when returning to initial state
    st.session_state.token_exchanged = False

    st.write("Click the button below to securely connect your bank account.")

    if st.button("Connect Bank Account", type="primary", use_container_width=True):
        try:
            # Get user ID from session state
            user = st.session_state.get("user")
            if not user:
                st.error("Authentication required. Please log in.")
                st.stop()

            user_id = _get_session_user_id(user)

            # Create link token with optional redirect URI
            link_token = create_link_token(
                user_id=user_id, redirect_uri=settings.plaid_redirect_uri
            )

            # Generate HTML with embedded Plaid Link
            plaid_html = get_plaid_link_html(
                link_token=link_token,
                redirect_uri=settings.plaid_redirect_uri,
                is_oauth_resume=False,
            )

            # Embed Plaid Link with auto-open
            st.components.v1.html(plaid_html, height=600, scrolling=True)

        except PlaidError as e:
            st.error(f"Failed to create link token: {e}")
            logger.error(f"Link token creation failed: {e}")
        except Exception as e:
            st.error(f"Unexpected error: {e}")
            logger.error(f"Unexpected error during link token creation: {e}")

# Show existing connections
st.divider()
st.subheader("Connected Accounts")
st.write("View your connected accounts on the Accounts page.")

if st.button("Go to Accounts"):
    st.switch_page("pages/accounts.py")
