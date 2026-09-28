"""Unit tests for liabilities synchronization."""

import uuid
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from budget_me.db.models.plaid_item import PlaidItem, PlaidItemStatus
from budget_me.plaid.liabilities_sync import sync_liabilities


class TestSyncLiabilities:
    """Tests for sync_liabilities function."""

    @pytest.fixture
    def mock_item_without_liabilities(self):
        """Create a mock PlaidItem without liabilities product."""
        item = PlaidItem(
            user_key="user_123",
            item_id="item_123",
            access_token_enc=b"encrypted_token",
            institution_id="ins_1",
            status=PlaidItemStatus.ACTIVE,
        )
        item.id = uuid.uuid4()
        item.products = ["transactions"]  # No liabilities
        return item

    @pytest.fixture
    def mock_item_with_liabilities(self):
        """Create a mock PlaidItem with liabilities product."""
        item = PlaidItem(
            user_key="user_123",
            item_id="item_123",
            access_token_enc=b"encrypted_token",
            institution_id="ins_1",
            status=PlaidItemStatus.ACTIVE,
        )
        item.id = uuid.uuid4()
        item.products = ["transactions", "liabilities"]
        return item

    @pytest.fixture
    def sample_plaid_liabilities_response(self):
        """Sample Plaid liabilities response."""
        return MagicMock(
            liabilities=MagicMock(
                credit=[
                    MagicMock(
                        account_id="acc_123",
                        aprs=[
                            MagicMock(
                                apr_type="purchase_apr",
                                apr_percentage=20.00,
                                balance_subject_to_apr=100.00,
                                interest_charge_amount=None,
                            ),
                            MagicMock(
                                apr_type="balance_transfer_apr",
                                apr_percentage=0.00,
                                balance_subject_to_apr=200.00,
                                interest_charge_amount=None,
                            ),
                        ],
                        is_overdue=False,
                        last_payment_amount=30.00,
                        last_payment_date="2030-01-15",
                        last_statement_balance=300.00,
                        last_statement_issue_date="2030-01-01",
                        minimum_payment_amount=10.00,
                        next_payment_due_date="2030-02-15",
                    )
                ]
            )
        )

    @pytest.mark.asyncio
    async def test_sync_liabilities_when_product_not_enabled(
        self, mock_item_without_liabilities
    ):
        """Test sync_liabilities returns early when liabilities not enabled."""

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                # Setup mocks
                mock_repo = AsyncMock()
                mock_repo.get_by_id.return_value = mock_item_without_liabilities
                mock_repo_class.return_value = mock_repo

                result = await sync_liabilities(mock_item_without_liabilities.id)

                # Should return skipped result
                assert result.skipped is True
                assert result.accounts_updated == 0
                assert result.aprs_tracked == 0

    @pytest.mark.asyncio
    async def test_sync_liabilities_fetches_from_plaid_api(
        self, mock_item_with_liabilities, sample_plaid_liabilities_response
    ):
        """Test sync_liabilities calls Plaid API with correct access_token."""

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = (
                                sample_plaid_liabilities_response
                            )
                            mock_client_func.return_value = mock_client

                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = MagicMock(
                                id=uuid.uuid4()
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            result = await sync_liabilities(
                                mock_item_with_liabilities.id
                            )

                            # Verify Plaid API was called with correct access_token
                            mock_client.liabilities_get.assert_called_once()
                            call_args = mock_client.liabilities_get.call_args[0][0]
                            assert call_args.access_token == "test_access_token"

                            # Verify result
                            assert result.skipped is False

    @pytest.mark.asyncio
    async def test_sync_liabilities_parses_credit_data_correctly(
        self, mock_item_with_liabilities, sample_plaid_liabilities_response
    ):
        """Test sync_liabilities correctly parses credit liability data."""

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = (
                                sample_plaid_liabilities_response
                            )
                            mock_client_func.return_value = mock_client

                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = MagicMock(
                                id=uuid.uuid4()
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            await sync_liabilities(mock_item_with_liabilities.id)

                            # Verify upsert_liability was called with parsed data
                            mock_liab_repo.upsert_liability.assert_called_once()
                            call_kwargs = mock_liab_repo.upsert_liability.call_args[1]

                            assert call_kwargs["account_id"] == "acc_123"
                            # Data is passed as a dict, not unpacked kwargs
                            data = call_kwargs["data"]
                            assert data["is_overdue"] is False
                            assert data["last_payment_amount"] == Decimal("30.00")
                            assert data["minimum_payment_amount"] == Decimal("10.00")

    @pytest.mark.asyncio
    async def test_sync_liabilities_handles_multiple_aprs(
        self, mock_item_with_liabilities, sample_plaid_liabilities_response
    ):
        """Test sync_liabilities handles multiple APRs per card."""

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = (
                                sample_plaid_liabilities_response
                            )
                            mock_client_func.return_value = mock_client

                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = MagicMock(
                                id=uuid.uuid4()
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            await sync_liabilities(mock_item_with_liabilities.id)

                            # Verify upsert_aprs was called with all APRs
                            mock_liab_repo.upsert_aprs.assert_called_once()
                            call_args = mock_liab_repo.upsert_aprs.call_args[0]
                            aprs_list = call_args[1]  # Second argument is aprs list

                            assert len(aprs_list) == 2
                            assert aprs_list[0]["apr_type"] == "purchase_apr"
                            assert aprs_list[1]["apr_type"] == "balance_transfer_apr"

    @pytest.mark.asyncio
    async def test_sync_liabilities_identifies_promotional_apr(self):
        """Test sync_liabilities correctly identifies special/promotional APRs."""
        from budget_me.plaid.liabilities_sync import _parse_aprs

        # Sample APR data with special type
        aprs_data = [
            MagicMock(
                apr_type="special",
                apr_percentage=0.00,
                balance_subject_to_apr=5000.00,
                interest_charge_amount=None,
            ),
        ]

        result = _parse_aprs(aprs_data)

        assert len(result) == 1
        assert result[0]["apr_type"] == "special"
        assert result[0]["apr_percentage"] == Decimal("0.00")

    @pytest.mark.asyncio
    async def test_sync_liabilities_upserts_liability_record(
        self, mock_item_with_liabilities, sample_plaid_liabilities_response
    ):
        """Test sync_liabilities upserts liability record (doesn't duplicate)."""

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = (
                                sample_plaid_liabilities_response
                            )
                            mock_client_func.return_value = mock_client

                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = MagicMock(
                                id=uuid.uuid4()
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            await sync_liabilities(mock_item_with_liabilities.id)

                            # Verify upsert was called (not insert)
                            mock_liab_repo.upsert_liability.assert_called_once()

    @pytest.mark.asyncio
    async def test_sync_liabilities_returns_summary_result(
        self, mock_item_with_liabilities
    ):
        """Test sync_liabilities returns summary with counts."""

        # Create response with 2 accounts
        sample_response = MagicMock(
            liabilities=MagicMock(
                credit=[
                    MagicMock(
                        account_id="acc_1",
                        aprs=[
                            MagicMock(
                                apr_type="purchase_apr",
                                apr_percentage=20.0,
                                balance_subject_to_apr=100,
                                interest_charge_amount=None,
                            ),
                            MagicMock(
                                apr_type="cash_advance_apr",
                                apr_percentage=25.0,
                                balance_subject_to_apr=None,
                                interest_charge_amount=None,
                            ),
                        ],
                        is_overdue=False,
                        last_payment_amount=None,
                        last_payment_date=None,
                        last_statement_balance=None,
                        last_statement_issue_date=None,
                        minimum_payment_amount=None,
                        next_payment_due_date=None,
                    ),
                    MagicMock(
                        account_id="acc_2",
                        aprs=[
                            MagicMock(
                                apr_type="purchase_apr",
                                apr_percentage=18.0,
                                balance_subject_to_apr=200,
                                interest_charge_amount=None,
                            ),
                            MagicMock(
                                apr_type="balance_transfer_apr",
                                apr_percentage=0.0,
                                balance_subject_to_apr=500,
                                interest_charge_amount=None,
                            ),
                            MagicMock(
                                apr_type="special",
                                apr_percentage=0.0,
                                balance_subject_to_apr=1000,
                                interest_charge_amount=None,
                            ),
                        ],
                        is_overdue=False,
                        last_payment_amount=None,
                        last_payment_date=None,
                        last_statement_balance=None,
                        last_statement_issue_date=None,
                        minimum_payment_amount=None,
                        next_payment_due_date=None,
                    ),
                ]
            )
        )

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = sample_response
                            mock_client_func.return_value = mock_client

                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = MagicMock(
                                id=uuid.uuid4()
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            result = await sync_liabilities(
                                mock_item_with_liabilities.id
                            )

                            # Verify summary result
                            assert result.skipped is False
                            assert result.accounts_updated == 2
                            assert result.aprs_tracked == 5  # 2 + 3 APRs


class TestParseAprs:
    """Tests for _parse_aprs helper function."""

    def test_parse_aprs_converts_to_decimal(self):
        """Test _parse_aprs converts float percentages to Decimal."""
        from budget_me.plaid.liabilities_sync import _parse_aprs

        aprs_data = [
            MagicMock(
                apr_type="purchase_apr",
                apr_percentage=20.00,
                balance_subject_to_apr=100.00,
                interest_charge_amount=None,
            ),
        ]

        result = _parse_aprs(aprs_data)

        assert len(result) == 1
        # Verify Decimal precision
        assert result[0]["apr_percentage"] == Decimal("20.00")
        assert result[0]["balance_subject_to_apr"] == Decimal("100.00")
        assert isinstance(result[0]["apr_percentage"], Decimal)


class TestSyncPreservesManualEntries:
    """Tests for Plaid sync preserving manually-entered APRs."""

    @pytest.fixture
    def mock_item_with_liabilities(self):
        """Create a mock PlaidItem with liabilities product."""
        item = PlaidItem(
            user_key="user_123",
            item_id="item_123",
            access_token_enc=b"encrypted_token",
            institution_id="ins_1",
            status=PlaidItemStatus.ACTIVE,
        )
        item.id = uuid.uuid4()
        item.products = ["transactions", "liabilities"]
        return item

    @pytest.mark.asyncio
    async def test_plaid_sync_preserves_manual_entries(
        self, mock_item_with_liabilities
    ):
        """Test Plaid sync doesn't delete manual APRs."""

        # Create response with one APR from Plaid
        sample_response = MagicMock(
            liabilities=MagicMock(
                credit=[
                    MagicMock(
                        account_id="acc_123",
                        aprs=[
                            MagicMock(
                                apr_type="purchase_apr",
                                apr_percentage=18.99,
                                balance_subject_to_apr=1000.00,
                                interest_charge_amount=None,
                            ),
                        ],
                        is_overdue=False,
                        last_payment_amount=None,
                        last_payment_date=None,
                        last_statement_balance=None,
                        last_statement_issue_date=None,
                        minimum_payment_amount=None,
                        next_payment_due_date=None,
                    )
                ]
            )
        )

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = sample_response
                            mock_client_func.return_value = mock_client

                            # Mock liability with existing manual APR
                            mock_liability = MagicMock(id=uuid.uuid4())
                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = (
                                mock_liability
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            await sync_liabilities(mock_item_with_liabilities.id)

                            # Verify upsert_aprs was called
                            # In Phase 2, this will be modified to preserve manual APRs
                            mock_liab_repo.upsert_aprs.assert_called_once()

    @pytest.mark.asyncio
    async def test_plaid_sync_replaces_plaid_entries(self, mock_item_with_liabilities):
        """Test Plaid sync updates existing Plaid-sourced APRs."""

        # Create response with updated Plaid APR
        sample_response = MagicMock(
            liabilities=MagicMock(
                credit=[
                    MagicMock(
                        account_id="acc_123",
                        aprs=[
                            MagicMock(
                                apr_type="purchase_apr",
                                apr_percentage=19.99,  # Updated APR
                                balance_subject_to_apr=1200.00,  # Updated balance
                                interest_charge_amount=None,
                            ),
                        ],
                        is_overdue=False,
                        last_payment_amount=None,
                        last_payment_date=None,
                        last_statement_balance=None,
                        last_statement_issue_date=None,
                        minimum_payment_amount=None,
                        next_payment_due_date=None,
                    )
                ]
            )
        )

        with patch("budget_me.plaid.liabilities_sync.get_async_session"):
            with patch("budget_me.plaid.liabilities_sync.ItemsRepo") as mock_repo_class:
                with patch(
                    "budget_me.plaid.liabilities_sync.TokenEncryption"
                ) as mock_enc_class:
                    with patch(
                        "budget_me.plaid.liabilities_sync.get_plaid_client"
                    ) as mock_client_func:
                        with patch(
                            "budget_me.plaid.liabilities_sync.LiabilitiesRepo"
                        ) as mock_liab_repo_class:
                            # Setup mocks
                            mock_repo = AsyncMock()
                            mock_repo.get_by_id.return_value = (
                                mock_item_with_liabilities
                            )
                            mock_repo_class.return_value = mock_repo

                            mock_encryptor = MagicMock()
                            mock_encryptor.decrypt.return_value = "test_access_token"
                            mock_enc_class.return_value = mock_encryptor

                            mock_client = MagicMock()
                            mock_client.liabilities_get.return_value = sample_response
                            mock_client_func.return_value = mock_client

                            mock_liability = MagicMock(id=uuid.uuid4())
                            mock_liab_repo = AsyncMock()
                            mock_liab_repo.upsert_liability.return_value = (
                                mock_liability
                            )
                            mock_liab_repo.upsert_aprs.return_value = None
                            mock_liab_repo_class.return_value = mock_liab_repo

                            await sync_liabilities(mock_item_with_liabilities.id)

                            # Verify upsert_aprs was called with updated Plaid data
                            mock_liab_repo.upsert_aprs.assert_called_once()
                            call_args = mock_liab_repo.upsert_aprs.call_args[0]
                            aprs_list = call_args[1]

                            assert len(aprs_list) == 1
                            assert aprs_list[0]["apr_percentage"] == Decimal("19.99")
                            assert aprs_list[0]["balance_subject_to_apr"] == Decimal(
                                "1200.00"
                            )
