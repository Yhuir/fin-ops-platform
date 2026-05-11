from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from itertools import count
from typing import Any


EXCEPTION_CASE_DEFINITIONS: dict[str, dict[str, str]] = {
    "oa_missing_bank": {
        "label": "OA缺流水",
        "category": "oa_bank",
    },
    "bank_missing_oa_fee": {
        "label": "费用类银行流水缺OA",
        "category": "bank",
    },
    "bank_missing_oa_loan": {
        "label": "借款类银行流水缺OA",
        "category": "bank",
    },
    "bank_missing_oa_interest": {
        "label": "利息类银行流水缺OA",
        "category": "bank",
    },
    "bank_missing_oa_misc": {
        "label": "其他银行流水缺OA",
        "category": "bank",
    },
    "bank_fee": {
        "label": "银行手续费",
        "category": "bank",
    },
    "oa_bank_amount_mismatch": {
        "label": "金额不一致，继续异常",
        "category": "oa_bank",
    },
    "oa_one_to_many_bank": {
        "label": "OA对应多笔银行流水",
        "category": "oa_bank",
    },
    "oa_many_to_one_bank": {
        "label": "多笔OA对应一笔银行流水",
        "category": "oa_bank",
    },
    "manual_review": {
        "label": "人工复核",
        "category": "manual",
    },
    "pending_collection": {
        "label": "待匹配流水",
        "category": "invoice",
    },
    "pending_match": {
        "label": "待找流水与发票",
        "category": "manual",
    },
    "personal_advance_repayment_settlement": {
        "label": "还清个人暂借款",
        "category": "oa_bank_settlement",
    },
}

ACTIVE_CASE_STATUSES = {"open", "ignored", "reopened", "legacy_confirmed", "confirmed"}
CASE_STATUSES = ACTIVE_CASE_STATUSES | {"closed", "cancelled", "settled"}
CASE_SCHEMA_VERSION = 2
ROW_TYPES = {"oa", "bank", "invoice"}


