from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Callable

from fin_ops_platform.services.workbench_reconciliation_models import expand_scope_month_window


DEFAULT_DIRTY_DEBOUNCE_SECONDS = 60
DEFAULT_LEASE_TIMEOUT_SECONDS = 600
DEFAULT_RETRY_MAX_ATTEMPTS = 5
DEFAULT_RETRY_BACKOFF_SECONDS = (60, 300, 900, 1800, 3600)


def _utc_now() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True, slots=True)
class WorkbenchReconciliationDirtyQueueOptions:
    dirty_debounce_seconds: int = DEFAULT_DIRTY_DEBOUNCE_SECONDS
    lease_timeout_seconds: int = DEFAULT_LEASE_TIMEOUT_SECONDS
    retry_max_attempts: int = DEFAULT_RETRY_MAX_ATTEMPTS
    retry_backoff_seconds: tuple[int, ...] = DEFAULT_RETRY_BACKOFF_SECONDS
    now: Callable[[], datetime] = _utc_now


class WorkbenchReconciliationDirtyQueue:
    def __init__(
        self,
        repository: Any | None = None,
        *,
        tenant_id: str = "default",
        options: WorkbenchReconciliationDirtyQueueOptions | None = None,
    ) -> None:
        self._repository = repository
        self._tenant_id = str(tenant_id or "default")
        self._options = options or WorkbenchReconciliationDirtyQueueOptions()
        self._scopes: dict[str, dict[str, Any]] = {}
        self._runs: list[dict[str, Any]] = []

    def mark_dirty_expanded(
        self,
        months: list[str],
        *,
        reason: str,
        source_versions: dict[str, object] | None = None,
    ) -> list[str]:
        expanded = sorted({expanded for month in months for expanded in expand_scope_month_window(str(month))})
        if self._repository is not None:
            return self._repository.mark_workbench_matching_dirty_scopes(
                tenant_id=self._tenant_id,
                scope_months=expanded,
                reason=reason,
                source_versions=source_versions or {},
                debounce_seconds=self._options.dirty_debounce_seconds,
            )
        available_at = self._now() + timedelta(seconds=self._options.dirty_debounce_seconds)
        for scope_month in expanded:
            entry = self._scopes.get(scope_month)
            if entry is None:
                entry = {
                    "tenant_id": self._tenant_id,
                    "scope_month": scope_month,
                    "status": "dirty",
                    "attempt_count": 0,
                    "reasons": [],
                    "last_error": None,
                    "available_at": available_at,
                    "lease_owner": None,
                    "lease_expires_at": None,
                    "request_id": None,
                    "started_at": None,
                    "completed_at": None,
                    "failed_at": None,
                    "duration_ms": None,
                    "source_versions": {},
                    "error_summary": None,
                }
                self._scopes[scope_month] = entry
            entry["status"] = "dirty"
            entry["available_at"] = max(entry["available_at"], available_at)
            entry["lease_owner"] = None
            entry["lease_expires_at"] = None
            if reason and reason not in entry["reasons"]:
                entry["reasons"].append(reason)
            entry["source_versions"] = {**entry.get("source_versions", {}), **(source_versions or {})}
        return expanded

    def claim_due_scopes(
        self,
        *,
        worker_id: str,
        limit: int,
        lease_seconds: int | None = None,
        request_id: str | None = None,
    ) -> list[str]:
        resolved_lease_seconds = lease_seconds or self._options.lease_timeout_seconds
        if self._repository is not None:
            return self._repository.claim_workbench_matching_dirty_scopes(
                tenant_id=self._tenant_id,
                worker_id=worker_id,
                limit=limit,
                lease_seconds=resolved_lease_seconds,
                request_id=request_id,
            )
        now = self._now()
        claimed: list[str] = []
        for scope_month, entry in sorted(self._scopes.items()):
            if len(claimed) >= max(0, limit):
                break
            if not self._is_claimable(entry, now):
                continue
            entry["status"] = "processing"
            entry["lease_owner"] = worker_id
            entry["lease_expires_at"] = now + timedelta(seconds=resolved_lease_seconds)
            entry["request_id"] = request_id or f"{worker_id}:{scope_month}:{int(now.timestamp())}"
            entry["started_at"] = now
            entry["completed_at"] = None
            entry["failed_at"] = None
            entry["duration_ms"] = None
            entry["error_summary"] = None
            self._runs.append(
                {
                    "scope_month": scope_month,
                    "request_id": entry["request_id"],
                    "started_at": now,
                    "completed_at": None,
                    "failed_at": None,
                    "duration_ms": None,
                    "status": "running",
                    "source_versions": deepcopy(entry.get("source_versions") or {}),
                    "error_summary": None,
                }
            )
            claimed.append(scope_month)
        return claimed

    def complete(self, scope_month: str, *, source_versions: dict[str, object]) -> None:
        if self._repository is not None:
            self._repository.complete_workbench_matching_dirty_scope(
                tenant_id=self._tenant_id,
                scope_month=scope_month,
                source_versions=source_versions,
            )
            return
        entry = self._require_scope(scope_month)
        now = self._now()
        entry["status"] = "completed"
        entry["completed_at"] = now
        entry["failed_at"] = None
        entry["source_versions"] = dict(source_versions)
        entry["lease_owner"] = None
        entry["lease_expires_at"] = None
        entry["duration_ms"] = _duration_ms(entry.get("started_at"), now)
        self._finish_run(scope_month, status="completed", at=now, source_versions=source_versions, error=None)

    def fail(self, scope_month: str, *, error: str, retry_delay_seconds: int | None = None) -> None:
        if self._repository is not None:
            self._repository.fail_workbench_matching_dirty_scope(
                tenant_id=self._tenant_id,
                scope_month=scope_month,
                error=error,
                retry_delay_seconds=retry_delay_seconds,
                retry_max_attempts=self._options.retry_max_attempts,
                retry_backoff_seconds=list(self._options.retry_backoff_seconds),
            )
            return
        entry = self._require_scope(scope_month)
        now = self._now()
        entry["attempt_count"] = int(entry.get("attempt_count") or 0) + 1
        entry["last_error"] = error
        entry["failed_at"] = now
        entry["completed_at"] = None
        entry["duration_ms"] = _duration_ms(entry.get("started_at"), now)
        entry["lease_owner"] = None
        entry["lease_expires_at"] = None
        entry["error_summary"] = error
        if entry["attempt_count"] >= self._options.retry_max_attempts:
            entry["status"] = "failed"
        else:
            entry["status"] = "retry"
            entry["available_at"] = now + timedelta(seconds=retry_delay_seconds or self._retry_backoff(entry["attempt_count"]))
        self._finish_run(scope_month, status="failed", at=now, source_versions=entry.get("source_versions") or {}, error=error)

    def list_dirty_scopes(self) -> list[dict[str, Any]]:
        if self._repository is not None:
            return self._repository.list_workbench_matching_dirty_scopes(tenant_id=self._tenant_id)
        return [deepcopy(self._scopes[key]) for key in sorted(self._scopes)]

    def get_dirty_scope(self, scope_month: str) -> dict[str, Any]:
        return deepcopy(self._require_scope(scope_month))

    def list_matching_runs(self) -> list[dict[str, Any]]:
        if self._repository is not None:
            return self._repository.list_workbench_matching_runs(tenant_id=self._tenant_id)
        return deepcopy(self._runs)

    def _is_claimable(self, entry: dict[str, Any], now: datetime) -> bool:
        if entry.get("status") in {"dirty", "retry"}:
            return entry.get("available_at") <= now
        if entry.get("status") == "processing":
            lease_expires_at = entry.get("lease_expires_at")
            return lease_expires_at is not None and lease_expires_at <= now
        return False

    def _retry_backoff(self, attempt_count: int) -> int:
        if not self._options.retry_backoff_seconds:
            return 0
        index = min(max(attempt_count - 1, 0), len(self._options.retry_backoff_seconds) - 1)
        return self._options.retry_backoff_seconds[index]

    def _require_scope(self, scope_month: str) -> dict[str, Any]:
        try:
            return self._scopes[scope_month]
        except KeyError as exc:
            raise KeyError(f"Unknown dirty scope: {scope_month}") from exc

    def _finish_run(
        self,
        scope_month: str,
        *,
        status: str,
        at: datetime,
        source_versions: dict[str, object],
        error: str | None,
    ) -> None:
        for run in reversed(self._runs):
            if run.get("scope_month") == scope_month and run.get("status") == "running":
                if status == "completed":
                    run["completed_at"] = at
                else:
                    run["failed_at"] = at
                run["duration_ms"] = _duration_ms(run.get("started_at"), at)
                run["status"] = status
                run["source_versions"] = dict(source_versions)
                run["error_summary"] = error
                return

    def _now(self) -> datetime:
        value = self._options.now()
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _duration_ms(started_at: object, finished_at: datetime) -> int | None:
    if not isinstance(started_at, datetime):
        return None
    return int((finished_at - started_at).total_seconds() * 1000)
