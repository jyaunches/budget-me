"""Value objects for categorization domain.

These immutable data classes represent categorization results and statistics.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal
from typing import Literal
from uuid import UUID


@dataclass(frozen=True)
class InferenceResult:
    """Result from Claude inference."""

    category: str | None
    confidence: Literal["high", "medium", "low", "none"]


@dataclass(frozen=True)
class UnknownMerchant:
    """Merchant that couldn't be categorized."""

    name: str
    amount: Decimal
    date: date
    reason: str
    account_name: str = ""


@dataclass
class CategorizationStats:
    """Statistics from a categorization run."""

    total_processed: int = 0
    from_rules: int = 0
    from_inference: int = 0
    from_search: int = 0
    skipped: int = 0
    unknown: int = 0
    reimbursable_flagged: int = 0


@dataclass
class CategorizationResult:
    """Complete result from categorization workflow."""

    categorized: dict[str, list[UUID]] = field(
        default_factory=dict
    )  # category → transaction IDs
    new_rules: dict[str, str] = field(
        default_factory=dict
    )  # merchant → category (to persist)
    unknowns: list[UnknownMerchant] = field(default_factory=list)
    stats: CategorizationStats = field(default_factory=CategorizationStats)
    reimbursable_flagged: dict[UUID, str] = field(
        default_factory=dict
    )  # transaction ID → group tag
