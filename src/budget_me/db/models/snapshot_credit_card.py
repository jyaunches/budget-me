"""SnapshotCreditCard model for storing per-month credit card state."""

import uuid
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import (
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account
    from budget_me.db.models.monthly_snapshot import MonthlySnapshot


class SnapshotCreditCard(Base, UUIDMixin, TimestampMixin):
    """Represents a credit card's state in a monthly snapshot."""

    __tablename__ = "snapshot_credit_cards"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monthly_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    statement_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    payment_strategy: Mapped[str] = mapped_column(String(30), nullable=False)
    fixed_payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    calculated_payment: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    due_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    actual_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    actual_payment_source: Mapped[str | None] = mapped_column(String(30), nullable=True)
    actual_payment_transaction_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="RESTRICT"),
        nullable=True,
    )
    actual_payment_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Relationships
    snapshot: Mapped["MonthlySnapshot"] = relationship(
        "MonthlySnapshot", back_populates="credit_cards"
    )
    account: Mapped["Account"] = relationship("Account", foreign_keys=[account_id])

    # Constraints and Indexes
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "account_id",
            name="uq_snapshot_credit_cards_snapshot_account",
        ),
        CheckConstraint(
            "actual_payment_source IS NULL "
            "OR actual_payment_source = 'card_feed' "
            "OR (actual_payment_source = 'checking_account' "
            "AND actual_payment_amount IS NOT NULL "
            "AND actual_payment_date IS NOT NULL "
            "AND actual_payment_transaction_id IS NOT NULL "
            "AND NULLIF(BTRIM(actual_payment_note), '') IS NOT NULL)",
            name="ck_snapshot_credit_cards_actual_payment_source",
        ),
        Index("ix_snapshot_credit_cards_snapshot_id", "snapshot_id"),
    )
