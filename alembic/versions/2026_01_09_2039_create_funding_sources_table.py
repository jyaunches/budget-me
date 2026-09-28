"""create_funding_sources_table

Revision ID: f6c84b4d76d1
Revises: 4e4dca40c5ec
Create Date: 2026-01-09 20:39:39.119785+00:00

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'f6c84b4d76d1'
down_revision: Union[str, None] = '4e4dca40c5ec'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create funding_sources table."""
    op.create_table(
        'funding_sources',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, server_default=sa.text('gen_random_uuid()')),
        sa.Column('name', sa.String(length=255), nullable=False),
        sa.Column('source_type', sa.String(length=30), nullable=False),
        sa.Column('available_amount', sa.Numeric(precision=12, scale=2), nullable=False),
        sa.Column('notes', sa.Text(), nullable=True),
        sa.Column('active', sa.Boolean(), nullable=False, server_default='true'),
        sa.Column('created_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('updated_at', sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.text('now()')),
    )


def downgrade() -> None:
    """Drop funding_sources table."""
    op.drop_table('funding_sources')
