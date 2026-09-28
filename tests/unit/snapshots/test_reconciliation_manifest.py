"""Strict parsing and hashing tests for private reconciliation manifests."""

from __future__ import annotations

import json
from copy import deepcopy
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError
from yaml.constructor import ConstructorError

from budget_me.snapshots.reconciliation_manifest import (
    ReconciliationManifest,
    load_reconciliation_manifest,
    manifest_decision_hash,
)

TXN_A = "00000000-0000-0000-0000-000000000001"
TXN_B = "00000000-0000-0000-0000-000000000002"
LINE_A = "00000000-0000-0000-0000-000000000011"
LINE_B = "00000000-0000-0000-0000-000000000012"
PAIR_GROUP = "00000000-0000-0000-0000-000000000021"


def _valid_payload() -> dict:
    return {
        "version": 1,
        "year_month": "2026-07",
        "account_id": "synthetic-checking",
        "transaction_decisions": [
            {
                "transaction_id": TXN_A,
                "manual_locked": True,
                "pair_group_id": None,
                "allocations": [
                    {
                        "flow_type": "expense",
                        "amount": "12.34",
                        "category": "groceries",
                    },
                    {
                        "flow_type": "transfer_out",
                        "amount": "5.00",
                        "category": "transfer",
                    },
                ],
            },
            {
                "transaction_id": TXN_B,
                "pair_group_id": PAIR_GROUP,
                "allocations": [],
            },
        ],
        "line_item_decisions": [
            {
                "line_item_id": LINE_A,
                "resolution": "remaining",
                "remaining_amount": "20.00",
                "matches": [
                    {
                        "transaction_id": TXN_A,
                        "allocation_index": 1,
                        "amount": "5.00",
                    },
                    {
                        "transaction_id": TXN_A,
                        "allocation_index": 0,
                        "amount": "12.34",
                    },
                ],
            },
            {
                "line_item_id": LINE_B,
                "resolution": "fulfilled",
                "remaining_amount": "0.00",
                "matches": [],
            },
        ],
    }


def _write(path: Path, content: str) -> Path:
    path.write_text(content, encoding="utf-8")
    return path


def test_loads_yaml_and_json_into_the_same_strict_manifest(tmp_path: Path) -> None:
    payload = _valid_payload()
    yaml_path = _write(
        tmp_path / "manifest.yaml",
        yaml.safe_dump(payload, sort_keys=False),
    )
    json_path = _write(
        tmp_path / "manifest.json",
        json.dumps(payload, indent=4),
    )

    yaml_manifest = load_reconciliation_manifest(yaml_path)
    json_manifest = load_reconciliation_manifest(json_path)

    assert yaml_manifest == json_manifest
    assert yaml_manifest.transaction_decisions[0].allocations[0].amount == Decimal(
        "12.34"
    )
    assert yaml_manifest.line_item_decisions[0].remaining_amount == Decimal("20.00")
    assert yaml_manifest.transaction_decisions[1].manual_locked is True


def test_zero_transaction_may_explicitly_have_no_allocations() -> None:
    payload = _valid_payload()
    payload["transaction_decisions"] = [payload["transaction_decisions"][1]]

    manifest = ReconciliationManifest.model_validate(payload)

    assert manifest.transaction_decisions[0].allocations == []


@pytest.mark.parametrize(
    ("mutate", "invalid_value"),
    [
        (
            lambda payload, value: payload["transaction_decisions"][0]["allocations"][
                0
            ].__setitem__("amount", value),
            12.34,
        ),
        (
            lambda payload, value: payload["line_item_decisions"][0].__setitem__(
                "remaining_amount", value
            ),
            20.0,
        ),
        (
            lambda payload, value: payload["line_item_decisions"][0]["matches"][
                0
            ].__setitem__("amount", value),
            5,
        ),
    ],
)
def test_money_fields_reject_float_and_integer_coercion(mutate, invalid_value) -> None:
    payload = _valid_payload()
    mutate(payload, invalid_value)

    with pytest.raises(ValidationError, match="string with exactly two decimal"):
        ReconciliationManifest.model_validate(payload)


def test_adjustment_amount_rejects_float_coercion() -> None:
    payload = _valid_payload()
    payload["line_item_decisions"] = [
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "adjustment_flow_type": "expense",
            "adjustment_amount": 2.0,
            "authorization_note": "approved synthetic adjustment",
        }
    ]

    with pytest.raises(ValidationError, match="string with exactly two decimal"):
        ReconciliationManifest.model_validate(payload)


@pytest.mark.parametrize("amount", ["0.00", "-1.00", "1", "1.0", "1.000", " 1.00"])
def test_positive_allocation_amount_is_exactly_two_decimal_string(amount: str) -> None:
    payload = _valid_payload()
    payload["transaction_decisions"][0]["allocations"][0]["amount"] = amount

    with pytest.raises(ValidationError):
        ReconciliationManifest.model_validate(payload)


