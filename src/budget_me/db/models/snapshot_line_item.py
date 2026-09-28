"""SnapshotLineItem model for storing snapshot expenses and income."""

import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.anticipated_item import AnticipatedItem
    from budget_me.db.models.monthly_snapshot import MonthlySnapshot


class SnapshotLineItem(Base, UUIDMixin, TimestampMixin):
    """Represents an expense or income line item in a monthly snapshot."""

    __tablename__ = "snapshot_line_items"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monthly_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source_item_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("anticipated_items.id", ondelete="SET NULL"),
        nullable=True,
    )
    is_one_time: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    skipped: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Relationships
    snapshot: Mapped["MonthlySnapshot"] = relationship(
        "MonthlySnapshot", back_populates="line_items"
    )
    source_item: Mapped["AnticipatedItem | None"] = relationship(
        "AnticipatedItem", foreign_keys=[source_item_id]
    )

    # Indexes
    __table_args__ = (
        Index(
            "ix_snapshot_line_items_snapshot_id_item_type", "snapshot_id", "item_type"
        ),
        Index("ix_snapshot_line_items_source_item_id", "source_item_id"),
    )
