from __future__ import annotations

from copy import deepcopy
from time import perf_counter
from typing import Any, Callable


DERIVED_DATA_EVENTS = (
    "invoice_import_confirmed",
    "bank_import_confirmed",
    "etc_import_confirmed",
    "etc_oa_submitted",
    "etc_oa_revoked",
    "oa_rebuilt",
    "oa_attachment_invoice_cache_updated",
    "pair_relation_changed",
    "exception_case_changed",
    "settings_reset_completed",
    "project_scope_changed",
    "manual_derived_cache_cleanup",
    "startup_stale_scan",
)

DERIVED_DATA_DOMAINS = (
    "workbench_read_model",
    "workbench_candidate_matches",
    "workbench_matching_dirty_scopes",
    "cost_statistics_read_model",
    "tax_offset_read_model",
    "tax_offset_month_cache",
    "search_cache",
    "oa_adapter_records_cache",
    "file_import_sessions",
    "tax_certified_import_sessions",
    "background_jobs",
    "historical_etc_repair_state",
)

PROTECTED_TARGETS = (
    "app_settings",
    "oa_source",
    "canonical_invoices",
    "canonical_bank_transactions",
    "confirmed_import_batches",
    "workbench_pair_relations",
    "workbench_exception_cases",
    "historical_etc_seed_bundles",
    "historical_etc_parsed_seeds",
    "auth_session_data",
)


Executor = Callable[[dict[str, Any]], dict[str, Any] | None]


