"""Drop retired inbound-message storage from previously migrated databases.

Revision ID: d4a7e9c2f610
Revises: a38d91f0c4e2
Create Date: 2026-07-30 01:00:00+00:00

The historical messaging revisions are no-op compatibility markers in the
public source tree. Private installations that applied the original revisions
may still contain stored messages, so this follow-on migration normalizes both
installation paths by removing that table. Stored rows are intentionally not
recoverable through downgrade.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "d4a7e9c2f610"
down_revision: str | None = "a38d91f0c4e2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

DROP_LEGACY_MESSAGE_SQL = 'DROP TABLE IF EXISTS public."whatsapp_messages" CASCADE'


def upgrade() -> None:
    """Permanently remove retired inbound-message storage when it exists."""
    op.execute(DROP_LEGACY_MESSAGE_SQL)


def downgrade() -> None:
    """Do not recreate retired storage or purged message data."""
    # The preceding compatibility revisions no longer create this table, and
    # recreating an empty table would not restore deleted private messages.
    return None
