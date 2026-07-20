from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from time import sleep as default_sleep
from typing import Any
from uuid import uuid4


MATCHING_SOURCE_VERSIONS_CHANGED_REASON = "matching_source_versions_changed"


def _default_request_id() -> str:
    return f"workbench-dirty-{uuid4().hex}"


@dataclass(frozen=True)
class WorkbenchMatchingDirtyScopeWorkerConfig:
    worker_id: str
    worker_kind: str = "workbench-matching"
    poll_interval_seconds: float = 5.0
    batch_size: int = 10
    lease_seconds: int = 600
    retry_delay_seconds: int | None = None
    max_iterations: int | None = None
    request_id_factory: Callable[[], str] = field(default_factory=lambda: _default_request_id)

    def __post_init__(self) -> None:
        if not str(self.worker_id or "").strip():
            raise ValueError("worker_id is required.")
        if not str(self.worker_kind or "").strip():
            raise ValueError("worker_kind is required.")
        if self.poll_interval_seconds < 0:
            raise ValueError("poll_interval_seconds must be zero or positive.")
        if self.batch_size <= 0:
            raise ValueError("batch_size must be positive.")
        if self.lease_seconds <= 0:
            raise ValueError("lease_seconds must be positive.")
        if self.retry_delay_seconds is not None and self.retry_delay_seconds <= 0:
            raise ValueError("retry_delay_seconds must be positive when provided.")
        if self.max_iterations is not None and self.max_iterations < 0:
            raise ValueError("max_iterations must be zero or positive when provided.")