class DerivedDataLifecycleService:
    """Builds and executes derived-data invalidation plans.

    The service is intentionally a pure orchestration layer. It does not import
    application wiring, persistence adapters, or concrete business services.
    """

    _DOMAIN_ACTIONS: dict[str, str] = {
        "workbench_read_model": "invalidate",
        "workbench_candidate_matches": "cleanup_old_schema",
        "workbench_matching_dirty_scopes": "mark_dirty",
        "cost_statistics_read_model": "invalidate",
        "tax_offset_read_model": "invalidate",
        "tax_offset_month_cache": "clear",
        "search_cache": "clear",
        "oa_adapter_records_cache": "clear",
        "file_import_sessions": "ttl_cleanup",
        "tax_certified_import_sessions": "ttl_cleanup",
        "background_jobs": "terminal_retention_cleanup",
        "historical_etc_repair_state": "reconcile_status",
    }

    _EVENT_DOMAINS: dict[str, tuple[str, ...]] = {
        "invoice_import_confirmed": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "bank_import_confirmed": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "etc_import_confirmed": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "historical_etc_repair_state",
            "search_cache",
        ),
        "etc_oa_submitted": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "etc_oa_revoked": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "oa_rebuilt": (
            "oa_adapter_records_cache",
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "historical_etc_repair_state",
            "search_cache",
        ),
        "oa_attachment_invoice_cache_updated": (
            "workbench_read_model",
            "workbench_matching_dirty_scopes",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "pair_relation_changed": (
            "workbench_read_model",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "exception_case_changed": (
            "workbench_read_model",
            "cost_statistics_read_model",
            "search_cache",
        ),
        "settings_reset_completed": (
            "oa_adapter_records_cache",
            "workbench_read_model",
            "workbench_candidate_matches",
            "workbench_matching_dirty_scopes",
            "cost_statistics_read_model",
            "tax_offset_read_model",
            "tax_offset_month_cache",
            "search_cache",
            "file_import_sessions",
            "tax_certified_import_sessions",
            "historical_etc_repair_state",
        ),
        "project_scope_changed": (
            "cost_statistics_read_model",
            "search_cache",
        ),
        "manual_derived_cache_cleanup": DERIVED_DATA_DOMAINS,
        "startup_stale_scan": (
            "workbench_read_model",
            "workbench_candidate_matches",
            "cost_statistics_read_model",
            "tax_offset_read_model",
            "file_import_sessions",
            "tax_certified_import_sessions",
            "background_jobs",
            "historical_etc_repair_state",
        ),
    }

    _EVENT_JOBS: dict[str, tuple[str, ...]] = {
        "invoice_import_confirmed": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
        ),
        "bank_import_confirmed": (
            "workbench_matching",
            "cost_statistics_cache_warmup",
        ),
        "etc_import_confirmed": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
            "historical_etc_reconcile",
        ),
        "etc_oa_submitted": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
        ),
        "etc_oa_revoked": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
        ),
        "oa_rebuilt": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
            "historical_etc_reconcile",
        ),
        "oa_attachment_invoice_cache_updated": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
        ),
        "settings_reset_completed": (
            "workbench_matching",
            "tax_offset_cache_warmup",
            "cost_statistics_cache_warmup",
            "historical_etc_reconcile",
        ),
    }

    def __init__(self, *, domain_registry: dict[str, dict[str, Any]] | None = None) -> None:
        self._domain_registry = self._build_domain_registry(domain_registry)

    @property
    def domain_registry(self) -> dict[str, dict[str, Any]]:
        return deepcopy(self._domain_registry)

    def plan_event(
        self,
        event: str,
        months: list[str] | tuple[str, ...] | str | None = None,
        scope_keys: list[str] | tuple[str, ...] | str | None = None,
        include_all: bool = True,
        dry_run: bool = True,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_event = str(event or "").strip()
        if normalized_event not in DERIVED_DATA_EVENTS:
            raise ValueError(f"Unsupported derived data lifecycle event: {event}")

        affected_scopes = self._normalize_scopes(months=months, scope_keys=scope_keys, include_all=include_all)
        domain_names = self._EVENT_DOMAINS[normalized_event]
        domain_plans = [
            self._build_domain_plan(domain_name, affected_scopes=affected_scopes, dry_run=dry_run)
            for domain_name in domain_names
        ]
        return {
            "event": normalized_event,
            "dry_run": bool(dry_run),
            "affected_scopes": affected_scopes,
            "domains": domain_plans,
            "protected_targets": list(PROTECTED_TARGETS),
            "will_enqueue_jobs": list(self._EVENT_JOBS.get(normalized_event, ())),
            "metadata": deepcopy(metadata if isinstance(metadata, dict) else {}),
        }

    def execute_plan(
        self,
        plan: dict[str, Any],
        executors: dict[str, Executor] | None = None,
    ) -> dict[str, Any]:
        if not isinstance(plan, dict):
            raise ValueError("plan must be a dict.")
        event = str(plan.get("event") or "").strip()
        if event not in DERIVED_DATA_EVENTS:
            raise ValueError(f"Unsupported derived data lifecycle event: {event}")

        started_at = perf_counter()
        resolved_executors = executors if isinstance(executors, dict) else {}
        summary: dict[str, Any] = {
            "event": event,
            "dry_run": bool(plan.get("dry_run", True)),
            "deleted_counts": {},
            "invalidated_scopes": [],
            "enqueued_jobs": [],
            "skipped": [],
            "skipped_protected_targets": list(PROTECTED_TARGETS),
            "errors": [],
            "duration_ms": 0,
        }

        for domain_plan in list(plan.get("domains") or []):
            if not isinstance(domain_plan, dict):
                continue
            domain_name = str(domain_plan.get("domain") or "").strip()
            executor = resolved_executors.get(domain_name)
            if executor is None:
                summary["skipped"].append(domain_name)
                continue
            try:
                result = executor(deepcopy(domain_plan))
            except Exception as exc:  # pragma: no cover - exact exception type belongs to concrete executor.
                summary["errors"].append({"domain": domain_name, "error": str(exc)})
                continue
            self._merge_executor_result(summary, domain_name, result)

        summary["duration_ms"] = int((perf_counter() - started_at) * 1000)
        return summary

    def _build_domain_registry(self, overrides: dict[str, dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
        registry = {
            domain: {
                "domain": domain,
                "action": self._DOMAIN_ACTIONS[domain],
                "delete_targets": [domain],
            }
            for domain in DERIVED_DATA_DOMAINS
        }
        if not overrides:
            return registry
        for domain, override in overrides.items():
            if domain not in registry:
                raise ValueError(f"Unsupported derived data domain: {domain}")
            if not isinstance(override, dict):
                raise ValueError("domain registry overrides must be dict values.")
            registry[domain] = {**registry[domain], **deepcopy(override)}
        return registry

    def _build_domain_plan(self, domain_name: str, *, affected_scopes: list[str], dry_run: bool) -> dict[str, Any]:
        domain = self._domain_registry[domain_name]
        delete_targets = [
            str(target)
            for target in list(domain.get("delete_targets") or [])
            if str(target) not in PROTECTED_TARGETS
        ]
        return {
            "domain": domain_name,
            "action": str(domain.get("action") or "invalidate"),
            "scope_keys": list(affected_scopes),
            "estimated_count": len(affected_scopes),
            "delete_targets": delete_targets,
            "dry_run": bool(dry_run),
        }

    @classmethod
    def _normalize_scopes(
        cls,
        *,
        months: list[str] | tuple[str, ...] | str | None,
        scope_keys: list[str] | tuple[str, ...] | str | None,
        include_all: bool,
    ) -> list[str]:
        scopes = cls._coerce_text_list(months) + cls._coerce_text_list(scope_keys)
        if include_all:
            scopes.append("all")
        normalized: list[str] = []
        seen: set[str] = set()
        for scope in scopes:
            if scope in seen:
                continue
            seen.add(scope)
            normalized.append(scope)
        return normalized

    @staticmethod
    def _coerce_text_list(value: list[str] | tuple[str, ...] | str | None) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            values = [value]
        else:
            values = list(value)
        return [str(item).strip() for item in values if str(item or "").strip()]

    @classmethod
    def _merge_executor_result(
        cls,
        summary: dict[str, Any],
        domain_name: str,
        result: dict[str, Any] | None,
    ) -> None:
        if result is None:
            return
        if not isinstance(result, dict):
            summary["errors"].append({"domain": domain_name, "error": "executor returned a non-dict result"})
            return

        deleted_counts = result.get("deleted_counts")
        if isinstance(deleted_counts, dict):
            for key, value in deleted_counts.items():
                cls._add_deleted_count(summary, str(key), value)
        elif "deleted_count" in result:
            cls._add_deleted_count(summary, domain_name, result.get("deleted_count"))

        cls._extend_unique(summary["invalidated_scopes"], result.get("invalidated_scopes"))
        cls._extend_unique(summary["enqueued_jobs"], result.get("enqueued_jobs"))
        errors = result.get("errors")
        if isinstance(errors, list):
            for error in errors:
                summary["errors"].append(error if isinstance(error, dict) else {"domain": domain_name, "error": str(error)})
        elif errors:
            summary["errors"].append({"domain": domain_name, "error": str(errors)})

    @staticmethod
    def _add_deleted_count(summary: dict[str, Any], key: str, value: Any) -> None:
        try:
            count = int(value)
        except (TypeError, ValueError):
            count = 0
        summary["deleted_counts"][key] = int(summary["deleted_counts"].get(key, 0)) + max(count, 0)

    @staticmethod
    def _extend_unique(target: list[Any], values: Any) -> None:
        if values is None:
            return
        source = values if isinstance(values, list) else [values]
        for value in source:
            if value not in target:
                target.append(value)
