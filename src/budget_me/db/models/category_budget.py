"""CategoryBudget model for storing per-account, per-month budget targets."""

from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.account import Account


class CategoryBudget(Base, UUIDMixin, TimestampMixin):
    """Represents a monthly budget target for a spending category."""

    __tablename__ = "category_budgets"

    account_id: Mapped[str] = mapped_column(
        String(255),
        ForeignKey("accounts.account_id", ondelete="CASCADE"),
        nullable=False,
    )
    year_month: Mapped[str] = mapped_column(
        String(7), nullable=False
    )  # Format: "2025-01"
    category: Mapped[str] = mapped_column(String(100), nullable=False)
    budget_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    # Relationships
    account: Mapped["Account"] = relationship(
        "Account",
        foreign_keys=[account_id],
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "year_month",
            "category",
            name="uq_category_budgets_account_month_category",
        ),
        Index("ix_category_budgets_account_month", "account_id", "year_month"),
    )
