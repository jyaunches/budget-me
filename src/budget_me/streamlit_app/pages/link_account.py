"""Streamlit page for adding and repairing Plaid connections."""

import asyncio
import json
from collections.abc import Mapping
from uuid import UUID

import streamlit as st
from loguru import logger

from budget_me.config import get_settings
from budget_me.plaid.errors import PlaidError
from budget_me.plaid.link_flow import (
    create_item_relink_token,
    create_link_token,
    exchange_public_token,
    list_plaid_items_for_link,
    verify_item_relink,
)


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


def _list_plaid_items_sync() -> list[dict[str, str | None]]:
    """Load non-secret connection metadata for the Link page."""
    return asyncio.run(list_plaid_items_for_link())


def _create_item_relink_token_sync(
    plaid_item_id: str,
    user_id: str,
    redirect_uri: str | None,
) -> str:
    """Create an existing-Item update token from Streamlit."""
    return asyncio.run(
        create_item_relink_token(
            plaid_item_id=UUID(plaid_item_id),
            user_id=user_id,
            redirect_uri=redirect_uri,
        )
    )


def _verify_item_relink_sync(plaid_item_id: str) -> dict[str, str | None]:
    """Verify a completed update-mode session from Streamlit."""
    return asyncio.run(verify_item_relink(UUID(plaid_item_id)))


def _javascript_value(value: str) -> str:
    """Encode untrusted text for a JavaScript literal inside an HTML script."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace("\u2028", "\\u2028")
        .replace("\u2029", "\\u2029")
    )


def get_plaid_link_html(
    link_token: str,
    redirect_uri: str | None,
    is_oauth_resume: bool = False,
    mode: str = "new",
) -> str:
    """Generate a visible, user-initiated Plaid Link launcher.

    Browsers commonly block Link when it is opened automatically from a
    Streamlit component iframe. This launcher waits for Plaid's onLoad
    callback, enables a real button inside the iframe, and reports script,
    initialization, and launch failures instead of spinning indefinitely.

    New connections expose an explicit final navigation after onSuccess so the
    public token can be exchanged by Streamlit. Update mode does not exchange a
    public token; the surrounding page verifies the existing Item directly.
    """
    if not link_token or not link_token.strip():
        raise ValueError("link_token cannot be empty")
    if is_oauth_resume and not redirect_uri:
        raise ValueError("redirect_uri required for OAuth resume")
    if mode not in {"new", "relink"}:
        raise ValueError("mode must be 'new' or 'relink'")

    oauth_config = ""
    if is_oauth_resume and redirect_uri:
        oauth_config = f"receivedRedirectUri: {_javascript_value(redirect_uri)},"

    if mode == "relink":
        button_label = "Reconnect account"
        success_handler = """
                    openButton.hidden = true;
                    statusEl.className = "success";
                    statusEl.textContent =
                        "Reconnection completed. Click Verify Reconnection below.";
        """
    else:
        button_label = "Open Plaid Link"
        success_handler = """
                    try {
                        if (!document.referrer) {
                            throw new Error("The Streamlit page URL is unavailable.");
                        }
                        const callbackUrl = new URL(document.referrer);
                        callbackUrl.search = "";
                        callbackUrl.hash = "";
                        callbackUrl.searchParams.set("public_token", public_token);
                        callbackUrl.searchParams.set("link_success", "true");
                        finishLink.href = callbackUrl.toString();
                        finishLink.hidden = false;
                        openButton.hidden = true;
                        statusEl.className = "success";
                        statusEl.textContent =
                            "Connection completed. Click Finish Connection to save it.";
                    } catch (error) {
                        showError(
                            "Connection completed, but Budget Me could not build " +
                            "the return link. Reload the page and try again."
                        );
                    }
        """

    return f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8">
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {{
                font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                min-height: 220px;
                margin: 0;
                background: transparent;
            }}
            #status {{
                max-width: 520px;
                padding: 12px;
                text-align: center;
                color: #555;
            }}
            button, .finish-link {{
                border: 0;
                border-radius: 6px;
                padding: 12px 20px;
                background: #1677ff;
                color: white;
                cursor: pointer;
                font-size: 16px;
                font-weight: 600;
                text-decoration: none;
            }}
            button:disabled {{
                background: #9aa4b2;
                cursor: wait;
            }}
            .success {{ color: #137333 !important; font-weight: 600; }}
            .error {{ color: #b3261e !important; font-weight: 600; }}
        </style>
    </head>
    <body>
        <div id="status">Loading the secure Plaid connection…</div>
        <button id="open-plaid" disabled>{button_label}</button>
        <a id="finish-link" class="finish-link" target="_top" hidden>
            Finish Connection
        </a>

        <script>
            const linkToken = {_javascript_value(link_token)};
            const statusEl = document.getElementById("status");
            const openButton = document.getElementById("open-plaid");
            const finishLink = document.getElementById("finish-link");
            let handler = null;
            let ready = false;

            function showError(message) {{
                statusEl.className = "error";
                statusEl.textContent = message;
                openButton.disabled = true;
            }}

            const loadTimeout = window.setTimeout(function() {{
                if (!ready) {{
                    showError(
                        "Plaid Link did not load. Check this browser's content " +
                        "blocking settings, then reload and try again."
                    );
                }}
            }}, 15000);

            function initializePlaid() {{
                if (!window.Plaid) {{
                    showError("The Plaid Link library did not become available.");
                    return;
                }}

                try {{
                    handler = window.Plaid.create({{
                        token: linkToken,
                        {oauth_config}
                        onSuccess: function(public_token, metadata) {{
                            {success_handler}
                        }},
                        onExit: function(err, metadata) {{
                            if (err) {{
                                console.error("Plaid Link error", err);
                                showError(
                                    "Plaid reported an error. Reload the page and try again."
                                );
                                return;
                            }}
                            statusEl.className = "";
                            statusEl.textContent =
                                "Connection cancelled. You can open Plaid again.";
                            openButton.disabled = false;
                        }},
                        onLoad: function() {{
                            window.clearTimeout(loadTimeout);
                            ready = true;
                            statusEl.className = "";
                            statusEl.textContent =
                                "Plaid Link is ready. Continue when you are ready.";
                            openButton.disabled = false;
                        }},
                    }});
                }} catch (error) {{
                    console.error("Plaid Link initialization failed", error);
                    showError(
                        "Plaid Link could not be initialized. Reload the page and try again."
                    );
                }}
            }}

            function plaidScriptFailed() {{
                window.clearTimeout(loadTimeout);
                showError(
                    "The Plaid Link script could not be downloaded. Check this " +
                    "browser's content blocking or network settings and try again."
                );
            }}

            openButton.addEventListener("click", function() {{
                if (!ready || !handler) {{
                    showError("Plaid Link is not ready. Reload the page and try again.");
                    return;
                }}
                openButton.disabled = true;
                statusEl.className = "";
                statusEl.textContent = "Opening Plaid Link…";
                try {{
                    handler.open();
                }} catch (error) {{
                    console.error("Plaid Link launch failed", error);
                    showError(
                        "Plaid Link could not be opened. Reload the page and try again."
                    );
                }}
            }});
        </script>
        <script
            src="https://cdn.plaid.com/link/v2/stable/link-initialize.js"
            onload="initializePlaid()"
            onerror="plaidScriptFailed()"
        ></script>
    </body>
    </html>
    """


