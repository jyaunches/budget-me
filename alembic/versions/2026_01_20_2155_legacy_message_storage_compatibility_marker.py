"""legacy message storage compatibility marker

Revision ID: e25787f8a849
Revises: 4741692f7c3e
Create Date: 2026-01-20 21:55:15.002442+00:00

This revision previously created storage for a retired messaging integration.
Its identifier remains in the migration chain for databases that already
recorded it.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "e25787f8a849"
down_revision: str | None = "4741692f7c3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Retain this applied revision without creating retired schema."""
    pass


def downgrade() -> None:
    """Retain this compatibility marker during downgrade."""
    pass
