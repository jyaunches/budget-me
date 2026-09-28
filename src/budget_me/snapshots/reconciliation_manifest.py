"""Strict private manifest schema for snapshot reconciliation decisions.

The manifest is intentionally data-only.  Loading and hashing it never logs or
renders its contents; callers decide how protected operator artifacts are
stored and displayed.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Annotated, Any, Literal
from uuid import UUID

import yaml
from pydantic import (
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StrictBool,
    StrictInt,
    field_validator,
    model_validator,
)
from yaml.constructor import ConstructorError
from yaml.nodes import MappingNode

FlowType = Literal[
    "income",
    "expense",
    "transfer_in",
    "transfer_out",
    "reimbursement_in",
    "reimbursement_out",
    "card_payment",
]
AdjustmentFlowType = Literal[
    "income",
    "expense",
    "transfer_in",
    "transfer_out",
    "reimbursement_in",
    "reimbursement_out",
]
LineItemResolution = Literal["fulfilled", "skipped", "remaining", "adjustment"]

_MONEY_PATTERN = re.compile(r"^[0-9]+\.[0-9]{2}$")
_SIGNED_MONEY_PATTERN = re.compile(r"^-?[0-9]+\.[0-9]{2}$")
_YEAR_MONTH_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])$")
_DATE_PATTERN = re.compile(r"^[0-9]{4}-(0[1-9]|1[0-2])-[0-9]{2}$")


def _strict_nonblank_string(value: Any) -> str:
    """Accept a string only and normalize insignificant edge whitespace."""
    if not isinstance(value, str):
        raise ValueError("must be a string")
    normalized = value.strip()
    if not normalized:
        raise ValueError("must not be blank")
    return normalized


def _strict_uuid(value: Any) -> UUID:
    """Parse UUID text without accepting numeric or byte coercions."""
    if isinstance(value, UUID):
        return value
    if not isinstance(value, str):
        raise ValueError("must be a UUID string")
    try:
        return UUID(value)
    except (ValueError, AttributeError) as exc:
        raise ValueError("must be a valid UUID") from exc


def _money_from_string(value: Any, *, allow_zero: bool) -> Decimal:
    """Parse one non-negative, exactly two-decimal money string."""
    if not isinstance(value, str) or _MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError("must be a string with exactly two decimal places")
    parsed = Decimal(value)
    if parsed < 0 or (not allow_zero and parsed == 0):
        comparator = "nonnegative" if allow_zero else "positive"
        raise ValueError(f"must be {comparator}")
    return parsed


def _positive_money(value: Any) -> Decimal:
    return _money_from_string(value, allow_zero=False)


def _nonnegative_money(value: Any) -> Decimal:
    return _money_from_string(value, allow_zero=True)


def _signed_money(value: Any) -> Decimal:
    if not isinstance(value, str) or _SIGNED_MONEY_PATTERN.fullmatch(value) is None:
        raise ValueError("must be a signed money string with exactly two decimals")
    return Decimal(value)


def _source_date(value: Any) -> str:
    if not isinstance(value, str) or _DATE_PATTERN.fullmatch(value) is None:
        raise ValueError("must be a date string in YYYY-MM-DD form")
    try:
        parsed = date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("must be a valid calendar date") from exc
    return parsed.isoformat()


NonBlankString = Annotated[str, BeforeValidator(_strict_nonblank_string)]
ManifestUUID = Annotated[UUID, BeforeValidator(_strict_uuid)]
PositiveMoney = Annotated[Decimal, BeforeValidator(_positive_money)]
NonnegativeMoney = Annotated[Decimal, BeforeValidator(_nonnegative_money)]
SignedMoney = Annotated[Decimal, BeforeValidator(_signed_money)]
SourceDate = Annotated[str, BeforeValidator(_source_date)]


class _ManifestModel(BaseModel):
    """Shared fail-closed Pydantic settings for every manifest node."""

    model_config = ConfigDict(
        extra="forbid",
        frozen=True,
        hide_input_in_errors=True,
        validate_default=True,
    )


class ReconciliationAllocation(_ManifestModel):
    """One normalized allocation of a source transaction."""

    flow_type: FlowType
    amount: PositiveMoney
    category: NonBlankString


class TransactionDecision(_ManifestModel):
    """Operator-locked allocation decision for one source transaction."""

    transaction_id: ManifestUUID
    manual_locked: StrictBool = True
    pair_group_id: ManifestUUID | None = None
    allocations: list[ReconciliationAllocation]
    source_date: SourceDate | None = None
    source_amount: SignedMoney | None = None
    source_description: NonBlankString | None = None
    source_budget_category: NonBlankString | None = None
    source_reviewed: StrictBool | None = None


class LineItemMatch(_ManifestModel):
    """Amount from one transaction allocation matched to a line item."""

    transaction_id: ManifestUUID
    allocation_index: Annotated[StrictInt, Field(ge=0)]
    amount: PositiveMoney


class LineItemDecision(_ManifestModel):
    """Resolution of one existing snapshot line item."""

    line_item_id: ManifestUUID
    resolution: LineItemResolution
    remaining_amount: NonnegativeMoney = "0.00"
    adjustment_flow_type: AdjustmentFlowType | None = None
    adjustment_amount: PositiveMoney | None = None
    authorization_note: NonBlankString | None = None
    matches: list[LineItemMatch] = Field(default_factory=list)
    source_name: NonBlankString | None = None
    source_item_type: (
        Literal["income", "expense", "transfer_in", "transfer_out"] | None
    ) = None
    source_planned_amount: PositiveMoney | None = None

    @model_validator(mode="after")
    def validate_resolution_payload(self) -> LineItemDecision:
        """Require exactly the fields meaningful for the selected resolution."""
        locators = [
            (match.transaction_id, match.allocation_index) for match in self.matches
        ]
        if len(locators) != len(set(locators)):
            raise ValueError(
                "line-item matches must use each transaction allocation at most once"
            )
        has_adjustment_payload = any(
            value is not None
            for value in (
                self.adjustment_flow_type,
                self.adjustment_amount,
                self.authorization_note,
            )
        )

        if self.resolution == "remaining":
            if self.remaining_amount <= 0:
                raise ValueError("remaining resolution requires remaining_amount > 0")
            if has_adjustment_payload:
                raise ValueError(
                    "remaining resolution cannot include adjustment fields"
                )
            return self

        if self.resolution in {"fulfilled", "skipped"}:
            if self.remaining_amount != 0:
                raise ValueError(
                    f"{self.resolution} resolution requires remaining_amount = 0"
                )
            if has_adjustment_payload:
                raise ValueError(
                    f"{self.resolution} resolution cannot include adjustment fields"
                )
            return self

        if self.remaining_amount != 0:
            raise ValueError("adjustment resolution requires remaining_amount = 0")
        if (
            self.adjustment_flow_type is None
            or self.adjustment_amount is None
            or self.authorization_note is None
        ):
            raise ValueError(
                "adjustment resolution requires adjustment_flow_type, "
                "adjustment_amount, and authorization_note"
            )
        return self


class ReconciliationManifest(_ManifestModel):
    """Versioned target and all operator decisions for one snapshot."""

    version: Literal[1]
    year_month: str
    account_id: NonBlankString
    transaction_decisions: list[TransactionDecision]
    line_item_decisions: list[LineItemDecision]

    @field_validator("version", mode="before")
    @classmethod
    def validate_version_type(cls, value: Any) -> Any:
        """Reject bool/string coercions into manifest version 1."""
        if type(value) is not int:  # noqa: E721 - bool must not pass as integer 1
            raise ValueError("version must be the integer 1")
        return value

    @field_validator("year_month", mode="before")
    @classmethod
    def validate_year_month(cls, value: Any) -> str:
        """Require a literal calendar month in YYYY-MM form."""
        if not isinstance(value, str) or _YEAR_MONTH_PATTERN.fullmatch(value) is None:
            raise ValueError("year_month must use YYYY-MM with a valid month")
        return value

    @model_validator(mode="after")
    def validate_unique_decisions(self) -> ReconciliationManifest:
        """Prevent later list entries from silently overriding a UUID decision."""
        transaction_ids = [
            decision.transaction_id for decision in self.transaction_decisions
        ]
        if len(transaction_ids) != len(set(transaction_ids)):
            raise ValueError("transaction decisions must have unique transaction_id")

        line_item_ids = [decision.line_item_id for decision in self.line_item_decisions]
        if len(line_item_ids) != len(set(line_item_ids)):
            raise ValueError("line item decisions must have unique line_item_id")
        return self


class _UniqueKeySafeLoader(yaml.SafeLoader):
    """SafeLoader variant that rejects duplicate YAML mapping keys."""


def _construct_unique_mapping(
    loader: _UniqueKeySafeLoader,
    node: MappingNode,
    deep: bool = False,
) -> dict[Any, Any]:
    if not isinstance(node, MappingNode):
        raise ConstructorError(
            None,
            None,
            "expected a mapping node",
            node.start_mark,
        )

    mapping: dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in mapping
        except TypeError as exc:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found an unhashable mapping key",
                key_node.start_mark,
            ) from exc
        if duplicate:
            raise ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                "found a duplicate mapping key",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


_UniqueKeySafeLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_unique_mapping,
)


def parse_reconciliation_manifest(content: str) -> ReconciliationManifest:
    """Parse one YAML/JSON mapping without rendering private content."""
    document = yaml.load(content, Loader=_UniqueKeySafeLoader)
    if not isinstance(document, dict):
        raise ValueError("reconciliation manifest root must be a mapping")
    return ReconciliationManifest.model_validate(document)


def load_reconciliation_manifest(path: Path) -> ReconciliationManifest:
    """Load one UTF-8 YAML/JSON mapping without rendering private content."""
    return parse_reconciliation_manifest(path.read_text(encoding="utf-8"))


def _canonical_decision_payload(manifest: ReconciliationManifest) -> dict[str, Any]:
    """Return semantic content with order-insensitive decision lists normalized."""
    payload = manifest.model_dump(mode="json")
    payload["transaction_decisions"] = sorted(
        payload["transaction_decisions"],
        key=lambda decision: decision["transaction_id"],
    )
    for decision in payload["transaction_decisions"]:
        for source_field in (
            "source_date",
            "source_amount",
            "source_description",
            "source_budget_category",
            "source_reviewed",
        ):
            decision.pop(source_field, None)
    for decision in payload["line_item_decisions"]:
        for source_field in (
            "source_name",
            "source_item_type",
            "source_planned_amount",
        ):
            decision.pop(source_field, None)
        decision["matches"] = sorted(
            decision["matches"],
            key=lambda match: (
                match["transaction_id"],
                match["allocation_index"],
                match["amount"],
            ),
        )
    payload["line_item_decisions"] = sorted(
        payload["line_item_decisions"],
        key=lambda decision: decision["line_item_id"],
    )
    return payload


def manifest_decision_hash(manifest: ReconciliationManifest) -> str:
    """Hash normalized target and decisions, independent of YAML/JSON formatting."""
    encoded = json.dumps(
        _canonical_decision_payload(manifest),
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


__all__ = [
    "AdjustmentFlowType",
    "FlowType",
    "LineItemDecision",
    "LineItemMatch",
    "LineItemResolution",
    "ReconciliationAllocation",
    "ReconciliationManifest",
    "TransactionDecision",
    "load_reconciliation_manifest",
    "manifest_decision_hash",
    "parse_reconciliation_manifest",
]
