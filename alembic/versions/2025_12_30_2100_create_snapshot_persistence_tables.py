"""Create snapshot persistence tables

Revision ID: 009_create_snapshot_tables
Revises: 008_add_promo_apr_fields
Create Date: 2025-12-30 21:00:00.000000

Creates tables for persisting monthly financial snapshots:
- monthly_snapshots: Header records for each month
- snapshot_line_items: Expenses and income per snapshot
- snapshot_credit_cards: Credit card state per snapshot
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "009_create_snapshot_tables"
down_revision: Union[str, None] = "008_add_promo_apr_fields"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create monthly_snapshots, snapshot_line_items, and snapshot_credit_cards tables."""
    # Create monthly_snapshots table
    op.create_table(
        "monthly_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("year_month", sa.String(7), nullable=False, unique=True),
        sa.Column("status", sa.String(10), nullable=False, server_default="open"),
        sa.Column("income_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("expense_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("credit_card_total", sa.Numeric(12, 2), nullable=True),
        sa.Column("net", sa.Numeric(12, 2), nullable=True),
        sa.Column(
            "closed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
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
    )

    # Create indexes for monthly_snapshots
    op.create_index(
        "ix_monthly_snapshots_year_month",
        "monthly_snapshots",
        ["year_month"],
    )
    op.create_index(
        "ix_monthly_snapshots_status",
        "monthly_snapshots",
        ["status"],
    )

    # Create snapshot_line_items table
    op.create_table(
        "snapshot_line_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monthly_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column(
            "source_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("anticipated_items.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("is_one_time", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("skipped", sa.Boolean(), nullable=False, server_default=sa.text("false")),
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
    )

    # Create indexes for snapshot_line_items
    op.create_index(
        "ix_snapshot_line_items_snapshot_id_item_type",
        "snapshot_line_items",
        ["snapshot_id", "item_type"],
    )
    op.create_index(
        "ix_snapshot_line_items_source_item_id",
        "snapshot_line_items",
        ["source_item_id"],
    )

    # Create snapshot_credit_cards table
    op.create_table(
        "snapshot_credit_cards",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "snapshot_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("monthly_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("statement_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("payment_strategy", sa.String(30), nullable=False),
        sa.Column("fixed_payment_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("calculated_payment", sa.Numeric(12, 2), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=True),
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
    )

    # Create unique constraint and index for snapshot_credit_cards
    op.create_unique_constraint(
        "uq_snapshot_credit_cards_snapshot_account",
        "snapshot_credit_cards",
        ["snapshot_id", "account_id"],
    )
    op.create_index(
        "ix_snapshot_credit_cards_snapshot_id",
        "snapshot_credit_cards",
        ["snapshot_id"],
    )


def downgrade() -> None:
    """Drop snapshot tables."""
    # Drop snapshot_credit_cards table (drop constraint first)
    op.drop_constraint(
        "uq_snapshot_credit_cards_snapshot_account",
        "snapshot_credit_cards",
        type_="unique",
    )
    op.drop_index("ix_snapshot_credit_cards_snapshot_id", "snapshot_credit_cards")
    op.drop_table("snapshot_credit_cards")

    # Drop snapshot_line_items table
    op.drop_index("ix_snapshot_line_items_source_item_id", "snapshot_line_items")
    op.drop_index("ix_snapshot_line_items_snapshot_id_item_type", "snapshot_line_items")
    op.drop_table("snapshot_line_items")

    # Drop monthly_snapshots table
    op.drop_index("ix_monthly_snapshots_status", "monthly_snapshots")
    op.drop_index("ix_monthly_snapshots_year_month", "monthly_snapshots")
    op.drop_table("monthly_snapshots")
