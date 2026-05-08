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

ACTIVE_CASE_STATUSES = {"confirmed", "ignored"}
CASE_STATUSES = ACTIVE_CASE_STATUSES | {"cancelled", "settled"}
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
        self._cases[case_id] = case_payload
        return deepcopy(case_payload)

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
        if status not in ACTIVE_CASE_STATUSES:
            for row_id in list(case_payload.get("row_ids") or []):
                if self._row_case_index.get(str(row_id)) == case_payload["id"]:
                    del self._row_case_index[str(row_id)]
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
            case_payload["exception_code"] = cls._normalize_exception_code(str(case_payload.get("exception_code") or ""))
            case_payload["exception_label"] = cls._non_empty_text(case_payload.get("exception_label"), "exception_label")
            case_payload["category"] = cls._non_empty_text(case_payload.get("category"), "category")
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
