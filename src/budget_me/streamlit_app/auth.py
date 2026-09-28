"""Authentication module for Streamlit app using Google OAuth."""

from collections.abc import Mapping
from typing import Any

import streamlit as st
from loguru import logger

from budget_me.config import get_settings

LOCAL_USER = {
    "id": "local-dev",
    "email": "dev@localhost",
    "name": "Local Dev",
}


def _get_claim(user: Any, key: str) -> Any:
    """Read a claim from Streamlit's dict-like user object."""
    if isinstance(user, Mapping):
        value = user.get(key)
        if value is not None:
            return value
    return getattr(user, key, None)


def _normalize_user(raw_user: Any) -> dict[str, str] | None:
    """Return the stable subset of OAuth claims used by the app."""
    email_claim = _get_claim(raw_user, "email")
    if not isinstance(email_claim, str) or not email_claim.strip():
        logger.warning("Authenticated user is missing an email claim")
        return None

    email = email_claim.strip()
    user_id_claim = _get_claim(raw_user, "sub") or _get_claim(raw_user, "id")
    user_id = str(user_id_claim).strip() if user_id_claim else email.casefold()
    if not user_id:
        logger.warning("Authenticated user is missing a stable identifier")
        return None

    name_claim = _get_claim(raw_user, "name")
    name = str(name_claim).strip() if name_claim else email
    return {"id": user_id, "email": email, "name": name}


def _allowed_emails(value: str | None) -> set[str]:
    """Parse a case-insensitive comma-separated email allowlist."""
    if not value:
        return set()
    return {email.strip().casefold() for email in value.split(",") if email.strip()}


def require_auth() -> dict[str, str] | None:
    """Return an app user based on the explicit authentication settings."""
    try:
        settings = get_settings()
        if not settings.auth_required:
            logger.debug("Authentication disabled by AUTH_REQUIRED")
            return dict(LOCAL_USER)

        allowed_emails = _allowed_emails(settings.auth_allowed_emails)
        if not allowed_emails:
            logger.error(
                "AUTH_ALLOWED_EMAILS is required when authentication is enabled"
            )
            return None

        raw_user = getattr(st, "user", None)
        if raw_user is None or not bool(_get_claim(raw_user, "is_logged_in")):
            return None

        user = _normalize_user(raw_user)
        if user is None:
            return None

        if user["email"].casefold() not in allowed_emails:
            logger.warning("Authenticated user is not in AUTH_ALLOWED_EMAILS")
            return None

        return user
    except Exception:
        logger.exception("Auth check failed")
        return None


def show_login_button() -> None:
    """Render Google OAuth login button.

    Uses Streamlit's native st.login() which handles the entire OAuth flow
    with persistent cookie-based sessions.

    OAuth credentials are configured in .streamlit/secrets.toml which
    reads from environment variables set in Render dashboard.
    """
    st.title("Budget Me")
    st.write("Please log in to access your budget data.")

    # Streamlit's native login button handles OAuth flow automatically
    # Credentials are loaded from .streamlit/secrets.toml
    st.login(provider="google")


def logout() -> None:
    """Sign out user and clear session."""
    st.session_state.pop("user", None)

    try:
        if hasattr(st, "logout"):
            st.logout()
    except Exception as e:
        logger.error(f"Logout failed: {e}")

    # Force rerun to show login page
    st.rerun()


def show_user_info() -> None:
    """Display current user and logout button in sidebar."""
    user = st.session_state.get("user")
    if not user:
        user = require_auth()
    if not user:
        return

    st.sidebar.write(f"Logged in as: {user['email']}")

    if st.sidebar.button("Logout"):
        logout()
