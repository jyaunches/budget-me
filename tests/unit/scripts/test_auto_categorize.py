"""Tests for scripts/auto_categorize.py."""

import ast
from pathlib import Path

from scripts.auto_categorize import _redacted_failure_message


class TestAutoCategorizeScript:
    """Tests for the auto_categorize.py script configuration."""

    def test_lookback_days_accounts_for_plaid_lag(self):
        """Test that categorization uses sufficient lookback days for Plaid sync lag.

        Plaid typically has a 1-3 day lag between when a transaction occurs
        (transaction_date) and when it appears in the sync. The categorization
        query filters by Transaction.date, not created_at, so we need a lookback
        window of at least 3 days to catch transactions that synced recently
        but have older transaction dates.

        With days=1 (the bug), transactions that synced today but have a
        transaction_date of 2+ days ago would be missed by categorization.
        """
        script_path = Path("scripts/auto_categorize.py")
        assert script_path.exists(), "auto_categorize.py script should exist"

        source = script_path.read_text()
        tree = ast.parse(source)

        # Find the call to categorize_transactions
        days_value = None
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                # Look for method call to categorize_transactions
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr == "categorize_transactions":
                        # Find the 'days' keyword argument
                        for keyword in node.keywords:
                            if keyword.arg == "days":
                                if isinstance(keyword.value, ast.Constant):
                                    days_value = keyword.value.value
                                    break

        assert days_value is not None, (
            "Could not find 'days' argument in categorize_transactions() call"
        )
        assert days_value >= 3, (
            f"categorize_transactions() uses days={days_value}, but should be >= 3 "
            f"to account for Plaid's 1-3 day sync lag. Transactions that sync today "
            f"may have transaction_dates from 2-3 days ago, which would be missed "
            f"with a smaller lookback window."
        )

    def test_rules_are_loaded_and_persisted_through_postgres_store(self):
        """The automation uses database-backed rules, not a private YAML file."""
        source = Path("scripts/auto_categorize.py").read_text(encoding="utf-8")

        assert "PostgresCategorizationRuleStore" in source
        assert "rule_set = await rule_store.load()" in source
        assert "rule_store=rule_store" in source

        for legacy_yaml_reference in (
            "get_rules_path",
            "update_rules_yaml",
            "categorization-rules.yaml",
        ):
            assert legacy_yaml_reference not in source

    def test_failure_message_does_not_expose_exception_text(self):
        """Provider and database exception details never reach shared CI logs."""
        private_detail = "merchant=Private Cafe url=postgresql://owner:secret@db"

        message = _redacted_failure_message(RuntimeError(private_detail))

        assert message == (
            "Auto-categorization failed (RuntimeError); "
            "sensitive error details were withheld."
        )
        assert private_detail not in message
        assert "Private Cafe" not in message
        assert "owner:secret" not in message
