"""Base model class with common fields for all entities."""

import uuid
from datetime import UTC, datetime

from sqlalchemy import DateTime, event
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Base class for all SQLAlchemy ORM models."""

    pass


class UUIDMixin:
    """Mixin that provides a UUID primary key."""

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class TimestampMixin:
    """Mixin that provides created_at and updated_at timestamps."""

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )


# Event listener to update updated_at on modification
@event.listens_for(Base, "before_update", propagate=True)
def receive_before_update(mapper, connection, target):
    """Update updated_at timestamp before any model update."""
    if hasattr(target, "updated_at"):
        target.updated_at = datetime.now(UTC)
