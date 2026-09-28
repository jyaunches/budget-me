"""Tests for Telegram notification module."""

from unittest.mock import AsyncMock, MagicMock, patch


class TestIsConfigured:
    """Tests for is_configured function."""

    @patch("budget_me.notifications.telegram.get_settings")
    def test_is_configured_returns_true_with_all_settings(self, mock_get_settings):
        """Returns True when all Telegram settings are configured."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = "123456789"
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import is_configured

        result = is_configured()

        assert result is True

    @patch("budget_me.notifications.telegram.get_settings")
    def test_is_configured_returns_false_with_missing_token(self, mock_get_settings):
        """Returns False when TELEGRAM_BOT_TOKEN is not set."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_ids = "123456789"
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import is_configured

        result = is_configured()

        assert result is False

    @patch("budget_me.notifications.telegram.get_settings")
    def test_is_configured_returns_false_with_missing_chat_ids(self, mock_get_settings):
        """Returns False when TELEGRAM_CHAT_IDS is not set."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = None
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import is_configured

        result = is_configured()

        assert result is False


class TestGetRecipients:
    """Tests for get_recipients helper function."""

    @patch("budget_me.notifications.telegram.get_settings")
    def test_get_recipients_parses_chat_ids(self, mock_get_settings):
        """Parses comma-separated chat IDs into list."""
        mock_settings = MagicMock()
        mock_settings.telegram_chat_ids = "123456789,987654321"
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import get_recipients

        result = get_recipients()

        assert result == ["123456789", "987654321"]

    @patch("budget_me.notifications.telegram.get_settings")
    def test_get_recipients_handles_whitespace(self, mock_get_settings):
        """Trims whitespace from chat IDs."""
        mock_settings = MagicMock()
        mock_settings.telegram_chat_ids = " 111 , 222 , 333 "
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import get_recipients

        result = get_recipients()

        assert result == ["111", "222", "333"]

    @patch("budget_me.notifications.telegram.get_settings")
    def test_get_recipients_single_chat_id(self, mock_get_settings):
        """Returns single chat ID as list."""
        mock_settings = MagicMock()
        mock_settings.telegram_chat_ids = "123456789"
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import get_recipients

        result = get_recipients()

        assert result == ["123456789"]

    @patch("budget_me.notifications.telegram.get_settings")
    def test_get_recipients_empty(self, mock_get_settings):
        """Returns empty list when no chat IDs configured."""
        mock_settings = MagicMock()
        mock_settings.telegram_chat_ids = None
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import get_recipients

        result = get_recipients()

        assert result == []


class TestSendMessage:
    """Tests for send_message function."""

    @patch("budget_me.notifications.telegram.Bot")
    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_sends_to_all_recipients(
        self, mock_get_settings, mock_bot_class
    ):
        """Sends message to all configured chat IDs."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = "111,222,333"
        mock_get_settings.return_value = mock_settings

        # Mock Bot instance with async send_message
        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        from budget_me.notifications.telegram import send_message

        result = send_message("Test message")

        assert result is True
        assert mock_bot.send_message.call_count == 3

        # Verify all chat IDs were called
        call_args_list = mock_bot.send_message.call_args_list
        chat_ids_called = [call.kwargs["chat_id"] for call in call_args_list]
        assert "111" in chat_ids_called
        assert "222" in chat_ids_called
        assert "333" in chat_ids_called

    @patch("budget_me.notifications.telegram.Bot")
    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_continues_on_partial_failure(
        self, mock_get_settings, mock_bot_class
    ):
        """Continues attempting all recipients even if one fails."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = "111,222,333"
        mock_get_settings.return_value = mock_settings

        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        # First succeeds, second fails, third succeeds
        mock_bot.send_message = AsyncMock(
            side_effect=[
                MagicMock(message_id=1),
                Exception("Telegram API error"),
                MagicMock(message_id=3),
            ]
        )

        from budget_me.notifications.telegram import send_message

        result = send_message("Test")

        # Returns False because not all succeeded
        assert result is False
        # All 3 recipients attempted
        assert mock_bot.send_message.call_count == 3

    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_gracefully_fails_when_not_configured(self, mock_get_settings):
        """Returns False and logs warning when Telegram not configured."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = None
        mock_settings.telegram_chat_ids = "123"
        mock_get_settings.return_value = mock_settings

        from budget_me.notifications.telegram import send_message

        result = send_message("Test message")

        # Graceful degradation - no exception
        assert result is False

    @patch("budget_me.notifications.telegram.Bot")
    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_single_recipient_success(
        self, mock_get_settings, mock_bot_class
    ):
        """Works correctly with single recipient."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = "123456789"
        mock_get_settings.return_value = mock_settings

        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        mock_bot.send_message = AsyncMock(return_value=MagicMock(message_id=1))

        from budget_me.notifications.telegram import send_message

        result = send_message("Test message")

        assert result is True
        assert mock_bot.send_message.call_count == 1

    @patch("budget_me.notifications.telegram.Bot")
    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_no_recipients(self, mock_get_settings, mock_bot_class):
        """Returns False when no recipients configured."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = None
        mock_get_settings.return_value = mock_settings

        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot

        from budget_me.notifications.telegram import send_message

        result = send_message("Test message")

        assert result is False
        mock_bot.send_message.assert_not_called()

    @patch("budget_me.notifications.telegram.Bot")
    @patch("budget_me.notifications.telegram.get_settings")
    def test_send_message_all_fail(self, mock_get_settings, mock_bot_class):
        """Returns False when all recipients fail."""
        mock_settings = MagicMock()
        mock_settings.telegram_bot_token = "test-telegram-token"
        mock_settings.telegram_chat_ids = "111,222"
        mock_get_settings.return_value = mock_settings

        mock_bot = MagicMock()
        mock_bot_class.return_value = mock_bot
        mock_bot.send_message = AsyncMock(side_effect=Exception("Telegram error"))

        from budget_me.notifications.telegram import send_message

        result = send_message("Test")

        assert result is False
        assert mock_bot.send_message.call_count == 2


class TestSendSyncSummary:
    """Tests for outbound-only sync summaries."""

    @patch("budget_me.notifications.telegram.send_message", return_value=True)
    @patch("budget_me.notifications.telegram.is_configured", return_value=True)
    def test_special_merchants_direct_user_to_app(
        self, _mock_is_configured, mock_send_message
    ):
        """Special merchants are reviewed in-app, not through an inbound reply."""
        from budget_me.notifications.telegram import send_sync_summary

        result = send_sync_summary(
            {
                "status": "completed",
                "items_ok": 1,
                "items_failed": 0,
                "items": [],
            },
            {
                "stats": {"unknown": 1},
                "unknowns": [
                    {
                        "is_special_merchant": True,
                        "name": "Example Merchant",
                        "date": "2026-07-30",
                        "amount": "-12.34",
                    }
                ],
            },
        )

        assert result is True
        notification = mock_send_message.call_args.args[0]
        assert "Special merchants (review in Budget Me):" in notification
        assert "reply" not in notification.lower()
