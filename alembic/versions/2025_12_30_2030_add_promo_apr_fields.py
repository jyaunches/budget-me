"""Add promotional APR tracking fields

Revision ID: 008_add_promo_apr_fields
Revises: 007_add_monthly_snapshot
Create Date: 2025-12-30 20:30:00.000000

Adds support for promotional APR tracking:
- Add promo_rate_end_date to track when promotional rates expire
- Add promo_offer_id to identify specific promotional offers
- Add source field to distinguish Plaid vs manually-entered APRs
- Create partial index on promo_rate_end_date for efficient expiration queries
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision: str = "008_add_promo_apr_fields"
down_revision: Union[str, None] = "007_add_monthly_snapshot"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Add promotional APR tracking fields to credit_liability_aprs table."""
    # Add promo_rate_end_date column
    op.add_column(
        "credit_liability_aprs",
        sa.Column("promo_rate_end_date", sa.Date(), nullable=True),
    )

    # Add promo_offer_id column
    op.add_column(
        "credit_liability_aprs",
        sa.Column("promo_offer_id", sa.String(100), nullable=True),
    )

    # Add source column with default 'plaid'
    op.add_column(
        "credit_liability_aprs",
        sa.Column(
            "source",
            sa.String(20),
            nullable=False,
            server_default="plaid",
        ),
    )

    # Create partial index on promo_rate_end_date for efficient expiration queries
    op.create_index(
        "ix_credit_liability_aprs_promo_end_date",
        "credit_liability_aprs",
        ["promo_rate_end_date"],
        postgresql_where=sa.text("promo_rate_end_date IS NOT NULL"),
    )


def downgrade() -> None:
    """Remove promotional APR tracking fields."""
    # Drop index first
    op.drop_index(
        "ix_credit_liability_aprs_promo_end_date",
        table_name="credit_liability_aprs",
    )

    # Drop columns
    op.drop_column("credit_liability_aprs", "source")
    op.drop_column("credit_liability_aprs", "promo_offer_id")
    op.drop_column("credit_liability_aprs", "promo_rate_end_date")
