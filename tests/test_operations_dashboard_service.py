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
                "oa_attachment_count": 6,
                "oa_attachment_non_manual_count": 2,
                "latest_synced_at": datetime(2026, 5, 21, 8, 0, tzinfo=UTC),
                "manual_latest_synced_at": datetime(2026, 5, 18, 8, 0, tzinfo=UTC),
                "oa_attachment_latest_synced_at": datetime(2026, 5, 22, 9, 0, tzinfo=UTC),
            }
        if "from app.oa_applications" in normalized and "oa_records_count" in normalized:
            return {
                "oa_records_count": 7,
                "oa_records_completed_count": 5,
                "oa_records_in_progress_count": 2,
                "oa_items_count": 30,
                "oa_records_latest_synced_at": datetime(2026, 5, 19, 11, 0, tzinfo=UTC),
                "latest_successful_sync_at": datetime(2026, 5, 20, 10, 5, tzinfo=UTC),
                "oa_latest_synced_at": datetime(2026, 5, 20, 10, 5, tzinfo=UTC),
            }
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
                    "status": "completed",
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
                    "status": "completed",
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
            "publishing_count": 1,
            "failed_count": 2,
            "publish_failed_count": 1,
            "oldest_pending_age_seconds": 42.0,
            "status": "available",
        }

    def dashboard_queue_metrics(self) -> list[dict[str, object]]:
        return [
            {
                "event_type": "workbench.read_model.refresh",
                "queue": "finops.workbench.read_model.refresh",
                "messages": None,
                "unacked": None,
                "consumers": None,
                "dlq_messages": None,
                "status": "unknown",
                "warning_code": "rabbitmq_metrics_unavailable",
            }
        ]

    def dashboard_read_model_metrics(self) -> list[dict[str, object]]:
        return [
            {
                "key": "workbench",
                "refresh_duration_ms": {"p50": 100.0, "p95": 250.0, "p99": 300.0},
                "stale_count": 1,
                "unavailable_count": 0,
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
        self.assertEqual(payload["data_inventory"]["oa"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        invoice_sources = {row["key"]: row for row in payload["data_inventory"]["invoice"]["sources"]}
        self.assertEqual(set(invoice_sources), {"manual", "oa_attachment"})
        self.assertEqual(invoice_sources["manual"]["count"], 14)
        self.assertEqual(invoice_sources["oa_attachment"]["count"], 6)
        self.assertEqual(invoice_sources["oa_attachment"]["supplementary_count"], 2)
        oa_sources = {row["key"]: row for row in payload["data_inventory"]["oa"]["sources"]}
        self.assertEqual(oa_sources["oa_records"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        self.assertEqual(oa_sources["oa_records_completed"]["count"], 5)
        self.assertEqual(oa_sources["oa_records_in_progress"]["count"], 2)
        self.assertEqual(oa_sources["oa_items"]["count"], 30)
        self.assertEqual(oa_sources["oa_items"]["latest_synced_at"], "2026-05-20T10:05:00+00:00")
        import_events = payload["data_inventory"]["import_events"]
        self.assertEqual([row["source_key"] for row in import_events], ["bank_transactions", "manual"])
        self.assertNotIn("oa_attachment", [row["source_key"] for row in import_events])
        self.assertNotIn("oa_records", [row["source_key"] for row in import_events])
        endpoints = {row["endpoint"]: row for row in payload["request_performance"]["endpoints"]}
        self.assertEqual(endpoints["GET /api/workbench/summary"]["duration_ms"]["p95"], 640.0)
        self.assertEqual(endpoints["GET /api/workbench/summary"]["database_duration_ms"]["p99"], 310.0)
        self.assertEqual(endpoints["GET /api/search"]["duration_ms"]["p95"], None)
        self.assertEqual(payload["runtime_performance"]["outbox"]["pending_count"], 3)
        self.assertEqual(payload["runtime_performance"]["queues"][0]["status"], "unknown")
        self.assertIn("rabbitmq_metrics_unavailable", payload["freshness"]["warnings"])

    def test_optional_historical_worker_warning_stays_row_level_only(self) -> None:
        class RuntimeRepository(FakeRuntimeRepository):
            def dashboard_queue_metrics(self) -> list[dict[str, object]]:
                return []

            def dashboard_worker_metrics(self) -> list[dict[str, object]]:
                return [
                    {
                        "worker_kind": "cost-tax-read-model",
                        "status": "stale",
                        "required": False,
                        "current_effective": False,
                        "warning_code": "worker_event_type_mismatch",
                    },
                    {
                        "worker_kind": "workbench-read-model",
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

        self.assertEqual(worker_rows["cost-tax-read-model"]["warning_code"], "worker_event_type_mismatch")
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

    def test_default_dashboard_runtime_metrics_do_not_block_on_rabbitmq_management(self) -> None:
        class RuntimeOnlyConnection(FakeDashboardConnection):
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
                if "from read_model.workbench_generations" in normalized and "consistency_status" in normalized:
                    return {"inconsistent_count": 0}
                return super().fetch_one(sql, params)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "metric_windows(window_name" in normalized:
                    return []
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized:
                    return []
                return super().fetch_all(sql, params)

        service = OperationsDashboardService(
            RuntimeOnlyConnection(),
            api_performance_recorder=ApiPerformanceRecorder(),
        )

        payload = service.build_payload()

        self.assertTrue(payload["runtime_performance"]["queues"])
        self.assertEqual(payload["runtime_performance"]["queues"][0]["status"], "unknown")
        self.assertIn("rabbitmq_metrics_unavailable", payload["freshness"]["warnings"])

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
                            "worker_id": "worker-search-1",
                            "worker_kind": "search-pending-read-model",
                            "status": "idle",
                            "heartbeat_lag_seconds": 900.0,
                        }
                    ]
                raise AssertionError(sql)

        repository = RuntimeMonitoringRepository(WorkerConnection(), rabbitmq_metrics_provider=object())

        worker_rows = {row["worker_kind"]: row for row in repository.dashboard_worker_metrics()}

        self.assertEqual(worker_rows["search-pending-read-model"]["status"], "stale")
        self.assertEqual(worker_rows["search-pending-read-model"]["warning_code"], "worker_heartbeat_stale")
        self.assertEqual(worker_rows["workbench-read-model"]["status"], "missing")
        self.assertEqual(worker_rows["workbench-read-model"]["warning_code"], "required_worker_missing")

    def test_runtime_repository_uses_recent_window_for_read_model_health_duration(self) -> None:
        class WindowedConnection:
            def __init__(self) -> None:
                self.fetch_one_sql: list[str] = []

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                self.fetch_one_sql.append(normalized)
                if "from read_model.workbench_generations" in normalized and "consistency_status" in normalized:
                    return {"inconsistent_count": 0}
                raise AssertionError(sql)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "metric_windows(window_name" in normalized:
                    return [
                        {
                            "event_type": "workbench.read_model.refresh",
                            "window_name": "recent_15m",
                            "refresh_kind": "incremental",
                            "sample_count": 2,
                            "last_completed_at": "2026-05-28T10:00:00+00:00",
                            "p50_ms": 100.0,
                            "p95_ms": 120.0,
                            "p99_ms": 125.0,
                        },
                        {
                            "event_type": "workbench.read_model.refresh",
                            "window_name": "all_time",
                            "refresh_kind": "full",
                            "sample_count": 100,
                            "last_completed_at": "2026-05-28T09:00:00+00:00",
                            "p50_ms": 4000.0,
                            "p95_ms": 24000.0,
                            "p99_ms": 30000.0,
                        },
                    ]
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                raise AssertionError(sql)

        connection = WindowedConnection()
        repository = RuntimeMonitoringRepository(connection)

        rows = repository.dashboard_read_model_metrics()

        workbench = next(row for row in rows if row["key"] == "workbench")
        self.assertEqual(workbench["refresh_duration_ms"]["p95"], 120.0)
        self.assertEqual(workbench["historical_refresh_duration_ms"]["p95"], 24000.0)
        self.assertEqual(workbench["refresh_duration_windows"]["recent_15m"]["sample_count"], 2)
        self.assertIn("full", workbench["refresh_duration_by_kind"])
        self.assertTrue(
            any(
                "from read_model.workbench_generations" in sql and "consistency_status = 'inconsistent'" in sql
                for sql in connection.fetch_one_sql
            )
        )
        self.assertFalse(any("workbench_generation_consistency" in sql for sql in connection.fetch_one_sql))

    def test_runtime_repository_splits_outbox_dashboard_attention_candidates(self) -> None:
        class CapturingConnection:
            def __init__(self) -> None:
                self.sql = ""

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                self.sql = sql
                return {
                    "pending_count": 0,
                    "publishing_count": 0,
                    "failed_count": 0,
                    "publish_failed_count": 3,
                    "oldest_pending_age_seconds": None,
                }

        connection = CapturingConnection()
        repository = RuntimeMonitoringRepository(connection)

        payload = repository.dashboard_outbox_metric()

        normalized_sql = " ".join(connection.sql.lower().split())
        self.assertEqual(payload["publish_failed_count"], 3)
        self.assertIn("dashboard_outbox_attention_events as", normalized_sql)
        self.assertIn("union all", normalized_sql)
        self.assertIn("e.status in ('pending', 'failed', 'dead_lettered')", normalized_sql)
        self.assertIn("e.publish_status = 'publishing'", normalized_sql)
        self.assertIn("e.publish_status = 'failed'", normalized_sql)
        self.assertIn("e.status not in ('pending', 'failed', 'dead_lettered')", normalized_sql)

    def test_runtime_repository_bounds_read_model_duration_history_query(self) -> None:
        class CapturingConnection:
            def __init__(self) -> None:
                self.duration_sql = ""
                self.duration_params: tuple[object, ...] = ()

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "from read_model.workbench_generations" in normalized and "consistency_status" in normalized:
                    return {"inconsistent_count": 0}
                raise AssertionError(sql)

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                normalized = " ".join(sql.lower().split())
                if "metric_windows(window_name" in normalized:
                    self.duration_sql = sql
                    self.duration_params = params
                    return []
                if "from job.read_model_dirty_scopes" in normalized:
                    return []
                raise AssertionError(sql)

        connection = CapturingConnection()
        repository = RuntimeMonitoringRepository(connection)

        repository.dashboard_read_model_metrics()

        normalized_sql = " ".join(connection.duration_sql.lower().split())
        self.assertIn("cross join lateral", normalized_sql)
        self.assertIn("event_type_filter(event_type)", normalized_sql)
        self.assertIn("event_type like '%%.read_model.refresh'", normalized_sql)
        self.assertIn("order by updated_at desc", normalized_sql)
        self.assertIn("limit %s", normalized_sql)
        self.assertIn("'-infinity'::timestamptz", normalized_sql)
        self.assertNotIn("row_number() over", normalized_sql)
        self.assertNotIn("runtime_metric_rank", normalized_sql)
        self.assertEqual(len(connection.duration_params), 2)
        self.assertEqual(connection.duration_params[1], 512)


if __name__ == "__main__":
    unittest.main()
