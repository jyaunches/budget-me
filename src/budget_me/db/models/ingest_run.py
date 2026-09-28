"""Ingest run tracking models."""

import enum
import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.plaid_item import PlaidItem


class IngestRunType(str, enum.Enum):
    """Type of ingest run."""

    SCHEDULED = "scheduled"
    MANUAL = "manual"
    WEBHOOK = "webhook"


class IngestRunStatus(str, enum.Enum):
    """Status of an ingest run."""

    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


class IngestRun(Base, UUIDMixin):
    """Tracks a single ingest run across all items."""

    __tablename__ = "ingest_runs"

    started_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    ended_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    run_type: Mapped[IngestRunType] = mapped_column(
        Enum(
            IngestRunType,
            name="ingest_run_type",
            values_callable=lambda x: [e.value for e in x],
        ),
        nullable=False,
    )
    status: Mapped[IngestRunStatus] = mapped_column(
        Enum(
            IngestRunStatus,
            name="ingest_run_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=IngestRunStatus.RUNNING,
        nullable=False,
    )
    items_total: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_ok: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    items_failed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_modified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_summary: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    run_items: Mapped[list["IngestRunItem"]] = relationship(
        "IngestRunItem", back_populates="ingest_run"
    )


class IngestRunItemStatus(str, enum.Enum):
    """Status of an ingest run item."""

    PENDING = "pending"
    SUCCESS = "success"
    FAILED = "failed"
    SKIPPED = "skipped"


class IngestRunItem(Base, UUIDMixin):
    """Tracks the result of ingesting a single Plaid item."""

    __tablename__ = "ingest_run_items"

    ingest_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("ingest_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    status: Mapped[IngestRunItemStatus] = mapped_column(
        Enum(
            IngestRunItemStatus,
            name="ingest_run_item_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=IngestRunItemStatus.PENDING,
        nullable=False,
    )
    tx_added: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_modified: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tx_removed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Relationships
    ingest_run: Mapped["IngestRun"] = relationship(
        "IngestRun", back_populates="run_items"
    )
    plaid_item: Mapped["PlaidItem"] = relationship(
        "PlaidItem", back_populates="ingest_run_items"
    )
