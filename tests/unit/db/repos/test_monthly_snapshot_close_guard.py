"""Tests for the monthly snapshot repository close guard."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest

from budget_me.db.repos.monthly_snapshot_repo import MonthlySnapshotRepo


@pytest.mark.asyncio
async def test_close_refuses_unguarded_repository_mutation() -> None:
    """Repository callers must use the guarded snapshot close service."""
    session = AsyncMock()

    with pytest.raises(
        RuntimeError,
        match=r"budget_me\.snapshots\.service\.close_snapshot\(\)",
    ):
        await MonthlySnapshotRepo(session).close(uuid4())

    assert session.mock_calls == []