@pytest.mark.parametrize(
    "year_month",
    ["2026-7", "2026-00", "2026-13", "26-07", "2026/07", 202607],
)
def test_year_month_requires_valid_yyyy_mm(year_month) -> None:
    payload = _valid_payload()
    payload["year_month"] = year_month

    with pytest.raises(ValidationError, match="YYYY-MM"):
        ReconciliationManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("decision_key", "identifier_key"),
    [
        ("transaction_decisions", "transaction_id"),
        ("line_item_decisions", "line_item_id"),
    ],
)
def test_decision_identifiers_must_be_unique(
    decision_key: str,
    identifier_key: str,
) -> None:
    payload = _valid_payload()
    payload[decision_key][1][identifier_key] = payload[decision_key][0][identifier_key]

    with pytest.raises(ValidationError, match="must have unique"):
        ReconciliationManifest.model_validate(payload)


@pytest.mark.parametrize(
    "line_decision",
    [
        {
            "line_item_id": LINE_A,
            "resolution": "remaining",
            "remaining_amount": "0.00",
        },
        {
            "line_item_id": LINE_A,
            "resolution": "remaining",
            "remaining_amount": "1.00",
            "adjustment_amount": "1.00",
        },
        {
            "line_item_id": LINE_A,
            "resolution": "fulfilled",
            "remaining_amount": "1.00",
        },
        {
            "line_item_id": LINE_A,
            "resolution": "skipped",
            "adjustment_flow_type": "expense",
        },
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "adjustment_flow_type": "expense",
            "adjustment_amount": "2.00",
        },
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "remaining_amount": "1.00",
            "adjustment_flow_type": "expense",
            "adjustment_amount": "2.00",
            "authorization_note": "approved synthetic adjustment",
        },
    ],
)
def test_line_item_resolution_payloads_fail_closed(line_decision: dict) -> None:
    payload = _valid_payload()
    payload["line_item_decisions"] = [line_decision]

    with pytest.raises(ValidationError):
        ReconciliationManifest.model_validate(payload)


def test_adjustment_requires_complete_authorized_payload() -> None:
    payload = _valid_payload()
    payload["line_item_decisions"] = [
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "remaining_amount": "0.00",
            "adjustment_flow_type": "reimbursement_in",
            "adjustment_amount": "2.00",
            "authorization_note": "  approved synthetic adjustment  ",
            "matches": [],
        }
    ]

    manifest = ReconciliationManifest.model_validate(payload)

    decision = manifest.line_item_decisions[0]
    assert decision.adjustment_amount == Decimal("2.00")
    assert decision.authorization_note == "approved synthetic adjustment"


def test_card_payment_is_not_an_adjustment_flow() -> None:
    payload = _valid_payload()
    payload["line_item_decisions"] = [
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "adjustment_flow_type": "card_payment",
            "adjustment_amount": "2.00",
            "authorization_note": "approved",
        }
    ]

    with pytest.raises(ValidationError):
        ReconciliationManifest.model_validate(payload)


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("account_id", "   "),
        ("version", "1"),
        ("version", True),
    ],
)
def test_top_level_scalar_types_are_not_coerced(field: str, value) -> None:
    payload = _valid_payload()
    payload[field] = value

    with pytest.raises(ValidationError):
        ReconciliationManifest.model_validate(payload)


def test_manual_locked_must_be_a_boolean() -> None:
    payload = _valid_payload()
    payload["transaction_decisions"][0]["manual_locked"] = "true"

    with pytest.raises(ValidationError):
        ReconciliationManifest.model_validate(payload)


def test_pair_group_must_be_a_uuid() -> None:
    payload = _valid_payload()
    payload["transaction_decisions"][0]["pair_group_id"] = "not-a-uuid"

    with pytest.raises(ValidationError, match="valid UUID"):
        ReconciliationManifest.model_validate(payload)


def test_category_and_authorization_note_must_be_nonblank() -> None:
    payload = _valid_payload()
    payload["transaction_decisions"][0]["allocations"][0]["category"] = "  "

    with pytest.raises(ValidationError, match="must not be blank"):
        ReconciliationManifest.model_validate(payload)

    payload = _valid_payload()
    payload["line_item_decisions"] = [
        {
            "line_item_id": LINE_A,
            "resolution": "adjustment",
            "adjustment_flow_type": "expense",
            "adjustment_amount": "2.00",
            "authorization_note": "  ",
        }
    ]
    with pytest.raises(ValidationError, match="must not be blank"):
        ReconciliationManifest.model_validate(payload)


