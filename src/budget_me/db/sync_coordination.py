"""PostgreSQL coordination between Plaid sync admission and snapshot close."""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session

from budget_me.db.engine import get_engine

_SYNC_ADMISSION_LOCK_SQL = text("LOCK TABLE plaid_items IN ROW EXCLUSIVE MODE")
_CLOSE_COORDINATION_LOCK_SQL = text("LOCK TABLE plaid_items IN SHARE MODE")
_TRANSACTION_RECONCILIATION_LOCK_SQL = text("LOCK TABLE transactions IN SHARE MODE")


async def acquire_sync_admission_lock(session: AsyncSession) -> None:
    """Join SyncService admission to the PostgreSQL sync/close barrier.

    The lock is intentionally table-wide. Budget Me is a single-household
    application, and a conservative global barrier is safer than deriving a
    possibly incomplete per-item scope before the RUNNING/PENDING rows exist.
    PostgreSQL permits concurrent ROW EXCLUSIVE holders, while a close-side
    SHARE holder waits for every admitted sync publisher to finish.
    """
    await session.execute(_SYNC_ADMISSION_LOCK_SQL)


def acquire_close_coordination_lock(session: Session) -> None:
    """Wait for admitted Plaid work and prevent new Plaid work through close."""
    session.execute(_CLOSE_COORDINATION_LOCK_SQL)


def acquire_transaction_reconciliation_lock(session: Session) -> None:
    """Wait for transaction writers and hold new writers out of reconciliation.

    Supported Plaid writers acquire the ``plaid_items`` barrier first. Callers
    must therefore acquire ``acquire_close_coordination_lock`` before this lock
    to preserve one global lock order. PostgreSQL's SHARE table lock conflicts
    with the ROW EXCLUSIVE lock taken by INSERT, UPDATE, and DELETE statements,
    so a reconciler or close sees every earlier annotation/provider commit and
    prevents a later one until its own transaction finishes.
    """
    session.execute(_TRANSACTION_RECONCILIATION_LOCK_SQL)


@asynccontextmanager
async def hold_sync_item_coordination() -> AsyncIterator[None]:
    """Hold the sync side of the barrier across one complete public item sync.

    ``sync_item`` commits each provider page through separate ORM work. A
    dedicated pinned connection keeps this transaction-scoped table lock alive
    across those commits without leaking a session-level advisory lock through
    the connection pool.
    """
    async with get_engine().connect() as connection:
        async with connection.begin():
            await connection.execute(_SYNC_ADMISSION_LOCK_SQL)
            yield
