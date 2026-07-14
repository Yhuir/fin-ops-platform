from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from typing import Any, Callable

from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_exception_classifier import WorkbenchExceptionClassifier
from fin_ops_platform.services.workbench_exception_rules import ACTION_DEFINITIONS, RULE_VERSION, action
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError


RowProvider = Callable[[str, list[str]], list[dict[str, Any]]]
SourceVersionsProvider = Callable[[], dict[str, Any]]
ExceptionEvidenceProvider = Callable[[str, list[str]], list[dict[str, Any]]]


class WorkbenchExceptionApplicationConflict(ValueError):
    def __init__(self, code: str, message: str, *, payload: dict[str, Any] | None = None) -> None:
        super().__init__(message)
        self.code = code
        self.payload = deepcopy(payload if isinstance(payload, dict) else {})


class WorkbenchExceptionApplicationService:
    def __init__(
        self,
        *,
        row_provider: RowProvider,
        case_service: WorkbenchExceptionCaseService,
        exception_evidence_provider: ExceptionEvidenceProvider | None = None,
        classifier: WorkbenchExceptionClassifier | None = None,
        source_versions_provider: SourceVersionsProvider | None = None,
        relation_command_service: Any | None = None,
    ) -> None:
        self._row_provider = row_provider
        self._case_service = case_service
        self._exception_evidence_provider = exception_evidence_provider
        self._classifier = classifier or WorkbenchExceptionClassifier()
        self._source_versions_provider = source_versions_provider or (lambda: {})
        self._relation_command_service = relation_command_service

    def preview(self, request: dict[str, Any]) -> dict[str, Any]:
        month, row_ids = self._request_month_and_row_ids(request)
        rows = self._resolve_rows(month, row_ids)
        candidate_evidence = self._candidate_evidence(month, row_ids)
        classification = self._classifier.preview(
            {
                "month": month,
                "selected_row_ids": row_ids,
                "rows": rows,
                "candidate_evidence": candidate_evidence,
            }
        )
        warnings = self._normalized_classifier_warnings(classification.get("warnings"))
        active_cases = self._case_service.preview_existing_case_conflicts(row_ids)
        active_relations = self._active_relations_for_row_ids(row_ids)
        if active_cases:
            warnings.append(
                self._warning(
                    "active_exception_case_conflict",
                    "Selected rows already have active exception cases.",
                    {"case_ids": [str(case.get("id") or "") for case in active_cases]},
                )
            )
        if active_relations:
            warnings.append(
                self._warning(
                    "active_pair_relation_conflict",
                    "Selected rows already have active pair relations.",
                    {"case_ids": [str(relation.get("case_id") or "") for relation in active_relations]},
                )
            )
        can_apply = not active_cases and not active_relations
        return self._preview_payload(
            classification=classification,
            warnings=warnings,
            candidate_evidence=candidate_evidence,
            can_apply=can_apply,
        )

    def apply(self, request: dict[str, Any], *, actor: str = "system") -> dict[str, Any]:
        month, row_ids = self._request_month_and_row_ids(request)
        scenario_code = str(request.get("scenario_code") or "").strip()
        action_code = str(request.get("action_code") or "").strip()
        if not scenario_code:
            raise ValueError("scenario_code is required.")
        if not action_code:
            raise ValueError("action_code is required.")
        idempotency_key = self._idempotency_key(month=month, row_ids=row_ids, scenario_code=scenario_code, action_code=action_code)
        existing_case = self._case_service.find_case_by_idempotency_key(idempotency_key)
        if existing_case is not None:
            relation = self._active_relation_by_case_id(str(existing_case.get("id") or ""))
            return self._apply_payload(
                case=existing_case,
                pair_relation=relation,
                row_ids=row_ids,
                updated_rows=[],
                idempotent=True,
            )

        preview = self.preview({"month": month, "row_ids": row_ids})
        self._raise_preview_conflict(preview)
        actual_scenario_code = str(preview["scenario"]["scenario_code"])
        if scenario_code != actual_scenario_code:
            raise ValueError(f"scenario_code does not match preview: {actual_scenario_code}")

        resolved_action = self._resolve_action(action_code, preview)
        payload = deepcopy(request.get("payload") if isinstance(request.get("payload"), dict) else {})
        resolution_payload = self._resolution_payload(
            action_code=action_code,
            action_payload=resolved_action,
            request_payload=payload,
            preview=preview,
            actor=actor,
        )
        action_for_case = {
            **deepcopy(resolved_action),
            "relation_mode": self._relation_mode_for_action(action_code, resolved_action, resolution_payload),
        }
        relation_command_service = None
        if str(action_for_case.get("result_status") or "") == "closed":
            relation_command_service = self._require_relation_command_service()
            preflight = getattr(relation_command_service, "assert_write_precondition", None)
            if callable(preflight):
                preflight(row_ids=row_ids, month_scope=month)
        case_payload = self._case_service.create_case_from_action(
            rows=self._resolve_rows(month, row_ids),
            scenario={
                **deepcopy(preview["scenario"]),
                "rule_version": str(preview.get("rule_version") or RULE_VERSION),
            },
            action=action_for_case,
            amount_summary=deepcopy(preview.get("amount_summary") or {}),
            workflow_projection=deepcopy(preview.get("workflow_projection") or {}),
            actor=actor,
            payload=resolution_payload,
            candidate_ids=[],
            source_versions=self._source_versions(str(preview.get("rule_version") or RULE_VERSION)),
            idempotency_key=idempotency_key,
        )

        pair_relation = None
        if str(case_payload.get("status") or "") == "closed":
            pair_relation = self._create_pair_relation(
                case_payload=case_payload,
                action_code=action_code,
                action_payload=action_for_case,
                resolution_payload=resolution_payload,
                row_ids=row_ids,
                month=month,
                actor=actor,
                relation_command_service=relation_command_service,
            )

        return self._apply_payload(
            case=case_payload,
            pair_relation=pair_relation,
            row_ids=row_ids,
            updated_rows=[],
            idempotent=False,
        )

    def _request_month_and_row_ids(self, request: dict[str, Any]) -> tuple[str, list[str]]:
        if not isinstance(request, dict):
            raise ValueError("request must be a dict.")
        month = str(request.get("month") or "").strip()
        if not month:
            raise ValueError("month is required.")
        raw_row_ids = request.get("row_ids")
        if raw_row_ids is None and request.get("row_id") is not None:
            raw_row_ids = [request.get("row_id")]
        row_ids = self._normalize_row_ids(list(raw_row_ids or []))
        return month, row_ids

    def _resolve_rows(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        rows = self._row_provider(month, row_ids)
        rows_by_id = {str(row.get("id") or ""): deepcopy(row) for row in rows if isinstance(row, dict)}
        missing = [row_id for row_id in row_ids if row_id not in rows_by_id]
        if missing:
            raise KeyError(missing[0])
        return [rows_by_id[row_id] for row_id in row_ids]

    def _candidate_evidence(self, month: str, row_ids: list[str]) -> list[dict[str, Any]]:
        if self._exception_evidence_provider is None:
            return []
        raw_evidence = self._exception_evidence_provider(month, list(row_ids))
        if not isinstance(raw_evidence, list):
            raise ValueError("exception_evidence_provider must return a list.")
        return [deepcopy(item) for item in raw_evidence if isinstance(item, dict)]

    @staticmethod
    def _preview_payload(
        *,
        classification: dict[str, Any],
        warnings: list[dict[str, Any]],
        candidate_evidence: list[dict[str, Any]],
        can_apply: bool,
    ) -> dict[str, Any]:
        return {
            "rule_version": str(classification.get("rule_version") or RULE_VERSION),
            "scenario": {
                "business_line": str(classification.get("business_line") or ""),
                "scenario_code": str(classification.get("scenario_code") or ""),
                "scenario_label": str(classification.get("scenario_label") or ""),
            },
            "amount_summary": deepcopy(classification.get("amount_summary") if isinstance(classification.get("amount_summary"), dict) else {}),
            "automatic_actions": deepcopy(classification.get("automatic_actions") if isinstance(classification.get("automatic_actions"), list) else []),
            "available_actions": deepcopy(classification.get("available_actions") if isinstance(classification.get("available_actions"), list) else []),
            "warnings": warnings,
            "workflow_projection": deepcopy(
                classification.get("workflow_projection") if isinstance(classification.get("workflow_projection"), dict) else {}
            ),
            "candidate_evidence": deepcopy(candidate_evidence),
            "can_apply": can_apply,
        }

    @staticmethod
    def _normalized_classifier_warnings(raw_warnings: Any) -> list[dict[str, Any]]:
        warnings: list[dict[str, Any]] = []
        for warning in list(raw_warnings or []):
            if isinstance(warning, dict):
                warnings.append(deepcopy(warning))
            else:
                warnings.append(WorkbenchExceptionApplicationService._warning("classifier_warning", str(warning)))
        return warnings

    @staticmethod
    def _warning(code: str, message: str, payload: dict[str, Any] | None = None) -> dict[str, Any]:
        warning = {"code": code, "message": message}
        if isinstance(payload, dict):
            warning["payload"] = deepcopy(payload)
        return warning

    @staticmethod
    def _raise_preview_conflict(preview: dict[str, Any]) -> None:
        if preview.get("can_apply"):
            return
        warnings = [warning for warning in list(preview.get("warnings") or []) if isinstance(warning, dict)]
        priority = ["active_pair_relation_conflict", "active_exception_case_conflict"]
        for code in priority:
            for warning in warnings:
                if warning.get("code") == code:
                    raise WorkbenchExceptionApplicationConflict(
                        code,
                        str(warning.get("message") or code),
                        payload=deepcopy(warning.get("payload") if isinstance(warning.get("payload"), dict) else {}),
                    )
        raise WorkbenchExceptionApplicationConflict("exception_apply_conflict", "Selected rows cannot be applied.")

    @staticmethod
    def _resolve_action(action_code: str, preview: dict[str, Any]) -> dict[str, Any]:
        for action_payload in [
            *list(preview.get("automatic_actions") or []),
            *list(preview.get("available_actions") or []),
        ]:
            if isinstance(action_payload, dict) and str(action_payload.get("action_code") or "") == action_code:
                return deepcopy(action_payload)
        if action_code in ACTION_DEFINITIONS:
            return action(action_code)
        raise ValueError(f"unsupported action_code: {action_code}")

    def _resolution_payload(
        self,
        *,
        action_code: str,
        action_payload: dict[str, Any],
        request_payload: dict[str, Any],
        preview: dict[str, Any],
        actor: str,
    ) -> dict[str, Any]:
        note = str(request_payload.get("note") or request_payload.get("comment") or "").strip()
        if action_code == "confirm_oa_exempt_auto":
            payload = deepcopy(action_payload.get("payload") if isinstance(action_payload.get("payload"), dict) else {})
            if not payload:
                payload = self._auto_oa_exemption_from_preview(preview)
            payload.setdefault("relation_mode", "oa_exempt")
            payload.setdefault("display_tags", ["自动免OA"])
            oa_exemption = payload.setdefault("oa_exemption", {})
            if isinstance(oa_exemption, dict):
                oa_exemption.setdefault("source", "auto")
                oa_exemption.setdefault("rule_version", str(preview.get("rule_version") or RULE_VERSION))
                oa_exemption.setdefault("confirmed_by", None)
                oa_exemption.setdefault("confirmed_at", None)
                oa_exemption.setdefault("note", None)
            return payload
        if action_code == "confirm_oa_exempt_manual":
            reason_code = str(request_payload.get("reason_code") or "manual_confirmed").strip()
            reason_label = str(request_payload.get("reason_label") or self._manual_reason_label(reason_code)).strip()
            confirmed_at = str(request_payload.get("confirmed_at") or self._now())
            return {
                "relation_mode": "oa_exempt",
                "oa_exemption": {
                    "source": "manual",
                    "reason_code": reason_code,
                    "reason_label": reason_label,
                    "rule_code": str(request_payload.get("rule_code") or "manual_oa_exempt"),
                    "rule_version": str(preview.get("rule_version") or RULE_VERSION),
                    "evidence": deepcopy(request_payload.get("evidence") if isinstance(request_payload.get("evidence"), dict) else {}),
                    "confirmed_by": str(request_payload.get("confirmed_by") or actor or "system"),
                    "confirmed_at": confirmed_at,
                    "note": note,
                },
                "display_tags": self._unique_tags(["人工免OA", reason_label]),
                "note": note,
            }
        resolved = deepcopy(request_payload)
        if note and "note" not in resolved:
            resolved["note"] = note
        return resolved

    @staticmethod
    def _manual_reason_label(reason_code: str) -> str:
        labels = {
            "manual_confirmed": "人工确认免 OA",
            "bank_fee": "银行手续费",
            "salary": "工资",
            "internal_transfer": "内部转账",
        }
        return labels.get(reason_code, "人工确认免 OA")

    @staticmethod
    def _auto_oa_exemption_from_preview(preview: dict[str, Any]) -> dict[str, Any]:
        for candidate in list(preview.get("candidate_evidence") or []):
            if not isinstance(candidate, dict):
                continue
            rule_code = str(candidate.get("rule_code") or candidate.get("special_type") or "auto_oa_exempt")
            return {
                "relation_mode": "oa_exempt",
                "oa_exemption": {
                    "source": "auto",
                    "reason_code": str(candidate.get("reason_code") or "configured_auto_debit"),
                    "reason_label": str(candidate.get("reason_label") or "自动免 OA"),
                    "rule_code": rule_code,
                    "rule_version": str(preview.get("rule_version") or RULE_VERSION),
                    "evidence": deepcopy(candidate.get("evidence") if isinstance(candidate.get("evidence"), dict) else candidate),
                    "confirmed_by": None,
                    "confirmed_at": None,
                    "note": None,
                },
                "display_tags": ["自动免OA"],
            }
        return {
            "relation_mode": "oa_exempt",
            "oa_exemption": {
                "source": "auto",
                "reason_code": "configured_auto_debit",
                "reason_label": "自动免 OA",
                "rule_code": "auto_oa_exempt",
                "rule_version": str(preview.get("rule_version") or RULE_VERSION),
                "evidence": {},
                "confirmed_by": None,
                "confirmed_at": None,
                "note": None,
            },
            "display_tags": ["自动免OA"],
        }

    @staticmethod
    def _relation_mode_for_action(action_code: str, action_payload: dict[str, Any], resolution_payload: dict[str, Any]) -> str:
        if action_code in {"confirm_closed", "confirm_income_closed"}:
            return "normal_match"
        relation_mode = str(resolution_payload.get("relation_mode") or action_payload.get("relation_mode") or "").strip()
        return relation_mode or "manual_confirmed"

    def _create_pair_relation(
        self,
        *,
        case_payload: dict[str, Any],
        action_code: str,
        action_payload: dict[str, Any],
        resolution_payload: dict[str, Any],
        row_ids: list[str],
        month: str,
        actor: str,
        relation_command_service: Any,
    ) -> dict[str, Any]:
        relation_mode = self._relation_mode_for_action(action_code, action_payload, resolution_payload)
        oa_exemption = resolution_payload.get("oa_exemption") if isinstance(resolution_payload.get("oa_exemption"), dict) else None
        display_tags = (
            [str(tag).strip() for tag in list(resolution_payload.get("display_tags") or []) if str(tag).strip()]
            if isinstance(resolution_payload.get("display_tags"), list)
            else []
        )
        evidence = deepcopy(oa_exemption.get("evidence") if isinstance(oa_exemption, dict) and isinstance(oa_exemption.get("evidence"), dict) else {})
        confirm_relation = getattr(relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            raise self._relation_command_unavailable_error()
        result = confirm_relation(
            case_id=str(case_payload["id"]),
            row_ids=row_ids,
            row_types=[str(row_type) for row_type in list(case_payload.get("row_types") or [])],
            relation_mode=relation_mode,
            actor_id=actor or "system",
            month_scope=month,
            note=str(case_payload.get("resolution", {}).get("note") or ""),
            amount_check=deepcopy(case_payload.get("amount_summary") if isinstance(case_payload.get("amount_summary"), dict) else {}),
            special_metadata={
                "special_type": relation_mode,
                "source": "workbench_exception_application",
                "action_code": action_code,
            },
            exception_case_id=str(case_payload["id"]),
            rule_version=str(case_payload.get("rule_version") or RULE_VERSION),
            evidence=evidence,
            oa_exemption=oa_exemption,
            display_tags=display_tags,
            idempotency_key=f"workbench_exception:{case_payload['id']}:relation",
            history_operation_type="workbench_exception_apply",
        )
        relation = result.get("relation") if isinstance(result, dict) else None
        return deepcopy(relation) if isinstance(relation, dict) else {}

    def _require_relation_command_service(self) -> Any:
        if self._relation_command_service is None:
            raise self._relation_command_unavailable_error()
        return self._relation_command_service

    @staticmethod
    def _relation_command_unavailable_error() -> WorkbenchRelationCommandError:
        return WorkbenchRelationCommandError(
            "workbench_relation_command_unavailable",
            "Workbench relation command service is not configured.",
            payload={"read_model_status": "unavailable"},
        )

    def _active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, Any]]:
        relation_command_service = self._require_relation_command_service()
        active_relations = getattr(relation_command_service, "active_relations_for_row_ids", None)
        if not callable(active_relations):
            raise self._relation_command_unavailable_error()
        return [
            deepcopy(relation)
            for relation in list(active_relations(list(row_ids or [])) or [])
            if isinstance(relation, dict)
        ]

    def _active_relation_by_case_id(self, case_id: str) -> dict[str, Any] | None:
        relation_command_service = self._require_relation_command_service()
        get_relation = getattr(relation_command_service, "get_active_relation_by_case_id", None)
        if not callable(get_relation):
            raise self._relation_command_unavailable_error()
        try:
            relation = get_relation(case_id)
        except WorkbenchRelationCommandError as exc:
            if exc.error_code == "workbench_relation_not_found":
                return None
            raise
        return deepcopy(relation) if isinstance(relation, dict) else None

    def _source_versions(self, rule_version: str) -> dict[str, Any]:
        source_versions = deepcopy(self._source_versions_provider() or {})
        source_versions["workbench_exception_rules_version"] = rule_version
        return source_versions

    @staticmethod
    def _apply_payload(
        *,
        case: dict[str, Any],
        pair_relation: dict[str, Any] | None,
        row_ids: list[str],
        updated_rows: list[dict[str, Any]],
        idempotent: bool,
    ) -> dict[str, Any]:
        return {
            "success": True,
            "case": deepcopy(case),
            "pair_relation": deepcopy(pair_relation) if isinstance(pair_relation, dict) else None,
            "updated_rows": deepcopy(updated_rows),
            "affected_row_ids": list(row_ids),
            "workbench_refresh_required": True,
            "idempotent": idempotent,
        }

    @staticmethod
    def _idempotency_key(*, month: str, row_ids: list[str], scenario_code: str, action_code: str) -> str:
        payload = {
            "month": month,
            "row_ids": sorted(row_ids),
            "scenario_code": scenario_code,
            "action_code": action_code,
        }
        digest = hashlib.sha256(
            json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        return f"workbench_exception_apply:{digest}"

    @staticmethod
    def _normalize_row_ids(row_ids: list[Any]) -> list[str]:
        normalized: list[str] = []
        seen: set[str] = set()
        for row_id in row_ids:
            resolved = str(row_id or "").strip()
            if not resolved or resolved in seen:
                continue
            seen.add(resolved)
            normalized.append(resolved)
        if not normalized:
            raise ValueError("row_ids must contain at least one row id.")
        return normalized

    @staticmethod
    def _unique_tags(tags: list[str]) -> list[str]:
        result: list[str] = []
        for tag in tags:
            resolved = str(tag or "").strip()
            if resolved and resolved not in result:
                result.append(resolved)
        return result

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()
