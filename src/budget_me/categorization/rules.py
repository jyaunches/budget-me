"""Load and match categorization rules without committing personal data."""

from pathlib import Path

import yaml

PACKAGED_RULES_PATH = (
    Path(__file__).resolve().parents[1] / "data" / "categorization-rules.yaml"
)

# Patterns to skip (transfers, payroll, etc.)
SKIP_PATTERNS = [
    "FUNDS TRANSFER",
    "PAYROLL",
    "CREDIT CRD AUTOPAY",
    "CREDIT CRD RWRD",
    "AUTOMATIC PAYMENT",
    "AUTOPAY PAYMENT",
    "ONLINE PAYMENT",
    "EPAYMENT",
    "INTEREST PAID",
    "BALANCE TRANSFER",
    "WIRE TRANSFER",
    "CHECK #",
    "OVERDRAFT",
    "BENEFIT PAYMENT",
    "PAYMENT RECEIVED",
    "ELECTRONIC PAYMENT RECEIVED",
]

# Special merchants that lack merchant information (e.g., Venmo, Zelle)
# These should be flagged for manual review instead of going through inference
SPECIAL_MERCHANTS = [
    "Venmo",
    "Venmo Payment",
    "Zelle",
    "Cash App",
]


def load_rules(path: Path) -> tuple[dict[str, str], list[str], dict[str, str]]:
    """Load merchant→category mappings, category list, and reimbursable merchants from YAML.

    Args:
        path: Path to YAML rules file

    Returns:
        Tuple of (merchant_rules, category_list, reimbursable_merchants)

    Raises:
        FileNotFoundError: If path doesn't exist
    """
    if not path.exists():
        raise FileNotFoundError(f"Rules file not found: {path}")

    with path.open() as f:
        data = yaml.safe_load(f)

    # Extract categories
    categories = list(data.get("categories", {}).keys())

    # Extract merchant mappings
    merchants = data.get("merchants", {})

    # Extract reimbursable merchant mappings
    reimbursable_merchants = data.get("reimbursable_merchants", {})

    return merchants, categories, reimbursable_merchants


def match_merchant(name: str, rules: dict[str, str]) -> tuple[str, str] | None:
    """Match merchant name to category using case-insensitive substring matching.

    Normalizes input by stripping whitespace and converting to lowercase.
    Uses substring matching where the rule merchant name must be contained
    within the transaction name. When multiple rules match, prefers the
    longest/most specific match.

    Args:
        name: Merchant name to match
        rules: Merchant→category mapping dict

    Returns:
        Tuple of (category, matched_merchant_key) or None if no match
    """
    normalized_name = name.strip().lower()

    # Find all matching rules (substring matching)
    matches = []
    for merchant_key, category in rules.items():
        normalized_key = merchant_key.strip().lower()
        if normalized_key in normalized_name:
            matches.append((merchant_key, category, len(normalized_key)))

    # No matches found
    if not matches:
        return None

    # Prefer longer/more specific matches
    # Sort by length descending, return the longest match
    matches.sort(key=lambda x: x[2], reverse=True)
    merchant_key, category, _ = matches[0]

    return (category, merchant_key)


def match_reimbursable(name: str, rules: dict[str, str]) -> str | None:
    """Match merchant name to reimbursable group tag using case-insensitive matching.

    Normalizes input by stripping whitespace and converting to lowercase.

    Args:
        name: Merchant name to match
        rules: Merchant→group_tag mapping dict

    Returns:
        Group tag string (e.g., "work", "utilities") or None if no match
    """
    normalized_name = name.strip().lower()

    for merchant_key, group_tag in rules.items():
        if merchant_key.strip().lower() == normalized_name:
            return group_tag

    return None


def should_skip(name: str) -> bool:
    """Check if transaction should be skipped (transfer, payroll, etc.).

    Args:
        name: Transaction name to check

    Returns:
        True if transaction matches skip pattern
    """
    upper_name = name.upper()
    return any(pattern in upper_name for pattern in SKIP_PATTERNS)


def is_special_merchant(name: str) -> bool:
    """Check if merchant is a special merchant requiring manual review.

    Special merchants (like Venmo, Zelle, Cash App) lack actual merchant information
    from Plaid and should be flagged for manual categorization instead of going
    through the inference/search tiers.

    Args:
        name: Merchant name to check

    Returns:
        True if merchant is in SPECIAL_MERCHANTS list (case-insensitive, exact match)
    """
    normalized_name = name.strip().lower()

    for special_merchant in SPECIAL_MERCHANTS:
        if special_merchant.strip().lower() == normalized_name:
            return True

    return False
