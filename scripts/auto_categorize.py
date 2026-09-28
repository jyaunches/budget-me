#!/usr/bin/env python
"""GitHub Actions entry point for auto-categorization.

The script loads packaged defaults plus PostgreSQL overrides, categorizes recent
transactions, persists learned rules in the same transaction, and writes a
short-lived JSON summary for the notification step.
"""

import asyncio
import json
import os
import sys
from pathlib import Path

from budget_me.categorization.inference import MerchantInferenceClient
from budget_me.categorization.rules import is_special_merchant
from budget_me.categorization.search import MerchantSearchClient
from budget_me.categorization.service import CategorizationService
from budget_me.categorization.store import PostgresCategorizationRuleStore
from budget_me.config import get_settings
from budget_me.db.engine import get_async_session
from budget_me.db.repos.accounts_repo import AccountsRepo


def _redacted_failure_message(exc: BaseException) -> str:
    """Describe a failure without exposing provider, database, or merchant detail."""
    return (
        "Auto-categorization failed "
        f"({type(exc).__name__}); sensitive error details were withheld."
    )


async def main() -> None:
    """Run categorization with PostgreSQL-backed rule persistence."""
    settings = get_settings()

    inference = (
        MerchantInferenceClient(settings.anthropic_api_key)
        if settings.anthropic_api_key
        else None
    )
    search = (
        MerchantSearchClient(settings.tavily_api_key)
        if settings.tavily_api_key
        else None
    )

    try:
        async with get_async_session() as session:
            rule_store = PostgresCategorizationRuleStore(session)
            rule_set = await rule_store.load()

            accounts_repo = AccountsRepo(session)
            excluded_accounts = await accounts_repo.get_excluded()
            excluded_ids = {acc.account_id for acc in excluded_accounts}

            service = CategorizationService(
                session,
                rule_set.merchants,
                rule_set.categories,
                inference_client=inference,
                search_client=search,
                reimbursable_rules=rule_set.reimbursable_merchants,
                rule_store=rule_store,
            )
            result = await service.categorize_transactions(
                days=60,
                excluded_account_ids=excluded_ids,
            )
    finally:
        if search:
            await search.close()

    output = {
        "stats": {
            "total_processed": result.stats.total_processed,
            "from_rules": result.stats.from_rules,
            "from_inference": result.stats.from_inference,
            "from_search": result.stats.from_search,
            "reimbursable_flagged": result.stats.reimbursable_flagged,
            "skipped": result.stats.skipped,
            "unknown": result.stats.unknown,
        },
        "unknowns": [
            {
                "name": unknown.name,
                "amount": str(unknown.amount),
                "date": str(unknown.date),
                "reason": unknown.reason,
                "is_special_merchant": is_special_merchant(unknown.name),
            }
            for unknown in result.unknowns
        ],
    }

    output_path = Path("categorize_output.json")
    file_descriptor = os.open(
        output_path,
        os.O_WRONLY | os.O_CREAT | os.O_TRUNC,
        0o600,
    )
    os.fchmod(file_descriptor, 0o600)
    with os.fdopen(file_descriptor, "w", encoding="utf-8") as handle:
        json.dump(output, handle, indent=2)

    # Never write merchant names, dates, or amounts to public CI logs.
    print(json.dumps({"stats": output["stats"]}, indent=2))


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as exc:
        print(_redacted_failure_message(exc), file=sys.stderr)
        sys.exit(1)
