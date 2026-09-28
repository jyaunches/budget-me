"""add_per_account_snapshot_columns

Revision ID: 4bbf60d85196
Revises: 012_add_transfer_totals
Create Date: 2025-12-31 20:12:56.522682+00:00

Adds per-account support for monthly snapshots:
- account_id column to monthly_snapshots (FK to accounts)
- account_id column to anticipated_items (FK to accounts)
- paying_account_id column to accounts (self-referential FK)
- Updates unique constraint on monthly_snapshots to (year_month, account_id)
- Assigns legacy unscoped rows to the first available account
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '4bbf60d85196'
down_revision: Union[str, None] = '012_add_transfer_totals'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add per-account columns and migrate data."""
    # 1. Add account_id column to monthly_snapshots
    op.add_column(
        "monthly_snapshots",
        sa.Column("account_id", sa.String(255), nullable=True)
    )

    # 2. Add account_id column to anticipated_items
    op.add_column(
        "anticipated_items",
        sa.Column("account_id", sa.String(255), nullable=True)
    )

    # 3. Add paying_account_id column to accounts (self-referential)
    op.add_column(
        "accounts",
        sa.Column("paying_account_id", sa.String(255), nullable=True)
    )

    # 4. Add foreign key constraints
    op.create_foreign_key(
        "fk_monthly_snapshots_account_id",
        "monthly_snapshots",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="SET NULL"
    )

    op.create_foreign_key(
        "fk_anticipated_items_account_id",
        "anticipated_items",
        "accounts",
        ["account_id"],
        ["account_id"],
        ondelete="SET NULL"
    )

    op.create_foreign_key(
        "fk_accounts_paying_account_id",
        "accounts",
        "accounts",
        ["paying_account_id"],
        ["account_id"],
        ondelete="SET NULL"
    )

    # 5. Assign legacy unscoped rows to a deterministic existing account.
    # Existing private installations have already applied this revision.
    op.execute("""
        UPDATE monthly_snapshots
        SET account_id = (
            SELECT account_id
            FROM accounts
            ORDER BY account_id
            LIMIT 1
        )
        WHERE account_id IS NULL
    """)

    op.execute("""
        UPDATE anticipated_items
        SET account_id = (
            SELECT account_id
            FROM accounts
            ORDER BY account_id
            LIMIT 1
        )
        WHERE account_id IS NULL
    """)

    # 6. Drop old unique constraint on monthly_snapshots
    op.drop_constraint(
        "monthly_snapshots_year_month_key",
        "monthly_snapshots",
        type_="unique"
    )

    # 7. Create new composite unique constraint
    op.create_unique_constraint(
        "uq_monthly_snapshots_year_month_account",
        "monthly_snapshots",
        ["year_month", "account_id"]
    )

    # 8. Create index on account_id for better query performance
    op.create_index(
        "ix_monthly_snapshots_account_id",
        "monthly_snapshots",
        ["account_id"]
    )


def downgrade() -> None:
    """Remove per-account columns and restore original schema."""
    # 1. Drop indexes
    op.drop_index("ix_monthly_snapshots_account_id", table_name="monthly_snapshots")

    # 2. Drop new unique constraint
    op.drop_constraint(
        "uq_monthly_snapshots_year_month_account",
        "monthly_snapshots",
        type_="unique"
    )

    # 3. Restore old unique constraint
    op.create_unique_constraint(
        "monthly_snapshots_year_month_key",
        "monthly_snapshots",
        ["year_month"]
    )

    # 4. Drop foreign key constraints
    op.drop_constraint(
        "fk_accounts_paying_account_id",
        "accounts",
        type_="foreignkey"
    )

    op.drop_constraint(
        "fk_anticipated_items_account_id",
        "anticipated_items",
        type_="foreignkey"
    )

    op.drop_constraint(
        "fk_monthly_snapshots_account_id",
        "monthly_snapshots",
        type_="foreignkey"
    )

    # 5. Drop columns
    op.drop_column("accounts", "paying_account_id")
    op.drop_column("anticipated_items", "account_id")
    op.drop_column("monthly_snapshots", "account_id")
