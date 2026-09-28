"""Unit tests for categorization service."""

from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from budget_me.categorization.models import InferenceResult
from budget_me.categorization.service import CategorizationService
from budget_me.db.models.transaction import Transaction


@pytest.fixture
def mock_session():
    """Mock database session."""
    session = MagicMock(spec=AsyncSession)
    return session


@pytest.fixture
def sample_rules():
    """Sample merchant rules."""
    return {"Starbucks": "dining", "Costco": "groceries"}


@pytest.fixture
def sample_categories():
    """Sample category list."""
    return ["dining", "groceries", "shopping"]


@pytest.fixture
def mock_inference_client():
    """Mock inference client."""
    client = MagicMock()
    client.infer_category = AsyncMock()
    return client


@pytest.fixture
def mock_search_client():
    """Mock search client."""
    client = MagicMock()
    client.search = AsyncMock()
    return client


def make_transaction(
    name: str,
    account_id: str = "acc123",
    amount: Decimal = Decimal("10.00"),
) -> Transaction:
    """Create a test transaction."""
    txn = Transaction(
        id=uuid4(),
        plaid_transaction_id=f"txn_{uuid4()}",
        plaid_item_id=uuid4(),
        account_id=account_id,
        date=date(2026, 1, 5),
        amount=amount,
        name=name,
        pending=False,
    )
    return txn


