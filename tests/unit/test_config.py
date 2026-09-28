"""Tests for configuration module."""

import importlib.util
import json
import os
from pathlib import Path

import pytest
from pydantic import ValidationError


class TestConfig:
    """Tests for Settings configuration."""

    def test_config_loads_from_env(self, monkeypatch):
        """Config object loads values from environment variables."""
        monkeypatch.setenv(
            "DATABASE_URL_DEV", "postgresql+asyncpg://user:pass@dev:5432/db"
        )
        monkeypatch.setenv(
            "DATABASE_URL_PROD", "postgresql+asyncpg://user:pass@prod:5432/db"
        )
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key-32-bytes-long-for-fernet")
        monkeypatch.setenv("ENVIRONMENT", "production")
        monkeypatch.setenv("LOG_LEVEL", "DEBUG")

        # Clear cache to force reload
        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        assert settings.database_url_dev == "postgresql+asyncpg://user:pass@dev:5432/db"
        assert (
            settings.database_url_prod == "postgresql+asyncpg://user:pass@prod:5432/db"
        )
        assert settings.app_token_enc_key == "test-key-32-bytes-long-for-fernet"
        assert settings.environment == "production"
        assert settings.log_level == "DEBUG"

    def test_config_selects_prod_database_when_production(self, monkeypatch):
        """database_url returns prod URL when ENVIRONMENT=production."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql://user:pass@dev:5432/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql://user:pass@prod:5432/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("ENVIRONMENT", "production")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        # Should use prod URL and normalize to asyncpg
        assert "prod" in settings.active_database_url
        assert "asyncpg" in settings.active_database_url

    def test_config_selects_dev_database_when_development(self, monkeypatch):
        """database_url returns dev URL when ENVIRONMENT=development."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql://user:pass@dev:5432/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql://user:pass@prod:5432/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("ENVIRONMENT", "development")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        # Should use dev URL and normalize to asyncpg
        assert "dev" in settings.active_database_url
        assert "asyncpg" in settings.active_database_url

    def test_config_normalizes_postgres_url(self, monkeypatch):
        """database_url normalizes postgres:// to postgresql+asyncpg://."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgres://user:pass@dev:5432/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgres://user:pass@prod:5432/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("ENVIRONMENT", "development")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        assert settings.active_database_url.startswith("postgresql+asyncpg://")

    def test_config_validates_database_url_format(self, monkeypatch):
        """Invalid DATABASE_URL format raises ValidationError."""
        monkeypatch.setenv("DATABASE_URL_DEV", "invalid://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "Database URL must start with" in str(exc_info.value)

    def test_config_validates_encryption_key_present(self, monkeypatch):
        """Missing APP_TOKEN_ENC_KEY raises ValidationError."""
        monkeypatch.delenv("APP_TOKEN_ENC_KEY", raising=False)
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        # Create settings without reading .env file to ensure we test just env vars
        with pytest.raises(ValidationError) as exc_info:
            Settings(_env_file=None)

        # Check that the error mentions the missing field
        error_str = str(exc_info.value)
        assert "app_token_enc_key" in error_str.lower()

    def test_unit_test_mode_does_not_load_private_dotenv(self, monkeypatch, tmp_path):
        """Test bootstrap ignores a checkout's private dotenv file."""
        monkeypatch.chdir(tmp_path)
        (tmp_path / ".env").write_text(
            "APP_TOKEN_ENC_KEY=must-not-load\n"
            "DATABASE_URL=postgresql://private:secret@example.test/private\n",
            encoding="utf-8",
        )
        monkeypatch.delenv("APP_TOKEN_ENC_KEY", raising=False)

        from budget_me.config import Settings

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "app_token_enc_key" in str(exc_info.value).lower()

    def test_unit_bootstrap_scrubs_inherited_database_targets(self, monkeypatch):
        """Unit startup removes exported database targets before app imports."""
        database_variables = (
            "DATABASE_URL",
            "DATABASE_URL_DEV",
            "DATABASE_URL_PROD",
        )
        for variable in database_variables:
            monkeypatch.setenv(
                variable,
                f"postgresql://private:secret@example.test/{variable.lower()}",
            )
        monkeypatch.delenv("BUDGET_ME_ALLOW_INTEGRATION_TESTS", raising=False)

        conftest_path = Path(__file__).parents[1] / "conftest.py"
        spec = importlib.util.spec_from_file_location(
            "isolated_unit_test_bootstrap", conftest_path
        )
        assert spec is not None and spec.loader is not None
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert all(variable not in os.environ for variable in database_variables)

        from budget_me.config import Settings

        settings = Settings()
        assert settings.database_url is None
        assert settings.database_url_dev is None
        assert settings.database_url_prod is None
        with pytest.raises(ValueError, match="must be set"):
            _ = settings.active_database_url

    def test_config_defaults(self, monkeypatch):
        """Config uses correct defaults for optional fields."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.delenv("ENVIRONMENT", raising=False)
        monkeypatch.delenv("LOG_LEVEL", raising=False)

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        assert settings.environment == "development"
        assert settings.log_level == "INFO"

    def test_config_validates_log_level(self, monkeypatch):
        """Invalid LOG_LEVEL raises ValidationError."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("LOG_LEVEL", "INVALID")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "LOG_LEVEL must be one of" in str(exc_info.value)


