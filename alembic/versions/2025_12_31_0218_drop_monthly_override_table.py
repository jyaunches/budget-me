"""drop_monthly_override_table

Revision ID: 3ab78eb5fad1
Revises: 009_create_snapshot_tables
Create Date: 2025-12-31 02:18:46.150300+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3ab78eb5fad1'
down_revision: Union[str, None] = '009_create_snapshot_tables'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Drop monthly_overrides table - replaced by snapshot tables."""
    op.drop_table('monthly_overrides')


def downgrade() -> None:
    """Recreate monthly_overrides table if needed."""
    op.create_table(
        'monthly_overrides',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('year_month', sa.String(length=7), nullable=False),
        sa.Column('anticipated_item_id', sa.UUID(), nullable=True),
        sa.Column('override_type', sa.String(length=20), nullable=False),
        sa.Column('name', sa.String(length=255), nullable=True),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=True),
        sa.Column('item_type', sa.String(length=20), nullable=True),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint('id'),
        sa.ForeignKeyConstraint(['anticipated_item_id'], ['anticipated_items.id'], ondelete='SET NULL'),
    )
    op.create_index('ix_monthly_overrides_year_month', 'monthly_overrides', ['year_month'])
    op.create_index('ix_monthly_overrides_anticipated_item_id', 'monthly_overrides', ['anticipated_item_id'])
