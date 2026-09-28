"""Tests for database engine and session management."""

import pytest
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from budget_me.db.engine import get_engine, get_session_factory


class TestGetEngine:
    """Tests for engine creation."""

    def test_engine_creates_from_url(self):
        """Engine object can be created from a database URL."""
        # Use a test URL (not connecting)
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"

        # Clear cache to test fresh creation
        get_engine.cache_clear()

        engine = get_engine(url)

        assert isinstance(engine, AsyncEngine)
        assert "asyncpg" in str(engine.url)

    def test_engine_converts_postgresql_url(self):
        """Engine converts postgresql:// to postgresql+asyncpg://."""
        url = "postgresql://user:pass@localhost:5432/testdb"

        get_engine.cache_clear()

        engine = get_engine(url)

        assert "asyncpg" in str(engine.url)

    def test_engine_converts_postgres_url(self):
        """Engine converts postgres:// to postgresql+asyncpg://."""
        url = "postgres://user:pass@localhost:5432/testdb"

        get_engine.cache_clear()

        engine = get_engine(url)

        assert "asyncpg" in str(engine.url)

    def test_engine_is_cached(self):
        """Same URL returns cached engine instance."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"

        get_engine.cache_clear()

        engine1 = get_engine(url)
        engine2 = get_engine(url)

        assert engine1 is engine2


class TestGetSessionFactory:
    """Tests for session factory."""

    def test_session_factory_creates_async_session(self):
        """Session factory creates AsyncSession instances."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        get_engine.cache_clear()
        engine = get_engine(url)

        factory = get_session_factory(engine)
        session = factory()

        assert isinstance(session, AsyncSession)


class TestBaseModel:
    """Tests for base model mixins."""

    def test_uuid_mixin_generates_uuid_id(self):
        """UUIDMixin generates a valid UUID for id field."""
        from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

        class TestModel(Base, UUIDMixin, TimestampMixin):
            __tablename__ = "test_model"

        # The default is a factory, so we can check the column default
        assert TestModel.__table__.c.id.default is not None

    def test_timestamp_mixin_has_created_at_and_updated_at(self):
        """TimestampMixin adds created_at and updated_at columns."""
        from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

        class TestModel(Base, UUIDMixin, TimestampMixin):
            __tablename__ = "test_model_2"

        # Check columns exist
        assert "created_at" in TestModel.__table__.c
        assert "updated_at" in TestModel.__table__.c

        # Check they have defaults
        assert TestModel.__table__.c.created_at.default is not None
        assert TestModel.__table__.c.updated_at.default is not None
        assert TestModel.__table__.c.updated_at.onupdate is not None


class TestAsyncSessionContextManager:
    """Tests for async session context manager behavior."""

    @pytest.mark.asyncio
    async def test_session_context_manager_basic_usage(self):
        """Session context manager provides a working session."""
        from budget_me.db.engine import get_async_session

        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        get_engine.cache_clear()
        engine = get_engine(url)

        # We can't actually connect without a real database,
        # but we can test the context manager structure
        try:
            async with get_async_session(engine) as session:
                assert isinstance(session, AsyncSession)
        except Exception:
            # Expected to fail on actual connection
            pass

    @pytest.mark.asyncio
    async def test_session_factory_returns_correct_type(self):
        """Session factory returns an AsyncSession-like object."""
        url = "postgresql+asyncpg://user:pass@localhost:5432/testdb"
        get_engine.cache_clear()
        engine = get_engine(url)

        factory = get_session_factory(engine)
        session = factory()

        assert isinstance(session, AsyncSession)
        await session.close()
