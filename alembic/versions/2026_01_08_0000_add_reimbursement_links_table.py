"""add_reimbursement_links_table

Revision ID: b6f2c3d4a789
Revises: a518f7b8387a
Create Date: 2026-01-08 00:00:00.000000+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'b6f2c3d4a789'
down_revision: Union[str, None] = 'a518f7b8387a'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create reimbursement_links table
    op.create_table(
        'reimbursement_links',
        sa.Column('id', postgresql.UUID(as_uuid=True), nullable=False, primary_key=True),
        sa.Column('expense_transaction_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('deposit_transaction_id', postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column('amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('linked_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.ForeignKeyConstraint(['expense_transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['deposit_transaction_id'], ['transactions.id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('expense_transaction_id', 'deposit_transaction_id', name='uq_reimbursement_expense_deposit'),
    )

    # Create indexes for query performance
    op.create_index('ix_reimbursement_links_expense_id', 'reimbursement_links', ['expense_transaction_id'], unique=False)
    op.create_index('ix_reimbursement_links_deposit_id', 'reimbursement_links', ['deposit_transaction_id'], unique=False)


def downgrade() -> None:
    # Drop indexes
    op.drop_index('ix_reimbursement_links_deposit_id', table_name='reimbursement_links')
    op.drop_index('ix_reimbursement_links_expense_id', table_name='reimbursement_links')

    # Drop table
    op.drop_table('reimbursement_links')
