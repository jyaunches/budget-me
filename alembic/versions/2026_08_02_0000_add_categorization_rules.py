"""Add persistent categorization-rule overrides.

Revision ID: c21f6a9d8e34
Revises: d4a7e9c2f610
Create Date: 2026-08-02 00:00:00+00:00

The table stores installation-specific overrides layered over the defaults
shipped with the open-source package. Row-level security is enabled without
policies so Supabase's public API cannot read or mutate private rules.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c21f6a9d8e34"
down_revision: str | None = "d4a7e9c2f610"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE_NAME = "categorization_rules"
ENABLE_RLS_SQL = f'ALTER TABLE public."{TABLE_NAME}" ENABLE ROW LEVEL SECURITY'


def upgrade() -> None:
    """Create private categorization-rule storage and enable RLS."""
    op.create_table(
        TABLE_NAME,
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("rule_type", sa.String(length=20), nullable=False),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column(
            "normalized_pattern",
            sa.Text(),
            sa.Computed("lower(btrim(pattern))", persisted=True),
            nullable=False,
        ),
        sa.Column("category", sa.String(length=50), nullable=True),
        sa.Column("reimbursement_note", sa.String(length=255), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "source",
            sa.String(length=20),
            nullable=False,
            server_default=sa.text("'manual'"),
        ),
        sa.Column("confidence", sa.String(length=10), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.CheckConstraint(
            "length(btrim(pattern)) BETWEEN 1 AND 255",
            name="ck_categorization_rules_pattern_length",
        ),
        sa.CheckConstraint(
            "rule_type IN ('category', 'reimbursable')",
            name="ck_categorization_rules_type",
        ),
        sa.CheckConstraint(
            "source IN ('manual', 'import', 'learned')",
            name="ck_categorization_rules_source",
        ),
        sa.CheckConstraint(
            "confidence IS NULL OR confidence IN ('high', 'medium', 'low')",
            name="ck_categorization_rules_confidence",
        ),
        sa.CheckConstraint(
            "enabled = false OR "
            "(rule_type = 'category' AND category IS NOT NULL "
            "AND reimbursement_note IS NULL) OR "
            "(rule_type = 'reimbursable' AND category IS NULL "
            "AND reimbursement_note IS NOT NULL)",
            name="ck_categorization_rules_payload",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "rule_type",
            "normalized_pattern",
            name="uq_categorization_rules_type_pattern",
        ),
    )
    op.create_index(
        "ix_categorization_rules_enabled_type",
        TABLE_NAME,
        ["enabled", "rule_type"],
        unique=False,
    )
    op.execute(ENABLE_RLS_SQL)


def downgrade() -> None:
    """Drop categorization rules; export private rules before downgrading."""
    op.drop_index(
        "ix_categorization_rules_enabled_type",
        table_name=TABLE_NAME,
    )
    op.drop_table(TABLE_NAME)
