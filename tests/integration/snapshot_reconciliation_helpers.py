"""Test-only helpers for seeding and removing reconciliation receipts."""

from collections.abc import Iterable
from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.orm import Session

from budget_me.db.models.snapshot_reconciliation import (
    SnapshotLineItemMatch,
    SnapshotLineItemResolution,
    SnapshotReconciliationRun,
    SnapshotTransactionAllocation,
    SnapshotTransactionResolution,
)
from budget_me.snapshots.reconciliation import (
    SnapshotReconciliationPreview,
    apply_reconciliation,
    build_reconciliation_preview,
)
from budget_me.snapshots.reconciliation_manifest import ReconciliationManifest

_DISPOSABLE_DATABASE_NAME = "budget_me_test"


def seed_reconciliation_receipt(
    session: Session,
    manifest: ReconciliationManifest,
    *,
    reconciled_at: datetime,
) -> SnapshotReconciliationPreview:
    """Preview and apply a valid receipt through the public service boundary."""
    preview = build_reconciliation_preview(session, manifest)
    if preview.blockers:
        raise AssertionError(
            "Synthetic reconciliation manifest unexpectedly blocked: "
            + " ".join(preview.blockers)
        )

    # apply_reconciliation starts a SERIALIZABLE transaction and must be the
    # first statement in it. The synthetic setup was committed by the caller.
    session.rollback()
    applied = apply_reconciliation(
        session,
        manifest,
        confirm_month=manifest.year_month,
        input_hash=preview.input_hash,
        now=reconciled_at,
    )
    session.commit()
    if applied.current_run_id is None:
        raise AssertionError("Synthetic reconciliation receipt was not persisted")
    return applied


def delete_reconciliation_receipts(
    session: Session, snapshot_ids: Iterable[UUID]
) -> None:
    """Delete only named test receipts while immutable row triggers are bypassed."""
    target_snapshot_ids = tuple(snapshot_ids)
    if not target_snapshot_ids:
        return

    database_name = session.execute(text("SELECT current_database()")).scalar_one()
    if database_name != _DISPOSABLE_DATABASE_NAME:
        raise RuntimeError(
            "Refusing reconciliation cleanup outside the disposable test database"
        )

    run_ids = select(SnapshotReconciliationRun.id).where(
        SnapshotReconciliationRun.snapshot_id.in_(target_snapshot_ids)
    )
    transaction_resolution_ids = select(SnapshotTransactionResolution.id).where(
        SnapshotTransactionResolution.run_id.in_(run_ids)
    )
    line_resolution_ids = select(SnapshotLineItemResolution.id).where(
        SnapshotLineItemResolution.run_id.in_(run_ids)
    )

    # These append-only triggers are intentionally bypassed only in the exact
    # disposable database above. Deletes remain scoped to the supplied UUIDs.
    session.execute(text("SET LOCAL session_replication_role = 'replica'"))
    session.execute(
        delete(SnapshotLineItemMatch).where(
            SnapshotLineItemMatch.resolution_id.in_(line_resolution_ids)
        )
    )
    session.execute(
        delete(SnapshotLineItemResolution).where(
            SnapshotLineItemResolution.id.in_(line_resolution_ids)
        )
    )
    session.execute(
        delete(SnapshotTransactionAllocation).where(
            SnapshotTransactionAllocation.resolution_id.in_(transaction_resolution_ids)
        )
    )
    session.execute(
        delete(SnapshotTransactionResolution).where(
            SnapshotTransactionResolution.id.in_(transaction_resolution_ids)
        )
    )
    session.execute(
        delete(SnapshotReconciliationRun).where(
            SnapshotReconciliationRun.id.in_(run_ids)
        )
    )
    session.execute(text("SET LOCAL session_replication_role = 'origin'"))
