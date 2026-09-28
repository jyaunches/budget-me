#!/usr/bin/env python
"""Send sync summary notification via Telegram."""

import json
import sys
from pathlib import Path

from budget_me.notifications.telegram import send_sync_summary


def main():
    """Send notification with sync results and optional categorization results."""
    # Load sync results (required)
    sync_path = Path("sync_output.json")
    if not sync_path.exists():
        print("sync_output.json not found", file=sys.stderr)
        return False

    with sync_path.open() as f:
        sync_data = json.load(f)

    # Load categorization results (optional)
    categorize_data = None
    categorize_path = Path("categorize_output.json")
    if categorize_path.exists():
        with categorize_path.open() as f:
            categorize_data = json.load(f)

    # Send notification
    return send_sync_summary(sync_data, categorize_data)


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)