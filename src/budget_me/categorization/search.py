"""Tavily API client for merchant information search.

Uses Tavily's search API to find information about unknown merchants.
"""

import httpx
from loguru import logger


class MerchantSearchClient:
    """Searches for merchant information using Tavily API."""

    def __init__(self, api_key: str):
        """Initialize the search client.

        Args:
            api_key: Tavily API key
        """
        self.api_key = api_key
        self._client = httpx.AsyncClient(timeout=10.0)

    async def search(self, merchant: str) -> str:
        """Search for merchant info. Returns concatenated result snippets.

        Args:
            merchant: Merchant name to search for

        Returns:
            Concatenated search result snippets, or empty string on error
        """
        try:
            response = await self._client.post(
                "https://api.tavily.com/search",
                json={
                    "api_key": self.api_key,
                    "query": f"{merchant} company business",
                    "max_results": 3,
                },
            )
            response.raise_for_status()
            data = response.json()

            # Extract and concatenate result snippets
            results = data.get("results", [])
            if not results:
                return ""

            snippets = [result.get("content", "") for result in results]
            return " ".join(filter(None, snippets))

        except httpx.TimeoutException:
            logger.warning("Merchant search timed out")
            return ""
        except httpx.HTTPStatusError as e:
            logger.warning(f"Merchant search HTTP error: {e.response.status_code}")
            return ""
        except Exception as e:
            logger.error(f"Merchant search failed: {type(e).__name__}")
            return ""

    async def close(self):
        """Close the HTTP client."""
        await self._client.aclose()
