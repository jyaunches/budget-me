"""MonthlySnapshot model for persisting monthly financial snapshots."""

import enum
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    Boolean,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account
    from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
    from budget_me.db.models.snapshot_line_item import SnapshotLineItem


class SnapshotStatus(str, enum.Enum):
    """Status of a monthly snapshot."""

    OPEN = "open"
    CLOSED = "closed"


class MonthlySnapshot(Base, UUIDMixin, TimestampMixin):
    """Represents a monthly financial snapshot."""

    __tablename__ = "monthly_snapshots"

    year_month: Mapped[str] = mapped_column(String(7), nullable=False, index=True)
    account_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default=SnapshotStatus.OPEN
    )
    income_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    expense_total: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    transfer_in_total: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    transfer_out_total: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    reimbursement_in_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    reimbursement_out_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2), nullable=False, default=Decimal("0.00"), server_default="0.00"
    )
    credit_card_total: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    net: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    starting_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    closing_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    closing_balance_frozen: Mapped[bool] = mapped_column(
        Boolean, default=lambda: False, nullable=False
    )
    closed_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    last_synced_at: Mapped[datetime | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    account: Mapped["Account | None"] = relationship(
        "Account",
        foreign_keys=[account_id],
    )
    line_items: Mapped[list["SnapshotLineItem"]] = relationship(
        "SnapshotLineItem",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )
    credit_cards: Mapped[list["SnapshotCreditCard"]] = relationship(
        "SnapshotCreditCard",
        back_populates="snapshot",
        cascade="all, delete-orphan",
    )

    # Indexes and constraints
    __table_args__ = (
        UniqueConstraint(
            "year_month", "account_id", name="uq_monthly_snapshots_year_month_account"
        ),
        Index("ix_monthly_snapshots_year_month", "year_month"),
        Index("ix_monthly_snapshots_account_id", "account_id"),
        Index("ix_monthly_snapshots_status", "status"),
    )
