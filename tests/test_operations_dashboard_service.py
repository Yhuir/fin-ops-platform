from __future__ import annotations

import unittest
from datetime import UTC, datetime

from fin_ops_platform.services.api_performance_metrics import ApiPerformanceRecorder
from fin_ops_platform.services.operations_dashboard import OperationsDashboardService
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


class FakeDashboardConnection:
    def __init__(
        self,
        *,
        fail_invoice_inventory: bool = False,
        fail_import_events: bool = False,
    ) -> None:
        self.fail_invoice_inventory = fail_invoice_inventory
        self.fail_import_events = fail_import_events
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            if "nullif(status" in normalized:
                raise AssertionError("bank inventory must qualify bank_transactions.status when import_batches is joined")
            return {"total_count": 12, "latest_synced_at": datetime(2026, 5, 20, 10, 30, tzinfo=UTC)}
        if "from app.invoices" in normalized and "invoice_flags" in normalized:
            if self.fail_invoice_inventory:
                raise RuntimeError("invoice inventory missing")
            return {
                "total_count": 20,
                "manual_count": 14,
                "input_invoice_count": 17,
                "output_invoice_count": 3,
                "oa_attachment_count": 6,
                "oa_attachment_non_manual_count": 2,
                "latest_synced_at": datetime(2026, 5, 21, 8, 0, tzinfo=UTC),
                "manual_latest_synced_at": datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
                "input_invoice_latest_synced_at": datetime(2026, 5, 21, 8, 0, tzinfo=UTC),
                "output_invoice_latest_synced_at": datetime(2026, 5, 17, 8, 0, tzinfo=UTC),
                "oa_attachment_latest_synced_at": datetime(2026, 5, 22, 9, 0, tzinfo=UTC),
            }
        if "from app.oa_applications" in normalized and "oa_records_count" in normalized:
            if "read_model.oa_pending_payment_rows" in normalized:
                raise AssertionError("OA inventory must not use the retired OA pending payment read model")
            if "from app.oa_pending_payment_admissions" not in normalized:
                raise AssertionError("OA in-progress inventory must include canonical admissions")
            if "count(distinct oa_id)" not in normalized:
                raise AssertionError("OA in-progress inventory must deduplicate canonical rows")
            return {
                "oa_records_count": 7,
                "oa_records_completed_count": 5,
                "oa_records_in_progress_count": 6,
                "oa_pending_payment_in_progress_latest_synced_at": datetime(2026, 5, 20, 9, 45, tzinfo=UTC),
                "oa_items_count": 30,
                "oa_records_latest_synced_at": datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
                "latest_successful_sync_at": datetime(2026, 5, 20, 10, 5, tzinfo=UTC),
                "oa_latest_synced_at": datetime(2026, 5, 20, 10, 5, tzinfo=UTC),
            }
        if "count(*)::bigint as total from app.import_batches batch" in normalized:
            return {"total": 2}
        raise AssertionError(f"Unexpected fetch_one SQL: {sql}")

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if self.fail_import_events and "from app.import_batches" in normalized:
            raise RuntimeError("import events missing")
        if "from app.import_batches" in normalized and "batch_type in" in normalized:
            return [
                {
                    "event_id": "bank-batch-2",
                    "source_key": "bank_transactions",
                    "label": "流水导入",
                    "source_name": "bank-2.xlsx",
                    "imported_by": "ops",
                    "count": 8,
                    "supplementary_count": None,
                    "imported_at": datetime(2026, 5, 23, 10, 5, tzinfo=UTC),
                    "batch_status": "completed",
                    "file_status": "confirmed",
                    "session_status": "confirmed",
                    "job_status": "succeeded",
                },
                {
                    "event_id": "invoice-batch-1",
                    "source_key": "manual",
                    "label": "手工导入",
                    "source_name": "invoice-1.xlsx",
                    "imported_by": "ops",
                    "count": 6,
                    "supplementary_count": None,
                    "imported_at": datetime(2026, 5, 22, 10, 5, tzinfo=UTC),
                    "batch_status": "completed",
                    "file_status": "confirmed",
                    "session_status": "confirmed",
                    "job_status": "succeeded",
                },
            ]
        if "oa_attachment_source_links" in normalized:
            raise AssertionError("import events must not read OA attachment source links")
        if "from app.oa_sync_runs" in normalized and "sync_type = 'oa_projection'" in normalized:
            raise AssertionError("import events must not read OA sync runs")
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class FakeRuntimeRepository:
    def dashboard_outbox_metric(self) -> dict[str, object]:
        return {
            "pending_count": 3,
            "processing_count": 1,
            "failed_count": 2,
            "oldest_pending_age_seconds": 42.0,
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, object]]:
        return [
            {
                "event_type": "oa.sync",
                "queue": "job.outbox_events",
                "pending_count": 3,
                "processing_count": 1,
                "failed_count": 2,
                "status": "available",
            }
        ]

    def dashboard_worker_metrics(self) -> list[dict[str, object]]:
        return [{"worker_kind": "runtime-worker", "heartbeat_lag_seconds": 8.0, "status": "available"}]


