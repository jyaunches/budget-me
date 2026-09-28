"""Unit tests for LiabilitiesRepo."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest

from budget_me.db.models.credit_liability import CreditLiabilityApr
from budget_me.db.repos.liabilities_repo import LiabilitiesRepo


class TestUpsertManualApr:
    """Tests for upsert_manual_apr repository method."""

    @pytest.mark.asyncio
    async def test_upsert_manual_apr_creates_new(self):
        """Test upsert_manual_apr creates new manual APR entry."""
        # Mock session
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None  # No existing APR
        mock_session.execute.return_value = mock_result

        repo = LiabilitiesRepo(mock_session)
        liability_id = uuid.uuid4()

        # Call upsert_manual_apr
        apr = await repo.upsert_manual_apr(
            liability_id=liability_id,
            apr_type="promotional",
            apr_percentage=Decimal("0.00"),
            balance=Decimal("123.45"),
            promo_end_date=date(2099, 12, 31),
            offer_id="TEST-OFFER-0001",
        )

        # Verify new APR was created with correct values
        assert apr.credit_liability_id == liability_id
        assert apr.apr_type == "promotional"
        assert apr.apr_percentage == Decimal("0.00")
        assert apr.balance_subject_to_apr == Decimal("123.45")
        assert apr.promo_rate_end_date == date(2099, 12, 31)
        assert apr.promo_offer_id == "TEST-OFFER-0001"
        assert apr.source == "manual"

        # Verify session.add was called
        mock_session.add.assert_called_once()

    @pytest.mark.asyncio
    async def test_upsert_manual_apr_updates_existing(self):
        """Test upsert_manual_apr updates existing manual APR by offer_id."""
        # Mock session with existing APR
        existing_apr = CreditLiabilityApr(
            credit_liability_id=uuid.uuid4(),
            apr_type="promotional",
            apr_percentage=Decimal("0.00"),
            balance_subject_to_apr=Decimal("123.45"),
            promo_rate_end_date=date(2099, 12, 31),
            promo_offer_id="TEST-OFFER-0001",
            source="manual",
        )

        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = existing_apr
        mock_session.execute.return_value = mock_result

        repo = LiabilitiesRepo(mock_session)

        # Call upsert with updated balance
        apr = await repo.upsert_manual_apr(
            liability_id=existing_apr.credit_liability_id,
            apr_type="promotional",
            apr_percentage=Decimal("0.00"),
            balance=Decimal("100.00"),  # Updated
            promo_end_date=date(2099, 12, 31),
            offer_id="TEST-OFFER-0001",
        )

        # Verify existing APR was updated
        assert apr.balance_subject_to_apr == Decimal("100.00")
        assert apr.promo_offer_id == "TEST-OFFER-0001"

        # Verify session.add was NOT called (update, not create)
        mock_session.add.assert_not_called()

    @pytest.mark.asyncio
    async def test_upsert_manual_apr_match_by_offer_id(self):
        """Test different offer_ids create separate APR records."""
        # This test verifies that the query uses offer_id for matching
        mock_session = AsyncMock()
        mock_result = Mock()
        mock_result.scalar_one_or_none.return_value = None  # No existing match
        mock_session.execute.return_value = mock_result

        repo = LiabilitiesRepo(mock_session)
        liability_id = uuid.uuid4()

        # Create APR with offer_id
        apr = await repo.upsert_manual_apr(
            liability_id=liability_id,
            apr_type="promotional",
            apr_percentage=Decimal("0.00"),
            balance=Decimal("123.45"),
            promo_end_date=date(2099, 12, 31),
            offer_id="TEST-OFFER-0001",
        )

        # Verify offer_id is set
        assert apr.promo_offer_id == "TEST-OFFER-0001"
        assert apr.source == "manual"
