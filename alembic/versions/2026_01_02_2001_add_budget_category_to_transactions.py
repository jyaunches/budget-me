"""add budget_category to transactions

Revision ID: 2c9efb1b373b
Revises: c6db3c909dd4
Create Date: 2026-01-02 20:01:35.066924+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2c9efb1b373b'
down_revision: Union[str, None] = 'c6db3c909dd4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add budget_category column to transactions table
    op.add_column(
        'transactions',
        sa.Column('budget_category', sa.String(length=50), nullable=True)
    )
    # Create index on budget_category for efficient filtering
    op.create_index(
        'ix_transactions_budget_category',
        'transactions',
        ['budget_category'],
        unique=False
    )


def downgrade() -> None:
    # Remove index and column
    op.drop_index('ix_transactions_budget_category', table_name='transactions')
    op.drop_column('transactions', 'budget_category')