class OperationsDashboardServiceTests(unittest.TestCase):
    def test_build_payload_reports_inventory_performance_and_runtime_metrics(self) -> None:
        recorder = ApiPerformanceRecorder()
        recorder.record_request(
            method="GET",
            route_path="/api/workbench",
            status_code=200,
            duration_ms=640.0,
            database_duration_ms=310.0,
            connection_acquire_duration_ms=12.0,
            sql_execute_fetch_duration_ms=298.0,
            database_query_count=5,
        )
        service = OperationsDashboardService(
            FakeDashboardConnection(),
            api_performance_recorder=recorder,
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        self.assertIn("generated_at", payload)
        self.assertEqual(payload["data_inventory"]["bank"]["total_count"], 12)
        self.assertEqual(payload["data_inventory"]["invoice"]["total_count"], 20)
        self.assertEqual(payload["data_inventory"]["oa"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertEqual(set(invoice_sources), {"manual", "input_invoice", "output_invoice", "oa_attachment"})
        self.assertEqual(invoice_sources["manual"]["count"], 14)
        self.assertEqual(invoice_sources["input_invoice"]["count"], 17)
        self.assertEqual(invoice_sources["input_invoice"]["latest_synced_at"], "2026-05-21T08:00:00+00:00")
        self.assertEqual(invoice_sources["output_invoice"]["count"], 3)
        self.assertEqual(invoice_sources["output_invoice"]["latest_synced_at"], "2026-05-17T08:00:00+00:00")
        self.assertEqual(invoice_sources["oa_attachment"]["count"], 6)
        self.assertEqual(invoice_sources["oa_attachment"]["supplementary_count"], 2)
        oa_sources = {row["key"]: row for row in payload["data_inventory"]["oa"]["sources"]}
        self.assertEqual(oa_sources["oa_records"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        self.assertEqual(oa_sources["oa_records_completed"]["count"], 5)
        self.assertEqual(oa_sources["oa_records_in_progress"]["count"], 6)
        self.assertEqual(oa_sources["oa_records_in_progress"]["latest_synced_at"], "2026-05-20T09:45:00+00:00")
        self.assertEqual(oa_sources["oa_items"]["count"], 30)
        self.assertEqual(oa_sources["oa_items"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        import_events = payload["data_inventory"]["import_events"]
        self.assertEqual([row["source_key"] for row in import_events], ["bank_transactions", "manual"])
        self.assertEqual([row["status"] for row in import_events], ["succeeded", "succeeded"])
        self.assertNotIn("oa_attachment", [row["source_key"] for row in import_events])
        self.assertNotIn("oa_records", [row["source_key"] for row in import_events])
        endpoints = {row["endpoint"]: row for row in payload["request_performance"]["endpoints"]}
        self.assertEqual(endpoints["GET /api/workbench"]["duration_ms"]["p95"], 640.0)
        self.assertEqual(endpoints["GET /api/workbench"]["database_duration_ms"]["p99"], 310.0)
        self.assertNotIn("GET /api/search", endpoints)
        self.assertEqual(payload["runtime_performance"]["outbox"]["pending_count"], 3)
        self.assertEqual(payload["runtime_performance"]["queues"][0]["status"], "available")
        self.assertNotIn("rabbitmq_metrics_unavailable", payload["freshness"]["warnings"])

    def test_worker_warning_stays_row_level_only(self) -> None:
        class RuntimeRepository(FakeRuntimeRepository):
            def dashboard_queue_metrics(self) -> list[dict[str, object]]:
                return []

            def dashboard_worker_metrics(self) -> list[dict[str, object]]:
                return [
                    {
                        "worker_kind": "optional-maintenance",
                        "status": "stale",
                        "required": False,
                        "current_effective": False,
                        "warning_code": "worker_event_type_mismatch",
                    },
                    {
                        "worker_kind": "settings-maintenance",
                        "status": "missing",
                        "required": True,
                        "current_effective": True,
                        "warning_code": "required_worker_missing",
                    },
                ]

        service = OperationsDashboardService(
            FakeDashboardConnection(),
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=RuntimeRepository(),
        )

        payload = service.build_payload()
        worker_rows = {
            row["worker_kind"]: row
            for row in payload["runtime_performance"]["workers"]
        }

        self.assertEqual(worker_rows["optional-maintenance"]["warning_code"], "worker_event_type_mismatch")
        self.assertNotIn("worker_event_type_mismatch", payload["freshness"]["warnings"])
        self.assertIn("required_worker_missing", payload["freshness"]["warnings"])

    def test_invoice_inventory_unknown_uses_null_not_zero(self) -> None:
        service = OperationsDashboardService(
            FakeDashboardConnection(fail_invoice_inventory=True),
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertIsNone(invoice_sources["oa_attachment"]["count"])
        self.assertIsNone(invoice_sources["oa_attachment"]["supplementary_count"])
        self.assertEqual(invoice_sources["oa_attachment"]["status"], "unknown")
        self.assertIn("invoice_inventory_unknown", payload["freshness"]["warnings"])

    def test_invoice_inventory_uses_canonical_source_links_not_oa_cache_or_workbench_rows(self) -> None:
        connection = FakeDashboardConnection()
        service = OperationsDashboardService(
            connection,
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        normalized_calls = [" ".join(sql.lower().split()) for sql, _params in connection.calls]
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertEqual(invoice_sources["manual"]["count"], 14)
        self.assertEqual(invoice_sources["oa_attachment"]["count"], 6)
        self.assertEqual(invoice_sources["oa_attachment"]["supplementary_count"], 2)
        self.assertTrue(any("jsonb_array_elements" in sql and "manual_invoice_import" in sql and "oa_attachment_invoice" in sql for sql in normalized_calls))
        self.assertFalse(any("from app.oa_attachment_invoice_cache" in sql for sql in normalized_calls))
        self.assertFalse(any("from read_model.workbench_rows" in sql for sql in normalized_calls))

    def test_import_events_failure_warns_without_blocking_inventory(self) -> None:
        connection = FakeDashboardConnection(fail_import_events=True)
        service = OperationsDashboardService(
            connection,
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        self.assertEqual(payload["data_inventory"]["bank"]["total_count"], 12)
        self.assertEqual(payload["data_inventory"]["import_events"], [])
        self.assertIn("import_events_unknown", payload["freshness"]["warnings"])

    def test_default_dashboard_runtime_metrics_use_postgres_only(self) -> None:
        class RuntimeOnlyConnection(FakeDashboardConnection):
            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized and "pending_count" in normalized:
                    return {
                        "pending_count": 0,
                        "processing_count": 0,
                        "failed_count": 0,
                        "oldest_pending_age_seconds": None,
                    }
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "metric_windows(window_name" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized:
                    return []
                if "from job.outbox_events" in normalized:
                    return []
                return super().fetch_all(sql, params)

        service = OperationsDashboardService(
            RuntimeOnlyConnection(),
            api_performance_recorder=ApiPerformanceRecorder(),
        )

        payload = service.build_payload()

        self.assertEqual(payload["runtime_performance"]["queues"], [])
        self.assertNotIn("rabbitmq_metrics_unavailable", payload["freshness"]["warnings"])

    def test_runtime_repository_outputs_postgres_queue_rows(self) -> None:
        class EmptyConnection:
            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized and "pending_count" in normalized:
                    return {
                        "pending_count": 0,
                        "processing_count": 0,
                        "failed_count": 0,
                        "oldest_pending_age_seconds": None,
                    }
                raise AssertionError(sql)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    return [
                        {
                            "event_type": "oa.sync",
                            "pending_count": 2,
                            "processing_count": 1,
                            "failed_count": 0,
                        }
                    ]
                if "from job.runtime_worker_heartbeats" in normalized:
                    return []
                raise AssertionError(sql)

        repository = RuntimeMonitoringRepository(EmptyConnection())

        queue_rows = repository.dashboard_queue_metrics()

        self.assertEqual(len(queue_rows), 1)
        self.assertEqual(queue_rows[0]["queue"], "job.outbox_events")
        self.assertEqual(queue_rows[0]["pending_count"], 2)
        self.assertEqual(queue_rows[0]["status"], "available")

    def test_runtime_repository_reports_missing_and_stale_required_workers(self) -> None:
        class WorkerConnection:
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.runtime_worker_heartbeats" in normalized:
                    return [
                        {
                            "worker_id": "worker-oa-sync-1",
                            "worker_kind": "oa-sync",
                            "status": "idle",
                            "heartbeat_lag_seconds": 900.0,
                        }
                    ]
                raise AssertionError(sql)

        repository = RuntimeMonitoringRepository(WorkerConnection())

        worker_rows = {row["worker_kind"]: row for row in repository.dashboard_worker_metrics()}

        self.assertEqual(worker_rows["oa-sync"]["status"], "stale")
        self.assertEqual(worker_rows["oa-sync"]["warning_code"], "worker_heartbeat_stale")
        self.assertEqual(worker_rows["workbench-matching"]["status"], "missing")
        self.assertEqual(worker_rows["workbench-matching"]["warning_code"], "required_worker_missing")

    def test_runtime_repository_splits_outbox_dashboard_attention_candidates(self) -> None:
        class CapturingConnection:
            def __init__(self) -> None:
                self.sql = ""

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                self.sql = sql
                return {
                    "pending_count": 0,
                    "processing_count": 2,
                    "failed_count": 0,
                    "oldest_pending_age_seconds": None,
                }

        connection = CapturingConnection()
        repository = RuntimeMonitoringRepository(connection)

        payload = repository.dashboard_outbox_metric()

        normalized_sql = " ".join(connection.sql.lower().split())
        self.assertEqual(payload["processing_count"], 2)
        self.assertIn("from job.outbox_events", normalized_sql)
        self.assertIn("status in ('pending', 'processing', 'failed', 'dead_lettered')", normalized_sql)
        self.assertNotIn("publish_status", normalized_sql)


if __name__ == "__main__":
    unittest.main()
