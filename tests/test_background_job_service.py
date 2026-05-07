from __future__ import annotations

import json
import tempfile
import time
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Event

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.background_job_service import BackgroundJobService
from fin_ops_platform.services.state_store import ApplicationStateStore


class BackgroundJobServiceTests(unittest.TestCase):
    def _service(self, temp_dir: str) -> BackgroundJobService:
        store = ApplicationStateStore(Path(temp_dir))
        return BackgroundJobService(store, recent_success_seconds=60)

    def test_create_job_is_visible_in_active_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)

            job = service.create_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                total=31,
            )
            active_jobs = service.list_active_jobs("user-001")

        self.assertEqual([item.job_id for item in active_jobs], [job.job_id])
        self.assertEqual(active_jobs[0].status, "queued")
        self.assertEqual(active_jobs[0].short_label, "正在导入 ETC发票 0/31")

    def test_update_progress_recomputes_percent_and_active_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                total=31,
            )

            service.start_job(job.job_id)
            updated = service.update_progress(
                job.job_id,
                phase="persist_items",
                message="正在导入 ETC发票。",
                current=3,
                total=31,
            )
            active_jobs = service.list_active_jobs("user-001")

        self.assertEqual(updated.current, 3)
        self.assertEqual(updated.total, 31)
        self.assertEqual(updated.percent, 9)
        self.assertEqual(active_jobs[0].current, 3)
        self.assertEqual(active_jobs[0].short_label, "正在导入 ETC发票 3/31")

    def test_succeeded_job_is_active_until_acknowledged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
                total=2,
            )

            service.start_job(job.job_id)
            service.succeed_job(job.job_id, "银行流水导入完成。", result_summary={"created": 2})
            before_ack = service.list_active_jobs("user-001")
            acknowledged = service.acknowledge_job(job.job_id, "user-001")
            after_ack = service.list_active_jobs("user-001")

        self.assertEqual(before_ack[0].status, "succeeded")
        self.assertEqual(before_ack[0].percent, 100)
        self.assertEqual(acknowledged.status, "acknowledged")
        self.assertEqual(after_ack, [])

    def test_succeeded_job_is_not_active_after_recent_success_window(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = BackgroundJobService(store, recent_success_seconds=8)
            job = service.create_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
                total=2,
            )
            service.succeed_job(job.job_id, "银行流水导入完成。")
            jobs = store.load_background_jobs()
            old_time = (datetime.now(UTC) - timedelta(minutes=1)).isoformat()
            jobs[job.job_id]["finished_at"] = old_time
            jobs[job.job_id]["updated_at"] = old_time
            store.save_background_jobs(jobs)

            active_jobs = service.list_active_jobs("user-001")

        self.assertEqual(active_jobs, [])

    def test_failed_job_remains_active_until_acknowledged(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="settings_data_reset",
                label="重置 OA 数据",
                owner_user_id="user-001",
                visibility="system",
            )

            service.start_job(job.job_id)
            failed = service.fail_job(job.job_id, "数据重置失败。", "boom")
            before_ack = service.list_active_jobs("another-user")
            service.acknowledge_job(job.job_id, "another-user")
            after_ack = service.list_active_jobs("another-user")

        self.assertEqual(failed.status, "failed")
        self.assertEqual(before_ack[0].job_id, job.job_id)
        self.assertEqual(before_ack[0].error, "boom")
        self.assertEqual(after_ack, [])

    def test_acknowledge_job_is_idempotent_for_visible_acknowledged_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
            )
            service.fail_job(job.job_id, "银行流水导入失败。", "boom")

            first_ack = service.acknowledge_job(job.job_id, "user-001")
            second_ack = service.acknowledge_job(job.job_id, "user-001")
            active_jobs = service.list_active_jobs("user-001")

        self.assertEqual(first_ack.status, "acknowledged")
        self.assertEqual(second_ack.status, "acknowledged")
        self.assertEqual(second_ack.acknowledged_at, first_ack.acknowledged_at)
        self.assertEqual(active_jobs, [])

    def test_idempotent_create_returns_existing_unfailed_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)

            first = service.create_or_get_idempotent_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                idempotency_key="etc_import_session:session-001",
            )
            second = service.create_or_get_idempotent_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                idempotency_key="etc_import_session:session-001",
            )

        self.assertEqual(second.job_id, first.job_id)

    def test_payload_is_sanitized_before_persistence(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            service = BackgroundJobService(store, recent_success_seconds=60)

            job = service.create_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                source={
                    "session_id": "session-001",
                    "oa_password": "secret-password",
                    "token": "secret-token",
                    "raw_file_content": b"raw-bytes",
                },
                result_summary={"created": 1, "file_content": "raw text"},
            )
            persisted = store.load_background_jobs()

        serialized = json.dumps(persisted[job.job_id], ensure_ascii=False)
        self.assertNotIn("secret-password", serialized)
        self.assertNotIn("secret-token", serialized)
        self.assertNotIn("raw-bytes", serialized)
        self.assertNotIn("raw text", serialized)
        self.assertEqual(persisted[job.job_id]["source"], {"session_id": "session-001"})
        self.assertEqual(persisted[job.job_id]["result_summary"], {"created": 1})

    def test_service_start_marks_stale_running_jobs_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            stale_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            store.save_background_jobs(
                {
                    "job_stale": {
                        "job_id": "job_stale",
                        "type": "file_import",
                        "label": "导入 银行流水",
                        "short_label": "正在导入 银行流水",
                        "owner_user_id": "user-001",
                        "visibility": "owner",
                        "status": "running",
                        "phase": "persist_items",
                        "current": 1,
                        "total": 2,
                        "percent": 50,
                        "message": "正在导入 银行流水。",
                        "result_summary": {},
                        "error": None,
                        "idempotency_key": None,
                        "source": {},
                        "affected_scopes": [],
                        "affected_months": [],
                        "created_at": stale_time,
                        "started_at": stale_time,
                        "updated_at": stale_time,
                        "finished_at": None,
                        "acknowledged_at": None,
                    }
                }
            )

            service = BackgroundJobService(store, stale_after_seconds=1)
            job = service.get_job("job_stale", "user-001")

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.message, "服务重启，任务已中断，请重新执行。")
        self.assertEqual(job.error, "interrupted_by_restart")

    def test_run_job_executes_handler_and_marks_success(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="workbench_rebuild",
                label="重建关联台",
                owner_user_id="user-001",
                total=1,
            )
            handler_started = Event()

            def handler(running_job):
                handler_started.set()
                service.update_progress(running_job.job_id, phase="rebuild", message="正在重建关联台。", current=1, total=1)
                return {"rebuilt": 1}

            service.run_job(job, handler)
            self.assertTrue(handler_started.wait(timeout=2))
            deadline = time.monotonic() + 2
            completed = service.get_job(job.job_id, "user-001")
            while time.monotonic() < deadline:
                completed = service.get_job(job.job_id, "user-001")
                if completed.status == "succeeded":
                    break
                time.sleep(0.02)

        self.assertEqual(completed.status, "succeeded")
        self.assertEqual(completed.result_summary, {"rebuilt": 1})

    def test_background_job_api_returns_and_acknowledges_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            job = app._background_job_service.create_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="test_finops_user",
                total=2,
            )
            app._background_job_service.start_job(job.job_id)
            app._background_job_service.update_progress(
                job.job_id,
                phase="persist_items",
                message="正在导入 ETC发票。",
                current=1,
                total=2,
            )

            active_response = app.handle_request("GET", "/api/background-jobs/active")
            active_payload = json.loads(active_response.body)
            get_response = app.handle_request("GET", f"/api/background-jobs/{job.job_id}")
            get_payload = json.loads(get_response.body)
            ack_response = app.handle_request("POST", f"/api/background-jobs/{job.job_id}/acknowledge", body="{}")
            ack_payload = json.loads(ack_response.body)
            second_ack_response = app.handle_request("POST", f"/api/background-jobs/{job.job_id}/acknowledge", body="{}")
            second_ack_payload = json.loads(second_ack_response.body)
            active_after_ack = json.loads(app.handle_request("GET", "/api/background-jobs/active").body)

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_payload["jobs"][0]["job_id"], job.job_id)
        self.assertEqual(active_payload["jobs"][0]["short_label"], "正在导入 ETC发票 1/2")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_payload["job"]["job_id"], job.job_id)
        self.assertEqual(ack_response.status_code, 200)
        self.assertEqual(ack_payload["job"]["status"], "acknowledged")
        self.assertEqual(second_ack_response.status_code, 200)
        self.assertEqual(second_ack_payload["job"]["status"], "acknowledged")
        self.assertEqual(second_ack_payload["job"]["acknowledged_at"], ack_payload["job"]["acknowledged_at"])
        self.assertEqual(active_after_ack["jobs"], [])


if __name__ == "__main__":
    unittest.main()