st.title("Link Bank Account")
st.write(
    "Connect a new institution or repair an existing Plaid connection. "
    "Credentials are entered only in Plaid Link."
)

settings = get_settings()
oauth_state_id = st.query_params.get("oauth_state_id")
public_token = st.query_params.get("public_token")
link_success = st.query_params.get("link_success")

if "token_exchanged" not in st.session_state:
    st.session_state.token_exchanged = False

flash_message = st.session_state.pop("plaid_link_flash", None)
if flash_message:
    st.success(flash_message)

if public_token and link_success == "true" and not st.session_state.token_exchanged:
    st.info("Saving the new connection…")
    try:
        user = st.session_state.get("user")
        if not user:
            st.error("Authentication required. Please log in.")
            st.stop()

        _exchange_public_token_sync(
            public_token=public_token,
            user_id=_get_session_user_id(user),
        )
        st.session_state.token_exchanged = True
        st.session_state.pop("plaid_link_session", None)
        st.query_params.clear()
        st.success("Successfully linked the institution.")
        st.write("Accounts will appear after the next transaction sync.")
    except PlaidError as e:
        st.error(f"Failed to save the connection: {e}")
        logger.error("Plaid token exchange failed")
        st.session_state.token_exchanged = False
    except Exception:
        st.error("Budget Me could not save the connection. Please try again.")
        logger.exception("Unexpected Plaid token exchange failure")
        st.session_state.token_exchanged = False

elif oauth_state_id:
    link_session = st.session_state.get("plaid_link_session")
    if not settings.plaid_redirect_uri:
        st.error("OAuth cannot resume because PLAID_REDIRECT_URI is not configured.")
    elif not link_session:
        st.error("The Plaid session expired. Start the connection again.")
    else:
        st.info("Continue the secure connection after returning from your bank.")
        plaid_html = get_plaid_link_html(
            link_token=link_session["link_token"],
            redirect_uri=settings.plaid_redirect_uri,
            is_oauth_resume=True,
            mode=link_session["mode"],
        )
        st.components.v1.html(plaid_html, height=300, scrolling=False)

