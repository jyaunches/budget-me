"""Unit tests for Transaction model budget_category field."""

from budget_me.db.models.transaction import Transaction


def test_transaction_has_budget_category_field():
    """Verify budget_category field exists and is accessible on Transaction model."""
    # Create a Transaction instance with budget_category
    transaction = Transaction(
        plaid_transaction_id="test-txn-123",
        plaid_item_id="00000000-0000-0000-0000-000000000000",
        account_id="test-account-123",
        date="2025-01-01",
        amount=100.00,
        name="Test Transaction",
        budget_category="groceries",
    )

    # Verify field persists on the model
    assert hasattr(transaction, "budget_category")
    assert transaction.budget_category == "groceries"


def test_budget_category_is_nullable():
    """Verify budget_category field is nullable (existing transactions work without it)."""
    # Create a Transaction instance without budget_category
    transaction = Transaction(
        plaid_transaction_id="test-txn-456",
        plaid_item_id="00000000-0000-0000-0000-000000000000",
        account_id="test-account-456",
        date="2025-01-01",
        amount=50.00,
        name="Test Transaction Without Category",
    )

    # Verify transaction is created successfully
    assert hasattr(transaction, "budget_category")
    assert transaction.budget_category is None


def test_transaction_has_project_tag_field():
    """Verify project_tag field exists, is settable, and defaults to None."""
    tagged = Transaction(
        plaid_transaction_id="test-txn-789",
        plaid_item_id="00000000-0000-0000-0000-000000000000",
        account_id="test-account-789",
        date="2027-01-01",
        amount=100.00,
        name="Test Project Transaction",
        project_tag="example_project_2027",
    )
    assert tagged.project_tag == "example_project_2027"

    untagged = Transaction(
        plaid_transaction_id="test-txn-790",
        plaid_item_id="00000000-0000-0000-0000-000000000000",
        account_id="test-account-790",
        date="2026-03-12",
        amount=10.00,
        name="Untagged Transaction",
    )
    assert hasattr(untagged, "project_tag")
    assert untagged.project_tag is None
