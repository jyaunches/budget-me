"""Tests for explicit authentication settings."""

from budget_me.config import Settings


def test_auth_settings_default_to_disabled(monkeypatch):
    monkeypatch.delenv("AUTH_REQUIRED", raising=False)
    monkeypatch.delenv("AUTH_ALLOWED_EMAILS", raising=False)

    settings = Settings(
        _env_file=None,
        app_token_enc_key="test-key",
    )

    assert settings.auth_required is False
    assert settings.auth_allowed_emails is None


def test_auth_settings_load_from_environment(monkeypatch):
    monkeypatch.setenv("AUTH_REQUIRED", "true")
    monkeypatch.setenv(
        "AUTH_ALLOWED_EMAILS",
        "owner@example.com,partner@example.com",
    )

    settings = Settings(
        _env_file=None,
        app_token_enc_key="test-key",
    )

    assert settings.auth_required is True
    assert settings.auth_allowed_emails == "owner@example.com,partner@example.com"
