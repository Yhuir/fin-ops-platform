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
        fail_oa_attachment_inventory: bool = False,
        fail_oa_attachment_cache_inventory: bool = False,
    ) -> None:
        self.fail_oa_attachment_inventory = fail_oa_attachment_inventory
        self.fail_oa_attachment_cache_inventory = fail_oa_attachment_cache_inventory
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from app.bank_transactions" in normalized:
            if "nullif(status" in normalized:
                raise AssertionError("bank inventory must qualify bank_transactions.status when import_batches is joined")
            return {"total_count": 12, "latest_synced_at": datetime(2026, 5, 20, 10, 30, tzinfo=UTC)}
        if "from app.invoices" in normalized and "invoice_flags" in normalized:
            return {
                "total_count": 20,
                "standard_count": 11,
                "manual_count": 2,
                "etc_count": 4,
                "app_oa_attachment_count": 3,
                "latest_synced_at": datetime(2026, 5, 21, 8, 0, tzinfo=UTC),
                "standard_latest_synced_at": datetime(2026, 5, 21, 8, 0, tzinfo=UTC),
                "manual_latest_synced_at": datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
                "etc_latest_synced_at": datetime(2026, 5, 17, 8, 0, tzinfo=UTC),
                "app_oa_attachment_latest_synced_at": datetime(2026, 5, 16, 8, 0, tzinfo=UTC),
            }
        if "from app.oa_attachment_invoice_cache" in normalized:
            if self.fail_oa_attachment_inventory or self.fail_oa_attachment_cache_inventory:
                raise RuntimeError("cache missing")
            return {"count": 3, "latest_synced_at": datetime(2026, 5, 22, 9, 0, tzinfo=UTC)}
        if "from app.oa_applications" in normalized and "oa_records_count" in normalized:
            return {
                "oa_records_count": 7,
                "oa_items_count": 30,
                "oa_records_latest_synced_at": datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
                "oa_latest_synced_at": datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
            }
        raise AssertionError(f"Unexpected fetch_one SQL: {sql}")

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        raise AssertionError(f"Unexpected fetch_all SQL: {sql}")


class FakeRuntimeRepository:
    def dashboard_outbox_metric(self) -> dict[str, object]:
        return {
            "pending_count": 3,
            "publishing_count": 1,
            "failed_count": 2,
            "publish_failed_count": 1,
            "oldest_pending_age_seconds": 42.0,
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, object]]:
        return [
            {
                "event_type": "oa.sync",
                "queue": "finops.oa.sync",
                "messages": None,
                "unacked": None,
                "consumers": None,
                "dlq_messages": None,
                "status": "unknown",
                "warning_code": "rabbitmq_metrics_unavailable",
            }
        ]

    def dashboard_worker_metrics(self) -> list[dict[str, object]]:
        return [{"worker_kind": "runtime-worker", "heartbeat_lag_seconds": 8.0, "status": "available"}]


