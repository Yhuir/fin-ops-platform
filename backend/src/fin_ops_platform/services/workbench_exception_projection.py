from __future__ import annotations

from copy import deepcopy
from typing import Any


EXCEPTION_PROJECTION_VERSION = "exception_projection_v1"

OPEN_CASE_STATUSES = {"open", "confirmed", "reopened", "legacy_confirmed"}
CLOSED_CASE_STATUSES = {"closed", "settled"}
IGNORED_CASE_STATUSES = {"ignored"}


class WorkbenchExceptionProjectionService:
    """Build display-only projections from exception case and pair relation facts."""

    projection_version = EXCEPTION_PROJECTION_VERSION

    def project_exception_case(
        self,
        case_payload: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        candidate_evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(case_payload, dict):
            raise ValueError("case_payload must be a dict.")

        normalized_case = self._case_summary(case_payload)
        row_overrides = {
            row_id: self._exception_case_row_override(
                row_id=row_id,
                case_summary=normalized_case,
                candidate_evidence=candidate_evidence,
            )
            for row_id in self._target_row_ids(case_payload, rows)
        }
        group_metadata = self._group_metadata_from_case(normalized_case, row_overrides)
        processed_summary = (
            self._processed_summary(normalized_case, relation_mode=normalized_case.get("relation_mode"))
            if normalized_case["status"] in CLOSED_CASE_STATUSES
            else None
        )
        return {
            "projection_version": EXCEPTION_PROJECTION_VERSION,
            "projection_kind": "exception_case",
            "case_id": normalized_case["case_id"],
            "exception_case_id": normalized_case["exception_case_id"],
            "row_overrides": row_overrides,
            "group_metadata": group_metadata,
            "processed_exception_summary": processed_summary,
        }

    def project_pair_relation(
        self,
        relation_payload: dict[str, Any],
        rows: list[dict[str, Any]],
        *,
        case_payload: dict[str, Any] | None = None,
        candidate_evidence: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(relation_payload, dict):
            raise ValueError("relation_payload must be a dict.")

        relation_summary = self._relation_summary(relation_payload, case_payload=case_payload)
        row_overrides = {
            row_id: self._pair_relation_row_override(
                row_id=row_id,
                relation_summary=relation_summary,
                candidate_evidence=candidate_evidence,
            )
            for row_id in self._target_row_ids(relation_payload, rows)
        }
        group_metadata = self._group_metadata_from_relation(relation_summary, row_overrides)
        processed_summary = self._processed_summary(
            relation_summary,
            relation_mode=relation_summary.get("relation_mode"),
        )
        return {
            "projection_version": EXCEPTION_PROJECTION_VERSION,
            "projection_kind": "pair_relation",
            "case_id": relation_summary["case_id"],
            "exception_case_id": relation_summary["exception_case_id"],
            "row_overrides": row_overrides,
            "group_metadata": group_metadata,
            "processed_exception_summary": processed_summary,
        }

    def _exception_case_row_override(
        self,
        *,
        row_id: str,
        case_summary: dict[str, Any],
        candidate_evidence: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        status = str(case_summary.get("status") or "open")
        ignored = status in IGNORED_CASE_STATUSES
        closed = status in CLOSED_CASE_STATUSES
        relation = (
            self._closed_relation_payload(case_summary.get("relation_mode"), case_summary.get("resolution_label"))
            if closed
            else self._ignored_relation_payload(case_summary.get("detail_note"))
            if ignored
            else self._open_relation_payload(case_summary)
        )
        override = self._base_row_override(
            projection_kind="exception_case",
            row_id=row_id,
            summary=case_summary,
            relation=relation,
            available_actions=self._case_available_actions(status),
            handled_exception=not ignored and not closed,
            candidate_evidence=candidate_evidence,
        )
        if not closed:
            override["auto_close_suppressed"] = True
        if ignored:
            override["ignored"] = True
        return override

    def _pair_relation_row_override(
        self,
        *,
        row_id: str,
        relation_summary: dict[str, Any],
        candidate_evidence: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        override = self._base_row_override(
            projection_kind="pair_relation",
            row_id=row_id,
            summary=relation_summary,
            relation=self._closed_relation_payload(relation_summary.get("relation_mode")),
            available_actions=["detail", "cancel_link", "reopen_exception"],
            handled_exception=False,
            candidate_evidence=candidate_evidence,
        )
        override["case_status"] = "closed"
        override["relation_status"] = str(relation_summary.get("relation_status") or "active")
        return override

    def _base_row_override(
        self,
        *,
        projection_kind: str,
        row_id: str,
        summary: dict[str, Any],
        relation: dict[str, str],
        available_actions: list[str],
        handled_exception: bool,
        candidate_evidence: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        display_tags = self._text_list(summary.get("display_tags"))
        override: dict[str, Any] = {
            "projection_version": EXCEPTION_PROJECTION_VERSION,
            "projection_kind": projection_kind,
            "case_id": summary["case_id"],
            "exception_case_id": summary["exception_case_id"],
            "case_status": summary["status"],
            "relation_status": summary.get("relation_status", ""),
            "relation_mode": summary.get("relation_mode", ""),
            "relation": relation,
            "available_actions": list(available_actions),
            "handled_exception": bool(handled_exception),
            "detail_note": summary.get("detail_note", ""),
            "scenario": deepcopy(summary.get("scenario") or {}),
            "resolution": deepcopy(summary.get("resolution") or {}),
            "amount_summary": deepcopy(summary.get("amount_summary") or {}),
            "display_tags": display_tags,
            "tags": display_tags,
            "audit_summary": deepcopy(summary.get("audit_summary") or {}),
            "source_versions": deepcopy(summary.get("source_versions") or {}),
            "candidate_ids": self._text_list(summary.get("candidate_ids")),
        }
        if isinstance(summary.get("oa_exemption"), dict):
            override["oa_exemption"] = deepcopy(summary["oa_exemption"])
        if candidate_evidence:
            override["candidate_evidence"] = deepcopy(candidate_evidence)
        return override

    def _case_summary(self, case_payload: dict[str, Any]) -> dict[str, Any]:
        case_id = self._first_text(case_payload.get("id"), case_payload.get("case_id"))
        if not case_id:
            raise ValueError("case payload requires id or case_id.")

        status = self._case_status(case_payload)
        resolution = self._resolution_summary(case_payload.get("resolution"), fallback=case_payload)
        scenario_code = self._first_text(
            case_payload.get("scenario_code"),
            case_payload.get("exception_code"),
            resolution.get("action_code"),
        )
        scenario_label = self._first_text(
            case_payload.get("scenario_label"),
            case_payload.get("exception_label"),
            scenario_code,
        )
        relation_mode = self._first_text(
            resolution.get("relation_mode"),
            case_payload.get("relation_mode"),
            case_payload.get("workflow_projection", {}).get("relation_mode")
            if isinstance(case_payload.get("workflow_projection"), dict)
            else None,
        )
        detail_note = self._first_text(
            case_payload.get("detail_note"),
            case_payload.get("comment"),
            case_payload.get("note"),
            resolution.get("note"),
            resolution.get("action_label"),
            scenario_label,
        )
        display_tags = self._merge_text_lists(
            case_payload.get("display_tags"),
            resolution.get("display_tags"),
        )
        source_versions = self._source_versions(case_payload)
        if case_payload.get("rule_version"):
            source_versions["exception_rules_version"] = str(case_payload.get("rule_version"))
        source_versions["exception_projection_version"] = EXCEPTION_PROJECTION_VERSION

        return {
            "case_id": case_id,
            "exception_case_id": self._first_text(case_payload.get("exception_case_id"), case_id),
            "status": status,
            "business_line": self._first_text(case_payload.get("business_line")),
            "scenario": {
                "business_line": self._first_text(case_payload.get("business_line")),
                "code": scenario_code,
                "label": scenario_label,
                "rule_version": self._first_text(case_payload.get("rule_version")),
            },
            "resolution": resolution,
            "resolution_label": self._first_text(resolution.get("action_label"), resolution.get("label")),
            "relation_mode": relation_mode,
            "amount_summary": deepcopy(case_payload.get("amount_summary") if isinstance(case_payload.get("amount_summary"), dict) else {}),
            "display_tags": display_tags,
            "audit_summary": self._audit_summary(case_payload),
            "source_versions": source_versions,
            "candidate_ids": self._text_list(case_payload.get("candidate_ids")),
            "detail_note": detail_note,
        }

    def _relation_summary(
        self,
        relation_payload: dict[str, Any],
        *,
        case_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        case_id = self._first_text(
            relation_payload.get("exception_case_id"),
            relation_payload.get("case_id"),
            case_payload.get("id") if isinstance(case_payload, dict) else None,
        )
        if not case_id:
            raise ValueError("relation payload requires case_id or exception_case_id.")

        relation_mode = self._first_text(relation_payload.get("relation_mode"), "manual_confirmed")
        case_summary = self._case_summary(case_payload) if isinstance(case_payload, dict) else {}
        display_tags = self._merge_text_lists(
            case_summary.get("display_tags"),
            relation_payload.get("display_tags"),
            relation_payload.get("special_metadata", {}).get("display_tags")
            if isinstance(relation_payload.get("special_metadata"), dict)
            else None,
            [relation_payload.get("oa_exemption", {}).get("reason_label")]
            if isinstance(relation_payload.get("oa_exemption"), dict)
            else None,
        )
        if isinstance(case_summary.get("amount_summary"), dict) and case_summary["amount_summary"]:
            amount_summary = deepcopy(case_summary["amount_summary"])
        elif isinstance(relation_payload.get("amount_summary"), dict):
            amount_summary = deepcopy(relation_payload["amount_summary"])
        elif isinstance(relation_payload.get("amount_check"), dict):
            amount_summary = deepcopy(relation_payload["amount_check"])
        else:
            amount_summary = {}
        source_versions = self._source_versions(relation_payload)
        if isinstance(case_summary.get("source_versions"), dict):
            source_versions = {**case_summary["source_versions"], **source_versions}
        source_versions["exception_projection_version"] = EXCEPTION_PROJECTION_VERSION

        return {
            "case_id": case_id,
            "exception_case_id": self._first_text(relation_payload.get("exception_case_id"), case_id),
            "status": "closed",
            "relation_status": self._first_text(relation_payload.get("status"), "active"),
            "business_line": case_summary.get("business_line", ""),
            "scenario": deepcopy(case_summary.get("scenario") or {}),
            "resolution": {
                **deepcopy(case_summary.get("resolution") or {}),
                "relation_mode": relation_mode,
            },
            "resolution_label": self._first_text(
                relation_payload.get("resolution_label"),
                relation_payload.get("note"),
                self._relation_mode_label(relation_mode),
            ),
            "relation_mode": relation_mode,
            "amount_summary": amount_summary,
            "display_tags": display_tags,
            "audit_summary": self._audit_summary(relation_payload),
            "source_versions": source_versions,
            "candidate_ids": self._text_list(relation_payload.get("candidate_ids")),
            "detail_note": self._first_text(
                relation_payload.get("detail_note"),
                relation_payload.get("note"),
                self._relation_mode_label(relation_mode),
            ),
            "oa_exemption": deepcopy(relation_payload.get("oa_exemption"))
            if isinstance(relation_payload.get("oa_exemption"), dict)
            else None,
        }

    @staticmethod
    def _target_row_ids(payload: dict[str, Any], rows: list[dict[str, Any]]) -> list[str]:
        row_ids = {
            str(row_id).strip()
            for row_id in list(payload.get("row_ids") or [])
            if str(row_id).strip()
        }
        if not row_ids:
            row_ids = {
                str(row.get("id") or row.get("row_id") or "").strip()
                for row in rows
                if isinstance(row, dict) and str(row.get("id") or row.get("row_id") or "").strip()
            }
        return [
            str(row.get("id") or row.get("row_id") or "").strip()
            for row in rows
            if isinstance(row, dict)
            and str(row.get("id") or row.get("row_id") or "").strip()
            and str(row.get("id") or row.get("row_id") or "").strip() in row_ids
        ]

    @staticmethod
    def _case_status(case_payload: dict[str, Any]) -> str:
        status = str(case_payload.get("status") or "").strip()
        if status:
            return status
        resolution = case_payload.get("resolution")
        if isinstance(resolution, dict) and str(resolution.get("result_status") or "").strip() == "closed":
            return "closed"
        return "open"

    def _resolution_summary(self, resolution: Any, *, fallback: dict[str, Any]) -> dict[str, Any]:
        if isinstance(resolution, dict):
            payload = deepcopy(resolution)
        else:
            payload = {}
        action_code = self._first_text(
            payload.get("action_code"),
            fallback.get("action_code"),
            fallback.get("exception_code"),
        )
        action_label = self._first_text(
            payload.get("action_label"),
            payload.get("label"),
            fallback.get("action_label"),
            fallback.get("exception_label"),
            action_code,
        )
        if action_code:
            payload["action_code"] = action_code
        if action_label:
            payload["action_label"] = action_label
        return payload

    @staticmethod
    def _open_relation_payload(case_summary: dict[str, Any]) -> dict[str, str]:
        resolution = case_summary.get("resolution")
        action_code = ""
        action_label = ""
        if isinstance(resolution, dict):
            action_code = str(
                resolution.get("legacy_relation_code")
                or resolution.get("legacy_exception_code")
                or resolution.get("action_code")
                or ""
            ).strip()
            action_label = str(
                resolution.get("legacy_relation_label")
                or resolution.get("legacy_exception_label")
                or resolution.get("action_label")
                or resolution.get("label")
                or ""
            ).strip()
        code = action_code or str(case_summary.get("relation_mode") or "").strip() or "manual_review"
        label = action_label or str(case_summary.get("scenario", {}).get("label") or "").strip() or "待人工处理"
        return {"code": code, "label": label, "tone": "danger"}

    @staticmethod
    def _ignored_relation_payload(detail_note: Any) -> dict[str, str]:
        return {"code": "ignored", "label": str(detail_note or "已忽略"), "tone": "warn"}

    @classmethod
    def _closed_relation_payload(cls, relation_mode: Any, fallback_label: Any = None) -> dict[str, str]:
        mode = str(relation_mode or "").strip() or "manual_confirmed"
        return {
            "code": mode,
            "label": cls._relation_mode_label(mode, fallback_label=fallback_label),
            "tone": "success",
        }

    @staticmethod
    def _relation_mode_label(relation_mode: str, *, fallback_label: Any = None) -> str:
        if fallback_label:
            return f"已处理：{fallback_label}"
        labels = {
            "expense_closed": "已处理：支出闭环",
            "income_closed": "已处理：收入闭环",
            "oa_exempt": "已处理：免 OA",
            "internal_transfer": "已处理：内部转账",
            "internal_transfer_pair": "已匹配：内部往来款",
            "salary": "已匹配：工资",
            "salary_personal_auto_match": "已匹配：工资",
            "etc_batch": "已处理：ETC 批次",
            "etc_batch_invoice_link": "已处理：ETC 批次",
            "personal_advance_repayment_settlement": "已匹配：还清个人暂借款",
            "no_invoice_income": "已处理：无需开票收入",
            "output_invoice_void_or_red": "已处理：销项票作废或红冲",
            "manual_confirmed": "完全关联",
        }
        return labels.get(relation_mode, "已处理")

    @staticmethod
    def _case_available_actions(status: str) -> list[str]:
        if status in IGNORED_CASE_STATUSES:
            return ["detail", "unignore"]
        if status in CLOSED_CASE_STATUSES:
            return ["detail", "reopen_exception"]
        return ["detail", "cancel_exception"]

    @staticmethod
    def _group_metadata_from_case(
        case_summary: dict[str, Any],
        row_overrides: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        status = str(case_summary.get("status") or "")
        if status in IGNORED_CASE_STATUSES:
            group_type = "ignored"
        elif status in CLOSED_CASE_STATUSES:
            group_type = "processed_exception"
        else:
            group_type = "open_exception"
        return {
            "group_id": f"case:{case_summary['case_id']}",
            "group_type": group_type,
            "case_id": case_summary["case_id"],
            "exception_case_id": case_summary["exception_case_id"],
            "status": status,
            "row_ids": list(row_overrides.keys()),
            "scenario": deepcopy(case_summary.get("scenario") or {}),
            "resolution": deepcopy(case_summary.get("resolution") or {}),
            "display_tags": deepcopy(case_summary.get("display_tags") or []),
            "audit_summary": deepcopy(case_summary.get("audit_summary") or {}),
            "amount_summary": deepcopy(case_summary.get("amount_summary") or {}),
        }

    @staticmethod
    def _group_metadata_from_relation(
        relation_summary: dict[str, Any],
        row_overrides: dict[str, dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "group_id": f"case:{relation_summary['case_id']}",
            "group_type": "processed_exception",
            "case_id": relation_summary["case_id"],
            "exception_case_id": relation_summary["exception_case_id"],
            "status": "closed",
            "relation_mode": relation_summary.get("relation_mode", ""),
            "row_ids": list(row_overrides.keys()),
            "scenario": deepcopy(relation_summary.get("scenario") or {}),
            "resolution": deepcopy(relation_summary.get("resolution") or {}),
            "display_tags": deepcopy(relation_summary.get("display_tags") or []),
            "audit_summary": deepcopy(relation_summary.get("audit_summary") or {}),
            "amount_summary": deepcopy(relation_summary.get("amount_summary") or {}),
        }

    @staticmethod
    def _processed_summary(summary: dict[str, Any], *, relation_mode: Any) -> dict[str, Any]:
        return {
            "case_id": summary["case_id"],
            "exception_case_id": summary["exception_case_id"],
            "scenario": deepcopy(summary.get("scenario") or {}),
            "resolution": deepcopy(summary.get("resolution") or {}),
            "business_line": summary.get("business_line", ""),
            "relation_mode": str(relation_mode or ""),
            "amount_summary": deepcopy(summary.get("amount_summary") or {}),
            "display_tags": deepcopy(summary.get("display_tags") or []),
            "audit_summary": deepcopy(summary.get("audit_summary") or {}),
            "available_actions": ["detail", "cancel_link", "reopen_exception"],
        }

    @staticmethod
    def _audit_summary(payload: dict[str, Any]) -> dict[str, Any]:
        audit = payload.get("audit")
        if isinstance(audit, dict):
            return deepcopy(audit)
        summary: dict[str, Any] = {}
        for key in ("created_by", "created_at", "updated_by", "updated_at"):
            if payload.get(key) not in (None, ""):
                summary[key] = payload.get(key)
        history = payload.get("history")
        if isinstance(history, list) and history:
            last_event = history[-1]
            if isinstance(last_event, dict):
                summary["last_event"] = deepcopy(last_event)
        return summary

    @staticmethod
    def _source_versions(payload: dict[str, Any]) -> dict[str, Any]:
        source_versions = payload.get("source_versions")
        return deepcopy(source_versions) if isinstance(source_versions, dict) else {}

    @classmethod
    def _merge_text_lists(cls, *values: Any) -> list[str]:
        merged: list[str] = []
        seen: set[str] = set()
        for value in values:
            for item in cls._text_list(value):
                if item in seen:
                    continue
                seen.add(item)
                merged.append(item)
        return merged

    @staticmethod
    def _text_list(value: Any) -> list[str]:
        if value in (None, ""):
            return []
        if isinstance(value, (list, tuple, set)):
            return [str(item).strip() for item in value if str(item).strip()]
        text = str(value).strip()
        return [text] if text else []

    @staticmethod
    def _first_text(*values: Any) -> str:
        for value in values:
            if value is None:
                continue
            text = str(value).strip()
            if text:
                return text
        return ""
