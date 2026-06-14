from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fin_ops_platform.services.app_status_domain_registry import (
    APP_STATUS_DOMAIN_REGISTRY,
    AppStatusDomainDefinition,
    domains_by_job_type,
)
from fin_ops_platform.services.app_status_dependency_registry import (
    APP_STATUS_DEPENDENCY_REGISTRY,
    AppStatusDependencyDefinition,
)


APP_STATUS_VERSION = 1
ATTENTION_JOB_STATUSES = {"failed", "partial_success"}
ACTIVE_JOB_STATUSES = {"queued", "running"}
BUSY_READ_MODEL_STATUSES = {
    "loading",
    "pending",
    "processing",
    "refreshing",
    "stale",
    "missing",
    "schema_mismatch",
    "source_mismatch",
}
BLOCKED_READ_MODEL_STATUSES = {"failed", "unavailable"}
BUSY_WORKER_STATUSES = {"stale"}
BLOCKED_WORKER_STATUSES = {"missing", "mismatch", "unavailable"}


class AppStatusOverviewService:
    def __init__(
        self,
        *,
        domains: tuple[AppStatusDomainDefinition, ...] = APP_STATUS_DOMAIN_REGISTRY,
        dependency_registry: dict[str, AppStatusDependencyDefinition] = APP_STATUS_DEPENDENCY_REGISTRY,
    ) -> None:
        self._domains = domains
        self._dependency_registry = dependency_registry
        self._domains_by_job_type = domains_by_job_type(domains)
        self._domains_by_key = {domain.key: domain for domain in domains}

    def build_overview(
        self,
        *,
        session: object,
        active_jobs: list[object],
        attention_jobs: list[object],
        app_health_snapshot: dict[str, Any],
        read_model_statuses: dict[str, dict[str, Any]] | None = None,
        worker_statuses: dict[str, dict[str, Any]] | None = None,
        outbox_statuses: dict[str, dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        generated_at = self._generated_at(app_health_snapshot)
        resolved_read_models = (
            read_model_statuses
            if read_model_statuses is not None
            else self._read_model_statuses_from_snapshot(app_health_snapshot)
        )
        resolved_workers = worker_statuses or {}
        resolved_outbox = outbox_statuses or {}
        dependencies = app_health_snapshot.get("dependencies") if isinstance(app_health_snapshot.get("dependencies"), dict) else {}
        all_jobs = self._combine_jobs(active_jobs, attention_jobs)
        tasks = [self._task_payload(job) for job in all_jobs]
        domains = [
            self._domain_payload(
                domain,
                generated_at=generated_at,
                read_model_statuses=resolved_read_models,
                worker_statuses=resolved_workers,
                outbox_statuses=resolved_outbox,
                dependencies=dependencies,
                tasks=tasks,
            )
            for domain in self._domains
        ]
        overall = self._overall_payload(
            session=session,
            domains=domains,
            tasks=tasks,
            dependencies=dependencies,
            alerts=app_health_snapshot.get("alerts"),
            runtime_unavailable_reason=self._runtime_unavailable_reason(
                resolved_read_models,
                resolved_workers,
                resolved_outbox,
            ),
        )
        return {
            "version": APP_STATUS_VERSION,
            "generated_at": generated_at,
            "overall": overall,
            "domains": domains,
            "background_tasks": tasks,
            "alerts": self._active_alerts(app_health_snapshot.get("alerts")),
        }

    def _domain_payload(
        self,
        domain: AppStatusDomainDefinition,
        *,
        generated_at: str,
        read_model_statuses: dict[str, dict[str, Any]],
        worker_statuses: dict[str, dict[str, Any]],
        outbox_statuses: dict[str, dict[str, Any]],
        dependencies: dict[str, Any],
        tasks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        details: list[str] = []
        domain_task_ids = [
            str(task.get("job_id") or "")
            for task in tasks
            if domain.key in set(task.get("affected_domains") or [])
        ]
        read_model_values = [
            self._normalize_status(read_model_statuses.get(key))
            for key in domain.read_model_keys
        ]
        read_model_scopes = self._read_model_scope_payloads(
            read_model_statuses=read_model_statuses,
            domain=domain,
        )
        historical_read_model_scopes = self._historical_read_model_scope_payloads(
            read_model_statuses=read_model_statuses,
            domain=domain,
        )
        worker_values = [
            self._normalize_status(worker_statuses.get(key))
            for key in domain.worker_instances
        ]
        outbox_values = [
            self._normalize_status(outbox_statuses.get(job_type))
            for job_type in domain.job_types
        ]
        dependency_values = [
            self._normalize_dependency_status(key, dependencies.get(key))
            for key in domain.dependencies
        ]
        for key in domain.read_model_keys:
            status_payload = read_model_statuses.get(key) or {}
            if not isinstance(status_payload, dict):
                continue
            reason = str(status_payload.get("last_error") or status_payload.get("reason") or "").strip()
            if reason:
                details.append(reason)
        for scope in read_model_scopes:
            reason = str(scope.get("last_error") or "").strip()
            if reason:
                scope_key = str(scope.get("scope_key") or "").strip()
                details.append(f"{scope_key}: {reason}" if scope_key else reason)
        for key in domain.dependencies:
            dependency = dependencies.get(key)
            if isinstance(dependency, dict):
                message = str(dependency.get("message") or "").strip()
                if message:
                    details.append(message)
            elif key in self._dependency_registry:
                details.append(f"{key} dependency status missing")
        for key in domain.worker_instances:
            worker_payload = worker_statuses.get(key)
            if not isinstance(worker_payload, dict):
                continue
            warning_code = str(worker_payload.get("warning_code") or "").strip()
            if warning_code:
                details.append(warning_code)

        read_model_blocked = any(status in BLOCKED_READ_MODEL_STATUSES for status in read_model_values)
        cost_statistics_local_failure = False
        if domain.key == "cost_statistics":
            read_model_blocked = self._cost_statistics_read_model_blocked(
                read_model_values=read_model_values,
                read_model_scopes=read_model_scopes,
            )
            cost_statistics_local_failure = self._cost_statistics_local_failure(read_model_scopes)

        has_blocked = read_model_blocked
        has_blocked = has_blocked or any(status in BLOCKED_WORKER_STATUSES for status in worker_values)
        has_blocked = has_blocked or any(status == "unavailable" for status in dependency_values)
        has_busy = bool(domain_task_ids)
        has_busy = has_busy or any(status in BUSY_READ_MODEL_STATUSES for status in read_model_values)
        has_busy = has_busy or cost_statistics_local_failure
        has_busy = has_busy or any(status in BUSY_WORKER_STATUSES.union(BLOCKED_WORKER_STATUSES) for status in worker_values)
        has_busy = has_busy or any(status in {"pending", "publishing", "failed"} for status in outbox_values)

        if has_blocked and domain.critical:
            level = "blocked"
            status = (
                (self._cost_statistics_blocked_status(read_model_scopes) if domain.key == "cost_statistics" else None)
                or self._first_status(read_model_values, BLOCKED_READ_MODEL_STATUSES)
                or self._first_status(worker_values, BLOCKED_WORKER_STATUSES)
                or "unavailable"
            )
            reason = f"{domain.label}不可用"
        elif has_busy:
            level = "busy"
            status = (
                (self._cost_statistics_local_failure_status(read_model_scopes) if cost_statistics_local_failure else None)
                or self._first_status(read_model_values, BUSY_READ_MODEL_STATUSES)
                or self._first_status(worker_values, BUSY_WORKER_STATUSES.union(BLOCKED_WORKER_STATUSES))
                or "refreshing"
            )
            reason = (
                "成本统计局部分片需要重试"
                if domain.key == "cost_statistics" and cost_statistics_local_failure
                else f"{domain.label}正在同步"
            )
        else:
            level = "ok"
            status = "ready"
            reason = f"{domain.label}已同步"

        return {
            "key": domain.key,
            "label": domain.label,
            "route": domain.route,
            "level": level,
            "status": status,
            "reason": reason,
            "details": self._unique(details),
            "read_models": list(domain.read_model_keys),
            "read_model_scopes": read_model_scopes,
            "historical_read_model_scopes": historical_read_model_scopes,
            "workers": list(domain.worker_instances),
            "job_ids": [job_id for job_id in domain_task_ids if job_id],
            "updated_at": generated_at,
        }

    def _read_model_scope_payloads(
        self,
        *,
        read_model_statuses: dict[str, dict[str, Any]],
        domain: AppStatusDomainDefinition,
    ) -> list[dict[str, str]]:
        payloads: list[dict[str, str]] = []
        for key in domain.read_model_keys:
            status_payload = read_model_statuses.get(key) or {}
            if not isinstance(status_payload, dict):
                continue
            raw_scopes = status_payload.get("scopes")
            if not isinstance(raw_scopes, list):
                continue
            for raw_scope in raw_scopes:
                if not isinstance(raw_scope, dict):
                    continue
                payloads.append(
                    {
                        "read_model_key": str(raw_scope.get("read_model_key") or key).strip(),
                        "scope_type": str(raw_scope.get("scope_type") or status_payload.get("scope_type") or "").strip(),
                        "scope_key": str(raw_scope.get("scope_key") or "").strip(),
                        "status": self._normalize_status(raw_scope),
                        "last_error": str(raw_scope.get("last_error") or "").strip(),
                        "updated_at": str(raw_scope.get("updated_at") or "").strip(),
                    }
                )
        return payloads

    def _historical_read_model_scope_payloads(
        self,
        *,
        read_model_statuses: dict[str, dict[str, Any]],
        domain: AppStatusDomainDefinition,
    ) -> list[dict[str, str]]:
        payloads: list[dict[str, str]] = []
        for key in domain.read_model_keys:
            status_payload = read_model_statuses.get(key) or {}
            if not isinstance(status_payload, dict):
                continue
            raw_scopes = status_payload.get("historical_scopes")
            if not isinstance(raw_scopes, list):
                continue
            for raw_scope in raw_scopes:
                if not isinstance(raw_scope, dict):
                    continue
                payloads.append(
                    {
                        "read_model_key": str(raw_scope.get("read_model_key") or key).strip(),
                        "scope_type": str(raw_scope.get("scope_type") or status_payload.get("scope_type") or "").strip(),
                        "scope_key": str(raw_scope.get("scope_key") or "").strip(),
                        "status": self._normalize_status(raw_scope),
                        "last_error": str(raw_scope.get("last_error") or "").strip(),
                        "updated_at": str(raw_scope.get("updated_at") or "").strip(),
                        "current_effective": str(raw_scope.get("current_effective") is not False).lower(),
                        "history_reason": str(raw_scope.get("history_reason") or "").strip(),
                    }
                )
        return payloads

    @staticmethod
    def _cost_statistics_read_model_blocked(
        *,
        read_model_values: list[str],
        read_model_scopes: list[dict[str, str]],
    ) -> bool:
        if not read_model_scopes:
            return any(status in BLOCKED_READ_MODEL_STATUSES for status in read_model_values)
        return any(
            AppStatusOverviewService._normalize_status(scope) in BLOCKED_READ_MODEL_STATUSES
            and AppStatusOverviewService._cost_statistics_scope_is_parent(scope)
            for scope in read_model_scopes
        )

    @staticmethod
    def _cost_statistics_local_failure(read_model_scopes: list[dict[str, str]]) -> bool:
        return any(
            AppStatusOverviewService._normalize_status(scope) in BLOCKED_READ_MODEL_STATUSES
            and not AppStatusOverviewService._cost_statistics_scope_is_parent(scope)
            for scope in read_model_scopes
        )

    @staticmethod
    def _cost_statistics_blocked_status(read_model_scopes: list[dict[str, str]]) -> str | None:
        return next(
            (
                AppStatusOverviewService._normalize_status(scope)
                for scope in read_model_scopes
                if AppStatusOverviewService._normalize_status(scope) in BLOCKED_READ_MODEL_STATUSES
                and AppStatusOverviewService._cost_statistics_scope_is_parent(scope)
            ),
            None,
        )

    @staticmethod
    def _cost_statistics_local_failure_status(read_model_scopes: list[dict[str, str]]) -> str | None:
        return next(
            (
                AppStatusOverviewService._normalize_status(scope)
                for scope in read_model_scopes
                if AppStatusOverviewService._normalize_status(scope) in BLOCKED_READ_MODEL_STATUSES
                and not AppStatusOverviewService._cost_statistics_scope_is_parent(scope)
            ),
            None,
        )

    @staticmethod
    def _cost_statistics_scope_is_parent(scope: dict[str, str]) -> bool:
        scope_key = str(scope.get("scope_key") or "").strip()
        if not scope_key:
            return True
        return scope_key in {"active:all", "all:all"} or scope_key.endswith(":all")

    def _task_payload(self, job: object) -> dict[str, Any]:
        raw = self._job_payload(job)
        job_type = str(raw.get("type") or "").strip()
        affected_domains = self._domains_for_job(raw, job_type)
        route = affected_domains[0].route if affected_domains else "/operations/app-health"
        return {
            "job_id": str(raw.get("job_id") or raw.get("jobId") or "").strip(),
            "type": job_type,
            "status": str(raw.get("status") or "").strip(),
            "label": str(raw.get("label") or "后台任务").strip(),
            "short_label": str(raw.get("short_label") or raw.get("shortLabel") or raw.get("message") or raw.get("label") or "后台任务处理中").strip(),
            "message": str(raw.get("message") or "").strip(),
            "phase": str(raw.get("phase") or "").strip(),
            "current": self._int_value(raw.get("current")),
            "total": self._int_value(raw.get("total")),
            "percent": self._percent_value(raw.get("percent")),
            "affected_domains": [domain.key for domain in affected_domains],
            "affected_scopes": self._string_list(raw.get("affected_scopes") or raw.get("affectedScopes")),
            "affected_months": self._string_list(raw.get("affected_months") or raw.get("affectedMonths")),
            "route": route,
            "attention": bool(raw.get("attention")) or str(raw.get("status") or "") in ATTENTION_JOB_STATUSES,
            "updated_at": str(raw.get("updated_at") or raw.get("updatedAt") or raw.get("created_at") or raw.get("createdAt") or "").strip(),
        }

    def _domains_for_job(self, raw: dict[str, Any], job_type: str) -> tuple[AppStatusDomainDefinition, ...]:
        explicit_domain_keys = self._string_list(raw.get("affected_domains") or raw.get("affectedDomains"))
        if explicit_domain_keys:
            explicit_domains = tuple(
                self._domains_by_key[key]
                for key in explicit_domain_keys
                if key in self._domains_by_key
            )
            if explicit_domains:
                return explicit_domains
        return self._domains_for_job_type(job_type)

    def _domains_for_job_type(self, job_type: str) -> tuple[AppStatusDomainDefinition, ...]:
        exact = self._domains_by_job_type.get(job_type)
        if exact:
            return exact
        if job_type == "file_import":
            return tuple(domain for domain in self._domains if domain.key.startswith("imports_"))
        return ()

    def _overall_payload(
        self,
        *,
        session: object,
        domains: list[dict[str, Any]],
        tasks: list[dict[str, Any]],
        dependencies: dict[str, Any],
        alerts: object,
        runtime_unavailable_reason: str,
    ) -> dict[str, Any]:
        if not bool(getattr(session, "allowed", False)) or not bool(getattr(session, "can_access_app", False)):
            write_safety = self._write_safety_payload(
                status="blocked",
                reason="当前账号不可用",
                blockers=["session"],
            )
            return {
                "level": "blocked",
                "color": "red",
                "reason": "当前账号不可用",
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        if runtime_unavailable_reason:
            write_safety = self._write_safety_payload(
                status="blocked",
                reason=runtime_unavailable_reason,
                blockers=["runtime"],
            )
            return {
                "level": "blocked",
                "color": "red",
                "reason": runtime_unavailable_reason,
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        unavailable_dependency = self._first_unavailable_dependency(dependencies)
        if unavailable_dependency:
            write_safety = self._write_safety_payload(
                status="blocked",
                reason=unavailable_dependency,
                blockers=["dependency"],
            )
            return {
                "level": "blocked",
                "color": "red",
                "reason": unavailable_dependency,
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        write_safety = self._write_safety_payload(status="ready", reason="写操作可用", blockers=[])
        blocked_domain = next((domain for domain in domains if domain.get("level") == "blocked"), None)
        if blocked_domain:
            return {
                "level": "blocked",
                "color": "red",
                "reason": str(blocked_domain.get("reason") or "系统状态异常"),
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        if any(str(task.get("status") or "") in ACTIVE_JOB_STATUSES.union(ATTENTION_JOB_STATUSES) for task in tasks):
            return {
                "level": "busy",
                "color": "yellow",
                "reason": "后台任务处理中",
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        busy_domain = next((domain for domain in domains if domain.get("level") == "busy"), None)
        if busy_domain:
            return {
                "level": "busy",
                "color": "yellow",
                "reason": str(busy_domain.get("reason") or "数据正在同步"),
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        if self._active_alerts(alerts):
            return {
                "level": "busy",
                "color": "yellow",
                "reason": "存在运行告警",
                "blocks_mutations": bool(write_safety["blocks_mutations"]),
                "write_safety": write_safety,
            }
        return {
            "level": "ok",
            "color": "green",
            "reason": "系统状态正常",
            "blocks_mutations": bool(write_safety["blocks_mutations"]),
            "write_safety": write_safety,
        }

    @staticmethod
    def _write_safety_payload(*, status: str, reason: str, blockers: list[str]) -> dict[str, Any]:
        normalized_blockers = [str(blocker).strip() for blocker in blockers if str(blocker).strip()]
        return {
            "status": status,
            "reason": reason,
            "blocks_mutations": bool(normalized_blockers),
            "blockers": normalized_blockers,
        }

    @staticmethod
    def _generated_at(snapshot: dict[str, Any]) -> str:
        value = str(snapshot.get("generated_at") or "").strip()
        return value or datetime.now(UTC).isoformat()

    @staticmethod
    def _job_payload(job: object) -> dict[str, Any]:
        if isinstance(job, dict):
            return dict(job)
        to_payload = getattr(job, "to_payload", None)
        if callable(to_payload):
            payload = to_payload()
            if isinstance(payload, dict):
                return dict(payload)
        return {
            "job_id": getattr(job, "job_id", ""),
            "type": getattr(job, "type", ""),
            "status": getattr(job, "status", ""),
            "label": getattr(job, "label", ""),
            "short_label": getattr(job, "short_label", ""),
            "message": getattr(job, "message", ""),
            "phase": getattr(job, "phase", ""),
            "current": getattr(job, "current", 0),
            "total": getattr(job, "total", 0),
            "percent": getattr(job, "percent", 0),
            "affected_scopes": getattr(job, "affected_scopes", []),
            "affected_months": getattr(job, "affected_months", []),
            "updated_at": getattr(job, "updated_at", ""),
        }

    @staticmethod
    def _combine_jobs(active_jobs: list[object], attention_jobs: list[object]) -> list[object]:
        combined: list[object] = []
        seen: set[str] = set()
        for job in [*active_jobs, *attention_jobs]:
            raw = AppStatusOverviewService._job_payload(job)
            job_id = str(raw.get("job_id") or raw.get("jobId") or "").strip()
            if job_id and job_id in seen:
                continue
            if job_id:
                seen.add(job_id)
            combined.append(job)
        return combined

    @staticmethod
    def _read_model_statuses_from_snapshot(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
        statuses: dict[str, dict[str, Any]] = {}
        workbench = snapshot.get("workbench_read_model")
        if isinstance(workbench, dict):
            statuses["workbench"] = {
                "status": AppStatusOverviewService._workbench_status(str(workbench.get("status") or "")),
                "last_error": workbench.get("last_error") or workbench.get("last_matching_error"),
            }
        relation = snapshot.get("workbench_relation_read_model")
        if isinstance(relation, dict):
            statuses["workbench_relation"] = {
                "status": AppStatusOverviewService._workbench_status(str(relation.get("status") or "")),
                "last_error": relation.get("last_failure_reason"),
            }
        return statuses

    @staticmethod
    def _workbench_status(status: str) -> str:
        normalized = status.strip().lower()
        if normalized == "ready":
            return "ready"
        if normalized == "rebuilding":
            return "refreshing"
        if normalized in {"error", "failed", "unavailable"}:
            return "failed"
        if normalized in {"stale", "refreshing", "missing"}:
            return normalized
        return "ready"

    @staticmethod
    def _normalize_status(payload: object) -> str:
        if isinstance(payload, dict):
            value = payload.get("status") or payload.get("read_model_status")
        else:
            value = payload
        return str(value or "ready").strip().lower() or "ready"

    @staticmethod
    def _normalize_dependency_payload(payload: object) -> str:
        if isinstance(payload, dict):
            return str(payload.get("status") or "available").strip().lower() or "available"
        return "available"

    def _normalize_dependency_status(self, key: str, payload: object) -> str:
        if payload is None and key in self._dependency_registry:
            return "unavailable" if self._dependency_registry[key].critical else "degraded"
        return self._normalize_dependency_payload(payload)

    @staticmethod
    def _runtime_unavailable_reason(*status_groups: dict[str, dict[str, Any]]) -> str:
        for statuses in status_groups:
            payload = statuses.get("__runtime__")
            if not isinstance(payload, dict):
                continue
            if AppStatusOverviewService._normalize_status(payload) != "unavailable":
                continue
            reason = str(payload.get("last_error") or payload.get("reason") or "").strip()
            return reason or "运行状态事实源不可用"
        return ""

    @staticmethod
    def _first_status(values: list[str], targets: set[str]) -> str | None:
        return next((value for value in values if value in targets), None)

    def _first_unavailable_dependency(self, dependencies: dict[str, Any]) -> str:
        for key, definition in self._dependency_registry.items():
            if key not in dependencies and definition.critical:
                return f"{key}依赖状态缺失"
        for dependency in dependencies.values():
            if not isinstance(dependency, dict) or dependency.get("status") != "unavailable":
                continue
            message = str(dependency.get("message") or "").strip()
            return message or "系统依赖不可用"
        return ""

    @staticmethod
    def _active_alerts(alerts: object) -> list[dict[str, Any]]:
        if isinstance(alerts, dict) and isinstance(alerts.get("active"), list):
            return [item for item in alerts["active"] if isinstance(item, dict)]
        if isinstance(alerts, list):
            return [item for item in alerts if isinstance(item, dict)]
        return []

    @staticmethod
    def _string_list(value: object) -> list[str]:
        if not isinstance(value, list):
            return []
        return [str(item).strip() for item in value if str(item).strip()]

    @staticmethod
    def _int_value(value: object) -> int:
        try:
            return int(value or 0)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _percent_value(value: object) -> int | None:
        if value is None:
            return None
        try:
            return max(0, min(100, int(value)))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _unique(values: list[str]) -> list[str]:
        return list(dict.fromkeys(value for value in values if value))
