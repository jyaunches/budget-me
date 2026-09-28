"""Merchant normalization models."""

from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from budget_me.db.models.base import Base, UUIDMixin


class MerchantRule(Base, UUIDMixin):
    """Rule for normalizing merchant names."""

    __tablename__ = "merchant_rules"

    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    replacement: Mapped[str] = mapped_column(Text, nullable=False)
    priority: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)


class MerchantMap(Base):
    """Cached mapping from input merchant names to normalized names."""

    __tablename__ = "merchant_map"

    input_name: Mapped[str] = mapped_column(String(255), primary_key=True)
    normalized: Mapped[str] = mapped_column(String(255), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        onupdate=lambda: datetime.now(UTC),
        nullable=False,
    )
