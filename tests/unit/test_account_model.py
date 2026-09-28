"""Tests for Account model."""

from decimal import Decimal
from uuid import uuid4

from budget_me.db.models import Account, PlaidItem


class TestAccount:
    """Tests for Account model."""

    def test_account_model_creation(self):
        """Account model can be instantiated with all required fields."""
        account = Account(
            plaid_item_id=uuid4(),
            account_id="test_account_id",
            name="Checking",
            type="depository",
            subtype="checking",
            mask="0000",
            balance_available=Decimal("1000.00"),
            balance_current=Decimal("1050.00"),
        )
        assert account.account_id == "test_account_id"
        assert account.name == "Checking"
        assert account.balance_current == Decimal("1050.00")

    def test_account_has_required_columns(self):
        """Account model has all required columns."""
        columns = Account.__table__.columns.keys()

        assert "id" in columns
        assert "plaid_item_id" in columns
        assert "account_id" in columns
        assert "name" in columns
        assert "display_name" in columns
        assert "type" in columns
        assert "subtype" in columns
        assert "mask" in columns
        assert "balance_available" in columns
        assert "balance_current" in columns
        assert "created_at" in columns
        assert "updated_at" in columns
        assert "is_excluded" in columns

    def test_account_display_name_defaults_to_none(self):
        """Account display_name defaults to None."""
        account = Account(
            plaid_item_id=uuid4(),
            account_id="test_account_id",
            name="Checking",
            type="depository",
        )
        assert account.display_name is None

    def test_account_accepts_display_name(self):
        """Account model accepts display_name field."""
        account = Account(
            plaid_item_id=uuid4(),
            account_id="test_account_id",
            name="CREDIT CARD",
            display_name="Example Card A",
            type="credit",
        )
        assert account.display_name == "Example Card A"
        assert account.name == "CREDIT CARD"

    def test_account_has_account_id_index(self):
        """Account has index on account_id for efficient joins."""
        index_names = [idx.name for idx in Account.__table__.indexes]
        assert "ix_accounts_account_id" in index_names

    def test_account_id_has_one_non_unique_index(self):
        """Keep the explicit lookup index distinct from the unique constraint."""
        indexes = [
            index
            for index in Account.__table__.indexes
            if index.name == "ix_accounts_account_id"
        ]
        assert [
            (index.unique, [column.name for column in index.columns])
            for index in indexes
        ] == [(False, ["account_id"])]

    def test_account_account_id_is_unique(self):
        """account_id has unique constraint."""
        col = Account.__table__.c.account_id
        assert col.unique is True

    def test_account_model_has_is_excluded_field(self):
        """Account model has is_excluded field with default False."""
        is_excluded_column = Account.__table__.c.is_excluded
        assert is_excluded_column is not None
        assert is_excluded_column.default is not None
        assert is_excluded_column.default.arg is False

    def test_account_is_excluded_can_be_set_to_true(self):
        """Account model accepts is_excluded=True."""
        account = Account(
            plaid_item_id=uuid4(),
            account_id="test_account_id",
            name="Checking",
            type="depository",
            is_excluded=True,
        )
        assert account.is_excluded is True


class TestAccountRelationships:
    """Tests for Account model relationships."""

    def test_plaid_item_has_accounts_relationship(self):
        """PlaidItem has accounts relationship."""
        assert hasattr(PlaidItem, "accounts")

    def test_account_has_paying_account_id_field(self):
        """Account model has paying_account_id field for self-referential FK."""
        account = Account(
            plaid_item_id=uuid4(),
            account_id="credit-card-123",
            name="Example Card B",
            type="credit",
            paying_account_id="checking-acc-456",
        )
        assert hasattr(account, "paying_account_id")
        assert account.paying_account_id == "checking-acc-456"

    def test_account_has_paying_account_relationship(self):
        """Account model has paying_account relationship."""
        assert hasattr(Account, "paying_account")

    def test_account_paying_account_id_in_columns(self):
        """Account table has paying_account_id column."""
        columns = Account.__table__.columns.keys()
        assert "paying_account_id" in columns
