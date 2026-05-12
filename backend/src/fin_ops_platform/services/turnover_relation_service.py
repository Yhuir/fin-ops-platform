from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
from threading import RLock
from typing import Any


TURNOVER_RELATION_SCHEMA_VERSION = "2026-05-turnover-relation-v1"
TURNOVER_RELATION_STATUSES = {
    "suggested",
    "deterministic",
    "confirmed",
    "conflict",
    "stale",
    "withdrawn",
}
SYNCABLE_TURNOVER_RELATION_STATUSES = {"deterministic", "confirmed"}
LEGACY_TURNOVER_CATEGORY_CODES = {
    "external_turnover",
    "internal_transfer",
    "offset",
    "cash_turnover",
}
MONEY_QUANT = Decimal("0.01")
ZERO = Decimal("0.00")


class TurnoverRelationError(ValueError):
    def __init__(self, error_code: str, message: str) -> None:
        super().__init__(message)
        self.error_code = error_code


class TurnoverRelationValidationError(TurnoverRelationError):
    pass


@dataclass(frozen=True)
class _CategoryRule:
    category_code: str
    category_family: str
    business_type: str
    side: str
    expected_direction: str | None
    direction_semantics: str


@dataclass(frozen=True)
class _PreparedRow:
    row_id: str
    row: dict[str, Any]
    category_code: str
    category_family: str
    business_type: str
    side: str
    direction: str | None
    expected_direction: str | None
    direction_semantics: str
    amount: Decimal
    counterparty_name: str
    normalized_counterparty_name: str
    transaction_at: str | None


def _build_category_rules() -> dict[str, _CategoryRule]:
    rules: dict[str, _CategoryRule] = {}
    for family in ("personal", "company", "bank"):
        rules[f"borrow_in_{family}_pending_repayment"] = _CategoryRule(
            category_code=f"borrow_in_{family}_pending_repayment",
            category_family=family,
            business_type="borrow_in",
            side="principal",
            expected_direction="inflow",
            direction_semantics="borrow_in_principal",
        )
        rules[f"borrow_in_{family}_repaid"] = _CategoryRule(
            category_code=f"borrow_in_{family}_repaid",
            category_family=family,
            business_type="borrow_in",
            side="settlement",
            expected_direction="outflow",
            direction_semantics="borrow_in_repayment",
        )
    for family, code_family in (("personal", "personal"), ("company", "company"), ("business", "goods")):
        rules[f"borrow_out_{code_family}_lent"] = _CategoryRule(
            category_code=f"borrow_out_{code_family}_lent",
            category_family=family,
            business_type="borrow_out",
            side="principal",
            expected_direction="outflow",
            direction_semantics="borrow_out_principal",
        )
        rules[f"borrow_out_{code_family}_pending_collection"] = _CategoryRule(
            category_code=f"borrow_out_{code_family}_pending_collection",
            category_family=family,
            business_type="borrow_out",
            side="settlement",
            expected_direction="inflow",
            direction_semantics="borrow_out_collection",
        )
    for category_code in (
        "business_warranty_pending_collection",
        "business_bid_bond_pending_collection",
        "business_performance_bond_pending_collection",
        "business_invoiced_pending_collection",
    ):
        rules[category_code] = _CategoryRule(
            category_code=category_code,
            category_family="business",
            business_type="business_receivable",
            side="by_direction",
            expected_direction=None,
            direction_semantics="business_receivable",
        )
    return rules


TURNOVER_CATEGORY_RULES = _build_category_rules()


