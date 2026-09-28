"""Account model for storing Plaid account data."""

import enum
import uuid
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account_balance_snapshot import AccountBalanceSnapshot
    from budget_me.db.models.credit_liability import CreditLiability
    from budget_me.db.models.loan_details import LoanDetails
    from budget_me.db.models.plaid_item import PlaidItem


class PaymentStrategy(str, enum.Enum):
    """Payment strategy for credit card accounts."""

    PAY_IN_FULL = "pay_in_full"
    PROMOTIONAL_PAYDOWN = "promotional_paydown"


class Account(Base, UUIDMixin, TimestampMixin):
    """Represents a Plaid account within a PlaidItem."""

    __tablename__ = "accounts"

    plaid_item_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("plaid_items.id", ondelete="CASCADE"),
        nullable=False,
    )
    account_id: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    type: Mapped[str] = mapped_column(String(50), nullable=False)
    subtype: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mask: Mapped[str | None] = mapped_column(String(10), nullable=True)
    balance_available: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    balance_current: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    payment_strategy: Mapped[str] = mapped_column(
        String(30), nullable=False, default=PaymentStrategy.PAY_IN_FULL
    )
    fixed_payment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    projected_monthly_payment: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    is_excluded: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default="false"
    )
    paying_account_id: Mapped[str | None] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="SET NULL"),
        nullable=True,
    )

    # Relationships
    plaid_item: Mapped["PlaidItem"] = relationship(
        "PlaidItem", back_populates="accounts"
    )
    paying_account: Mapped["Account | None"] = relationship(
        "Account",
        foreign_keys=[paying_account_id],
        remote_side="Account.account_id",
    )
    credit_liability: Mapped["CreditLiability | None"] = relationship(
        "CreditLiability",
        back_populates="account",
        uselist=False,
        foreign_keys="CreditLiability.account_id",
        primaryjoin="Account.account_id == CreditLiability.account_id",
    )
    loan_details: Mapped["LoanDetails | None"] = relationship(
        "LoanDetails",
        back_populates="account",
        uselist=False,
        foreign_keys="LoanDetails.account_id",
        primaryjoin="Account.account_id == LoanDetails.account_id",
    )
    balance_snapshots: Mapped[list["AccountBalanceSnapshot"]] = relationship(
        "AccountBalanceSnapshot",
        back_populates="account",
        foreign_keys="AccountBalanceSnapshot.account_id",
        primaryjoin="Account.account_id == AccountBalanceSnapshot.account_id",
    )

    # Indexes defined at table level
    __table_args__ = (Index("ix_accounts_account_id", "account_id"),)
