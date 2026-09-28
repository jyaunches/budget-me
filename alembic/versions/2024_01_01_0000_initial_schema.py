"""Initial schema - all tables for Plaid ingestion pipeline

Revision ID: 001_initial
Revises:
Create Date: 2024-01-01 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    op.execute("CREATE TYPE plaid_item_status AS ENUM ('active', 'relink_required', 'revoked', 'pending')")
    op.execute("CREATE TYPE ingest_run_type AS ENUM ('scheduled', 'manual', 'webhook')")
    op.execute("CREATE TYPE ingest_run_status AS ENUM ('running', 'completed', 'failed', 'partial')")
    op.execute("CREATE TYPE ingest_run_item_status AS ENUM ('pending', 'success', 'failed', 'skipped')")

    # Create plaid_items table
    op.create_table(
        "plaid_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("user_key", sa.String(255), nullable=False, index=True),
        sa.Column("item_id", sa.String(255), nullable=False, unique=True),
        sa.Column("institution_id", sa.String(255), nullable=True),
        sa.Column("access_token_enc", sa.Text(), nullable=False),
        sa.Column(
            "status",
            postgresql.ENUM("active", "relink_required", "revoked", "pending", name="plaid_item_status", create_type=False),
            nullable=False,
            server_default="active",
        ),
        sa.Column("last_success_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error_code", sa.String(100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create plaid_cursors table
    op.create_table(
        "plaid_cursors",
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("transactions_cursor", sa.Text(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create transactions table
    op.create_table(
        "transactions",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("plaid_transaction_id", sa.String(255), nullable=False, unique=True),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(255), nullable=False),
        sa.Column("date", sa.Date(), nullable=False),
        sa.Column("authorized_date", sa.Date(), nullable=True),
        sa.Column("amount", sa.Numeric(12, 2), nullable=False),
        sa.Column("iso_currency_code", sa.String(3), nullable=True),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("merchant_name", sa.Text(), nullable=True),
        sa.Column("pending", sa.Boolean(), nullable=False, server_default="false"),
        sa.Column("payment_channel", sa.String(50), nullable=True),
        sa.Column("category_primary", sa.String(100), nullable=True),
        sa.Column("category_detailed", sa.String(100), nullable=True),
        sa.Column("merchant_id", sa.String(255), nullable=True),
        sa.Column("normalized_merchant", sa.String(255), nullable=True),
        sa.Column("raw", postgresql.JSONB(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create indexes for transactions
    op.create_index("ix_transactions_date", "transactions", ["date"])
    op.create_index("ix_transactions_plaid_item_id_date", "transactions", ["plaid_item_id", "date"])
    op.create_index("ix_transactions_account_id", "transactions", ["account_id"])

    # Create merchant_rules table
    op.create_table(
        "merchant_rules",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("pattern", sa.Text(), nullable=False),
        sa.Column("replacement", sa.Text(), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("enabled", sa.Boolean(), nullable=False, server_default="true"),
    )

    # Create merchant_map table
    op.create_table(
        "merchant_map",
        sa.Column("input_name", sa.String(255), primary_key=True),
        sa.Column("normalized", sa.String(255), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # Create ingest_runs table
    op.create_table(
        "ingest_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "run_type",
            postgresql.ENUM("scheduled", "manual", "webhook", name="ingest_run_type", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("running", "completed", "failed", "partial", name="ingest_run_status", create_type=False),
            nullable=False,
            server_default="running",
        ),
        sa.Column("items_total", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_ok", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("items_failed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tx_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tx_modified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tx_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_summary", sa.Text(), nullable=True),
    )

    # Create ingest_run_items table
    op.create_table(
        "ingest_run_items",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "ingest_run_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("ingest_runs.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "plaid_item_id",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("plaid_items.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "status",
            postgresql.ENUM("pending", "success", "failed", "skipped", name="ingest_run_item_status", create_type=False),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("tx_added", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tx_modified", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("tx_removed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("error_code", sa.String(100), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
    )


def downgrade() -> None:
    # Drop tables in reverse order (respecting foreign keys)
    op.drop_table("ingest_run_items")
    op.drop_table("ingest_runs")
    op.drop_table("merchant_map")
    op.drop_table("merchant_rules")
    op.drop_table("transactions")
    op.drop_table("plaid_cursors")
    op.drop_table("plaid_items")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS ingest_run_item_status")
    op.execute("DROP TYPE IF EXISTS ingest_run_status")
    op.execute("DROP TYPE IF EXISTS ingest_run_type")
    op.execute("DROP TYPE IF EXISTS plaid_item_status")
