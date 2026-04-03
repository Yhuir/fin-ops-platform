from __future__ import annotations

from copy import deepcopy
from itertools import count
from typing import Any


class WorkbenchOverrideService:
    def __init__(
        self,
        *,
        row_overrides: dict[str, dict[str, Any]] | None = None,
        case_counter: int = 0,
    ) -> None:
        self._row_overrides = deepcopy(row_overrides or {})
        self._case_counter_value = max(case_counter, 0)
        self._case_counter = count(self._case_counter_value + 1)

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchOverrideService":
        if not snapshot:
            return cls()
        row_overrides = snapshot.get("row_overrides")
        normalized_row_overrides = cls._normalize_row_overrides(
            row_overrides if isinstance(row_overrides, dict) else {},
        )
        return cls(
            row_overrides=normalized_row_overrides,
            case_counter=int(snapshot.get("case_counter", 0)),
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "case_counter": self._case_counter_value,
            "row_overrides": deepcopy(self._row_overrides),
        }

    def apply_to_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        for section in ("paired", "open"):
            section_payload = result.get(section)
            if not isinstance(section_payload, dict):
                continue
            for row_type in ("oa", "bank", "invoice"):
                rows = section_payload.get(row_type)
                if not isinstance(rows, list):
                    continue
                section_payload[row_type] = [self.apply_to_row(row) for row in rows]
        return result

    def apply_to_row(self, row: dict[str, Any]) -> dict[str, Any]:
        payload = deepcopy(row)
        override = self._row_overrides.get(str(payload.get("id")))
        if not isinstance(override, dict):
            return payload

        if "ignored" in override:
            payload["ignored"] = bool(override.get("ignored"))

        if "case_id" in override:
            payload["case_id"] = override.get("case_id")

        relation = override.get("relation")
        if isinstance(relation, dict):
            relation_field = self.relation_field_name(str(payload["type"]))
            payload[relation_field] = deepcopy(relation)
            self._sync_summary_relation(payload, str(relation.get("label", "")))

        if "available_actions" in override:
            payload["available_actions"] = list(override.get("available_actions") or [])

        if "handled_exception" in override:
            payload["handled_exception"] = bool(override.get("handled_exception"))

        detail_note = override.get("detail_note")
        if isinstance(detail_note, str) and detail_note.strip():
            self._sync_detail_note(payload, detail_note)

        return payload

    def confirm_link(self, *, rows: list[dict[str, Any]], case_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        resolved_case_id = case_id or self._first_case_id(rows) or self._next_case_id()
        for row in rows:
            self._row_overrides[str(row["id"])] = {
                "case_id": resolved_case_id,
                "relation": self.linked_relation(),
                "available_actions": ["detail"],
                "handled_exception": False,
            }
        return resolved_case_id, [self.apply_to_row(row) for row in rows]

    def cancel_link(self, *, rows: list[dict[str, Any]], comment: str | None = None) -> list[dict[str, Any]]:
        updated_rows: list[dict[str, Any]] = []
        for row in rows:
            pending = self.pending_relation(str(row["type"]))
            if comment:
                pending = {**pending, "label": "取消关联，待重新处理"}
            self._row_overrides[str(row["id"])] = {
                "case_id": None,
                "relation": pending,
                "available_actions": self.available_actions(str(row["type"]), "open"),
                "detail_note": comment or "已取消关联",
                "handled_exception": False,
            }
            updated_rows.append(self.apply_to_row(row))
        return updated_rows

    def mark_exception(
        self,
        *,
        row: dict[str, Any],
        exception_code: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        self._row_overrides[str(row["id"])] = {
            "case_id": None,
            "relation": {
                "code": exception_code,
                "label": comment or "待人工处理",
                "tone": "danger",
            },
            "available_actions": self.available_actions(str(row["type"]), "open"),
            "detail_note": comment or exception_code,
            "handled_exception": True,
        }
        return self.apply_to_row(row)

    def update_bank_exception(
        self,
        *,
        row: dict[str, Any],
        relation_code: str,
        relation_label: str,
        comment: str | None = None,
    ) -> dict[str, Any]:
        self._row_overrides[str(row["id"])] = {
            "case_id": None,
            "relation": {
                "code": relation_code,
                "label": relation_label,
                "tone": "danger",
            },
            "available_actions": self.available_actions("bank", "open"),
            "detail_note": comment or relation_label,
            "handled_exception": True,
        }
        return self.apply_to_row(row)

    def apply_oa_bank_exception(
        self,
        *,
        rows: list[dict[str, Any]],
        exception_code: str,
        exception_label: str,
        comment: str | None = None,
    ) -> list[dict[str, Any]]:
        updated_rows: list[dict[str, Any]] = []
        detail_note = comment or exception_label
        for row in rows:
            row_type = str(row.get("type"))
            if row_type not in {"oa", "bank"}:
                raise ValueError("oa_bank_exception only supports oa and bank rows.")
            self._row_overrides[str(row["id"])] = {
                "case_id": None,
                "relation": {
                    "code": exception_code,
                    "label": exception_label,
                    "tone": "danger",
                },
                "available_actions": self.available_actions(row_type, "open"),
                "detail_note": detail_note,
                "handled_exception": True,
            }
            updated_rows.append(self.apply_to_row(row))
        return updated_rows

    def ignore_row(self, *, row: dict[str, Any], comment: str | None = None) -> dict[str, Any]:
        self._row_overrides[str(row["id"])] = {
            "case_id": None,
            "relation": self.pending_relation(str(row["type"])),
            "available_actions": ["detail"],
            "detail_note": comment or "已忽略",
            "ignored": True,
            "handled_exception": False,
        }
        return self.apply_to_row(row)

    def unignore_row(self, *, row: dict[str, Any]) -> dict[str, Any]:
        self._row_overrides[str(row["id"])] = {
            "case_id": None,
            "relation": self.pending_relation(str(row["type"])),
            "available_actions": self.available_actions(str(row["type"]), "open"),
            "detail_note": "已撤回忽略",
            "ignored": False,
            "handled_exception": False,
        }
        return self.apply_to_row(row)

    def cancel_exception(self, *, rows: list[dict[str, Any]], comment: str | None = None) -> list[dict[str, Any]]:
        updated_rows: list[dict[str, Any]] = []
        detail_note = comment or "已取消异常处理"
        for row in rows:
            row_type = str(row["type"])
            self._row_overrides[str(row["id"])] = {
                "case_id": None,
                "relation": self.pending_relation(row_type),
                "available_actions": self.available_actions(row_type, "open"),
                "detail_note": detail_note,
                "handled_exception": False,
                "ignored": False,
            }
            updated_rows.append(self.apply_to_row(row))
        return updated_rows

    @staticmethod
    def relation_field_name(row_type: str) -> str:
        return {
            "oa": "oa_bank_relation",
            "bank": "invoice_relation",
            "invoice": "invoice_bank_relation",
        }[row_type]

    @staticmethod
    def linked_relation() -> dict[str, str]:
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

    @staticmethod
    def pending_relation(row_type: str) -> dict[str, str]:
        if row_type == "oa":
            return {"code": "pending_match", "label": "待找流水与发票", "tone": "warn"}
        if row_type == "bank":
            return {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"}
        return {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"}

    @staticmethod
    def available_actions(row_type: str, section: str) -> list[str]:
        if row_type == "bank":
            return ["detail", "view_relation", "cancel_link", "handle_exception"]
        if row_type == "invoice" and section == "open":
            return ["detail", "confirm_link", "mark_exception", "ignore"]
        if section == "open":
            return ["detail", "confirm_link", "mark_exception"]
        return ["detail", "cancel_link"]

    def _next_case_id(self) -> str:
        self._case_counter_value = next(self._case_counter)
        return f"CASE-AUTO-{self._case_counter_value:04d}"

    @staticmethod
    def _first_case_id(rows: list[dict[str, Any]]) -> str | None:
        for row in rows:
            case_id = row.get("case_id")
            if case_id not in (None, ""):
                return str(case_id)
        return None

    @staticmethod
    def _sync_summary_relation(row: dict[str, Any], label: str) -> None:
        summary_fields = row.get("summary_fields")
        if not isinstance(summary_fields, dict):
            return
        if row["type"] == "oa":
            summary_fields["OA和流水关联情况"] = label
        elif row["type"] == "bank":
            summary_fields["和发票关联情况"] = label

    @staticmethod
    def _sync_detail_note(row: dict[str, Any], note: str) -> None:
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            detail_fields["备注"] = note

        summary_fields = row.get("summary_fields")
        if not isinstance(summary_fields, dict):
            return
        if "备注" in summary_fields:
            summary_fields["备注"] = note

    @staticmethod
    def _normalize_row_overrides(row_overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for row_id, raw_override in row_overrides.items():
            if not isinstance(raw_override, dict):
                continue
            override = deepcopy(raw_override)
            if "handled_exception" not in override:
                relation = override.get("relation")
                tone = relation.get("tone") if isinstance(relation, dict) else None
                ignored = bool(override.get("ignored"))
                override["handled_exception"] = bool(tone == "danger" and not ignored)
            normalized[str(row_id)] = override
        return normalized
