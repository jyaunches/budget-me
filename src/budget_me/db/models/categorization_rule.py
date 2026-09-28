"""Persistent household-specific transaction categorization rules."""

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Computed,
    Index,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from budget_me.db.models.base import Base, TimestampMixin, UUIDMixin


class CategorizationRule(Base, UUIDMixin, TimestampMixin):
    """A private category or reimbursement override layered over OSS defaults."""

    __tablename__ = "categorization_rules"

    rule_type: Mapped[str] = mapped_column(String(20), nullable=False)
    pattern: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_pattern: Mapped[str] = mapped_column(
        Text,
        Computed("lower(btrim(pattern))", persisted=True),
        nullable=False,
    )
    category: Mapped[str | None] = mapped_column(String(50), nullable=True)
    reimbursement_note: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    source: Mapped[str] = mapped_column(String(20), default="manual", nullable=False)
    confidence: Mapped[str | None] = mapped_column(String(10), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "rule_type",
            "normalized_pattern",
            name="uq_categorization_rules_type_pattern",
        ),
        CheckConstraint(
            "length(btrim(pattern)) BETWEEN 1 AND 255",
            name="ck_categorization_rules_pattern_length",
        ),
        CheckConstraint(
            "rule_type IN ('category', 'reimbursable')",
            name="ck_categorization_rules_type",
        ),
        CheckConstraint(
            "source IN ('manual', 'import', 'learned')",
            name="ck_categorization_rules_source",
        ),
        CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_categorization_rules_confidence",
        ),
        CheckConstraint(
            "enabled = false OR "
            "(rule_type = 'category' AND category IS NOT NULL "
            "AND reimbursement_note IS NULL) OR "
            "(rule_type = 'reimbursable' AND category IS NULL "
            "AND reimbursement_note IS NOT NULL)",
            name="ck_categorization_rules_payload",
        ),
        Index("ix_categorization_rules_enabled_type", "enabled", "rule_type"),
    )
