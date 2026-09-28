"""Application configuration using Pydantic Settings."""

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field, computed_field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=(
            None if os.environ.get("BUDGET_ME_DISABLE_DOTENV") == "1" else ".env"
        ),
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Environment
    environment: Literal["development", "production"] = Field(
        default="development",
        description="Application environment - determines which database to use",
    )

    # Database URL - supports two patterns:
    # 1. GitHub Environments: Single DATABASE_URL from environment secrets
    # 2. Local .env: Separate DATABASE_URL_DEV and DATABASE_URL_PROD
    database_url: str | None = Field(
        default=None,
        description="PostgreSQL connection string (GitHub Environments pattern)",
    )
    database_url_dev: str | None = Field(
        default=None,
        description="PostgreSQL connection string for development (Budget Me Dev)",
    )
    database_url_prod: str | None = Field(
        default=None,
        description="PostgreSQL connection string for production (Budget Me)",
    )

    # Encryption
    app_token_enc_key: str = Field(
        ...,
        description="Base64-encoded 32-byte Fernet key for token encryption",
    )

    # Logging
    log_level: str = Field(
        default="INFO",
        description="Logging level (DEBUG, INFO, WARNING, ERROR, CRITICAL)",
    )

    # Authentication
    auth_required: bool = Field(
        default=False,
        description="Require users to authenticate with Streamlit OAuth",
    )
    auth_allowed_emails: str | None = Field(
        default=None,
        description=(
            "Comma-separated email allowlist. A non-empty value is required "
            "when AUTH_REQUIRED is true."
        ),
    )

    # Plaid Configuration
    plaid_client_id: str = Field(
        default="",
        description="Plaid API client ID",
    )
    plaid_secret: str = Field(
        default="",
        description="Plaid API secret",
    )
    plaid_env: Literal["sandbox", "production"] = Field(
        default="sandbox",
        description="Plaid environment - sandbox or production",
    )
    plaid_redirect_uri: str | None = Field(
        default=None,
        description="OAuth redirect URI for OAuth-required banks (e.g., Chase, USAA)",
    )

    # Categorization API Keys (optional - graceful degradation)
    anthropic_api_key: str | None = Field(
        default=None,
        description="Anthropic API key for Claude inference",
    )
    tavily_api_key: str | None = Field(
        default=None,
        description="Tavily API key for web search",
    )

    # Telegram Configuration (optional - graceful degradation)
    telegram_bot_token: str | None = Field(
        default=None,
        description="Telegram Bot API token from BotFather",
    )
    telegram_chat_ids: str | None = Field(
        default=None,
        description="Comma-separated list of Telegram chat IDs",
    )

    @computed_field
    @property
    def active_database_url(self) -> str:
        """Get the active database URL.

        Supports two patterns:
        1. GitHub Environments: Uses DATABASE_URL directly
        2. Local .env: Uses DATABASE_URL_DEV or DATABASE_URL_PROD based on ENVIRONMENT
        """
        # Pattern 1: GitHub Environments (single DATABASE_URL)
        if self.database_url:
            return self._normalize_db_url(self.database_url)

        # Pattern 2: Local .env (environment-specific URLs)
        if self.environment == "production":
            if not self.database_url_prod:
                raise ValueError(
                    "DATABASE_URL_PROD must be set for production environment"
                )
            return self._normalize_db_url(self.database_url_prod)
        else:
            if not self.database_url_dev:
                raise ValueError(
                    "DATABASE_URL_DEV must be set for development environment"
                )
            return self._normalize_db_url(self.database_url_dev)

    def _normalize_db_url(self, url: str) -> str:
        """Ensure database URL uses asyncpg driver."""
        if url.startswith("postgresql://"):
            return url.replace("postgresql://", "postgresql+asyncpg://", 1)
        elif url.startswith("postgres://"):
            return url.replace("postgres://", "postgresql+asyncpg://", 1)
        return url

    @field_validator("database_url", "database_url_dev", "database_url_prod")
    @classmethod
    def validate_database_url(cls, v: str | None) -> str | None:
        """Validate that database URL has correct format."""
        if v is None:
            return v
        if not v.startswith(("postgresql+asyncpg://", "postgresql://", "postgres://")):
            raise ValueError(
                "Database URL must start with postgresql+asyncpg://, "
                "postgresql://, or postgres://"
            )
        return v

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, v: str) -> str:
        """Validate log level is valid."""
        valid_levels = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper_v = v.upper()
        if upper_v not in valid_levels:
            raise ValueError(f"LOG_LEVEL must be one of: {', '.join(valid_levels)}")
        return upper_v


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()


# Convenience accessor for direct imports
settings = get_settings()
