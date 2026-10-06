"""AnticipatedItem model for storing recurring expenses and income."""

import enum
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account


class ItemType(str, enum.Enum):
    """Type of anticipated item."""

    EXPENSE = "expense"
    INCOME = "income"


class ItemFrequency(str, enum.Enum):
    """Frequency of anticipated item occurrence."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"  # Every 3 months from start_month; Jan if unset
    ANNUAL = "annual"  # Specified month only
    ONE_TIME = "one_time"  # Single occurrence in start_month


class AnticipatedItem(Base, UUIDMixin, TimestampMixin):
    """Represents an anticipated recurring expense or income item."""

    __tablename__ = "anticipated_items"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    item_type: Mapped[str] = mapped_column(String(20), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    frequency: Mapped[str] = mapped_column(
        String(20), nullable=False, default="monthly"
    )
    start_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    end_month: Mapped[str | None] = mapped_column(String(7), nullable=True)
    account_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    account: Mapped["Account | None"] = relationship(
        "Account",
        foreign_keys=[account_id],
    )

    # Indexes
    __table_args__ = (
        Index("ix_anticipated_items_item_type_active", "item_type", "active"),
    )
