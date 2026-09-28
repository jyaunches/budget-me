"""Integration tests for CategoryBudget database operations."""

from decimal import Decimal
from uuid import uuid4

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

from budget_me.db.models.category_budget import CategoryBudget

pytestmark = pytest.mark.asyncio


async def create_test_account(conn):
    """Helper to create a test account."""
    # Create plaid item
    plaid_item_result = await conn.execute(
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
        {"item_id": f"test-item-{uuid4()}"},
    )
    plaid_item_id = plaid_item_result.fetchone()[0]

    # Create account
    account_result = await conn.execute(
        text("""
            INSERT INTO accounts (id, plaid_item_id, account_id, name, type, created_at, updated_at)
            VALUES (
                gen_random_uuid(),
                :plaid_item_id,
                :account_id,
                'Test Account',
                'depository',
                NOW(),
                NOW()
            )
            RETURNING account_id
        """),
        {
            "plaid_item_id": plaid_item_id,
            "account_id": f"test-acc-{uuid4()}",
        },
    )
    return account_result.fetchone()[0]


async def test_category_budget_model_fields(db_session):
    """Verify CategoryBudget model stores all fields correctly."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    # When: creating a CategoryBudget with all fields
    budget = CategoryBudget(
        account_id=test_account_id,
        year_month="2025-01",
        category="groceries",
        budget_amount=Decimal("600.00"),
    )
    session.add(budget)
    await session.flush()

    # Then: all fields are stored correctly
    assert budget.id is not None
    assert budget.account_id == test_account_id
    assert budget.year_month == "2025-01"
    assert budget.category == "groceries"
    assert budget.budget_amount == Decimal("600.00")
    assert budget.created_at is not None
    assert budget.updated_at is not None


async def test_category_budget_unique_constraint(db_session):
    """Verify unique constraint prevents duplicate budgets."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    # Given: a checking account with one budget
    budget1 = CategoryBudget(
        account_id=test_account_id,
        year_month="2025-01",
        category="groceries",
        budget_amount=Decimal("600.00"),
    )
    session.add(budget1)
    await session.flush()

    # When: attempting to create duplicate budget via raw SQL (bypass ORM)
    with pytest.raises(IntegrityError):
        await conn.execute(
            text("""
                INSERT INTO category_budgets (id, account_id, year_month, category, budget_amount, created_at, updated_at)
                VALUES (gen_random_uuid(), :account_id, :year_month, :category, :budget_amount, NOW(), NOW())
            """),
            {
                "account_id": test_account_id,
                "year_month": "2025-01",
                "category": "groceries",
                "budget_amount": Decimal("700.00"),
            },
        )


async def test_category_budget_allows_different_accounts_same_month_category(
    db_session,
):
    """Verify different accounts can have budgets for same month/category."""
    session, conn = db_session
    account1_id = await create_test_account(conn)
    account2_id = await create_test_account(conn)

    # When: creating budgets with same month/category but different accounts
    budget1 = CategoryBudget(
        account_id=account1_id,
        year_month="2025-01",
        category="groceries",
        budget_amount=Decimal("600.00"),
    )
    budget2 = CategoryBudget(
        account_id=account2_id,
        year_month="2025-01",
        category="groceries",
        budget_amount=Decimal("800.00"),
    )
    session.add_all([budget1, budget2])
    await session.flush()

    # Then: both budgets are created successfully
    assert budget1.id != budget2.id
    assert budget1.budget_amount == Decimal("600.00")
    assert budget2.budget_amount == Decimal("800.00")


async def test_category_budget_timestamp_updates(db_session):
    """Verify updated_at changes when budget is modified."""
    session, conn = db_session
    test_account_id = await create_test_account(conn)

    # Given: an existing budget
    budget = CategoryBudget(
        account_id=test_account_id,
        year_month="2025-01",
        category="groceries",
        budget_amount=Decimal("600.00"),
    )
    session.add(budget)
    await session.flush()
    await session.refresh(budget)
    original_updated_at = budget.updated_at

    # When: updating the budget amount
    await session.execute(
        text("SELECT pg_sleep(0.01)")  # Small delay to ensure timestamp differs
    )
    budget.budget_amount = Decimal("700.00")
    await session.flush()
    await session.refresh(budget)

    # Then: updated_at is changed
    assert budget.updated_at > original_updated_at
    assert budget.created_at <= budget.updated_at
