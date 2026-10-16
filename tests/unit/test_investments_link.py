"""Tests for investment-specific Plaid Link tokens."""

from pathlib import Path

from plaid.model.products import Products


def test_new_investment_link_initializes_investments(mocker):
    from budget_me.plaid.link_flow import create_investment_link_token

    response = mocker.MagicMock(link_token="link-investments")
    client = mocker.MagicMock()
    client.link_token_create.return_value = response
    mocker.patch("budget_me.plaid.link_flow.get_plaid_client", return_value=client)

    assert create_investment_link_token("owner") == "link-investments"
    request = client.link_token_create.call_args.args[0]
    assert request.products == [Products("investments")]


def test_existing_item_upgrade_requests_investments_consent(mocker):
    from budget_me.plaid.link_flow import create_investments_upgrade_token

    response = mocker.MagicMock(link_token="link-upgrade")
    client = mocker.MagicMock()
    client.link_token_create.return_value = response
    mocker.patch("budget_me.plaid.link_flow.get_plaid_client", return_value=client)

    token = create_investments_upgrade_token(
        access_token="access-existing",
        user_id="owner",
    )

    assert token == "link-upgrade"
    request = client.link_token_create.call_args.args[0]
    assert request.access_token == "access-existing"
    assert request.additional_consented_products == [Products("investments")]


def test_link_page_exposes_new_and_existing_investment_flows():
    source = Path("src/budget_me/streamlit_app/pages/link_account.py").read_text()

    assert "Connect New Investment Account" in source
    assert "Enable Investments for" in source
    assert "Verify Investments" in source
