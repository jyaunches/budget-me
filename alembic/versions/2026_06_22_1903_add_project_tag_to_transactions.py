"""add_project_tag_to_transactions

Revision ID: 5db7aa663bb5
Revises: 5a9fe94b6e75
Create Date: 2026-06-22 19:03:20.089252+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5db7aa663bb5'
down_revision: Union[str, None] = '5a9fe94b6e75'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'transactions',
        sa.Column('project_tag', sa.String(length=100), nullable=True),
    )
    op.create_index(
        op.f('ix_transactions_project_tag'),
        'transactions',
        ['project_tag'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_transactions_project_tag'), table_name='transactions')
    op.drop_column('transactions', 'project_tag')
