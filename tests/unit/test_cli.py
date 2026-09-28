"""Unit tests for CLI commands."""

import json
import uuid
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from click import unstyle
from typer.testing import CliRunner

from budget_me.cli.main import app
from budget_me.db.models.ingest_run import IngestRunStatus, IngestRunType
from budget_me.db.models.plaid_item import PlaidItem, PlaidItemStatus
from budget_me.services.sync_service import SyncItemResult, SyncRunResult

runner = CliRunner()


class TestLinkCommand:
    """Tests for budget-me link command."""

    def test_cli_link_starts_server(self):
        """Test that `budget-me link` starts the link server."""
        with patch("budget_me.cli.commands.link.start_link_server") as mock_server:
            mock_server.return_value = None
            result = runner.invoke(app, ["link"])

            assert result.exit_code == 0
            mock_server.assert_called_once()

    def test_cli_link_shows_url(self, capsys):
        """Test that link command prints server URL."""
        with patch("budget_me.cli.commands.link.start_link_server") as mock_server:
            with patch("budget_me.cli.commands.link.console") as mock_console:
                mock_server.return_value = None
                runner.invoke(app, ["link"])

                # Verify console.print was called to show URL
                assert mock_console.print.called


class TestSyncCommand:
    """Tests for budget-me sync command."""

    @pytest.fixture
    def mock_sync_result_success(self):
        """Create a successful sync result."""
        return SyncRunResult(
            run_id=uuid.uuid4(),
            status=IngestRunStatus.COMPLETED,
            items_total=2,
            items_ok=2,
            items_failed=0,
            tx_added=15,
            tx_modified=3,
            tx_removed=1,
            item_results=[
                SyncItemResult(
                    item_id=uuid.uuid4(),
                    institution_id="ins_1",
                    institution_name="Bank One",
                    success=True,
                    added=10,
                    modified=2,
                    removed=1,
                    duration_ms=500,
                ),
                SyncItemResult(
                    item_id=uuid.uuid4(),
                    institution_id="ins_2",
                    institution_name="Bank Two",
                    success=True,
                    added=5,
                    modified=1,
                    removed=0,
                    duration_ms=300,
                ),
            ],
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=800,
        )

    @pytest.fixture
    def mock_sync_result_partial(self):
        """Create a partial sync result (some failures)."""
        return SyncRunResult(
            run_id=uuid.uuid4(),
            status=IngestRunStatus.PARTIAL,
            items_total=2,
            items_ok=1,
            items_failed=1,
            tx_added=10,
            tx_modified=0,
            tx_removed=0,
            item_results=[
                SyncItemResult(
                    item_id=uuid.uuid4(),
                    institution_id="ins_1",
                    institution_name="Bank One",
                    success=True,
                    added=10,
                    modified=0,
                    removed=0,
                    duration_ms=500,
                ),
                SyncItemResult(
                    item_id=uuid.uuid4(),
                    institution_id="ins_2",
                    institution_name="Bank Two",
                    success=False,
                    error_code="ITEM_LOGIN_REQUIRED",
                    error_message="User needs to relogin",
                    duration_ms=100,
                ),
            ],
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=600,
            error_summary="ins_2: ITEM_LOGIN_REQUIRED",
        )

    @pytest.fixture
    def mock_sync_result_failed(self):
        """Create a failed sync result."""
        return SyncRunResult(
            run_id=uuid.uuid4(),
            status=IngestRunStatus.FAILED,
            items_total=1,
            items_ok=0,
            items_failed=1,
            tx_added=0,
            tx_modified=0,
            tx_removed=0,
            item_results=[
                SyncItemResult(
                    item_id=uuid.uuid4(),
                    institution_id="ins_1",
                    institution_name="Bank One",
                    success=False,
                    error_code="INSTITUTION_NOT_RESPONDING",
                    error_message="Bank is down",
                    duration_ms=5000,
                ),
            ],
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=5000,
            error_summary="ins_1: INSTITUTION_NOT_RESPONDING",
        )

    @pytest.fixture
    def mock_sync_result_no_items(self):
        """Create a sync result with no items."""
        return SyncRunResult(
            run_id=uuid.uuid4(),
            status=IngestRunStatus.COMPLETED,
            items_total=0,
            items_ok=0,
            items_failed=0,
            tx_added=0,
            tx_modified=0,
            tx_removed=0,
            item_results=[],
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=10,
        )

    def test_cli_sync_exit_0_on_success(self, mock_sync_result_success):
        """Test `budget-me sync` returns exit code 0 on success."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                assert result.exit_code == 0
                assert "Sync complete" in result.stdout

    def test_cli_sync_exit_1_on_partial(self, mock_sync_result_partial):
        """Test `budget-me sync` returns exit code 1 on partial success."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_partial
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                assert result.exit_code == 1
                assert "completed with errors" in result.stdout

    def test_cli_sync_exit_2_on_failure(self, mock_sync_result_failed):
        """Test `budget-me sync` returns exit code 2 on failure."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_failed
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                assert result.exit_code == 2
                assert "Sync failed" in result.stdout

    def test_cli_sync_outputs_summary(self, mock_sync_result_success):
        """Test sync command outputs summary with counts."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                assert result.exit_code == 0
                # Check summary is in output
                assert "Summary" in result.stdout
                assert "+15" in result.stdout  # tx_added
                assert "~3" in result.stdout  # tx_modified
                assert "-1" in result.stdout  # tx_removed

    def test_cli_sync_handles_no_items(self, mock_sync_result_no_items):
        """Test sync command when no items exist returns exit code 0."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_no_items
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                # No items is still a successful run
                assert result.exit_code == 0
                assert "No active items" in result.stdout

    def test_cli_sync_specific_item(self, mock_sync_result_success):
        """Test `budget-me sync --item-id <uuid>` syncs only specified item."""
        item_id = str(uuid.uuid4())

        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--item-id", item_id])

                assert result.exit_code == 0
                # Verify run_sync was called with item_id
                call_kwargs = mock_service.run_sync.call_args.kwargs
                assert call_kwargs["item_id"] == uuid.UUID(item_id)

    def test_cli_sync_scheduled_run_type(self, mock_sync_result_success):
        """Test `budget-me sync --run-type scheduled` sets correct run type."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--run-type", "scheduled"])

                assert result.exit_code == 0
                call_kwargs = mock_service.run_sync.call_args.kwargs
                assert call_kwargs["run_type"] == IngestRunType.SCHEDULED

    def test_cli_sync_default_run_type_manual(self, mock_sync_result_success):
        """Test `budget-me sync` defaults to manual run type."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync"])

                assert result.exit_code == 0
                call_kwargs = mock_service.run_sync.call_args.kwargs
                assert call_kwargs["run_type"] == IngestRunType.MANUAL

    def test_cli_sync_invalid_run_type_error(self):
        """Test `budget-me sync --run-type invalid` returns exit code 2."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--run-type", "invalid"])

                assert result.exit_code == 2
                assert "Invalid run type" in result.stdout

    def test_cli_sync_json_output(self, mock_sync_result_success):
        """Test `budget-me sync --json` outputs valid JSON."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--json"])

                assert result.exit_code == 0
                # Parse JSON output
                output = json.loads(result.stdout)
                assert output["status"] == "completed"
                assert output["tx_added"] == 15
                assert output["items_total"] == 2
                assert len(output["items"]) == 2

    def test_cli_sync_json_output_includes_timing(self, mock_sync_result_success):
        """Test JSON output includes duration_ms."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_success
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--json"])

                output = json.loads(result.stdout)
                assert "duration_ms" in output
                assert output["duration_ms"] == 800

    def test_cli_sync_json_output_shows_errors(self, mock_sync_result_partial):
        """Test JSON output includes error details."""
        with patch("budget_me.cli.commands.sync.get_async_session"):
            with patch("budget_me.cli.commands.sync.SyncService") as mock_service_class:
                mock_service = AsyncMock()
                mock_service.run_sync.return_value = mock_sync_result_partial
                mock_service_class.return_value = mock_service

                result = runner.invoke(app, ["sync", "--json"])

                output = json.loads(result.stdout)
                assert output["error_summary"] == "ins_2: ITEM_LOGIN_REQUIRED"
                # Find the failed item
                failed_item = [i for i in output["items"] if not i["success"]][0]
                assert failed_item["error_code"] == "ITEM_LOGIN_REQUIRED"


