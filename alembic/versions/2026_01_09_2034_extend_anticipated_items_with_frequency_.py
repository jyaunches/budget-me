"""extend_anticipated_items_with_frequency_and_dates

Revision ID: 4e4dca40c5ec
Revises: b6f2c3d4a789
Create Date: 2026-01-09 20:34:07.268588+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4e4dca40c5ec'
down_revision: Union[str, None] = 'b6f2c3d4a789'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add frequency, start_month, and end_month to anticipated_items table."""
    # Add frequency column with default 'monthly'
    op.add_column(
        'anticipated_items',
        sa.Column('frequency', sa.String(length=20), nullable=False, server_default='monthly')
    )

    # Add start_month column (nullable)
    op.add_column(
        'anticipated_items',
        sa.Column('start_month', sa.String(length=7), nullable=True)
    )

    # Add end_month column (nullable)
    op.add_column(
        'anticipated_items',
        sa.Column('end_month', sa.String(length=7), nullable=True)
    )


def downgrade() -> None:
    """Remove frequency, start_month, and end_month from anticipated_items table."""
    op.drop_column('anticipated_items', 'end_month')
    op.drop_column('anticipated_items', 'start_month')
    op.drop_column('anticipated_items', 'frequency')
