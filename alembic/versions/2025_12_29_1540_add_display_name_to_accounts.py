"""Add display_name column to accounts table

Revision ID: 006_add_display_name
Revises: 005_add_liabilities
Create Date: 2025-12-29 15:40:00.000000

Adds a user-editable display_name field that persists across Plaid syncs.
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "006_add_display_name"
down_revision: Union[str, None] = "005_add_liabilities"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add display_name column to accounts table."""
    op.add_column(
        "accounts",
        sa.Column("display_name", sa.String(255), nullable=True),
    )


def downgrade() -> None:
    """Remove display_name column from accounts table."""
    op.drop_column("accounts", "display_name")
