"""Plaid API client wrapper with environment-aware configuration."""

import plaid
from plaid.api import plaid_api
from plaid.configuration import Configuration

from budget_me.config import get_settings

# Module-level cache
_client_cache = {}


def get_plaid_client() -> plaid_api.PlaidApi:
    """
    Get configured Plaid API client.

    Returns cached client instance based on current settings.
    The client is configured for the appropriate environment
    (sandbox or production) based on PLAID_ENV.

    Returns:
        PlaidApi: Configured Plaid API client
    """
    settings = get_settings()
    cache_key = (settings.plaid_client_id, settings.plaid_secret, settings.plaid_env)

    if cache_key not in _client_cache:
        _client_cache.clear()  # Only keep one client at a time
        _client_cache[cache_key] = _create_plaid_client(settings)

    return _client_cache[cache_key]


def _create_plaid_client(settings) -> plaid_api.PlaidApi:
    """Create Plaid API client from settings."""
    # Map environment to Plaid host
    env_hosts = {
        "sandbox": plaid.Environment.Sandbox,
        "production": plaid.Environment.Production,
    }

    host = env_hosts[settings.plaid_env]

    # Create configuration
    configuration = Configuration(
        host=host,
        api_key={
            "clientId": settings.plaid_client_id,
            "secret": settings.plaid_secret,
        },
    )

    # Create and return API client
    api_client = plaid.ApiClient(configuration)
    return plaid_api.PlaidApi(api_client)
