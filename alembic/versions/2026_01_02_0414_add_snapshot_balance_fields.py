"""add snapshot balance fields

Revision ID: c6db3c909dd4
Revises: 5d2b47688f16
Create Date: 2026-01-02 04:14:22.815272+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c6db3c909dd4'
down_revision: Union[str, None] = '5d2b47688f16'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add balance fields to monthly_snapshots table
    op.add_column(
        'monthly_snapshots',
        sa.Column('starting_balance', sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        'monthly_snapshots',
        sa.Column('closing_balance', sa.Numeric(precision=12, scale=2), nullable=True)
    )
    op.add_column(
        'monthly_snapshots',
        sa.Column('closing_balance_frozen', sa.Boolean(), nullable=False, server_default='false')
    )


def downgrade() -> None:
    # Remove balance fields from monthly_snapshots table
    op.drop_column('monthly_snapshots', 'closing_balance_frozen')
    op.drop_column('monthly_snapshots', 'closing_balance')
    op.drop_column('monthly_snapshots', 'starting_balance')
