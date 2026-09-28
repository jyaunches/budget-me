"""ReimbursementLink model for linking reimbursement deposits to expenses."""

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, UUIDMixin

if TYPE_CHECKING:
    from budget_me.db.models.transaction import Transaction


class ReimbursementLink(Base, UUIDMixin):
    """Links a reimbursement deposit to one or more expense transactions."""

    __tablename__ = "reimbursement_links"

    expense_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    deposit_transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("transactions.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    linked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(UTC),
        nullable=False,
    )

    # Relationships
    expense_transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        foreign_keys=[expense_transaction_id],
        backref="reimbursement_links_as_expense",
    )
    deposit_transaction: Mapped["Transaction"] = relationship(
        "Transaction",
        foreign_keys=[deposit_transaction_id],
        backref="reimbursement_links_as_deposit",
    )

    # Constraints and indexes
    __table_args__ = (
        UniqueConstraint(
            "expense_transaction_id",
            "deposit_transaction_id",
            name="uq_reimbursement_expense_deposit",
        ),
        Index("ix_reimbursement_links_expense_id", "expense_transaction_id"),
        Index("ix_reimbursement_links_deposit_id", "deposit_transaction_id"),
    )