class WorkbenchMatchingDirtyScopeWorker:
    def __init__(
        self,
        *,
        dirty_queue: Any,
        matching_orchestrator: Any,
        source_versions_provider: Callable[[], dict[str, object]],
        heartbeat_recorder: Any,
        config: WorkbenchMatchingDirtyScopeWorkerConfig,
        sleep: Callable[[float], None] = default_sleep,
    ) -> None:
        self._dirty_queue = dirty_queue
        self._matching_orchestrator = matching_orchestrator
        self._source_versions_provider = source_versions_provider
        self._heartbeat_recorder = heartbeat_recorder
        self._config = config
        self._sleep = sleep

    def run_once(self) -> dict[str, object]:
        request_id = str(self._config.request_id_factory()).strip()
        if not request_id:
            request_id = _default_request_id()
        source_versions = dict(self._source_versions_provider() or {})
        stale_completed_scope_months = self._mark_stale_completed_scopes(source_versions)
        summary: dict[str, object] = {
            "request_id": request_id,
            "scope_months": [],
            "stale_completed_scope_months": stale_completed_scope_months,
            "processed_months": [],
            "failed_months": [],
            "planned_relation_count": 0,
            "created_relation_count": 0,
            "extended_relation_count": 0,
            "enriched_relation_count": 0,
            "ambiguous_etc_batch_link_count": 0,
            "unowned_etc_batch_link_count": 0,
            "blocked_count": 0,
        }
        self._record_heartbeat(
            "polling",
            {
                "batch_size": self._config.batch_size,
                "lease_seconds": self._config.lease_seconds,
                "stale_completed_scope_count": len(stale_completed_scope_months),
            },
        )
        scope_months = self._dirty_queue.claim_due_scopes(
            worker_id=self._config.worker_id,
            limit=self._config.batch_size,
            lease_seconds=self._config.lease_seconds,
            request_id=request_id,
        )
        summary["scope_months"] = list(scope_months)
        if not scope_months:
            self._record_heartbeat("idle", {"claimed_scope_count": 0})
            return summary

        self._record_heartbeat(
            "processing",
            {
                "request_id": request_id,
                "scope_months": list(scope_months),
                "claimed_scope_count": len(scope_months),
            },
        )
        for scope_month in scope_months:
            self._process_scope(scope_month, request_id=request_id, source_versions=source_versions, summary=summary)

        if summary["failed_months"]:
            self._record_heartbeat(
                "failed",
                {
                    "request_id": request_id,
                    "processed_months": list(summary["processed_months"]),
                    "failed_months": list(summary["failed_months"]),
                },
            )
        else:
            self._record_heartbeat(
                "idle",
                {
                    "request_id": request_id,
                    "processed_months": list(summary["processed_months"]),
                    "created_relation_count": summary["created_relation_count"],
                },
            )
        return summary

    def run_forever(self) -> None:
        iterations = 0
        while self._config.max_iterations is None or iterations < self._config.max_iterations:
            try:
                self.run_once()
            except Exception as exc:
                self._record_heartbeat("failed", {"phase": "iteration", "error": str(exc)})
            iterations += 1
            if self._config.max_iterations is not None and iterations >= self._config.max_iterations:
                return
            self._sleep(max(float(self._config.poll_interval_seconds), 0.0))

    def _mark_stale_completed_scopes(self, source_versions: dict[str, object]) -> list[str]:
        if not source_versions:
            return []
        marker = getattr(self._dirty_queue, "mark_stale_completed_scopes", None)
        if not callable(marker):
            return []
        return list(
            marker(
                source_versions=source_versions,
                reason=MATCHING_SOURCE_VERSIONS_CHANGED_REASON,
                debounce_seconds=0,
                limit=self._config.batch_size,
            )
            or []
        )

    def _process_scope(
        self,
        scope_month: str,
        *,
        request_id: str,
        source_versions: dict[str, object],
        summary: dict[str, object],
    ) -> None:
        scope_request_id = f"{request_id}:{scope_month}"
        try:
            run_summary = self._matching_orchestrator.run(
                changed_scope_months=[scope_month],
                reason="dirty_scope_retry",
                request_id=scope_request_id,
            ) or {}
            self._dirty_queue.complete(
                scope_month,
                source_versions=source_versions,
                worker_id=self._config.worker_id,
                request_id=scope_request_id,
            )
            processed_months = list(summary["processed_months"])
            processed_months.append(scope_month)
            summary["processed_months"] = processed_months
            for count_key in (
                "planned_relation_count",
                "created_relation_count",
                "extended_relation_count",
                "enriched_relation_count",
                "ambiguous_etc_batch_link_count",
                "unowned_etc_batch_link_count",
                "blocked_count",
            ):
                summary[count_key] = int(summary.get(count_key) or 0) + int(run_summary.get(count_key) or 0)
        except Exception as exc:
            self._dirty_queue.fail(
                scope_month,
                error=str(exc),
                retry_delay_seconds=self._config.retry_delay_seconds,
                worker_id=self._config.worker_id,
                request_id=scope_request_id,
            )
            failed_months = list(summary["failed_months"])
            failed_months.append(scope_month)
            summary["failed_months"] = failed_months

    def _record_heartbeat(self, status: str, payload: dict[str, object]) -> None:
        record = getattr(self._heartbeat_recorder, "record_worker_heartbeat", None)
        if callable(record):
            record(self._config.worker_id, self._config.worker_kind, status, payload=payload)
            return
        if callable(self._heartbeat_recorder):
            self._heartbeat_recorder(self._config.worker_id, self._config.worker_kind, status, payload=payload)


class WorkbenchMatchingScopeRunnerAdapter:
    def __init__(self, run_matching_for_scopes: Callable[..., dict[str, object] | None]) -> None:
        self._run_matching_for_scopes = run_matching_for_scopes

    def run(
        self,
        *,
        changed_scope_months: list[str],
        reason: str,
        request_id: str,
        progress_callback: Callable[[dict[str, object]], None] | None = None,
    ) -> dict[str, object] | None:
        kwargs: dict[str, object] = {
            "reason": reason,
            "request_id": request_id,
            "requeue_on_error": False,
            "raise_on_error": True,
        }
        if progress_callback is not None:
            kwargs["progress_callback"] = progress_callback
        return self._run_matching_for_scopes(
            changed_scope_months,
            **kwargs,
        )
