"""Add auditable evidence for checking-side card payments.

Revision ID: f5b6a7c8d901
Revises: e7b4c2d91a60
Create Date: 2026-09-15 00:00:00+00:00
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "f5b6a7c8d901"
down_revision: str | None = "e7b4c2d91a60"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

TABLE = "snapshot_credit_cards"
CONSTRAINT = "ck_snapshot_credit_cards_actual_payment_source"
FOREIGN_KEY = "fk_snapshot_credit_cards_actual_payment_transaction"


def upgrade() -> None:
    op.add_column(
        TABLE, sa.Column("actual_payment_source", sa.String(length=30), nullable=True)
    )
    op.add_column(
        TABLE,
        sa.Column(
            "actual_payment_transaction_id",
            postgresql.UUID(as_uuid=True),
            nullable=True,
        ),
    )
    op.add_column(TABLE, sa.Column("actual_payment_note", sa.Text(), nullable=True))
    op.create_foreign_key(
        FOREIGN_KEY,
        TABLE,
        "transactions",
        ["actual_payment_transaction_id"],
        ["id"],
        ondelete="RESTRICT",
    )
    op.create_check_constraint(
        CONSTRAINT,
        TABLE,
        "actual_payment_source IS NULL "
        "OR actual_payment_source = 'card_feed' "
        "OR (actual_payment_source = 'checking_account' "
        "AND actual_payment_amount IS NOT NULL "
        "AND actual_payment_date IS NOT NULL "
        "AND actual_payment_transaction_id IS NOT NULL "
        "AND NULLIF(BTRIM(actual_payment_note), '') IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT, TABLE, type_="check")
    op.drop_constraint(FOREIGN_KEY, TABLE, type_="foreignkey")
    op.drop_column(TABLE, "actual_payment_note")
    op.drop_column(TABLE, "actual_payment_transaction_id")
    op.drop_column(TABLE, "actual_payment_source")
