"""Add loan_details table for tracking mortgage and auto loans

Revision ID: 010_add_loan_details
Revises: 3ab78eb5fad1
Create Date: 2025-12-31 10:30:00.000000

Adds support for manual loan tracking:
- Create loan_details table linked to accounts
- Store interest rate, monthly payment, maturity date
- Support mortgage, auto, personal, student loans
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "010_add_loan_details"
down_revision: Union[str, None] = "3ab78eb5fad1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create loan_details table."""
    op.create_table(
        "loan_details",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "account_id",
            sa.String(255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("loan_type", sa.String(20), nullable=False),
        sa.Column("interest_rate", sa.Numeric(6, 4), nullable=False),
        sa.Column("monthly_payment", sa.Numeric(12, 2), nullable=False),
        sa.Column("maturity_date", sa.Date(), nullable=False),
        sa.Column("original_amount", sa.Numeric(12, 2), nullable=True),
        sa.Column("loan_start_date", sa.Date(), nullable=True),
        sa.Column("remaining_payments", sa.Integer(), nullable=True),
        sa.Column("lender_name", sa.String(255), nullable=True),
        sa.Column("collateral_description", sa.String(500), nullable=True),
        sa.Column("source", sa.String(20), nullable=False, server_default="manual"),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    # Create indexes for common query patterns
    op.create_index("ix_loan_details_loan_type", "loan_details", ["loan_type"])
    op.create_index("ix_loan_details_maturity_date", "loan_details", ["maturity_date"])


def downgrade() -> None:
    """Drop loan_details table."""
    op.drop_index("ix_loan_details_maturity_date", "loan_details")
    op.drop_index("ix_loan_details_loan_type", "loan_details")
    op.drop_table("loan_details")
