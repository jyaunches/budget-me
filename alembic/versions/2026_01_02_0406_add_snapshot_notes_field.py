"""add_snapshot_notes_field

Revision ID: 5d2b47688f16
Revises: f600fd133273
Create Date: 2026-01-02 04:06:21.913782+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5d2b47688f16'
down_revision: Union[str, None] = 'f600fd133273'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'monthly_snapshots',
        sa.Column('notes', sa.Text(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('monthly_snapshots', 'notes')
