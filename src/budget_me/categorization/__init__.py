"""Transaction categorization domain module.

This module provides automated categorization of bank transactions using a three-tier approach:
1. Packaged defaults plus PostgreSQL-backed private overrides
2. Claude API inference for national brands
3. Tavily web search for unknown merchants

Public exports provide the main entry point via CategorizationService.
"""

from budget_me.categorization.models import (
    CategorizationResult,
    CategorizationStats,
    InferenceResult,
    UnknownMerchant,
)
from budget_me.categorization.service import CategorizationService

__all__ = [
    "CategorizationResult",
    "CategorizationService",
    "CategorizationStats",
    "InferenceResult",
    "UnknownMerchant",
]
