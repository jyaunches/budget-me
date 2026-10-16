"""Models for Plaid investment securities, holdings, and transactions."""

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING, Any

from sqlalchemy import (
    Date,
    DateTime,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account
    from budget_me.db.models.plaid_item import PlaidItem


class InvestmentSecurity(Base, TimestampMixin):
    """A security referenced by one or more Plaid investment records."""

    __tablename__ = "investment_securities"

    security_id: Mapped[str] = mapped_column(String(255), primary_key=True)
    institution_security_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    institution_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    name: Mapped[str | None] = mapped_column(Text, nullable=True)
    ticker_symbol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    security_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    close_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    close_price_as_of: Mapped[date | None] = mapped_column(Date, nullable=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unofficial_currency_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)


class InvestmentHolding(Base, UUIDMixin, TimestampMixin):
    """The latest known quantity and value for a security in an account."""

    __tablename__ = "investment_holdings"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("investment_securities.security_id", ondelete="CASCADE"),
        nullable=False,
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    institution_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    institution_price_as_of: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    institution_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unofficial_currency_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    plaid_item: Mapped["PlaidItem"] = relationship("PlaidItem")
    account: Mapped["Account"] = relationship("Account")
    security: Mapped[InvestmentSecurity] = relationship("InvestmentSecurity")

    __table_args__ = (
        UniqueConstraint(
            "account_id", "security_id", name="uq_investment_holdings_account_security"
        ),
        Index("ix_investment_holdings_plaid_item_id", "plaid_item_id"),
        Index("ix_investment_holdings_account_id", "account_id"),
    )


class InvestmentHoldingSnapshot(Base, UUIDMixin, TimestampMixin):
    """Daily holding value used for portfolio history and contribution analysis."""

    __tablename__ = "investment_holding_snapshots"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("investment_securities.security_id", ondelete="CASCADE"),
        nullable=False,
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    institution_price: Mapped[Decimal] = mapped_column(Numeric(24, 8), nullable=False)
    institution_value: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    cost_basis: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unofficial_currency_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )

    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "security_id",
            "snapshot_date",
            name="uq_investment_holding_snapshots_account_security_date",
        ),
        Index(
            "ix_investment_holding_snapshots_item_date",
            "plaid_item_id",
            "snapshot_date",
        ),
    )


class InvestmentTransaction(Base, UUIDMixin, TimestampMixin):
    """A transaction returned by Plaid's Investments product."""

    __tablename__ = "investment_transactions"

    investment_transaction_id: Mapped[str] = mapped_column(
        String(255), nullable=False, unique=True
    )
    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    security_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("investment_securities.security_id", ondelete="SET NULL"),
        nullable=True,
    )
    cancel_transaction_id: Mapped[str | None] = mapped_column(
        String(255), nullable=True
    )
    date: Mapped[date] = mapped_column(Date, nullable=False)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(18, 2), nullable=False)
    fees: Mapped[Decimal | None] = mapped_column(Numeric(18, 2), nullable=True)
    price: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    quantity: Mapped[Decimal | None] = mapped_column(Numeric(24, 8), nullable=True)
    transaction_type: Mapped[str | None] = mapped_column(String(100), nullable=True)
    subtype: Mapped[str | None] = mapped_column(String(100), nullable=True)
    iso_currency_code: Mapped[str | None] = mapped_column(String(3), nullable=True)
    unofficial_currency_code: Mapped[str | None] = mapped_column(
        String(20), nullable=True
    )
    raw: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)

    __table_args__ = (
        Index("ix_investment_transactions_item_date", "plaid_item_id", "date"),
        Index("ix_investment_transactions_account_id", "account_id"),
    )
