from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.background_job_service import (
    TERMINAL_BACKGROUND_JOB_STATUSES,
    BackgroundJobService,
)
from fin_ops_platform.services.settings_data_reset_service import (
    RESET_OA_AND_REBUILD_ACTION,
)


SETTINGS_DATA_RESET_REQUESTED_EVENT = "settings.data_reset.requested"


class SettingsDataResetJobHandler:
    """Executes one durable settings reset event outside the API process."""

    def __init__(
        self,
        *,
        reset_executor: Callable[..., Any],
        supported_actions: set[str],
        background_jobs: BackgroundJobService,
        scope_months_provider: Callable[[], list[str]],
        lifecycle_executor: Callable[[list[str], str], dict[str, object]],
        runtime_reload_request: Callable[[], None] | None = None,
        audit_recorder: Callable[..., Any] | None = None,
    ) -> None:
        self._reset_executor = reset_executor
        self._supported_actions = set(supported_actions)
        self._background_jobs = background_jobs
        self._scope_months_provider = scope_months_provider
        self._lifecycle_executor = lifecycle_executor
        self._runtime_reload_request = runtime_reload_request
        self._audit_recorder = audit_recorder

    def handle_runtime_event(self, event: Any) -> dict[str, object]:
        payload = event.payload if isinstance(getattr(event, "payload", None), dict) else {}
        job_id = str(payload.get("job_id") or "").strip()
        owner_user_id = str(payload.get("owner_user_id") or "").strip()
        action = str(payload.get("action") or "").strip()
        reason = str(payload.get("reason") or "").strip()
        impact_fingerprint = str(payload.get("impact_fingerprint") or "").strip()
        recovery_receipt_id = str(payload.get("recovery_receipt_id") or "").strip()
        request_id = str(payload.get("request_id") or "").strip()
        if (
            not job_id
            or not owner_user_id
            or action not in self._supported_actions
            or not reason
            or not impact_fingerprint
            or not recovery_receipt_id
            or not request_id
        ):
            raise ValueError("settings data reset event is missing its recovery or audit contract.")

        job = self._background_jobs.get_job(job_id, owner_user_id)
        if job.status in TERMINAL_BACKGROUND_JOB_STATUSES:
            return dict(job.result_summary)
        if job.status == "running":
            message = "数据重置任务执行状态不明确，已停止自动重试，请人工确认后重新执行。"
            self._background_jobs.fail_job(job_id, message, "interrupted_data_reset_requires_manual_retry")
            return {"action": action, "status": "failed", "message": message}

        self._background_jobs.start_job(job_id)
        self._record_audit(
            actor_id=owner_user_id,
            action=action,
            job_id=job_id,
            request_id=request_id,
            reason=reason,
            outcome="started",
            impact_fingerprint=impact_fingerprint,
            recovery_receipt_id=recovery_receipt_id,
        )

        def update(phase: str, message: str, current: int, total: int) -> None:
            safe_total = max(int(total), 1)
            safe_current = max(0, min(int(current), safe_total))
            self._background_jobs.update_progress(
                job_id,
                phase=phase,
                message=message,
                current=5 + round((safe_current / safe_total) * 75),
                total=100,
                result_summary={"action": action},
            )

        try:
            scope_months = self._scope_months_provider()
            result = self._reset_executor(
                action,
                progress_callback=update,
                reset_context={
                    "job_id": job_id,
                    "actor_id": owner_user_id,
                    "reason": reason,
                    "impact_fingerprint": impact_fingerprint,
                    "recovery_receipt_id": recovery_receipt_id,
                },
            )
            self._background_jobs.update_progress(
                job_id,
                phase="refresh",
                message="正在刷新受影响的后台数据。",
                current=85,
                total=100,
                result_summary={"action": action},
            )
            lifecycle = self._lifecycle_executor(scope_months, action)
            payload_result = result.to_payload()
            payload_result["derived_data_lifecycle"] = lifecycle
            matching_failed = any(
                isinstance(error, dict) and error.get("domain") == "workbench_matching_dirty_scopes"
                for error in list(lifecycle.get("errors") or [])
            )
            if action == RESET_OA_AND_REBUILD_ACTION:
                payload_result["rebuild_status"] = "failed" if matching_failed else "pending"
                payload_result["message"] = (
                    "已清空 OA 工作台人工状态，但关联台后台重建入队失败。"
                    if matching_failed
                    else "已清空 OA 相关工作台人工状态，关联台重建已进入后台队列。"
                )
                if matching_failed:
                    payload_result["status"] = "partial"
            if self._runtime_reload_request is not None:
                try:
                    self._runtime_reload_request()
                except Exception as exc:
                    payload_result["status"] = "partial"
                    payload_result["message"] = f"{payload_result['message']} API 运行时刷新失败，请联系管理员重启服务。"
                    lifecycle.setdefault("errors", []).append(
                        {"domain": "api_runtime_reload", "error": str(exc)}
                    )
            failed = payload_result.get("status") == "partial" or matching_failed
            self._background_jobs.update_progress(
                job_id,
                phase="failed" if failed else "complete",
                message=str(payload_result["message"]),
                current=100,
                total=100,
                result_summary=payload_result,
            )
            if failed:
                self._background_jobs.fail_job(job_id, str(payload_result["message"]), str(payload_result["message"]))
            else:
                self._background_jobs.succeed_job(
                    job_id,
                    str(payload_result["message"]),
                    result_summary=payload_result,
                )
            self._record_audit(
                actor_id=owner_user_id,
                action=action,
                job_id=job_id,
                request_id=request_id,
                reason=reason,
                outcome="partial" if failed else "success",
                impact_fingerprint=impact_fingerprint,
                recovery_receipt_id=recovery_receipt_id,
                result=payload_result,
            )
            return payload_result
        except Exception as exc:
            self._background_jobs.fail_job(job_id, "数据重置任务失败。", str(exc))
            self._record_audit(
                actor_id=owner_user_id,
                action=action,
                job_id=job_id,
                request_id=request_id,
                reason=reason,
                outcome="failed",
                impact_fingerprint=impact_fingerprint,
                recovery_receipt_id=recovery_receipt_id,
                error=str(exc),
            )
            return {"action": action, "status": "failed", "message": str(exc)}

    def _record_audit(
        self,
        *,
        actor_id: str,
        action: str,
        job_id: str,
        request_id: str,
        reason: str,
        outcome: str,
        impact_fingerprint: str,
        recovery_receipt_id: str,
        result: dict[str, object] | None = None,
        error: str | None = None,
    ) -> None:
        if self._audit_recorder is None:
            return
        self._audit_recorder(
            actor_id=actor_id,
            action=action,
            entity_type="settings_data_reset_job",
            entity_id=job_id,
            metadata={
                "event_type": f"settings.data_reset.{outcome}",
                "scope": "settings",
                "trace_id": request_id,
                "page_key": "settings",
                "operation_location": "设置/数据重置",
                "reason": reason,
                "outcome": outcome,
                "request_id": request_id,
                "impact_fingerprint": impact_fingerprint,
                "recovery_receipt_id": recovery_receipt_id,
                "result": result or {},
                "error": error,
            },
        )
