from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from tests.app_test_support import build_local_state_application as build_application


class FakeOperationsDashboardConnection:
    def __init__(self) -> None:
        self.fail = False

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        if self.fail:
            raise RuntimeError("dashboard database timeout")
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            return {"total_count": 1, "latest_synced_at": "2026-05-20T10:00:00+00:00"}
        if "invoice_flags" in normalized:
            return {
                "total_count": 2,
                "manual_count": 1,
                "oa_attachment_count": 1,
                "oa_attachment_non_manual_count": 1,
                "latest_synced_at": "2026-05-20T10:00:00+00:00",
                "manual_latest_synced_at": "2026-05-20T10:00:00+00:00",
                "oa_attachment_latest_synced_at": "2026-05-20T10:00:00+00:00",
            }
        if "oa_records_count" in normalized:
            return {
                "oa_records_count": 3,
                "oa_items_count": 4,
                "oa_records_latest_synced_at": "2026-05-20T10:00:00+00:00",
                "oa_latest_synced_at": "2026-05-20T10:00:00+00:00",
            }
        if "from job.outbox_events" in normalized and "pending_count" in normalized:
            return {
                "pending_count": 0,
                "publishing_count": 0,
                "failed_count": 0,
                "publish_failed_count": 0,
                "oldest_pending_age_seconds": None,
            }
        if "max_pending_age_seconds" in normalized:
            return {"max_pending_age_seconds": None}
        raise AssertionError(sql)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        if self.fail:
            raise RuntimeError("dashboard database timeout")
        normalized = " ".join(sql.lower().split())
        if "from app.import_batches" in normalized and "batch_type in" in normalized:
            return [
                {
                    "event_id": "batch-bank-1",
                    "source_key": "bank_transactions",
                    "label": "流水导入",
                    "source_name": "bank.xlsx",
                    "imported_by": "ops",
                    "count": 1,
                    "supplementary_count": None,
                    "imported_at": "2026-05-20T10:00:00+00:00",
                    "status": "completed",
                }
            ]
        if "oa_attachment_source_links" in normalized:
            return [
                {
                    "event_id": "oa-attachment-1",
                    "source_key": "oa_attachment",
                    "label": "OA 解析",
                    "source_name": "OA 附件解析",
                    "imported_by": "oa_sync",
                    "count": 1,
                    "supplementary_count": 1,
                    "imported_at": "2026-05-19T10:00:00+00:00",
                    "status": "completed",
                }
            ]
        if "from app.oa_sync_runs" in normalized and "sync_type = 'oa_projection'" in normalized:
            return []
        if "from job.outbox_events" in normalized:
            return []
        if "from job.read_model_dirty_scopes" in normalized:
            return []
        if "from job.runtime_worker_heartbeats" in normalized:
            return []
        raise AssertionError(sql)


