"""Tests for checking-side card payment evidence."""

from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

from budget_me.snapshots.card_payment_evidence import (
    actual_matches_feed_or_evidence,
)

CHECKING_ID = "checking-1"


def _card(transaction_id):
    return SimpleNamespace(
        actual_payment_amount=Decimal("180.00"),
        actual_payment_date=date(2026, 7, 23),
        actual_payment_source="checking_account",
        actual_payment_transaction_id=transaction_id,
        actual_payment_note="Unique posted checking debit; card feed omitted it.",
    )


def _transaction(transaction_id):
    return SimpleNamespace(
        id=transaction_id,
        account_id=CHECKING_ID,
        date=date(2026, 7, 23),
        amount=Decimal("180.00"),
        pending=False,
        budget_category="credit_card_payment",
    )


def test_exact_card_feed_match_needs_no_manual_evidence() -> None:
    card = SimpleNamespace(
        actual_payment_amount=Decimal("40.00"),
        actual_payment_date=date(2026, 7, 10),
    )

    assert actual_matches_feed_or_evidence(
        card,
        Decimal("40.00"),
        date(2026, 7, 10),
        transactions=[],
        paying_account_id=CHECKING_ID,
    )


def test_checking_evidence_requires_the_exact_posted_classified_row() -> None:
    transaction_id = uuid4()
    card = _card(transaction_id)
    transaction = _transaction(transaction_id)

    assert actual_matches_feed_or_evidence(
        card,
        Decimal("0.00"),
        None,
        transactions=[transaction],
        paying_account_id=CHECKING_ID,
    )

    transaction.pending = True
    assert not actual_matches_feed_or_evidence(
        card,
        Decimal("0.00"),
        None,
        transactions=[transaction],
        paying_account_id=CHECKING_ID,
    )

    transaction.pending = False
    transaction.budget_category = "transfer"
    assert not actual_matches_feed_or_evidence(
        card,
        Decimal("0.00"),
        None,
        transactions=[transaction],
        paying_account_id=CHECKING_ID,
    )


def test_note_or_unrelated_transaction_cannot_waive_a_mismatch() -> None:
    transaction_id = uuid4()
    card = _card(transaction_id)

    assert not actual_matches_feed_or_evidence(
        card,
        Decimal("0.00"),
        None,
        transactions=[_transaction(uuid4())],
        paying_account_id=CHECKING_ID,
    )

    card.actual_payment_note = " "
    assert not actual_matches_feed_or_evidence(
        card,
        Decimal("0.00"),
        None,
        transactions=[_transaction(transaction_id)],
        paying_account_id=CHECKING_ID,
    )
