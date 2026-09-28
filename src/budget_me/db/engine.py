"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from functools import lru_cache

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@lru_cache
def get_engine(database_url: str | None = None) -> AsyncEngine:
    """Create and cache the async SQLAlchemy engine.

    Args:
        database_url: The database URL. If not provided, loads from settings.

    Returns:
        Cached AsyncEngine instance.
    """
    if database_url is None:
        from budget_me.config import settings

        database_url = settings.active_database_url

    # Ensure URL uses asyncpg driver
    if database_url.startswith("postgresql://"):
        database_url = database_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    elif database_url.startswith("postgres://"):
        database_url = database_url.replace("postgres://", "postgresql+asyncpg://", 1)

    # Detect if using Supabase pooler (port 6543) which requires disabling
    # prepared statement cache due to pgbouncer transaction mode
    connect_args = {}
    if ":6543/" in database_url or ".pooler.supabase.com" in database_url:
        connect_args["statement_cache_size"] = 0

    return create_async_engine(
        database_url,
        echo=False,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
        connect_args=connect_args,
    )


def get_session_factory(engine: AsyncEngine | None = None) -> async_sessionmaker:
    """Get the async session factory.

    Args:
        engine: Optional engine to use. If not provided, uses default.

    Returns:
        Async session factory.
    """
    if engine is None:
        engine = get_engine()

    return async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )


@asynccontextmanager
async def get_async_session(
    engine: AsyncEngine | None = None,
) -> AsyncGenerator[AsyncSession, None]:
    """Provide a transactional scope around a series of operations.

    This context manager handles commit on success and rollback on error.

    Args:
        engine: Optional engine to use. If not provided, uses default.

    Yields:
        An async session instance.

    Example:
        async with get_async_session() as session:
            # Do database operations
            result = await session.execute(select(User))
    """
    factory = get_session_factory(engine)
    session = factory()
    try:
        yield session
        await session.commit()
    except Exception:
        await session.rollback()
        raise
    finally:
        await session.close()


async def get_session_dependency() -> AsyncGenerator[AsyncSession, None]:
    """FastAPI dependency for getting database sessions.

    Use with FastAPI's Depends() for automatic session management.

    Yields:
        An async session instance.
    """
    async with get_async_session() as session:
        yield session
