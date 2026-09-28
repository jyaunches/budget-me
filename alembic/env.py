"""Alembic environment configuration for async SQLAlchemy migrations."""

import asyncio
import os
import sys
from logging.config import fileConfig

from dotenv import load_dotenv

# Normal application commands load the project dotenv for convenience. Tests and
# safety tooling can require environment-only configuration so a private checkout
# can never become an implicit migration target.
if os.environ.get("BUDGET_ME_DISABLE_DOTENV") != "1":
    load_dotenv(os.path.join(os.path.dirname(__file__), "..", ".env"))

from alembic import context
from sqlalchemy import pool
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import async_engine_from_config

# Add src to path for imports
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from budget_me.db.models import Base

# This is the Alembic Config object
config = context.config

# Interpret the config file for Python logging
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Model's MetaData object for 'autogenerate' support
target_metadata = Base.metadata


def get_url() -> str:
    """Get the database URL for migrations.

    Prefer the deployment-friendly DATABASE_URL setting, then fall back to
    DATABASE_URL_DEV or DATABASE_URL_PROD based on ENVIRONMENT.
    """
    url = os.environ.get("DATABASE_URL", "")

    if not url:
        environment = os.environ.get("ENVIRONMENT", "development")

        if environment == "production":
            url = os.environ.get("DATABASE_URL_PROD", "")
            if not url:
                raise ValueError(
                    "DATABASE_URL or DATABASE_URL_PROD environment variable is "
                    "required for production"
                )
        else:
            url = os.environ.get("DATABASE_URL_DEV", "")
            if not url:
                raise ValueError(
                    "DATABASE_URL or DATABASE_URL_DEV environment variable is "
                    "required for development"
                )

    # Convert to asyncpg format if needed
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif url.startswith("postgres://"):
        url = url.replace("postgres://", "postgresql+asyncpg://", 1)

    return url


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode.

    This configures the context with just a URL and not an Engine.
    Calls to context.execute() emit the given string to the script output.
    """
    url = get_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection: Connection) -> None:
    """Run migrations with the given connection."""
    context.configure(connection=connection, target_metadata=target_metadata)

    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Run migrations in 'online' mode with async engine."""
    configuration = config.get_section(config.config_ini_section) or {}
    configuration["sqlalchemy.url"] = get_url()

    connectable = async_engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
