"""PlaidItem model for storing Plaid connection data."""

import enum
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, Enum, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account
    from budget_me.db.models.credit_liability import CreditLiability
    from budget_me.db.models.ingest_run import IngestRunItem
    from budget_me.db.models.plaid_cursor import PlaidCursor
    from budget_me.db.models.transaction import Transaction


class PlaidItemStatus(str, enum.Enum):
    """Status of a Plaid Item connection."""

    ACTIVE = "active"
    RELINK_REQUIRED = "relink_required"
    REVOKED = "revoked"
    PENDING = "pending"


class PlaidItem(Base, UUIDMixin, TimestampMixin):
    """Represents a Plaid Item (bank connection)."""

    __tablename__ = "plaid_items"

    user_key: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    item_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    institution_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    institution_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    access_token_enc: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[PlaidItemStatus] = mapped_column(
        Enum(
            PlaidItemStatus,
            name="plaid_item_status",
            values_callable=lambda x: [e.value for e in x],
        ),
        default=PlaidItemStatus.ACTIVE,
        nullable=False,
    )
    last_success_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    last_error_code: Mapped[str | None] = mapped_column(String(100), nullable=True)
    last_error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    products: Mapped[list[str]] = mapped_column(
        JSONB, nullable=False, server_default='["transactions"]'
    )

    # Relationships
    cursor: Mapped["PlaidCursor | None"] = relationship(
        "PlaidCursor", back_populates="plaid_item", uselist=False
    )
    accounts: Mapped[list["Account"]] = relationship(
        "Account", back_populates="plaid_item", cascade="all, delete-orphan"
    )
    transactions: Mapped[list["Transaction"]] = relationship(
        "Transaction", back_populates="plaid_item"
    )
    credit_liabilities: Mapped[list["CreditLiability"]] = relationship(
        "CreditLiability", back_populates="plaid_item", cascade="all, delete-orphan"
    )
    ingest_run_items: Mapped[list["IngestRunItem"]] = relationship(
        "IngestRunItem", back_populates="plaid_item"
    )