class WorkbenchExceptionCaseService:
    def __init__(
        self,
        *,
        cases: dict[str, dict[str, Any]] | None = None,
        row_case_index: dict[str, str] | None = None,
        case_counter: int = 0,
    ) -> None:
        self._cases = self._normalize_cases(cases or {})
        self._case_counter_value = max(int(case_counter), self._max_case_counter(self._cases))
        self._case_counter = count(self._case_counter_value + 1)
        self._row_case_index = self._normalize_row_case_index(row_case_index or {})
        if not self._row_case_index:
            self._row_case_index = self._build_row_case_index()

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchExceptionCaseService":
        if not snapshot:
            return cls()
        cases = snapshot.get("cases")
        row_case_index = snapshot.get("row_case_index")
        return cls(
            cases=cases if isinstance(cases, dict) else {},
            row_case_index=row_case_index if isinstance(row_case_index, dict) else {},
            case_counter=int(snapshot.get("case_counter", 0) or 0),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "case_counter": self._case_counter_value,
            "cases": deepcopy(self._cases),
            "row_case_index": deepcopy(self._row_case_index),
        }

    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, Any]:
        requested = {str(case_id) for case_id in case_ids if str(case_id).strip()}
        return {
            "case_counter": self._case_counter_value,
            "cases": {
                case_id: deepcopy(case_payload)
                for case_id, case_payload in self._cases.items()
                if case_id in requested
            },
            "row_case_index": {
                row_id: case_id
                for row_id, case_id in deepcopy(self._row_case_index).items()
                if case_id in requested
            },
        }

    def create_exception_case(
        self,
        rows: list[dict[str, Any]],
        exception_code: str,
        exception_label: str,
        category: str,
        comment: str | None = None,
        scope_months: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_rows = self._normalize_rows(rows)
        normalized_code = self._normalize_exception_code(exception_code)
        normalized_label = self._non_empty_text(exception_label, "exception_label")
        normalized_category = self._non_empty_text(category, "category")
        active_case_ids = self.case_ids_for_rows([row["id"] for row in normalized_rows])
        if active_case_ids:
            raise ValueError(f"rows already have active exception cases: {', '.join(active_case_ids)}")

        case_id = self._next_case_id()
        now = self._now()
        row_ids = [row["id"] for row in normalized_rows]
        case_payload = {
            "id": case_id,
            "status": "confirmed",
            "exception_code": normalized_code,
            "exception_label": normalized_label,
            "category": normalized_category,
            "row_ids": row_ids,
            "row_types": self._unique_preserve_order(row["type"] for row in normalized_rows),
            "scope_months": self._normalize_scope_months(scope_months, normalized_rows),
            "comment": comment,
            "created_at": now,
            "updated_at": now,
            "history": [
                {
                    "action": "created",
                    "at": now,
                    "comment": comment,
                }
            ],
        }
        self._ensure_v2_compat_fields(case_payload)
        self._cases[case_id] = case_payload
        for row_id in row_ids:
            self._row_case_index[row_id] = case_id
        return deepcopy(case_payload)

    def create_settlement_case(
        self,
        rows: list[dict[str, Any]],
        exception_code: str,
        exception_label: str,
        category: str,
        comment: str | None = None,
        scope_months: list[str] | None = None,
    ) -> dict[str, Any]:
        normalized_rows = self._normalize_rows(rows)
        normalized_code = self._normalize_exception_code(exception_code)
        normalized_label = self._non_empty_text(exception_label, "exception_label")
        normalized_category = self._non_empty_text(category, "category")

        case_id = self._next_case_id()
        now = self._now()
        row_ids = [row["id"] for row in normalized_rows]
        case_payload = {
            "id": case_id,
            "status": "settled",
            "exception_code": normalized_code,
            "exception_label": normalized_label,
            "category": normalized_category,
            "row_ids": row_ids,
            "row_types": self._unique_preserve_order(row["type"] for row in normalized_rows),
            "scope_months": self._normalize_scope_months(scope_months, normalized_rows),
            "comment": comment,
            "created_at": now,
            "updated_at": now,
            "history": [
                {
                    "action": "settled",
                    "at": now,
                    "comment": comment,
                }
            ],
        }
        self._ensure_v2_compat_fields(case_payload)
        self._cases[case_id] = case_payload
        return deepcopy(case_payload)

    def create_case_from_action(
        self,
        *,
        rows: list[dict[str, Any]],
        scenario: dict[str, Any],
        action: dict[str, Any],
        amount_summary: dict[str, Any],
        workflow_projection: dict[str, Any],
        actor: str,
        payload: dict[str, Any] | None = None,
        candidate_ids: list[str] | None = None,
        source_versions: dict[str, Any] | None = None,
        idempotency_key: str | None = None,
    ) -> dict[str, Any]:
        normalized_rows = self._normalize_rows(rows)
        resolved_idempotency_key = str(idempotency_key or "").strip()
        if resolved_idempotency_key:
            existing_case = self.find_case_by_idempotency_key(resolved_idempotency_key)
            if existing_case is not None:
                return existing_case

        result_status = str(action.get("result_status") or "").strip()
        status = result_status if result_status in {"open", "closed"} else "open"
        if status in ACTIVE_CASE_STATUSES:
            active_case_ids = self.case_ids_for_rows([row["id"] for row in normalized_rows])
            if active_case_ids:
                raise ValueError(f"rows already have active exception cases: {', '.join(active_case_ids)}")

        scenario_code = self._non_empty_text(scenario.get("scenario_code"), "scenario_code")
        scenario_label = self._non_empty_text(scenario.get("scenario_label") or scenario_code, "scenario_label")
        business_line = self._non_empty_text(scenario.get("business_line") or "manual", "business_line")
        rule_version = self._non_empty_text(scenario.get("rule_version") or "exception_rules_v1", "rule_version")
        action_code = self._non_empty_text(action.get("action_code"), "action_code")
        action_label = self._non_empty_text(action.get("label") or action_code, "action_label")
        now = self._now()
        row_ids = [row["id"] for row in normalized_rows]
        resolution_payload = deepcopy(payload if isinstance(payload, dict) else {})
        resolution = {
            "action_code": action_code,
            "action_label": action_label,
            "result_status": status,
            "relation_mode": str(action.get("relation_mode") or ""),
            **resolution_payload,
        }
        if "note" not in resolution:
            note = resolution_payload.get("note")
            resolution["note"] = str(note).strip() if note is not None else ""

        case_id = self._next_case_id()
        case_payload = {
            "id": case_id,
            "schema_version": CASE_SCHEMA_VERSION,
            "status": status,
            "business_line": business_line,
            "scenario_code": scenario_code,
            "scenario_label": scenario_label,
            "rule_version": rule_version,
            "row_ids": row_ids,
            "row_types": self._unique_preserve_order(row["type"] for row in normalized_rows),
            "scope_months": self._normalize_scope_months(None, normalized_rows),
            "amount_summary": deepcopy(amount_summary if isinstance(amount_summary, dict) else {}),
            "resolution": resolution,
            "workflow_projection": deepcopy(workflow_projection if isinstance(workflow_projection, dict) else {}),
            "audit": [
                {
                    "event": "created",
                    "actor": str(actor or "system"),
                    "at": now,
                    "payload": {
                        "scenario_code": scenario_code,
                        "action_code": action_code,
                    },
                }
            ],
            "candidate_ids": self._normalize_optional_text_list(candidate_ids),
            "source_versions": deepcopy(source_versions if isinstance(source_versions, dict) else {}),
            "idempotency_key": resolved_idempotency_key,
            "created_at": now,
            "updated_at": now,
            "exception_code": scenario_code,
            "exception_label": scenario_label,
            "category": business_line,
            "comment": resolution.get("note") or None,
            "history": [
                {
                    "action": "created",
                    "at": now,
                    "comment": resolution.get("note") or None,
                }
            ],
        }
        self._cases[case_id] = case_payload
        if status in ACTIVE_CASE_STATUSES:
            for row_id in row_ids:
                self._row_case_index[row_id] = case_id
        return deepcopy(case_payload)

    def get_case(self, case_id: str) -> dict[str, Any] | None:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            return None
        case_payload = self._cases.get(resolved_case_id)
        if not isinstance(case_payload, dict):
            return None
        return deepcopy(case_payload)

    def find_case_by_idempotency_key(self, idempotency_key: str) -> dict[str, Any] | None:
        resolved_key = str(idempotency_key or "").strip()
        if not resolved_key:
            return None
        for case_payload in self._cases.values():
            if str(case_payload.get("idempotency_key") or "").strip() == resolved_key:
                return deepcopy(case_payload)
        return None

    def preview_existing_case_conflicts(self, row_ids: list[str]) -> list[dict[str, Any]]:
        return [
            deepcopy(self._cases[case_id])
            for case_id in self.case_ids_for_rows(row_ids)
            if isinstance(self._cases.get(case_id), dict)
        ]

    def append_audit_event(
        self,
        case_id: str,
        *,
        event: str,
        actor: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        resolved_case_id = str(case_id or "").strip()
        case_payload = self._cases.get(resolved_case_id)
        if not isinstance(case_payload, dict):
            raise KeyError(resolved_case_id)
        audit = case_payload.setdefault("audit", [])
        if not isinstance(audit, list):
            audit = []
            case_payload["audit"] = audit
        audit.append(
            {
                "event": self._non_empty_text(event, "event"),
                "actor": str(actor or "system"),
                "at": self._now(),
                "payload": deepcopy(payload if isinstance(payload, dict) else {}),
            }
        )
        case_payload["updated_at"] = self._now()
        return deepcopy(case_payload)

    def close_case(
        self,
        case_id: str,
        *,
        resolution: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        case_payload = self._cases.get(str(case_id or "").strip())
        if not isinstance(case_payload, dict):
            raise KeyError(case_id)
        case_payload["resolution"] = deepcopy(resolution)
        return self._transition_case(case_payload, action="closed", status="closed", comment=str(resolution.get("note") or ""))

    def reopen_case(self, case_id: str, *, reason: str, actor: str) -> dict[str, Any]:
        case_payload = self._cases.get(str(case_id or "").strip())
        if not isinstance(case_payload, dict):
            raise KeyError(case_id)
        reopened = self._transition_case(case_payload, action="reopened", status="reopened", comment=reason)
        self.append_audit_event(str(case_id), event="reopened", actor=actor, payload={"reason": reason})
        return reopened

    def cancel_exception_cases(
        self,
        rows: list[dict[str, Any]],
        comment: str | None = None,
    ) -> list[dict[str, Any]]:
        row_ids = [row["id"] for row in self._normalize_rows(rows)]
        case_ids = self.case_ids_for_rows(row_ids)
        cancelled: list[dict[str, Any]] = []
        for case_id in case_ids:
            case_payload = self._cases.get(case_id)
            if not isinstance(case_payload, dict) or case_payload.get("status") not in ACTIVE_CASE_STATUSES:
                continue
            cancelled.append(self._transition_case(case_payload, action="cancelled", status="cancelled", comment=comment))
        return cancelled

    def ignore_row(self, row: dict[str, Any], comment: str | None = None) -> dict[str, Any]:
        normalized_rows = self._normalize_rows([row])
        normalized_row = normalized_rows[0]
        if normalized_row["type"] != "invoice":
            raise ValueError("ignore_row only supports invoice rows.")

        existing_case_ids = self.case_ids_for_rows([normalized_row["id"]])
        if existing_case_ids:
            existing_case = self._cases[existing_case_ids[0]]
            if existing_case.get("status") == "ignored":
                return deepcopy(existing_case)
            raise ValueError(f"row already has an active exception case: {existing_case_ids[0]}")

        definition = EXCEPTION_CASE_DEFINITIONS["pending_collection"]
        case_payload = self.create_exception_case(
            rows=[row],
            exception_code="pending_collection",
            exception_label=definition["label"],
            category=definition["category"],
            comment=comment,
        )
        stored_case = self._cases[case_payload["id"]]
        stored_case["status"] = "ignored"
        stored_case["history"][0]["action"] = "ignored"
        return deepcopy(stored_case)

    def unignore_row(self, row: dict[str, Any]) -> dict[str, Any] | None:
        normalized_row = self._normalize_rows([row])[0]
        case_ids = self.case_ids_for_rows([normalized_row["id"]])
        if not case_ids:
            return None
        case_payload = self._cases.get(case_ids[0])
        if not isinstance(case_payload, dict):
            return None
        if case_payload.get("status") != "ignored":
            raise ValueError(f"row is not ignored by exception case: {case_ids[0]}")
        return self._transition_case(case_payload, action="unignored", status="cancelled", comment=None)

    def case_ids_for_rows(self, row_ids: list[str]) -> list[str]:
        case_ids: list[str] = []
        seen: set[str] = set()
        for row_id in row_ids:
            case_id = self._row_case_index.get(str(row_id))
            if not case_id or case_id in seen:
                continue
            case_payload = self._cases.get(case_id)
            if not isinstance(case_payload, dict) or case_payload.get("status") not in ACTIVE_CASE_STATUSES:
                continue
            seen.add(case_id)
            case_ids.append(case_id)
        return case_ids

    def _transition_case(
        self,
        case_payload: dict[str, Any],
        *,
        action: str,
        status: str,
        comment: str | None,
    ) -> dict[str, Any]:
        if status not in CASE_STATUSES:
            raise ValueError(f"unsupported exception case status: {status}")
        now = self._now()
        case_payload["status"] = status
        case_payload["updated_at"] = now
        history = case_payload.setdefault("history", [])
        if not isinstance(history, list):
            history = []
            case_payload["history"] = history
        history.append({"action": action, "at": now, "comment": comment})
        audit = case_payload.setdefault("audit", [])
        if isinstance(audit, list):
            audit.append({"event": action, "actor": "system", "at": now, "payload": {"comment": comment}})
        if status not in ACTIVE_CASE_STATUSES:
            for row_id in list(case_payload.get("row_ids") or []):
                if self._row_case_index.get(str(row_id)) == case_payload["id"]:
                    del self._row_case_index[str(row_id)]
        else:
            for row_id in list(case_payload.get("row_ids") or []):
                resolved_row_id = str(row_id).strip()
                if resolved_row_id:
                    self._row_case_index[resolved_row_id] = str(case_payload["id"])
        return deepcopy(case_payload)

    def _next_case_id(self) -> str:
        self._case_counter_value = next(self._case_counter)
        return f"WEX-{self._case_counter_value:06d}"

    def _normalize_row_case_index(self, row_case_index: dict[str, Any]) -> dict[str, str]:
        normalized: dict[str, str] = {}
        for row_id, case_id in row_case_index.items():
            resolved_row_id = str(row_id).strip()
            resolved_case_id = str(case_id).strip()
            case_payload = self._cases.get(resolved_case_id)
            if not resolved_row_id or not isinstance(case_payload, dict):
                continue
            if case_payload.get("status") not in ACTIVE_CASE_STATUSES:
                continue
            if resolved_row_id not in set(case_payload.get("row_ids") or []):
                continue
            normalized[resolved_row_id] = resolved_case_id
        return normalized

    def _build_row_case_index(self) -> dict[str, str]:
        index: dict[str, str] = {}
        for case_id, case_payload in self._cases.items():
            if case_payload.get("status") not in ACTIVE_CASE_STATUSES:
                continue
            for row_id in case_payload.get("row_ids") or []:
                resolved_row_id = str(row_id).strip()
                if resolved_row_id:
                    index[resolved_row_id] = case_id
        return index

    @classmethod
    def _normalize_cases(cls, cases: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for fallback_case_id, raw_case in cases.items():
            if not isinstance(raw_case, dict):
                continue
            case_payload = deepcopy(raw_case)
            case_id = str(case_payload.get("id") or fallback_case_id).strip()
            if not case_id:
                continue
            case_payload["id"] = case_id
            status = str(case_payload.get("status") or "").strip()
            if status not in CASE_STATUSES:
                raise ValueError(f"unsupported exception case status: {status}")
            case_payload["status"] = status
            case_payload["exception_code"] = cls._normalize_case_code(case_payload)
            case_payload["exception_label"] = cls._non_empty_text(
                case_payload.get("exception_label") or case_payload.get("scenario_label"),
                "exception_label",
            )
            case_payload["category"] = cls._non_empty_text(
                case_payload.get("category") or case_payload.get("business_line") or "manual",
                "category",
            )
            row_ids = cls._normalize_text_list(case_payload.get("row_ids"), "row_ids")
            row_types = cls._normalize_row_types(case_payload.get("row_types"))
            case_payload["row_ids"] = row_ids
            case_payload["row_types"] = row_types
            case_payload["scope_months"] = cls._normalize_month_list(case_payload.get("scope_months"))
            case_payload["comment"] = case_payload.get("comment")
            case_payload["created_at"] = cls._non_empty_text(case_payload.get("created_at"), "created_at")
            case_payload["updated_at"] = cls._non_empty_text(case_payload.get("updated_at"), "updated_at")
            history = case_payload.get("history")
            case_payload["history"] = deepcopy(history) if isinstance(history, list) else []
            cls._ensure_v2_compat_fields(case_payload)
            normalized[case_id] = case_payload
        return normalized

    @staticmethod
    def _normalize_rows(rows: list[dict[str, Any]]) -> list[dict[str, str]]:
        if not isinstance(rows, list) or not rows:
            raise ValueError("rows must contain at least one row.")
        normalized: list[dict[str, str]] = []
        seen_row_ids: set[str] = set()
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("rows must contain dictionaries.")
            row_id = str(row.get("id") or "").strip()
            row_type = str(row.get("type") or "").strip()
            if not row_id:
                raise ValueError("row id is required.")
            if row_type not in ROW_TYPES:
                raise ValueError(f"unsupported row type: {row_type}")
            if row_id in seen_row_ids:
                raise ValueError(f"duplicate row id: {row_id}")
            seen_row_ids.add(row_id)
            normalized.append(
                {
                    "id": row_id,
                    "type": row_type,
                    "month": WorkbenchExceptionCaseService._month_from_row(row),
                }
            )
        return normalized

    @staticmethod
    def _normalize_exception_code(exception_code: str) -> str:
        normalized_code = str(exception_code or "").strip()
        if normalized_code not in EXCEPTION_CASE_DEFINITIONS:
            raise ValueError(f"unsupported exception code: {normalized_code}")
        return normalized_code

    @staticmethod
    def _normalize_case_code(case_payload: dict[str, Any]) -> str:
        normalized_code = str(case_payload.get("exception_code") or case_payload.get("scenario_code") or "").strip()
        if normalized_code in EXCEPTION_CASE_DEFINITIONS:
            return normalized_code
        if int(case_payload.get("schema_version") or 0) >= CASE_SCHEMA_VERSION or str(case_payload.get("scenario_code") or "").strip():
            if not normalized_code:
                raise ValueError("exception_code is required.")
            return normalized_code
        raise ValueError(f"unsupported exception code: {normalized_code}")

    @staticmethod
    def _normalize_scope_months(scope_months: list[str] | None, rows: list[dict[str, str]]) -> list[str]:
        if scope_months is not None:
            return WorkbenchExceptionCaseService._normalize_month_list(scope_months)
        return WorkbenchExceptionCaseService._normalize_month_list([row["month"] for row in rows if row.get("month")])

    @staticmethod
    def _normalize_month_list(values: Any) -> list[str]:
        if values in (None, ""):
            return []
        if not isinstance(values, list):
            raise ValueError("scope_months must be a list.")
        months = WorkbenchExceptionCaseService._unique_preserve_order(str(value).strip() for value in values if str(value).strip())
        for month in months:
            if len(month) != 7 or month[4] != "-":
                raise ValueError(f"invalid scope month: {month}")
        return months

    @staticmethod
    def _normalize_text_list(values: Any, field_name: str) -> list[str]:
        if not isinstance(values, list):
            raise ValueError(f"{field_name} must be a list.")
        normalized = WorkbenchExceptionCaseService._unique_preserve_order(str(value).strip() for value in values if str(value).strip())
        if not normalized:
            raise ValueError(f"{field_name} must not be empty.")
        return normalized

    @staticmethod
    def _normalize_optional_text_list(values: Any) -> list[str]:
        if not isinstance(values, list):
            return []
        return WorkbenchExceptionCaseService._unique_preserve_order(
            str(value).strip() for value in values if str(value).strip()
        )

    @staticmethod
    def _normalize_row_types(values: Any) -> list[str]:
        row_types = WorkbenchExceptionCaseService._normalize_text_list(values, "row_types")
        unsupported = [row_type for row_type in row_types if row_type not in ROW_TYPES]
        if unsupported:
            raise ValueError(f"unsupported row type: {unsupported[0]}")
        return row_types

    @staticmethod
    def _non_empty_text(value: Any, field_name: str) -> str:
        normalized = str(value or "").strip()
        if not normalized:
            raise ValueError(f"{field_name} is required.")
        return normalized

    @staticmethod
    def _unique_preserve_order(values: Any) -> list[str]:
        result: list[str] = []
        seen: set[str] = set()
        for value in values:
            text = str(value).strip()
            if not text or text in seen:
                continue
            seen.add(text)
            result.append(text)
        return result

    @staticmethod
    def _month_from_row(row: dict[str, Any]) -> str:
        for field_name in ("month", "scope_month", "reconciliation_month", "accounting_month"):
            value = str(row.get(field_name) or "").strip()
            if len(value) >= 7:
                return value[:7]
        for field_name in ("pay_receive_time", "transaction_time", "date", "created_at"):
            value = str(row.get(field_name) or "").strip()
            if len(value) >= 7 and value[4:5] == "-":
                return value[:7]
        return ""

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @classmethod
    def _ensure_v2_compat_fields(cls, case_payload: dict[str, Any]) -> None:
        case_payload["schema_version"] = int(case_payload.get("schema_version") or CASE_SCHEMA_VERSION)
        status = str(case_payload.get("status") or "")
        exception_code = str(case_payload.get("exception_code") or case_payload.get("scenario_code") or "")
        exception_label = str(case_payload.get("exception_label") or case_payload.get("scenario_label") or exception_code)
        category = str(case_payload.get("category") or case_payload.get("business_line") or "manual")
        business_line = str(case_payload.get("business_line") or cls._business_line_for_category(category))
        case_payload["business_line"] = business_line
        case_payload["scenario_code"] = str(case_payload.get("scenario_code") or exception_code)
        case_payload["scenario_label"] = str(case_payload.get("scenario_label") or exception_label)
        case_payload["rule_version"] = str(case_payload.get("rule_version") or "legacy")
        amount_summary = case_payload.get("amount_summary")
        case_payload["amount_summary"] = deepcopy(amount_summary) if isinstance(amount_summary, dict) else {}
        resolution = case_payload.get("resolution")
        if not isinstance(resolution, dict):
            action_code = "legacy_settled" if status == "settled" else "legacy_confirmed"
            resolution = {
                "action_code": action_code,
                "action_label": exception_label,
                "result_status": "closed" if status in {"settled", "closed"} else "open",
                "relation_mode": category,
                "note": case_payload.get("comment") or "",
            }
        case_payload["resolution"] = deepcopy(resolution)
        workflow_projection = case_payload.get("workflow_projection")
        if not isinstance(workflow_projection, dict):
            workflow_projection = {
                "state": cls._workflow_state_for_status(status),
                "allowed_next_events": ["CANCEL"] if status in ACTIVE_CASE_STATUSES else ["REOPEN"],
                "assignee": None,
                "due_at": None,
            }
        case_payload["workflow_projection"] = deepcopy(workflow_projection)
        audit = case_payload.get("audit")
        if not isinstance(audit, list):
            audit = []
            for history in list(case_payload.get("history") or []):
                if not isinstance(history, dict):
                    continue
                audit.append(
                    {
                        "event": str(history.get("action") or "legacy_event"),
                        "actor": "system",
                        "at": str(history.get("at") or case_payload.get("updated_at") or cls._now()),
                        "payload": {"comment": history.get("comment")},
                    }
                )
            if not audit:
                audit.append(
                    {
                        "event": "created",
                        "actor": "system",
                        "at": str(case_payload.get("created_at") or cls._now()),
                        "payload": {},
                    }
                )
        case_payload["audit"] = deepcopy(audit)
        case_payload["candidate_ids"] = cls._normalize_optional_text_list(case_payload.get("candidate_ids"))
        source_versions = case_payload.get("source_versions")
        case_payload["source_versions"] = deepcopy(source_versions) if isinstance(source_versions, dict) else {}

    @staticmethod
    def _business_line_for_category(category: str) -> str:
        if category == "invoice":
            return "income"
        if category in {"bank", "oa_bank", "oa_bank_settlement"}:
            return "expense"
        return str(category or "manual")

    @staticmethod
    def _workflow_state_for_status(status: str) -> str:
        if status == "closed":
            return "CLOSED"
        if status == "settled":
            return "LEGACY_SETTLED"
        if status == "ignored":
            return "IGNORED"
        if status == "cancelled":
            return "CANCELLED"
        if status == "reopened":
            return "REOPENED"
        return "LEGACY_CONFIRMED" if status == "confirmed" else str(status or "OPEN").upper()

    @staticmethod
    def _max_case_counter(cases: dict[str, dict[str, Any]]) -> int:
        max_counter = 0
        for case_id in cases:
            if not case_id.startswith("WEX-"):
                continue
            suffix = case_id.removeprefix("WEX-")
            if suffix.isdigit():
                max_counter = max(max_counter, int(suffix))
        return max_counter
