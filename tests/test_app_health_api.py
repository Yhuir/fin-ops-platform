from __future__ import annotations

import json
import os
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from pathlib import Path
from threading import Lock
from time import sleep
from types import SimpleNamespace
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from fin_ops_platform.services.audit import AuditTrailService
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.postgres_repositories.operations_audit import PostgresOperationsAuditRepository

from tests.app_test_support import (
    build_local_state_application as build_application,
)
from tests.app_test_support import (
    configure_access_control,
)


class FakeOperationsDashboardConnection:
    def __init__(self) -> None:
        self.import_status = "completed"
        self.fail_read_model_metrics = False

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
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
        if "count(*)::bigint as total from app.import_batches batch" in normalized:
            return {"total": 1}
        if "from job.outbox_events" in normalized and "pending_count" in normalized:
            return {
                "pending_count": 0,
                "processing_count": 0,
                "failed_count": 0,
                "oldest_pending_age_seconds": None,
            }
        if "max_pending_age_seconds" in normalized:
            return {"max_pending_age_seconds": None}
        raise AssertionError(sql)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        normalized = " ".join(sql.lower().split())
        if self.fail_read_model_metrics and "metric_windows(window_name" in normalized:
            raise RuntimeError("read model metrics timeout")
        if "from app.import_batches" in normalized and "batch_type in" in normalized:
            return [
                {
                    "total": 1, "display_status": "succeeded" if self.import_status == "completed" else "awaiting_confirmation", "event_id": "batch-bank-1",
                    "source_key": "bank_transactions",
                    "label": "流水导入",
                    "source_name": "bank.xlsx",
                    "imported_by": "ops",
                    "count": 1,
                    "supplementary_count": None,
                    "imported_at": "2026-05-20T10:00:00+00:00",
                    "batch_status": self.import_status,
                    "file_status": "preview_ready" if self.import_status == "pending" else "confirmed",
                    "session_status": "preview_ready" if self.import_status == "pending" else "confirmed",
                    "job_status": None,
                }
            ]
        if "oa_attachment_source_links" in normalized:
            raise AssertionError("dashboard import events must not read OA attachment source links")
        if "from app.oa_sync_runs" in normalized and "sync_type = 'oa_projection'" in normalized:
            raise AssertionError("dashboard import events must not read OA sync runs")
        if "scoped_jobs" in normalized:
            return []
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
            "source_fact_count": 2,
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
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
            "source_fact_count": 2,
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
        }


class FakePageBusinessAuditConnection(FakeInputInvoiceUsageAuditConnection):
    def fetch_all(self, sql, params=()):
        if "from filtered) totals" in sql:
            self.fetch_all_calls.append((sql, params))
            return [{"event_id": None, "total": 0}]
        return super().fetch_all(sql, params)

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("page audit database timeout")
        self.fetch_one_calls.append((sql, params))
        if "app.tax_certified_import_records" in sql and "count(*) as count" in sql:
            return {"count": 0}
        return {
            "source_fact_count": 2,
            "active_relation_count": 1,
            "linked_relation_group_count": 1,
        }


