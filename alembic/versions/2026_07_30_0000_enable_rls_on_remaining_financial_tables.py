"""Enable RLS on financial tables added after the original RLS migration.

Revision ID: a38d91f0c4e2
Revises: 5db7aa663bb5
Create Date: 2026-07-30 00:00:00.000000

The original RLS migration predates several financial tables added later.
This migration closes that gap. Enabling RLS with no policies blocks access
through Supabase's public API while preserving the app's direct database access.
"""

from collections.abc import Sequence

from alembic import op

revision: str = "a38d91f0c4e2"
down_revision: str | None = "5db7aa663bb5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Current financial tables created after 003_enable_rls.
TABLES = (
    "credit_liabilities",
    "credit_liability_aprs",
    "anticipated_items",
    "monthly_snapshots",
    "snapshot_line_items",
    "snapshot_credit_cards",
    "loan_details",
    "account_balance_snapshots",
    "category_budgets",
    "reimbursement_links",
    "funding_sources",
)


def upgrade() -> None:
    """Enable RLS to block public API access when no policies are defined."""
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    """Disable RLS only for tables covered by this migration."""
    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" DISABLE ROW LEVEL SECURITY')
