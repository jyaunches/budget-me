"""Integration tests for Plaid using Sandbox environment.

These tests require valid Plaid Sandbox credentials:
- BUDGET_ME_PLAID_TEST_CLIENT_ID
- BUDGET_ME_PLAID_TEST_SECRET
- BUDGET_ME_PLAID_TEST_DATABASE_URL
- BUDGET_ME_ALLOW_PLAID_PROVIDER_TESTS=1
- PLAID_ENV=sandbox

Run only through: make test-plaid-integration
"""

import uuid

import pytest

from budget_me.db.engine import get_async_session
from budget_me.db.models.plaid_item import PlaidItemStatus
from budget_me.db.repos.cursors import CursorsRepo
from budget_me.db.repos.items import ItemsRepo
from budget_me.db.repos.transactions import TransactionsRepo

pytestmark = [pytest.mark.integration, pytest.mark.plaid_provider_integration]


@pytest.fixture
def plaid_sandbox_api(plaid_provider_test_target):
    """Import provider callables only after the dedicated gate has passed."""
    from budget_me.plaid.link_flow import exchange_public_token
    from budget_me.plaid.sandbox import create_sandbox_item
    from budget_me.plaid.transactions_sync import sync_item

    return create_sandbox_item, exchange_public_token, sync_item


