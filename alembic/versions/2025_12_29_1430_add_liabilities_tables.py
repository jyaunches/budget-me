"""Add liabilities tables and products tracking

Revision ID: 005_add_liabilities
Revises: 004_add_reviewed
Create Date: 2025-12-29 14:30:00.000000

Adds support for Plaid Liabilities product:
- Add products JSONB column to plaid_items
- Create credit_liabilities table
- Create credit_liability_aprs table
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "005_add_liabilities"
down_revision: Union[str, None] = "004_add_reviewed"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add products field to plaid_items and create liabilities tables."""
    # Add products JSONB column to plaid_items with default
    op.add_column(
        "plaid_items",
        sa.Column(
            "products",
            postgresql.JSONB,
            nullable=False,
            server_default=sa.text("'[\"transactions\"]'::jsonb"),
        ),
    )

    # Create credit_liabilities table
    op.create_table(
        "credit_liabilities",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("is_overdue", sa.Boolean(), nullable=True),
        sa.Column("last_payment_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("last_payment_date", sa.Date(), nullable=True),
        sa.Column("last_statement_balance", sa.Numeric(12, 2), nullable=True),
        sa.Column("last_statement_issue_date", sa.Date(), nullable=True),
        sa.Column("minimum_payment_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("next_payment_due_date", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create index on plaid_item_id for efficient lookups
    op.create_index("ix_credit_liabilities_plaid_item_id", "credit_liabilities", ["plaid_item_id"])

    # Create credit_liability_aprs table
    op.create_table(
        "credit_liability_aprs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "credit_liability_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("credit_liabilities.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("apr_type", sa.String(50), nullable=False),
        sa.Column("apr_percentage", sa.Numeric(6, 2), nullable=False),
        sa.Column("balance_subject_to_apr", sa.Numeric(12, 2), nullable=True),
        sa.Column("interest_charge_amount", sa.Numeric(12, 2), nullable=True),
    )

    # Create index on credit_liability_id for efficient joins
    op.create_index("ix_credit_liability_aprs_liability_id", "credit_liability_aprs", ["credit_liability_id"])


def downgrade() -> None:
    """Remove liabilities tables and products field."""
    # Drop indexes first
    op.drop_index("ix_credit_liability_aprs_liability_id", "credit_liability_aprs")
    op.drop_index("ix_credit_liabilities_plaid_item_id", "credit_liabilities")

    # Drop tables
    op.drop_table("credit_liability_aprs")
    op.drop_table("credit_liabilities")

    # Drop products column from plaid_items
    op.drop_column("plaid_items", "products")
