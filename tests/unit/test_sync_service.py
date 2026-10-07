"""Tests for SyncService with IngestRun tracking."""

from uuid import uuid4

import pytest

from budget_me.db.models.ingest_run import (
    IngestRunItemStatus,
    IngestRunStatus,
    IngestRunType,
)
from budget_me.plaid.transactions_sync import ItemSyncResult


class TestSyncService:
    """Tests for SyncService."""

    @pytest.mark.asyncio
    async def test_sync_service_creates_ingest_run(self, mocker):
        """run_sync creates an IngestRun with RUNNING status."""
        from budget_me.db.models.ingest_run import IngestRun
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()

        async def create_after_admission_lock(**kwargs):
            assert mock_session.execute.await_count == 1
            return mock_run

        mock_ingest_repo.create_run = mocker.AsyncMock(
            side_effect=create_after_admission_lock
        )

        async def complete_after_zero_item_scope_is_published(**kwargs):
            assert mock_session.commit.await_count == 1
            return mock_run

        mock_ingest_repo.complete_run = mocker.AsyncMock(
            side_effect=complete_after_zero_item_scope_is_published
        )
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo with no active items
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        service = SyncService(mock_session)
        await service.run_sync()

        # Verify IngestRun was created
        mock_ingest_repo.create_run.assert_called_once()
        call_kwargs = mock_ingest_repo.create_run.call_args.kwargs
        assert call_kwargs["run_type"] == IngestRunType.MANUAL
        assert call_kwargs["items_total"] == 0
        assert mock_session.commit.await_count == 2
        lock_sql = str(mock_session.execute.await_args.args[0])
        assert lock_sql == "LOCK TABLE plaid_items IN ROW EXCLUSIVE MODE"

    @pytest.mark.asyncio
    async def test_sync_service_creates_run_items_for_each_item(self, mocker):
        """run_sync creates IngestRunItems for each PlaidItem."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create 3 mock items
        mock_items = []
        for i in range(3):
            item = mocker.MagicMock(spec=PlaidItem)
            item.id = uuid4()
            item.institution_id = f"ins_{i}"
            item.item_id = f"item_{i}"
            mock_items.append(item)

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_items = []
        for item in mock_items:
            run_item = mocker.MagicMock(spec=IngestRunItem)
            run_item.id = uuid4()
            mock_run_items.append(run_item)

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        pending_run_items = iter(mock_run_items)

        async def add_run_item_before_first_commit(**kwargs):
            assert mock_session.commit.await_count == 0
            return next(pending_run_items)

        mock_ingest_repo.add_run_item = mocker.AsyncMock(
            side_effect=add_run_item_before_first_commit
        )
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=mock_items)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Every item must be registered before the first provider call begins.
        async def sync_after_scope_is_visible(*args, **kwargs):
            assert mock_ingest_repo.add_run_item.await_count == len(mock_items)
            assert mock_session.commit.await_count == 1
            return ItemSyncResult(added=0, modified=0, removed=0)

        mock_sync_item = mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mocker.AsyncMock(side_effect=sync_after_scope_is_visible),
        )

        service = SyncService(mock_session)
        await service.run_sync()

        # Verify 3 IngestRunItems were created
        assert mock_ingest_repo.add_run_item.call_count == 3
        assert mock_sync_item.await_count == 3
        assert [
            call.kwargs["plaid_item_id"]
            for call in mock_ingest_repo.add_run_item.await_args_list
        ] == [item.id for item in mock_items]

    @pytest.mark.asyncio
    async def test_sync_service_completes_run_success(self, mocker):
        """run_sync marks IngestRun as COMPLETED when all items succeed."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create mock items
        mock_items = []
        for i in range(2):
            item = mocker.MagicMock(spec=PlaidItem)
            item.id = uuid4()
            item.institution_id = f"ins_{i}"
            item.item_id = f"item_{i}"
            mock_items.append(item)

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=mock_items)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item to succeed
        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mocker.AsyncMock(
                return_value=ItemSyncResult(added=5, modified=0, removed=0)
            ),
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify status is COMPLETED
        assert result.status == IngestRunStatus.COMPLETED

        # Verify complete_run was called with SUCCESS status
        call_kwargs = mock_ingest_repo.complete_run.call_args.kwargs
        assert call_kwargs["status"] == IngestRunStatus.COMPLETED

    @pytest.mark.asyncio
    async def test_sync_service_completes_run_partial(self, mocker):
        """run_sync marks IngestRun as PARTIAL when some items fail."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.plaid.errors import PlaidError
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create 3 mock items
        mock_items = []
        for i in range(3):
            item = mocker.MagicMock(spec=PlaidItem)
            item.id = uuid4()
            item.institution_id = f"ins_{i}"
            item.item_id = f"item_{i}"
            mock_items.append(item)

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=mock_items)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item: 2 succeed, 1 fails
        call_count = 0

        async def mock_sync_item(item_id, include_transactions=False):
            nonlocal call_count
            call_count += 1
            if call_count == 2:
                raise PlaidError(
                    error_code="SOME_ERROR",
                    message="Test error",
                    status=400,
                )
            return ItemSyncResult(added=5, modified=0, removed=0)

        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mock_sync_item,
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify status is PARTIAL
        assert result.status == IngestRunStatus.PARTIAL
        assert result.items_ok == 2
        assert result.items_failed == 1

    @pytest.mark.asyncio
    async def test_sync_service_completes_run_fail(self, mocker):
        """run_sync marks IngestRun as FAILED when all items fail."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.plaid.errors import PlaidError
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create 2 mock items
        mock_items = []
        for i in range(2):
            item = mocker.MagicMock(spec=PlaidItem)
            item.id = uuid4()
            item.institution_id = f"ins_{i}"
            item.item_id = f"item_{i}"
            mock_items.append(item)

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=mock_items)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item: all fail
        async def mock_sync_item(item_id, include_transactions=False):
            raise PlaidError(
                error_code="SOME_ERROR",
                message="Test error",
                status=400,
            )

        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mock_sync_item,
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify status is FAILED
        assert result.status == IngestRunStatus.FAILED
        assert result.items_ok == 0
        assert result.items_failed == 2

    @pytest.mark.asyncio
    async def test_sync_service_records_item_duration(self, mocker):
        """run_sync records duration_ms for each IngestRunItem."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create mock item
        mock_item = mocker.MagicMock(spec=PlaidItem)
        mock_item.id = uuid4()
        mock_item.institution_id = "ins_1"
        mock_item.item_id = "item_1"

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[mock_item])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item to succeed
        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mocker.AsyncMock(
                return_value=ItemSyncResult(added=5, modified=0, removed=0)
            ),
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify complete_run_item was called with duration_ms
        mock_ingest_repo.complete_run_item.assert_called_once()
        call_kwargs = mock_ingest_repo.complete_run_item.call_args.kwargs
        assert "duration_ms" in call_kwargs
        assert call_kwargs["duration_ms"] >= 0

        # Verify result also has duration
        assert result.item_results[0].duration_ms >= 0

    @pytest.mark.asyncio
    async def test_sync_service_aggregates_counts(self, mocker):
        """run_sync aggregates tx_added/modified/removed from all items."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create 2 mock items
        mock_items = []
        for i in range(2):
            item = mocker.MagicMock(spec=PlaidItem)
            item.id = uuid4()
            item.institution_id = f"ins_{i}"
            item.item_id = f"item_{i}"
            mock_items.append(item)

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=mock_items)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item: Item 1 adds 10, Item 2 adds 5
        call_count = 0

        async def mock_sync_item(item_id, include_transactions=False):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                return ItemSyncResult(added=10, modified=2, removed=1)
            else:
                return ItemSyncResult(added=5, modified=3, removed=0)

        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mock_sync_item,
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify aggregated counts
        assert result.tx_added == 15  # 10 + 5
        assert result.tx_modified == 5  # 2 + 3
        assert result.tx_removed == 1  # 1 + 0

        # Verify complete_run was called with aggregated counts
        call_kwargs = mock_ingest_repo.complete_run.call_args.kwargs
        assert call_kwargs["tx_added"] == 15
        assert call_kwargs["tx_modified"] == 5
        assert call_kwargs["tx_removed"] == 1

    @pytest.mark.asyncio
    async def test_sync_service_records_error_on_item(self, mocker):
        """run_sync records error_code and error_message on failed items."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.plaid.errors import PlaidError
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create mock item
        mock_item = mocker.MagicMock(spec=PlaidItem)
        mock_item.id = uuid4()
        mock_item.institution_id = "ins_1"
        mock_item.item_id = "item_1"

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[mock_item])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item to fail with PlaidError
        async def mock_sync_item(item_id, include_transactions=False):
            raise PlaidError(
                error_code="ITEM_LOGIN_REQUIRED",
                message="User needs to relogin",
                status=400,
            )

        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mock_sync_item,
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify complete_run_item was called with error info
        mock_ingest_repo.complete_run_item.assert_called_once()
        call_kwargs = mock_ingest_repo.complete_run_item.call_args.kwargs
        assert call_kwargs["status"] == IngestRunItemStatus.FAILED
        assert call_kwargs["error_code"] == "ITEM_LOGIN_REQUIRED"
        assert call_kwargs["error_message"] == "User needs to relogin"

        # Verify result item has error info
        assert result.item_results[0].error_code == "ITEM_LOGIN_REQUIRED"
        assert result.item_results[0].error_message == "User needs to relogin"

    @pytest.mark.asyncio
    async def test_sync_service_reports_liability_failure(self, mocker):
        """A liability refresh failure must not publish a successful debt sync."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.plaid.errors import PlaidError
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()
        mock_item = mocker.MagicMock(spec=PlaidItem)
        mock_item.id = uuid4()
        mock_item.institution_id = "ins_debt"
        mock_item.item_id = "item_debt"
        mock_item.products = ["transactions", "liabilities"]
        mock_item.last_success_at = None

        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[mock_item])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )
        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mocker.AsyncMock(
                return_value=ItemSyncResult(added=1, modified=0, removed=0)
            ),
        )
        mocker.patch(
            "budget_me.services.sync_service.sync_liabilities",
            mocker.AsyncMock(
                side_effect=PlaidError(
                    message="Liabilities unavailable",
                    error_code="PRODUCT_NOT_READY",
                    status=400,
                )
            ),
        )

        result = await SyncService(mock_session).run_sync()

        assert result.status == IngestRunStatus.FAILED
        assert result.items_ok == 0
        assert result.items_failed == 1
        assert mock_item.last_success_at is None
        call_kwargs = mock_ingest_repo.complete_run_item.call_args.kwargs
        assert call_kwargs["status"] == IngestRunItemStatus.FAILED
        assert call_kwargs["error_code"] == "PRODUCT_NOT_READY"

    @pytest.mark.asyncio
    async def test_sync_service_sets_run_type(self, mocker):
        """run_sync sets run_type on IngestRun based on parameter."""
        from budget_me.db.models.ingest_run import IngestRun
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo with no items
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        service = SyncService(mock_session)
        await service.run_sync(run_type=IngestRunType.SCHEDULED)

        # Verify run_type was passed correctly
        call_kwargs = mock_ingest_repo.create_run.call_args.kwargs
        assert call_kwargs["run_type"] == IngestRunType.SCHEDULED

    @pytest.mark.asyncio
    async def test_sync_service_handles_no_active_items(self, mocker):
        """run_sync with no active items creates IngestRun with items_total=0, status=COMPLETED."""
        from budget_me.db.models.ingest_run import IngestRun
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo with no active items
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.find_active = mocker.AsyncMock(return_value=[])
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        service = SyncService(mock_session)
        result = await service.run_sync()

        # Verify IngestRun was created with items_total=0
        call_kwargs = mock_ingest_repo.create_run.call_args.kwargs
        assert call_kwargs["items_total"] == 0

        # Verify status is COMPLETED (not FAILED)
        assert result.status == IngestRunStatus.COMPLETED
        assert result.items_total == 0

    @pytest.mark.asyncio
    async def test_sync_service_syncs_specific_item(self, mocker):
        """run_sync with item_id syncs only that specific item."""
        from budget_me.db.models.ingest_run import IngestRun, IngestRunItem
        from budget_me.db.models.plaid_item import PlaidItem
        from budget_me.services.sync_service import SyncService

        mock_session = mocker.AsyncMock()

        # Create mock item
        specific_item_id = uuid4()
        mock_item = mocker.MagicMock(spec=PlaidItem)
        mock_item.id = specific_item_id
        mock_item.institution_id = "ins_specific"
        mock_item.item_id = "item_specific"

        # Mock IngestRun
        mock_run = mocker.MagicMock(spec=IngestRun)
        mock_run.id = uuid4()

        # Mock IngestRunItem
        mock_run_item = mocker.MagicMock(spec=IngestRunItem)
        mock_run_item.id = uuid4()

        # Mock IngestRunsRepo
        mock_ingest_repo = mocker.MagicMock()
        mock_ingest_repo.create_run = mocker.AsyncMock(return_value=mock_run)
        mock_ingest_repo.add_run_item = mocker.AsyncMock(return_value=mock_run_item)
        mock_ingest_repo.complete_run_item = mocker.AsyncMock()
        mock_ingest_repo.complete_run = mocker.AsyncMock(return_value=mock_run)
        mocker.patch(
            "budget_me.services.sync_service.IngestRunsRepo",
            return_value=mock_ingest_repo,
        )

        # Mock ItemsRepo - get_by_id for specific item
        mock_items_repo = mocker.MagicMock()
        mock_items_repo.get_by_id = mocker.AsyncMock(return_value=mock_item)
        mocker.patch(
            "budget_me.services.sync_service.ItemsRepo",
            return_value=mock_items_repo,
        )

        # Mock sync_item
        mock_sync_item = mocker.AsyncMock(
            return_value=ItemSyncResult(added=5, modified=0, removed=0)
        )
        mocker.patch(
            "budget_me.services.sync_service.sync_item",
            mock_sync_item,
        )

        service = SyncService(mock_session)
        result = await service.run_sync(item_id=specific_item_id)

        # Verify get_by_id was called instead of find_active
        mock_items_repo.get_by_id.assert_called_once_with(specific_item_id)

        # Verify only one item was synced
        mock_sync_item.assert_called_once_with(
            specific_item_id, include_transactions=False
        )
        assert result.items_total == 1


class TestSyncServiceExports:
    """Tests for SyncService module exports."""

    def test_sync_service_exported(self):
        """SyncService is exported from services module."""
        from budget_me.services import SyncService

        assert SyncService is not None

    def test_sync_run_result_exported(self):
        """SyncRunResult is exported from services module."""
        from budget_me.services import SyncRunResult

        assert SyncRunResult is not None

    def test_sync_item_result_exported(self):
        """SyncItemResult is exported from services module."""
        from budget_me.services import SyncItemResult

        assert SyncItemResult is not None
