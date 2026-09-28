"""Unit tests for snapshot actual payment fields."""

import uuid
from datetime import date
from decimal import Decimal
from unittest.mock import MagicMock, patch

from budget_me.db.models.monthly_snapshot import MonthlySnapshot, SnapshotStatus
from budget_me.db.models.snapshot_credit_card import SnapshotCreditCard
from budget_me.streamlit_app import db


class TestSnapshotActualPaymentFields:
    """Test actual payment fields in snapshot credit cards."""

    @patch("budget_me.streamlit_app.db.get_session")
    def test_get_snapshot_credit_cards_returns_actual_payment_fields(
        self, mock_get_session
    ):
        """Verify get_snapshot_credit_cards includes actual payment fields."""
        # Create mock session
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Create test data
        snapshot_id = uuid.uuid4()
        account_id = "test-account-123"

        # Mock snapshot query
        mock_snapshot = MonthlySnapshot(
            id=snapshot_id, year_month="2025-01", status=SnapshotStatus.OPEN
        )
        mock_session.execute.return_value.scalar_one_or_none.return_value = (
            mock_snapshot
        )

        # Mock credit card query with actual payment fields
        mock_card = SnapshotCreditCard(
            id=uuid.uuid4(),
            snapshot_id=snapshot_id,
            account_id=account_id,
            payment_strategy="pay_in_full",
            calculated_payment=Decimal("500.00"),
            actual_payment_amount=Decimal("500.00"),
            actual_payment_date=date(2025, 1, 15),
        )

        # Mock the credit cards query result
        mock_row = MagicMock()
        mock_row.SnapshotCreditCard = mock_card
        mock_row.name = "Test Card"
        mock_row.mask = "1234"

        # Setup the query execution to return our mock row
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Configure session.execute to return different results for different queries
        def execute_side_effect(stmt):
            # First call: snapshot query
            # Second call: credit cards query
            if mock_session.execute.call_count <= 1:
                result = MagicMock()
                result.scalar_one_or_none.return_value = mock_snapshot
                return result
            else:
                return mock_result

        mock_session.execute.side_effect = execute_side_effect

        # Call the function
        with patch("budget_me.streamlit_app.db.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_session
            cards = db.get_snapshot_credit_cards(mock_session, "2025-01", account_id)

        # Assert actual payment fields are included
        assert len(cards) == 1
        card = cards[0]
        assert "actual_payment_amount" in card
        assert "actual_payment_date" in card
        assert card["actual_payment_amount"] == 500.00
        assert card["actual_payment_date"] == date(2025, 1, 15)

    @patch("budget_me.streamlit_app.db.get_session")
    def test_get_or_create_snapshot_returns_last_synced_at(self, mock_get_session):
        """Verify get_or_create_snapshot includes last_synced_at field."""
        # Create mock session
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Create test snapshot with last_synced_at
        from datetime import datetime

        test_datetime = datetime(2025, 1, 15, 10, 30, 0)
        mock_snapshot = MonthlySnapshot(
            id=uuid.uuid4(),
            year_month="2025-01",
            status=SnapshotStatus.OPEN,
            income_total=Decimal("5000.00"),
            expense_total=Decimal("2000.00"),
            credit_card_total=Decimal("1000.00"),
            net=Decimal("3000.00"),
            last_synced_at=test_datetime,
        )

        # Mock the query to return existing snapshot
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = mock_snapshot
        mock_session.execute.return_value = mock_result

        # Call the function
        with patch("budget_me.streamlit_app.db.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_session
            snapshot = db.get_or_create_snapshot(
                mock_session, "2025-01", "test-account-123"
            )

        # Assert last_synced_at is included
        assert "last_synced_at" in snapshot
        assert snapshot["last_synced_at"] == test_datetime

    @patch("budget_me.streamlit_app.db.get_session")
    def test_snapshot_credit_card_actual_payment_fields_nullable(
        self, mock_get_session
    ):
        """Verify actual payment fields are nullable by default."""
        # Create mock session
        mock_session = MagicMock()
        mock_get_session.return_value.__enter__.return_value = mock_session

        # Create snapshot credit card without actual payment fields
        snapshot_id = uuid.uuid4()
        account_id = "test-account-123"

        mock_snapshot = MonthlySnapshot(
            id=snapshot_id, year_month="2025-01", status=SnapshotStatus.OPEN
        )

        # Create card without setting actual_payment fields
        mock_card = SnapshotCreditCard(
            id=uuid.uuid4(),
            snapshot_id=snapshot_id,
            account_id=account_id,
            payment_strategy="pay_in_full",
            calculated_payment=Decimal("500.00"),
            # actual_payment_amount and actual_payment_date NOT set
        )

        # Mock the credit cards query result
        mock_row = MagicMock()
        mock_row.SnapshotCreditCard = mock_card
        mock_row.name = "Test Card"
        mock_row.mask = "1234"

        mock_result = MagicMock()
        mock_result.fetchall.return_value = [mock_row]

        # Setup query mocking
        def execute_side_effect(stmt):
            if mock_session.execute.call_count <= 1:
                result = MagicMock()
                result.scalar_one_or_none.return_value = mock_snapshot
                return result
            else:
                return mock_result

        mock_session.execute.side_effect = execute_side_effect

        # Call the function
        with patch("budget_me.streamlit_app.db.get_session") as mock_ctx:
            mock_ctx.return_value.__enter__.return_value = mock_session
            cards = db.get_snapshot_credit_cards(mock_session, "2025-01", account_id)

        # Assert fields default to None
        assert len(cards) == 1
        card = cards[0]
        assert card["actual_payment_amount"] is None
        assert card["actual_payment_date"] is None