class FakeRuntimeQueueRepository:
    def __init__(self) -> None:
        self.enqueued: list[dict[str, object]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> SimpleNamespace:
        self.enqueued.append(dict(kwargs))
        return SimpleNamespace(event_id=f"event-{len(self.enqueued)}", status="pending")

    def read_model_refresh_is_active(self, **_kwargs: object) -> bool:
        return False


class FakeBankImportWithdrawalService:
    def __init__(self) -> None:
        self.calls: list[dict[str, object]] = []

    def withdraw(self, **kwargs: object) -> dict[str, object]:
        self.calls.append(dict(kwargs))
        return {
            "status": "withdrawn",
            "batch_id": kwargs["batch_id"],
            "withdrawn_count": 2,
            "idempotent_replay": False,
        }


class FakeOperationHistoryRepository:
    EVENT_ID = "10000000-0000-4000-8000-000000000001"
    OPERATION_KEY = "request:request-1"

    def __init__(self) -> None:
        self.list_calls: list[dict[str, object]] = []
        self.detail_calls: list[str] = []

    def list_logical_operations(self, **kwargs: object) -> list[dict[str, object]]:
        self.list_calls.append(dict(kwargs))
        return [{**self._event(), "operation_key": self.OPERATION_KEY, "started_at": self._event()["occurred_at"]}]

    def get_operation_history_snapshot(self, operation_key: str):
        return self.get_logical_operation(operation_key), self.list_operation_events_for_key(operation_key)

    def get_logical_operation(self, operation_key: str) -> dict[str, object] | None:
        return {**self._event(), "operation_key": operation_key} if operation_key == self.OPERATION_KEY else None

    def list_operation_actors(self) -> list[dict[str, object]]:
        return [{"actor_id": "005", "actor_name": "权限管理员", "actor_account": "YNSYLP005"}]

    def list_operation_events_for_key(self, operation_key: str) -> list[dict[str, object]]:
        self.detail_calls.append(operation_key)
        return [self._event()] if operation_key == self.OPERATION_KEY else []

    def list_workbench_relation_history_for_request(self, _request_id: str) -> list[dict[str, object]]:
        return []

    @classmethod
    def _event(cls) -> dict[str, object]:
        return {
            "id": cls.EVENT_ID,
            "event_type": "operation.completed",
            "actor_id": "005",
            "actor_name": "权限管理员",
            "actor_account": "YNSYLP005",
            "action": "POST /api/workbench/actions/confirm-link",
            "page_key": "reconciliation-workbench",
            "operation_location": "/api/workbench/actions/confirm-link",
            "object_type": "http_request",
            "object_id": "request-1",
            "occurred_at": datetime(2026, 8, 9, 12, 0, tzinfo=UTC),
            "outcome": "success",
            "reason": None,
            "request_id": "request-1",
            "payload": {"summary": "确认关联", "before": None, "after": None},
        }


class FakeDurableAuditRepository:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.events: list[dict[str, object]] = []

    def append_operation_event(self, event: dict[str, object]) -> dict[str, object]:
        if self.fail:
            raise RuntimeError("audit database unavailable")
        self.events.append(dict(event))
        return {"id": f"10000000-0000-4000-8000-{len(self.events):012d}"}


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
        "counts": {outbox_status: 1},
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
    @staticmethod
    def _build_admin_application(*, data_dir: Path):
        return build_application(data_dir=data_dir, test_username="YNSYLP005")

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
        self.assertEqual(payload["workbench_matching"]["status"], "ready")
        self.assertEqual(payload["background_jobs"]["active"], 0)
        self.assertIn("dependencies", payload)
        self.assertEqual(payload["version"], 1)
        self.assertIn("metrics", payload)
        self.assertEqual(payload["alerts"]["active"], [])

    def test_app_health_uses_durable_import_payload_and_preserves_review_state(self) -> None:
        app = build_application()
        job = {"job_id":"import:review", "type":"file_import", "label":"发票导入",
               "short_label":"请复核预览", "status":"needs_review", "phase":"commit",
               "source":{"route":"/imports/invoices"}, "affected_domains":["imports_invoices"],
               "route":"/imports/invoices", "attention":True, "retryable":True,
               "retry_mode":"reprepare", "acknowledgeable":False}
        with patch.object(app, "_import_workflow", return_value=SimpleNamespace(active_payloads=lambda owner:[job])):
            response=app.handle_request("GET", "/api/app-health")
        payload=json.loads(response.body)
        self.assertEqual(response.status_code,200)
        self.assertEqual(payload['background_jobs']['attention'],1)
        self.assertEqual(payload['app_status']['background_tasks'][0]['status'],'needs_review')
        domains={item['key']:item for item in payload['app_status']['domains']}
        self.assertEqual(domains['imports_bank_transactions']['status'],'ready')
        self.assertEqual(domains['imports_invoices']['status'],'needs_review')
        self.assertFalse(payload['app_status']['overall']['blocks_mutations'])

    def test_active_jobs_loads_one_snapshot_and_preserves_owner_and_attention(self) -> None:
        app = build_application()
        service = app._background_job_service
        active = service.create_job(job_type="settings_data_reset", label="active", owner_user_id="test_finops_user")
        failed = service.create_job(job_type="settings_data_reset", label="failed", owner_user_id="test_finops_user")
        hidden = service.create_job(job_type="settings_data_reset", label="hidden", owner_user_id="other")
        service.fail_job(failed.job_id, "failed", "test failure")
        with patch.object(service, "_load_jobs", wraps=service._load_jobs) as load:
            response = app.handle_request("GET", "/api/background-jobs/active")
        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(load.call_count, 1)
        self.assertIn(active.job_id, [job["job_id"] for job in payload["active_jobs"]])
        self.assertIn(failed.job_id, [job["job_id"] for job in payload["attention_jobs"]])
        self.assertNotIn(hidden.job_id, [job["job_id"] for job in payload["jobs"]])

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

    def test_operation_history_is_visible_to_protected_admin_and_supports_detail(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            repository = FakeOperationHistoryRepository()
            app._runtime_repositories = SimpleNamespace(operations_audit_repository=repository)

            list_response = app.handle_request(
                "GET",
                "/api/operations/history?limit=25&search=%E5%85%B3%E8%81%94",
            )
            detail_response = app.handle_request(
                "GET",
                f"/api/operations/history/{repository.OPERATION_KEY}",
            )
            actors_response = app.handle_request("GET", "/api/operations/history/actors")

        list_payload = json.loads(list_response.body)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(list_payload["rows"][0]["actor_id"], "005")
        self.assertEqual(repository.list_calls[0]["limit"], 26)
        self.assertEqual(repository.list_calls[0]["search"], "关联")
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_payload["operation"]["operation_key"], repository.OPERATION_KEY)
        self.assertEqual(json.loads(actors_response.body)["rows"][0]["actor_account"], "YNSYLP005")

    def test_operation_history_rejects_invalid_filters_and_passes_category_and_outcome(self):
        app = build_application(test_username="YNSYLP005")
        self.addCleanup(app.close)
        repository = FakeOperationHistoryRepository()
        app._runtime_repositories = SimpleNamespace(operations_audit_repository=repository)
        for query in ("category=other", "outcome=succeeded", "limit=201", "limit=0", "date_from=2026-10-11&date_to=2026-10-10"):
            response = app.handle_request("GET", "/api/operations/history?" + query)
            self.assertEqual(response.status_code, 400)
            self.assertEqual(json.loads(response.body)["error"], "invalid_operation_history_query")
        self.assertEqual(repository.list_calls, [])
        response = app.handle_request("GET", "/api/operations/history?category=oa&outcome=failed&limit=200")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.list_calls[0]["category"], "oa")
        self.assertEqual(repository.list_calls[0]["outcome"], "failed")
        self.assertEqual(repository.list_calls[0]["limit"], 201)

    def test_operation_history_rejects_non_admin_without_querying_repository(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, usernames=["YNSYLP006"])
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="006",
                username="YNSYLP006",
                nickname="普通用户",
                display_name="普通用户",
            )
            repository = FakeOperationHistoryRepository()
            app._runtime_repositories = SimpleNamespace(operations_audit_repository=repository)

            response = app.handle_request(
                "GET",
                "/api/operations/history",
                headers={"Authorization": "Bearer full-token"},
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "admin_access_required")
        self.assertEqual(repository.list_calls, [])

    def test_mutation_records_requested_and_completed_events_with_one_request_id(self) -> None:
        app = build_application()
        repository = FakeDurableAuditRepository()
        app._audit_service = AuditTrailService(repository)

        response = app.handle_request("PUT", "/api/bank-details/auto-tag-rules", body="{")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            [event["event_type"] for event in repository.events],
            [
                "operation.requested",
                "operation.completed",
            ],
        )
        self.assertEqual(repository.events[0]["request_id"], repository.events[1]["request_id"])
        self.assertEqual(repository.events[0]["outcome"], "pending")
        self.assertEqual(repository.events[1]["outcome"], "failed")
        self.assertEqual(repository.events[0]["page_key"], "bank-details")
        self.assertEqual(repository.events[0]["action"], "bank.auto_tag_rules.update")
        self.assertEqual(repository.events[1]["action"], "bank.auto_tag_rules.update")
        self.assertEqual(repository.events[0]["object_type"], "bank_tag_rule")
        requested_metadata = repository.events[0]["payload"]["metadata"]
        completed_metadata = repository.events[1]["payload"]["metadata"]
        self.assertEqual(requested_metadata["action_label"], "保存自动标签规则")
        self.assertEqual(requested_metadata["object_label"], "流水标签规则")
        self.assertEqual(completed_metadata["action_label"], "保存自动标签规则")
        self.assertEqual(repository.events[0]["payload"]["summary"], "保存自动标签规则")
        self.assertEqual(repository.events[1]["payload"]["summary"], "保存自动标签规则")
        self.assertEqual(repository.events[0]["actor_name"], repository.events[1]["actor_name"])
        self.assertEqual(repository.events[0]["actor_account"], repository.events[1]["actor_account"])
        self.assertTrue(repository.events[0]["actor_name"])
        self.assertTrue(repository.events[0]["actor_account"])

    def test_mutation_api_trace_records_timing_and_allowlisted_parameters_without_secrets(self):
        app = build_application()
        self.addCleanup(app.close)
        repository = FakeDurableAuditRepository()
        app._audit_service = AuditTrailService(repository)
        app.handle_request("PUT", "/api/bank-details/auto-tag-rules?token=never-appear&month=2026-10",
            body=json.dumps({"password": "never-appear", "nested": {"cookie": "never-appear"}, "unknown": "never-appear"}))
        trace = repository.events[-1]["payload"]["metadata"]["api_call"]
        self.assertEqual(trace["method"], "PUT")
        self.assertEqual(trace["path"], "/api/bank-details/auto-tag-rules")
        self.assertEqual(trace["parameters"], {"month": "2026-10"})
        self.assertGreaterEqual(trace["duration_ms"], 0)
        self.assertIsInstance(trace["status_code"], int)
        self.assertNotIn("never-appear", str(repository.events))

    def test_registered_download_records_real_get_completion_without_auditing_normal_reads(self):
        app = build_application(test_username="YNSYLP005")
        self.addCleanup(app.close)
        repository = FakeDurableAuditRepository()
        app._audit_service = AuditTrailService(repository)
        def export_route(method, path, query, body, headers):
            if path.endswith("/export"):
                app._record_input_invoice_usage_export_download(None, "发票.xlsx", query)
                return app._input_invoice_usage_xlsx_response("发票.xlsx", b"xlsx", 3)
            return app._json_response(200, {"rows": []})
        app._input_invoice_usage_routes = lambda: SimpleNamespace(route=export_route)
        response = app.handle_request("GET", "/api/input-invoice-usage/export?month=2026-10")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.events[0]["event_type"], "operation.requested")
        completed = repository.events[-1]
        self.assertEqual(completed["event_type"], "operation.completed")
        self.assertEqual(completed["outcome"], "success")
        self.assertEqual(completed["payload"]["metadata"]["api_call"]["method"], "GET")
        self.assertEqual(completed["payload"]["metadata"]["api_call"]["status_code"], 200)
        self.assertEqual(completed["payload"]["metadata"]["evidence"]["target"]["title"], "发票.xlsx")
        recorded_count = len(repository.events)
        app.handle_request("GET", "/api/input-invoice-usage")
        self.assertEqual(len(repository.events), recorded_count)
        app._input_invoice_usage_routes = lambda: SimpleNamespace(route=lambda *args: app._json_response(400, {"error": "invalid_month"}))
        response = app.handle_request("GET", "/api/input-invoice-usage/export?month=invalid")
        self.assertEqual(response.status_code, 400)
        self.assertEqual(repository.events[-1]["outcome"], "failed")
        self.assertEqual(repository.events[-1]["payload"]["metadata"]["evidence"]["failure"]["code"], "invalid_month")
        app._input_invoice_usage_routes = lambda: SimpleNamespace(route=lambda *args: app._input_invoice_usage_xlsx_response("完整清单.xlsx", b"xlsx", 4))
        response = app.handle_request("GET", "/api/input-invoice-usage/export")
        self.assertEqual(response.status_code, 200)
        evidence = repository.events[-1]["payload"]["metadata"]["evidence"]
        self.assertEqual(evidence["target"]["title"], "完整清单.xlsx")
        self.assertEqual(evidence["target"]["fields"], [{"label": "记录数", "value": "4"}])

    def test_mutation_audit_normalizes_operation_routes_to_page_keys(self) -> None:
        self.assertEqual(
            Application._audit_page_key_for_route("/api/workbench/actions/confirm-link"),
            "reconciliation-workbench",
        )
        self.assertEqual(
            Application._audit_page_key_for_route("/imports/etc-invoices/confirm"),
            "imports.etc-invoices",
        )

    def test_mutation_fails_closed_when_requested_event_cannot_be_persisted(self) -> None:
        app = build_application()
        app._audit_service = AuditTrailService(FakeDurableAuditRepository(fail=True))

        response = app.handle_request("POST", "/api/unknown-write", body="{}")

        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "page_access_policy_missing")

    def test_dashboard_reads_inventory_and_queue_on_every_request(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_admin_application(data_dir=Path(directory))
            connection = FakeOperationsDashboardConnection()
            app._state_store._connection = connection
            with patch("fin_ops_platform.services.runtime_monitoring.RuntimeMonitoringRepository.dashboard_queue_metrics",
                       side_effect=[[{"failed_count": 1}], [{"failed_count": 0}]]):
                first = json.loads(app.handle_request("GET", "/api/operations/app-health-dashboard").body)
                connection.import_status = "pending"
                second = json.loads(app.handle_request("GET", "/api/operations/app-health-dashboard").body)
            self.assertEqual(first["runtime_performance"]["queues"][0]["failed_count"], 1)
            self.assertEqual(second["runtime_performance"]["queues"][0]["failed_count"], 0)
            self.assertEqual(first["data_inventory"]["import_events"][0]["status"], "succeeded")
            self.assertEqual(second["data_inventory"]["import_events"][0]["status"], "awaiting_confirmation")
            self.assertNotIn("import_jobs", second["runtime_performance"])

    def test_dashboard_build_error_is_not_replaced_by_previous_success(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_admin_application(data_dir=Path(directory))
            app._state_store._connection = FakeOperationsDashboardConnection()
            self.assertEqual(app.handle_request("GET", "/api/operations/app-health-dashboard").status_code, 200)
            with patch("fin_ops_platform.app.server.OperationsDashboardService.build_payload",
                       side_effect=RuntimeError("dashboard build failed")):
                with self.assertRaisesRegex(RuntimeError, "dashboard build failed"):
                    app.handle_request("GET", "/api/operations/app-health-dashboard")

    def test_history_filters_detail_missing_and_admin_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            app = self._build_admin_application(data_dir=Path(directory))
            app._state_store._connection = FakeOperationsDashboardConnection()
            response = app.handle_request("GET", "/api/operations/import-history?batch_type=bank_transaction&status=succeeded&page_size=100")
            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.body)
            self.assertEqual(payload["pagination"]["page_size"], 100)
            self.assertEqual(payload["rows"][0]["status"], "succeeded")
            for query in ("page=0", "page_size=101", "status=wrong", "start_date=bad", "batch_type=wrong"):
                result = app.handle_request("GET", "/api/operations/import-history?" + query)
                self.assertEqual(result.status_code, 400)
                self.assertEqual(json.loads(result.body)["error"], "invalid_import_history_request")
            detail = app.handle_request("GET", "/api/operations/import-history/batch-bank-1")
            self.assertEqual(detail.status_code, 200)
            self.assertEqual(json.loads(detail.body)["row"]["status"], "succeeded")
            with patch("fin_ops_platform.services.import_lifecycle_service.ImportLifecycleService.detail_event", side_effect=KeyError("missing")):
                missing = app.handle_request("GET", "/api/operations/import-history/missing")
            self.assertEqual(missing.status_code, 404)
            self.assertEqual(json.loads(missing.body)["error"], "import_batch_not_found")
            user = build_application(data_dir=Path(directory) / "user")
            user._resolve_request_session = lambda _headers=None: SimpleNamespace(allowed=True, role="user", can_access_page=lambda _page: False, identity=SimpleNamespace(username="ordinary", display_name="普通用户"))
            for path in ("/api/operations/import-history", "/api/operations/import-history/batch-bank-1"):
                self.assertEqual(user.handle_request("GET", path).status_code, 403)

    def test_operations_input_invoice_usage_audit_returns_read_only_report_for_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=input-invoice-usage",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "page-business-canonical-read-audit")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["tenant_id"], "default")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertIn("app.invoices", payload["audit_contract"]["source_tables"])
        self.assertEqual(payload["audit_contract"]["derived_tables"], [])
        self.assertIn("app.workbench_pair_relations", payload["audit_contract"]["relation_tables"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.invoices", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)

    def test_operations_output_invoice_collection_audit_returns_read_only_report_for_admin(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakeOutputInvoiceCollectionAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=output-invoice-collections",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "page-business-canonical-read-audit")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertIn("app.invoices", payload["audit_contract"]["source_tables"])
        self.assertEqual(payload["audit_contract"]["derived_tables"], [])
        self.assertIn("app.workbench_pair_relations", payload["audit_contract"]["relation_tables"])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.invoices", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)

    def test_operations_input_invoice_usage_audit_reports_relation_issues_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakeInputInvoiceUsageAuditConnection(
                rows_by_check={
                    "canonical_relation_invoice_member_exists": [
                        {
                            "subject_id": "case-1",
                            "scope_key": "2026-05",
                            "row_id": "inv-1",
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
            {"input_invoice_usage_canonical_relation_invoice_member_missing": 1},
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
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-details")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["mode"], "page-business-canonical-read-audit")
        self.assertEqual(payload["page_key"], "bank-details")
        self.assertEqual(payload["domain_key"], "bank_details")
        self.assertEqual(payload["overall_status"], "pass")
        self.assertEqual(payload["summary"]["blocking_issue_sample_count"], 0)
        self.assertEqual(payload["audit_contract"]["write_policy"], "read_only")
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        self.assertEqual(payload["audit_contract"]["contract_revision"], "page-audit-contract.v29")
        self.assertIn("app.bank_transactions", payload["audit_contract"]["source_tables"])
        self.assertEqual(payload["audit_contract"]["derived_tables"], [])
        self.assertEqual(connection.executed, [])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertIn("app.bank_transactions", queried_sql)
        self.assertIn("app.workbench_pair_relations", queried_sql)
        self.assertNotIn("read_model.", queried_sql)

    def test_operations_page_audit_reports_page_invariants_without_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection(
                rows_by_check={
                    "key_display_fields": [
                        {
                            "subject_id": "batch-1",
                            "scope_key": "2026-05",
                        }
                    ],
                    "consumer_relation_edge_equality": [
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
                "bank_flow_rule_batches_consumer_relation_edge_mismatch": 1,
                "bank_flow_rule_batches_key_display_fields_mismatch": 1,
            },
        )
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_dispatches_both_invoice_pages_through_the_unified_route(self) -> None:
        cases = (
            ("input-invoice-usage", FakeInputInvoiceUsageAuditConnection, "input_invoice_usage"),
            ("output-invoice-collections", FakeOutputInvoiceCollectionAuditConnection, "output_invoice_collection"),
        )
        for page_key, connection_factory, domain_key in cases:
            with self.subTest(page_key=page_key), tempfile.TemporaryDirectory() as temp_dir:
                app = self._build_admin_application(data_dir=Path(temp_dir))
                connection = connection_factory()
                inject_operations_audit_connection(app, connection)

                response = app.handle_request(
                    "GET",
                    f"/api/operations/app-health/page-audit?page={page_key}",
                )
                payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200)
            self.assertEqual(payload["page_key"], page_key)
            self.assertEqual(payload["domain_key"], domain_key)
            self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
            queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
            self.assertIn("app.invoices", queried_sql)
            self.assertNotIn("job.outbox_events", queried_sql)
            self.assertNotIn("read_model.", queried_sql)

    def test_operations_page_audit_dispatches_etc_direct_canonical_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
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
        self.assertTrue(payload["audit_contract"]["relation_proof_required"])
        self.assertEqual(payload["audit_contract"]["proof_availability"], "ready")
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("app.etc_business_batches", queried_sql)
        self.assertIn("app.etc_reconciliation_tasks", queried_sql)
        self.assertIn("app.etc_batch_invoice_links", queried_sql)
        self.assertIn("job.import_jobs", queried_sql)
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_dispatches_secret_safe_settings_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
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
        self.assertFalse(payload["audit_contract"]["relation_proof_required"])
        self.assertIn("not selected", payload["audit_contract"]["secret_policy"])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_all_calls)
        self.assertIn("app.app_settings", queried_sql)
        self.assertIn("app.oa_applicant_credentials", queried_sql)
        self.assertIn("job.background_jobs", queried_sql)
        self.assertNotIn("pgp_sym_decrypt", queried_sql)
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_requires_page_key(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            inject_operations_audit_connection(app, FakePageBusinessAuditConnection())

            response = app.handle_request("GET", "/api/operations/app-health/page-audit")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "page_audit_page_required")

    def test_operations_page_audit_rejects_unsupported_page(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            inject_operations_audit_connection(app, FakePageBusinessAuditConnection())

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=unknown")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "unsupported_page_audit_page")

    def test_operations_page_audit_returns_system_proof_for_app_health(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
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
        self.assertEqual(payload["audit_contract"]["contract_revision"], "page-audit-contract.v29")
        self.assertEqual(payload["external_evidence"]["end_to_end_source_truth"], "unproven")

    def test_operations_page_audit_returns_unified_workbench_proof(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            connection = FakePageBusinessAuditConnection()
            inject_operations_audit_connection(app, connection)

            response = app.handle_request(
                "GET",
                "/api/operations/app-health/page-audit?page=reconciliation-workbench",
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["page_key"], "reconciliation-workbench")
        self.assertEqual(payload["mode"], "workbench-canonical-page-audit")
        self.assertIn("app.workbench_pair_relations", payload["audit_contract"]["source_tables"])
        self.assertEqual(payload["audit_contract"]["derived_tables"], [])
        self.assertTrue(payload["audit_contract"]["relation_proof_required"])
        queried_sql = " ".join(sql for sql, _params in connection.fetch_one_calls + connection.fetch_all_calls)
        self.assertNotIn("read_model.", queried_sql)
        self.assertEqual(connection.executed, [])

    def test_operations_page_audit_requires_postgres_connection(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/operations/app-health/page-audit?page=bank-details")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 503)
        self.assertEqual(payload["error"], "postgres_required")

    def test_retired_page_read_model_refresh_routes_are_not_found(self) -> None:
        routes = (
            "/api/operations/app-health/input-invoice-usage-refresh",
            "/api/operations/app-health/output-invoice-collection-refresh",
            "/api/operations/app-health/pending-invoice-refresh",
        )
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._build_admin_application(data_dir=Path(temp_dir))
            queue = FakeRuntimeQueueRepository()
            app._runtime_repositories = SimpleNamespace(queue_repository=queue)

            for route in routes:
                with self.subTest(route=route):
                    response = app.handle_request(
                        "POST",
                        route,
                        json.dumps({"scope_keys": ["2026-06"]}),
                    )
                    payload = json.loads(response.body)

                    self.assertEqual(response.status_code, 404)
                    self.assertEqual(payload["error"], "not_found")

        self.assertEqual(queue.enqueued, [])


def _audit_check_name(sql: str) -> str:
    marker = "/* check:"
    if marker not in sql:
        return ""
    return sql.split(marker, 1)[1].split("*/", 1)[0].strip()


if __name__ == "__main__":
    unittest.main()
