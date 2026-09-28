"""Claude API client for merchant category inference.

Uses Anthropic's Claude API to infer merchant categories based on merchant names.
"""

import json
from typing import Any

import anthropic
from loguru import logger

from budget_me.categorization.models import InferenceResult


class MerchantInferenceClient:
    """Infers merchant categories using Claude API."""

    def __init__(self, api_key: str, model: str = "claude-sonnet-4-20250514"):
        """Initialize the inference client.

        Args:
            api_key: Anthropic API key
            model: Claude model to use (default: claude-sonnet-4-20250514)
        """
        self.client = anthropic.Anthropic(api_key=api_key)
        self.model = model

    async def infer_category(
        self,
        merchant: str,
        categories: list[str],
    ) -> InferenceResult:
        """Infer category from merchant name using training knowledge.

        Args:
            merchant: Merchant name to categorize
            categories: List of valid category names

        Returns:
            InferenceResult with category and confidence level
        """
        try:
            prompt = self._build_prompt(merchant, categories)
            response = self.client.messages.create(
                model=self.model,
                max_tokens=100,
                messages=[{"role": "user", "content": prompt}],
            )

            # Extract text from response
            content = response.content[0].text if response.content else ""

            # Parse JSON response
            result = self._parse_response(content)

            # Validate category is in list
            category = result.get("category")
            if category and category not in categories and category != "unknown":
                logger.warning(
                    "Inference returned a category outside the configured set"
                )
                return InferenceResult(category=None, confidence="none")

            # Convert "unknown" to None
            if category == "unknown":
                category = None

            confidence = result.get("confidence", "none")
            return InferenceResult(category=category, confidence=confidence)

        except Exception as e:
            logger.error(f"Category inference failed: {type(e).__name__}")
            return InferenceResult(category=None, confidence="none")

    def _build_prompt(self, merchant: str, categories: list[str]) -> str:
        """Build prompt for Claude API.

        Args:
            merchant: Merchant name
            categories: List of valid categories

        Returns:
            Formatted prompt string
        """
        categories_str = ", ".join(categories)
        return f"""Given the merchant name "{merchant}", determine which budget category it belongs to.

Available categories: {categories_str}

Respond ONLY with valid JSON in this format:
{{"category": "category_name", "confidence": "high|medium|low"}}

Use "unknown" for the category if you cannot confidently categorize this merchant.
Use confidence "high" for well-known national brands, "medium" for recognizable merchants,
and "low" for ambiguous or unclear merchant names.

Examples:
- "Starbucks" -> {{"category": "dining", "confidence": "high"}}
- "Target" -> {{"category": "shopping", "confidence": "high"}}
- "VUYNRP" -> {{"category": "unknown", "confidence": "low"}}
"""

    def _parse_response(self, content: str) -> dict[str, Any]:
        """Parse JSON response from Claude.

        Args:
            content: Response text from Claude

        Returns:
            Parsed JSON dict

        Raises:
            json.JSONDecodeError: If response is not valid JSON
        """
        # Try to extract JSON from response (in case there's surrounding text)
        content = content.strip()
        if "{" in content and "}" in content:
            start = content.index("{")
            end = content.rindex("}") + 1
            content = content[start:end]

        return json.loads(content)