else:
    st.session_state.token_exchanged = False

    st.subheader("Repair an existing connection")
    st.write(
        "Use update mode for a connection marked as requiring login. "
        "This keeps the existing accounts and transaction history."
    )

    if st.button("Check Connection Status", use_container_width=True):
        try:
            st.session_state["plaid_link_items"] = _list_plaid_items_sync()
        except Exception:
            st.error("Budget Me could not load the connection list.")
            logger.exception("Failed to list Plaid Items for Link page")

    link_items = st.session_state.get("plaid_link_items", [])
    relink_items = [
        item for item in link_items if item.get("status") == "relink_required"
    ]

    if link_items and not relink_items:
        st.success("No connections currently require reauthentication.")

    for item in relink_items:
        institution = item.get("institution_name") or "Connected institution"
        error_code = item.get("last_error_code") or "login required"
        st.warning(f"{institution}: {error_code}")
        if st.button(
            f"Reconnect {institution}",
            key=f"relink-{item['id']}",
            use_container_width=True,
        ):
            try:
                user = st.session_state.get("user")
                if not user:
                    st.error("Authentication required. Please log in.")
                    st.stop()
                token = _create_item_relink_token_sync(
                    plaid_item_id=item["id"],
                    user_id=_get_session_user_id(user),
                    redirect_uri=settings.plaid_redirect_uri,
                )
                st.session_state["plaid_link_session"] = {
                    "mode": "relink",
                    "item_id": item["id"],
                    "institution_name": institution,
                    "link_token": token,
                }
            except PlaidError as e:
                st.error(f"Failed to start reconnection: {e}")
                logger.error("Failed to create Plaid update-mode token")
            except Exception:
                st.error("Budget Me could not start the reconnection.")
                logger.exception("Unexpected Plaid relink-token failure")

    st.divider()
    st.subheader("Connect a new institution")
    st.write("Use this only when the institution is not already connected.")

    if st.button(
        "Connect New Bank Account",
        type="primary",
        use_container_width=True,
    ):
        try:
            user = st.session_state.get("user")
            if not user:
                st.error("Authentication required. Please log in.")
                st.stop()
            token = create_link_token(
                user_id=_get_session_user_id(user),
                redirect_uri=settings.plaid_redirect_uri,
            )
            st.session_state["plaid_link_session"] = {
                "mode": "new",
                "link_token": token,
            }
        except PlaidError as e:
            st.error(f"Failed to start Plaid Link: {e}")
            logger.error("Failed to create Plaid link token")
        except Exception:
            st.error("Budget Me could not start Plaid Link.")
            logger.exception("Unexpected Plaid link-token failure")

    link_session = st.session_state.get("plaid_link_session")
    if link_session:
        st.divider()
        mode = link_session["mode"]
        title = (
            f"Reconnect {link_session['institution_name']}"
            if mode == "relink"
            else "Connect a new institution"
        )
        st.subheader(title)
        plaid_html = get_plaid_link_html(
            link_token=link_session["link_token"],
            redirect_uri=settings.plaid_redirect_uri,
            mode=mode,
        )
        st.components.v1.html(plaid_html, height=300, scrolling=False)

        if mode == "relink":
            st.caption(
                "After Plaid reports success, verify the repaired connection here."
            )
            if st.button(
                "Verify Reconnection",
                type="primary",
                use_container_width=True,
            ):
                try:
                    result = _verify_item_relink_sync(link_session["item_id"])
                    institution = (
                        result.get("institution_name")
                        or link_session["institution_name"]
                    )
                    st.session_state.pop("plaid_link_session", None)
                    st.session_state.pop("plaid_link_items", None)
                    st.session_state["plaid_link_flash"] = (
                        f"{institution} was reconnected and its balances refreshed."
                    )
                    st.rerun()
                except PlaidError as e:
                    st.error(
                        "Plaid has not confirmed the reconnection yet. "
                        f"Complete Link and try Verify again: {e}"
                    )
                except Exception:
                    st.error("Budget Me could not verify the reconnection.")
                    logger.exception("Unexpected Plaid relink verification failure")

        if st.button("Cancel Link Session", use_container_width=True):
            st.session_state.pop("plaid_link_session", None)
            st.rerun()

    if not settings.plaid_redirect_uri:
        st.caption(
            "OAuth institutions require an HTTPS PLAID_REDIRECT_URI that is also "
            "allowed in the Plaid dashboard. Non-OAuth Link flows can still run."
        )

st.divider()
if st.button("Go to Accounts"):
    st.switch_page("pages/accounts.py")
