from __future__ import annotations

from copy import deepcopy
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from threading import RLock
from typing import Any


TURNOVER_LEDGER_EXTRA_SNAPSHOT_VERSION = 1
TURNOVER_LEDGER_INTEREST_RATE_TYPES = {"annual", "monthly", "none"}
RATE_QUANT = Decimal("0.000001")
MONEY_QUANT = Decimal("0.01")
MAX_PAYMENT_METHOD_LENGTH = 64
MAX_NOTE_LENGTH = 500


class TurnoverLedgerExtraValidationError(ValueError):
    pass


class TurnoverLedgerExtraService:
    def __init__(self, extras: list[dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._extras: dict[str, dict[str, Any]] = {}
        for extra in list(extras or []):
            if not isinstance(extra, dict):
                continue
            normalized = self._normalize_snapshot_extra(extra)
            self._extras[str(normalized["relation_id"])] = normalized

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, object] | None) -> "TurnoverLedgerExtraService":
        if not snapshot:
            return cls()
        extras = snapshot.get("extras")
        return cls(extras=extras if isinstance(extras, list) else [])

    def snapshot(self) -> dict[str, object]:
        with self._lock:
            return {
                "version": TURNOVER_LEDGER_EXTRA_SNAPSHOT_VERSION,
                "extras": [
                    deepcopy(self._extras[relation_id])
                    for relation_id in sorted(self._extras)
                ],
            }

    def get(self, relation_id: str) -> dict[str, object] | None:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        with self._lock:
            extra = self._extras.get(normalized_relation_id)
            return deepcopy(extra) if extra is not None else None

    def upsert(self, relation_id: str, payload: dict[str, object], *, actor: str) -> dict[str, object]:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        normalized_actor = self._normalize_actor(actor)
        incoming = payload if isinstance(payload, dict) else {}
        with self._lock:
            existing = self._extras.get(normalized_relation_id)
            updated_at = self._next_updated_at(existing)
            normalized = self._normalize_extra(
                normalized_relation_id,
                incoming,
                existing=existing,
                updated_at=updated_at,
                updated_by=normalized_actor,
            )
            self._extras[normalized_relation_id] = normalized
            return deepcopy(normalized)

    def remove(self, relation_id: str, *, actor: str) -> None:
        normalized_relation_id = self._normalize_relation_id(relation_id)
        self._normalize_actor(actor)
        with self._lock:
            self._extras.pop(normalized_relation_id, None)

    @classmethod
    def _normalize_snapshot_extra(cls, payload: dict[str, Any]) -> dict[str, Any]:
        relation_id = cls._normalize_relation_id(str(payload.get("relation_id") or ""))
        updated_at = cls._normalize_updated_at(payload.get("updated_at"))
        updated_by = cls._normalize_text(
            payload.get("updated_by"),
            field_name="updated_by",
            max_length=MAX_PAYMENT_METHOD_LENGTH,
        )
        return cls._normalize_extra(
            relation_id,
            payload,
            existing=None,
            updated_at=updated_at,
            updated_by=updated_by,
        )

    @classmethod
    def _normalize_extra(
        cls,
        relation_id: str,
        payload: dict[str, Any],
        *,
        existing: dict[str, Any] | None,
        updated_at: str,
        updated_by: str,
    ) -> dict[str, Any]:
        base = cls._default_extra(relation_id)
        if isinstance(existing, dict):
            base.update(deepcopy(existing))

        if "interest_rate_type" in payload:
            rate_type = cls._normalize_interest_rate_type(payload.get("interest_rate_type"))
        else:
            rate_type = str(base.get("interest_rate_type") or "none")

        if "interest_rate_value" in payload:
            rate_value = cls._normalize_decimal(payload.get("interest_rate_value"), field_name="interest_rate_value")
        else:
            rate_value = Decimal(str(base.get("interest_rate_value") or "0"))
        if rate_type == "none":
            rate_value = Decimal("0")

        if "interest_paid_amount" in payload:
            interest_paid_amount = cls._normalize_decimal(
                payload.get("interest_paid_amount"),
                field_name="interest_paid_amount",
            )
        else:
            interest_paid_amount = Decimal(str(base.get("interest_paid_amount") or "0"))

        if "interest_paid_date" in payload:
            interest_paid_date = cls._normalize_date(payload.get("interest_paid_date"))
        else:
            interest_paid_date = base.get("interest_paid_date")

        if "interest_payment_method" in payload:
            interest_payment_method = cls._normalize_text(
                payload.get("interest_payment_method"),
                field_name="interest_payment_method",
                max_length=MAX_PAYMENT_METHOD_LENGTH,
            )
        else:
            interest_payment_method = str(base.get("interest_payment_method") or "")

        if "note" in payload:
            note = cls._normalize_text(
                payload.get("note"),
                field_name="note",
                max_length=MAX_NOTE_LENGTH,
            )
        else:
            note = str(base.get("note") or "")

        return {
            "relation_id": relation_id,
            "interest_rate_type": rate_type,
            "interest_rate_value": cls._format_decimal(rate_value, RATE_QUANT),
            "interest_paid_amount": cls._format_decimal(interest_paid_amount, MONEY_QUANT),
            "interest_paid_date": interest_paid_date,
            "interest_payment_method": interest_payment_method,
            "note": note,
            "updated_at": updated_at,
            "updated_by": updated_by,
        }

    @staticmethod
    def _default_extra(relation_id: str) -> dict[str, Any]:
        return {
            "relation_id": relation_id,
            "interest_rate_type": "none",
            "interest_rate_value": "0.000000",
            "interest_paid_amount": "0.00",
            "interest_paid_date": None,
            "interest_payment_method": "",
            "note": "",
            "updated_at": "",
            "updated_by": "",
        }

    @staticmethod
    def _normalize_relation_id(relation_id: str) -> str:
        normalized = str(relation_id or "").strip()
        if not normalized:
            raise TurnoverLedgerExtraValidationError("relation_id is required.")
        return normalized

    @staticmethod
    def _normalize_actor(actor: str) -> str:
        normalized = TurnoverLedgerExtraService._normalize_text(
            actor,
            field_name="actor",
            max_length=MAX_PAYMENT_METHOD_LENGTH,
        )
        if not normalized:
            raise TurnoverLedgerExtraValidationError("actor is required.")
        return normalized

    @staticmethod
    def _normalize_interest_rate_type(value: object) -> str:
        normalized = str(value or "").strip().lower()
        if normalized not in TURNOVER_LEDGER_INTEREST_RATE_TYPES:
            raise TurnoverLedgerExtraValidationError("interest_rate_type must be annual, monthly, or none.")
        return normalized

    @staticmethod
    def _normalize_decimal(value: object, *, field_name: str) -> Decimal:
        if value is None or value == "":
            return Decimal("0")
        if isinstance(value, bool):
            raise TurnoverLedgerExtraValidationError(f"{field_name} must be a non-negative decimal.")
        try:
            decimal_value = Decimal(str(value).strip())
        except (InvalidOperation, ValueError):
            raise TurnoverLedgerExtraValidationError(f"{field_name} must be a non-negative decimal.") from None
        if not decimal_value.is_finite() or decimal_value < 0:
            raise TurnoverLedgerExtraValidationError(f"{field_name} must be a non-negative decimal.")
        return decimal_value

    @staticmethod
    def _format_decimal(value: Decimal, quant: Decimal) -> str:
        return str(value.quantize(quant, rounding=ROUND_HALF_UP))

    @staticmethod
    def _normalize_date(value: object) -> str | None:
        if value is None:
            return None
        normalized = str(value).strip()
        if not normalized:
            return None
        try:
            parsed = date.fromisoformat(normalized)
        except ValueError:
            raise TurnoverLedgerExtraValidationError("interest_paid_date must be an ISO date.") from None
        return parsed.isoformat()

    @staticmethod
    def _normalize_text(value: object, *, field_name: str, max_length: int) -> str:
        normalized = str(value or "").strip()
        if len(normalized) > max_length:
            raise TurnoverLedgerExtraValidationError(f"{field_name} is too long.")
        return normalized

    @staticmethod
    def _normalize_updated_at(value: object) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            return datetime.now(UTC).isoformat()
        try:
            datetime.fromisoformat(normalized)
        except ValueError:
            raise TurnoverLedgerExtraValidationError("updated_at must be an ISO datetime.") from None
        return normalized

    @classmethod
    def _next_updated_at(cls, existing: dict[str, Any] | None) -> str:
        now = datetime.now(UTC)
        if isinstance(existing, dict):
            previous_value = str(existing.get("updated_at") or "").strip()
            if previous_value:
                try:
                    previous = datetime.fromisoformat(previous_value)
                    if previous.tzinfo is None:
                        previous = previous.replace(tzinfo=UTC)
                    if now <= previous:
                        now = previous + timedelta(microseconds=1)
                except ValueError:
                    pass
        return now.isoformat()
