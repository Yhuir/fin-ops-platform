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

from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository
from tests.app_test_support import (
    build_local_state_application as build_application,
    install_fresh_workbench_write_gate,
)


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
                "input_invoice_count": 1,
                "output_invoice_count": 1,
                "oa_attachment_count": 1,
                "oa_attachment_non_manual_count": 1,
                "latest_synced_at": "2026-05-20T10:00:00+00:00",
                "manual_latest_synced_at": "2026-05-20T10:00:00+00:00",
                "input_invoice_latest_synced_at": "2026-05-20T10:00:00+00:00",
                "output_invoice_latest_synced_at": "2026-05-20T10:00:00+00:00",
                "oa_attachment_latest_synced_at": "2026-05-20T10:00:00+00:00",
            }
        if "oa_records_count" in normalized:
            return {
                "oa_records_count": 3,
                "oa_records_completed_count": 2,
                "oa_records_in_progress_count": 1,
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
            raise AssertionError("dashboard import events must not read OA attachment source links")
        if "from app.oa_sync_runs" in normalized and "sync_type = 'oa_projection'" in normalized:
            raise AssertionError("dashboard import events must not read OA sync runs")
        if "from job.outbox_events" in normalized:
            return []
        if "from job.read_model_dirty_scopes" in normalized:
            return []
        if "from job.runtime_worker_heartbeats" in normalized:
            return []
        raise AssertionError(sql)


class FakeInputInvoiceUsageAuditConnection:
    def __init__(
        self,
        *,
        rows_by_check: dict[str, list[dict[str, object]]] | None = None,
        fail: bool = False,
    ) -> None:
        self.rows_by_check = rows_by_check or {}
        self.fail = fail
        self.executed: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []
        self.fetch_all_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("audit database timeout")
        self.fetch_one_calls.append((sql, params))
        return {
            "active_input_invoice_count": 2,
            "active_input_invoice_total_with_tax": "300.00",
            "read_model_invoice_member_count": 2,
            "read_model_row_count": 1,
            "input_invoice_usage_scope_count": 1,
            "workbench_relation_scope_count": 1,
            "active_workbench_pair_relation_count": 1,
            "linked_workbench_relation_group_count": 1,
        }

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
        if self.fail:
            raise RuntimeError("audit database timeout")
        self.fetch_all_calls.append((sql, params))
        return [dict(row) for row in self.rows_by_check.get(_audit_check_name(sql), [])]

    def execute(self, sql: str, params: tuple[object, ...] = ()) -> int:
        self.executed.append((sql, params))
        raise AssertionError("audit endpoint must be read-only")


class FakeOutputInvoiceCollectionAuditConnection(FakeInputInvoiceUsageAuditConnection):
    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("audit database timeout")
        self.fetch_one_calls.append((sql, params))
        return {
            "active_output_invoice_count": 2,
            "active_output_invoice_total_with_tax": "300.00",
            "read_model_invoice_member_count": 2,
            "read_model_row_count": 1,
            "output_invoice_collection_scope_count": 1,
            "workbench_relation_scope_count": 1,
            "active_workbench_pair_relation_count": 1,
            "linked_workbench_relation_group_count": 1,
        }


class FakePageBusinessAuditConnection(FakeInputInvoiceUsageAuditConnection):
    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("page audit database timeout")
        self.fetch_one_calls.append((sql, params))
        return {
            "source_fact_count": 2,
            "read_model_row_count": 2,
            "read_model_scope_count": 1,
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
            "dirty_scope_count": 0,
            "outbox_backlog_count": 0,
        }


class FakeRuntimeQueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> SimpleNamespace:
        self.enqueued.append(dict(kwargs))
        return SimpleNamespace(event_id=f"event-{len(self.enqueued)}", status="pending")

    def read_model_refresh_is_active(self, **_kwargs: object) -> bool:
        return False


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


def inject_operations_audit_connection(app, connection: object) -> None:
    app._runtime_repositories = SimpleNamespace(
        operations_audit_repository=PostgresOperationsAuditRepository(connection),
        queue_repository=getattr(app._runtime_repositories, "queue_repository", None),
    )


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

    def test_app_health_builds_snapshot_once_per_request(self) -> None:
        app = build_application()

        class CountingAppHealthService:
            def __init__(self, delegate: object) -> None:
                self._delegate = delegate
                self.calls = 0

            def build_snapshot(self, **kwargs: object) -> dict[str, object]:
                self.calls += 1
                return self._delegate.build_snapshot(**kwargs)

            def __getattr__(self, name: str) -> object:
                return getattr(self._delegate, name)

        service = CountingAppHealthService(app._app_health_service)
        app._app_health_service = service

        response = app.handle_request("GET", "/api/app-health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(service.calls, 1)

    def test_operation_barrier_status_returns_runtime_readiness_contract(self) -> None:
        app = build_application()
        requested_targets: list[list[dict[str, str]]] = []

        def operation_barrier_runtime_snapshot(targets: list[dict[str, str]]) -> dict[str, object]:
            requested_targets.append(targets)
            return {
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

        app._state_store = SimpleNamespace(
            operation_barrier_runtime_snapshot=operation_barrier_runtime_snapshot,
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
        self.assertEqual(
            requested_targets,
            [[{"read_model_key": "workbench_relation", "scope_type": "workbench_relation", "scope_key": "2026-02"}]],
        )

    def test_operation_barrier_fails_closed_without_target_scoped_runtime_provider(self) -> None:
        app = build_application()
        app._state_store = SimpleNamespace(app_status_runtime_snapshot=lambda: {})

        response = app.handle_request(
            "POST",
            "/api/operation-barrier/status",
            body=json.dumps({"targets": [{"read_model_key": "workbench_relation", "scope_key": "2026-02"}]}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "blocked")
        self.assertEqual(payload["targets"][0]["reason"], "runtime_unavailable")

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

    def test_app_health_caches_runtime_snapshot_briefly(self) -> None:
        app = build_application()
        calls = 0

        def runtime_snapshot() -> dict[str, object]:
            nonlocal calls
            calls += 1
            return {
                "read_model_statuses": {},
                "worker_statuses": {},
                "outbox_statuses": {},
            }

        app._state_store = SimpleNamespace(
            storage_mode="postgres",
            storage_backend="postgres",
            app_status_runtime_snapshot=runtime_snapshot,
            save_app_health_alerts=lambda _snapshot: None,
        )

        with self._temporary_env(FIN_OPS_APP_STATUS_RUNTIME_SNAPSHOT_CACHE_TTL_SECONDS="30"):
            app.handle_request("GET", "/api/app-health")
            app.handle_request("GET", "/api/app-health")

        self.assertEqual(calls, 1)

    def test_dirty_oa_scopes_block_workbench_write_actions(self) -> None:
        app = build_application()
        read_model_version = install_fresh_workbench_write_gate(app)
        inject_oa_sync_runtime_status(app, outbox_status="pending", scope_key="all")

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/confirm-link",
            body=json.dumps(
                {
                    "month": "all",
                    "row_ids": ["oa-missing"],
                    "expected_read_model_version": read_model_version,
                }
            ),
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
            label="生成正式配对关系",
            owner_user_id="test_finops_user",
            affected_months=["2026-05"],
        )
        app._background_job_service.fail_job(failed_job.job_id, "银行流水导入失败。", "boom")
        app._background_job_service.succeed_job(
            partial_job.job_id,
            "正式配对关系部分完成。",
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
            label="生成正式配对关系",
            owner_user_id="test_finops_user",
            affected_months=["2026-05"],
        )
        app._background_job_service.succeed_job(job.job_id, "正式配对关系部分完成。", status="partial_success")

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
        first_heartbeat_event = next(stream)
        snapshot_event = next(stream)
        second_heartbeat_event = next(stream)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.stream)
        self.assertIn("text/event-stream", response.headers["Content-Type"])
        self.assertIn("event: heartbeat", first_heartbeat_event)
        self.assertIn('"phase": "connected"', first_heartbeat_event)
        self.assertIn("event: app_health", snapshot_event)
        self.assertIn('"status": "ok"', snapshot_event)
        self.assertIn("event: heartbeat", second_heartbeat_event)

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
        self.assertEqual(set(invoice_sources), {"manual", "input_invoice", "output_invoice", "oa_attachment"})
        self.assertEqual(invoice_sources["input_invoice"]["count"], 1)
        self.assertEqual(invoice_sources["output_invoice"]["count"], 1)
        self.assertEqual(invoice_sources["oa_attachment"]["supplementary_count"], 1)
        oa_sources = {row["key"]: row for row in payload["data_inventory"]["oa"]["sources"]}
        self.assertEqual(set(oa_sources), {"oa_records", "oa_records_completed", "oa_records_in_progress", "oa_items"})
        self.assertEqual(oa_sources["oa_records_completed"]["count"], 2)
        self.assertEqual(oa_sources["oa_records_in_progress"]["count"], 1)
        import_source_keys = [row["source_key"] for row in payload["data_inventory"]["import_events"]]
        self.assertEqual(import_source_keys, ["bank_transactions"])
        self.assertNotIn("oa_attachment", import_source_keys)
        self.assertNotIn("oa_records", import_source_keys)

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

    def test_operations_input_invoice_usage_audit_returns_read_only_report_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=input-invoice-usage",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["tenant_id"], "default")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertIn("app.invoices", payload["audit_contract"]["source_tables"])
        self.assertIn("read_model.input_invoice_usage_rows", payload["audit_contract"]["source_tables"])
        self.assertIn("read_model.workbench_relation_rows", payload["audit_contract"]["source_tables"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.invoices", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)

    def test_operations_output_invoice_collection_audit_returns_read_only_report_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeOutputInvoiceCollectionAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=output-invoice-collections",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "dry-run")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertIn("read_model.output_invoice_collection_rows", payload["audit_contract"]["source_tables"])
        self.assertIn("read_model.workbench_relation_rows", payload["audit_contract"]["source_tables"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("read_model.output_invoice_collection_rows", queried_sql)
        self.assertIn("output_invoice_ids", queried_sql)

    def test_operations_input_invoice_usage_audit_reports_relation_issues_without_writes(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection(
                rows_by_check={
                    "relation_edge_equality": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-05",
                            "row_id": "inv-1",
                            "row_type": "input_invoice",
                            "mismatch_kind": "canonical_missing_group_edge",
                        }
                    ]
                }
            )
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=input-invoice-usage",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["overall_status"], "issues_found")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 1)
        self.assertEqual(
            payload["summary"]["issue_sample_counts_by_code"],
            {"input_invoice_usage_relation_edge_mismatch": 1},
        )
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_is_admin_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-details")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_operations_page_audit_returns_page_business_report_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-details")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "page-business-read-model-audit")
        self.assertEqual(payload["page_key"], "bank-details")
        self.assertEqual(payload["domain_key"], "bank_details")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        self.assertEqual(payload["audit_contract"]["contract_revision"], "page-audit-contract.v25")
        self.assertIn("app.bank_transactions", payload["audit_contract"]["source_tables"])
        self.assertIn("read_model.bank_detail_rows", payload["audit_contract"]["read_model_tables"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("read_model.bank_detail_rows", queried_sql)
        self.assertIn("read_model.workbench_relation_groups", queried_sql)

    def test_operations_page_audit_reports_page_invariants_without_writes(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection(
                rows_by_check={
                    "missing_read_model_row": [
                        {
                            "subject_id": "batch-1",
                            "scope_key": "2026-05",
                        }
                    ],
                    "relation_edge_equality": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-05",
                            "row_id": "bank-1",
                            "row_type": "bank_transaction",
                            "mismatch_kind": "canonical_missing_group_edge",
                        }
                    ],
                }
            )
            inject_operations_audit_connection(app, connection)

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-flow-rule-batches")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["overall_status"], "issues_found")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 2)
        self.assertEqual(
            payload["summary"]["issue_sample_counts_by_code"],
            {
                "bank_flow_rule_batches_relation_edge_mismatch": 1,
                "bank_flow_rule_batches_missing_read_model_row": 1,
            },
        )
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_dispatches_both_invoice_pages_through_the_unified_route(self) -> None:
        cases = (
            ("input-invoice-usage", FakeInputInvoiceUsageAuditConnection, "input_invoice_usage"),
            ("output-invoice-collections", FakeOutputInvoiceCollectionAuditConnection, "output_invoice_collection"),
        )
        for page_key, connection_factory, read_model_key in cases:
            with self.subTest(page_key=page_key), self._temporary_env(
                FIN_OPS_ADMIN_USERNAMES="test_finops_user"
            ), tempfile.TemporaryDirectory() as temp_dir:
                app = build_application(data_dir=Path(temp_dir))
                connection = connection_factory()
                inject_operations_audit_connection(app, connection)

                response = app.handle_request(
                    "GET",
                    f"/api/operations/app-health/page-audit?page={page_key}",
                )
                payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["page_key"], page_key)
            self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
            self.assertIn(read_model_key, payload["audit_contract"]["registered_read_model_keys"])
            queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
            self.assertIn("job.outbox_events", queried_sql)

    def test_operations_page_audit_dispatches_etc_direct_canonical_proof(self) -> None:
        with self._temporary_env(
            FIN_OPS_ADMIN_USERNAMES="test_finops_user"
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=etc-tickets",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["page_key"], "etc-tickets")
        self.assertEqual(payload["mode"], "etc-tickets-page-audit")
        self.assertEqual(payload["audit_contract"]["registered_read_model_keys"], [])
        self.assertTrue(payload["audit_contract"]["relation_proof_required"])
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("app.etc_business_batches", queried_sql)
        self.assertIn("app.etc_reconciliation_tasks", queried_sql)
        self.assertIn("app.etc_batch_invoice_links", queried_sql)
        self.assertIn("job.import_jobs", queried_sql)
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_dispatches_secret_safe_settings_proof(self) -> None:
        with self._temporary_env(
            FIN_OPS_ADMIN_USERNAMES="test_finops_user"
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=settings",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["page_key"], "settings")
        self.assertEqual(payload["mode"], "settings-page-audit")
        self.assertEqual(payload["audit_contract"]["registered_read_model_keys"], [])
        self.assertFalse(payload["audit_contract"]["relation_proof_required"])
        self.assertIn("not selected", payload["audit_contract"]["secret_policy"])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("app.app_settings", queried_sql)
        self.assertIn("app.oa_applicant_credentials", queried_sql)
        self.assertIn("job.background_jobs", queried_sql)
        self.assertNotIn("pgp_sym_decrypt", queried_sql)
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_requires_page_key(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            inject_operations_audit_connection(app, FakePageBusinessAuditConnection())

            response = app.handle_request("GET", "/api/operations/app-health/page-audit")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "page_audit_page_required")

    def test_operations_page_audit_rejects_unsupported_page(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            inject_operations_audit_connection(app, FakePageBusinessAuditConnection())

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=unknown")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "unsupported_page_audit_page")

    def test_operations_page_audit_returns_system_proof_for_app_health(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            inject_operations_audit_connection(app, FakePageBusinessAuditConnection())

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=app-health-operations",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["page_key"], "app-health-operations")
        self.assertEqual(payload["mode"], "app-health-system-audit")
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        self.assertEqual(payload["audit_contract"]["contract_revision"], "page-audit-contract.v25")
        self.assertEqual(payload["external_evidence"]["end_to_end_source_truth"], "unproven")

    def test_operations_page_audit_returns_unified_workbench_proof(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=reconciliation-workbench",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["page_key"], "reconciliation-workbench")
        self.assertEqual(payload["mode"], "workbench-page-audit")
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        self.assertIn("query_composed_relation_case_ownership", payload["audit_contract"]["proof_checks"])
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_requires_postgres_connection(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-details")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "postgres_required")

    def test_operations_input_invoice_usage_refresh_is_admin_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/input-invoice-usage-refresh",
                json.dumps({"scope_keys": ["2026-06"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_operations_pending_invoice_refresh_is_admin_only(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/pending-invoice-refresh",
                json.dumps({"scope_keys": ["expense:all"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_operations_input_invoice_usage_refresh_enqueues_valid_scopes_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/input-invoice-usage-refresh",
                json.dumps(
                    {
                        "scope_keys": ["2025-09", "2025-09", "2026-06"],
                        "reason": "production_audit_repair",
                        "metadata": {"audit": "input_invoice_usage"},
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_key"], "input_invoice_usage")
        self.assertEqual(payload["enqueued_scope_keys"], ["2025-09", "2026-06"])
        self.assertEqual(payload["enqueued_count"], 2)
        self.assertEqual([item["scope_type"] for item in queue.enqueued], ["input_invoice_usage", "input_invoice_usage"])
        self.assertEqual([item["scope_key"] for item in queue.enqueued], ["2025-09", "2026-06"])
        self.assertTrue(all(item["priority"] == "high" for item in queue.enqueued))
        self.assertTrue(all(item["reason"] == "production_audit_repair" for item in queue.enqueued))
        self.assertEqual(queue.enqueued[0]["metadata"]["source"], "operations_app_health")
        self.assertEqual(queue.enqueued[0]["metadata"]["audit"], "input_invoice_usage")

    def test_operations_output_invoice_collection_refresh_enqueues_valid_scopes_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/output-invoice-collection-refresh",
                json.dumps(
                    {
                        "scope_keys": ["2026-01", "2026-01", "2026-06"],
                        "reason": "production_audit_repair",
                        "metadata": {"audit": "output_invoice_collection"},
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_key"], "output_invoice_collection")
        self.assertEqual(payload["enqueued_scope_keys"], ["2026-01", "2026-06"])
        self.assertEqual(payload["enqueued_count"], 2)
        self.assertEqual([item["scope_type"] for item in queue.enqueued], ["output_invoice_collection", "output_invoice_collection"])
        self.assertEqual([item["scope_key"] for item in queue.enqueued], ["2026-01", "2026-06"])
        self.assertTrue(all(item["priority"] == "high" for item in queue.enqueued))
        self.assertTrue(all(item["reason"] == "production_audit_repair" for item in queue.enqueued))
        self.assertEqual(queue.enqueued[0]["metadata"]["source"], "operations_app_health")
        self.assertEqual(queue.enqueued[0]["metadata"]["audit"], "output_invoice_collection")

    def test_operations_pending_invoice_refresh_enqueues_valid_scopes_for_admin(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/pending-invoice-refresh",
                json.dumps(
                    {
                        "scope_keys": ["expense:all", "expense:all", "income:all"],
                        "reason": "production_audit_repair",
                        "metadata": {"audit": "pending_invoice"},
                    }
                ),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_key"], "pending_invoice")
        self.assertEqual(payload["enqueued_scope_keys"], ["expense:all", "income:all"])
        self.assertEqual(payload["enqueued_count"], 2)
        self.assertEqual([item["scope_type"] for item in queue.enqueued], ["pending_invoice", "pending_invoice"])
        self.assertEqual([item["scope_key"] for item in queue.enqueued], ["expense:all", "income:all"])
        self.assertTrue(all(item["priority"] == "high" for item in queue.enqueued))
        self.assertTrue(all(item["reason"] == "production_audit_repair" for item in queue.enqueued))
        self.assertEqual(queue.enqueued[0]["metadata"]["source"], "operations_app_health")
        self.assertEqual(queue.enqueued[0]["metadata"]["audit"], "pending_invoice")

    def test_operations_input_invoice_usage_refresh_rejects_invalid_scope(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/input-invoice-usage-refresh",
                json.dumps({"scope_keys": ["not-a-month"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_input_invoice_usage_refresh_scope")
        self.assertEqual(queue.enqueued, [])

    def test_operations_output_invoice_collection_refresh_rejects_invalid_scope(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/output-invoice-collection-refresh",
                json.dumps({"scope_keys": ["not-a-month"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_output_invoice_collection_refresh_scope")
        self.assertEqual(queue.enqueued, [])

    def test_operations_pending_invoice_refresh_rejects_invalid_scope(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/pending-invoice-refresh",
                json.dumps({"scope_keys": ["2026-06"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_pending_invoice_refresh_scope")
        self.assertEqual(queue.enqueued, [])

    def test_operations_input_invoice_usage_refresh_requires_runtime_queue(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._runtime_repositories = SimpleNamespace(queue_repository=object())

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/input-invoice-usage-refresh",
                json.dumps({"scope_keys": ["2026-06"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "runtime_queue_required")

    def test_operations_output_invoice_collection_refresh_requires_runtime_queue(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._runtime_repositories = SimpleNamespace(queue_repository=object())

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/output-invoice-collection-refresh",
                json.dumps({"scope_keys": ["2026-06"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "runtime_queue_required")

    def test_operations_pending_invoice_refresh_requires_runtime_queue(self) -> None:
        with self._temporary_env(FIN_OPS_ADMIN_USERNAMES="test_finops_user"), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._runtime_repositories = SimpleNamespace(queue_repository=object())

            response = app.handle_request(
                "POST",
                "/api/operations/app-health/pending-invoice-refresh",
                json.dumps({"scope_keys": ["expense:all"]}),
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "runtime_queue_required")


def _audit_check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
