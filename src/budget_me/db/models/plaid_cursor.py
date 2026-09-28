"""PlaidCursor model for transaction sync cursors."""

import uuid
from datetime import UTC, datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base

if TYPE_CHECKING:
    from budget_me.db.models.plaid_item import PlaidItem


class PlaidCursor(Base):
    """Stores the transaction sync cursor for a Plaid Item."""

    __tablename__ = "plaid_cursors"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        primary_key=True,
    )
    transactions_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    plaid_item: Mapped["PlaidItem"] = relationship("PlaidItem", back_populates="cursor")
