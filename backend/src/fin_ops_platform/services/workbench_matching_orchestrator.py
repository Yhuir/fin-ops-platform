from __future__ import annotations

from copy import deepcopy
import logging
import re
from time import perf_counter
from typing import Any, Callable, Protocol

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_matching_rules import WorkbenchMatchingRules
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_read_model_service import WorkbenchReadModelService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
LOGGER = logging.getLogger(__name__)
MANUAL_CONFIRMED_RELATION_MODE = "manual_confirmed"
ACTIVE_RELATION_STATUS = "active"


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
        pair_relation_service: WorkbenchPairRelationService,
        candidate_match_service: WorkbenchCandidateMatchService,
        read_model_service: WorkbenchReadModelService,
        rules: WorkbenchMatchingRules,
        settings_provider: Callable[[], dict[str, Any]] | None = None,
        source_versions_provider: Callable[[], dict[str, Any]] | None = None,
        logger: logging.Logger | None = None,
    ) -> None:
        self._row_provider = row_provider
        self._pair_relation_service = pair_relation_service
        self._candidate_match_service = candidate_match_service
        self._read_model_service = read_model_service
        self._rules = rules
        self._settings_provider = settings_provider
        self._source_versions_provider = source_versions_provider
        self._logger = logger or LOGGER

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
                self._candidate_match_service.delete_month(scope_month)
                held_row_ids = self._manual_confirmed_row_ids(scope_month)
                oa_rows = self._exclude_held_rows(self._rows_for_month("oa", scope_month), held_row_ids)
                bank_rows = self._exclude_held_rows(self._rows_for_month("bank", scope_month), held_row_ids)
                invoice_rows = self._exclude_held_rows(self._rows_for_month("invoice", scope_month), held_row_ids)

                candidates = self._generate_candidates(scope_month, oa_rows, bank_rows, invoice_rows)
                self._accumulate_rule_summary(summary)
                for candidate in candidates:
                    upserted = self._candidate_match_service.upsert_candidate(candidate)
                    summary["candidate_count"] += 1
                    if upserted.get("status") == "auto_closed":
                        summary["auto_closed_count"] += 1
                    if upserted.get("status") == "conflict":
                        summary["conflict_count"] += 1

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
        candidates = generate_candidates(
            scope_month,
            oa_rows,
            bank_rows,
            invoice_rows,
            settings=self._settings(),
            source_versions=self._source_versions(),
        )
        if not isinstance(candidates, list):
            raise ValueError("rules.generate_candidates(...) must return a list.")
        return candidates

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
        if self._source_versions_provider is None:
            return {}
        payload = self._source_versions_provider()
        if not isinstance(payload, dict):
            raise ValueError("source_versions_provider must return a dict.")
        return payload

    def _rows_for_month(self, row_type: str, scope_month: str) -> list[dict[str, Any]]:
        rows = self._resolve_rows(row_type, scope_month)
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

    def _manual_confirmed_row_ids(self, scope_month: str) -> set[str]:
        list_active_relations = getattr(self._pair_relation_service, "list_active_relations", None)
        if not callable(list_active_relations):
            raise ValueError("pair_relation_service must provide list_active_relations().")

        held_row_ids: set[str] = set()
        for relation in list_active_relations():
            if not isinstance(relation, dict):
                raise ValueError("pair_relation_service returned a non-dict active relation.")
            if str(relation.get("status") or ACTIVE_RELATION_STATUS) != ACTIVE_RELATION_STATUS:
                continue
            if str(relation.get("relation_mode") or MANUAL_CONFIRMED_RELATION_MODE) != MANUAL_CONFIRMED_RELATION_MODE:
                continue
            month_scope = str(relation.get("month_scope") or "all").strip()
            if month_scope not in {"all", scope_month}:
                continue
            for row_id in list(relation.get("row_ids") or []):
                resolved_row_id = str(row_id or "").strip()
                if resolved_row_id:
                    held_row_ids.add(resolved_row_id)
        return held_row_ids

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