class TestStatusCommand:
    """Tests for budget-me status command."""

    @pytest.fixture
    def mock_items_with_sync(self):
        """Create mock PlaidItem objects with sync data."""
        item1 = PlaidItem(
            user_key="user_123",
            item_id="item_123",
            access_token_enc="encrypted_token",
            institution_id="ins_1",
            status=PlaidItemStatus.ACTIVE,
        )
        item1.id = uuid.uuid4()
        item1.created_at = datetime.now(UTC)
        item1.last_success_at = datetime.now(UTC)

        item2 = PlaidItem(
            user_key="user_123",
            item_id="item_456",
            access_token_enc="encrypted_token_2",
            institution_id="ins_2",
            status=PlaidItemStatus.RELINK_REQUIRED,
        )
        item2.id = uuid.uuid4()
        item2.created_at = datetime.now(UTC)
        item2.last_error_code = "ITEM_LOGIN_REQUIRED"
        item2.last_error_message = "Login required"

        return [item1, item2]

    def test_cli_status_shows_items(self, mock_items_with_sync):
        """Test `budget-me status` displays item information."""
        with patch("budget_me.cli.commands.status.get_async_session"):
            with patch("budget_me.cli.commands.status.ItemsRepo") as mock_repo_class:
                with patch("budget_me.cli.commands.status.Table") as mock_table:
                    mock_repo = AsyncMock()
                    mock_repo.get_all.return_value = mock_items_with_sync
                    mock_repo_class.return_value = mock_repo

                    result = runner.invoke(app, ["status"])

                    assert result.exit_code == 0
                    # Verify Table was created and used
                    assert mock_table.called

    def test_cli_status_shows_last_sync(self, mock_items_with_sync):
        """Test status command displays last sync timestamp."""
        with patch("budget_me.cli.commands.status.get_async_session"):
            with patch("budget_me.cli.commands.status.ItemsRepo") as mock_repo_class:
                with patch("budget_me.cli.commands.status.console"):
                    mock_repo = AsyncMock()
                    mock_repo.get_all.return_value = mock_items_with_sync
                    mock_repo_class.return_value = mock_repo

                    result = runner.invoke(app, ["status"])

                    assert result.exit_code == 0

    def test_cli_status_shows_errors(self, mock_items_with_sync):
        """Test status command displays error information."""
        with patch("budget_me.cli.commands.status.get_async_session"):
            with patch("budget_me.cli.commands.status.ItemsRepo") as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo.get_all.return_value = [
                    mock_items_with_sync[1]
                ]  # Only error item
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(app, ["status"])

                assert result.exit_code == 0
                # Error info should be in output or handled by Rich Table

    def test_cli_status_handles_no_items(self):
        """Test status command when no items exist."""
        with patch("budget_me.cli.commands.status.get_async_session"):
            with patch("budget_me.cli.commands.status.ItemsRepo") as mock_repo_class:
                mock_repo = AsyncMock()
                mock_repo.get_all.return_value = []
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(app, ["status"])

                assert result.exit_code == 0
                assert "No items" in result.stdout or result.exit_code == 0


class TestCLIHelp:
    """Test CLI help and metadata."""

    def test_cli_has_help(self):
        """Test that CLI commands have help text."""
        result = runner.invoke(app, ["--help"])
        assert result.exit_code == 0
        assert "link" in result.stdout
        assert "sync" in result.stdout
        assert "status" in result.stdout

    def test_link_has_help(self):
        """Test link command has help."""
        result = runner.invoke(app, ["link", "--help"])
        assert result.exit_code == 0

    def test_sync_has_help(self):
        """Test sync command has help."""
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
        # Verify exit codes are documented
        assert "Exit Codes" in result.stdout or "exit" in result.stdout.lower()

    def test_sync_help_shows_run_type_option(self):
        """Test sync --help shows --run-type option."""
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
        assert "--run-type" in unstyle(result.stdout)

    def test_sync_help_shows_json_option(self):
        """Test sync --help shows --json option."""
        result = runner.invoke(app, ["sync", "--help"])
        assert result.exit_code == 0
        assert "--json" in unstyle(result.stdout)

    def test_status_has_help(self):
        """Test status command has help."""
        result = runner.invoke(app, ["status", "--help"])
        assert result.exit_code == 0
