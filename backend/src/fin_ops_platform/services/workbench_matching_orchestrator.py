from __future__ import annotations

from copy import deepcopy
import logging
import re
from time import perf_counter
from typing import Any, Callable, Protocol

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_amount_check_service import WorkbenchAmountCheckService
from fin_ops_platform.services.workbench_matching_rules import WORKBENCH_MATCHING_RULES_VERSION, WorkbenchMatchingRules
from fin_ops_platform.services.workbench_reconciliation_decision_store import WorkbenchReconciliationDecisionStore
from fin_ops_platform.services.workbench_reconciliation_engine import (
    AUTO_PAIR_ACTOR,
    AUTO_PAIR_HISTORY_OPERATION,
    WorkbenchMatchingRelationReadPort,
    WorkbenchReconciliationEngine,
)
from fin_ops_platform.services.workbench_reconciliation_models import expand_scope_month_window
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
from fin_ops_platform.services.workbench_special_reconciliation_adapter import WorkbenchSpecialReconciliationAdapter
from fin_ops_platform.services.workbench_special_pair_rule_service import (
    WORKBENCH_SPECIAL_RULES_VERSION,
    WorkbenchSpecialPairRuleService,
)


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
LOGGER = logging.getLogger(__name__)
MANUAL_CONFIRMED_RELATION_MODE = "manual_confirmed"
ACTIVE_RELATION_STATUS = "active"
WORKBENCH_EXCEPTION_RULES_VERSION = "2026-05-exception-preview-apply-candidate-contract"
OA_ATTACHMENT_INVOICE_SOURCE_KIND = "oa_attachment_invoice"


class WorkbenchMonthlyRowProvider(Protocol):
    def get_oa_rows(self, scope_month: str) -> list[dict[str, Any]]:
        ...

    def get_bank_rows(self, scope_month: str) -> list[dict[str, Any]]:
        ...

    def get_invoice_rows(self, scope_month: str) -> list[dict[str, Any]]:
        ...


