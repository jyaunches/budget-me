"""Tests for Plaid error handling."""

from plaid.api_client import ApiException

from budget_me.plaid.errors import (
    PlaidAuthError,
    PlaidError,
    PlaidInstitutionError,
    PlaidItemError,
    PlaidRateLimitError,
    get_friendly_message,
    map_plaid_error,
)


class TestErrorMapping:
    """Tests for error code to friendly message mapping."""

    def test_error_maps_to_friendly_message_item_login_required(self):
        """ITEM_LOGIN_REQUIRED maps to user-friendly message."""
        message = get_friendly_message("ITEM_LOGIN_REQUIRED")
        assert "authentication" in message.lower() or "link" in message.lower()
        assert len(message) > 10  # Should be a meaningful message

    def test_error_maps_to_friendly_message_invalid_credentials(self):
        """INVALID_API_KEYS maps to user-friendly message."""
        message = get_friendly_message("INVALID_API_KEYS")
        assert "credential" in message.lower() or "api" in message.lower()

    def test_error_maps_to_friendly_message_rate_limit(self):
        """RATE_LIMIT maps to user-friendly message."""
        message = get_friendly_message("RATE_LIMIT")
        assert (
            "rate" in message.lower()
            or "limit" in message.lower()
            or "try again" in message.lower()
        )

    def test_error_maps_to_friendly_message_institution_down(self):
        """INSTITUTION_NOT_RESPONDING maps to user-friendly message."""
        message = get_friendly_message("INSTITUTION_NOT_RESPONDING")
        assert (
            "institution" in message.lower()
            or "bank" in message.lower()
            or "unavailable" in message.lower()
        )

    def test_error_maps_to_friendly_message_unknown_code(self):
        """Unknown error code returns generic but helpful message."""
        message = get_friendly_message("UNKNOWN_ERROR_CODE_12345")
        assert len(message) > 0
        assert "error" in message.lower() or "plaid" in message.lower()


class TestPlaidErrorClasses:
    """Tests for Plaid error exception classes."""

    def test_plaid_error_stores_code_and_status(self):
        """PlaidError stores error code and HTTP status."""
        error = PlaidError(message="Test error", error_code="TEST_ERROR", status=400)
        assert error.message == "Test error"
        assert error.error_code == "TEST_ERROR"
        assert error.status == 400

    def test_plaid_auth_error_is_plaid_error(self):
        """PlaidAuthError inherits from PlaidError."""
        error = PlaidAuthError(
            message="Auth failed", error_code="INVALID_API_KEYS", status=401
        )
        assert isinstance(error, PlaidError)
        assert error.error_code == "INVALID_API_KEYS"

    def test_plaid_item_error_is_plaid_error(self):
        """PlaidItemError inherits from PlaidError."""
        error = PlaidItemError(
            message="Item error", error_code="ITEM_LOGIN_REQUIRED", status=400
        )
        assert isinstance(error, PlaidError)
        assert error.error_code == "ITEM_LOGIN_REQUIRED"

    def test_plaid_rate_limit_error_is_plaid_error(self):
        """PlaidRateLimitError inherits from PlaidError."""
        error = PlaidRateLimitError(
            message="Rate limited", error_code="RATE_LIMIT", status=429
        )
        assert isinstance(error, PlaidError)
        assert error.status == 429

    def test_plaid_institution_error_is_plaid_error(self):
        """PlaidInstitutionError inherits from PlaidError."""
        error = PlaidInstitutionError(
            message="Institution down",
            error_code="INSTITUTION_NOT_RESPONDING",
            status=400,
        )
        assert isinstance(error, PlaidError)


class TestMapPlaidError:
    """Tests for mapping ApiException to typed PlaidError."""

    def test_map_plaid_error_invalid_credentials(self):
        """ApiException with INVALID_API_KEYS maps to PlaidAuthError."""
        api_ex = ApiException(status=401, reason="Invalid credentials")
        api_ex.body = (
            '{"error_code": "INVALID_API_KEYS", "error_message": "Invalid API keys"}'
        )

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidAuthError)
        assert error.error_code == "INVALID_API_KEYS"
        assert error.status == 401

    def test_map_plaid_error_item_login_required(self):
        """ApiException with ITEM_LOGIN_REQUIRED maps to PlaidItemError."""
        api_ex = ApiException(status=400, reason="Item login required")
        api_ex.body = '{"error_code": "ITEM_LOGIN_REQUIRED", "error_message": "Item requires reauth"}'

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidItemError)
        assert error.error_code == "ITEM_LOGIN_REQUIRED"

    def test_map_plaid_error_rate_limit(self):
        """ApiException with RATE_LIMIT maps to PlaidRateLimitError."""
        api_ex = ApiException(status=429, reason="Rate limit exceeded")
        api_ex.body = (
            '{"error_code": "RATE_LIMIT", "error_message": "Too many requests"}'
        )

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidRateLimitError)
        assert error.error_code == "RATE_LIMIT"
        assert error.status == 429

    def test_map_plaid_error_institution_down(self):
        """ApiException with INSTITUTION_NOT_RESPONDING maps to PlaidInstitutionError."""
        api_ex = ApiException(status=400, reason="Institution down")
        api_ex.body = '{"error_code": "INSTITUTION_NOT_RESPONDING", "error_message": "Bank unavailable"}'

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidInstitutionError)
        assert error.error_code == "INSTITUTION_NOT_RESPONDING"

    def test_map_plaid_error_unknown_code(self):
        """ApiException with unknown error code maps to generic PlaidError."""
        api_ex = ApiException(status=500, reason="Unknown error")
        api_ex.body = (
            '{"error_code": "UNKNOWN_ERROR", "error_message": "Something went wrong"}'
        )

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidError)
        assert error.error_code == "UNKNOWN_ERROR"

    def test_map_plaid_error_no_body(self):
        """ApiException without body still creates PlaidError."""
        api_ex = ApiException(status=500, reason="Server error")

        error = map_plaid_error(api_ex)

        assert isinstance(error, PlaidError)
        assert error.status == 500
        assert "Server error" in error.message
