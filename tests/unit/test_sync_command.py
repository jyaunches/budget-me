"""Unit tests for sync CLI command."""

import json
from uuid import uuid4

import pytest
from typer.testing import CliRunner

from budget_me.cli.main import app
from budget_me.db.models.ingest_run import IngestRunStatus
from budget_me.services.sync_service import SyncItemResult, SyncRunResult


class TestSyncCommandJsonOutput:
    """Tests for sync command JSON output format."""

    @pytest.fixture
    def runner(self):
        """Click CLI runner."""
        return CliRunner()

    def test_json_output_valid_when_error_message_contains_newlines(
        self, runner, mocker
    ):
        """JSON output is valid even when error messages contain newlines.

        This test demonstrates the bug where Rich's console.print() wraps
        long lines, breaking JSON output when error messages span multiple lines.

        Expected: JSON should have escaped newlines (\\n) not literal newlines.
        Actual (bug): Rich wraps output, inserting literal newlines in strings.
        """
        from datetime import UTC, datetime

        # Create a mock result with an error message containing a newline
        # This simulates Python's TypeError message format
        error_with_newline = (
            "BaseRepository.update() takes 2 positional arguments but\n3 were given"
        )

        mock_result = SyncRunResult(
            run_id=uuid4(),
            status=IngestRunStatus.PARTIAL,
            items_total=1,
            items_ok=0,
            items_failed=1,
            tx_added=0,
            tx_modified=0,
            tx_removed=0,
            item_results=[
                SyncItemResult(
                    item_id=uuid4(),
                    institution_id="ins_test",
                    institution_name="Test Bank",
                    success=False,
                    error_code="UNKNOWN_ERROR",
                    error_message=error_with_newline,
                    duration_ms=100,
                )
            ],
            started_at=datetime.now(UTC),
            ended_at=datetime.now(UTC),
            duration_ms=100,
        )

        # Mock the SyncService.run_sync to return our result
        mock_service_class = mocker.patch("budget_me.cli.commands.sync.SyncService")
        mock_service = mocker.MagicMock()
        mock_service_class.return_value = mock_service

        async def mock_run_sync(**kwargs):
            return mock_result

        mock_service.run_sync = mock_run_sync

        # Mock get_async_session context manager
        mock_session = mocker.AsyncMock()
        mock_context = mocker.MagicMock()
        mock_context.__aenter__ = mocker.AsyncMock(return_value=mock_session)
        mock_context.__aexit__ = mocker.AsyncMock(return_value=None)
        mocker.patch(
            "budget_me.cli.commands.sync.get_async_session",
            return_value=mock_context,
        )

        # Run sync with --json flag
        result = runner.invoke(app, ["sync", "--json"])

        # The output should be valid JSON
        assert result.exit_code == 1  # Partial status returns exit code 1

        # Parse the JSON output - this will fail if there are literal newlines
        try:
            output = json.loads(result.output)
        except json.JSONDecodeError as e:
            pytest.fail(
                f"JSON output is invalid: {e}\nOutput was:\n{result.output[:500]}"
            )

        # Verify the error message is present and properly escaped
        assert len(output["items"]) == 1
        assert output["items"][0]["error_message"] == error_with_newline
        assert output["items"][0]["error_code"] == "UNKNOWN_ERROR"
