from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from decimal import Decimal
import re
from collections.abc import Mapping
from types import MappingProxyType
from typing import Any


DISPLAY_STATE_PAIRED = "paired"
DISPLAY_STATE_OPEN = "open"
DISPLAY_STATES = (DISPLAY_STATE_PAIRED, DISPLAY_STATE_OPEN)

DECISION_STATUS_PROPOSED = "proposed"
DECISION_STATUS_PAIRED = "paired"
DECISION_STATUS_OPEN = "open"
DECISION_STATUS_SUPPRESSED = "suppressed"
DECISION_STATUS_CONSUMED = "consumed"
DECISION_STATUS_EXPIRED = "expired"
DECISION_STATUSES = (
    DECISION_STATUS_PROPOSED,
    DECISION_STATUS_PAIRED,
    DECISION_STATUS_OPEN,
    DECISION_STATUS_SUPPRESSED,
    DECISION_STATUS_CONSUMED,
    DECISION_STATUS_EXPIRED,
)

MATCH_DOMAIN_FREE = "free"
MATCH_DOMAIN_SPECIAL = "special"
MATCH_DOMAINS = (MATCH_DOMAIN_FREE, MATCH_DOMAIN_SPECIAL)

WARNING_INVOICE_AMOUNT_MISMATCH = "invoice_amount_mismatch"

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True, slots=True)
class DecisionWarning:
    code: str
    message: str

    def __post_init__(self) -> None:
        _normalize_required_text(self.code, "code")
        _normalize_required_text(self.message, "message")

    def to_dict(self) -> dict[str, str]:
        return {
            "code": self.code,
            "message": self.message,
        }


@dataclass(frozen=True, slots=True)
class WorkbenchReconciliationDecision:
    decision_id: str
    decision_key: str
    scope_month: str
    display_state: str
    decision_status: str
    match_domain: str
    match_shape: str
    rule_code: str
    rule_version: str
    row_ids: tuple[str, ...]
    oa_row_ids: tuple[str, ...] = ()
    bank_row_ids: tuple[str, ...] = ()
    invoice_row_ids: tuple[str, ...] = ()
    amount: Decimal | str | int | float | None = None
    direction: str = ""
    payment_amount_closed: bool | None = None
    invoice_amount_closed: bool | None = None
    warnings: tuple[DecisionWarning, ...] = ()
    evidence: dict[str, Any] | None = None
    blockers: tuple[dict[str, Any], ...] = ()
    explanation: str = ""
    generated_at: datetime | str | None = None
    source_versions: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "decision_id", _normalize_required_text(self.decision_id, "decision_id"))
        object.__setattr__(self, "decision_key", _normalize_required_text(self.decision_key, "decision_key"))
        object.__setattr__(self, "scope_month", _normalize_month(self.scope_month, "scope_month"))
        _validate_choice(self.display_state, DISPLAY_STATES, "display_state")
        _validate_choice(self.decision_status, DECISION_STATUSES, "decision_status")
        _validate_choice(self.match_domain, MATCH_DOMAINS, "match_domain")
        object.__setattr__(self, "match_shape", _normalize_required_text(self.match_shape, "match_shape"))
        object.__setattr__(self, "rule_code", _normalize_required_text(self.rule_code, "rule_code"))
        object.__setattr__(self, "rule_version", _normalize_required_text(self.rule_version, "rule_version"))
        object.__setattr__(self, "row_ids", _normalize_row_ids(self.row_ids, "row_ids"))
        object.__setattr__(self, "oa_row_ids", _normalize_row_ids(self.oa_row_ids, "oa_row_ids"))
        object.__setattr__(self, "bank_row_ids", _normalize_row_ids(self.bank_row_ids, "bank_row_ids"))
        object.__setattr__(self, "invoice_row_ids", _normalize_row_ids(self.invoice_row_ids, "invoice_row_ids"))
        for warning in self.warnings:
            if not isinstance(warning, DecisionWarning):
                raise ValueError("warnings must contain DecisionWarning values.")
        object.__setattr__(self, "warnings", tuple(self.warnings))
        object.__setattr__(self, "evidence", _freeze_plain_value(self.evidence or {}))
        object.__setattr__(self, "blockers", _freeze_plain_value(tuple(self.blockers)))
        object.__setattr__(self, "source_versions", _freeze_plain_value(self.source_versions or {}))

    def to_dict(self) -> dict[str, Any]:
        return {
            "decision_id": self.decision_id,
            "decision_key": self.decision_key,
            "scope_month": self.scope_month,
            "display_state": self.display_state,
            "decision_status": self.decision_status,
            "match_domain": self.match_domain,
            "match_shape": self.match_shape,
            "rule_code": self.rule_code,
            "rule_version": self.rule_version,
            "row_ids": list(self.row_ids),
            "oa_row_ids": list(self.oa_row_ids),
            "bank_row_ids": list(self.bank_row_ids),
            "invoice_row_ids": list(self.invoice_row_ids),
            "amount": _to_plain_value(self.amount),
            "direction": self.direction,
            "payment_amount_closed": self.payment_amount_closed,
            "invoice_amount_closed": self.invoice_amount_closed,
            "warnings": [warning.to_dict() for warning in self.warnings],
            "evidence": _to_plain_value(self.evidence or {}),
            "blockers": _to_plain_value(list(self.blockers)),
            "explanation": self.explanation,
            "generated_at": _to_plain_value(self.generated_at),
            "source_versions": _to_plain_value(self.source_versions or {}),
        }