class OperationsDashboardServiceTests(unittest.TestCase):
    def test_build_payload_reports_inventory_performance_and_runtime_metrics(self) -> None:
        recorder = ApiPerformanceRecorder()
        recorder.record_request(
            method="GET",
            route_path="/api/workbench/summary",
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
        self.assertEqual(payload["data_inventory"]["invoice"]["sources"][1]["key"], "oa_attachment")
        self.assertEqual(payload["data_inventory"]["invoice"]["sources"][1]["count"], 3)
        self.assertEqual(payload["data_inventory"]["oa"]["sources"][1]["count"], 30)
        endpoints = {row["endpoint"]: row for row in payload["request_performance"]["endpoints"]}
        self.assertEqual(endpoints["GET /api/workbench/summary"]["duration_ms"]["p95"], 640.0)
        self.assertEqual(endpoints["GET /api/workbench/summary"]["database_duration_ms"]["p99"], 310.0)
        self.assertEqual(endpoints["GET /api/search"]["duration_ms"]["p95"], None)
        self.assertEqual(payload["runtime_performance"]["outbox"]["pending_count"], 3)
        self.assertEqual(payload["runtime_performance"]["queues"][0]["status"], "unknown")
        self.assertNotIn("read_models", payload["runtime_performance"])
        self.assertIn("rabbitmq_metrics_unavailable", payload["freshness"]["warnings"])

    def test_oa_attachment_inventory_unknown_uses_null_not_zero(self) -> None:
        service = OperationsDashboardService(
            FakeDashboardConnection(fail_oa_attachment_inventory=True),
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertIsNone(invoice_sources["oa_attachment"]["count"])
        self.assertEqual(invoice_sources["oa_attachment"]["status"], "unknown")
        self.assertIn("invoice_oa_attachment_inventory_unknown", payload["freshness"]["warnings"])

    def test_oa_attachment_inventory_uses_cache_without_legacy_projection(self) -> None:
        connection = FakeDashboardConnection()
        service = OperationsDashboardService(
            connection,
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        normalized_calls = [" ".join(sql.lower().split()) for sql, _params in connection.calls]
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertEqual(invoice_sources["oa_attachment"]["count"], 3)
        self.assertTrue(any("from app.oa_attachment_invoice_cache" in sql for sql in normalized_calls))
        self.assertTrue(any("count(distinct concat_ws" in sql for sql in normalized_calls))
        self.assertTrue(any("document_kind, '') <> 'non_tax_receipt'" in sql for sql in normalized_calls))
        self.assertTrue(any("position('发票' in invoice_kind) > 0" in sql for sql in normalized_calls))
        self.assertFalse(any("from read_model." in sql and "workbench_" in sql for sql in normalized_calls))

    def test_oa_attachment_inventory_reports_unknown_when_cache_missing(self) -> None:
        connection = FakeDashboardConnection(fail_oa_attachment_cache_inventory=True)
        service = OperationsDashboardService(
            connection,
            api_performance_recorder=ApiPerformanceRecorder(),
            runtime_repository=FakeRuntimeRepository(),
        )

        payload = service.build_payload()

        normalized_calls = [" ".join(sql.lower().split()) for sql, _params in connection.calls]
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertIsNone(invoice_sources["oa_attachment"]["count"])
        self.assertEqual(invoice_sources["oa_attachment"]["status"], "unknown")
        self.assertIn("invoice_oa_attachment_inventory_unknown", payload["freshness"]["warnings"])
        self.assertFalse(any("from read_model." in sql and "workbench_" in sql for sql in normalized_calls))

    def test_runtime_repository_outputs_unknown_queue_rows_when_rabbitmq_metrics_unavailable(self) -> None:
        class EmptyConnection:
            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized and "pending_count" in normalized:
                    return {
                        "pending_count": 0,
                        "publishing_count": 0,
                        "failed_count": 0,
                        "publish_failed_count": 0,
                        "oldest_pending_age_seconds": None,
                    }
                raise AssertionError(sql)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.outbox_events" in normalized:
                    return []
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized:
                    return []
                raise AssertionError(sql)

        class UnavailableRabbitMq:
            def summary(self) -> dict[str, object]:
                return {"rabbitmq_management_configured": False}

        repository = RuntimeMonitoringRepository(EmptyConnection(), rabbitmq_metrics_provider=UnavailableRabbitMq())

        queue_rows = repository.dashboard_queue_metrics()

        self.assertGreaterEqual(len(queue_rows), 1)
        self.assertEqual(queue_rows[0]["messages"], None)
        self.assertEqual(queue_rows[0]["status"], "unknown")
        self.assertEqual(queue_rows[0]["warning_code"], "rabbitmq_metrics_unavailable")

    def test_runtime_repository_reports_missing_and_stale_required_workers(self) -> None:
        class WorkerConnection:
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from job.runtime_worker_heartbeats" in normalized:
                    return [
                        {
                            "worker_id": "worker-oa-sync-1",
                            "worker_instance": "oa-sync",
                            "worker_kind": "oa-sync",
                            "status": "idle",
                            "heartbeat_lag_seconds": 900.0,
                        }
                    ]
                raise AssertionError(sql)

        repository = RuntimeMonitoringRepository(WorkerConnection(), rabbitmq_metrics_provider=object())

        worker_rows = {row["worker_kind"]: row for row in repository.dashboard_worker_metrics()}

        self.assertEqual(worker_rows["oa-sync"]["status"], "stale")
        self.assertEqual(worker_rows["oa-sync"]["warning_code"], "worker_heartbeat_stale")
        self.assertEqual(worker_rows["workbench-matching"]["status"], "missing")
        self.assertEqual(worker_rows["workbench-matching"]["warning_code"], "required_worker_missing")

if __name__ == "__main__":
    unittest.main()
