"""legacy message platform compatibility marker

Revision ID: b9014a2b4fc8
Revises: e25787f8a849
Create Date: 2026-01-29 04:33:32.071980+00:00

This revision previously expanded storage for a retired messaging integration.
Its identifier remains in the migration chain because later revisions depend
on it and deployed databases may already record it.
"""

from collections.abc import Sequence

# revision identifiers, used by Alembic.
revision: str = "b9014a2b4fc8"
down_revision: str | None = "e25787f8a849"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """Retain this applied revision without creating retired schema."""
    pass


def downgrade() -> None:
    """Retain this compatibility marker during downgrade."""
    pass
