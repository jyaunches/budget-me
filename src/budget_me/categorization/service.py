"""Categorization service for orchestrating transaction categorization workflow.

This service composes rules, inference, and search tiers to categorize transactions.
"""

from loguru import logger
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.categorization.inference import MerchantInferenceClient
from budget_me.categorization.models import (
    CategorizationResult,
    UnknownMerchant,
)
from budget_me.categorization.rules import (
    is_special_merchant,
    match_merchant,
    match_reimbursable,
    should_skip,
)
from budget_me.categorization.search import MerchantSearchClient
from budget_me.categorization.store import CategorizationRuleStore
from budget_me.db.models.transaction import Transaction
from budget_me.db.repos.transactions import TransactionsRepo


class CategorizationService:
    """Orchestrates transaction categorization workflow.

    Follows composition pattern - receives all dependencies via constructor.
    """

    def __init__(
        self,
        session: AsyncSession,
        rules: dict[str, str],
        categories: list[str],
        inference_client: MerchantInferenceClient | None = None,
        search_client: MerchantSearchClient | None = None,
        reimbursable_rules: dict[str, str] | None = None,
        rule_store: CategorizationRuleStore | None = None,
    ):
        """Initialize the service.

        Args:
            session: Database session
            rules: Merchant→category mapping dict
            categories: List of valid category names
            inference_client: Optional Claude inference client
            search_client: Optional Tavily search client
            reimbursable_rules: Optional merchant→group tag mapping for reimbursable expenses
            rule_store: Optional persistence for newly inferred merchant mappings
        """
        self.repo = TransactionsRepo(session)
        self.rules = rules
        self.categories = categories
        self.inference = inference_client
        self.search = search_client
        self.reimbursable_rules = reimbursable_rules
        self.rule_store = rule_store

    async def categorize_transactions(
        self,
        days: int = 1,
        excluded_account_ids: set[str] | None = None,
        account_names: dict[str, str] | None = None,
    ) -> CategorizationResult:
        """Run full categorization workflow.

        1. Fetch uncategorized transactions
        2. Filter excluded accounts and skip patterns
        3. Apply known rules
        4. Try Claude inference for unknowns
        5. Try web search for remaining unknowns
        6. Update database
        7. Return results for persistence/reporting

        Args:
            days: Number of days to look back
            excluded_account_ids: Account IDs to exclude from processing
            account_names: Mapping of account_id to display name for unknown merchants

        Returns:
            CategorizationResult with stats and categorized transactions
        """
        result = CategorizationResult()
        excluded_account_ids = excluded_account_ids or set()
        account_names = account_names or {}

        # 1. Fetch uncategorized transactions
        transactions = await self.repo.get_uncategorized_since(days=days)
        logger.info(f"Found {len(transactions)} uncategorized transactions")

        if not transactions:
            return result

        # 2. Filter excluded accounts, skip patterns, and detect special merchants
        to_process = []
        for txn in transactions:
            if txn.account_id in excluded_account_ids:
                continue

            if should_skip(txn.name):
                result.stats.skipped += 1
                continue

            # Detect special merchants early (before rules/inference/search)
            if is_special_merchant(txn.name):
                result.unknowns.append(
                    UnknownMerchant(
                        name=txn.name,
                        amount=txn.amount,
                        date=txn.date,
                        reason="Special merchant - manual review required",
                        account_name=account_names.get(txn.account_id, ""),
                    )
                )
                result.stats.unknown += 1
                continue

            to_process.append(txn)

        result.stats.total_processed = len(to_process)
        logger.info(
            f"Processing {len(to_process)} transactions "
            f"({result.stats.skipped} skipped)"
        )

        # 3. Apply known rules
        remaining = await self._apply_rules(to_process, result)

        # 4. Try Claude inference for unknowns
        if self.inference and remaining:
            remaining = await self._apply_inference(remaining, result)

        # 5. Try web search for remaining unknowns
        if self.search and remaining:
            remaining = await self._apply_search(remaining, result)

        # 6. Collect truly unknown merchants
        for txn in remaining:
            result.unknowns.append(
                UnknownMerchant(
                    name=txn.name,
                    amount=txn.amount,
                    date=txn.date,
                    reason="No category found",
                    account_name=account_names.get(txn.account_id, ""),
                )
            )
            result.stats.unknown += 1

        # 7. Update database with categorized transactions
        await self._update_database(result)

        logger.info(
            f"Categorization complete: "
            f"{result.stats.from_rules} from rules, "
            f"{result.stats.from_inference} from inference, "
            f"{result.stats.from_search} from search, "
            f"{result.stats.unknown} unknown"
        )

        return result

    async def _apply_rules(
        self,
        transactions: list[Transaction],
        result: CategorizationResult,
    ) -> list[Transaction]:
        """Apply known rules to transactions.

        Args:
            transactions: Transactions to categorize
            result: Result object to update

        Returns:
            List of transactions that didn't match any rule
        """
        remaining = []

        for txn in transactions:
            match = match_merchant(txn.name, self.rules)
            if match:
                category, matched_key = match
                # Add to categorized
                if category not in result.categorized:
                    result.categorized[category] = []
                result.categorized[category].append(txn.id)
                result.stats.from_rules += 1
                logger.debug("Matched transaction using a local rule")
            else:
                remaining.append(txn)

            # Check if merchant is reimbursable (additive - doesn't replace category)
            if self.reimbursable_rules:
                group = match_reimbursable(txn.name, self.reimbursable_rules)
                if group:
                    result.reimbursable_flagged[txn.id] = group
                    result.stats.reimbursable_flagged += 1
                    logger.debug("Flagged transaction as reimbursable")

        return remaining

    async def _apply_inference(
        self,
        transactions: list[Transaction],
        result: CategorizationResult,
    ) -> list[Transaction]:
        """Apply Claude inference to transactions.

        Args:
            transactions: Transactions to categorize
            result: Result object to update

        Returns:
            List of transactions that weren't confidently categorized
        """
        remaining = []

        for txn in transactions:
            inference_result = await self.inference.infer_category(
                txn.name, self.categories
            )

            # Accept high or medium confidence
            if inference_result.category and inference_result.confidence in [
                "high",
                "medium",
            ]:
                category = inference_result.category
                # Add to categorized
                if category not in result.categorized:
                    result.categorized[category] = []
                result.categorized[category].append(txn.id)
                result.stats.from_inference += 1

                # Add to new rules (to persist to YAML)
                result.new_rules[txn.name] = category

                logger.debug("Inferred a transaction category")
            else:
                remaining.append(txn)

        return remaining

    async def _apply_search(
        self,
        transactions: list[Transaction],
        result: CategorizationResult,
    ) -> list[Transaction]:
        """Apply web search and re-inference to transactions.

        Args:
            transactions: Transactions to categorize
            result: Result object to update

        Returns:
            List of transactions that couldn't be categorized via search
        """
        remaining = []

        for txn in transactions:
            # Search for merchant info
            search_content = await self.search.search(txn.name)

            if not search_content:
                remaining.append(txn)
                continue

            # Re-run inference with search context
            if self.inference:
                inference_result = await self.inference.infer_category(
                    f"{txn.name} - {search_content[:200]}", self.categories
                )

                if inference_result.category and inference_result.confidence in [
                    "high",
                    "medium",
                ]:
                    category = inference_result.category
                    # Add to categorized
                    if category not in result.categorized:
                        result.categorized[category] = []
                    result.categorized[category].append(txn.id)
                    result.stats.from_search += 1

                    # Add to new rules
                    result.new_rules[txn.name] = category

                    logger.debug("Inferred a transaction category after search")
                else:
                    remaining.append(txn)
            else:
                remaining.append(txn)

        return remaining

    async def _update_database(self, result: CategorizationResult) -> None:
        """Update database with categorized transactions.

        Args:
            result: Categorization result with transaction IDs and categories
        """
        for category, transaction_ids in result.categorized.items():
            if transaction_ids:
                count = await self.repo.bulk_update_budget_category(
                    transaction_ids, category
                )
                logger.debug(f"Updated {count} categorized transactions")

        # Update reimbursable flags
        if result.reimbursable_flagged:
            count = await self.repo.update_reimbursable(
                list(result.reimbursable_flagged.keys()),
                reimbursable=True,
                status="pending",
                notes=result.reimbursable_flagged,
            )
            logger.debug(f"Updated {count} transactions with reimbursable flags")

        if result.new_rules and self.rule_store:
            count = await self.rule_store.persist_learned(result.new_rules)
            logger.debug(f"Persisted {count} newly inferred categorization rules")
