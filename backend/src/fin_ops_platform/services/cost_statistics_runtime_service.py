from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any, Callable

from fin_ops_platform.services.cost_statistics_read_model_service import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.read_model_freshness import normalize_source_versions


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
PROJECT_SCOPE_ORDER = ("active", "all")


class CostStatisticsRuntimeService:
    def __init__(
        self,
        *,
        read_model_service: Any | None = None,
        background_job_service: Any | None = None,
        queue_repository: Any | None = None,
        redis_helper: Any | None = None,
        source_versions_provider: Callable[[str], dict[str, Any]] | None = None,
        persist_read_models: Callable[..., None] | None = None,
    ) -> None:
        self._read_model_service = read_model_service
        self._background_job_service = background_job_service
        self._queue_repository = queue_repository
        self._redis_helper = redis_helper
        self._source_versions_provider = source_versions_provider
        self._persist_read_models = persist_read_models

    @staticmethod
    def request_scope_key(month: str, project_scope: str) -> str:
        return f"{str(project_scope or 'active').strip().lower()}:{str(month or 'all').strip() or 'all'}"

    def expected_source_versions(self, scope_key: str) -> dict[str, Any]:
        if callable(self._source_versions_provider):
            return dict(self._source_versions_provider(scope_key) or {})
        _project_scope, month = str(scope_key or "active:all").split(":", 1)
        return {
            "cost_statistics_read_model_schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "workbench_scope_key": month,
        }

    def redis_cache_key(self, scope_key: str, *, source_versions: dict[str, Any] | None = None) -> str:
        return self.read_model_redis_cache_key(
            "cost_statistics:explorer",
            scope_key,
            schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            source_versions=source_versions,
        )

    def month_redis_cache_key(self, scope_key: str, *, source_versions: dict[str, Any] | None = None) -> str:
        return self.read_model_redis_cache_key(
            "cost_statistics:month",
            scope_key,
            schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            source_versions=source_versions,
        )

    @staticmethod
    def read_model_redis_cache_key(
        prefix: str,
        scope_key: str,
        *,
        schema_version: str,
        source_versions: dict[str, Any] | None,
    ) -> str:
        normalized_source_versions = normalize_source_versions(source_versions)
        source_hash = hashlib.sha256(
            json.dumps(
                normalized_source_versions or {"source_versions": "unknown"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return f"{prefix}:{scope_key}:schema:{schema_version}:sources:{source_hash}"

    @staticmethod
    def redis_ttl_seconds() -> int:
        raw_value = os.getenv("FIN_OPS_COST_STATISTICS_REDIS_TTL_SECONDS", "60").strip()
        try:
            return min(120, max(1, int(raw_value)))
        except ValueError:
            return 60

    def enqueue_read_model_refresh(self, scope_key: str, *, reason: str) -> bool:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not gateway.can_enqueue():
            return False
        enqueued_scope_keys = gateway.enqueue_many(
            "cost_statistics",
            [scope_key],
            reason=reason,
        )
        return bool(enqueued_scope_keys)

    def delete_redis_cache(self, scope_key: str) -> None:
        delete = getattr(self._redis_helper, "delete", None)
        if not callable(delete):
            return
        source_versions = self.expected_source_versions(scope_key)
        delete(self.redis_cache_key(scope_key, source_versions=source_versions))
        delete(self.month_redis_cache_key(scope_key, source_versions=source_versions))
        delete(f"cost_statistics:explorer:{scope_key}")
        delete(f"cost_statistics:month:{scope_key}")

    def read_model_scope_key(
        self,
        month: str,
        project_scope: str,
        *,
        read_model: dict[str, Any] | None = None,
    ) -> str:
        if isinstance(read_model, dict):
            scope_key = str(read_model.get("scope_key", "")).strip()
            if scope_key:
                return scope_key
        scope_key = getattr(self._read_model_service, "scope_key", None)
        if callable(scope_key):
            return str(scope_key(month, project_scope))
        return self.request_scope_key(month, project_scope)

    @staticmethod
    def months_from_workbench_scope_keys(scope_keys: list[str]) -> set[str]:
        months: set[str] = set()
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key).strip()
            if not scope_key:
                continue
            for part in reversed(scope_key.split(":")):
                normalized_part = str(part).strip()
                if normalized_part == "all" or MONTH_RE.match(normalized_part):
                    months.add(normalized_part)
                    break
        return months

    def warmup_months_from_read_model_scope_keys(self, scope_keys: list[str]) -> list[str]:
        months = self.months_from_workbench_scope_keys(scope_keys)
        specific_months = sorted(month for month in months if month != "all")
        if specific_months:
            return specific_months
        if "all" in months:
            return ["all"]
        return []

    def invalidate_read_models(self, *, schedule_warmup: bool = True, persist_empty: bool = True) -> list[str]:
        if self._read_model_service is None:
            return []
        clear = getattr(self._read_model_service, "clear", None)
        snapshot = getattr(self._read_model_service, "snapshot", None)
        if not callable(clear) or not callable(snapshot):
            return []
        deleted_scope_keys = clear()
        if deleted_scope_keys or persist_empty:
            self._persist(
                snapshot=snapshot(),
                changed_scope_keys=deleted_scope_keys,
                operation="invalidate_cost_statistics_read_models",
            )
        if not schedule_warmup:
            return deleted_scope_keys
        warmup_months = self.warmup_months_from_read_model_scope_keys(deleted_scope_keys) or ["all"]
        self.enqueue_refresh_for_months(warmup_months, reason="cost_statistics_read_model_invalidated")
        return deleted_scope_keys

    def invalidate_read_model_scopes(
        self,
        scope_keys: list[str],
        *,
        reason: str = "",
        schedule_warmup: bool = True,
        persist_empty: bool = True,
    ) -> list[str]:
        if self._read_model_service is None:
            return []
        months = self.months_from_workbench_scope_keys(scope_keys)
        if not months:
            return []
        specific_months = sorted(month for month in months if month != "all")
        invalidate_months = getattr(self._read_model_service, "invalidate_months", None)
        snapshot = getattr(self._read_model_service, "snapshot", None)
        if not callable(invalidate_months) or not callable(snapshot):
            return []
        if specific_months:
            deleted_scope_keys = invalidate_months(
                specific_months,
                project_scopes=["active", "all"],
                include_all=True,
            )
            warmup_months = specific_months
        else:
            deleted_scope_keys = invalidate_months(
                [],
                project_scopes=["active", "all"],
                include_all=True,
            )
            warmup_months = ["all"]
        if deleted_scope_keys or persist_empty:
            self._persist(
                snapshot=snapshot(),
                changed_scope_keys=deleted_scope_keys,
                operation=reason or "invalidate_cost_statistics_read_model_scopes",
            )
        if schedule_warmup:
            self.enqueue_refresh_for_months(
                warmup_months,
                reason=reason or "cost_statistics_scope_invalidated",
            )
        return deleted_scope_keys

    def enqueue_refresh_for_months(self, months: list[str], *, reason: str) -> bool:
        enqueued = False
        for target in self.warmup_targets(months=months, project_scopes=["active", "all"]):
            scope_key = target["scope_key"]
            self.delete_redis_cache(scope_key)
            enqueued = self.enqueue_read_model_refresh(scope_key, reason=reason) or enqueued
        return enqueued

    def enqueue_refresh_for_scope_keys(self, scope_keys: list[str], *, reason: str) -> bool:
        enqueued = False
        for scope_key in self.normalize_scope_keys(scope_keys):
            self.delete_redis_cache(scope_key)
            enqueued = self.enqueue_read_model_refresh(scope_key, reason=reason) or enqueued
        return enqueued

    def recover_interrupted_cache_warmup_jobs(self) -> None:
        list_attention_jobs = getattr(self._background_job_service, "list_attention_jobs", None)
        if not callable(list_attention_jobs):
            return
        try:
            attention_jobs = list_attention_jobs("system", include_system=True)
        except Exception:
            return
        for job in attention_jobs:
            if getattr(job, "type", None) != "cost_statistics_cache_warmup":
                continue
            if getattr(job, "error", None) != "interrupted_by_restart":
                continue
            target_scope_keys = self.retry_warmup_scope_keys(job)
            if target_scope_keys:
                self.enqueue_refresh_for_scope_keys(target_scope_keys, reason="startup_recovery")
            self.close_replaced_warmup_job(job, "system", None)

    def find_reusable_warmup_job(self, target_scope_keys: list[str], *, exclude_job_id: str | None = None):
        return None

    def close_replaced_warmup_job(self, old_job: Any, owner_user_id: str, replacement_job: Any) -> None:
        if self._background_job_service is None:
            return
        if replacement_job is None:
            self._background_job_service.acknowledge_job(old_job.job_id, owner_user_id)
            return
        supersede_job = getattr(self._background_job_service, "supersede_job", None)
        if callable(supersede_job):
            supersede_job(
                old_job.job_id,
                owner_user_id,
                superseded_by_job_id=replacement_job.job_id,
            )
            return
        self._background_job_service.acknowledge_job(old_job.job_id, owner_user_id)

    def schedule_cache_warmup(
        self,
        months: list[str],
        reason: str,
        *,
        target_scope_keys: list[str] | None = None,
    ):
        if target_scope_keys is not None:
            self.enqueue_refresh_for_scope_keys(target_scope_keys, reason=reason)
        else:
            self.enqueue_refresh_for_months(months, reason=reason)
        return None

    def run_cache_warmup_job(
        self,
        running_job: Any,
        *,
        months: list[str] | None = None,
        project_scopes: list[str] | None = None,
        targets: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        if self._background_job_service is None:
            return self.warmup_result_summary(
                target_scope_keys=[],
                warmed_scope_keys=[],
                failed_scope_keys=[],
                remaining_scope_keys=[],
            )
        resolved_targets = (
            list(targets or [])
            if targets is not None
            else self.warmup_targets(
                months=months or [],
                project_scopes=project_scopes or ["active", "all"],
            )
        )
        target_scope_keys = [target["scope_key"] for target in resolved_targets]
        self.enqueue_refresh_for_scope_keys(target_scope_keys, reason="legacy_cost_statistics_refresh_bridge")
        result_summary = self.warmup_result_summary(
            target_scope_keys=target_scope_keys,
            warmed_scope_keys=[],
            failed_scope_keys=target_scope_keys,
            remaining_scope_keys=[],
        )
        self._background_job_service.succeed_job(
            running_job.job_id,
            "成本统计缓存预热旧路径已停用，请等待 cost_statistics.read_model.refresh。",
            result_summary=result_summary,
            status="partial_success" if target_scope_keys else "succeeded",
        )
        return result_summary

    def rebuild_read_model_scope(self, scope_key: str) -> dict[str, Any]:
        parsed = self.parse_scope_key(scope_key)
        if parsed is None:
            raise ValueError("cost statistics read model scope_key must be project_scope:month.")
        raise RuntimeError("cost statistics read model refresh must use CostStatisticsReadModelRefreshService.")

    def warmup_targets(
        self,
        *,
        months: list[str],
        project_scopes: list[str],
        target_scope_keys: list[str] | None = None,
    ) -> list[dict[str, str]]:
        if target_scope_keys is not None:
            targets: list[dict[str, str]] = []
            for scope_key in self.normalize_scope_keys(target_scope_keys):
                parsed = self.parse_scope_key(scope_key)
                if parsed is None:
                    continue
                project_scope, month = parsed
                targets.append({"month": month, "project_scope": project_scope, "scope_key": scope_key})
            return targets

        normalized_months = {
            str(month).strip()
            for month in list(months or [])
            if str(month).strip()
        }
        ordered_months = sorted((month for month in normalized_months if month != "all"), reverse=True)
        if "all" in normalized_months:
            ordered_months.append("all")
        deduped_months = list(dict.fromkeys(ordered_months))
        normalized_project_scopes = [
            str(project_scope).strip()
            for project_scope in list(project_scopes or [])
            if str(project_scope).strip() in PROJECT_SCOPES
        ]
        targets = []
        for month in deduped_months:
            if month != "all" and not MONTH_RE.match(month):
                continue
            for project_scope in normalized_project_scopes:
                scope_key = self.read_model_scope_key(month, project_scope)
                targets.append({"month": month, "project_scope": project_scope, "scope_key": scope_key})
        return targets

    def normalize_scope_keys(self, scope_keys: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key or "").strip()
            parsed = self.parse_scope_key(scope_key)
            if parsed is None:
                continue
            project_scope, month = parsed
            resolved_scope_key = self.read_model_scope_key(month, project_scope)
            if resolved_scope_key not in normalized:
                normalized.append(resolved_scope_key)
        return normalized

    @classmethod
    def refresh_scope_keys_from_scope_keys(cls, scope_keys: list[str]) -> list[str]:
        raw_scope_keys = [
            str(scope_key or "").strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key or "").strip()
        ]
        if not raw_scope_keys:
            return []
        parsed_scope_keys: list[str] = []
        all_parseable = True
        for scope_key in raw_scope_keys:
            parsed = cls.parse_scope_key(scope_key)
            if parsed is None:
                all_parseable = False
                break
            project_scope, month = parsed
            resolved_scope_key = cls.request_scope_key(month, project_scope)
            if resolved_scope_key not in parsed_scope_keys:
                parsed_scope_keys.append(resolved_scope_key)
        if all_parseable:
            return parsed_scope_keys

        months = cls.months_from_workbench_scope_keys(raw_scope_keys)
        target_months = sorted(month for month in months if month != "all")
        if "all" in months:
            target_months.append("all")
        return [
            cls.request_scope_key(month, project_scope)
            for month in target_months
            for project_scope in PROJECT_SCOPE_ORDER
        ]

    @staticmethod
    def parse_scope_key(scope_key: str) -> tuple[str, str] | None:
        raw_scope_key = str(scope_key or "").strip()
        if ":" not in raw_scope_key:
            return None
        project_scope, month = raw_scope_key.split(":", 1)
        project_scope = project_scope.strip()
        month = month.strip()
        if project_scope not in PROJECT_SCOPES:
            return None
        if month != "all" and not MONTH_RE.match(month):
            return None
        return project_scope, month

    def job_target_scope_keys(self, job: Any) -> list[str]:
        result_summary = job.result_summary if isinstance(job.result_summary, dict) else {}
        target_scope_keys = self._result_summary_scope_keys(result_summary, "target_scope_keys")
        if target_scope_keys:
            return self.normalize_scope_keys(target_scope_keys)
        affected_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(getattr(job, "affected_scopes", []) or [])
            if str(scope_key).strip()
        ]
        if affected_scope_keys:
            return self.normalize_scope_keys(affected_scope_keys)
        months = self.retry_warmup_months(job)
        return [
            target["scope_key"]
            for target in self.warmup_targets(months=months, project_scopes=["active", "all"])
        ]

    def retry_warmup_scope_keys(self, job: Any) -> list[str]:
        result_summary = job.result_summary if isinstance(job.result_summary, dict) else {}
        failed_scope_keys = self._result_summary_scope_keys(result_summary, "failed_scope_keys")
        remaining_scope_keys = self._result_summary_scope_keys(result_summary, "remaining_scope_keys")
        if getattr(job, "status", None) == "partial_success" and failed_scope_keys:
            return self.normalize_scope_keys(failed_scope_keys)
        if getattr(job, "error", None) == "interrupted_by_restart" and remaining_scope_keys:
            return self.normalize_scope_keys([*remaining_scope_keys, *failed_scope_keys])
        derived_remaining_scope_keys = self.derive_remaining_warmup_scope_keys(job)
        if getattr(job, "error", None) == "interrupted_by_restart" and derived_remaining_scope_keys:
            return self.normalize_scope_keys([*derived_remaining_scope_keys, *failed_scope_keys])
        target_scope_keys = self._result_summary_scope_keys(result_summary, "target_scope_keys")
        if target_scope_keys:
            return self.normalize_scope_keys(target_scope_keys)
        affected_scope_keys = [
            str(scope_key).strip()
            for scope_key in list(getattr(job, "affected_scopes", []) or [])
            if str(scope_key).strip()
        ]
        if affected_scope_keys:
            return self.normalize_scope_keys(affected_scope_keys)
        months = self.retry_warmup_months(job)
        return [
            target["scope_key"]
            for target in self.warmup_targets(months=months, project_scopes=["active", "all"])
        ]

    def derive_remaining_warmup_scope_keys(self, job: Any) -> list[str]:
        result_summary = job.result_summary if isinstance(job.result_summary, dict) else {}
        target_scope_keys = self._result_summary_scope_keys(result_summary, "target_scope_keys")
        if not target_scope_keys:
            return []
        completed_scope_keys = set(
            self.normalize_scope_keys(
                [
                    *self._result_summary_scope_keys(result_summary, "warmed_scope_keys"),
                    *self._result_summary_scope_keys(result_summary, "failed_scope_keys"),
                ]
            )
        )
        return [
            scope_key
            for scope_key in self.normalize_scope_keys(target_scope_keys)
            if scope_key not in completed_scope_keys
        ]

    @staticmethod
    def retry_warmup_months(job: Any) -> list[str]:
        source = job.source if isinstance(job.source, dict) else {}
        candidates = [
            getattr(job, "affected_months", []),
            source.get("affected_months"),
            source.get("months"),
            source.get("month"),
        ]
        months: list[str] = []
        for candidate in candidates:
            values = candidate if isinstance(candidate, (list, tuple, set)) else [candidate]
            for value in values:
                month = str(value or "").strip()
                if not month:
                    continue
                if month == "all" or MONTH_RE.match(month):
                    months.append(month)
        return list(dict.fromkeys(months))

    @staticmethod
    def warmup_result_summary(
        *,
        target_scope_keys: list[str],
        warmed_scope_keys: list[str],
        failed_scope_keys: list[str],
        remaining_scope_keys: list[str],
    ) -> dict[str, Any]:
        return {
            "target_scope_keys": list(target_scope_keys),
            "warmed_scope_keys": list(warmed_scope_keys),
            "failed_scope_keys": list(failed_scope_keys),
            "remaining_scope_keys": list(remaining_scope_keys),
            "warmed": len(warmed_scope_keys),
            "failed": len(failed_scope_keys),
            "total": len(target_scope_keys),
        }

    @staticmethod
    def _result_summary_scope_keys(result_summary: object, field: str) -> list[str]:
        if not isinstance(result_summary, dict):
            return []
        return [
            str(scope_key).strip()
            for scope_key in list(result_summary.get(field) or [])
            if str(scope_key).strip()
        ]

    def _persist(self, *, snapshot: dict[str, Any], changed_scope_keys: list[str] | None, operation: str) -> None:
        if self._persist_read_models is None:
            return
        self._persist_read_models(
            snapshot=snapshot,
            changed_scope_keys=changed_scope_keys,
            operation=operation,
        )
