"""Enable Row Level Security on all tables

Revision ID: 003_enable_rls
Revises: 002_accounts
Create Date: 2025-12-29 11:21:00.000000

Supabase exposes tables in the public schema via its REST API.
Without RLS, anyone with the anon key could access data.
Enabling RLS with no policies blocks all API access while
direct PostgreSQL connections (used by our app) still work.
"""

from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "003_enable_rls"
down_revision: Union[str, None] = "002_accounts"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# All tables that need RLS enabled
TABLES = [
    "plaid_items",
    "plaid_cursors",
    "transactions",
    "accounts",
    "merchant_rules",
    "merchant_map",
    "ingest_runs",
    "ingest_run_items",
]


def upgrade() -> None:
    """Enable RLS on all tables to block Supabase API access."""
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")


def downgrade() -> None:
    """Disable RLS on all tables (not recommended for production)."""
    for table in TABLES:
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")
