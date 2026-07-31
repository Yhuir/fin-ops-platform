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
    ) -> None:
        self._reset_executor = reset_executor
        self._supported_actions = set(supported_actions)
        self._background_jobs = background_jobs
        self._scope_months_provider = scope_months_provider
        self._lifecycle_executor = lifecycle_executor
        self._runtime_reload_request = runtime_reload_request

    def handle_runtime_event(self, event: Any) -> dict[str, object]:
        payload = event.payload if isinstance(getattr(event, "payload", None), dict) else {}
        job_id = str(payload.get("job_id") or "").strip()
        owner_user_id = str(payload.get("owner_user_id") or "").strip()
        action = str(payload.get("action") or "").strip()
        if not job_id or not owner_user_id or action not in self._supported_actions:
            raise ValueError("settings data reset event requires job_id, owner_user_id and a supported action.")

        job = self._background_jobs.get_job(job_id, owner_user_id)
        if job.status in TERMINAL_BACKGROUND_JOB_STATUSES:
            return dict(job.result_summary)
        if job.status == "running":
            message = "数据重置任务执行状态不明确，已停止自动重试，请人工确认后重新执行。"
            self._background_jobs.fail_job(job_id, message, "interrupted_data_reset_requires_manual_retry")
            return {"action": action, "status": "failed", "message": message}

        self._background_jobs.start_job(job_id)

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
            result = self._reset_executor(action, progress_callback=update)
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
            return payload_result
        except Exception as exc:
            self._background_jobs.fail_job(job_id, "数据重置任务失败。", str(exc))
            return {"action": action, "status": "failed", "message": str(exc)}
