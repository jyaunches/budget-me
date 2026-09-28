"""add_institution_name_to_plaid_items

Revision ID: 5a9fe94b6e75
Revises: b9014a2b4fc8
Create Date: 2026-02-02 14:27:07.753624+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5a9fe94b6e75'
down_revision: Union[str, None] = 'b9014a2b4fc8'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'plaid_items',
        sa.Column('institution_name', sa.String(255), nullable=True)
    )


def downgrade() -> None:
    op.drop_column('plaid_items', 'institution_name')
