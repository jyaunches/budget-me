"""add category_budgets table

Revision ID: 5440489bed64
Revises: 2c9efb1b373b
Create Date: 2026-01-02 23:44:23.588875+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID


# revision identifiers, used by Alembic.
revision: str = '5440489bed64'
down_revision: Union[str, None] = '2c9efb1b373b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create category_budgets table
    op.create_table(
        'category_budgets',
        sa.Column('id', UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column('account_id', sa.String(length=255), nullable=False),
        sa.Column('year_month', sa.String(length=7), nullable=False),
        sa.Column('category', sa.String(length=100), nullable=False),
        sa.Column('budget_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(['account_id'], ['accounts.account_id'], ondelete='CASCADE'),
        sa.UniqueConstraint('account_id', 'year_month', 'category', name='uq_category_budgets_account_month_category'),
    )

    # Create index for efficient queries
    op.create_index(
        'ix_category_budgets_account_month',
        'category_budgets',
        ['account_id', 'year_month'],
        unique=False
    )


def downgrade() -> None:
    # Drop index
    op.drop_index('ix_category_budgets_account_month', table_name='category_budgets')

    # Drop table
    op.drop_table('category_budgets')