class TurnoverRelationService:
    def __init__(
        self,
        *,
        bank_rows: list[dict[str, Any]] | None = None,
        relations: list[dict[str, Any]] | None = None,
        audit_log: list[dict[str, Any]] | None = None,
    ) -> None:
        self._lock = RLock()
        self._bank_rows_by_id: dict[str, dict[str, Any]] = {}
        normalized_relations = [
            self._normalize_relation_snapshot(relation)
            for relation in list(relations or [])
            if isinstance(relation, dict)
        ]
        self._relations = self._degrade_invalid_snapshot_syncable_relations(normalized_relations)
        self._audit_log = [
            deepcopy(entry)
            for entry in list(audit_log or [])
            if isinstance(entry, dict)
        ]
        self._set_bank_rows(bank_rows or [])

    @classmethod
    def from_snapshot(
        cls,
        snapshot: dict[str, Any] | None,
        *,
        bank_rows: list[dict[str, Any]] | None = None,
    ) -> "TurnoverRelationService":
        if not snapshot:
            return cls(bank_rows=bank_rows)
        relations = snapshot.get("relations")
        audit_log = snapshot.get("audit_log")
        return cls(
            bank_rows=bank_rows,
            relations=relations if isinstance(relations, list) else [],
            audit_log=audit_log if isinstance(audit_log, list) else [],
        )

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {
                "schema_version": TURNOVER_RELATION_SCHEMA_VERSION,
                "relations": deepcopy(self._relations),
                "audit_log": deepcopy(self._audit_log),
            }

    def relations(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._relations)

    def audit_log(self) -> list[dict[str, Any]]:
        with self._lock:
            return deepcopy(self._audit_log)

    def rebuild_from_bank_rows(self, bank_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        with self._lock:
            self._set_bank_rows(bank_rows)
            prepared_rows: list[_PreparedRow] = []
            conflict_rows: list[_PreparedRow] = []
            for row in list(bank_rows or []):
                prepared = self._prepare_row(row, allow_invalid_direction=True)
                if prepared is None:
                    continue
                if not self._direction_is_valid(prepared):
                    conflict_rows.append(prepared)
                    continue
                prepared_rows.append(prepared)

            relations = [
                self._build_conflict_relation(prepared, reason="invalid_direction")
                for prepared in conflict_rows
            ]
            relations.extend(self._build_auto_relations(prepared_rows))
            manual_relations = [
                deepcopy(relation)
                for relation in self._relations
                if relation.get("source") == "manual"
                or relation.get("status") in {"confirmed", "withdrawn"}
            ]
            manual_syncable_row_ids = self._active_syncable_row_ids(manual_relations)
            if manual_syncable_row_ids:
                relations = [
                    relation
                    for relation in relations
                    if not manual_syncable_row_ids.intersection(
                        {str(row_id) for row_id in list(relation.get("bank_row_ids") or [])}
                    )
                ]
            self._relations = [*relations, *manual_relations]
            return deepcopy(self._relations)

    def confirm_relation(
        self,
        bank_row_ids: list[str],
        *,
        actor: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        normalized_actor = self._require_actor(actor)
        row_ids = self._normalize_row_ids(bank_row_ids)
        with self._lock:
            prepared_rows = [self._require_prepared_row(row_id) for row_id in row_ids]
            self._ensure_confirmable_relation(prepared_rows)
            self._ensure_no_active_syncable_overlap(row_ids)
            relation = self._build_relation_from_rows(
                prepared_rows,
                status="confirmed",
                source="manual",
                created_by=normalized_actor,
                evidence={
                    "matched_fields": ["category_code", "counterparty_name", "manual_selection"],
                    "manual_reason": "user_confirmed",
                    "note": note,
                },
            )
            self._relations = [
                existing_relation
                for existing_relation in self._relations
                if str(existing_relation.get("relation_id") or "") != str(relation["relation_id"])
            ]
            self._relations.append(relation)
            self._append_audit(
                relation_id=str(relation["relation_id"]),
                action="confirm_relation",
                old_status=None,
                new_status="confirmed",
                affected_row_ids=row_ids,
                actor=normalized_actor,
                note=note,
                version=int(relation["version"]),
            )
            return deepcopy(relation)

    def withdraw_relation(
        self,
        relation_id: str,
        *,
        actor: str,
        note: str | None = None,
    ) -> dict[str, Any]:
        normalized_actor = self._require_actor(actor)
        normalized_relation_id = str(relation_id or "").strip()
        if not normalized_relation_id:
            raise TurnoverRelationValidationError("invalid_relation_id", "relation_id is required.")
        timestamp = self._now()
        with self._lock:
            for relation in self._relations:
                if str(relation.get("relation_id") or "") != normalized_relation_id:
                    continue
                old_status = str(relation.get("status") or "")
                relation["status"] = "withdrawn"
                relation["sync_to_workbench"] = False
                relation["updated_by"] = normalized_actor
                relation["updated_at"] = timestamp
                relation["version"] = int(relation.get("version") or 0) + 1
                self._append_audit(
                    relation_id=normalized_relation_id,
                    action="withdraw_relation",
                    old_status=old_status,
                    new_status="withdrawn",
                    affected_row_ids=list(relation.get("bank_row_ids") or []),
                    actor=normalized_actor,
                    note=note,
                    version=int(relation["version"]),
                )
                return deepcopy(relation)
        raise TurnoverRelationValidationError(
            "unknown_relation_id",
            f"Unknown turnover relation id: {normalized_relation_id}",
        )

    def invalidate_for_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        actor: str = "system",
    ) -> list[dict[str, Any]]:
        normalized_actor = self._require_actor(actor)
        affected_ids = set(self._normalize_row_ids(transaction_ids))
        if not affected_ids:
            return []
        timestamp = self._now()
        updated: list[dict[str, Any]] = []
        with self._lock:
            for relation in self._relations:
                relation_row_ids = set(str(row_id) for row_id in list(relation.get("bank_row_ids") or []))
                if not relation_row_ids.intersection(affected_ids):
                    continue
                old_status = str(relation.get("status") or "")
                if old_status == "withdrawn":
                    continue
                relation["status"] = "conflict" if old_status == "confirmed" else "stale"
                relation["sync_to_workbench"] = False
                relation["updated_by"] = normalized_actor
                relation["updated_at"] = timestamp
                relation["version"] = int(relation.get("version") or 0) + 1
                relation.setdefault("evidence", {})
                if isinstance(relation["evidence"], dict):
                    relation["evidence"]["invalidated_by_transaction_ids"] = sorted(affected_ids)
                self._append_audit(
                    relation_id=str(relation.get("relation_id") or ""),
                    action="invalidate_relation",
                    old_status=old_status,
                    new_status=str(relation["status"]),
                    affected_row_ids=sorted(relation_row_ids.intersection(affected_ids)),
                    actor=normalized_actor,
                    note="bank transaction category changed",
                    version=int(relation["version"]),
                )
                updated.append(deepcopy(relation))
        return updated

    def _build_auto_relations(self, prepared_rows: list[_PreparedRow]) -> list[dict[str, Any]]:
        grouped: dict[tuple[str, str, str, str], list[_PreparedRow]] = {}
        for prepared in prepared_rows:
            grouped.setdefault(self._auto_group_key(prepared), []).append(prepared)

        relations: list[dict[str, Any]] = []
        for rows in grouped.values():
            principal_rows = [
                row
                for row in rows
                if self._resolved_side(row) == "principal"
            ]
            settlement_rows = [
                row
                for row in rows
                if self._resolved_side(row) == "settlement"
            ]
            if not principal_rows and not settlement_rows:
                continue
            principal_amount = sum((row.amount for row in principal_rows), ZERO)
            settled_amount = sum((row.amount for row in settlement_rows), ZERO)
            balance_amount = principal_amount - settled_amount
            reason = self._auto_confirm_reason(principal_rows, settlement_rows, balance_amount)
            status = "deterministic" if reason == "unique_exact_fifo_closed" else "suggested"
            relations.append(
                self._build_relation_from_rows(
                    [*principal_rows, *settlement_rows],
                    status=status,
                    source="system",
                    created_by="system",
                    evidence={
                        "matched_fields": ["category_code", "counterparty_name", "amount"],
                        "auto_confirm_reason": reason,
                    },
                )
            )
        return relations

    @staticmethod
    def _auto_confirm_reason(
        principal_rows: list[_PreparedRow],
        settlement_rows: list[_PreparedRow],
        balance_amount: Decimal,
    ) -> str:
        if balance_amount != ZERO:
            return "partial_closed"
        if len(principal_rows) >= 1 and len(settlement_rows) >= 1 and (
            len(principal_rows) == 1 or len(settlement_rows) == 1
        ):
            return "unique_exact_fifo_closed"
        return "multiple_solutions"

    @staticmethod
    def _auto_group_key(row: _PreparedRow) -> tuple[str, str, str, str]:
        business_discriminator = row.category_code if row.business_type == "business_receivable" else ""
        return (
            row.business_type,
            row.category_family,
            row.normalized_counterparty_name,
            business_discriminator,
        )

    def _build_relation_from_rows(
        self,
        rows: list[_PreparedRow],
        *,
        status: str,
        source: str,
        created_by: str,
        evidence: dict[str, Any],
    ) -> dict[str, Any]:
        if status not in TURNOVER_RELATION_STATUSES:
            raise TurnoverRelationValidationError("invalid_status", f"Unsupported relation status: {status}")
        if not rows:
            raise TurnoverRelationValidationError("empty_relation", "relation must contain at least one bank row.")
        self._ensure_relation_semantics(rows)

        principal_rows = [
            row for row in rows if self._resolved_side(row) == "principal"
        ]
        settlement_rows = [
            row for row in rows if self._resolved_side(row) == "settlement"
        ]
        principal_amount = sum((row.amount for row in principal_rows), ZERO)
        settled_amount = sum((row.amount for row in settlement_rows), ZERO)
        family = rows[0].category_family
        business_type = rows[0].business_type
        timestamp = self._now()
        bank_row_ids = [row.row_id for row in rows]
        relation_id = self._relation_id(
            status=status,
            source=source,
            row_ids=bank_row_ids,
        )
        relation = {
            "relation_id": relation_id,
            "status": status,
            "category_family": family,
            "business_type": business_type,
            "category_codes": sorted({row.category_code for row in rows}),
            "counterparty_name": rows[0].counterparty_name,
            "normalized_counterparty_name": rows[0].normalized_counterparty_name,
            "principal_row_ids": [row.row_id for row in principal_rows],
            "settlement_row_ids": [row.row_id for row in settlement_rows],
            "bank_row_ids": bank_row_ids,
            "principal_amount": self._format_money(principal_amount),
            "settled_amount": self._format_money(settled_amount),
            "balance_amount": self._format_money(principal_amount - settled_amount),
            "direction_semantics": self._direction_semantics(business_type),
            "first_transaction_at": self._first_transaction_at(rows),
            "last_settlement_at": self._last_settlement_at(settlement_rows),
            "source": source,
            "sync_to_workbench": status in SYNCABLE_TURNOVER_RELATION_STATUSES,
            "evidence": deepcopy(evidence),
            "version": 1,
            "created_by": created_by,
            "created_at": timestamp,
            "updated_by": created_by,
            "updated_at": timestamp,
        }
        if status not in SYNCABLE_TURNOVER_RELATION_STATUSES:
            relation["sync_to_workbench"] = False
        return relation

    def _build_conflict_relation(self, row: _PreparedRow, *, reason: str) -> dict[str, Any]:
        timestamp = self._now()
        return {
            "relation_id": self._relation_id(status="conflict", source="system", row_ids=[row.row_id]),
            "status": "conflict",
            "category_family": row.category_family,
            "business_type": row.business_type,
            "category_codes": [row.category_code],
            "counterparty_name": row.counterparty_name,
            "normalized_counterparty_name": row.normalized_counterparty_name,
            "principal_row_ids": [row.row_id] if row.side == "principal" else [],
            "settlement_row_ids": [row.row_id] if row.side == "settlement" else [],
            "bank_row_ids": [row.row_id],
            "principal_amount": self._format_money(row.amount if row.side == "principal" else ZERO),
            "settled_amount": self._format_money(row.amount if row.side == "settlement" else ZERO),
            "balance_amount": self._format_money(row.amount if row.side == "principal" else -row.amount),
            "direction_semantics": row.direction_semantics,
            "first_transaction_at": row.transaction_at,
            "last_settlement_at": row.transaction_at if row.side == "settlement" else None,
            "source": "system",
            "sync_to_workbench": False,
            "evidence": {
                "matched_fields": ["category_code"],
                "conflict_reason": reason,
                "expected_direction": row.expected_direction,
                "actual_direction": row.direction,
            },
            "version": 1,
            "created_by": "system",
            "created_at": timestamp,
            "updated_by": "system",
            "updated_at": timestamp,
        }

    def _ensure_relation_semantics(self, rows: list[_PreparedRow]) -> None:
        families = {row.category_family for row in rows}
        business_types = {row.business_type for row in rows}
        counterparties = {row.normalized_counterparty_name for row in rows}
        category_codes = {row.category_code for row in rows}
        if len(families) != 1:
            raise TurnoverRelationValidationError("category_family_conflict", "relation rows must share one category family.")
        if len(business_types) != 1:
            raise TurnoverRelationValidationError("business_type_conflict", "relation rows must share one business type.")
        if len(counterparties) != 1:
            raise TurnoverRelationValidationError("counterparty_conflict", "relation rows must share one counterparty.")
        if rows[0].business_type == "business_receivable" and len(category_codes) != 1:
            raise TurnoverRelationValidationError(
                "category_code_conflict",
                "business receivable relation rows must share one category code.",
            )
        for row in rows:
            if not self._direction_is_valid(row):
                raise TurnoverRelationValidationError("invalid_direction", "bank row direction conflicts with turnover category.")

    def _ensure_confirmable_relation(self, rows: list[_PreparedRow]) -> None:
        sides = {self._resolved_side(row) for row in rows}
        if "principal" not in sides or "settlement" not in sides:
            raise TurnoverRelationValidationError(
                "single_sided_relation",
                "confirmed turnover relation must contain principal and settlement rows.",
            )

    def _ensure_no_active_syncable_overlap(self, row_ids: list[str]) -> None:
        requested_row_ids = set(row_ids)
        for relation in self._relations:
            status = str(relation.get("status") or "")
            if status not in SYNCABLE_TURNOVER_RELATION_STATUSES:
                continue
            if not bool(relation.get("sync_to_workbench")):
                continue
            existing_row_ids = {
                str(row_id)
                for row_id in list(relation.get("bank_row_ids") or [])
                if str(row_id).strip()
            }
            overlap = sorted(requested_row_ids.intersection(existing_row_ids))
            if overlap:
                raise TurnoverRelationValidationError(
                    "relation_row_conflict",
                    f"Bank transaction already belongs to an active turnover relation: {', '.join(overlap)}",
                )

    @staticmethod
    def _active_syncable_row_ids(relations: list[dict[str, Any]]) -> set[str]:
        row_ids: set[str] = set()
        for relation in relations:
            status = str(relation.get("status") or "")
            if status not in SYNCABLE_TURNOVER_RELATION_STATUSES:
                continue
            if not bool(relation.get("sync_to_workbench")):
                continue
            row_ids.update(
                str(row_id)
                for row_id in list(relation.get("bank_row_ids") or [])
                if str(row_id).strip()
            )
        return row_ids

    def _prepare_row(
        self,
        row: dict[str, Any],
        *,
        allow_invalid_direction: bool,
    ) -> _PreparedRow | None:
        if not isinstance(row, dict):
            return None
        row_id = self._row_id(row)
        if not row_id:
            return None
        category_code = str(row.get("category_code") or "").strip()
        if category_code in LEGACY_TURNOVER_CATEGORY_CODES or not category_code:
            return None
        rule = TURNOVER_CATEGORY_RULES.get(category_code)
        if rule is None:
            return None
        debit = self._money_or_zero(row.get("debit_amount"))
        credit = self._money_or_zero(row.get("credit_amount"))
        direction = self._direction(debit, credit)
        amount = debit if direction == "outflow" else credit if direction == "inflow" else max(debit, credit)
        counterparty_name = str(row.get("counterparty_name") or row.get("counterparty") or "").strip()
        if not counterparty_name:
            counterparty_name = "UNKNOWN"
        side = rule.side
        expected_direction = rule.expected_direction
        if rule.side == "by_direction":
            if direction == "outflow":
                side = "principal"
            elif direction == "inflow":
                side = "settlement"
            elif not allow_invalid_direction:
                raise TurnoverRelationValidationError("invalid_direction", "business turnover rows require debit or credit amount.")
        prepared = _PreparedRow(
            row_id=row_id,
            row=deepcopy(row),
            category_code=category_code,
            category_family=rule.category_family,
            business_type=rule.business_type,
            side=side,
            direction=direction,
            expected_direction=expected_direction,
            direction_semantics=rule.direction_semantics,
            amount=amount,
            counterparty_name=counterparty_name,
            normalized_counterparty_name=self._normalize_counterparty_name(counterparty_name),
            transaction_at=self._transaction_at(row),
        )
        if not allow_invalid_direction and not self._direction_is_valid(prepared):
            raise TurnoverRelationValidationError("invalid_direction", "bank row direction conflicts with turnover category.")
        return prepared

    def _require_prepared_row(self, row_id: str) -> _PreparedRow:
        row = self._bank_rows_by_id.get(row_id)
        if row is None:
            raise TurnoverRelationValidationError("unknown_transaction_id", f"Unknown bank transaction id: {row_id}")
        prepared = self._prepare_row(row, allow_invalid_direction=False)
        if prepared is None:
            raise TurnoverRelationValidationError(
                "invalid_category_code",
                f"Bank transaction is not a supported turnover category: {row_id}",
            )
        return prepared

    @staticmethod
    def _resolved_side(row: _PreparedRow) -> str:
        return row.side

    @staticmethod
    def _direction_is_valid(row: _PreparedRow) -> bool:
        if row.expected_direction is None:
            return row.direction in {"inflow", "outflow"} and row.amount > ZERO
        return row.direction == row.expected_direction and row.amount > ZERO

    @staticmethod
    def _direction(debit: Decimal, credit: Decimal) -> str | None:
        if debit > ZERO and credit == ZERO:
            return "outflow"
        if credit > ZERO and debit == ZERO:
            return "inflow"
        return None

    @staticmethod
    def _money_or_zero(value: Any) -> Decimal:
        if value is None:
            return ZERO
        text = str(value).replace(",", "").strip()
        if not text:
            return ZERO
        try:
            amount = Decimal(text).quantize(MONEY_QUANT)
        except (InvalidOperation, ValueError):
            return ZERO
        return abs(amount)

    @staticmethod
    def _format_money(value: Decimal) -> str:
        return f"{value.quantize(MONEY_QUANT):.2f}"

    @staticmethod
    def _normalize_counterparty_name(value: str) -> str:
        return " ".join(str(value or "").strip().split())

    @staticmethod
    def _direction_semantics(business_type: str) -> str:
        if business_type == "borrow_in":
            return "borrow_in_repayment"
        if business_type == "borrow_out":
            return "borrow_out_collection"
        return "business_receivable_collection"

    @staticmethod
    def _transaction_at(row: dict[str, Any]) -> str | None:
        for key in ("transaction_at", "pay_receive_time", "transaction_time", "date", "business_date"):
            value = row.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return None

    @staticmethod
    def _first_transaction_at(rows: list[_PreparedRow]) -> str | None:
        values = sorted(row.transaction_at for row in rows if row.transaction_at)
        return values[0] if values else None

    @staticmethod
    def _last_settlement_at(rows: list[_PreparedRow]) -> str | None:
        values = sorted(row.transaction_at for row in rows if row.transaction_at)
        return values[-1] if values else None

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()

    def _set_bank_rows(self, bank_rows: list[dict[str, Any]]) -> None:
        self._bank_rows_by_id = {}
        for row in list(bank_rows or []):
            if not isinstance(row, dict):
                continue
            row_id = self._row_id(row)
            if row_id:
                self._bank_rows_by_id[row_id] = deepcopy(row)

    @staticmethod
    def _normalize_row_ids(row_ids: list[str]) -> list[str]:
        if not isinstance(row_ids, list) or not row_ids:
            raise TurnoverRelationValidationError("invalid_bank_row_ids", "bank_row_ids must be a non-empty list.")
        normalized = [str(row_id or "").strip() for row_id in row_ids if str(row_id or "").strip()]
        if not normalized:
            raise TurnoverRelationValidationError("invalid_bank_row_ids", "bank_row_ids must be a non-empty list.")
        if len(set(normalized)) != len(normalized):
            raise TurnoverRelationValidationError("invalid_bank_row_ids", "bank_row_ids must not contain duplicates.")
        return normalized

    @staticmethod
    def _require_actor(actor: str) -> str:
        normalized = str(actor or "").strip()
        if not normalized:
            raise TurnoverRelationValidationError("permission_denied", "actor is required.")
        return normalized

    @staticmethod
    def _relation_id(*, status: str, source: str, row_ids: list[str]) -> str:
        digest = sha1("|".join(sorted(row_ids)).encode("utf-8")).hexdigest()[:16]
        return f"turnover_rel_{digest}"

    @staticmethod
    def _normalize_relation_snapshot(relation: dict[str, Any]) -> dict[str, Any]:
        normalized = deepcopy(relation)
        status = str(normalized.get("status") or "").strip()
        if status not in TURNOVER_RELATION_STATUSES:
            status = "conflict"
            normalized["status"] = status
        if status not in SYNCABLE_TURNOVER_RELATION_STATUSES:
            normalized["sync_to_workbench"] = False
        elif "sync_to_workbench" not in normalized:
            normalized["sync_to_workbench"] = True
        else:
            normalized["sync_to_workbench"] = bool(normalized.get("sync_to_workbench"))
        row_ids = [
            str(row_id).strip()
            for row_id in list(normalized.get("bank_row_ids") or [])
            if str(row_id).strip()
        ]
        normalized["bank_row_ids"] = row_ids
        return normalized

    @classmethod
    def _degrade_invalid_snapshot_syncable_relations(
        cls,
        relations: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        seen_syncable_row_ids: set[str] = set()
        normalized_relations: list[dict[str, Any]] = []
        for relation in relations:
            normalized = deepcopy(relation)
            status = str(normalized.get("status") or "")
            if status not in SYNCABLE_TURNOVER_RELATION_STATUSES or not bool(normalized.get("sync_to_workbench")):
                normalized_relations.append(normalized)
                continue
            row_ids = {
                str(row_id).strip()
                for row_id in list(normalized.get("bank_row_ids") or [])
                if str(row_id).strip()
            }
            principal_row_ids = {
                str(row_id).strip()
                for row_id in list(normalized.get("principal_row_ids") or [])
                if str(row_id).strip()
            }
            settlement_row_ids = {
                str(row_id).strip()
                for row_id in list(normalized.get("settlement_row_ids") or [])
                if str(row_id).strip()
            }
            degrade_reason = ""
            if not principal_row_ids or not settlement_row_ids or not principal_row_ids.issubset(row_ids) or not settlement_row_ids.issubset(row_ids):
                degrade_reason = "malformed_syncable_relation"
            elif seen_syncable_row_ids.intersection(row_ids):
                degrade_reason = "active_syncable_overlap"

            if degrade_reason:
                cls._degrade_snapshot_relation(normalized, reason=degrade_reason)
            else:
                seen_syncable_row_ids.update(row_ids)
            normalized_relations.append(normalized)
        return normalized_relations

    @staticmethod
    def _degrade_snapshot_relation(relation: dict[str, Any], *, reason: str) -> None:
        relation["status"] = "conflict"
        relation["sync_to_workbench"] = False
        evidence = relation.get("evidence")
        if not isinstance(evidence, dict):
            evidence = {}
            relation["evidence"] = evidence
        evidence["snapshot_degraded_reason"] = reason

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    def _append_audit(
        self,
        *,
        relation_id: str,
        action: str,
        old_status: str | None,
        new_status: str,
        affected_row_ids: list[str],
        actor: str,
        note: str | None,
        version: int,
    ) -> None:
        self._audit_log.append(
            {
                "relation_id": relation_id,
                "action": action,
                "old_status": old_status,
                "new_status": new_status,
                "affected_row_ids": list(affected_row_ids),
                "actor": actor,
                "note": note,
                "created_at": self._now(),
                "version": version,
            }
        )
