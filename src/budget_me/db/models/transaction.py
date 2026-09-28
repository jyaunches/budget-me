"""Transaction model for storing Plaid transactions."""

import uuid
from datetime import date as date_type
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.plaid_item import PlaidItem


class Transaction(Base, UUIDMixin, TimestampMixin):
    """Represents a bank transaction from Plaid."""

    __tablename__ = "transactions"

    plaid_transaction_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    date: Mapped[date_type] = mapped_column(Date, nullable=False)
    authorized_date: Mapped[date_type | None] = mapped_column(Date, nullable=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    merchant_name: Mapped[str | None] = mapped_column(Text, nullable=True)
    pending: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    payment_channel: Mapped[str | None] = mapped_column(String(50), nullable=True)
    category_primary: Mapped[str | None] = mapped_column(String(100), nullable=True)
    category_detailed: Mapped[str | None] = mapped_column(String(100), nullable=True)
    merchant_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    normalized_merchant: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    # Budget categorization
    budget_category: Mapped[str | None] = mapped_column(String(50), nullable=True)

    # Review tracking
    reviewed: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    reviewed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    # Reimbursable expense tracking
    reimbursable: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    reimbursement_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    reimbursement_note: Mapped[str | None] = mapped_column(String(255), nullable=True)

    # Cross-month project tracking (budget-neutral free-text tag, e.g. "example_project_2027")
    project_tag: Mapped[str | None] = mapped_column(
        String(100), nullable=True, index=True
    )

    # Relationships
    plaid_item: Mapped["PlaidItem"] = relationship(
        "PlaidItem", back_populates="transactions"
    )

    # Indexes defined at table level
    __table_args__ = (
        Index("ix_transactions_date", "date"),
        Index("ix_transactions_plaid_item_id_date", "plaid_item_id", "date"),
        Index("ix_transactions_account_id", "account_id"),
        Index("ix_transactions_budget_category", "budget_category"),
        Index("ix_transactions_reviewed", "reviewed"),
        Index("ix_transactions_reimbursable", "reimbursable"),
    )
