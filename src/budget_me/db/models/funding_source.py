"""FundingSource model for tracking external funding sources."""

import enum
from decimal import Decimal

from sqlalchemy import Boolean, Numeric, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin


class FundingSourceType(str, enum.Enum):
    """Type of funding source."""

    INVESTMENT = "investment"  # Stock, RSUs, 401k
    SAVINGS = "savings"  # Savings accounts
    OTHER = "other"  # Any other liquid asset


class FundingSource(Base, UUIDMixin, TimestampMixin):
    """Represents an external funding source for deficit spending."""

    __tablename__ = "funding_sources"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(30), nullable=False)
    available_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