class WorkbenchMatchingOrchestrator:
    def __init__(
        self,
        *,
        row_provider: WorkbenchMonthlyRowProvider | Callable[[str], dict[str, Any]],
        relation_read_port: WorkbenchMatchingRelationReadPort,
        candidate_match_service: WorkbenchCandidateMatchService,
        read_model_service: WorkbenchReadModelService,
        rules: WorkbenchMatchingRules,
        special_rule_service: WorkbenchSpecialPairRuleService | None = None,
        exception_case_service: object | None = None,
        decision_store: WorkbenchReconciliationDecisionStore | None = None,
        reconciliation_engine: WorkbenchReconciliationEngine | None = None,
        relation_command_service: Any | None = None,
        settings_provider: Callable[[], dict[str, Any]] | None = None,
        source_versions_provider: Callable[[], dict[str, Any]] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._row_provider = row_provider
        self._relation_read_port = relation_read_port
        self._candidate_match_service = candidate_match_service
        self._read_model_service = read_model_service
        self._rules = rules
        self._special_rule_service = special_rule_service or WorkbenchSpecialPairRuleService()
        self._exception_case_service = exception_case_service
        self._decision_store = decision_store
        self._reconciliation_engine = reconciliation_engine
        self._relation_command_service = relation_command_service
        self._settings_provider = settings_provider
        self._source_versions_provider = source_versions_provider
        self._logger = logger or LOGGER
        self._amount_check_service = WorkbenchAmountCheckService()

    def run(
        self,
        *,
        changed_scope_months: list[str],
        reason: str,
        request_id: str,
        progress_callback: Callable[[dict[str, Any]], None] | None = None,
    ) -> dict[str, Any]:
        started_at = perf_counter()
        summary: dict[str, Any] = {
            "request_id": str(request_id or "").strip(),
            "reason": str(reason or "").strip(),
            "scope_months": [],
            "processed_months": [],
            "current_month": None,
            "candidate_count": 0,
            "auto_closed_count": 0,
            "conflict_count": 0,
            "skipped_rule_count": 0,
            "skipped_rules": [],
            "suppressed_by_exception_case_count": 0,
            "suppressed_by_pair_relation_count": 0,
            "candidate_attached_to_exception_case_count": 0,
            "auto_linked_relation_count": 0,
            "duration_ms": 0,
        }

        try:
            summary["request_id"] = self._required_text(request_id, "request_id")
            summary["reason"] = self._required_text(reason, "reason")
            scope_months = self._normalize_scope_months(changed_scope_months)
            summary["scope_months"] = scope_months
            self._log("workbench_matching.run.started", summary)

            for scope_month in scope_months:
                summary["current_month"] = scope_month
                if self._decision_store is not None:
                    self._run_decision_scope(scope_month, summary)
                    summary["processed_months"].append(scope_month)
                    summary["duration_ms"] = self._duration_ms(started_at)
                    self._emit_progress(progress_callback, summary)
                    continue

                self._candidate_match_service.delete_month(scope_month)
                month_rows = self._rows_for_scope(scope_month)
                held_row_ids = self._active_pair_relation_row_ids(scope_month)
                scoped_held_row_ids = self._row_ids_in_scope(month_rows, held_row_ids)
                summary["suppressed_by_pair_relation_count"] += len(scoped_held_row_ids)
                oa_rows = self._exclude_held_rows(month_rows["oa_rows"], held_row_ids)
                bank_rows = self._exclude_held_rows(month_rows["bank_rows"], held_row_ids)
                invoice_rows = self._exclude_held_rows(month_rows["invoice_rows"], held_row_ids)

                candidates = self._generate_candidates(scope_month, oa_rows, bank_rows, invoice_rows)
                candidates = self._suppress_candidates_for_active_exception_cases(candidates, summary)
                self._accumulate_rule_summary(summary)
                rows_by_id = self._rows_by_id([*oa_rows, *bank_rows, *invoice_rows])
                for candidate in candidates:
                    upserted = self._candidate_match_service.upsert_candidate(candidate)
                    summary["candidate_count"] += 1
                    if upserted.get("status") == "auto_closed":
                        summary["auto_closed_count"] += 1
                        if self._auto_link_candidate(upserted, rows_by_id=rows_by_id, scope_month=scope_month):
                            summary["auto_linked_relation_count"] += 1
                    if upserted.get("status") == "conflict":
                        summary["conflict_count"] += 1

                self._candidate_match_service.mark_scope_processed(
                    scope_month,
                    source_versions=self._source_versions(),
                    candidate_count=len(candidates),
                    request_id=str(summary["request_id"]),
                    reason=str(summary["reason"]),
                )
                self._invalidate_read_models(scope_month)
                summary["processed_months"].append(scope_month)
                summary["duration_ms"] = self._duration_ms(started_at)
                self._emit_progress(progress_callback, summary)

            summary["duration_ms"] = self._duration_ms(started_at)
            self._log("workbench_matching.run.finished", summary)
            return summary
        except Exception:
            summary["duration_ms"] = self._duration_ms(started_at)
            self._log("workbench_matching.run.failed", summary, failed=True)
            raise

    def _generate_candidates(
        self,
        scope_month: str,
        oa_rows: list[dict[str, Any]],
        bank_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        generate_candidates = getattr(self._rules, "generate_candidates", None)
        if not callable(generate_candidates):
            raise ValueError("rules must provide generate_candidates(...).")
        settings = self._settings()
        source_versions = self._source_versions()
        ordinary_candidates = generate_candidates(
            scope_month,
            oa_rows,
            bank_rows,
            invoice_rows,
            settings=settings,
            source_versions=source_versions,
        )
        if not isinstance(ordinary_candidates, list):
            raise ValueError("rules.generate_candidates(...) must return a list.")
        special_candidates = self._special_rule_service.generate_candidates(
            scope_month,
            oa_rows,
            bank_rows,
            invoice_rows,
            settings=settings,
            source_versions=source_versions,
        )
        if not isinstance(special_candidates, list):
            raise ValueError("special_rule_service.generate_candidates(...) must return a list.")
        return self._dedupe_candidates([*ordinary_candidates, *special_candidates])

    def _run_decision_scope(self, scope_month: str, summary: dict[str, Any]) -> None:
        if self._decision_store is None:
            raise ValueError("decision_store is required for reconciliation decision mode.")
        self._candidate_match_service.delete_month(scope_month)
        month_rows = self._rows_for_scope_window(scope_month)
        engine = self._reconciliation_engine or WorkbenchReconciliationEngine(
            decision_store=self._decision_store,
            relation_read_port=self._relation_read_port,
            special_adapter=WorkbenchSpecialReconciliationAdapter(
                special_rule_service=self._special_rule_service,
            ),
            relation_command_service=self._relation_command_service,
        )
        result = engine.run_scope(
            scope_month,
            oa_rows=month_rows["oa_rows"],
            bank_rows=month_rows["bank_rows"],
            invoice_rows=month_rows["invoice_rows"],
            settings=self._settings(),
            source_versions=self._source_versions(),
        )
        summary["decision_count"] = int(summary.get("decision_count") or 0) + int(result.get("decision_count") or 0)
        summary["paired_decision_count"] = int(summary.get("paired_decision_count") or 0) + int(result.get("paired_count") or 0)
        summary["open_decision_count"] = int(summary.get("open_decision_count") or 0) + int(result.get("open_count") or 0)
        summary["expired_decision_count"] = int(summary.get("expired_decision_count") or 0) + int(
            result.get("expired_decision_count") or 0
        )
        summary["suppressed_by_pair_relation_count"] += int(result.get("suppressed_by_pair_relation_count") or 0)
        summary["auto_completed_relation_count"] = int(summary.get("auto_completed_relation_count") or 0) + int(
            result.get("auto_completed_relation_count") or 0
        )
        summary["auto_created_relation_count"] = int(summary.get("auto_created_relation_count") or 0) + int(
            result.get("auto_created_relation_count") or 0
        )
        self._invalidate_read_models(scope_month)

    def _accumulate_rule_summary(self, summary: dict[str, Any]) -> None:
        last_summary = getattr(self._rules, "last_summary", None)
        if not callable(last_summary):
            return
        payload = last_summary()
        if not isinstance(payload, dict):
            raise ValueError("rules.last_summary() must return a dict.")
        skipped_rules = payload.get("skipped_rules") or []
        if not isinstance(skipped_rules, list):
            raise ValueError("rules.last_summary().skipped_rules must be a list.")
        skipped_rule_count = payload.get("skipped_rule_count")
        if skipped_rule_count is None:
            skipped_rule_count = len(skipped_rules)
        if not isinstance(skipped_rule_count, int):
            raise ValueError("rules.last_summary().skipped_rule_count must be an int.")
        summary["skipped_rule_count"] += skipped_rule_count
        for skipped_rule in skipped_rules:
            if not isinstance(skipped_rule, dict):
                raise ValueError("rules.last_summary().skipped_rules values must be dicts.")
            summary["skipped_rules"].append(deepcopy(skipped_rule))

    def _auto_link_candidate(
        self,
        candidate: dict[str, Any],
        *,
        rows_by_id: dict[str, dict[str, Any]],
        scope_month: str,
    ) -> bool:
        confirm_relation = getattr(self._relation_command_service, "confirm_relation", None)
        if not callable(confirm_relation):
            return False
        if str(candidate.get("status") or "").strip() != "auto_closed":
            return False
        if str(candidate.get("confidence") or "").strip() != "high":
            return False
        if list(candidate.get("conflict_candidate_keys") or []):
            return False
        row_ids = [str(row_id or "").strip() for row_id in list(candidate.get("row_ids") or []) if str(row_id or "").strip()]
        if len(row_ids) < 2 or any(row_id not in rows_by_id for row_id in row_ids):
            return False
        row_types = self._candidate_row_types(candidate, row_ids, rows_by_id)
        if len({row_type for row_type in row_types if row_type}) < 2:
            return False
        if self._relation_read_port.active_relations_for_row_ids(row_ids):
            return False
        if self._relation_read_port.has_withdrawn_relation_for_row_ids(row_ids):
            return False
        rows_by_type = self._candidate_rows_by_type(row_ids, row_types, rows_by_id)
        amount_check = self._amount_check_service.check(rows_by_type)
        if str(amount_check.get("status") or "") != "matched":
            return False
        case_id = self._auto_link_case_id(candidate)
        source_versions = candidate.get("source_versions") if isinstance(candidate.get("source_versions"), dict) else {}
        try:
            confirm_relation(
                case_id=case_id,
                row_ids=row_ids,
                row_types=row_types,
                relation_mode=MANUAL_CONFIRMED_RELATION_MODE,
                actor_id=AUTO_PAIR_ACTOR,
                month_scope=scope_month,
                note="系统自动配对",
                amount_check=amount_check,
                special_metadata={"auto_pair": {"candidate_key": candidate.get("candidate_key"), "rule_code": candidate.get("rule_code")}},
                evidence=deepcopy(candidate.get("special_metadata") or {}),
                rule_version=str(source_versions.get("workbench_matching_rules_version") or ""),
                relation_created_by=AUTO_PAIR_ACTOR,
                history_note="系统自动配对",
                idempotency_key=f"workbench:auto-pair-candidate:{candidate.get('candidate_key')}",
                history_operation_type=AUTO_PAIR_HISTORY_OPERATION,
            )
        except (WorkbenchRelationCommandError, ValueError):
            return False
        self._candidate_match_service.mark_candidates_consumed(
            candidate_keys=[str(candidate.get("candidate_key") or "")],
            consumed_by_case_id=case_id,
            consumed_by_relation_case_id=case_id,
        )
        return True

    @staticmethod
    def _auto_link_case_id(candidate: dict[str, Any]) -> str:
        candidate_key = str(candidate.get("candidate_key") or "").strip()
        digest = candidate_key.removeprefix("candidate:")[:16]
        return f"CASE-AUTO-{digest}" if digest else "CASE-AUTO-CANDIDATE"

    @classmethod
    def _candidate_row_types(
        cls,
        candidate: dict[str, Any],
        row_ids: list[str],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        oa_ids = set(cls._text_list(candidate.get("oa_row_ids")))
        bank_ids = set(cls._text_list(candidate.get("bank_row_ids")))
        invoice_ids = set(cls._text_list(candidate.get("invoice_row_ids")))
        row_types: list[str] = []
        for row_id in row_ids:
            if row_id in oa_ids:
                row_types.append("oa")
            elif row_id in bank_ids:
                row_types.append("bank")
            elif row_id in invoice_ids:
                row_types.append("invoice")
            else:
                row_type = str((rows_by_id.get(row_id) or {}).get("type") or "").strip()
                row_types.append(row_type if row_type in {"oa", "bank", "invoice"} else "")
        return row_types

    @staticmethod
    def _candidate_rows_by_type(
        row_ids: list[str],
        row_types: list[str],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> dict[str, list[dict[str, Any]]]:
        rows_by_type: dict[str, list[dict[str, Any]]] = {"oa": [], "bank": [], "invoice": []}
        for row_id, row_type in zip(row_ids, row_types):
            if row_type in rows_by_type:
                rows_by_type[row_type].append(deepcopy(rows_by_id[row_id]))
        return rows_by_type

    @staticmethod
    def _dedupe_candidates(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[tuple[str, str, tuple[str, ...]], dict[str, Any]] = {}
        for candidate in candidates:
            if not isinstance(candidate, dict):
                raise ValueError("candidate values must be dicts.")
            key = (
                str(candidate.get("scope_month") or ""),
                str(candidate.get("rule_code") or ""),
                tuple(sorted(str(row_id) for row_id in list(candidate.get("row_ids") or []))),
            )
            if key not in deduped:
                deduped[key] = candidate
        return list(deduped.values())

    def _emit_progress(
        self,
        progress_callback: Callable[[dict[str, Any]], None] | None,
        summary: dict[str, Any],
    ) -> None:
        if progress_callback is None:
            return
        progress_callback(deepcopy(summary))

    def _settings(self) -> dict[str, Any]:
        if self._settings_provider is None:
            return {}
        payload = self._settings_provider()
        if not isinstance(payload, dict):
            raise ValueError("settings_provider must return a dict.")
        return payload

    def _source_versions(self) -> dict[str, Any]:
        versions = {
            "workbench_matching_rules_version": WORKBENCH_MATCHING_RULES_VERSION,
            "workbench_special_rules_version": WORKBENCH_SPECIAL_RULES_VERSION,
            "workbench_exception_rules_version": WORKBENCH_EXCEPTION_RULES_VERSION,
        }
        if self._source_versions_provider is None:
            return versions
        payload = self._source_versions_provider()
        if not isinstance(payload, dict):
            raise ValueError("source_versions_provider must return a dict.")
        return {**versions, **payload}

    def _rows_for_month(self, row_type: str, scope_month: str) -> list[dict[str, Any]]:
        rows = self._resolve_rows(row_type, scope_month)
        return self._normalize_rows(row_type, rows)

    def _rows_for_scope(self, scope_month: str) -> dict[str, list[dict[str, Any]]]:
        if callable(self._row_provider) and not any(
            callable(getattr(self._row_provider, method_name, None))
            for method_name in (
                "get_oa_rows",
                "list_oa_rows",
                "get_bank_rows",
                "list_bank_rows",
                "get_invoice_rows",
                "list_invoice_rows",
            )
        ):
            payload = self._row_provider(scope_month)
            if not isinstance(payload, dict):
                raise ValueError("callable row_provider must return a dict.")
            rows = {
                "oa_rows": self._normalize_rows("oa", payload.get("oa_rows", [])),
                "bank_rows": self._normalize_rows("bank", payload.get("bank_rows", [])),
                "invoice_rows": self._normalize_rows("invoice", payload.get("invoice_rows", [])),
            }
            self._enrich_source_bound_attachment_invoice_months(rows["oa_rows"], rows["invoice_rows"])
            return rows
        rows = {
            "oa_rows": self._rows_for_month("oa", scope_month),
            "bank_rows": self._rows_for_month("bank", scope_month),
            "invoice_rows": self._rows_for_month("invoice", scope_month),
        }
        self._enrich_source_bound_attachment_invoice_months(rows["oa_rows"], rows["invoice_rows"])
        return rows

    def _rows_for_scope_window(self, scope_month: str) -> dict[str, list[dict[str, Any]]]:
        rows = {
            "oa_rows": [],
            "bank_rows": [],
            "invoice_rows": [],
        }
        for candidate_month in expand_scope_month_window(scope_month):
            month_rows = self._rows_for_scope(candidate_month)
            rows["oa_rows"].extend(month_rows["oa_rows"])
            rows["bank_rows"].extend(month_rows["bank_rows"])
            rows["invoice_rows"].extend(month_rows["invoice_rows"])
        self._enrich_source_bound_attachment_invoice_months(rows["oa_rows"], rows["invoice_rows"])
        return {
            "oa_rows": self._dedupe_rows(rows["oa_rows"]),
            "bank_rows": self._dedupe_rows(rows["bank_rows"]),
            "invoice_rows": self._dedupe_rows(rows["invoice_rows"]),
        }

    @classmethod
    def _enrich_source_bound_attachment_invoice_months(
        cls,
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
    ) -> None:
        oa_month_by_id = {
            row_id: month
            for row in oa_rows
            if (row_id := cls._row_id(row)) and (month := cls._owner_month("oa", row))
        }
        if not oa_month_by_id:
            return
        for invoice_row in invoice_rows:
            if str(invoice_row.get("source_kind") or "").strip() != OA_ATTACHMENT_INVOICE_SOURCE_KIND:
                continue
            linked_oa_id = cls._linked_oa_id(invoice_row)
            source_oa_month = oa_month_by_id.get(linked_oa_id)
            if not source_oa_month:
                continue
            invoice_row["source_oa_month"] = source_oa_month
            invoice_row["month"] = source_oa_month

    @staticmethod
    def _linked_oa_id(invoice_row: dict[str, Any]) -> str:
        for field_name in (
            "derived_from_oa_id",
            "derived_from_oa_row_id",
            "source_oa_row_id",
            "linked_oa_row_id",
            "parent_oa_row_id",
            "oa_row_id",
            "oa_id",
        ):
            value = str(invoice_row.get(field_name) or "").strip()
            if value:
                return value
        metadata = invoice_row.get("metadata")
        if isinstance(metadata, dict):
            for field_name in ("derived_from_oa_id", "source_oa_row_id", "oa_row_id", "oa_id"):
                value = str(metadata.get(field_name) or "").strip()
                if value:
                    return value
        return ""

    @staticmethod
    def _owner_month(row_type: str, row: dict[str, Any]) -> str:
        fields = {
            "oa": ("month", "oa_month", "apply_month", "application_date", "apply_date", "pay_receive_time"),
            "invoice": ("source_oa_month", "month", "invoice_month", "invoice_date", "issue_date"),
        }.get(row_type, ("month",))
        for field_name in fields:
            value = str(row.get(field_name) or "").strip()
            if len(value) >= 7:
                return value[:7]
        detail_fields = row.get("detail_fields")
        if row_type == "oa" and isinstance(detail_fields, dict):
            for field_name in ("申请日期", "申请时间", "提交日期", "提交时间"):
                value = str(detail_fields.get(field_name) or "").strip()
                if len(value) >= 7:
                    return value[:7]
        return ""

    @staticmethod
    def _dedupe_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        deduped: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if not row_id:
                raise ValueError("workbench row requires id or row_id.")
            if row_id not in deduped:
                deduped[row_id] = deepcopy(row)
        return list(deduped.values())

    @classmethod
    def _rows_by_id(cls, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        return {row_id: deepcopy(row) for row in rows if (row_id := cls._row_id(row))}

    @staticmethod
    def _row_id(row: dict[str, Any]) -> str:
        return str(row.get("id") or row.get("row_id") or "").strip()

    @staticmethod
    def _text_list(values: Any) -> list[str]:
        return [str(value or "").strip() for value in list(values or []) if str(value or "").strip()]

    @staticmethod
    def _normalize_rows(row_type: str, rows: Any) -> list[dict[str, Any]]:
        if not isinstance(rows, list):
            raise ValueError(f"{row_type} row provider must return a list.")
        normalized_rows: list[dict[str, Any]] = []
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError(f"{row_type} row provider returned a non-dict row.")
            normalized_rows.append(deepcopy(row))
        return normalized_rows

    def _resolve_rows(self, row_type: str, scope_month: str) -> Any:
        for method_name in (f"get_{row_type}_rows", f"list_{row_type}_rows"):
            method = getattr(self._row_provider, method_name, None)
            if callable(method):
                return method(scope_month)

        if callable(self._row_provider):
            payload = self._row_provider(scope_month)
            if not isinstance(payload, dict):
                raise ValueError("callable row_provider must return a dict.")
            return payload.get(f"{row_type}_rows", [])

        raise ValueError(
            "row_provider must provide get_oa_rows/get_bank_rows/get_invoice_rows "
            "or be callable with a scope month."
        )

    def _active_pair_relation_row_ids(self, scope_month: str) -> set[str]:
        window_months = set(expand_scope_month_window(scope_month))
        held_row_ids: set[str] = set()
        for relation in self._relation_read_port.list_active_relations():
            if str(relation.get("status") or ACTIVE_RELATION_STATUS) != ACTIVE_RELATION_STATUS:
                continue
            month_scope = self._relation_month_scope(relation)
            if month_scope != "all" and month_scope not in window_months:
                continue
            for row_id in list(relation.get("row_ids") or []):
                resolved_row_id = str(row_id or "").strip()
                if resolved_row_id:
                    held_row_ids.add(resolved_row_id)
        return held_row_ids

    @staticmethod
    def _relation_month_scope(relation: dict[str, Any]) -> str:
        month_scope = str(relation.get("month_scope") or "all").strip()
        if month_scope == "all":
            return "all"
        return month_scope[:7] if len(month_scope) >= 7 else month_scope

    def _suppress_candidates_for_active_exception_cases(
        self,
        candidates: list[dict[str, Any]],
        summary: dict[str, Any],
    ) -> list[dict[str, Any]]:
        if self._exception_case_service is None:
            return candidates
        resolved_candidates: list[dict[str, Any]] = []
        for candidate in candidates:
            row_ids = [str(row_id or "").strip() for row_id in list(candidate.get("row_ids") or []) if str(row_id or "").strip()]
            case_ids = self._active_exception_case_ids(row_ids)
            if not case_ids:
                resolved_candidates.append(candidate)
                continue
            summary["candidate_attached_to_exception_case_count"] += 1
            updated = deepcopy(candidate)
            updated["consumed_by_case_id"] = case_ids[0]
            special_metadata = deepcopy(updated.get("special_metadata") if isinstance(updated.get("special_metadata"), dict) else {})
            special_metadata["active_exception_case_ids"] = case_ids
            updated["special_metadata"] = special_metadata
            if str(updated.get("status") or "") == "auto_closed":
                updated["status"] = "suppressed"
                updated["suppressed_reason"] = "active_exception_case"
                summary["suppressed_by_exception_case_count"] += 1
            resolved_candidates.append(updated)
        return resolved_candidates

    def _active_exception_case_ids(self, row_ids: list[str]) -> list[str]:
        if not row_ids:
            return []
        case_ids_for_rows = getattr(self._exception_case_service, "case_ids_for_rows", None)
        if not callable(case_ids_for_rows):
            raise ValueError("exception_case_service must provide case_ids_for_rows(row_ids).")
        case_ids = case_ids_for_rows(row_ids)
        if not isinstance(case_ids, list):
            raise ValueError("exception_case_service.case_ids_for_rows(row_ids) must return a list.")
        normalized: list[str] = []
        for case_id in case_ids:
            resolved_case_id = str(case_id or "").strip()
            if resolved_case_id and resolved_case_id not in normalized:
                normalized.append(resolved_case_id)
        return normalized

    @staticmethod
    def _exclude_held_rows(rows: list[dict[str, Any]], held_row_ids: set[str]) -> list[dict[str, Any]]:
        if not held_row_ids:
            return rows
        filtered: list[dict[str, Any]] = []
        for row in rows:
            row_id = str(row.get("id") or row.get("row_id") or "").strip()
            if not row_id:
                raise ValueError("workbench row requires id or row_id.")
            if row_id not in held_row_ids:
                filtered.append(row)
        return filtered

    @staticmethod
    def _row_ids_in_scope(month_rows: dict[str, list[dict[str, Any]]], row_ids: set[str]) -> set[str]:
        if not row_ids:
            return set()
        scoped_ids: set[str] = set()
        for rows in month_rows.values():
            for row in rows:
                row_id = str(row.get("id") or row.get("row_id") or "").strip()
                if row_id in row_ids:
                    scoped_ids.add(row_id)
        return scoped_ids

    def _invalidate_read_models(self, scope_month: str) -> None:
        delete_read_model = getattr(self._read_model_service, "delete_read_model", None)
        if not callable(delete_read_model):
            raise ValueError("read_model_service must provide delete_read_model(scope_key).")
        for scope_key in (scope_month, "all"):
            delete_read_model(scope_key)

    def _log(self, event: str, summary: dict[str, Any], *, failed: bool = False) -> None:
        payload = {
            "event": event,
            "request_id": summary["request_id"],
            "scope_months": list(summary.get("scope_months") or []),
            "duration_ms": summary["duration_ms"],
            "candidate_count": summary["candidate_count"],
            "auto_closed_count": summary["auto_closed_count"],
            "conflict_count": summary["conflict_count"],
            "skipped_rule_count": summary.get("skipped_rule_count", 0),
            "reason": summary["reason"],
        }
        message = (
            f"{event} request_id={payload['request_id']} scope_months={payload['scope_months']} "
            f"duration_ms={payload['duration_ms']} candidate_count={payload['candidate_count']} "
            f"auto_closed_count={payload['auto_closed_count']} conflict_count={payload['conflict_count']} "
            f"skipped_rule_count={payload['skipped_rule_count']} reason={payload['reason']}"
        )
        if failed:
            self._logger.exception(message, extra={"workbench_matching": payload})
        else:
            self._logger.info(message, extra={"workbench_matching": payload})

    @classmethod
    def _normalize_scope_months(cls, changed_scope_months: list[str]) -> list[str]:
        if not isinstance(changed_scope_months, list):
            raise ValueError("changed_scope_months must be a list.")
        normalized: list[str] = []
        for month in changed_scope_months:
            resolved_month = str(month or "").strip()
            if not MONTH_RE.match(resolved_month):
                raise ValueError("changed_scope_months values must be YYYY-MM.")
            if resolved_month not in normalized:
                normalized.append(resolved_month)
        if not normalized:
            raise ValueError("changed_scope_months must include at least one month.")
        return normalized

    @staticmethod
    def _required_text(value: str, field_name: str) -> str:
        resolved_value = str(value or "").strip()
        if not resolved_value:
            raise ValueError(f"{field_name} is required.")
        return resolved_value

    @staticmethod
    def _duration_ms(started_at: float) -> int:
        return max(0, int((perf_counter() - started_at) * 1000))
