"""Add reviewed field to transactions

Revision ID: 004_add_reviewed
Revises: 003_enable_rls
Create Date: 2025-12-29 13:51:00.000000

Adds reviewed tracking fields to transactions table for the
Streamlit transaction review UI.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "004_add_reviewed"
down_revision: Union[str, None] = "003_enable_rls"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add reviewed and reviewed_at columns to transactions."""
    # Add reviewed column with default false
    op.add_column(
        "transactions",
        sa.Column("reviewed", sa.Boolean(), nullable=False, server_default=sa.text("false")),
    )
    # Add reviewed_at timestamp column
    op.add_column(
        "transactions",
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Add index for filtering by reviewed status
    op.create_index("ix_transactions_reviewed", "transactions", ["reviewed"])

    # Enable RLS on the new column (table already has RLS from 003_enable_rls)


def downgrade() -> None:
    """Remove reviewed tracking columns."""
    op.drop_index("ix_transactions_reviewed", "transactions")
    op.drop_column("transactions", "reviewed_at")
    op.drop_column("transactions", "reviewed")
