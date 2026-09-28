"""Notifications module for Budget Me."""

from budget_me.notifications.telegram import is_configured, send_sync_summary

__all__ = ["send_sync_summary", "is_configured"]
