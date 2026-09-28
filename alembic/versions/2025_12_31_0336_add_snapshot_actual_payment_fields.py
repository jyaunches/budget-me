"""add_snapshot_actual_payment_fields

Revision ID: 750d0c557895
Revises: 010_add_loan_details
Create Date: 2025-12-31 03:36:39.774101+00:00

Add fields to track actual credit card payments and sync timestamps:
- Add last_synced_at to monthly_snapshots table
- Add actual_payment_amount and actual_payment_date to snapshot_credit_cards table
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '750d0c557895'
down_revision: Union[str, None] = '010_add_loan_details'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add actual payment tracking fields to snapshot tables."""
    # Add last_synced_at to monthly_snapshots
    op.add_column(
        "monthly_snapshots",
        sa.Column(
            "last_synced_at",
            postgresql.TIMESTAMP(timezone=True),
            nullable=True,
        ),
    )

    # Add actual payment fields to snapshot_credit_cards
    op.add_column(
        "snapshot_credit_cards",
        sa.Column("actual_payment_amount", sa.Numeric(12, 2), nullable=True),
    )
    op.add_column(
        "snapshot_credit_cards",
        sa.Column("actual_payment_date", sa.Date(), nullable=True),
    )


def downgrade() -> None:
    """Remove actual payment tracking fields."""
    # Remove columns from snapshot_credit_cards
    op.drop_column("snapshot_credit_cards", "actual_payment_date")
    op.drop_column("snapshot_credit_cards", "actual_payment_amount")

    # Remove column from monthly_snapshots
    op.drop_column("monthly_snapshots", "last_synced_at")
