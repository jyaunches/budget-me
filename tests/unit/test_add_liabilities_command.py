"""Unit tests for add-liabilities CLI command."""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from typer.testing import CliRunner

from budget_me.cli.main import app
from budget_me.db.models.plaid_item import PlaidItem, PlaidItemStatus

runner = CliRunner()


class TestAddLiabilitiesCommand:
    """Tests for budget-me add-liabilities command."""

    @pytest.fixture
    def mock_item(self):
        """Create a mock PlaidItem."""
        item = PlaidItem(
            user_key="user_123",
            item_id="item_123",
            access_token_enc=b"encrypted_token",
            institution_id="ins_1",
            status=PlaidItemStatus.ACTIVE,
        )
        item.id = uuid.uuid4()
        item.products = ["transactions"]
        return item

    @pytest.fixture
    def mock_multiple_items(self, mock_item):
        """Create multiple mock PlaidItems."""
        item2 = PlaidItem(
            user_key="user_123",
            item_id="item_456",
            access_token_enc=b"encrypted_token_2",
            institution_id="ins_2",
            status=PlaidItemStatus.ACTIVE,
        )
        item2.id = uuid.uuid4()
        item2.products = ["transactions"]
        return [mock_item, item2]

    def test_add_liabilities_command_with_item_id_flag(self, mock_item):
        """Test `budget-me add-liabilities --item-id <uuid>` launches upgrade flow for that item."""
        item_id = str(mock_item.id)

        with patch("budget_me.cli.commands.add_liabilities.get_async_session"):
            with patch(
                "budget_me.cli.commands.add_liabilities.ItemsRepo"
            ) as mock_repo_class:
                with patch(
                    "budget_me.cli.commands.add_liabilities.webbrowser.open"
                ) as mock_browser:
                    with patch(
                        "budget_me.cli.commands.add_liabilities.start_link_server"
                    ) as mock_server:
                        # Setup mocks
                        mock_repo = AsyncMock()
                        mock_repo.get_by_id.return_value = mock_item
                        mock_repo_class.return_value = mock_repo
                        mock_server.return_value = None

                        result = runner.invoke(
                            app, ["add-liabilities", "--item-id", item_id]
                        )

                        # Verify command succeeds
                        assert result.exit_code == 0

                        # Verify browser opened with update mode URL
                        mock_browser.assert_called_once()
                        call_args = mock_browser.call_args[0][0]
                        assert "mode=update" in call_args
                        assert f"item_id={mock_item.id}" in call_args

                        # Verify server was started
                        mock_server.assert_called_once()

    def test_add_liabilities_command_without_flags_processes_all_items(
        self, mock_multiple_items
    ):
        """Test `budget-me add-liabilities` processes all active items sequentially."""
        with patch("budget_me.cli.commands.add_liabilities.get_async_session"):
            with patch(
                "budget_me.cli.commands.add_liabilities.ItemsRepo"
            ) as mock_repo_class:
                with patch(
                    "budget_me.cli.commands.add_liabilities.webbrowser.open"
                ) as mock_browser:
                    with patch(
                        "budget_me.cli.commands.add_liabilities.start_link_server"
                    ) as mock_server:
                        # Setup mocks
                        mock_repo = AsyncMock()
                        mock_repo.find_active.return_value = mock_multiple_items
                        mock_repo_class.return_value = mock_repo
                        mock_server.return_value = None

                        result = runner.invoke(app, ["add-liabilities"])

                        # Verify command succeeds
                        assert result.exit_code == 0

                        # Verify browser opened for each item
                        assert mock_browser.call_count == 2

                        # Verify server started for each item
                        assert mock_server.call_count == 2

    def test_add_liabilities_command_validates_item_exists(self):
        """Test `budget-me add-liabilities --item-id <invalid>` shows error."""
        invalid_id = str(uuid.uuid4())

        with patch("budget_me.cli.commands.add_liabilities.get_async_session"):
            with patch(
                "budget_me.cli.commands.add_liabilities.ItemsRepo"
            ) as mock_repo_class:
                # Setup mocks
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = None  # Item not found
                mock_repo_class.return_value = mock_repo

                result = runner.invoke(
                    app, ["add-liabilities", "--item-id", invalid_id]
                )

                # Verify command fails
                assert result.exit_code == 1

                # Verify error message
                assert "not found" in result.stdout.lower()

    def test_add_liabilities_command_handles_keyboard_interrupt(self, mock_item):
        """Test add-liabilities handles Ctrl+C gracefully."""
        item_id = str(mock_item.id)

        with patch("budget_me.cli.commands.add_liabilities.get_async_session"):
            with patch(
                "budget_me.cli.commands.add_liabilities.ItemsRepo"
            ) as mock_repo_class:
                with patch("budget_me.cli.commands.add_liabilities.webbrowser.open"):
                    with patch(
                        "budget_me.cli.commands.add_liabilities.start_link_server"
                    ) as mock_server:
                        # Setup mocks
                        mock_repo = AsyncMock()
                        mock_repo.get_by_id.return_value = mock_item
                        mock_repo_class.return_value = mock_repo

                        # Simulate Ctrl+C
                        mock_server.side_effect = KeyboardInterrupt()

                        result = runner.invoke(
                            app, ["add-liabilities", "--item-id", item_id]
                        )

                        # Verify graceful exit (not crash)
                        assert result.exit_code == 0

                        # Verify graceful shutdown message
                        assert "stopped" in result.stdout.lower()

    def test_add_liabilities_command_appears_in_help(self):
        """Test `budget-me --help` lists add-liabilities command."""
        result = runner.invoke(app, ["--help"])

        assert result.exit_code == 0
        assert "add-liabilities" in result.stdout
