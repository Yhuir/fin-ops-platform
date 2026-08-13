from __future__ import annotations

import json
import tempfile
import unittest
from datetime import UTC, datetime, timedelta
from pathlib import Path

from tests.app_test_support import build_local_state_application as build_application
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

    def test_app_health_active_and_attention_views_share_one_store_snapshot(self) -> None:
        class CountingStore:
            def __init__(self) -> None:
                self.jobs: dict[str, dict[str, object]] = {}
                self.load_calls = 0

            def load_background_jobs(self) -> dict[str, dict[str, object]]:
                self.load_calls += 1
                return {job_id: dict(payload) for job_id, payload in self.jobs.items()}

            def load_background_job(self, job_id: str) -> dict[str, object] | None:
                payload = self.jobs.get(job_id)
                return dict(payload) if payload is not None else None

            def save_background_job(self, job_payload: dict[str, object]) -> None:
                self.jobs[str(job_payload["job_id"])] = dict(job_payload)

        store = CountingStore()
        service = BackgroundJobService(store, recent_success_seconds=60)
        active_job = service.create_job(
            job_type="file_import",
            label="导入测试",
            owner_user_id="user-001",
        )
        failed_job = service.create_job(
            job_type="file_import",
            label="失败测试",
            owner_user_id="user-001",
        )
        service.fail_job(failed_job.job_id, "失败。", "boom")
        store.load_calls = 0

        active_jobs, attention_jobs = service.list_app_health_jobs("user-001")

        self.assertEqual(store.load_calls, 1)
        self.assertIn(active_job.job_id, [job.job_id for job in active_jobs])
        self.assertEqual([job.job_id for job in attention_jobs], [failed_job.job_id])

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

    def test_job_acceptance_and_progress_visibility_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            job = service.create_job(
                job_type="etc_invoice_import",
                label="导入 ETC发票",
                owner_user_id="user-001",
                total=31,
                source={
                    "affected_domains": ["imports_etc_invoices", "etc_tickets"],
                    "route": "/imports/etc-invoices",
                },
            )
            queued_jobs = service.list_active_jobs("user-001")

            service.start_job(job.job_id)
            service.update_progress(
                job.job_id,
                phase="persist_items",
                message="正在导入 ETC发票。",
                current=3,
                total=31,
            )
            running_jobs = service.list_active_jobs("user-001")

        self.assertEqual([item.job_id for item in queued_jobs], [job.job_id])
        queued_payload = queued_jobs[0].to_payload()
        self.assertEqual(queued_payload["status"], "queued")
        self.assertEqual(queued_payload["current"], 0)
        self.assertEqual(queued_payload["total"], 31)
        self.assertEqual(queued_payload["percent"], 0)
        self.assertEqual(queued_payload["short_label"], "正在导入 ETC发票 0/31")
        self.assertEqual(queued_payload["created_at"], queued_payload["updated_at"])
        self.assertEqual(queued_payload["affected_domains"], ["imports_etc_invoices", "etc_tickets"])
        self.assertEqual(queued_payload["route"], "/imports/etc-invoices")

        self.assertEqual([item.job_id for item in running_jobs], [job.job_id])
        running_payload = running_jobs[0].to_payload()
        self.assertEqual(running_payload["status"], "running")
        self.assertEqual(running_payload["phase"], "persist_items")
        self.assertEqual(running_payload["current"], 3)
        self.assertEqual(running_payload["total"], 31)
        self.assertEqual(running_payload["percent"], 9)
        self.assertEqual(running_payload["short_label"], "正在导入 ETC发票 3/31")
        self.assertIsNotNone(running_payload["started_at"])
        self.assertGreaterEqual(
            datetime.fromisoformat(str(running_payload["updated_at"])),
            datetime.fromisoformat(str(queued_payload["created_at"])),
        )

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
            store.save_background_job(jobs[job.job_id])

            active_jobs = service.list_active_jobs("user-001")

        self.assertEqual(active_jobs, [])

    def test_retired_workbench_matching_jobs_are_not_visible_as_progress_or_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            failed_job = service.create_job(
                job_type="settings_data_reset",
                label="重置 OA 数据",
                owner_user_id="user-001",
                visibility="system",
            )
            partial_job = service.create_job(
                job_type="workbench_matching",
                label="生成正式配对关系",
                owner_user_id="user-001",
                visibility="system",
            )

            service.start_job(failed_job.job_id)
            failed = service.fail_job(failed_job.job_id, "数据重置失败。", "boom")
            partial = service.succeed_job(
                partial_job.job_id,
                "正式配对关系部分完成。",
                status="partial_success",
            )
            active_before_ack = service.list_active_jobs("another-user")
            attention_before_ack = service.list_attention_jobs("another-user")
            service.acknowledge_job(failed_job.job_id, "another-user")
            service.acknowledge_job(partial_job.job_id, "another-user")
            active_after_ack = service.list_active_jobs("another-user")
            attention_after_ack = service.list_attention_jobs("another-user")

        self.assertEqual(failed.status, "failed")
        self.assertEqual(partial.status, "partial_success")
        self.assertEqual(active_before_ack, [])
        self.assertEqual([item.job_id for item in attention_before_ack], [failed_job.job_id])
        self.assertEqual(attention_before_ack[0].error, "boom")
        self.assertEqual(active_after_ack, [])
        self.assertEqual(attention_after_ack, [])

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

    def test_acknowledge_jobs_closes_multiple_attention_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            first = service.create_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
            )
            second = service.create_job(
                job_type="workbench_matching",
                label="生成正式配对关系",
                owner_user_id="user-001",
            )
            service.fail_job(first.job_id, "银行流水导入失败。", "boom")
            service.succeed_job(second.job_id, "正式配对关系部分完成。", status="partial_success")

            acknowledged = service.acknowledge_jobs([first.job_id, second.job_id], "user-001")
            attention_jobs = service.list_attention_jobs("user-001")

        self.assertEqual([item.status for item in acknowledged], ["acknowledged", "acknowledged"])
        self.assertEqual(attention_jobs, [])

    def test_superseded_job_is_not_active_or_attention(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            old_job = service.create_job(
                job_type="workbench_matching",
                label="生成正式配对关系",
                owner_user_id="system",
                visibility="system",
                affected_months=["2026-05"],
            )
            new_job = service.create_job(
                job_type="workbench_matching",
                label="生成正式配对关系",
                owner_user_id="system",
                visibility="system",
                affected_months=["2026-05"],
            )
            service.fail_job(old_job.job_id, "服务重启，任务已中断，请重新执行。", "interrupted_by_restart")

            superseded = service.supersede_job(
                old_job.job_id,
                "user-001",
                superseded_by_job_id=new_job.job_id,
            )
            active_jobs = service.list_active_jobs("user-001")
            attention_jobs = service.list_attention_jobs("user-001")

        self.assertEqual(superseded.status, "superseded")
        self.assertEqual(superseded.superseded_by_job_id, new_job.job_id)
        self.assertIsNotNone(superseded.superseded_at)
        self.assertEqual(active_jobs, [])
        self.assertEqual(attention_jobs, [])

    def test_old_snapshot_without_superseded_fields_still_loads(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            now = datetime.now(UTC).isoformat()
            store.save_background_job(
                    {
                        "job_id": "job_legacy",
                        "type": "file_import",
                        "label": "导入 银行流水",
                        "short_label": "导入 银行流水失败",
                        "owner_user_id": "user-001",
                        "visibility": "owner",
                        "status": "failed",
                        "phase": "failed",
                        "current": 0,
                        "total": 0,
                        "percent": 0,
                        "message": "银行流水导入失败。",
                        "result_summary": {},
                        "error": "boom",
                        "idempotency_key": None,
                        "source": {},
                        "affected_scopes": [],
                        "affected_months": [],
                        "created_at": now,
                        "started_at": None,
                        "updated_at": now,
                        "finished_at": now,
                        "acknowledged_at": None,
                    }
            )

            service = BackgroundJobService(store, recent_success_seconds=60)
            job = service.get_job("job_legacy", "user-001")
            attention_jobs = service.list_attention_jobs("user-001")

        self.assertIsNone(job.superseded_by_job_id)
        self.assertIsNone(job.superseded_at)
        self.assertEqual([item.job_id for item in attention_jobs], ["job_legacy"])

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

    def test_idempotent_retry_requeues_same_failed_job(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            first, first_activated = service.create_or_get_idempotent_job_with_created(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
                idempotency_key="file_import_session:session-001:file-001",
                source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
            )
            service.fail_job(first.job_id, "导入失败。", "queue unavailable")

            retried, retry_activated = service.create_or_get_idempotent_job_with_created(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
                idempotency_key="file_import_session:session-001:file-001",
                source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
            )

        self.assertTrue(first_activated)
        self.assertTrue(retry_activated)
        self.assertEqual(retried.job_id, first.job_id)
        self.assertEqual(retried.status, "queued")
        self.assertIsNone(retried.error)
        self.assertEqual(retried.created_at, first.created_at)

    def test_idempotent_create_rejects_same_key_with_different_source(self) -> None:
        from fin_ops_platform.services.background_job_service import BackgroundJobIdempotencyConflict

        with tempfile.TemporaryDirectory() as temp_dir:
            service = self._service(temp_dir)
            service.create_or_get_idempotent_job(
                job_type="file_import",
                label="导入 银行流水",
                owner_user_id="user-001",
                idempotency_key="file_import_session:session-001:file-001",
                source={"session_id": "session-001", "selected_file_ids": ["file-001"]},
            )

            with self.assertRaises(BackgroundJobIdempotencyConflict):
                service.create_or_get_idempotent_job(
                    job_type="file_import",
                    label="导入 银行流水",
                    owner_user_id="user-001",
                    idempotency_key="file_import_session:session-001:file-001",
                    source={"session_id": "session-002", "selected_file_ids": ["file-001"]},
                )

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

    def test_explicit_worker_recovery_marks_stale_running_jobs_failed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = ApplicationStateStore(Path(temp_dir))
            stale_time = (datetime.now(UTC) - timedelta(minutes=10)).isoformat()
            store.save_background_job(
                    {
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
            )

            service = BackgroundJobService(store, stale_after_seconds=1)
            self.assertEqual(service.recover_interrupted_jobs(), 1)
            job = service.get_job("job_stale", "user-001")

        self.assertEqual(job.status, "failed")
        self.assertEqual(job.message, "服务重启，任务已中断，请重新执行。")
        self.assertEqual(job.error, "interrupted_by_restart")

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
        self.assertEqual(active_payload["active_jobs"][0]["job_id"], job.job_id)
        self.assertEqual(active_payload["attention_jobs"], [])
        self.assertEqual(active_payload["jobs"][0]["short_label"], "正在导入 ETC发票 1/2")
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(get_payload["job"]["job_id"], job.job_id)
        self.assertEqual(ack_response.status_code, 200)
        self.assertEqual(ack_payload["job"]["status"], "acknowledged")
        self.assertEqual(second_ack_response.status_code, 200)
        self.assertEqual(second_ack_payload["job"]["status"], "acknowledged")
        self.assertEqual(second_ack_payload["job"]["acknowledged_at"], ack_payload["job"]["acknowledged_at"])
        self.assertEqual(active_after_ack["jobs"], [])

    def test_background_job_api_hides_retired_matching_progress_jobs(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            job = app._background_job_service.create_job(
                job_type="workbench_matching",
                label="生成正式配对关系",
                owner_user_id="system",
                visibility="system",
                affected_months=["2026-03"],
                source={"reason": "workbench_matching", "months": ["2026-03"]},
            )
            app._background_job_service.fail_job(
                job.job_id,
                "服务重启，任务已中断，请重新执行。",
                "interrupted_by_restart",
            )

            active_response = app.handle_request("GET", "/api/background-jobs/active")
            active_payload = json.loads(active_response.body)
            get_response = app.handle_request("GET", f"/api/background-jobs/{job.job_id}")
            get_payload = json.loads(get_response.body)

        self.assertEqual(active_response.status_code, 200)
        self.assertEqual(active_payload["jobs"], [])
        self.assertEqual(active_payload["active_jobs"], [])
        self.assertEqual(active_payload["attention_jobs"], [])
        self.assertFalse(get_payload["job"]["retryable"])
        self.assertEqual(get_response.status_code, 200)
        self.assertTrue(get_payload["job"]["acknowledgeable"])
        self.assertTrue(get_payload["job"]["attention"])


if __name__ == "__main__":
    unittest.main()
