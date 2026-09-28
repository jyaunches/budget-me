"""CreditLiability and CreditLiabilityApr models for tracking credit card liability data."""

import uuid
from datetime import date
from decimal import Decimal
from enum import Enum
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, Date, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account
    from budget_me.db.models.plaid_item import PlaidItem


class AprType(Enum):
    """APR types from Plaid Liabilities API."""

    BALANCE_TRANSFER = "balance_transfer_apr"
    CASH = "cash_apr"
    PURCHASE = "purchase_apr"
    SPECIAL = "special"


class CreditLiability(Base, UUIDMixin, TimestampMixin):
    """Represents credit card liability data for an account."""

    __tablename__ = "credit_liabilities"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    is_overdue: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    last_payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    last_payment_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_statement_balance: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    last_statement_issue_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    minimum_payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    next_payment_due_date: Mapped[date | None] = mapped_column(Date, nullable=True)

    # Relationships
    plaid_item: Mapped["PlaidItem"] = relationship(
        "PlaidItem", back_populates="credit_liabilities"
    )
    aprs: Mapped[list["CreditLiabilityApr"]] = relationship(
        "CreditLiabilityApr",
        back_populates="credit_liability",
        cascade="all, delete-orphan",
    )
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="credit_liability",
        foreign_keys=[account_id],
        primaryjoin="CreditLiability.account_id == Account.account_id",
    )

    # Indexes defined at table level
    __table_args__ = (Index("ix_credit_liabilities_plaid_item_id", "plaid_item_id"),)


class CreditLiabilityApr(Base, UUIDMixin):
    """Represents an APR entry for a credit liability.

    A single credit liability can have multiple APRs (purchase, balance transfer, etc.)
    Supports promotional APR tracking with expiration dates and offer IDs.
    """

    __tablename__ = "credit_liability_aprs"

    credit_liability_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("credit_liabilities.id", ondelete="CASCADE"),
        nullable=False,
    )
    apr_type: Mapped[str] = mapped_column(String(50), nullable=False)
    apr_percentage: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False)
    balance_subject_to_apr: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    interest_charge_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )

    # Promotional APR tracking fields
    promo_rate_end_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    promo_offer_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="plaid"
    )

    # Relationships
    credit_liability: Mapped["CreditLiability"] = relationship(
        "CreditLiability", back_populates="aprs"
    )

    # Indexes defined at table level
    __table_args__ = (
        Index("ix_credit_liability_aprs_liability_id", "credit_liability_id"),
        Index(
            "ix_credit_liability_aprs_promo_end_date",
            "promo_rate_end_date",
            postgresql_where="promo_rate_end_date IS NOT NULL",
        ),
    )