WorkbenchDecision = WorkbenchReconciliationDecision


def resolve_decision_scope_month(
    *,
    has_bank: bool,
    bank_trade_month: str | None,
    has_oa: bool,
    oa_month: str | None,
) -> str:
    if has_bank:
        if not bank_trade_month:
            raise ValueError("bank_trade_month is required for decisions containing bank rows.")
        return _normalize_month(bank_trade_month, "bank_trade_month")
    if has_oa:
        if not oa_month:
            raise ValueError("oa_month is required for OA decisions without bank rows.")
        return _normalize_month(oa_month, "oa_month")
    raise ValueError("scope month ownership requires bank_trade_month or oa_month.")


def expand_scope_month_window(scope_month: str) -> list[str]:
    year, month = _parse_month(scope_month, "scope_month")
    return [_format_month(year, month + offset) for offset in range(-2, 3)]


def _validate_choice(value: str, valid_values: tuple[str, ...], field_name: str) -> None:
    if value not in valid_values:
        allowed = ", ".join(valid_values)
        raise ValueError(f"{field_name} must be one of: {allowed}.")


def _normalize_required_text(value: str, field_name: str) -> str:
    normalized = str(value or "").strip()
    if not normalized:
        raise ValueError(f"{field_name} is required.")
    return normalized


def _normalize_row_ids(row_ids: tuple[str, ...], field_name: str) -> tuple[str, ...]:
    if not isinstance(row_ids, tuple):
        raise ValueError(f"{field_name} must be a tuple of row ids.")
    normalized = tuple(str(row_id or "").strip() for row_id in row_ids)
    if any(not row_id for row_id in normalized):
        raise ValueError(f"{field_name} cannot contain empty row ids.")
    if len(set(normalized)) != len(normalized):
        raise ValueError(f"{field_name} cannot contain duplicate row ids.")
    return normalized


def _normalize_month(value: str, field_name: str) -> str:
    month = str(value or "").strip()
    if not MONTH_RE.match(month):
        raise ValueError(f"{field_name} must be YYYY-MM.")
    _parse_month(month, field_name)
    return month


def _parse_month(value: str, field_name: str) -> tuple[int, int]:
    month = str(value or "").strip()
    if not MONTH_RE.match(month):
        raise ValueError(f"{field_name} must be YYYY-MM.")
    year_text, month_text = month.split("-", 1)
    year = int(year_text)
    month_number = int(month_text)
    if month_number < 1 or month_number > 12:
        raise ValueError(f"{field_name} must be YYYY-MM.")
    return year, month_number


def _format_month(year: int, month: int) -> str:
    zero_based_month = month - 1
    resolved_year = year + zero_based_month // 12
    resolved_month = zero_based_month % 12 + 1
    return f"{resolved_year:04d}-{resolved_month:02d}"


def _to_plain_value(value: Any) -> Any:
    if isinstance(value, DecisionWarning):
        return value.to_dict()
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, Mapping):
        return {str(key): _to_plain_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_to_plain_value(item) for item in value]
    return value


def _freeze_plain_value(value: Any) -> Any:
    if isinstance(value, DecisionWarning):
        return value
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Mapping):
        return MappingProxyType({str(key): _freeze_plain_value(item) for key, item in value.items()})
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_plain_value(item) for item in value)
    return value
