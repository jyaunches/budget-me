"""Unit tests for Tavily search client."""

from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from budget_me.categorization.search import MerchantSearchClient


@pytest.fixture
def mock_httpx_client():
    """Mock httpx.AsyncClient."""
    with patch("budget_me.categorization.search.httpx.AsyncClient") as mock:
        yield mock


@pytest.fixture
def search_client(mock_httpx_client):
    """Create search client with mocked httpx."""
    return MerchantSearchClient(api_key="test-key")


class TestMerchantSearchClient:
    """Tests for MerchantSearchClient."""

    @pytest.mark.asyncio
    async def test_search_returns_content(self, search_client, mock_httpx_client):
        """Test search returns concatenated content."""
        # Mock successful response
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"content": "First snippet"},
                {"content": "Second snippet"},
            ]
        }
        mock_httpx_client.return_value.post = AsyncMock(return_value=mock_response)

        result = await search_client.search("Test Merchant")

        assert result == "First snippet Second snippet"

    @pytest.mark.asyncio
    async def test_search_handles_no_results(self, search_client, mock_httpx_client):
        """Test search handles empty results gracefully."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_httpx_client.return_value.post = AsyncMock(return_value=mock_response)

        result = await search_client.search("Unknown")

        assert result == ""

    @pytest.mark.asyncio
    async def test_search_handles_errors(self, search_client, mock_httpx_client):
        """Test search handles errors gracefully."""
        mock_httpx_client.return_value.post = AsyncMock(
            side_effect=Exception("Network error")
        )

        result = await search_client.search("Test Merchant")

        assert result == ""

    @pytest.mark.asyncio
    async def test_client_closes_cleanly(self, search_client, mock_httpx_client):
        """Test client closes without errors."""
        mock_httpx_client.return_value.aclose = AsyncMock()

        await search_client.close()

        mock_httpx_client.return_value.aclose.assert_called_once()

    @pytest.mark.asyncio
    async def test_search_handles_timeout(self, search_client, mock_httpx_client):
        """Test search handles timeout gracefully."""
        mock_httpx_client.return_value.post = AsyncMock(
            side_effect=httpx.TimeoutException("Timeout")
        )

        result = await search_client.search("Test Merchant")

        assert result == ""

    @pytest.mark.asyncio
    async def test_search_handles_http_error(self, search_client, mock_httpx_client):
        """Test search handles HTTP errors gracefully."""
        mock_response = MagicMock()
        mock_response.status_code = 429
        mock_error = httpx.HTTPStatusError(
            "Rate limit", request=MagicMock(), response=mock_response
        )
        mock_httpx_client.return_value.post = AsyncMock(side_effect=mock_error)

        result = await search_client.search("Test Merchant")

        assert result == ""

    @pytest.mark.asyncio
    async def test_search_filters_empty_content(self, search_client, mock_httpx_client):
        """Test search filters out empty content."""
        mock_response = MagicMock()
        mock_response.json.return_value = {
            "results": [
                {"content": "Valid snippet"},
                {"content": ""},
                {"content": "Another snippet"},
            ]
        }
        mock_httpx_client.return_value.post = AsyncMock(return_value=mock_response)

        result = await search_client.search("Test Merchant")

        assert result == "Valid snippet Another snippet"

    @pytest.mark.asyncio
    async def test_search_sends_correct_request(self, search_client, mock_httpx_client):
        """Test search sends correct API request."""
        mock_response = MagicMock()
        mock_response.json.return_value = {"results": []}
        mock_httpx_client.return_value.post = AsyncMock(return_value=mock_response)

        await search_client.search("Starbucks")

        # Verify post was called with correct parameters
        call_args = mock_httpx_client.return_value.post.call_args
        assert call_args[0][0] == "https://api.tavily.com/search"
        assert call_args[1]["json"]["api_key"] == "test-key"
        assert "Starbucks" in call_args[1]["json"]["query"]
        assert call_args[1]["json"]["max_results"] == 3

    @pytest.mark.asyncio
    async def test_search_handles_malformed_response(
        self, search_client, mock_httpx_client
    ):
        """Test search handles malformed JSON response."""
        mock_response = MagicMock()
        mock_response.json.return_value = {}  # Missing "results" key
        mock_httpx_client.return_value.post = AsyncMock(return_value=mock_response)

        result = await search_client.search("Test Merchant")

        assert result == ""
