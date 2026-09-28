"""Focused tests for the Streamlit authentication contract."""

from types import SimpleNamespace

import pytest

from budget_me.streamlit_app import auth


def _set_auth_context(monkeypatch, *, required, allowed_emails=None, user=None):
    settings = SimpleNamespace(
        auth_required=required,
        auth_allowed_emails=allowed_emails,
    )
    monkeypatch.setattr(auth, "get_settings", lambda: settings)
    monkeypatch.setattr(auth, "st", SimpleNamespace(user=user))


def test_auth_disabled_returns_stable_local_user(monkeypatch):
    _set_auth_context(monkeypatch, required=False)

    assert auth.require_auth() == {
        "id": "local-dev",
        "email": "dev@localhost",
        "name": "Local Dev",
    }


def test_auth_required_rejects_logged_out_user(monkeypatch):
    _set_auth_context(
        monkeypatch,
        required=True,
        user={"is_logged_in": False},
    )

    assert auth.require_auth() is None


def test_auth_required_normalizes_allowed_oauth_user(monkeypatch):
    _set_auth_context(
        monkeypatch,
        required=True,
        allowed_emails="other@example.com, owner@example.com",
        user={
            "is_logged_in": True,
            "sub": "google-subject-123",
            "email": "Owner@Example.com",
            "name": "Budget Owner",
        },
    )

    assert auth.require_auth() == {
        "id": "google-subject-123",
        "email": "Owner@Example.com",
        "name": "Budget Owner",
    }


@pytest.mark.parametrize("allowed_emails", [None, "", " , "])
def test_auth_required_rejects_empty_or_missing_allowlist(monkeypatch, allowed_emails):
    _set_auth_context(
        monkeypatch,
        required=True,
        allowed_emails=allowed_emails,
        user={
            "is_logged_in": True,
            "email": "Owner@Example.com",
        },
    )

    assert auth.require_auth() is None


def test_nonempty_allowlist_rejects_unlisted_email(monkeypatch):
    _set_auth_context(
        monkeypatch,
        required=True,
        allowed_emails="owner@example.com",
        user={
            "is_logged_in": True,
            "sub": "google-subject-456",
            "email": "someone-else@example.com",
        },
    )

    assert auth.require_auth() is None
