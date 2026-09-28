"""Tests for add_liabilities_to_item functionality."""

import uuid

import pytest


class TestAddLiabilitiesToItem:
    """Tests for adding liabilities product to items."""

    @pytest.mark.asyncio
    async def test_add_liabilities_to_item_updates_products(self, mocker):
        """add_liabilities_to_item updates item products to include liabilities."""
        from budget_me.plaid.link_flow import add_liabilities_to_item

        # Mock the repo and session
        mock_session = mocker.AsyncMock()
        mock_repo = mocker.MagicMock()

        # Mock get_async_session to return our mock session
        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session),
                __aexit__=mocker.AsyncMock(),
            ),
        )

        # Mock ItemsRepo to return our mock repo
        mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=mock_repo)

        # Mock add_product method
        test_item_id = uuid.uuid4()
        mock_repo.add_product = mocker.AsyncMock()

        await add_liabilities_to_item(test_item_id)

        # Verify add_product was called with item_id and "liabilities"
        mock_repo.add_product.assert_called_once_with(test_item_id, "liabilities")

    @pytest.mark.asyncio
    async def test_add_liabilities_to_item_is_idempotent(self, mocker):
        """add_liabilities_to_item is safe to call multiple times."""
        from budget_me.plaid.link_flow import add_liabilities_to_item

        # Mock the repo and session
        mock_session = mocker.AsyncMock()
        mock_repo = mocker.MagicMock()

        # Mock get_async_session
        mocker.patch(
            "budget_me.plaid.link_flow.get_async_session",
            return_value=mocker.AsyncMock(
                __aenter__=mocker.AsyncMock(return_value=mock_session),
                __aexit__=mocker.AsyncMock(),
            ),
        )

        # Mock ItemsRepo
        mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=mock_repo)

        # Mock add_product to simulate idempotency
        # (The actual idempotency is in ItemsRepo.add_product)
        test_item_id = uuid.uuid4()
        mock_repo.add_product = mocker.AsyncMock()

        # Call twice
        await add_liabilities_to_item(test_item_id)
        await add_liabilities_to_item(test_item_id)

        # Both calls should succeed (repo handles idempotency)
        assert mock_repo.add_product.call_count == 2
