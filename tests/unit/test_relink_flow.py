"""Tests for repairing an existing Plaid Item through Link update mode."""

import uuid

import pytest
from plaid.api_client import ApiException

from budget_me.db.models.plaid_item import PlaidItemStatus


def _mock_session_context(mocker, session):
    return mocker.AsyncMock(
        __aenter__=mocker.AsyncMock(return_value=session),
        __aexit__=mocker.AsyncMock(return_value=False),
    )


class TestCreateUpdateLinkToken:
    def test_uses_existing_access_token_without_product_initialization(self, mocker):
        from budget_me.plaid.link_flow import create_update_link_token

        response = mocker.MagicMock(link_token="link-update-test")
        client = mocker.MagicMock()
        client.link_token_create.return_value = response
        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client",
            return_value=client,
        )

        token = create_update_link_token(
            access_token="access-test",
            user_id="synthetic-user",
            redirect_uri="https://example.test/plaid/callback",
        )

        assert token == "link-update-test"
        request = client.link_token_create.call_args.args[0]
        assert request.access_token == "access-test"
        assert request.user.client_user_id == "synthetic-user"
        assert request.redirect_uri == "https://example.test/plaid/callback"
        assert getattr(request, "products", None) is None
        assert getattr(request, "transactions", None) is None
        assert getattr(request, "additional_consented_products", None) is None

    def test_wraps_provider_errors(self, mocker):
        from budget_me.plaid.errors import PlaidError
        from budget_me.plaid.link_flow import create_update_link_token

        client = mocker.MagicMock()
        client.link_token_create.side_effect = ApiException(
            status=400,
            reason="synthetic failure",
        )
        mocker.patch(
            "budget_me.plaid.link_flow.get_plaid_client",
            return_value=client,
        )

        with pytest.raises(PlaidError, match="update-mode"):
            create_update_link_token(
                access_token="access-test",
                user_id="synthetic-user",
            )


@pytest.mark.asyncio
async def test_list_plaid_items_excludes_access_tokens_and_sorts(mocker):
    from budget_me.plaid.link_flow import list_plaid_items_for_link

    session = mocker.AsyncMock()
    repo = mocker.AsyncMock()
    repo.get_all.return_value = [
        mocker.MagicMock(
            id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
            institution_name="Zulu Bank",
            institution_id="ins_zulu",
            status=PlaidItemStatus.ACTIVE,
            last_error_code=None,
            access_token_enc="must-not-be-returned",
        ),
        mocker.MagicMock(
            id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            institution_name="Example Bank",
            institution_id="ins_example",
            status=PlaidItemStatus.RELINK_REQUIRED,
            last_error_code="ITEM_LOGIN_REQUIRED",
            access_token_enc="must-not-be-returned",
        ),
    ]
    mocker.patch(
        "budget_me.plaid.link_flow.get_async_session",
        return_value=_mock_session_context(mocker, session),
    )
    mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=repo)

    result = await list_plaid_items_for_link()

    assert [item["institution_name"] for item in result] == [
        "Example Bank",
        "Zulu Bank",
    ]
    assert result[0]["status"] == "relink_required"
    assert all("access_token" not in item for item in result)


@pytest.mark.asyncio
async def test_create_item_relink_token_decrypts_server_side(mocker):
    from budget_me.plaid.link_flow import create_item_relink_token

    item_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    session = mocker.AsyncMock()
    repo = mocker.AsyncMock()
    repo.get_by_id.return_value = mocker.MagicMock(
        id=item_id,
        access_token_enc="encrypted-test-token",
    )
    encryptor = mocker.MagicMock()
    encryptor.decrypt.return_value = "access-test"
    create_update = mocker.patch(
        "budget_me.plaid.link_flow.create_update_link_token",
        return_value="link-update-test",
    )
    mocker.patch(
        "budget_me.plaid.link_flow.get_async_session",
        return_value=_mock_session_context(mocker, session),
    )
    mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=repo)
    mocker.patch(
        "budget_me.plaid.link_flow.TokenEncryption",
        return_value=encryptor,
    )

    result = await create_item_relink_token(
        plaid_item_id=item_id,
        user_id="synthetic-user",
        redirect_uri=None,
    )

    assert result == "link-update-test"
    encryptor.decrypt.assert_called_once_with("encrypted-test-token")
    create_update.assert_called_once_with(
        access_token="access-test",
        user_id="synthetic-user",
        redirect_uri=None,
    )


@pytest.mark.asyncio
async def test_verify_item_relink_checks_plaid_before_reactivating(mocker):
    from budget_me.plaid.link_flow import verify_item_relink

    item_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    item = mocker.MagicMock(
        id=item_id,
        institution_name="Example Bank",
        institution_id="ins_example",
        access_token_enc="encrypted-test-token",
    )
    session = mocker.AsyncMock()
    repo = mocker.AsyncMock()
    repo.get_by_id.return_value = item
    client = mocker.MagicMock()
    encryptor = mocker.MagicMock()
    encryptor.decrypt.return_value = "access-test"
    refresh_accounts = mocker.patch(
        "budget_me.plaid.link_flow._fetch_and_store_accounts",
        new=mocker.AsyncMock(),
    )
    mocker.patch(
        "budget_me.plaid.link_flow.get_async_session",
        return_value=_mock_session_context(mocker, session),
    )
    mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=repo)
    mocker.patch(
        "budget_me.plaid.link_flow.TokenEncryption",
        return_value=encryptor,
    )
    mocker.patch(
        "budget_me.plaid.link_flow.get_plaid_client",
        return_value=client,
    )

    result = await verify_item_relink(item_id)

    client.item_get.assert_called_once()
    refresh_accounts.assert_awaited_once_with("access-test", item_id, session)
    repo.update_status.assert_awaited_once_with(
        item_id,
        PlaidItemStatus.ACTIVE,
    )
    assert result == {
        "id": str(item_id),
        "institution_name": "Example Bank",
        "status": "active",
    }


@pytest.mark.asyncio
async def test_verify_item_relink_does_not_activate_failed_provider_check(mocker):
    from budget_me.plaid.errors import PlaidError
    from budget_me.plaid.link_flow import verify_item_relink

    item_id = uuid.UUID("00000000-0000-0000-0000-000000000001")
    session = mocker.AsyncMock()
    repo = mocker.AsyncMock()
    repo.get_by_id.return_value = mocker.MagicMock(
        id=item_id,
        institution_name="Example Bank",
        institution_id="ins_example",
        access_token_enc="encrypted-test-token",
    )
    client = mocker.MagicMock()
    client.item_get.side_effect = ApiException(
        status=400,
        reason="ITEM_LOGIN_REQUIRED",
    )
    encryptor = mocker.MagicMock()
    encryptor.decrypt.return_value = "access-test"
    mocker.patch(
        "budget_me.plaid.link_flow.get_async_session",
        return_value=_mock_session_context(mocker, session),
    )
    mocker.patch("budget_me.plaid.link_flow.ItemsRepo", return_value=repo)
    mocker.patch(
        "budget_me.plaid.link_flow.TokenEncryption",
        return_value=encryptor,
    )
    mocker.patch(
        "budget_me.plaid.link_flow.get_plaid_client",
        return_value=client,
    )

    with pytest.raises(PlaidError, match="not confirmed"):
        await verify_item_relink(item_id)

    repo.update_status.assert_not_awaited()
