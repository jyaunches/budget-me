"""Add transfer_in_total and transfer_out_total columns to monthly_snapshots

Revision ID: 012_add_transfer_totals
Revises: 011_add_is_excluded
Create Date: 2025-12-31 04:52:00.000000

Adds support for tracking transfers in and out separately from income/expenses.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "012_add_transfer_totals"
down_revision: Union[str, None] = ("750d0c557895", "011_add_is_excluded")
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add transfer_in_total and transfer_out_total columns to monthly_snapshots."""
    op.add_column(
        "monthly_snapshots",
        sa.Column("transfer_in_total", sa.Numeric(precision=12, scale=2), nullable=True),
    )
    op.add_column(
        "monthly_snapshots",
        sa.Column("transfer_out_total", sa.Numeric(precision=12, scale=2), nullable=True),
    )


def downgrade() -> None:
    """Remove transfer_in_total and transfer_out_total columns from monthly_snapshots."""
    op.drop_column("monthly_snapshots", "transfer_out_total")
    op.drop_column("monthly_snapshots", "transfer_in_total")
