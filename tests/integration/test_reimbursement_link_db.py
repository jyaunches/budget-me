"""Integration tests for ReimbursementLink database operations."""

import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError

from budget_me.db.models.reimbursement_link import ReimbursementLink
from budget_me.db.models.transaction import Transaction

pytestmark = pytest.mark.asyncio


async def create_test_plaid_item(conn):
    """Helper to create a test plaid item."""
    result = await conn.execute(
        text("""
            INSERT INTO plaid_items (id, user_key, item_id, access_token_enc, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                'test-user',
                :item_id,
                'test-access-token-encrypted',
                NOW(),
                NOW()
            )
            RETURNING id
        """),
        {"item_id": f"test-item-{uuid.uuid4()}"},
    )
    return result.fetchone()[0]


async def create_expense_transaction(session, conn):
    """Create an expense transaction for testing."""
    plaid_item_id = await create_test_plaid_item(conn)

    tx = Transaction(
        plaid_transaction_id=f"expense-{uuid.uuid4()}",
        plaid_item_id=plaid_item_id,
        account_id=f"acc-{uuid.uuid4()}",
        date=date(2025, 1, 1),
        amount=Decimal("100.00"),
        name="Test Expense",
        reimbursable=True,
        reimbursement_status="pending",
        reimbursement_note="work",
    )
    session.add(tx)
    await session.flush()
    return tx


async def create_deposit_transaction(session, conn):
    """Create a deposit transaction for testing."""
    plaid_item_id = await create_test_plaid_item(conn)

    tx = Transaction(
        plaid_transaction_id=f"deposit-{uuid.uuid4()}",
        plaid_item_id=plaid_item_id,
        account_id=f"acc-{uuid.uuid4()}",
        date=date(2025, 1, 15),
        amount=Decimal("-200.00"),  # Negative = deposit
        name="Expense Reimbursement",
        budget_category="reimbursement",
    )
    session.add(tx)
    await session.flush()
    return tx


async def test_reimbursement_link_create(db_session):
    """Test creating a reimbursement link with valid data."""
    session, conn = db_session
    expense_tx = await create_expense_transaction(session, conn)
    deposit_tx = await create_deposit_transaction(session, conn)

    link = ReimbursementLink(
        expense_transaction_id=expense_tx.id,
        deposit_transaction_id=deposit_tx.id,
        amount=Decimal("100.00"),
    )
    session.add(link)
    await session.flush()

    # Verify saved
    assert link.id is not None
    assert link.linked_at is not None
    assert link.expense_transaction_id == expense_tx.id
    assert link.deposit_transaction_id == deposit_tx.id
    assert link.amount == Decimal("100.00")


async def test_reimbursement_link_requires_amount(db_session):
    """Test that amount is required."""
    session, conn = db_session
    expense_tx = await create_expense_transaction(session, conn)
    deposit_tx = await create_deposit_transaction(session, conn)

    link = ReimbursementLink(
        expense_transaction_id=expense_tx.id,
        deposit_transaction_id=deposit_tx.id,
        amount=None,  # Missing required field
    )
    session.add(link)

    with pytest.raises(IntegrityError):
        await session.flush()


async def test_reimbursement_link_unique_constraint(db_session):
    """Test that duplicate expense-deposit pairs are prevented."""
    session, conn = db_session
    expense_tx = await create_expense_transaction(session, conn)
    deposit_tx = await create_deposit_transaction(session, conn)

    # Create first link
    link1 = ReimbursementLink(
        expense_transaction_id=expense_tx.id,
        deposit_transaction_id=deposit_tx.id,
        amount=Decimal("50.00"),
    )
    session.add(link1)
    await session.flush()

    # Try to create duplicate via raw SQL to bypass ORM
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("""
                INSERT INTO reimbursement_links (id, expense_transaction_id, deposit_transaction_id, amount, linked_at)
                VALUES (gen_random_uuid(), :expense_id, :deposit_id, :amount, NOW())
            """),
            {
                "expense_id": expense_tx.id,
                "deposit_id": deposit_tx.id,
                "amount": Decimal("25.00"),
            },
        )


async def test_reimbursement_link_foreign_key_expense(db_session):
    """Test that expense_transaction_id FK is enforced."""
    session, conn = db_session
    deposit_tx = await create_deposit_transaction(session, conn)

    # Try to insert with non-existent expense via raw SQL
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("""
                INSERT INTO reimbursement_links (id, expense_transaction_id, deposit_transaction_id, amount, linked_at)
                VALUES (gen_random_uuid(), :expense_id, :deposit_id, :amount, NOW())
            """),
            {
                "expense_id": uuid.uuid4(),  # Non-existent ID
                "deposit_id": deposit_tx.id,
                "amount": Decimal("100.00"),
            },
        )


async def test_reimbursement_link_foreign_key_deposit(db_session):
    """Test that deposit_transaction_id FK is enforced."""
    session, conn = db_session
    expense_tx = await create_expense_transaction(session, conn)

    # Try to insert with non-existent deposit via raw SQL
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("""
                INSERT INTO reimbursement_links (id, expense_transaction_id, deposit_transaction_id, amount, linked_at)
                VALUES (gen_random_uuid(), :expense_id, :deposit_id, :amount, NOW())
            """),
            {
                "expense_id": expense_tx.id,
                "deposit_id": uuid.uuid4(),  # Non-existent ID
                "amount": Decimal("100.00"),
            },
        )


async def test_reimbursement_link_query(db_session):
    """Test querying links by expense transaction."""
    session, conn = db_session
    expense_tx = await create_expense_transaction(session, conn)
    deposit_tx = await create_deposit_transaction(session, conn)

    link = ReimbursementLink(
        expense_transaction_id=expense_tx.id,
        deposit_transaction_id=deposit_tx.id,
        amount=Decimal("100.00"),
    )
    session.add(link)
    await session.flush()

    # Query by expense ID
    result = await session.execute(
        select(ReimbursementLink).where(
            ReimbursementLink.expense_transaction_id == expense_tx.id
        )
    )
    queried_link = result.scalar_one()

    assert queried_link.id == link.id
    assert queried_link.amount == Decimal("100.00")
