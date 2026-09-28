"""Base repository class with common CRUD operations."""

import uuid
from typing import Generic, TypeVar

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.db.models.base import Base

ModelT = TypeVar("ModelT", bound=Base)


class BaseRepository(Generic[ModelT]):
    """Base repository providing common CRUD operations."""

    model: type[ModelT]

    def __init__(self, session: AsyncSession) -> None:
        """Initialize repository with database session.

        Args:
            session: Async SQLAlchemy session for database operations.
        """
        self.session = session

    async def get_by_id(self, id: uuid.UUID) -> ModelT | None:
        """Get a single record by ID.

        Args:
            id: The UUID of the record to retrieve.

        Returns:
            The model instance if found, None otherwise.
        """
        return await self.session.get(self.model, id)

    async def get_all(self, limit: int = 100, offset: int = 0) -> list[ModelT]:
        """Get all records with pagination.

        Args:
            limit: Maximum number of records to return.
            offset: Number of records to skip.

        Returns:
            List of model instances.
        """
        stmt = select(self.model).limit(limit).offset(offset)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def create(self, **kwargs) -> ModelT:
        """Create a new record.

        Args:
            **kwargs: Field values for the new record.

        Returns:
            The created model instance.
        """
        instance = self.model(**kwargs)
        self.session.add(instance)
        await self.session.flush()
        return instance

    async def update(self, instance: ModelT, **kwargs) -> ModelT:
        """Update an existing record.

        Args:
            instance: The model instance to update.
            **kwargs: Field values to update.

        Returns:
            The updated model instance.
        """
        for key, value in kwargs.items():
            setattr(instance, key, value)
        await self.session.flush()
        return instance

    async def delete(self, instance: ModelT) -> None:
        """Delete a record.

        Args:
            instance: The model instance to delete.
        """
        await self.session.delete(instance)
        await self.session.flush()
