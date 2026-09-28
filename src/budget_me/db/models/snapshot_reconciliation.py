"""Immutable transaction-to-snapshot reconciliation ledger models."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal

from sqlalchemy import (
    CHAR,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column, relationship

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin

RECONCILIATION_FLOW_TYPES = (
    "income",
    "expense",
    "transfer_in",
    "transfer_out",
    "reimbursement_in",
    "reimbursement_out",
    "card_payment",
)

ADJUSTMENT_FLOW_TYPES = tuple(
    flow_type for flow_type in RECONCILIATION_FLOW_TYPES if flow_type != "card_payment"
)

LINE_ITEM_RESOLUTIONS = (
    "fulfilled",
    "skipped",
    "remaining",
    "adjustment",
)

_FLOW_TYPE_SQL = ", ".join(f"'{flow_type}'" for flow_type in RECONCILIATION_FLOW_TYPES)
_ADJUSTMENT_FLOW_TYPE_SQL = ", ".join(
    f"'{flow_type}'" for flow_type in ADJUSTMENT_FLOW_TYPES
)
_LINE_ITEM_RESOLUTION_SQL = ", ".join(
    f"'{resolution}'" for resolution in LINE_ITEM_RESOLUTIONS
)


class SnapshotReconciliationRun(Base, UUIDMixin, TimestampMixin):
    """One immutable reconciliation manifest for a monthly snapshot."""

    __tablename__ = "snapshot_reconciliation_runs"

    snapshot_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("monthly_snapshots.id", ondelete="CASCADE"),
        nullable=False,
    )
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    is_current: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    manifest_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    input_hash: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    reconciled_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )

    income_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    expense_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transfer_in_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    transfer_out_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    reimbursement_in_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    reimbursement_out_total: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    credit_card_total: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    net: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    posted_transaction_count: Mapped[int] = mapped_column(Integer, nullable=False)
    allocation_count: Mapped[int] = mapped_column(Integer, nullable=False)
    line_item_count: Mapped[int] = mapped_column(Integer, nullable=False)
    has_remaining_items: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )

    snapshot = relationship("MonthlySnapshot", foreign_keys=[snapshot_id])
    transaction_resolutions: Mapped[list[SnapshotTransactionResolution]] = relationship(
        "SnapshotTransactionResolution",
        back_populates="run",
        cascade="all, delete-orphan",
    )
    line_item_resolutions: Mapped[list[SnapshotLineItemResolution]] = relationship(
        "SnapshotLineItemResolution",
        back_populates="run",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        CheckConstraint(
            "version > 0",
            name="ck_snapshot_reconciliation_runs_version_positive",
        ),
        CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_reconciliation_runs_manifest_hash",
        ),
        CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_reconciliation_runs_input_hash",
        ),
        CheckConstraint(
            "income_total >= 0 AND expense_total >= 0 "
            "AND transfer_in_total >= 0 AND transfer_out_total >= 0 "
            "AND reimbursement_in_total >= 0 AND reimbursement_out_total >= 0 "
            "AND credit_card_total >= 0",
            name="ck_snapshot_reconciliation_runs_nonnegative_totals",
        ),
        CheckConstraint(
            "posted_transaction_count >= 0 AND allocation_count >= 0 "
            "AND line_item_count >= 0",
            name="ck_snapshot_reconciliation_runs_nonnegative_counts",
        ),
        CheckConstraint(
            "net = income_total + transfer_in_total + reimbursement_in_total "
            "- expense_total - transfer_out_total - reimbursement_out_total "
            "- credit_card_total",
            name="ck_snapshot_reconciliation_runs_net",
        ),
        Index(
            "uq_snapshot_reconciliation_runs_current_snapshot",
            "snapshot_id",
            unique=True,
            postgresql_where=text("is_current"),
        ),
        Index(
            "ix_snapshot_reconciliation_runs_snapshot_reconciled_at",
            "snapshot_id",
            "reconciled_at",
        ),
    )


class SnapshotTransactionResolution(Base, UUIDMixin):
    """Immutable source facts and classification for one posted transaction."""

    __tablename__ = "snapshot_transaction_resolutions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("snapshot_reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    transaction_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False
    )
    fingerprint: Mapped[str] = mapped_column(CHAR(64), nullable=False)
    account_id: Mapped[str] = mapped_column(String(255), nullable=False)
    transaction_date: Mapped[date] = mapped_column(Date, nullable=False)
    signed_amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    source_updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    classification_source: Mapped[str] = mapped_column(
        String(30),
        nullable=False,
        default="manifest",
        server_default=text("'manifest'"),
    )
    manual_locked: Mapped[bool] = mapped_column(
        Boolean,
        nullable=False,
        default=False,
        server_default=text("false"),
    )
    pair_group_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True), nullable=True
    )

    run: Mapped[SnapshotReconciliationRun] = relationship(
        "SnapshotReconciliationRun", back_populates="transaction_resolutions"
    )
    allocations: Mapped[list[SnapshotTransactionAllocation]] = relationship(
        "SnapshotTransactionAllocation",
        back_populates="resolution",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "transaction_id",
            name="uq_snapshot_transaction_resolutions_run_transaction",
        ),
        CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_transaction_resolutions_fingerprint",
        ),
        CheckConstraint(
            "length(btrim(classification_source)) BETWEEN 1 AND 30",
            name="ck_snapshot_transaction_resolutions_classification_source",
        ),
        CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="ck_snapshot_transaction_resolutions_currency",
        ),
        Index("ix_snapshot_transaction_resolutions_run_id", "run_id"),
        Index("ix_snapshot_transaction_resolutions_transaction_id", "transaction_id"),
        Index(
            "ix_snapshot_transaction_resolutions_pair_group_id",
            "pair_group_id",
            postgresql_where=text("pair_group_id IS NOT NULL"),
        ),
    )


class SnapshotTransactionAllocation(Base, UUIDMixin):
    """A positive cash-flow allocation belonging to one transaction resolution."""

    __tablename__ = "snapshot_transaction_allocations"

    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("snapshot_transaction_resolutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    allocation_index: Mapped[int] = mapped_column(Integer, nullable=False)
    flow_type: Mapped[str] = mapped_column(String(30), nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    category: Mapped[str | None] = mapped_column(String(100), nullable=True)

    resolution: Mapped[SnapshotTransactionResolution] = relationship(
        "SnapshotTransactionResolution", back_populates="allocations"
    )
    line_item_matches: Mapped[list[SnapshotLineItemMatch]] = relationship(
        "SnapshotLineItemMatch",
        back_populates="allocation",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "resolution_id",
            "allocation_index",
            name="uq_snapshot_transaction_allocations_resolution_index",
        ),
        CheckConstraint(
            f"flow_type IN ({_FLOW_TYPE_SQL})",
            name="ck_snapshot_transaction_allocations_flow_type",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_snapshot_transaction_allocations_amount_positive",
        ),
        CheckConstraint(
            "allocation_index >= 0",
            name="ck_snapshot_transaction_allocations_index_nonnegative",
        ),
        Index("ix_snapshot_transaction_allocations_resolution_id", "resolution_id"),
        Index("ix_snapshot_transaction_allocations_flow_type", "flow_type"),
    )


class SnapshotLineItemResolution(Base, UUIDMixin):
    """Resolution of one planned or manual snapshot line item for a run."""

    __tablename__ = "snapshot_line_item_resolutions"

    run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("snapshot_reconciliation_runs.id", ondelete="CASCADE"),
        nullable=False,
    )
    line_item_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    resolution: Mapped[str] = mapped_column(String(20), nullable=False)
    remaining_amount: Mapped[Decimal] = mapped_column(
        Numeric(12, 2),
        nullable=False,
        default=Decimal("0.00"),
        server_default=text("0.00"),
    )
    adjustment_flow_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    adjustment_amount: Mapped[Decimal | None] = mapped_column(
        Numeric(12, 2), nullable=True
    )
    authorization_note: Mapped[str | None] = mapped_column(Text, nullable=True)

    run: Mapped[SnapshotReconciliationRun] = relationship(
        "SnapshotReconciliationRun", back_populates="line_item_resolutions"
    )
    matches: Mapped[list[SnapshotLineItemMatch]] = relationship(
        "SnapshotLineItemMatch",
        back_populates="resolution",
        cascade="all, delete-orphan",
    )

    __table_args__ = (
        UniqueConstraint(
            "run_id",
            "line_item_id",
            name="uq_snapshot_line_item_resolutions_run_line_item",
        ),
        CheckConstraint(
            f"resolution IN ({_LINE_ITEM_RESOLUTION_SQL})",
            name="ck_snapshot_line_item_resolutions_resolution",
        ),
        CheckConstraint(
            "remaining_amount >= 0",
            name="ck_snapshot_line_item_resolutions_remaining_nonnegative",
        ),
        CheckConstraint(
            "adjustment_flow_type IS NULL OR adjustment_flow_type IN "
            f"({_ADJUSTMENT_FLOW_TYPE_SQL})",
            name="ck_snapshot_line_item_resolutions_adjustment_flow_type",
        ),
        CheckConstraint(
            "(resolution = 'remaining' AND remaining_amount > 0 "
            "AND adjustment_flow_type IS NULL AND adjustment_amount IS NULL "
            "AND authorization_note IS NULL) OR "
            "(resolution = 'adjustment' AND remaining_amount = 0 "
            "AND adjustment_flow_type IS NOT NULL AND adjustment_amount > 0 "
            "AND length(btrim(authorization_note)) > 0) OR "
            "(resolution IN ('fulfilled', 'skipped') AND remaining_amount = 0 "
            "AND adjustment_flow_type IS NULL AND adjustment_amount IS NULL "
            "AND authorization_note IS NULL)",
            name="ck_snapshot_line_item_resolutions_payload",
        ),
        Index("ix_snapshot_line_item_resolutions_run_id", "run_id"),
        Index("ix_snapshot_line_item_resolutions_line_item_id", "line_item_id"),
    )


class SnapshotLineItemMatch(Base, UUIDMixin):
    """Many-to-many amount matched between a line resolution and an allocation."""

    __tablename__ = "snapshot_line_item_matches"

    resolution_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("snapshot_line_item_resolutions.id", ondelete="CASCADE"),
        nullable=False,
    )
    allocation_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("snapshot_transaction_allocations.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)

    resolution: Mapped[SnapshotLineItemResolution] = relationship(
        "SnapshotLineItemResolution", back_populates="matches"
    )
    allocation: Mapped[SnapshotTransactionAllocation] = relationship(
        "SnapshotTransactionAllocation", back_populates="line_item_matches"
    )

    __table_args__ = (
        UniqueConstraint(
            "resolution_id",
            "allocation_id",
            name="uq_snapshot_line_item_matches_resolution_allocation",
        ),
        CheckConstraint(
            "amount > 0",
            name="ck_snapshot_line_item_matches_amount_positive",
        ),
        Index("ix_snapshot_line_item_matches_resolution_id", "resolution_id"),
        Index("ix_snapshot_line_item_matches_allocation_id", "allocation_id"),
    )
