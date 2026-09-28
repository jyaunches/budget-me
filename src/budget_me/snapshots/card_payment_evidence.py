"""Evidence rules for snapshot credit-card payment actuals."""

from collections.abc import Sequence
from decimal import Decimal
from typing import Protocol

CARD_FEED_SOURCE = "card_feed"
CHECKING_ACCOUNT_SOURCE = "checking_account"
CARD_PAYMENT_CATEGORY = "credit_card_payment"


class CardPaymentActual(Protocol):
    """Fields required to validate a snapshot card payment actual."""

    actual_payment_amount: Decimal | None
    actual_payment_date: object | None
    actual_payment_source: str | None
    actual_payment_note: str | None
    actual_payment_transaction_id: object | None


class CheckingTransaction(Protocol):
    """Posted transaction fields used as checking-side evidence."""

    id: object
    account_id: str
    date: object
    amount: Decimal
    pending: bool
    budget_category: str | None


def has_checking_account_marker(card: CardPaymentActual) -> bool:
    """Return whether a card actual declares complete evidence metadata."""
    note = getattr(card, "actual_payment_note", None)
    return (
        getattr(card, "actual_payment_source", None) == CHECKING_ACCOUNT_SOURCE
        and card.actual_payment_amount is not None
        and card.actual_payment_date is not None
        and getattr(card, "actual_payment_transaction_id", None) is not None
        and bool(note and note.strip())
    )


def matching_checking_transaction(
    card: CardPaymentActual,
    transactions: Sequence[CheckingTransaction],
    paying_account_id: str,
) -> CheckingTransaction | None:
    """Return the exact posted checking row supporting a declared exception."""
    if not has_checking_account_marker(card):
        return None
    transaction_id = getattr(card, "actual_payment_transaction_id", None)
    matches = [
        transaction
        for transaction in transactions
        if transaction.id == transaction_id
        and transaction.account_id == paying_account_id
        and not transaction.pending
        and transaction.amount > 0
        and transaction.amount == card.actual_payment_amount
        and transaction.date == card.actual_payment_date
        and transaction.budget_category == CARD_PAYMENT_CATEGORY
    ]
    return matches[0] if len(matches) == 1 else None


def actual_matches_feed_or_evidence(
    card: CardPaymentActual,
    expected_amount: Decimal,
    expected_date: object | None,
    *,
    transactions: Sequence[CheckingTransaction],
    paying_account_id: str,
) -> bool:
    """Accept exact card-feed facts or one exact posted checking transaction."""
    return (
        card.actual_payment_amount == expected_amount
        and card.actual_payment_date == expected_date
    ) or matching_checking_transaction(
        card, transactions, paying_account_id
    ) is not None
