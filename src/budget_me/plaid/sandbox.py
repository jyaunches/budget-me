"""Plaid Sandbox utilities for automated testing.

This module provides helper functions for testing with Plaid's Sandbox environment,
enabling automated integration tests without manual Link flow intervention.
"""

from typing import Any

from loguru import logger
from plaid.model.products import Products
from plaid.model.sandbox_item_fire_webhook_request import (
    SandboxItemFireWebhookRequest,
)
from plaid.model.sandbox_item_reset_login_request import SandboxItemResetLoginRequest
from plaid.model.sandbox_public_token_create_request import (
    SandboxPublicTokenCreateRequest,
)
from plaid.model.sandbox_public_token_create_request_options import (
    SandboxPublicTokenCreateRequestOptions,
)
from plaid.model.webhook_type import WebhookType

from budget_me.plaid.client import get_plaid_client
from budget_me.plaid.errors import PlaidError, map_plaid_error


def create_sandbox_item(
    institution_id: str,
    products: list[str],
    options: dict[str, Any] | None = None,
) -> str:
    """
    Create a sandbox item using Plaid's sandbox public token creation endpoint.

    This bypasses the Link UI for automated testing. The item will have
    synthetic data for the specified products.

    Args:
        institution_id: Plaid institution ID (e.g., "ins_109508" for First Platypus Bank)
        products: List of products to enable (e.g., ["transactions"])
        options: Optional parameters like override_username, override_password

    Returns:
        str: A public token that can be exchanged for an access token

    Raises:
        PlaidError: If sandbox item creation fails

    Example:
        >>> public_token = create_sandbox_item(
        ...     "ins_109508",
        ...     ["transactions"],
        ...     {"override_username": "user_good", "override_password": "pass_good"}
        ... )
        >>> # Exchange public_token for access_token...
    """
    client = get_plaid_client()

    try:
        # Convert product strings to Products enum
        product_enums = [Products(p) for p in products]

        # Build request
        request_kwargs = {
            "institution_id": institution_id,
            "initial_products": product_enums,
        }

        # Add options if provided
        if options:
            options_obj = SandboxPublicTokenCreateRequestOptions(
                override_username=options.get("override_username"),
                override_password=options.get("override_password"),
            )
            request_kwargs["options"] = options_obj

        request = SandboxPublicTokenCreateRequest(**request_kwargs)

        # Call Plaid API
        response = client.sandbox_public_token_create(request)

        logger.info(
            "Created sandbox item",
            institution_id=institution_id,
            products=products,
        )

        return response.public_token

    except Exception as e:
        if hasattr(e, "status"):
            # Plaid ApiException
            plaid_error = map_plaid_error(e)
            logger.error(
                "Failed to create sandbox item",
                institution_id=institution_id,
                error=str(plaid_error),
            )
            raise plaid_error from e
        else:
            # Other exception
            logger.error(
                "Unexpected error creating sandbox item",
                institution_id=institution_id,
                error=str(e),
            )
            raise PlaidError(
                message=f"Failed to create sandbox item: {e}",
            ) from e


def fire_sandbox_webhook(access_token: str, webhook_code: str) -> bool:
    """
    Fire a webhook for a sandbox item.

    This simulates Plaid sending a webhook to your application. Useful for
    testing webhook handling logic.

    Args:
        access_token: The item's access token
        webhook_code: The webhook code to fire (e.g., "DEFAULT_UPDATE")

    Returns:
        bool: True if webhook was fired successfully

    Raises:
        PlaidError: If webhook firing fails

    Example:
        >>> fire_sandbox_webhook(access_token, "DEFAULT_UPDATE")
        True
    """
    client = get_plaid_client()

    try:
        request = SandboxItemFireWebhookRequest(
            access_token=access_token,
            webhook_code=webhook_code,
            webhook_type=WebhookType("TRANSACTIONS"),
        )

        response = client.sandbox_item_fire_webhook(request)

        logger.info(
            "Fired sandbox webhook",
            webhook_code=webhook_code,
            webhook_fired=response.webhook_fired,
        )

        return response.webhook_fired

    except Exception as e:
        if hasattr(e, "status"):
            # Plaid ApiException
            plaid_error = map_plaid_error(e)
            logger.error(
                "Failed to fire sandbox webhook",
                webhook_code=webhook_code,
                error=str(plaid_error),
            )
            raise plaid_error from e
        else:
            # Other exception
            logger.error(
                "Unexpected error firing sandbox webhook",
                webhook_code=webhook_code,
                error=str(e),
            )
            raise PlaidError(
                message=f"Failed to fire sandbox webhook: {e}",
            ) from e


def reset_sandbox_login(access_token: str) -> bool:
    """
    Reset login for a sandbox item, forcing it into ITEM_LOGIN_REQUIRED state.

    This simulates the user's credentials expiring or being changed at the
    institution, useful for testing relink flows.

    Args:
        access_token: The item's access token

    Returns:
        bool: True if login was reset successfully

    Raises:
        PlaidError: If login reset fails

    Example:
        >>> reset_sandbox_login(access_token)
        True
        >>> # Next sync will fail with ITEM_LOGIN_REQUIRED
    """
    client = get_plaid_client()

    try:
        request = SandboxItemResetLoginRequest(access_token=access_token)

        response = client.sandbox_item_reset_login(request)

        logger.info(
            "Reset sandbox item login",
            reset_login=response.reset_login,
        )

        return response.reset_login

    except Exception as e:
        if hasattr(e, "status"):
            # Plaid ApiException
            plaid_error = map_plaid_error(e)
            logger.error(
                "Failed to reset sandbox login",
                error=str(plaid_error),
            )
            raise plaid_error from e
        else:
            # Other exception
            logger.error(
                "Unexpected error resetting sandbox login",
                error=str(e),
            )
            raise PlaidError(
                message=f"Failed to reset sandbox login: {e}",
            ) from e
