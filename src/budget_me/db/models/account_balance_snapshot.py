"""Account balance snapshot model for tracking daily balances."""

from datetime import date, datetime
from decimal import Decimal
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import Date, ForeignKey, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base

if TYPE_CHECKING:
    from budget_me.db.models.account import Account


class AccountBalanceSnapshot(Base):
    """Daily snapshot of account balance from Plaid sync."""

    __tablename__ = "account_balance_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "account_id", "snapshot_date", name="uq_account_balance_snapshot"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    account_id: Mapped[str] = mapped_column(
        String, ForeignKey("accounts.account_id"), nullable=False, index=True
    )
    snapshot_date: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    balance_current: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    balance_available: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(insert_default=lambda: datetime.now())

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account", back_populates="balance_snapshots"
    )