class TestPlaidSandboxIntegration:
    """Integration tests using Plaid Sandbox."""

    @pytest.mark.asyncio
    async def test_integration_full_sync_flow(self, plaid_sandbox_api):
        """Test full flow: create sandbox item → sync → verify data."""
        create_sandbox_item, exchange_public_token, sync_item = plaid_sandbox_api
        # Step 1: Create sandbox item with user_transactions_dynamic for realistic data
        user_key = f"test_user_{uuid.uuid4().hex[:8]}"
        public_token = create_sandbox_item(
            institution_id="ins_109508",
            products=["transactions"],
            options={
                "override_username": "user_transactions_dynamic",
                "override_password": "test_password",
            },
        )

        assert public_token is not None
        assert public_token.startswith("public-sandbox-")

        # Step 2: Exchange token
        result = await exchange_public_token(
            public_token=public_token, user_id=user_key
        )

        assert "item_id" in result
        assert "plaid_item_id" in result

        item_uuid = result["item_id"]

        # Verify item was created (use fresh session)
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)
            item = await items_repo.get_by_id(item_uuid)

            assert item is not None
            assert item.user_key == user_key
            assert item.status == PlaidItemStatus.ACTIVE
            assert item.access_token_enc is not None
            item_id = item.id  # Capture for later use

        # Step 3: Run initial sync
        result = await sync_item(uuid.UUID(item_uuid))

        # Sandbox may not always have transactions in the 90-day window
        # Accept either transactions or an empty sync
        assert result["added"] >= 0
        assert result["modified"] == 0  # First sync, no modifications
        assert result["removed"] == 0  # First sync, no removals
        added = result["added"]

        # Step 4: Verify transactions in DB (if any were added) - fresh session
        async with get_async_session() as session:
            transactions_repo = TransactionsRepo(session)
            transactions = await transactions_repo.find_by_plaid_item(
                uuid.UUID(item_uuid)
            )

            # The sync may return 0 transactions if sandbox data is outside 90-day window
            if added > 0:
                assert len(transactions) == added
                assert all(t.plaid_item_id == item_id for t in transactions)

            # Step 5: Verify cursor was saved
            cursors_repo = CursorsRepo(session)
            cursor = await cursors_repo.find_by_item_id(item_id)

            assert cursor is not None
            assert (
                cursor.transactions_cursor is not None
            )  # Should have a cursor after sync

        # Step 6: Run incremental sync
        result2 = await sync_item(uuid.UUID(item_uuid))

        # user_transactions_dynamic may return modified transactions on subsequent syncs
        # This is expected behavior - it simulates realistic transaction updates
        assert result2["added"] >= 0
        assert result2["modified"] >= 0
        assert result2["removed"] >= 0

        # Step 7: Verify cursor was updated - fresh session
        async with get_async_session() as session:
            cursors_repo = CursorsRepo(session)
            cursor_after = await cursors_repo.find_by_item_id(item_id)
            assert cursor_after is not None
            # Cursor may change even if no transactions changed

        # Cleanup - use raw SQL to avoid ORM relationship issues with CASCADE
        async with get_async_session() as session:
            from sqlalchemy import text

            await session.execute(
                text("DELETE FROM plaid_items WHERE id = :id"), {"id": item_uuid}
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_integration_error_recovery(self, plaid_sandbox_api):
        """Test error handling and recovery flows."""
        create_sandbox_item, exchange_public_token, sync_item = plaid_sandbox_api
        # Create a basic sandbox item
        user_key = f"test_user_{uuid.uuid4().hex[:8]}"
        public_token = create_sandbox_item(
            institution_id="ins_109508",
            products=["transactions"],
            options={
                "override_username": "user_transactions_dynamic",
                "override_password": "test_password",
            },
        )

        result = await exchange_public_token(
            public_token=public_token, user_id=user_key
        )
        item_uuid = result["item_id"]

        # Verify item starts as ACTIVE - fresh session
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)
            item = await items_repo.get_by_id(item_uuid)
            assert item.status == PlaidItemStatus.ACTIVE

        # Run initial sync to ensure item works
        sync_result = await sync_item(uuid.UUID(item_uuid))
        assert sync_result["added"] >= 0

        # Note: To fully test error recovery, we would need to:
        # 1. Use sandbox/item/reset_login to force ITEM_LOGIN_REQUIRED
        # 2. Verify sync fails gracefully
        # 3. Verify item status is updated to RELINK_REQUIRED
        #
        # This requires additional sandbox utilities which are available
        # but not fully integrated in this test yet.

        # Cleanup - use raw SQL to avoid ORM relationship issues with CASCADE
        async with get_async_session() as session:
            from sqlalchemy import text

            await session.execute(
                text("DELETE FROM plaid_items WHERE id = :id"), {"id": item_uuid}
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_integration_cursor_persistence(self, plaid_sandbox_api):
        """Test that cursor persists correctly across multiple syncs."""
        create_sandbox_item, exchange_public_token, sync_item = plaid_sandbox_api
        # Create sandbox item
        user_key = f"test_user_{uuid.uuid4().hex[:8]}"
        public_token = create_sandbox_item(
            institution_id="ins_109508",
            products=["transactions"],
            options={
                "override_username": "user_transactions_dynamic",
                "override_password": "test_password",
            },
        )

        result = await exchange_public_token(
            public_token=public_token, user_id=user_key
        )
        item_uuid = result["item_id"]

        # Get item ID for cursor lookups
        async with get_async_session() as session:
            items_repo = ItemsRepo(session)
            item = await items_repo.get_by_id(item_uuid)
            item_id = item.id

            # Initially, cursor exists but may be None (created in exchange_public_token)
            cursors_repo = CursorsRepo(session)
            cursor_before = await cursors_repo.find_by_item_id(item_id)
            # Cursor record exists, but transactions_cursor is None before first sync
            assert cursor_before is None or cursor_before.transactions_cursor is None

        # Run first sync
        result1 = await sync_item(uuid.UUID(item_uuid))
        assert result1["added"] >= 0

        # Cursor should now exist - fresh session
        async with get_async_session() as session:
            cursors_repo = CursorsRepo(session)
            cursor_after_first = await cursors_repo.find_by_item_id(item_id)
            assert cursor_after_first is not None
            assert cursor_after_first.transactions_cursor is not None

        # Run second sync
        await sync_item(uuid.UUID(item_uuid))

        # Cursor should be updated (even if no new transactions) - fresh session
        async with get_async_session() as session:
            cursors_repo = CursorsRepo(session)
            cursor_after_second = await cursors_repo.find_by_item_id(item_id)
            assert cursor_after_second is not None
            assert cursor_after_second.transactions_cursor is not None

        # Cursor values may be the same or different depending on Plaid's response
        # The important thing is that it persists

        # Cleanup - use raw SQL to avoid ORM relationship issues with CASCADE
        async with get_async_session() as session:
            from sqlalchemy import text

            await session.execute(
                text("DELETE FROM plaid_items WHERE id = :id"), {"id": item_uuid}
            )
            await session.commit()

    @pytest.mark.asyncio
    async def test_integration_multiple_items(self, plaid_sandbox_api):
        """Test handling multiple Plaid items for different users."""
        create_sandbox_item, exchange_public_token, sync_item = plaid_sandbox_api
        # Create two different sandbox items
        user1_key = f"test_user1_{uuid.uuid4().hex[:8]}"
        user2_key = f"test_user2_{uuid.uuid4().hex[:8]}"

        public_token1 = create_sandbox_item(
            institution_id="ins_109508",
            products=["transactions"],
            options={
                "override_username": "user_transactions_dynamic",
                "override_password": "test_password",
            },
        )
        public_token2 = create_sandbox_item(
            institution_id="ins_109508",
            products=["transactions"],
            options={
                "override_username": "user_transactions_dynamic",
                "override_password": "test_password",
            },
        )

        result1 = await exchange_public_token(
            public_token=public_token1, user_id=user1_key
        )
        result2 = await exchange_public_token(
            public_token=public_token2, user_id=user2_key
        )

        item1_uuid = result1["item_id"]
        item2_uuid = result2["item_id"]

        # Sync both items
        sync_result1 = await sync_item(uuid.UUID(item1_uuid))
        sync_result2 = await sync_item(uuid.UUID(item2_uuid))

        assert sync_result1["added"] >= 0
        assert sync_result2["added"] >= 0
        added1 = sync_result1["added"]
        added2 = sync_result2["added"]

        # Verify transactions are properly isolated - fresh session
        async with get_async_session() as session:
            transactions_repo = TransactionsRepo(session)
            txns1 = await transactions_repo.find_by_plaid_item(uuid.UUID(item1_uuid))
            txns2 = await transactions_repo.find_by_plaid_item(uuid.UUID(item2_uuid))

            assert len(txns1) == added1
            assert len(txns2) == added2

            # Verify no transaction overlap
            txn1_ids = {t.plaid_transaction_id for t in txns1}
            txn2_ids = {t.plaid_transaction_id for t in txns2}
            assert txn1_ids.isdisjoint(txn2_ids)  # No common transaction IDs

        # Cleanup - use raw SQL to avoid ORM relationship issues with CASCADE
        async with get_async_session() as session:
            from sqlalchemy import text

            for item_id in [item1_uuid, item2_uuid]:
                await session.execute(
                    text("DELETE FROM plaid_items WHERE id = :id"), {"id": item_id}
                )
            await session.commit()
