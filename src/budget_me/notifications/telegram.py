"""Telegram notification module using python-telegram-bot."""

import asyncio
from datetime import datetime

from loguru import logger
from telegram import Bot

from budget_me.config import get_settings


def get_recipients() -> list[str]:
    """Get list of recipient chat IDs.

    Returns comma-separated chat IDs from telegram_chat_ids.

    Returns:
        List of chat IDs (e.g., ["123456789", "987654321"])
    """
    settings = get_settings()

    if settings.telegram_chat_ids:
        recipients = [
            r.strip() for r in settings.telegram_chat_ids.split(",") if r.strip()
        ]
        return recipients

    return []


def is_configured() -> bool:
    """Check if all Telegram settings are configured.

    Returns:
        True if all required Telegram settings are present, False otherwise.
    """
    settings = get_settings()
    return bool(settings.telegram_bot_token and settings.telegram_chat_ids)


def send_message(text: str) -> bool:
    """Send message to all configured Telegram chat IDs.

    Args:
        text: Message text to send

    Returns:
        True if message sent successfully to all recipients, False otherwise.
    """
    if not is_configured():
        logger.warning("Telegram not configured - skipping message send")
        return False

    settings = get_settings()
    recipients = get_recipients()

    if not recipients:
        logger.warning("No Telegram recipients configured")
        return False

    bot = Bot(token=settings.telegram_bot_token)
    success_count = 0
    fail_count = 0

    async def send_async():
        """Send messages asynchronously to all recipients."""
        nonlocal success_count, fail_count

        for chat_id in recipients:
            try:
                await bot.send_message(chat_id=chat_id, text=text)
                logger.debug("Telegram message sent")
                success_count += 1
            except Exception as e:
                logger.error(f"Telegram delivery failed: {type(e).__name__}")
                fail_count += 1

    # Run async operation synchronously
    asyncio.run(send_async())

    # Return True only if all succeeded
    return fail_count == 0 and success_count > 0


def _friendly_error_message(error_code: str | None) -> str:
    """Convert Plaid error codes to human-friendly messages.

    Args:
        error_code: Plaid error code like ITEM_LOGIN_REQUIRED

    Returns:
        Human-readable error message
    """
    error_messages = {
        "ITEM_LOGIN_REQUIRED": "Re-login required",
        "ITEM_NOT_SUPPORTED": "Account not supported",
        "INVALID_CREDENTIALS": "Invalid credentials",
        "INSTITUTION_DOWN": "Bank unavailable",
        "INSTITUTION_NOT_RESPONDING": "Bank not responding",
        "INSTITUTION_NO_LONGER_SUPPORTED": "Bank no longer supported",
        "USER_SETUP_REQUIRED": "Setup required",
        "MFA_NOT_SUPPORTED": "MFA not supported",
        "UNKNOWN_ERROR": "Unknown error",
    }
    return error_messages.get(error_code or "", error_code or "Error")


def send_sync_summary(sync_data: dict, categorize_data: dict | None) -> bool:
    """Send sync summary notification via Telegram.

    Sends formatted summary using Telegram Markdown formatting.
    No template required - Telegram supports rich formatting natively.

    Args:
        sync_data: Sync results with status, tx counts, and item counts
        categorize_data: Categorization results (optional)

    Returns:
        True on success, False if not configured or send failed
    """
    if not is_configured():
        logger.warning(
            "Telegram not configured - skipping notification. "
            "Set TELEGRAM_BOT_TOKEN and TELEGRAM_CHAT_IDS to enable notifications."
        )
        return False

    # Build message with Markdown formatting
    status = sync_data.get("status", "unknown")
    # Use appropriate emoji based on status:
    # - completed: all items succeeded
    # - partial: some items succeeded, some failed
    # - failed: all items failed
    if status == "completed":
        status_emoji = "✅"
    elif status == "partial":
        status_emoji = "⚠️"
    else:
        status_emoji = "❌"

    # Transaction counts
    tx_added = sync_data.get("tx_added", 0)
    tx_modified = sync_data.get("tx_modified", 0)
    tx_removed = sync_data.get("tx_removed", 0)

    # Bank status
    items_ok = sync_data.get("items_ok", 0)
    items_failed = sync_data.get("items_failed", 0)
    total_items = items_ok + items_failed

    # Build message lines
    lines = [
        f"{status_emoji} *Budget Sync Complete*",
        "",
        f"*Transactions:* +{tx_added} / ~{tx_modified} / -{tx_removed}",
        f"*Banks:* {items_ok}/{total_items} OK",
    ]

    # Add failed items details if any
    items = sync_data.get("items", [])
    failed_items = [item for item in items if not item.get("success", True)]
    if failed_items:
        lines.append("")
        lines.append("*Needs attention:*")
        for item in failed_items[:5]:  # Limit to 5 items
            # Prefer institution_name over institution_id for readability
            institution = (
                item.get("institution_name") or item.get("institution_id") or "Unknown"
            )
            error_code = item.get("error_code")
            friendly_msg = _friendly_error_message(error_code)
            lines.append(f"• {institution}: {friendly_msg}")
        if len(failed_items) > 5:
            remaining = len(failed_items) - 5
            lines.append(f"...and {remaining} more")

    # Add categorization details if available
    if categorize_data:
        stats = categorize_data.get("stats", {})
        unknown = stats.get("unknown", 0)

        # Special merchants section
        unknowns_list = categorize_data.get("unknowns", [])
        special_merchants = [
            u for u in unknowns_list if u.get("is_special_merchant", False)
        ]

        if special_merchants or unknown > 0:
            lines.append("")
            lines.append("*Details:*")

        if special_merchants:
            lines.append("Special merchants (review in Budget Me):")
            # Keep notifications concise and easy to scan.
            for merchant in special_merchants[:5]:
                date_str = merchant["date"]
                date_obj = datetime.strptime(date_str, "%Y-%m-%d")
                formatted_date = f"{date_obj.strftime('%b')} {date_obj.day}"
                amount = abs(float(merchant["amount"]))
                lines.append(f"• {merchant['name']} {formatted_date} ${amount:.2f}")

            if len(special_merchants) > 5:
                remaining = len(special_merchants) - 5
                lines.append(f"...and {remaining} more")

        if unknown > 0:
            lines.append(f"{unknown} unknown merchant(s) need review")

    message_text = "\n".join(lines)

    # Send using Markdown formatting
    return send_message(message_text)
