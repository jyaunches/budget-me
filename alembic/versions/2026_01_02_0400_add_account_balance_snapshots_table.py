"""add_account_balance_snapshots_table

Revision ID: f600fd133273
Revises: 4bbf60d85196
Create Date: 2026-01-02 04:00:36.253273+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f600fd133273'
down_revision: Union[str, None] = '4bbf60d85196'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create account_balance_snapshots table."""
    op.create_table(
        'account_balance_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('account_id', sa.String(), nullable=False),
        sa.Column('snapshot_date', sa.Date(), nullable=False),
        sa.Column('balance_current', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('balance_available', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=False), server_default=sa.func.now(), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.account_id'], ),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('account_id', 'snapshot_date', name='uq_account_balance_snapshot')
    )
    op.create_index('ix_account_balance_snapshots_account_id', 'account_balance_snapshots', ['account_id'])
    op.create_index('ix_account_balance_snapshots_snapshot_date', 'account_balance_snapshots', ['snapshot_date'])


def downgrade() -> None:
    """Drop account_balance_snapshots table."""
    op.drop_index('ix_account_balance_snapshots_snapshot_date', table_name='account_balance_snapshots')
    op.drop_index('ix_account_balance_snapshots_account_id', table_name='account_balance_snapshots')
    op.drop_table('account_balance_snapshots')
