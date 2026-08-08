from __future__ import annotations

import hashlib
from typing import Any

from fin_ops_platform.services.background_job_service import BackgroundJob, BackgroundJobService
from fin_ops_platform.services.postgres_repositories.settings_data_reset_request import (
    SettingsDataResetAlreadyActive,
    SettingsDataResetIdempotencyConflict,
)
from fin_ops_platform.services.settings_data_reset_job import SETTINGS_DATA_RESET_REQUESTED_EVENT


class SettingsDataResetEnqueueError(RuntimeError):
    def __init__(self, job: BackgroundJob, cause: Exception) -> None:
        super().__init__(str(cause))
        self.job = job


class SettingsDataResetRequestService:
    def __init__(
        self,
        *,
        background_jobs: BackgroundJobService,
        queue_repository: Any,
        atomic_repository: Any | None = None,
    ) -> None:
        self._background_jobs = background_jobs
        self._queue = queue_repository
        self._atomic_repository = atomic_repository

    def request(
        self,
        *,
        action: str,
        owner_user_id: str,
        idempotency_key: str,
        label: str,
    ) -> tuple[BackgroundJob, bool]:
        normalized_key = str(idempotency_key or "").strip()
        if not normalized_key:
            raise ValueError("idempotency_key is required.")
        fingerprint = hashlib.sha256(str(action).encode("utf-8")).hexdigest()
        job_options = {
            "job_type": "settings_data_reset",
            "label": label,
            "owner_user_id": owner_user_id,
            "visibility": "system",
            "phase": "queued",
            "current": 1,
            "total": 100,
            "message": "数据重置任务已排队。",
            "result_summary": {"action": action},
            "idempotency_key": normalized_key,
            "source": {"action": action},
            "affected_scopes": ["settings", "workbench"],
        }

        if self._atomic_repository is not None:
            candidate = self._background_jobs.build_job(**job_options)
            payload, created = self._atomic_repository.create_or_get(
                job_payload=candidate.to_payload(),
                request_fingerprint=fingerprint,
                event_type=SETTINGS_DATA_RESET_REQUESTED_EVENT,
                action=action,
            )
            return self._background_jobs.job_from_payload(payload), created

        for active in self._background_jobs.list_active_jobs(owner_user_id, include_system=True):
            if active.type != "settings_data_reset" or active.status not in {"queued", "running"}:
                continue
            if active.idempotency_key == normalized_key:
                self._assert_same_action(active, action)
                return active, False
            raise SettingsDataResetAlreadyActive(active.to_payload())

        job, created = self._background_jobs.create_or_get_idempotent_job_with_created(
            **job_options,
            reuse_any_status=True,
        )
        self._assert_same_action(job, action)
        if not created:
            return job, False
        try:
            self._queue.enqueue(
                event_type=SETTINGS_DATA_RESET_REQUESTED_EVENT,
                aggregate_type="settings_data_reset",
                aggregate_id=job.job_id,
                scope_type="settings",
                scope_key=action,
                dedupe_key=f"settings-data-reset:{job.job_id}",
                priority="urgent",
                payload={"job_id": job.job_id, "owner_user_id": owner_user_id, "action": action},
            )
        except Exception as exc:
            self._background_jobs.fail_job(job.job_id, "数据重置任务入队失败。", str(exc))
            failed_job = self._background_jobs.get_job(job.job_id, owner_user_id)
            raise SettingsDataResetEnqueueError(failed_job, exc) from exc
        return job, True

    @staticmethod
    def _assert_same_action(job: BackgroundJob, action: str) -> None:
        if str(job.source.get("action") or "") != action:
            raise SettingsDataResetIdempotencyConflict(
                "The idempotency key was already used for a different reset request."
            )
