"""Unit tests for Claude inference client."""

from unittest.mock import MagicMock, patch

import pytest

from budget_me.categorization.inference import MerchantInferenceClient
from budget_me.categorization.models import InferenceResult


@pytest.fixture
def mock_anthropic():
    """Mock Anthropic client."""
    with patch("budget_me.categorization.inference.anthropic.Anthropic") as mock:
        yield mock


@pytest.fixture
def inference_client(mock_anthropic):
    """Create inference client with mocked Anthropic."""
    return MerchantInferenceClient(api_key="test-key")


class TestMerchantInferenceClient:
    """Tests for MerchantInferenceClient."""

    @pytest.mark.asyncio
    async def test_infer_category_returns_inference_result(
        self, inference_client, mock_anthropic
    ):
        """Test that infer_category returns InferenceResult."""
        # Mock Claude response
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "dining", "confidence": "high"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert isinstance(result, InferenceResult)
        assert result.category == "dining"
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_infer_category_parses_high_confidence(
        self, inference_client, mock_anthropic
    ):
        """Test parsing high confidence response."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "dining", "confidence": "high"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert result.category == "dining"
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_infer_category_handles_unknown(
        self, inference_client, mock_anthropic
    ):
        """Test handling of unknown category."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "unknown", "confidence": "low"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "VUYNRP", ["dining", "groceries"]
        )

        assert result.category is None
        assert result.confidence == "low"

    @pytest.mark.asyncio
    async def test_infer_category_handles_errors(
        self, inference_client, mock_anthropic
    ):
        """Test error handling returns error result."""
        # Mock API error
        mock_anthropic.return_value.messages.create.side_effect = Exception("API Error")

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert result.category is None
        assert result.confidence == "none"

    @pytest.mark.asyncio
    async def test_infer_category_handles_malformed_json(
        self, inference_client, mock_anthropic
    ):
        """Test handling of malformed JSON response."""
        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="not valid json")]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert result.category is None
        assert result.confidence == "none"

    @pytest.mark.asyncio
    async def test_infer_category_handles_invalid_category(
        self, inference_client, mock_anthropic
    ):
        """Test handling when Claude returns invalid category."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "invalid_cat", "confidence": "high"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert result.category is None
        assert result.confidence == "none"

    @pytest.mark.asyncio
    async def test_infer_category_extracts_json_from_text(
        self, inference_client, mock_anthropic
    ):
        """Test extracting JSON from response with surrounding text."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text='Here is the answer: {"category": "dining", "confidence": "high"} Hope this helps!'
            )
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Starbucks", ["dining", "groceries"]
        )

        assert result.category == "dining"
        assert result.confidence == "high"

    @pytest.mark.asyncio
    async def test_infer_category_sends_correct_prompt(
        self, inference_client, mock_anthropic
    ):
        """Test that correct prompt is sent to Claude."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "dining", "confidence": "high"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        await inference_client.infer_category("Starbucks", ["dining", "groceries"])

        # Verify create was called with correct parameters
        call_args = mock_anthropic.return_value.messages.create.call_args
        assert call_args[1]["model"] == "claude-sonnet-4-20250514"
        assert call_args[1]["max_tokens"] == 100
        assert "Starbucks" in call_args[1]["messages"][0]["content"]
        assert "dining, groceries" in call_args[1]["messages"][0]["content"]

    @pytest.mark.asyncio
    async def test_infer_category_handles_medium_confidence(
        self, inference_client, mock_anthropic
    ):
        """Test handling medium confidence response."""
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(text='{"category": "groceries", "confidence": "medium"}')
        ]
        mock_anthropic.return_value.messages.create.return_value = mock_response

        result = await inference_client.infer_category(
            "Local Market", ["dining", "groceries"]
        )

        assert result.category == "groceries"
        assert result.confidence == "medium"