def inject_oa_sync_runtime_status(
    app,
    *,
    outbox_status: str = "ready",
    scope_key: str = "all",
    last_error: str | None = None,
    worker_status: str = "ready",
    latest_run: dict[str, object] | None = None,
) -> None:
    scope_payload = {
        "event_type": "oa.sync",
        "scope_type": "oa",
        "scope_key": scope_key,
        "status": outbox_status,
        "count": 1,
    }
    outbox_payload = {
        "status": outbox_status,
        "count": 1,
        "scopes": [scope_payload],
    }
    if last_error:
        outbox_payload["last_error"] = last_error
        scope_payload["last_error"] = last_error
    app._app_status_runtime_statuses = lambda: {
        "read_model_statuses": None,
        "outbox_statuses": {"oa.sync": outbox_payload},
        "worker_statuses": {"oa-sync": {"status": worker_status}},
    }
    app._postgres_oa_projection_latest_sync_run = lambda: latest_run


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

    def test_operation_barrier_status_returns_runtime_readiness_contract(self) -> None:
        app = build_application()
        app._state_store = SimpleNamespace(
            app_status_runtime_snapshot=lambda: {
                "read_model_statuses": {
                    "workbench_relation": {
                        "status": "refreshing",
                        "scopes": [
                            {
                                "scope_type": "workbench_relation",
                                "scope_key": "2026-02",
                                "status": "refreshing",
                                "updated_at": "2026-06-14T10:00:00+00:00",
                            }
                        ],
                    }
                },
                "outbox_statuses": {},
                "worker_statuses": {"workbench-relation": {"status": "ready"}},
            }
        )

        response = app.handle_request(
            "POST",
            "/api/operation-barrier/status",
            body=json.dumps({"targets": [{"read_model_key": "workbench_relation", "scope_key": "2026-02"}]}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "refreshing")
        self.assertFalse(payload["fresh"])
        self.assertEqual(payload["targets"][0]["read_model_key"], "workbench_relation")
        self.assertEqual(payload["targets"][0]["scope_key"], "2026-02")
        self.assertEqual(payload["targets"][0]["worker_status"], "ready")

    def test_operation_barrier_rejects_invalid_target_contract(self) -> None:
        app = build_application()

        response = app.handle_request(
            "POST",
            "/api/operation-barrier/status",
            body=json.dumps({"targets": [{"scope_key": "all"}]}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_operation_barrier_request")

    def test_operation_barrier_rejects_non_object_target_entries(self) -> None:
        app = build_application()

        response = app.handle_request(
            "POST",
            "/api/operation-barrier/status",
            body=json.dumps({"targets": ["workbench_relation"]}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_operation_barrier_request")

    def test_app_health_reports_dirty_oa_scopes_as_busy_and_stale(self) -> None:
        app = build_application()
        inject_oa_sync_runtime_status(app, outbox_status="pending", scope_key="all")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["oa_sync"]["status"], "refreshing")
        self.assertEqual(payload["oa_sync"]["dirty_scopes"], ["all"])
        self.assertEqual(payload["workbench_read_model"]["status"], "stale")
        self.assertEqual(payload["workbench_read_model"]["dirty_scopes"], ["all"])

    def test_app_health_reports_workbench_generation_consistency_failure(self) -> None:
        app = build_application()

        class FailedWorkbenchRepository:
            def get_workbench_refresh_status(self, *, scope_key: str):
                return {
                    "scope_key": scope_key,
                    "read_model_status": "failed",
                    "consistency_status": "failed",
                    "active_generation_id": "gen-all",
                    "last_error": "generation_metadata_actual_mismatch: all/gen-all",
                    "consistency_failures": [
                        {
                            "scope_key": "all",
                            "generation_id": "gen-all",
                            "group_count": 6,
                            "actual_group_count": 0,
                        }
                    ],
                }

        app._workbench_sql_read_repository = FailedWorkbenchRepository()

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["workbench_read_model"]["status"], "error")
        self.assertEqual(payload["workbench_read_model"]["consistency_status"], "failed")
        self.assertEqual(payload["workbench_read_model"]["active_generation_id"], "gen-all")
        self.assertIn("generation_metadata_actual_mismatch", payload["workbench_read_model"]["last_error"])

    def test_app_health_keeps_workbench_consistency_failure_busy_during_active_repair(self) -> None:
        app = build_application()

        class RepairingWorkbenchRepository:
            def get_workbench_refresh_status(self, *, scope_key: str):
                return {
                    "scope_key": scope_key,
                    "read_model_status": "refreshing",
                    "consistency_status": "failed",
                    "active_generation_id": "gen-all",
                    "last_error": "Workbench read model generation consistency failed.",
                    "consistency_failures": [
                        {
                            "scope_key": "all",
                            "generation_id": "gen-all",
                            "group_count": 6,
                            "actual_group_count": 0,
                        }
                    ],
                }

        app._workbench_sql_read_repository = RepairingWorkbenchRepository()

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "busy")
        self.assertEqual(payload["workbench_read_model"]["status"], "rebuilding")
        self.assertNotEqual(payload["dependencies"].get("workbench_read_model", {}).get("status"), "unavailable")
        self.assertNotEqual(payload["app_status"]["overall"]["level"], "blocked")

    def test_app_health_caches_workbench_refresh_status_briefly(self) -> None:
        app = build_application()

        class CountingWorkbenchRepository:
            def __init__(self) -> None:
                self.calls = 0

            def get_workbench_refresh_status(self, *, scope_key: str):
                self.calls += 1
                return {"scope_key": scope_key, "read_model_status": "fresh", "consistency_status": "fresh"}

        repository = CountingWorkbenchRepository()
        app._workbench_sql_read_repository = repository

        app.handle_request("GET", "/api/app-health")
        app.handle_request("GET", "/api/app-health")

        self.assertEqual(repository.calls, 1)

    def test_dirty_oa_scopes_block_workbench_write_actions(self) -> None:
        app = build_application()
        inject_oa_sync_runtime_status(app, outbox_status="pending", scope_key="all")

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
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertEqual(payload["background_jobs"]["active_jobs"], [])
        self.assertEqual(
            [job["job_id"] for job in payload["background_jobs"]["attention_jobs"]],
            [partial_job.job_id, failed_job.job_id],
        )
        self.assertEqual(payload["background_jobs"]["primary_attention"]["job_id"], failed_job.job_id)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["type"], "file_import")
        self.assertEqual(payload["background_jobs"]["primary_attention"]["message"], "银行流水导入失败。")
        self.assertEqual(payload["background_jobs"]["primary_attention"]["error"], "boom")
        self.assertTrue(payload["background_jobs"]["primary_attention"]["acknowledgeable"])
        self.assertTrue(payload["background_jobs"]["primary_attention"]["retryable"])
        self.assertIsNone(payload["background_jobs"]["primary_running"])
        self.assertEqual(
            [job["job_id"] for job in payload["background_jobs"]["jobs"]],
            [partial_job.job_id, failed_job.job_id],
        )

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

    def test_app_health_marks_cost_statistics_warmup_attention_retryable_and_serializes_job_policy(self) -> None:
        app = build_application()
        job = app._background_job_service.create_job(
            job_type="cost_statistics_cache_warmup",
            label="预热成本统计缓存",
            owner_user_id="system",
            visibility="system",
            affected_months=["2026-03"],
            source={"reason": "cost_statistics_scope_invalidated", "months": ["2026-03"]},
        )
        app._background_job_service.fail_job(job.job_id, "服务重启，任务已中断，请重新执行。", "interrupted_by_restart")

        response = app.handle_request("GET", "/api/app-health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["background_jobs"]["primary_attention"]["job_id"], job.job_id)
        self.assertTrue(payload["background_jobs"]["primary_attention"]["acknowledgeable"])
        self.assertTrue(payload["background_jobs"]["primary_attention"]["retryable"])
        self.assertEqual(payload["background_jobs"]["jobs"][0]["job_id"], job.job_id)
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertEqual(payload["background_jobs"]["active_jobs"], [])
        self.assertEqual(payload["background_jobs"]["attention_jobs"][0]["job_id"], job.job_id)
        self.assertTrue(payload["background_jobs"]["jobs"][0]["acknowledgeable"])
        self.assertTrue(payload["background_jobs"]["jobs"][0]["retryable"])

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
        inject_oa_sync_runtime_status(app, outbox_status="failed", scope_key="all", last_error="OA 同步失败")

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

    def test_operations_app_health_dashboard_is_admin_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/operations/app-health-dashboard")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_operations_app_health_dashboard_returns_read_only_payload_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            setattr(app._state_store, "_connection", FakeOperationsDashboardConnection())

            response = app.handle_request("GET", "/api/operations/app-health-dashboard")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn("data_inventory", payload)
        self.assertIn("request_performance", payload)
        self.assertIn("runtime_performance", payload)
        self.assertNotIn("status", payload)
        self.assertEqual(payload["data_inventory"]["bank"]["total_count"], 1)
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertEqual(set(invoice_sources), {"manual", "oa_attachment"})
        self.assertEqual(invoice_sources["oa_attachment"]["supplementary_count"], 1)
        self.assertEqual(payload["data_inventory"]["import_events"][0]["source_key"], "bank_transactions")

    def test_operations_app_health_dashboard_returns_stale_cached_payload_after_refresh_error(self) -> None:
        current_time = {"value": 100.0}

        def fake_monotonic() -> float:
            return current_time["value"]

        with (
            self._temporary_env(
                FIN_OPS_ADMIN_USERNAMES="test_finops_user",
                FIN_OPS_APP_HEALTH_DASHBOARD_CACHE_TTL_SECONDS="30",
            ),
            tempfile.TemporaryDirectory() as temp_dir,
            patch("fin_ops_platform.app.server.monotonic", side_effect=fake_monotonic),
        ):
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeOperationsDashboardConnection()
            setattr(app._state_store, "_connection", connection)

            first_response = app.handle_request("GET", "/api/operations/app-health-dashboard")
            connection.fail = True
            current_time["value"] = 140.0
            second_response = app.handle_request("GET", "/api/operations/app-health-dashboard")
            second_payload = json.loads(second_response.body)

        self.assertEqual(first_response.status_code, 200)
        self.assertEqual(second_response.status_code, 200)
        self.assertEqual(second_payload["data_inventory"]["bank"]["total_count"], 1)
        self.assertIn("dashboard_cache_stale_after_error", second_payload["freshness"]["warnings"])


if __name__ == "__main__":
    unittest.main()
