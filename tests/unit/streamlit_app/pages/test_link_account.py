"""Tests for Link Account Streamlit page."""

import pytest


class TestPlaidLinkHTML:
    """Tests for Plaid Link HTML generation."""

    def test_get_plaid_link_html_includes_link_token(self):
        """get_plaid_link_html includes link token in generated HTML."""
        from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

        html = get_plaid_link_html(
            link_token="link-sandbox-test-token", redirect_uri=None
        )

        assert "link-sandbox-test-token" in html
        assert "script" in html.lower()

    def test_get_plaid_link_html_oauth_resume(self):
        """get_plaid_link_html includes receivedRedirectUri for OAuth resume."""
        from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

        html = get_plaid_link_html(
            link_token="link-sandbox-test-token",
            redirect_uri="https://example.com",
            is_oauth_resume=True,
        )

        assert "link-sandbox-test-token" in html
        assert "https://example.com" in html
        # Check for receivedRedirectUri configuration
        assert "receivedRedirectUri" in html

    def test_get_plaid_link_html_success_redirect(self):
        """get_plaid_link_html includes onSuccess callback with public_token redirect."""
        from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

        html = get_plaid_link_html(
            link_token="link-sandbox-test-token", redirect_uri=None
        )

        # Verify onSuccess callback is present
        assert "onSuccess" in html
        # Verify redirect includes public_token param
        assert "public_token" in html
        assert 'searchParams.set("link_success", "true")' in html

    def test_get_plaid_link_html_empty_token_raises_error(self):
        """get_plaid_link_html raises error for empty link token."""
        from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

        with pytest.raises(ValueError, match="link_token cannot be empty"):
            get_plaid_link_html(link_token="", redirect_uri=None)

    def test_get_plaid_link_html_oauth_resume_without_redirect_raises_error(self):
        """get_plaid_link_html raises error for OAuth resume without redirect_uri."""
        from budget_me.streamlit_app.pages.link_account import get_plaid_link_html

        with pytest.raises(ValueError, match="redirect_uri required for OAuth resume"):
            get_plaid_link_html(
                link_token="link-sandbox-test-token",
                redirect_uri=None,
                is_oauth_resume=True,
            )


class TestSessionUserId:
    """Tests for stable Plaid user identifiers from auth session state."""

    @pytest.mark.parametrize(
        ("user", "expected"),
        [
            ({"id": "oauth-subject"}, "oauth-subject"),
            ({"id": "", "sub": "fallback-subject"}, "fallback-subject"),
            ({"email": "owner@example.com"}, "owner@example.com"),
        ],
    )
    def test_get_session_user_id_uses_first_nonempty_stable_claim(self, user, expected):
        from budget_me.streamlit_app.pages.link_account import _get_session_user_id

        assert _get_session_user_id(user) == expected

    @pytest.mark.parametrize("user", [None, {}, {"id": " "}])
    def test_get_session_user_id_rejects_missing_identifier(self, user):
        from budget_me.streamlit_app.pages.link_account import _get_session_user_id

        with pytest.raises(ValueError, match="stable identifier|missing from"):
            _get_session_user_id(user)


class TestTokenExchangeBridge:
    """Tests for awaiting Plaid's async token exchange from Streamlit."""

    def test_exchange_public_token_sync_awaits_exchange(self, monkeypatch):
        from budget_me.streamlit_app.pages import link_account

        calls = []

        async def fake_exchange_public_token(*, public_token, user_id):
            calls.append((public_token, user_id))
            return {"plaid_item_id": "item-123"}

        monkeypatch.setattr(
            link_account,
            "exchange_public_token",
            fake_exchange_public_token,
        )

        result = link_account._exchange_public_token_sync(
            public_token="public-token",
            user_id="oauth-subject",
        )

        assert result == {"plaid_item_id": "item-123"}
        assert calls == [("public-token", "oauth-subject")]
