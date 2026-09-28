"""LoanDetails model for storing loan liability data."""

import enum
from datetime import date
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Date, ForeignKey, Index, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account


class LoanType(str, enum.Enum):
    """Types of loans supported."""

    MORTGAGE = "mortgage"
    AUTO = "auto"
    PERSONAL = "personal"
    STUDENT = "student"
    OTHER = "other"


class LoanDetails(Base, UUIDMixin, TimestampMixin):
    """Represents loan liability data for an account.

    Stores details like interest rate, monthly payment, and maturity date
    for mortgage, auto, personal, and student loans.
    """

    __tablename__ = "loan_details"

    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
    )
    loan_type: Mapped[str] = mapped_column(String(20), nullable=False)
    interest_rate: Mapped[Decimal] = mapped_column(Numeric(6, 4), nullable=False)
    monthly_payment: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    maturity_date: Mapped[date] = mapped_column(Date, nullable=False)
    original_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    loan_start_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    remaining_payments: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lender_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    collateral_description: Mapped[str | None] = mapped_column(
        String(500), nullable=True
    )
    source: Mapped[str] = mapped_column(
        String(20), nullable=False, server_default="manual"
    )

    # Relationship back to Account
    account: Mapped["Account"] = relationship(
        "Account",
        back_populates="loan_details",
        foreign_keys=[account_id],
        primaryjoin="LoanDetails.account_id == Account.account_id",
    )

    # Indexes
    __table_args__ = (
        Index("ix_loan_details_loan_type", "loan_type"),
        Index("ix_loan_details_maturity_date", "maturity_date"),
    )
