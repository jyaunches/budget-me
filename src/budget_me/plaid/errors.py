"""Plaid-specific error handling."""

import json

from plaid.api_client import ApiException


class PlaidError(Exception):
    """Base exception for Plaid-related errors."""

    def __init__(
        self, message: str, error_code: str | None = None, status: int | None = None
    ):
        """
        Initialize PlaidError.

        Args:
            message: Error message
            error_code: Plaid error code (e.g., ITEM_LOGIN_REQUIRED)
            status: HTTP status code
        """
        self.message = message
        self.error_code = error_code
        self.status = status
        super().__init__(message)


class PlaidAuthError(PlaidError):
    """Authentication/authorization error with Plaid API."""

    pass


class PlaidItemError(PlaidError):
    """Error related to a specific Plaid item."""

    pass


class PlaidRateLimitError(PlaidError):
    """Rate limiting error from Plaid API."""

    pass


class PlaidInstitutionError(PlaidError):
    """Error related to institution availability."""

    pass


# Error code to friendly message mapping
ERROR_MESSAGES = {
    "ITEM_LOGIN_REQUIRED": "Your bank account requires re-authentication. Please link your account again.",
    "INVALID_API_KEYS": "Invalid Plaid API credentials. Please check your configuration.",
    "INVALID_ACCESS_TOKEN": "The access token for this account is invalid. Please re-link your account.",
    "RATE_LIMIT": "Too many requests to Plaid. Please wait a moment and try again.",
    "INSTITUTION_NOT_RESPONDING": "The bank or financial institution is temporarily unavailable. Please try again later.",
    "INSTITUTION_DOWN": "The bank or financial institution is currently down for maintenance. Please try again later.",
    "TRANSACTIONS_SYNC_MUTATION_DURING_PAGINATION": "Transaction data changed during sync. Retrying...",
    "ITEM_NOT_FOUND": "The linked account was not found. Please re-link your account.",
    "PRODUCTS_NOT_READY": "Account data is still being prepared. Please try again in a few moments.",
    "INVALID_REQUEST": "Invalid request to Plaid API. Please contact support.",
}


def get_friendly_message(error_code: str) -> str:
    """
    Get a user-friendly error message for a Plaid error code.

    Args:
        error_code: The Plaid error code (e.g., ITEM_LOGIN_REQUIRED)

    Returns:
        str: A human-readable error message
    """
    return ERROR_MESSAGES.get(
        error_code,
        f"An error occurred with Plaid: {error_code}. Please try again or contact support.",
    )


def map_plaid_error(api_exception: ApiException) -> PlaidError:
    """
    Map a Plaid ApiException to the appropriate PlaidError subclass.

    This function extracts the error code from the ApiException body and
    creates a typed error with a friendly message.

    Args:
        api_exception: The ApiException from the Plaid SDK

    Returns:
        PlaidError: An appropriate PlaidError subclass instance
    """
    error_code = None
    error_message = api_exception.reason

    # Try to parse the error code from the response body
    if hasattr(api_exception, "body") and api_exception.body:
        try:
            body_data = json.loads(api_exception.body)
            error_code = body_data.get("error_code")
            if body_data.get("error_message"):
                error_message = body_data["error_message"]
        except (json.JSONDecodeError, AttributeError):
            pass

    # Get friendly message
    friendly_message = get_friendly_message(error_code) if error_code else error_message

    # Map to appropriate error class
    if error_code in ("INVALID_API_KEYS", "INVALID_SECRET", "UNAUTHORIZED"):
        return PlaidAuthError(
            message=friendly_message,
            error_code=error_code,
            status=api_exception.status,
        )
    elif error_code in (
        "ITEM_LOGIN_REQUIRED",
        "INVALID_ACCESS_TOKEN",
        "ITEM_NOT_FOUND",
    ):
        return PlaidItemError(
            message=friendly_message,
            error_code=error_code,
            status=api_exception.status,
        )
    elif error_code == "RATE_LIMIT":
        return PlaidRateLimitError(
            message=friendly_message,
            error_code=error_code,
            status=api_exception.status,
        )
    elif error_code in ("INSTITUTION_NOT_RESPONDING", "INSTITUTION_DOWN"):
        return PlaidInstitutionError(
            message=friendly_message,
            error_code=error_code,
            status=api_exception.status,
        )
    else:
        # Generic PlaidError for unknown error codes
        return PlaidError(
            message=friendly_message,
            error_code=error_code,
            status=api_exception.status,
        )