class TestCategorizationService:
    """Tests for CategorizationService."""

    @pytest.mark.asyncio
    async def test_categorize_fetches_uncategorized_transactions(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that service fetches uncategorized transactions."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        # Mock repo method
        service.repo.get_uncategorized_since = AsyncMock(return_value=[])

        await service.categorize_transactions(days=7)

        service.repo.get_uncategorized_since.assert_called_once_with(days=7)

    @pytest.mark.asyncio
    async def test_categorize_filters_excluded_accounts(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that excluded accounts are filtered out."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        # Create transactions with different account IDs
        txn1 = make_transaction("Merchant A", account_id="acc1")
        txn2 = make_transaction("Merchant B", account_id="acc2")

        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn1, txn2])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(
            days=1, excluded_account_ids={"acc2"}
        )

        # Only txn1 should be processed (txn2 is excluded)
        assert result.stats.total_processed == 1

    @pytest.mark.asyncio
    async def test_categorize_filters_skip_patterns(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that skip patterns are filtered out."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        # Create transactions with skip patterns
        txn1 = make_transaction("PAYROLL DEPOSIT")
        txn2 = make_transaction("Starbucks")

        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn1, txn2])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        result = await service.categorize_transactions(days=1)

        # Payroll should be skipped
        assert result.stats.skipped == 1
        assert result.stats.total_processed == 1

    @pytest.mark.asyncio
    async def test_categorize_applies_known_rules_first(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that known rules are applied first."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        txn = make_transaction("Starbucks")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        result = await service.categorize_transactions(days=1)

        # Should be categorized via rules
        assert result.stats.from_rules == 1
        assert "dining" in result.categorized
        assert txn.id in result.categorized["dining"]

    @pytest.mark.asyncio
    async def test_categorize_tries_inference_for_unknown(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that inference is tried for unknown merchants."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        # Unknown merchant
        txn = make_transaction("Unknown Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        # Mock inference response
        mock_inference_client.infer_category.return_value = InferenceResult(
            category="dining", confidence="high"
        )

        result = await service.categorize_transactions(days=1)

        # Should call inference
        mock_inference_client.infer_category.assert_called_once()
        assert result.stats.from_inference == 1

    @pytest.mark.asyncio
    async def test_categorize_tries_search_for_low_confidence(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
        mock_search_client,
    ):
        """Test that search is tried for low confidence inference."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
            search_client=mock_search_client,
        )

        txn = make_transaction("VUYNRP")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        # Mock low confidence inference, then successful search + inference
        mock_inference_client.infer_category.side_effect = [
            InferenceResult(category=None, confidence="low"),
            InferenceResult(category="shopping", confidence="high"),
        ]
        mock_search_client.search.return_value = "Online retail store"

        result = await service.categorize_transactions(days=1)

        # Should call search
        mock_search_client.search.assert_called_once()
        assert result.stats.from_search == 1

    @pytest.mark.asyncio
    async def test_categorize_collects_unknowns(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that unknown merchants are collected."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        txn = make_transaction("Unknown Shop", amount=Decimal("42.50"))
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(days=1)

        # Should be in unknowns
        assert result.stats.unknown == 1
        assert len(result.unknowns) == 1
        assert result.unknowns[0].name == "Unknown Shop"
        assert result.unknowns[0].amount == Decimal("42.50")

    @pytest.mark.asyncio
    async def test_categorize_updates_database(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that database is updated with categories."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        txn = make_transaction("Starbucks")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        await service.categorize_transactions(days=1)

        # Should update database
        service.repo.bulk_update_budget_category.assert_called_once_with(
            [txn.id], "dining"
        )

    @pytest.mark.asyncio
    async def test_categorize_builds_new_rules(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that new rules are built from inference."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        txn = make_transaction("New Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)

        mock_inference_client.infer_category.return_value = InferenceResult(
            category="dining", confidence="high"
        )

        result = await service.categorize_transactions(days=1)

        # Should create new rule
        assert "New Cafe" in result.new_rules
        assert result.new_rules["New Cafe"] == "dining"

    @pytest.mark.asyncio
    async def test_categorize_persists_new_rules_through_injected_store(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Learned rules use the injected store in the transaction's session."""
        rule_store = MagicMock()
        rule_store.persist_learned = AsyncMock(return_value=1)
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
            rule_store=rule_store,
        )
        txn = make_transaction("New Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=1)
        mock_inference_client.infer_category.return_value = InferenceResult(
            category="dining", confidence="high"
        )

        await service.categorize_transactions(days=1)

        rule_store.persist_learned.assert_awaited_once_with({"New Cafe": "dining"})

    @pytest.mark.asyncio
    async def test_categorize_works_without_inference_client(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that service works without inference client."""
        service = CategorizationService(
            mock_session, sample_rules, sample_categories, inference_client=None
        )

        # Unknown merchant (not in rules)
        txn = make_transaction("Unknown Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(days=1)

        # Should go to unknowns (skip inference tier)
        assert result.stats.from_inference == 0
        assert result.stats.unknown == 1

    @pytest.mark.asyncio
    async def test_categorize_works_without_search_client(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that service works without search client."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
            search_client=None,
        )

        txn = make_transaction("Unknown Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        # Mock low confidence
        mock_inference_client.infer_category.return_value = InferenceResult(
            category=None, confidence="low"
        )

        result = await service.categorize_transactions(days=1)

        # Should go to unknowns (skip search tier)
        assert result.stats.from_search == 0
        assert result.stats.unknown == 1

    @pytest.mark.asyncio
    async def test_categorize_handles_empty_transaction_list(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that empty transaction list is handled gracefully."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        service.repo.get_uncategorized_since = AsyncMock(return_value=[])

        result = await service.categorize_transactions(days=1)

        # Should return empty result
        assert result.stats.total_processed == 0
        assert len(result.categorized) == 0

    @pytest.mark.asyncio
    async def test_categorize_multiple_transactions_same_category(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test multiple transactions categorized to same category."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        txn1 = make_transaction("Starbucks")
        txn2 = make_transaction("Starbucks")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn1, txn2])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=2)

        result = await service.categorize_transactions(days=1)

        # Both should be in same category
        assert result.stats.from_rules == 2
        assert len(result.categorized["dining"]) == 2

    @pytest.mark.asyncio
    async def test_categorize_only_accepts_high_medium_confidence(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that only high/medium confidence results are accepted."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        txn = make_transaction("Unknown Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        # Mock low confidence
        mock_inference_client.infer_category.return_value = InferenceResult(
            category="dining", confidence="low"
        )

        result = await service.categorize_transactions(days=1)

        # Should not be categorized
        assert result.stats.from_inference == 0
        assert result.stats.unknown == 1

    @pytest.mark.asyncio
    async def test_categorize_detects_special_merchants_early(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that special merchants are detected before inference tier."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        # Venmo transaction
        txn = make_transaction("Venmo")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(days=1)

        # Should NOT call inference (detected as special merchant)
        mock_inference_client.infer_category.assert_not_called()
        # Should be in unknowns
        assert result.stats.unknown == 1
        assert len(result.unknowns) == 1
        assert result.unknowns[0].name == "Venmo"
        assert result.unknowns[0].reason == "Special merchant - manual review required"

    @pytest.mark.asyncio
    async def test_categorize_skips_inference_for_venmo_payment(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that 'Venmo Payment' skips inference tier."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        txn = make_transaction("Venmo Payment")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(days=1)

        # Should NOT call inference
        mock_inference_client.infer_category.assert_not_called()
        assert result.stats.unknown == 1
        assert result.unknowns[0].reason == "Special merchant - manual review required"

    @pytest.mark.asyncio
    async def test_categorize_skips_search_for_special_merchants(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
        mock_search_client,
    ):
        """Test that special merchants skip search tier."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
            search_client=mock_search_client,
        )

        txn = make_transaction("Zelle")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        result = await service.categorize_transactions(days=1)

        # Should NOT call inference or search
        mock_inference_client.infer_category.assert_not_called()
        mock_search_client.search.assert_not_called()
        assert result.stats.unknown == 1
        assert result.unknowns[0].name == "Zelle"

    @pytest.mark.asyncio
    async def test_categorize_special_merchant_with_account_name(
        self, mock_session, sample_rules, sample_categories
    ):
        """Test that special merchants include account name in unknown."""
        service = CategorizationService(mock_session, sample_rules, sample_categories)

        txn = make_transaction("Cash App", account_id="acc123")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        # Pass account name mapping
        result = await service.categorize_transactions(
            days=1, account_names={"acc123": "Test Checking"}
        )

        # Should include account name
        assert result.stats.unknown == 1
        assert result.unknowns[0].name == "Cash App"
        assert result.unknowns[0].account_name == "Test Checking"
        assert result.unknowns[0].reason == "Special merchant - manual review required"

    @pytest.mark.asyncio
    async def test_categorize_mixes_special_and_regular_unknowns(
        self,
        mock_session,
        sample_rules,
        sample_categories,
        mock_inference_client,
    ):
        """Test that special merchants and regular unknowns are both collected."""
        service = CategorizationService(
            mock_session,
            sample_rules,
            sample_categories,
            inference_client=mock_inference_client,
        )

        # Mix of special merchant and regular unknown
        txn1 = make_transaction("Venmo")
        txn2 = make_transaction("Unknown Cafe")
        service.repo.get_uncategorized_since = AsyncMock(return_value=[txn1, txn2])
        service.repo.bulk_update_budget_category = AsyncMock(return_value=0)

        # Mock inference for regular unknown
        mock_inference_client.infer_category.return_value = InferenceResult(
            category=None, confidence="low"
        )

        result = await service.categorize_transactions(days=1)

        # Should have 2 unknowns with different reasons
        assert result.stats.unknown == 2
        assert len(result.unknowns) == 2

        # Find each unknown by name
        venmo_unknown = next(u for u in result.unknowns if u.name == "Venmo")
        regular_unknown = next(u for u in result.unknowns if u.name == "Unknown Cafe")

        assert venmo_unknown.reason == "Special merchant - manual review required"
        assert regular_unknown.reason == "No category found"

        # Inference should only be called once (for non-special merchant)
        assert mock_inference_client.infer_category.call_count == 1
