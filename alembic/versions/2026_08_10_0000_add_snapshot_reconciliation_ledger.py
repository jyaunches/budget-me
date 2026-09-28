"""Add the immutable snapshot reconciliation ledger.

Revision ID: e7b4c2d91a60
Revises: c21f6a9d8e34
Create Date: 2026-08-10 00:00:00+00:00

The ledger preserves copied transaction facts instead of foreign-keying source
transactions, records normalized allocations and line-item resolutions, and
enables row-level security without public policies on every new table.
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql
from sqlalchemy.sql.elements import TextClause

revision: str = "e7b4c2d91a60"
down_revision: str | None = "c21f6a9d8e34"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

RUNS_TABLE = "snapshot_reconciliation_runs"
TRANSACTION_RESOLUTIONS_TABLE = "snapshot_transaction_resolutions"
TRANSACTION_ALLOCATIONS_TABLE = "snapshot_transaction_allocations"
LINE_ITEM_RESOLUTIONS_TABLE = "snapshot_line_item_resolutions"
LINE_ITEM_MATCHES_TABLE = "snapshot_line_item_matches"

LEDGER_TABLES = (
    RUNS_TABLE,
    TRANSACTION_RESOLUTIONS_TABLE,
    TRANSACTION_ALLOCATIONS_TABLE,
    LINE_ITEM_RESOLUTIONS_TABLE,
    LINE_ITEM_MATCHES_TABLE,
)
ENABLE_RLS_SQL = tuple(
    f'ALTER TABLE public."{table}" ENABLE ROW LEVEL SECURITY' for table in LEDGER_TABLES
)

FLOW_TYPE_SQL = (
    "'income', 'expense', 'transfer_in', 'transfer_out', "
    "'reimbursement_in', 'reimbursement_out', 'card_payment'"
)
ADJUSTMENT_FLOW_TYPE_SQL = (
    "'income', 'expense', 'transfer_in', 'transfer_out', "
    "'reimbursement_in', 'reimbursement_out'"
)

ALLOCATION_TOTAL_FUNCTION_NAME = "enforce_snapshot_transaction_allocation_total"
ALLOCATION_RESOLUTION_TRIGGER_NAME = (
    "ck_snapshot_transaction_resolution_allocation_total"
)
ALLOCATION_MUTATION_TRIGGER_NAME = "ck_snapshot_transaction_allocation_total"
MATCH_RUN_FUNCTION_NAME = "enforce_snapshot_line_item_match_same_run"
MATCH_RUN_TRIGGER_NAME = "ck_snapshot_line_item_match_same_run"
RUN_IMMUTABILITY_FUNCTION_NAME = "enforce_snapshot_reconciliation_run_immutability"
RUN_IMMUTABILITY_TRIGGER_NAME = "ck_snapshot_reconciliation_run_immutable"
CHILD_IMMUTABILITY_FUNCTION_NAME = "reject_snapshot_reconciliation_child_mutation"
CHILD_IMMUTABILITY_TRIGGERS = (
    (
        TRANSACTION_RESOLUTIONS_TABLE,
        "ck_snapshot_transaction_resolution_immutable",
    ),
    (
        TRANSACTION_ALLOCATIONS_TABLE,
        "ck_snapshot_transaction_allocation_immutable",
    ),
    (
        LINE_ITEM_RESOLUTIONS_TABLE,
        "ck_snapshot_line_item_resolution_immutable",
    ),
    (
        LINE_ITEM_MATCHES_TABLE,
        "ck_snapshot_line_item_match_immutable",
    ),
)

CREATE_ALLOCATION_TOTAL_FUNCTION_SQL = f"""
CREATE FUNCTION public.{ALLOCATION_TOTAL_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
DECLARE
    resolution_to_check uuid;
    previous_resolution_to_check uuid;
BEGIN
    IF TG_TABLE_NAME = '{TRANSACTION_RESOLUTIONS_TABLE}' THEN
        resolution_to_check := NEW.id;
    ELSE
        IF TG_OP = 'DELETE' THEN
            resolution_to_check := OLD.resolution_id;
        ELSE
            resolution_to_check := NEW.resolution_id;
        END IF;
        IF TG_OP = 'UPDATE'
           AND OLD.resolution_id IS DISTINCT FROM NEW.resolution_id THEN
            previous_resolution_to_check := OLD.resolution_id;
        END IF;
    END IF;

    IF resolution_to_check IS NOT NULL AND EXISTS (
        SELECT 1
        FROM public.{TRANSACTION_RESOLUTIONS_TABLE} AS resolution
        WHERE resolution.id = resolution_to_check
          AND COALESCE(
                (
                    SELECT SUM(allocation.amount)
                    FROM public.{TRANSACTION_ALLOCATIONS_TABLE} AS allocation
                    WHERE allocation.resolution_id = resolution.id
                ),
                0
              ) <> abs(resolution.signed_amount)
    ) THEN
        RAISE EXCEPTION
            'transaction allocations must sum to the source magnitude'
            USING ERRCODE = '23514',
                  CONSTRAINT = '{ALLOCATION_MUTATION_TRIGGER_NAME}';
    END IF;

    IF previous_resolution_to_check IS NOT NULL AND EXISTS (
        SELECT 1
        FROM public.{TRANSACTION_RESOLUTIONS_TABLE} AS resolution
        WHERE resolution.id = previous_resolution_to_check
          AND COALESCE(
                (
                    SELECT SUM(allocation.amount)
                    FROM public.{TRANSACTION_ALLOCATIONS_TABLE} AS allocation
                    WHERE allocation.resolution_id = resolution.id
                ),
                0
              ) <> abs(resolution.signed_amount)
    ) THEN
        RAISE EXCEPTION
            'transaction allocations must sum to the source magnitude'
            USING ERRCODE = '23514',
                  CONSTRAINT = '{ALLOCATION_MUTATION_TRIGGER_NAME}';
    END IF;

    IF TG_OP = 'DELETE' THEN
        RETURN OLD;
    END IF;
    RETURN NEW;
END;
$$
"""

CREATE_ALLOCATION_RESOLUTION_TRIGGER_SQL = f"""
CREATE CONSTRAINT TRIGGER {ALLOCATION_RESOLUTION_TRIGGER_NAME}
AFTER INSERT OR UPDATE ON public.{TRANSACTION_RESOLUTIONS_TABLE}
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.{ALLOCATION_TOTAL_FUNCTION_NAME}()
"""

CREATE_ALLOCATION_MUTATION_TRIGGER_SQL = f"""
CREATE CONSTRAINT TRIGGER {ALLOCATION_MUTATION_TRIGGER_NAME}
AFTER INSERT OR UPDATE OR DELETE ON public.{TRANSACTION_ALLOCATIONS_TABLE}
DEFERRABLE INITIALLY DEFERRED
FOR EACH ROW
EXECUTE FUNCTION public.{ALLOCATION_TOTAL_FUNCTION_NAME}()
"""

CREATE_MATCH_RUN_FUNCTION_SQL = f"""
CREATE FUNCTION public.{MATCH_RUN_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.{LINE_ITEM_RESOLUTIONS_TABLE} AS line_resolution
        JOIN public.{TRANSACTION_ALLOCATIONS_TABLE} AS allocation
          ON allocation.id = NEW.allocation_id
        JOIN public.{TRANSACTION_RESOLUTIONS_TABLE} AS transaction_resolution
          ON transaction_resolution.id = allocation.resolution_id
        WHERE line_resolution.id = NEW.resolution_id
          AND line_resolution.run_id = transaction_resolution.run_id
    ) THEN
        RAISE EXCEPTION
            'line-item matches must reference parents from the same run'
            USING ERRCODE = '23514',
                  CONSTRAINT = '{MATCH_RUN_TRIGGER_NAME}';
    END IF;
    RETURN NEW;
END;
$$
"""

CREATE_MATCH_RUN_TRIGGER_SQL = f"""
CREATE TRIGGER {MATCH_RUN_TRIGGER_NAME}
BEFORE INSERT OR UPDATE ON public.{LINE_ITEM_MATCHES_TABLE}
FOR EACH ROW
EXECUTE FUNCTION public.{MATCH_RUN_FUNCTION_NAME}()
"""

CREATE_RUN_IMMUTABILITY_FUNCTION_SQL = f"""
CREATE FUNCTION public.{RUN_IMMUTABILITY_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    IF TG_OP = 'UPDATE'
       AND OLD.is_current IS TRUE
       AND NEW.is_current IS FALSE THEN
        -- SQLAlchemy's shared timestamp hook updates updated_at on every ORM
        -- update. Preserve it so is_current is the only stored change.
        NEW.is_current := OLD.is_current;
        NEW.updated_at := OLD.updated_at;
        IF NEW IS NOT DISTINCT FROM OLD THEN
            NEW.is_current := FALSE;
            RETURN NEW;
        END IF;
    END IF;

    RAISE EXCEPTION 'snapshot reconciliation runs are immutable after insert'
        USING ERRCODE = '23514',
              CONSTRAINT = '{RUN_IMMUTABILITY_TRIGGER_NAME}';
END;
$$
"""

CREATE_RUN_IMMUTABILITY_TRIGGER_SQL = f"""
CREATE TRIGGER {RUN_IMMUTABILITY_TRIGGER_NAME}
BEFORE UPDATE OR DELETE ON public.{RUNS_TABLE}
FOR EACH ROW
EXECUTE FUNCTION public.{RUN_IMMUTABILITY_FUNCTION_NAME}()
"""

CREATE_CHILD_IMMUTABILITY_FUNCTION_SQL = f"""
CREATE FUNCTION public.{CHILD_IMMUTABILITY_FUNCTION_NAME}()
RETURNS trigger
LANGUAGE plpgsql
AS $$
BEGIN
    RAISE EXCEPTION 'snapshot reconciliation ledger rows are immutable after insert'
        USING ERRCODE = '23514',
              CONSTRAINT = TG_NAME;
END;
$$
"""

CREATE_CHILD_IMMUTABILITY_TRIGGER_SQL = tuple(
    f"""
CREATE TRIGGER {trigger_name}
BEFORE UPDATE OR DELETE ON public.{table_name}
FOR EACH ROW
EXECUTE FUNCTION public.{CHILD_IMMUTABILITY_FUNCTION_NAME}()
"""
    for table_name, trigger_name in CHILD_IMMUTABILITY_TRIGGERS
)


def _uuid_column(name: str) -> sa.Column:
    """Return a required UUID column used by the ledger tables."""
    return sa.Column(name, postgresql.UUID(as_uuid=True), nullable=False)


def _money_column(name: str, *, server_default: TextClause | None = None) -> sa.Column:
    """Return a required fixed-precision money column."""
    return sa.Column(
        name,
        sa.Numeric(precision=12, scale=2),
        nullable=False,
        server_default=server_default,
    )


def upgrade() -> None:
    """Create the reconciliation ledger and protect it with RLS."""
    op.add_column(
        "monthly_snapshots",
        _money_column("reimbursement_in_total", server_default=sa.text("0.00")),
    )
    op.add_column(
        "monthly_snapshots",
        _money_column("reimbursement_out_total", server_default=sa.text("0.00")),
    )

    op.create_table(
        RUNS_TABLE,
        _uuid_column("id"),
        _uuid_column("snapshot_id"),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column(
            "is_current",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column("manifest_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("input_hash", sa.CHAR(length=64), nullable=False),
        sa.Column("reconciled_at", sa.DateTime(timezone=True), nullable=False),
        _money_column("income_total"),
        _money_column("expense_total"),
        _money_column("transfer_in_total"),
        _money_column("transfer_out_total"),
        _money_column("reimbursement_in_total", server_default=sa.text("0.00")),
        _money_column("reimbursement_out_total", server_default=sa.text("0.00")),
        _money_column("credit_card_total"),
        _money_column("net"),
        sa.Column("posted_transaction_count", sa.Integer(), nullable=False),
        sa.Column("allocation_count", sa.Integer(), nullable=False),
        sa.Column("line_item_count", sa.Integer(), nullable=False),
        sa.Column(
            "has_remaining_items",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
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
        sa.CheckConstraint(
            "version > 0",
            name="ck_snapshot_reconciliation_runs_version_positive",
        ),
        sa.CheckConstraint(
            "manifest_hash ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_reconciliation_runs_manifest_hash",
        ),
        sa.CheckConstraint(
            "input_hash ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_reconciliation_runs_input_hash",
        ),
        sa.CheckConstraint(
            "income_total >= 0 AND expense_total >= 0 "
            "AND transfer_in_total >= 0 AND transfer_out_total >= 0 "
            "AND reimbursement_in_total >= 0 AND reimbursement_out_total >= 0 "
            "AND credit_card_total >= 0",
            name="ck_snapshot_reconciliation_runs_nonnegative_totals",
        ),
        sa.CheckConstraint(
            "posted_transaction_count >= 0 AND allocation_count >= 0 "
            "AND line_item_count >= 0",
            name="ck_snapshot_reconciliation_runs_nonnegative_counts",
        ),
        sa.CheckConstraint(
            "net = income_total + transfer_in_total + reimbursement_in_total "
            "- expense_total - transfer_out_total - reimbursement_out_total "
            "- credit_card_total",
            name="ck_snapshot_reconciliation_runs_net",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id"],
            ["monthly_snapshots.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "uq_snapshot_reconciliation_runs_current_snapshot",
        RUNS_TABLE,
        ["snapshot_id"],
        unique=True,
        postgresql_where=sa.text("is_current"),
    )
    op.create_index(
        "ix_snapshot_reconciliation_runs_snapshot_reconciled_at",
        RUNS_TABLE,
        ["snapshot_id", "reconciled_at"],
        unique=False,
    )

    op.create_table(
        TRANSACTION_RESOLUTIONS_TABLE,
        _uuid_column("id"),
        _uuid_column("run_id"),
        _uuid_column("transaction_id"),
        sa.Column("fingerprint", sa.CHAR(length=64), nullable=False),
        sa.Column("account_id", sa.String(length=255), nullable=False),
        sa.Column("transaction_date", sa.Date(), nullable=False),
        _money_column("signed_amount"),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("source_updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "classification_source",
            sa.String(length=30),
            nullable=False,
            server_default=sa.text("'manifest'"),
        ),
        sa.Column(
            "manual_locked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "pair_group_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
        sa.CheckConstraint(
            "fingerprint ~ '^[0-9a-f]{64}$'",
            name="ck_snapshot_transaction_resolutions_fingerprint",
        ),
        sa.CheckConstraint(
            "length(btrim(classification_source)) BETWEEN 1 AND 30",
            name="ck_snapshot_transaction_resolutions_classification_source",
        ),
        sa.CheckConstraint(
            "currency IS NULL OR length(currency) = 3",
            name="ck_snapshot_transaction_resolutions_currency",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{RUNS_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "transaction_id",
            name="uq_snapshot_transaction_resolutions_run_transaction",
        ),
    )
    op.create_index(
        "ix_snapshot_transaction_resolutions_run_id",
        TRANSACTION_RESOLUTIONS_TABLE,
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_transaction_resolutions_transaction_id",
        TRANSACTION_RESOLUTIONS_TABLE,
        ["transaction_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_transaction_resolutions_pair_group_id",
        TRANSACTION_RESOLUTIONS_TABLE,
        ["pair_group_id"],
        unique=False,
        postgresql_where=sa.text("pair_group_id IS NOT NULL"),
    )

    op.create_table(
        TRANSACTION_ALLOCATIONS_TABLE,
        _uuid_column("id"),
        _uuid_column("resolution_id"),
        sa.Column("allocation_index", sa.Integer(), nullable=False),
        sa.Column("flow_type", sa.String(length=30), nullable=False),
        _money_column("amount"),
        sa.Column("category", sa.String(length=100), nullable=True),
        sa.CheckConstraint(
            f"flow_type IN ({FLOW_TYPE_SQL})",
            name="ck_snapshot_transaction_allocations_flow_type",
        ),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_snapshot_transaction_allocations_amount_positive",
        ),
        sa.CheckConstraint(
            "allocation_index >= 0",
            name="ck_snapshot_transaction_allocations_index_nonnegative",
        ),
        sa.ForeignKeyConstraint(
            ["resolution_id"],
            [f"{TRANSACTION_RESOLUTIONS_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resolution_id",
            "allocation_index",
            name="uq_snapshot_transaction_allocations_resolution_index",
        ),
    )
    op.create_index(
        "ix_snapshot_transaction_allocations_resolution_id",
        TRANSACTION_ALLOCATIONS_TABLE,
        ["resolution_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_transaction_allocations_flow_type",
        TRANSACTION_ALLOCATIONS_TABLE,
        ["flow_type"],
        unique=False,
    )

    op.create_table(
        LINE_ITEM_RESOLUTIONS_TABLE,
        _uuid_column("id"),
        _uuid_column("run_id"),
        _uuid_column("line_item_id"),
        sa.Column("resolution", sa.String(length=20), nullable=False),
        _money_column("remaining_amount", server_default=sa.text("0.00")),
        sa.Column("adjustment_flow_type", sa.String(length=30), nullable=True),
        sa.Column(
            "adjustment_amount",
            sa.Numeric(precision=12, scale=2),
            nullable=True,
        ),
        sa.Column("authorization_note", sa.Text(), nullable=True),
        sa.CheckConstraint(
            "resolution IN ('fulfilled', 'skipped', 'remaining', 'adjustment')",
            name="ck_snapshot_line_item_resolutions_resolution",
        ),
        sa.CheckConstraint(
            "remaining_amount >= 0",
            name="ck_snapshot_line_item_resolutions_remaining_nonnegative",
        ),
        sa.CheckConstraint(
            f"adjustment_flow_type IS NULL OR "
            f"adjustment_flow_type IN ({ADJUSTMENT_FLOW_TYPE_SQL})",
            name="ck_snapshot_line_item_resolutions_adjustment_flow_type",
        ),
        sa.CheckConstraint(
            "(resolution = 'remaining' AND remaining_amount > 0 "
            "AND adjustment_flow_type IS NULL AND adjustment_amount IS NULL "
            "AND authorization_note IS NULL) OR "
            "(resolution = 'adjustment' AND remaining_amount = 0 "
            "AND adjustment_flow_type IS NOT NULL AND adjustment_amount > 0 "
            "AND length(btrim(authorization_note)) > 0) OR "
            "(resolution IN ('fulfilled', 'skipped') AND remaining_amount = 0 "
            "AND adjustment_flow_type IS NULL AND adjustment_amount IS NULL "
            "AND authorization_note IS NULL)",
            name="ck_snapshot_line_item_resolutions_payload",
        ),
        sa.ForeignKeyConstraint(
            ["run_id"],
            [f"{RUNS_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "run_id",
            "line_item_id",
            name="uq_snapshot_line_item_resolutions_run_line_item",
        ),
    )
    op.create_index(
        "ix_snapshot_line_item_resolutions_run_id",
        LINE_ITEM_RESOLUTIONS_TABLE,
        ["run_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_line_item_resolutions_line_item_id",
        LINE_ITEM_RESOLUTIONS_TABLE,
        ["line_item_id"],
        unique=False,
    )

    op.create_table(
        LINE_ITEM_MATCHES_TABLE,
        _uuid_column("id"),
        _uuid_column("resolution_id"),
        _uuid_column("allocation_id"),
        _money_column("amount"),
        sa.CheckConstraint(
            "amount > 0",
            name="ck_snapshot_line_item_matches_amount_positive",
        ),
        sa.ForeignKeyConstraint(
            ["resolution_id"],
            [f"{LINE_ITEM_RESOLUTIONS_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["allocation_id"],
            [f"{TRANSACTION_ALLOCATIONS_TABLE}.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "resolution_id",
            "allocation_id",
            name="uq_snapshot_line_item_matches_resolution_allocation",
        ),
    )
    op.create_index(
        "ix_snapshot_line_item_matches_resolution_id",
        LINE_ITEM_MATCHES_TABLE,
        ["resolution_id"],
        unique=False,
    )
    op.create_index(
        "ix_snapshot_line_item_matches_allocation_id",
        LINE_ITEM_MATCHES_TABLE,
        ["allocation_id"],
        unique=False,
    )

    op.execute(CREATE_ALLOCATION_TOTAL_FUNCTION_SQL)
    op.execute(CREATE_ALLOCATION_RESOLUTION_TRIGGER_SQL)
    op.execute(CREATE_ALLOCATION_MUTATION_TRIGGER_SQL)
    op.execute(CREATE_MATCH_RUN_FUNCTION_SQL)
    op.execute(CREATE_MATCH_RUN_TRIGGER_SQL)
    op.execute(CREATE_RUN_IMMUTABILITY_FUNCTION_SQL)
    op.execute(CREATE_RUN_IMMUTABILITY_TRIGGER_SQL)
    op.execute(CREATE_CHILD_IMMUTABILITY_FUNCTION_SQL)
    for statement in CREATE_CHILD_IMMUTABILITY_TRIGGER_SQL:
        op.execute(statement)

    for statement in ENABLE_RLS_SQL:
        op.execute(statement)


def downgrade() -> None:
    """Drop ledger objects in reverse dependency order."""
    for table_name, trigger_name in reversed(CHILD_IMMUTABILITY_TRIGGERS):
        op.execute(f"DROP TRIGGER IF EXISTS {trigger_name} ON public.{table_name}")
    op.execute(
        f"DROP TRIGGER IF EXISTS {RUN_IMMUTABILITY_TRIGGER_NAME} ON public.{RUNS_TABLE}"
    )
    op.execute(
        f"DROP TRIGGER IF EXISTS {MATCH_RUN_TRIGGER_NAME} "
        f"ON public.{LINE_ITEM_MATCHES_TABLE}"
    )
    op.execute(
        f"DROP TRIGGER IF EXISTS {ALLOCATION_MUTATION_TRIGGER_NAME} "
        f"ON public.{TRANSACTION_ALLOCATIONS_TABLE}"
    )
    op.execute(
        f"DROP TRIGGER IF EXISTS {ALLOCATION_RESOLUTION_TRIGGER_NAME} "
        f"ON public.{TRANSACTION_RESOLUTIONS_TABLE}"
    )

    op.drop_index(
        "ix_snapshot_line_item_matches_allocation_id",
        table_name=LINE_ITEM_MATCHES_TABLE,
    )
    op.drop_index(
        "ix_snapshot_line_item_matches_resolution_id",
        table_name=LINE_ITEM_MATCHES_TABLE,
    )
    op.drop_table(LINE_ITEM_MATCHES_TABLE)

    op.drop_index(
        "ix_snapshot_line_item_resolutions_line_item_id",
        table_name=LINE_ITEM_RESOLUTIONS_TABLE,
    )
    op.drop_index(
        "ix_snapshot_line_item_resolutions_run_id",
        table_name=LINE_ITEM_RESOLUTIONS_TABLE,
    )
    op.drop_table(LINE_ITEM_RESOLUTIONS_TABLE)

    op.drop_index(
        "ix_snapshot_transaction_allocations_flow_type",
        table_name=TRANSACTION_ALLOCATIONS_TABLE,
    )
    op.drop_index(
        "ix_snapshot_transaction_allocations_resolution_id",
        table_name=TRANSACTION_ALLOCATIONS_TABLE,
    )
    op.drop_table(TRANSACTION_ALLOCATIONS_TABLE)

    op.drop_index(
        "ix_snapshot_transaction_resolutions_pair_group_id",
        table_name=TRANSACTION_RESOLUTIONS_TABLE,
    )
    op.drop_index(
        "ix_snapshot_transaction_resolutions_transaction_id",
        table_name=TRANSACTION_RESOLUTIONS_TABLE,
    )
    op.drop_index(
        "ix_snapshot_transaction_resolutions_run_id",
        table_name=TRANSACTION_RESOLUTIONS_TABLE,
    )
    op.drop_table(TRANSACTION_RESOLUTIONS_TABLE)

    op.drop_index(
        "ix_snapshot_reconciliation_runs_snapshot_reconciled_at",
        table_name=RUNS_TABLE,
    )
    op.drop_index(
        "uq_snapshot_reconciliation_runs_current_snapshot",
        table_name=RUNS_TABLE,
    )
    op.drop_table(RUNS_TABLE)

    op.execute(f"DROP FUNCTION IF EXISTS public.{MATCH_RUN_FUNCTION_NAME}()")
    op.execute(f"DROP FUNCTION IF EXISTS public.{ALLOCATION_TOTAL_FUNCTION_NAME}()")
    op.execute(f"DROP FUNCTION IF EXISTS public.{CHILD_IMMUTABILITY_FUNCTION_NAME}()")
    op.execute(f"DROP FUNCTION IF EXISTS public.{RUN_IMMUTABILITY_FUNCTION_NAME}()")

    op.drop_column("monthly_snapshots", "reimbursement_out_total")
    op.drop_column("monthly_snapshots", "reimbursement_in_total")
