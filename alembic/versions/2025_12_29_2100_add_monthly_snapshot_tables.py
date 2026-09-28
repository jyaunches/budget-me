"""Add monthly snapshot tables

Revision ID: 007_add_monthly_snapshot
Revises: 006_add_display_name
Create Date: 2025-12-29 21:00:00.000000

Adds support for monthly snapshot feature:
- Create anticipated_items table for recurring expenses/income
- Add payment_strategy and fixed_payment_amount to accounts table
- Create monthly_overrides table for per-month adjustments
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "007_add_monthly_snapshot"
down_revision: Union[str, None] = "006_add_display_name"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add anticipated_items, monthly_overrides tables and payment strategy to accounts."""
    # Create anticipated_items table
    op.create_table(
        "anticipated_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("item_type", sa.String(20), nullable=False),
        sa.Column("category", sa.String(100), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create index on item_type and active
    op.create_index(
        "ix_anticipated_items_item_type_active",
        "anticipated_items",
        ["item_type", "active"],
    )

    # Add payment strategy columns to accounts table
    op.add_column(
        "accounts",
        sa.Column(
            "payment_strategy",
            sa.String(30),
            nullable=False,
            server_default="pay_in_full",
        ),
    )
    op.add_column(
        "accounts",
        sa.Column("fixed_payment_amount", sa.Numeric(12, 2), nullable=True),
    )

    # Create monthly_overrides table
    op.create_table(
        "monthly_overrides",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("year_month", sa.String(7), nullable=False),
        sa.Column(
            "anticipated_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("anticipated_items.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("override_type", sa.String(20), nullable=False),
        sa.Column("name", sa.String(255), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("item_type", sa.String(20), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create unique constraint on (year_month, anticipated_item_id)
    op.create_unique_constraint(
        "uq_monthly_overrides_year_month_item",
        "monthly_overrides",
        ["year_month", "anticipated_item_id"],
    )


def downgrade() -> None:
    """Remove monthly snapshot tables and payment strategy from accounts."""
    # Drop unique constraint first
    op.drop_constraint(
        "uq_monthly_overrides_year_month_item", "monthly_overrides", type_="unique"
    )

    # Drop tables
    op.drop_table("monthly_overrides")

    # Drop index from anticipated_items
    op.drop_index("ix_anticipated_items_item_type_active", "anticipated_items")

    # Drop anticipated_items table
    op.drop_table("anticipated_items")

    # Drop payment strategy columns from accounts
    op.drop_column("accounts", "fixed_payment_amount")
    op.drop_column("accounts", "payment_strategy")
