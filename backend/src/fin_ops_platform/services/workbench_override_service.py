from __future__ import annotations

from copy import deepcopy
from itertools import count
from typing import Any

from fin_ops_platform.services.workbench_exception_projection import (
    EXCEPTION_PROJECTION_VERSION,
    WorkbenchExceptionProjectionService,
)
from fin_ops_platform.services.workbench_row_identity import (
    canonical_workbench_row_type,
    parse_workbench_row_identity_key,
    row_type_for_workbench_row_id,
    workbench_row_identity_key,
)


class WorkbenchOverrideService:
    def __init__(
        self,
        *,
        row_overrides: dict[str, dict[str, Any]] | None = None,
        case_counter: int = 0,
    ) -> None:
        self._row_overrides = self._normalize_row_overrides(row_overrides or {})
        self._case_counter_value = max(case_counter, 0)
        self._case_counter = count(self._case_counter_value + 1)
        self._projection_service = WorkbenchExceptionProjectionService()

    @property
    def projection_version(self) -> str:
        return EXCEPTION_PROJECTION_VERSION

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
            "projection_version": EXCEPTION_PROJECTION_VERSION,
            "row_overrides": deepcopy(self._row_overrides),
        }

    def case_id_for_row(self, row_id: str, *, row_type: str | None = None) -> str | None:
        normalized_id = str(row_id or "").strip()
        if not normalized_id:
            return None
        if row_type is not None:
            override = self._override_for_identity(row_type, normalized_id)
            case_id = override.get("case_id") if isinstance(override, dict) else None
            return str(case_id) if case_id not in (None, "") else None

        case_ids = {
            str(case_id)
            for key, override in self._row_overrides.items()
            if self._row_id_for_override(key, override) == normalized_id
            if (case_id := override.get("case_id")) not in (None, "")
        }
        return next(iter(case_ids)) if len(case_ids) == 1 else None

    def row_ids_for_case(self, case_id: str) -> list[str]:
        if not case_id:
            return []
        return [
            self._row_id_for_override(key, override)
            for key, override in self._row_overrides.items()
            if isinstance(override, dict) and override.get("case_id") == case_id
        ]

    def apply_to_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        result = deepcopy(payload)
        for section in ("paired", "unpaired"):
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
        if payload.get("type") == "oa":
            payload["available_actions"] = ["detail"]
        override = self._override_for_identity(
            payload.get("type") or payload.get("row_type"),
            payload.get("id") or payload.get("row_id"),
        )
        if not isinstance(override, dict):
            return payload

        if "ignored" in override:
            payload["ignored"] = bool(override.get("ignored"))

        if "case_id" in override:
            payload["case_id"] = override.get("case_id")

        if "exception_case_id" in override:
            payload["exception_case_id"] = override.get("exception_case_id")

        relation = override.get("relation")
        if isinstance(relation, dict):
            relation_field = self.relation_field_name(str(payload["type"]))
            payload[relation_field] = deepcopy(relation)
            self._sync_summary_relation(payload, str(relation.get("label", "")))

        if "available_actions" in override and payload.get("type") != "oa":
            payload["available_actions"] = list(override.get("available_actions") or [])

        if "handled_exception" in override:
            payload["handled_exception"] = bool(override.get("handled_exception"))

        if "auto_close_suppressed" in override:
            payload["auto_close_suppressed"] = bool(override.get("auto_close_suppressed"))

        for field_name in (
            "projection_version",
            "projection_kind",
            "case_status",
            "relation_status",
            "relation_mode",
            "scenario",
            "resolution",
            "amount_summary",
            "display_tags",
            "audit_summary",
            "source_versions",
            "candidate_ids",
            "candidate_evidence",
            "processed_exception_summary",
            "group_metadata",
            "oa_exemption",
        ):
            if field_name in override:
                payload[field_name] = deepcopy(override.get(field_name))

        if "tags" in override:
            payload["tags"] = self._merge_text_lists(payload.get("tags"), override.get("tags"))

        detail_note = override.get("detail_note")
        if isinstance(detail_note, str) and detail_note.strip():
            self._sync_detail_note(payload, detail_note)

        return payload

    def apply_relation_projection(
        self,
        relation_payload: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        case_payload: dict[str, Any] | None = None,
        candidate_evidence: list[dict[str, Any]] | None = None,
    ) -> list[dict[str, Any]]:
        projection = self._projection_service.project_pair_relation(
            relation_payload,
            rows,
            case_payload=case_payload,
            candidate_evidence=candidate_evidence,
        )
        self._apply_projection_overrides(projection, rows=rows)
        return [self.apply_to_row(row) for row in rows]

    def clear_projection_for_case(self, case_id: str) -> list[str]:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            return []
        cleared_row_ids: list[str] = []
        for key, override in list(self._row_overrides.items()):
            if not self._is_projection_override_for_case(override, resolved_case_id):
                continue
            del self._row_overrides[key]
            cleared_row_ids.append(self._row_id_for_override(key, override))
        return cleared_row_ids

    def clear_projection_for_relation(self, case_id: str) -> list[str]:
        resolved_case_id = str(case_id or "").strip()
        if not resolved_case_id:
            return []
        cleared_row_ids: list[str] = []
        for key, override in list(self._row_overrides.items()):
            if not self._is_projection_override_for_case(override, resolved_case_id):
                continue
            if str(override.get("projection_kind") or "") != "pair_relation":
                continue
            del self._row_overrides[key]
            cleared_row_ids.append(self._row_id_for_override(key, override))
        return cleared_row_ids

    def confirm_link(self, *, rows: list[dict[str, Any]], case_id: str | None = None) -> tuple[str, list[dict[str, Any]]]:
        resolved_case_id = case_id or self._first_case_id(rows) or self._next_case_id()
        for row in rows:
            self._set_override(row, {
                "case_id": resolved_case_id,
                "relation": self.linked_relation(),
                "available_actions": ["detail"],
                "handled_exception": False,
            })
        return resolved_case_id, [self.apply_to_row(row) for row in rows]

    def cancel_link(self, *, rows: list[dict[str, Any]], comment: str | None = None) -> list[dict[str, Any]]:
        updated_rows: list[dict[str, Any]] = []
        for row in rows:
            pending = self.pending_relation(str(row["type"]))
            if comment:
                pending = {**pending, "label": "取消关联，待重新处理"}
            self._set_override(row, {
                "case_id": None,
                "relation": pending,
                "available_actions": self.available_actions(str(row["type"]), "unpaired"),
                "detail_note": comment or "已取消关联",
                "auto_close_suppressed": True,
                "handled_exception": False,
            })
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
        if row_type == "oa":
            return ["detail"]
        if row_type == "bank":
            return ["detail", "view_relation", "cancel_link"]
        if row_type == "invoice" and section == "unpaired":
            return ["detail", "confirm_link"]
        return ["detail", "cancel_link"]

    def _next_case_id(self) -> str:
        self._case_counter_value = next(self._case_counter)
        return f"CASE-AUTO-{self._case_counter_value:04d}"

    def _apply_projection_overrides(
        self,
        projection: dict[str, Any],
        *,
        rows: list[dict[str, Any]],
    ) -> None:
        row_overrides = projection.get("row_overrides")
        if not isinstance(row_overrides, dict):
            return
        group_metadata = projection.get("group_metadata")
        processed_summary = projection.get("processed_exception_summary")
        for row in rows:
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            override = row_overrides.get(row_id)
            if not isinstance(override, dict):
                continue
            normalized_override = deepcopy(override)
            if isinstance(group_metadata, dict):
                normalized_override["group_metadata"] = deepcopy(group_metadata)
            if isinstance(processed_summary, dict):
                normalized_override["processed_exception_summary"] = deepcopy(processed_summary)
            self._set_override(row, normalized_override)

    @staticmethod
    def _is_projection_override_for_case(override: Any, case_id: str) -> bool:
        if not isinstance(override, dict):
            return False
        if override.get("projection_version") != EXCEPTION_PROJECTION_VERSION:
            return False
        return case_id in {
            str(override.get("case_id") or "").strip(),
            str(override.get("exception_case_id") or "").strip(),
        }

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
    def _merge_text_lists(*values: Any) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            items = value if isinstance(value, list) else [value]
            for item in items:
                text = str(item or "").strip()
                if not text or text in seen:
                    continue
                seen.add(text)
                merged.append(text)
        return merged

    def _set_override(
        self,
        row: dict[str, Any],
        override: dict[str, Any],
    ) -> None:
        row_type, row_id = self._identity_for_row(row)
        normalized_override = deepcopy(override)
        normalized_override["row_id"] = row_id
        normalized_override["row_type"] = row_type
        if not normalized_override.get("scope_month"):
            for field_name in (
                "scope_month",
                "month",
                "reconciliation_month",
                "accounting_month",
                "invoice_month",
                "txn_month",
            ):
                raw_month = str(row.get(field_name) or "").strip()
                if len(raw_month) >= 7 and raw_month[4:5] == "-":
                    normalized_override["scope_month"] = raw_month[:7]
                    break
        # A legacy raw-id entry is unsafe once a typed mutation exists because
        # it would otherwise be applied to every pane sharing the same id.
        self._row_overrides.pop(row_id, None)
        self._row_overrides[workbench_row_identity_key(row_type, row_id)] = normalized_override

    def _override_for_identity(
        self,
        row_type: object,
        row_id: object,
    ) -> dict[str, Any] | None:
        canonical_type = canonical_workbench_row_type(row_type, unknown="")
        normalized_id = str(row_id or "").strip()
        if not canonical_type or not normalized_id:
            return None
        override = self._row_overrides.get(
            workbench_row_identity_key(canonical_type, normalized_id)
        )
        return override if isinstance(override, dict) else None

    @staticmethod
    def _identity_for_row(row: dict[str, Any]) -> tuple[str, str]:
        row_type = canonical_workbench_row_type(
            row.get("type") or row.get("row_type"),
            unknown="",
        )
        row_id = str(row.get("id") or row.get("row_id") or "").strip()
        if not row_type or not row_id:
            raise ValueError("Workbench override requires a canonical typed row.")
        return row_type, row_id

    @staticmethod
    def _row_id_for_override(key: object, override: object) -> str:
        if isinstance(override, dict):
            row_id = str(override.get("row_id") or "").strip()
            if row_id:
                return row_id
        parsed = parse_workbench_row_identity_key(key)
        return parsed[1] if parsed is not None else str(key)

    @staticmethod
    def _normalize_row_overrides(row_overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for raw_key, raw_override in row_overrides.items():
            if not isinstance(raw_override, dict):
                continue
            override = deepcopy(raw_override)
            if "handled_exception" not in override:
                relation = override.get("relation")
                tone = relation.get("tone") if isinstance(relation, dict) else None
                ignored = bool(override.get("ignored"))
                override["handled_exception"] = bool(tone == "danger" and not ignored)
            parsed_identity = parse_workbench_row_identity_key(raw_key)
            payload_row_id = str(override.get("row_id") or "").strip()
            payload_row_type = canonical_workbench_row_type(
                override.get("row_type") or override.get("type"),
                unknown="",
            )
            if parsed_identity is not None:
                row_type, row_id = parsed_identity
                if payload_row_id and payload_row_id != row_id:
                    raise ValueError("Workbench override key and payload row ids do not match.")
                if payload_row_type and payload_row_type != row_type:
                    raise ValueError("Workbench override key and payload row types do not match.")
            elif payload_row_type:
                row_type = payload_row_type
                row_id = payload_row_id or str(raw_key).strip()
            else:
                row_id = payload_row_id or str(raw_key).strip()
                row_type = row_type_for_workbench_row_id(row_id, unknown="")
                if not row_type:
                    # Preserve ambiguous historical state for round-tripping,
                    # but never apply it across panes without a typed identity.
                    normalized[str(raw_key)] = override
                    continue
            override["row_id"] = row_id
            override["row_type"] = row_type
            normalized[workbench_row_identity_key(row_type, row_id)] = override
        return normalized
