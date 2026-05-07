from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any


APP_HEALTH_SCHEMA_VERSION = 1
REBUILD_JOB_TYPES = {
    "workbench_rebuild",
    "workbench_read_model_rebuild",
    "oa_sync_workbench_rebuild",
}


class AppHealthService:
    def build_snapshot(
        self,
        *,
        session: object,
        active_jobs: list[object],
        oa_sync_payload: dict[str, Any],
        state_store_info: dict[str, Any],
        rebuild_scheduled: bool,
        duration_ms: float,
        alerts: dict[str, list[dict[str, Any]]] | None = None,
        generated_at: datetime | None = None,
    ) -> dict[str, Any]:
        now = generated_at or datetime.now(UTC)
        running_jobs = [job for job in active_jobs if getattr(job, "status", None) == "running"]
        queued_jobs = [job for job in active_jobs if getattr(job, "status", None) == "queued"]
        attention_jobs = [
            job
            for job in active_jobs
            if getattr(job, "status", None) in {"failed", "partial_success"}
        ]
        rebuild_jobs = [
            job
            for job in active_jobs
            if getattr(job, "status", None) in {"queued", "running"}
            and self.is_workbench_read_model_rebuild_job(job)
        ]
        matching_dirty_scope_entries = self.matching_dirty_scope_entries(oa_sync_payload)
        matching_dirty_scopes = [
            str(entry.get("scope_month"))
            for entry in matching_dirty_scope_entries
            if str(entry.get("scope_month") or "").strip()
        ]
        matching_running_scopes = self.matching_running_scopes(oa_sync_payload)
        dirty_scopes = sorted(dict.fromkeys([*self.dirty_scopes(oa_sync_payload), *matching_dirty_scopes]))
        oa_sync_status = str(oa_sync_payload.get("status") or "").strip()
        oa_sync_unavailable = oa_sync_status == "error"
        rebuilding = bool(rebuild_jobs) or rebuild_scheduled or bool(matching_running_scopes)
        if oa_sync_unavailable:
            workbench_read_model_status = "error"
        elif rebuilding:
            workbench_read_model_status = "rebuilding"
        elif dirty_scopes:
            workbench_read_model_status = "stale"
        else:
            workbench_read_model_status = "ready"

        session_blocked = not bool(getattr(session, "allowed", False)) or not bool(getattr(session, "can_access_app", False))
        dependencies = {
            "oa_identity": {"status": "available"},
            "oa_sync": {
                "status": "unavailable" if oa_sync_unavailable else "available",
                "message": oa_sync_payload.get("message"),
            },
            "background_jobs": {"status": "available"},
            "state_store": {
                "status": "available",
                "storage_mode": state_store_info.get("storage_mode", "memory"),
                "backend": state_store_info.get("backend", "memory"),
            },
        }
        dependency_unavailable = any(
            isinstance(dependency, dict) and dependency.get("status") == "unavailable"
            for dependency in dependencies.values()
        )
        if session_blocked or dependency_unavailable:
            status = "blocked"
        elif dirty_scopes or rebuilding or running_jobs or queued_jobs:
            status = "busy"
        else:
            status = "ok"

        dirty_scope_ages = self.dirty_scope_ages(oa_sync_payload, dirty_scopes)
        rebuild_running_seconds = [
            self.seconds_since(getattr(job, "started_at", None) or getattr(job, "created_at", None), now)
            for job in rebuild_jobs
            if getattr(job, "status", None) == "running"
        ]
        metrics = {
            "app_health_duration_ms": round(float(duration_ms), 2),
            "dirty_scope_count": len(dirty_scopes),
            "workbench_matching_dirty_scope_count": len(matching_dirty_scopes),
            "dirty_scope_age_seconds": dirty_scope_ages,
            "dirty_scope_age_seconds_max": max(dirty_scope_ages.values(), default=0),
            "workbench_rebuild_running_seconds_max": round(max(rebuild_running_seconds, default=0), 2),
            "background_jobs_active_count": len(active_jobs),
            "background_jobs_running_count": len(running_jobs),
            "background_jobs_attention_count": len(attention_jobs),
            "active_alert_count": len((alerts or {}).get("active", [])),
        }
        return {
            "version": APP_HEALTH_SCHEMA_VERSION,
            "status": status,
            "generated_at": now.isoformat(),
            "session": self._session_payload(session, blocked=session_blocked),
            "oa_sync": oa_sync_payload,
            "workbench_read_model": {
                "status": workbench_read_model_status,
                "dirty_scopes": dirty_scopes,
                "matching_dirty_scopes": matching_dirty_scope_entries,
                "matching_running_scopes": matching_running_scopes,
                "last_matching_error": self.last_matching_error(matching_dirty_scope_entries),
                "rebuild_job_ids": [str(getattr(job, "job_id", "")) for job in rebuild_jobs],
            },
            "background_jobs": {
                "active": len(active_jobs),
                "queued": len(queued_jobs),
                "running": len(running_jobs),
                "attention": len(attention_jobs),
                "jobs": [self._job_payload(job) for job in active_jobs],
            },
            "dependencies": dependencies,
            "metrics": metrics,
            "alerts": alerts or {"active": [], "recent_recovered": []},
        }

    @staticmethod
    def dirty_scopes(oa_sync_payload: dict[str, Any]) -> list[str]:
        return [
            str(scope)
            for scope in list(oa_sync_payload.get("dirty_scopes", []) or [])
            if str(scope).strip()
        ]

    @staticmethod
    def matching_dirty_scope_entries(oa_sync_payload: dict[str, Any]) -> list[dict[str, Any]]:
        entries = oa_sync_payload.get("workbench_matching_dirty_scopes")
        if not isinstance(entries, list):
            return []
        return [entry for entry in entries if isinstance(entry, dict)]

    @staticmethod
    def matching_running_scopes(oa_sync_payload: dict[str, Any]) -> list[str]:
        return [
            str(scope).strip()
            for scope in list(oa_sync_payload.get("workbench_matching_running_scopes") or [])
            if str(scope).strip()
        ]

    @staticmethod
    def last_matching_error(entries: list[dict[str, Any]]) -> str | None:
        for entry in reversed(entries):
            error = str(entry.get("last_error") or "").strip()
            if error:
                return error
        return None

    @staticmethod
    def dirty_scope_ages(oa_sync_payload: dict[str, Any], dirty_scopes: list[str]) -> dict[str, float]:
        raw_ages = oa_sync_payload.get("dirty_scope_age_seconds")
        if isinstance(raw_ages, dict):
            return {
                scope: max(0.0, AppHealthService._as_float(raw_ages.get(scope)))
                for scope in dirty_scopes
            }
        lag_seconds = max(0.0, AppHealthService._as_float(oa_sync_payload.get("lag_seconds")))
        return {scope: lag_seconds for scope in dirty_scopes}

    @staticmethod
    def is_workbench_read_model_rebuild_job(job: object) -> bool:
        job_type = str(getattr(job, "type", "") or "").strip().lower()
        return job_type in REBUILD_JOB_TYPES or ("workbench" in job_type and "rebuild" in job_type)

    @staticmethod
    def serialize_sse_event(event: str, payload: dict[str, Any]) -> str:
        return f"event: {event}\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"

    @staticmethod
    def seconds_since(value: object, now: datetime | None = None) -> float:
        if not value:
            return 0.0
        try:
            parsed = datetime.fromisoformat(str(value))
        except ValueError:
            return 0.0
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=UTC)
        current_time = now or datetime.now(UTC)
        if current_time.tzinfo is None:
            current_time = current_time.replace(tzinfo=UTC)
        return max(0.0, (current_time.astimezone(UTC) - parsed.astimezone(UTC)).total_seconds())

    @staticmethod
    def _session_payload(session: object, *, blocked: bool) -> dict[str, Any]:
        identity = getattr(session, "identity", None)
        return {
            "status": "blocked" if blocked else "authenticated",
            "user": {
                "user_id": getattr(identity, "user_id", None),
                "username": getattr(identity, "username", None),
                "display_name": getattr(identity, "display_name", None),
            },
            "allowed": bool(getattr(session, "allowed", False)),
            "access_tier": getattr(session, "access_tier", None),
            "can_access_app": bool(getattr(session, "can_access_app", False)),
            "can_mutate_data": bool(getattr(session, "can_mutate_data", False)),
            "can_admin_access": bool(getattr(session, "can_admin_access", False)),
        }

    @staticmethod
    def _job_payload(job: object) -> dict[str, Any]:
        to_payload = getattr(job, "to_payload", None)
        if callable(to_payload):
            payload = to_payload()
            if isinstance(payload, dict):
                return payload
        return {
            "job_id": getattr(job, "job_id", None),
            "type": getattr(job, "type", None),
            "label": getattr(job, "label", None),
            "status": getattr(job, "status", None),
            "created_at": getattr(job, "created_at", None),
            "started_at": getattr(job, "started_at", None),
            "updated_at": getattr(job, "updated_at", None),
        }

    @staticmethod
    def _as_float(value: object) -> float:
        try:
            return float(value)
        except (TypeError, ValueError):
            return 0.0
