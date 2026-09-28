"""Add accounts table

Revision ID: 002_accounts
Revises: 001_initial
Create Date: 2025-12-28 21:55:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "002_accounts"
down_revision: Union[str, None] = "001_initial"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create accounts table
    op.create_table(
        "accounts",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(255), nullable=False, unique=True),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("type", sa.String(50), nullable=False),
        sa.Column("subtype", sa.String(50), nullable=True),
        sa.Column("mask", sa.String(10), nullable=True),
        sa.Column("balance_available", sa.Numeric(12, 2), nullable=True),
        sa.Column("balance_current", sa.Numeric(12, 2), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create index on account_id for efficient joins with transactions
    op.create_index("ix_accounts_account_id", "accounts", ["account_id"])


def downgrade() -> None:
    # Drop index first
    op.drop_index("ix_accounts_account_id", "accounts")

    # Drop accounts table
    op.drop_table("accounts")