def test_manifest_hash_ignores_formatting_and_decision_list_order(
    tmp_path: Path,
) -> None:
    payload = _valid_payload()
    reordered = deepcopy(payload)
    reordered["transaction_decisions"].reverse()
    reordered["line_item_decisions"].reverse()
    reordered["line_item_decisions"][1]["matches"].reverse()
    reordered["transaction_decisions"][1].pop("manual_locked")

    yaml_manifest = load_reconciliation_manifest(
        _write(
            tmp_path / "manifest.yaml",
            yaml.safe_dump(payload, sort_keys=False),
        )
    )
    json_manifest = load_reconciliation_manifest(
        _write(
            tmp_path / "manifest.json",
            json.dumps(reordered, sort_keys=True, separators=(",", ":")),
        )
    )

    yaml_hash = manifest_decision_hash(yaml_manifest)
    json_hash = manifest_decision_hash(json_manifest)
    assert yaml_hash == json_hash
    assert len(yaml_hash) == 64
    assert set(yaml_hash) <= set("0123456789abcdef")


@pytest.mark.parametrize(
    "mutation",
    [
        lambda payload: payload.__setitem__("account_id", "different-account"),
        lambda payload: payload["transaction_decisions"][0].__setitem__(
            "manual_locked", False
        ),
        lambda payload: payload["transaction_decisions"][0]["allocations"][
            0
        ].__setitem__("amount", "12.35"),
        lambda payload: payload["line_item_decisions"][0].__setitem__(
            "remaining_amount", "20.01"
        ),
    ],
)
def test_manifest_hash_includes_target_and_every_decision(mutation) -> None:
    original_payload = _valid_payload()
    changed_payload = deepcopy(original_payload)
    mutation(changed_payload)

    original = ReconciliationManifest.model_validate(original_payload)
    changed = ReconciliationManifest.model_validate(changed_payload)

    assert manifest_decision_hash(original) != manifest_decision_hash(changed)


def test_private_source_hints_are_typed_but_excluded_from_decision_hash() -> None:
    payload = _valid_payload()
    hinted = deepcopy(payload)
    hinted["transaction_decisions"][0].update(
        {
            "source_date": "2026-07-15",
            "source_amount": "17.34",
            "source_description": "PRIVATE MERCHANT CONTEXT",
            "source_budget_category": "groceries",
            "source_reviewed": True,
        }
    )
    hinted["line_item_decisions"][0].update(
        {
            "source_name": "PRIVATE PLAN CONTEXT",
            "source_item_type": "expense",
            "source_planned_amount": "25.00",
        }
    )

    plain_manifest = ReconciliationManifest.model_validate(payload)
    hinted_manifest = ReconciliationManifest.model_validate(hinted)

    assert hinted_manifest.transaction_decisions[0].source_description == (
        "PRIVATE MERCHANT CONTEXT"
    )
    assert manifest_decision_hash(hinted_manifest) == manifest_decision_hash(
        plain_manifest
    )


def test_duplicate_line_match_locator_is_rejected() -> None:
    payload = _valid_payload()
    payload["line_item_decisions"][0]["matches"][1]["allocation_index"] = 1

    with pytest.raises(ValidationError, match="at most once"):
        ReconciliationManifest.model_validate(payload)


def test_validation_errors_hide_private_input_values() -> None:
    payload = _valid_payload()
    private_value = "PRIVATE-MERCHANT-VALUE"
    payload["transaction_decisions"][0]["source_amount"] = private_value

    with pytest.raises(ValidationError) as raised:
        ReconciliationManifest.model_validate(payload)

    assert private_value not in str(raised.value)


def test_loader_rejects_non_mapping_and_unsafe_yaml_without_output(
    tmp_path: Path,
    capsys,
) -> None:
    non_mapping = _write(tmp_path / "list.yaml", "- private-value\n")
    unsafe = _write(
        tmp_path / "unsafe.yaml",
        "!!python/object/apply:builtins.print ['private-value']\n",
    )

    with pytest.raises(ValueError, match="root must be a mapping"):
        load_reconciliation_manifest(non_mapping)
    with pytest.raises(ConstructorError):
        load_reconciliation_manifest(unsafe)

    captured = capsys.readouterr()
    assert captured.out == ""
    assert captured.err == ""


def test_loader_rejects_duplicate_yaml_mapping_keys(tmp_path: Path) -> None:
    path = _write(
        tmp_path / "duplicate.yaml",
        """\
version: 1
version: 1
year_month: '2026-07'
account_id: synthetic
transaction_decisions: []
line_item_decisions: []
""",
    )

    with pytest.raises(ConstructorError, match="duplicate mapping key"):
        load_reconciliation_manifest(path)


def test_unknown_fields_are_rejected() -> None:
    payload = _valid_payload()
    payload["private_note"] = "must not be silently ignored"

    with pytest.raises(ValidationError, match="Extra inputs are not permitted"):
        ReconciliationManifest.model_validate(payload)
