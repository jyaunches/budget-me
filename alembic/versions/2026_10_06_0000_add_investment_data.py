"""Add Plaid investment securities, holdings, snapshots, and transactions.

Revision ID: c8f3b291d704
Revises: f5b6a7c8d901
Create Date: 2026-10-06 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "c8f3b291d704"
down_revision: str | None = "f5b6a7c8d901"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLES = (
    "investment_securities",
    "investment_holdings",
    "investment_holding_snapshots",
    "investment_transactions",
)


def _timestamps() -> tuple[sa.Column, sa.Column]:
    return (
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


def upgrade() -> None:
    op.create_table(
        "investment_securities",
        sa.Column("security_id", sa.String(length=255), primary_key=True),
        sa.Column("institution_security_id", sa.String(length=255)),
        sa.Column("institution_id", sa.String(length=255)),
        sa.Column("name", sa.Text()),
        sa.Column("ticker_symbol", sa.String(length=50)),
        sa.Column("security_type", sa.String(length=100)),
        sa.Column("close_price", sa.Numeric(24, 8)),
        sa.Column("close_price_as_of", sa.Date()),
        sa.Column("iso_currency_code", sa.String(length=3)),
        sa.Column("unofficial_currency_code", sa.String(length=20)),
        sa.Column("raw", postgresql.JSONB()),
        *_timestamps(),
    )
    op.create_table(
        "investment_holdings",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(length=255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "security_id",
            sa.String(length=255),
            sa.ForeignKey("investment_securities.security_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("institution_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("institution_price_as_of", sa.DateTime(timezone=True)),
        sa.Column("institution_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2)),
        sa.Column("iso_currency_code", sa.String(length=3)),
        sa.Column("unofficial_currency_code", sa.String(length=20)),
        sa.Column("raw", postgresql.JSONB()),
        *_timestamps(),
        sa.UniqueConstraint(
            "account_id",
            "security_id",
            name="uq_investment_holdings_account_security",
        ),
    )
    op.create_index(
        "ix_investment_holdings_plaid_item_id",
        "investment_holdings",
        ["plaid_item_id"],
    )
    op.create_index(
        "ix_investment_holdings_account_id", "investment_holdings", ["account_id"]
    )
    op.create_table(
        "investment_holding_snapshots",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(length=255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "security_id",
            sa.String(length=255),
            sa.ForeignKey("investment_securities.security_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("snapshot_date", sa.Date(), nullable=False),
        sa.Column("quantity", sa.Numeric(24, 8), nullable=False),
        sa.Column("institution_price", sa.Numeric(24, 8), nullable=False),
        sa.Column("institution_value", sa.Numeric(18, 2), nullable=False),
        sa.Column("cost_basis", sa.Numeric(18, 2)),
        sa.Column("iso_currency_code", sa.String(length=3)),
        sa.Column("unofficial_currency_code", sa.String(length=20)),
        *_timestamps(),
        sa.UniqueConstraint(
            "account_id",
            "security_id",
            "snapshot_date",
            name="uq_investment_holding_snapshots_account_security_date",
        ),
    )
    op.create_index(
        "ix_investment_holding_snapshots_item_date",
        "investment_holding_snapshots",
        ["plaid_item_id", "snapshot_date"],
    )
    op.create_table(
        "investment_transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "investment_transaction_id",
            sa.String(length=255),
            nullable=False,
            unique=True,
        ),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(length=255),
            sa.ForeignKey("accounts.account_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "security_id",
            sa.String(length=255),
            sa.ForeignKey("investment_securities.security_id", ondelete="SET NULL"),
        ),
        sa.Column("cancel_transaction_id", sa.String(length=255)),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount", sa.Numeric(18, 2), nullable=False),
        sa.Column("fees", sa.Numeric(18, 2)),
        sa.Column("price", sa.Numeric(24, 8)),
        sa.Column("quantity", sa.Numeric(24, 8)),
        sa.Column("transaction_type", sa.String(length=100)),
        sa.Column("subtype", sa.String(length=100)),
        sa.Column("iso_currency_code", sa.String(length=3)),
        sa.Column("unofficial_currency_code", sa.String(length=20)),
        sa.Column("raw", postgresql.JSONB()),
        *_timestamps(),
    )
    op.create_index(
        "ix_investment_transactions_item_date",
        "investment_transactions",
        ["plaid_item_id", "date"],
    )
    op.create_index(
        "ix_investment_transactions_account_id",
        "investment_transactions",
        ["account_id"],
    )

    for table in TABLES:
        op.execute(f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY')


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_table(table)
