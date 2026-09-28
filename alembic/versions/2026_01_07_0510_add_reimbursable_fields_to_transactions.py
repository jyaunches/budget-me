"""add_reimbursable_fields_to_transactions

Revision ID: a518f7b8387a
Revises: 5440489bed64
Create Date: 2026-01-07 05:10:36.305499+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'a518f7b8387a'
down_revision: Union[str, None] = '5440489bed64'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Add reimbursable tracking fields
    op.add_column('transactions', sa.Column('reimbursable', sa.Boolean(), nullable=True))
    op.add_column('transactions', sa.Column('reimbursement_status', sa.String(length=20), nullable=True))
    op.add_column('transactions', sa.Column('reimbursement_note', sa.String(length=255), nullable=True))

    # Add index on reimbursable column for query performance
    op.create_index('ix_transactions_reimbursable', 'transactions', ['reimbursable'], unique=False)


def downgrade() -> None:
    # Remove index
    op.drop_index('ix_transactions_reimbursable', table_name='transactions')

    # Remove columns
    op.drop_column('transactions', 'reimbursement_note')
    op.drop_column('transactions', 'reimbursement_status')
    op.drop_column('transactions', 'reimbursable')
