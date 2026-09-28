"""add_projected_monthly_payment_to_accounts

Revision ID: 4741692f7c3e
Revises: f6c84b4d76d1
Create Date: 2026-01-09 20:41:39.555154+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4741692f7c3e'
down_revision: Union[str, None] = 'f6c84b4d76d1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add projected_monthly_payment column to accounts table."""
    op.add_column(
        'accounts',
        sa.Column('projected_monthly_payment', sa.Numeric(precision=12, scale=2), nullable=True)
    )


def downgrade() -> None:
    """Remove projected_monthly_payment column from accounts table."""
    op.drop_column('accounts', 'projected_monthly_payment')
