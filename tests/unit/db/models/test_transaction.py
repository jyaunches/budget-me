"""Unit tests for Transaction model reimbursable fields."""

from datetime import datetime
from uuid import uuid4

import pytest

from budget_me.db.models.transaction import Transaction


class TestTransactionReimbursableFields:
    """Test suite for reimbursable tracking fields."""

    def test_transaction_reimbursable_fields_nullable(self):
        """Reimbursable fields should be nullable for backward compatibility."""
        transaction = Transaction(
            id=uuid4(),
            name="Test Merchant",
            amount=-100.00,
            date=datetime.now().date(),
            account_id=uuid4(),
            plaid_transaction_id="test_txn_123",
            reimbursable=None,
            reimbursement_status=None,
            reimbursement_note=None,
        )

        # Should be able to create with None values
        assert transaction.reimbursable is None
        assert transaction.reimbursement_status is None
        assert transaction.reimbursement_note is None

    def test_transaction_reimbursable_true(self):
        """Reimbursable field should accept True value."""
        transaction = Transaction(
            id=uuid4(),
            name="Test Merchant",
            amount=-100.00,
            date=datetime.now().date(),
            account_id=uuid4(),
            plaid_transaction_id="test_txn_123",
            reimbursable=True,
        )

        assert transaction.reimbursable is True
        assert isinstance(transaction.reimbursable, bool)

    def test_transaction_reimbursable_false(self):
        """Reimbursable field should accept False value and distinguish from None."""
        transaction = Transaction(
            id=uuid4(),
            name="Test Merchant",
            amount=-100.00,
            date=datetime.now().date(),
            account_id=uuid4(),
            plaid_transaction_id="test_txn_123",
            reimbursable=False,
        )

        assert transaction.reimbursable is False
        assert transaction.reimbursable is not None
        assert isinstance(transaction.reimbursable, bool)

    @pytest.mark.parametrize("status", ["pending", "received"])
    def test_transaction_reimbursement_status_values(self, status):
        """Reimbursement status should accept expected string values."""
        transaction = Transaction(
            id=uuid4(),
            name="Test Merchant",
            amount=-100.00,
            date=datetime.now().date(),
            account_id=uuid4(),
            plaid_transaction_id="test_txn_123",
            reimbursement_status=status,
        )

        assert transaction.reimbursement_status == status
        assert isinstance(transaction.reimbursement_status, str)

    def test_transaction_reimbursement_note_stores_text(self):
        """Reimbursement note should store descriptive text."""
        note_text = "NY Trip Dec 2024"
        transaction = Transaction(
            id=uuid4(),
            name="Test Merchant",
            amount=-100.00,
            date=datetime.now().date(),
            account_id=uuid4(),
            plaid_transaction_id="test_txn_123",
            reimbursement_note=note_text,
        )

        assert transaction.reimbursement_note == note_text
        assert isinstance(transaction.reimbursement_note, str)

    def test_transaction_model_has_reimbursable_index(self):
        """Transaction model should define index on reimbursable field."""
        # Check __table_args__ for index definition
        table_args = Transaction.__table_args__

        # Find index by name
        index_names = [idx.name for idx in table_args if hasattr(idx, "name")]

        assert "ix_transactions_reimbursable" in index_names
