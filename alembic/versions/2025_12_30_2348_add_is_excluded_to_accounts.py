"""Add is_excluded column to accounts table

Revision ID: 011_add_is_excluded
Revises: 010_add_loan_details
Create Date: 2025-12-30 23:48:00.000000

Adds ability to exclude accounts from operations while preserving historical data.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "011_add_is_excluded"
down_revision: Union[str, None] = "010_add_loan_details"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add is_excluded column to accounts table."""
    op.add_column(
        "accounts",
        sa.Column("is_excluded", sa.Boolean(), nullable=False, server_default="false"),
    )


def downgrade() -> None:
    """Remove is_excluded column from accounts table."""
    op.drop_column("accounts", "is_excluded")
