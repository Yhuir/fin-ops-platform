from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path

from fin_ops_platform.app.server import build_application


class AppHealthApiTests(unittest.TestCase):
    @contextmanager
    def _temporary_env(self, **updates: str | None):
        previous = {key: os.environ.get(key) for key in updates}
        try:
            for key, value in updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    def test_app_health_returns_ok_when_idle(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertIn("generated_at", payload)
        self.assertEqual(payload["session"]["status"], "authenticated")
        self.assertIn("oa_sync", payload)
        self.assertEqual(payload["workbench_read_model"]["status"], "ready")
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertIn("dependencies", payload)
        self.assertEqual(payload["version"], 1)
        self.assertIn("metrics", payload)
        self.assertEqual(payload["alerts"]["active"], [])

    def test_app_health_reports_dirty_oa_scopes_as_busy_and_stale(self) -> None:
        app = build_application()
        app._oa_sync_service.mark_changed(["all"], reason="OA Mongo changed")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["oa_sync"]["status"], "refreshing")
        self.assertEqual(payload["oa_sync"]["dirty_scopes"], ["all"])
        self.assertEqual(payload["workbench_read_model"]["status"], "stale")
        self.assertEqual(payload["workbench_read_model"]["dirty_scopes"], ["all"])

    def test_dirty_oa_scopes_block_workbench_write_actions(self) -> None:
        app = build_application()
        app._oa_sync_service.mark_changed(["all"], reason="OA Mongo changed")

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            body=json.dumps({"month": "all", "row_ids": ["oa-missing"]}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "workbench_stale")
        self.assertEqual(payload["dirty_scopes"], ["all"])

    def test_app_health_reports_running_background_job_as_busy(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="etc_invoice_import",
            label="导入 ETC发票",
            owner_user_id="test_finops_user",
            total=2,
        )
        app._background_job_service.start_job(job.job_id)

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["background_jobs"]["running"], 1)
        self.assertEqual(payload["background_jobs"]["active"], 1)
        self.assertEqual(payload["background_jobs"]["primary_running"]["job_id"], job.job_id)
        self.assertEqual(payload["background_jobs"]["primary_running"]["status"], "running")

    def test_app_health_reports_workbench_rebuild_job_as_rebuilding(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="workbench_rebuild",
            label="重建关联台",
            owner_user_id="test_finops_user",
            total=1,
        )
        app._background_job_service.start_job(job.job_id)

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["workbench_read_model"]["status"], "rebuilding")
        self.assertEqual(payload["workbench_read_model"]["rebuild_job_ids"], [job.job_id])

    def test_app_health_reports_unacknowledged_failed_and_partial_success_jobs_as_attention(self) -> None:
        app = build_application()
        failed_job = app._background_job_service.create_job(
            job_type="file_import",
            label="导入 银行流水",
            owner_user_id="test_finops_user",
            source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
        )
        partial_job = app._background_job_service.create_job(
            job_type="workbench_matching",
            label="生成关联台候选",
            owner_user_id="test_finops_user",
            affected_months=["2026-05"],
        )
        app._background_job_service.fail_job(failed_job.job_id, "银行流水导入失败。", "boom")
        app._background_job_service.succeed_job(
            partial_job.job_id,
            "关联台候选部分完成。",
            status="partial_success",
        )

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["background_jobs"]["attention"], 2)
        self.assertEqual(payload["background_jobs"]["active"], 2)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["job_id"], failed_job.job_id)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["type"], "file_import")
        self.assertEqual(payload["background_jobs"]["primary_attention"]["message"], "银行流水导入失败。")
        self.assertEqual(payload["background_jobs"]["primary_attention"]["error"], "boom")
        self.assertTrue(payload["background_jobs"]["primary_attention"]["acknowledgeable"])
        self.assertTrue(payload["background_jobs"]["primary_attention"]["retryable"])
        self.assertIsNone(payload["background_jobs"]["primary_running"])

    def test_app_health_excludes_acknowledged_failed_job_from_active_and_attention(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="file_import",
            label="导入 银行流水",
            owner_user_id="test_finops_user",
            source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
        )
        app._background_job_service.fail_job(job.job_id, "银行流水导入失败。", "boom")
        app._background_job_service.acknowledge_job(job.job_id, "test_finops_user")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertEqual(payload["background_jobs"]["attention"], 0)
        self.assertIsNone(payload["background_jobs"]["primary_attention"])

    def test_app_health_marks_workbench_matching_attention_retryable_when_months_exist(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="workbench_matching",
            label="生成关联台候选",
            owner_user_id="test_finops_user",
            affected_months=["2026-05"],
        )
        app._background_job_service.succeed_job(job.job_id, "关联台候选部分完成。", status="partial_success")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["job_id"], job.job_id)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["status"], "partial_success")
        self.assertTrue(payload["background_jobs"]["primary_attention"]["acknowledgeable"])
        self.assertTrue(payload["background_jobs"]["primary_attention"]["retryable"])

    def test_app_health_marks_interrupted_job_without_source_not_retryable_but_acknowledgeable(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="settings_data_reset",
            label="重置 OA 数据",
            owner_user_id="test_finops_user",
        )
        app._background_job_service.fail_job(job.job_id, "服务重启，任务已中断，请重新执行。", "interrupted_by_restart")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["job_id"], job.job_id)
        self.assertTrue(payload["background_jobs"]["primary_attention"]["acknowledgeable"])
        self.assertFalse(payload["background_jobs"]["primary_attention"]["retryable"])

    def test_app_health_excludes_succeeded_job_after_recent_success_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            job = app._background_job_service.create_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="test_finops_user",
                source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
            )
            app._background_job_service.succeed_job(job.job_id, "银行流水导入完成。")
            jobs = app._state_store.load_background_jobs()
            old_time = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            jobs[job.job_id]["finished_at"] = old_time
            jobs[job.job_id]["updated_at"] = old_time
            app._state_store.save_background_jobs(jobs)

            response = app.handle_request("GET", "/api/app-health")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertEqual(payload["background_jobs"]["jobs"], [])

    def test_app_health_reports_dependency_error_as_blocked(self) -> None:
        app = build_application()
        app._oa_sync_service.mark_error("OA 同步失败")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["workbench_read_model"]["status"], "error")
        self.assertEqual(payload["dependencies"]["oa_sync"]["status"], "unavailable")
        self.assertEqual(payload["alerts"]["active"][0]["kind"], "dependency_unavailable")

    def test_app_health_stream_returns_sse_snapshot_and_heartbeat(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/api/app-health/stream")
        stream = iter(response.body)
        snapshot_event = next(stream)
        heartbeat_event = next(stream)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.stream)
        self.assertIn("text/event-stream", response.headers["Content-Type"])
        self.assertIn("event: app_health", snapshot_event)
        self.assertIn('"status": "ok"', snapshot_event)
        self.assertIn("event: heartbeat", heartbeat_event)

    def test_app_health_uses_existing_auth_guard_when_session_is_missing(self) -> None:
        with self._temporary_env(FIN_OPS_TEST_DEFAULT_AUTH="0"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/app-health")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")


if __name__ == "__main__":
    unittest.main()