class TestLogging:
    """Tests for logging configuration."""

    def test_logger_outputs_json_format(self, capsys):
        """Log output is valid JSON with required fields."""
        from budget_me.logging import get_logger, setup_logging

        # Setup JSON logging
        setup_logging(log_level="DEBUG", json_output=True)

        log = get_logger("test")
        log.info("Test message")

        # Capture stdout
        captured = capsys.readouterr()
        log_line = captured.out.strip()

        # Parse as JSON
        log_data = json.loads(log_line)

        # Verify required fields
        assert "timestamp" in log_data
        assert log_data["level"] == "INFO"
        assert log_data["message"] == "Test message"

    def test_logger_includes_context_fields(self, capsys):
        """Log output includes extra context fields."""
        from loguru import logger

        from budget_me.logging import setup_logging

        # Setup JSON logging
        setup_logging(log_level="DEBUG", json_output=True)

        # Bind context and log
        log = logger.bind(item_id="item_123", user_key="user_456")
        log.info("Processing item")

        # Capture stdout
        captured = capsys.readouterr()
        log_line = captured.out.strip()

        log_data = json.loads(log_line)

        assert log_data["item_id"] == "item_123"
        assert log_data["user_key"] == "user_456"
        assert log_data["message"] == "Processing item"

    def test_setup_logging_json_mode(self):
        """setup_logging configures JSON output."""
        from budget_me.logging import setup_logging

        # Should not raise
        setup_logging(log_level="DEBUG", json_output=True)

    def test_setup_logging_standard_mode(self):
        """setup_logging configures standard output for development."""
        from budget_me.logging import setup_logging

        # Should not raise
        setup_logging(log_level="INFO", json_output=False)


class TestPlaidConfig:
    """Tests for Plaid configuration in Settings."""

    def test_plaid_config_loads_credentials(self, monkeypatch):
        """Config object loads Plaid credentials from environment variables."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "sandbox")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        settings = Settings()

        assert settings.plaid_client_id == "test-client-id"
        assert settings.plaid_secret == "test-secret"
        assert settings.plaid_env == "sandbox"

    def test_plaid_config_validates_env(self, monkeypatch):
        """Invalid PLAID_ENV raises ValidationError."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.setenv("PLAID_ENV", "invalid")

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        with pytest.raises(ValidationError) as exc_info:
            Settings()

        assert "plaid_env" in str(exc_info.value).lower()

    def test_plaid_config_defaults_to_sandbox(self, monkeypatch):
        """PLAID_ENV defaults to sandbox when not set."""
        monkeypatch.setenv("DATABASE_URL_DEV", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("DATABASE_URL_PROD", "postgresql+asyncpg://localhost/db")
        monkeypatch.setenv("APP_TOKEN_ENC_KEY", "test-key")
        monkeypatch.setenv("PLAID_CLIENT_ID", "test-client-id")
        monkeypatch.setenv("PLAID_SECRET", "test-secret")
        monkeypatch.delenv("PLAID_ENV", raising=False)

        from budget_me.config import Settings, get_settings

        get_settings.cache_clear()

        # Use _env_file=None to prevent loading from .env file
        settings = Settings(_env_file=None)

        assert settings.plaid_env == "sandbox"
