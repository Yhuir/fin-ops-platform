from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_queue import DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository
from fin_ops_platform.services.runtime_worker_registry import required_worker_instance_names


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "like '%." in normalized:
            raise AssertionError("literal percent signs must be escaped for psycopg SQL")
        if "current_refresh_event_samples" in normalized:
            return [
                {
                    "event_id": "event-current-cost-statistics-1",
                    "event_type": "cost_statistics.fact.changed",
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                    "status": "done",
                    "source_version": 43,
                    "priority": "normal",
                    "duration_ms": 28000.0,
                    "enqueue_to_fresh_ms": 35000.0,
                    "created_at": "2026-06-13 03:08:00+08",
                    "processed_at": "2026-06-13 03:08:35+08",
                    "updated_at": "2026-06-13 03:08:35+08",
                    "skipped": False,
                    "skip_reason": "",
                }
            ]
        if "slow_refresh_event_samples" in normalized:
            return [
                {
                    "event_id": "event-cost-statistics-slow-1",
                    "event_type": "cost_statistics.fact.changed",
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                    "status": "done",
                    "source_version": 42,
                    "priority": "normal",
                    "duration_ms": 35000.0,
                    "enqueue_to_fresh_ms": 35150.0,
                    "created_at": "2026-06-13 03:00:00+08",
                    "processed_at": "2026-06-13 03:00:35+08",
                    "updated_at": "2026-06-13 03:00:35+08",
                    "skipped": False,
                    "skip_reason": "",
                },
                {
                    "event_id": "event-cost-statistics-1",
                    "event_type": "cost_statistics.fact.changed",
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                    "status": "done",
                    "source_version": 40,
                    "priority": "normal",
                    "duration_ms": 28000.0,
                    "enqueue_to_fresh_ms": 29000.0,
                    "created_at": "2026-06-13 02:59:00+08",
                    "processed_at": "2026-06-13 02:59:29+08",
                    "updated_at": "2026-06-13 02:59:29+08",
                    "skipped": False,
                    "skip_reason": "",
                },
            ]
        if "recent_refresh_events" in normalized:
            return [
                {
                    "window_name": "all_time",
                    "event_type": "__all__",
                    "p50_ms": 120.0,
                    "p95_ms": 300.0,
                    "p99_ms": 450.0,
                    "enqueue_p50_ms": 180.0,
                    "enqueue_p95_ms": 350.0,
                    "enqueue_p99_ms": 500.0,
                    "completed_sample_count": 9,
                    "failed_count": 1,
                    "read_model_refresh_total": 10,
                    "last_completed_at": "2026-06-13 03:00:00+08",
                    "last_fresh_at": "2026-06-13 03:00:01+08",
                },
                {
                    "window_name": "all_time",
                    "event_type": "cost_statistics.fact.changed",
                    "p50_ms": 200.0,
                    "p95_ms": 500.0,
                    "p99_ms": 650.0,
                    "enqueue_p50_ms": 220.0,
                    "enqueue_p95_ms": 550.0,
                    "enqueue_p99_ms": 700.0,
                    "completed_sample_count": 4,
                    "failed_count": 1,
                    "read_model_refresh_total": 5,
                    "last_completed_at": "2026-06-13 03:00:00+08",
                    "last_fresh_at": "2026-06-13 03:00:01+08",
                },
                {
                    "window_name": "all_time",
                    "event_type": "tax_offset.fact.changed",
                    "p50_ms": 50.0,
                    "p95_ms": 80.0,
                    "p99_ms": 90.0,
                    "enqueue_p50_ms": 70.0,
                    "enqueue_p95_ms": 100.0,
                    "enqueue_p99_ms": 110.0,
                    "completed_sample_count": 5,
                    "failed_count": 0,
                    "read_model_refresh_total": 5,
                    "last_completed_at": "2026-06-13 03:01:00+08",
                    "last_fresh_at": "2026-06-13 03:01:01+08",
                },
                {
                    "window_name": "recent_15m",
                    "event_type": "__all__",
                    "p50_ms": 90.0,
                    "p95_ms": 140.0,
                    "p99_ms": 180.0,
                    "enqueue_p50_ms": 100.0,
                    "enqueue_p95_ms": 160.0,
                    "enqueue_p99_ms": 200.0,
                    "completed_sample_count": 3,
                    "failed_count": 0,
                    "read_model_refresh_total": 3,
                    "last_completed_at": "2026-06-13 03:08:00+08",
                    "last_fresh_at": "2026-06-13 03:08:01+08",
                },
                {
                    "window_name": "recent_15m",
                    "event_type": "cost_statistics.fact.changed",
                    "p50_ms": 95.0,
                    "p95_ms": 150.0,
                    "p99_ms": 190.0,
                    "enqueue_p50_ms": 105.0,
                    "enqueue_p95_ms": 170.0,
                    "enqueue_p99_ms": 210.0,
                    "completed_sample_count": 2,
                    "failed_count": 0,
                    "read_model_refresh_total": 2,
                    "last_completed_at": "2026-06-13 03:08:00+08",
                    "last_fresh_at": "2026-06-13 03:08:01+08",
                },
            ]
        if "pending_outbox_by_scope" in normalized:
            return [
                {
                    "event_type": "import.fact.changed",
                    "status": "pending",
                    "scope_type": "import",
                    "scope_key": "all",
                    "count": 2,
                    "oldest_age_seconds": 610.0,
                    "attempts": 1,
                    "last_error": "",
                }
            ]
        if "dirty_scope_backlog_by_scope" in normalized:
            return [
                {
                    "scope_type": "cost_statistics",
                    "scope_key": "all",
                    "status": "pending",
                    "count": 1,
                    "oldest_age_seconds": 620.0,
                    "attempts": 2,
                    "last_error": "still refreshing",
                }
            ]
        if "workbench_generation_status_counts" in normalized:
            return [{"status": "active", "count": 3}, {"status": "building", "count": 1}]
        if "workbench_active_generation_totals" in normalized:
            return [
                {
                    "active_scope_count": 3,
                    "active_row_count": 150,
                    "active_group_count": 45,
                    "active_summary_count": 3,
                    "latest_generated_at": "2026-05-29 21:00:00+08",
                }
            ]
        if "select e.publish_status, count(*)::bigint as count" in normalized:
            return [{"publish_status": "unpublished", "count": 4}, {"publish_status": "failed", "count": 2}]
        if "from job.outbox_events" in normalized:
            return [{"status": "pending", "count": 3}, {"status": "failed", "count": 1}]
        return []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "like '%." in normalized:
            raise AssertionError("literal percent signs must be escaped for psycopg SQL")
        if "from job.runtime_worker_heartbeats" in normalized:
            return {"max_worker_heartbeat_lag_seconds": 8.0}
        if "rabbitmq_publish" in normalized:
            return {"p50_ms": 10.0, "p95_ms": 20.0, "p99_ms": 30.0}
        if "read_model_refresh_total" in normalized:
            return {"failed_count": 1, "read_model_refresh_total": 10}
        if "publish_status in" in normalized:
            return {"max_unpublished_age_seconds": 11.0}
        if "workbench_all_scope_generation" in normalized:
            return {
                "status": "building",
                "row_count": 0,
                "group_count": 0,
                "summary_count": 0,
                "updated_at": "2026-05-29 21:02:00+08",
                "last_error": "",
            }
        return {"max_pending_age_seconds": 42.0}


class FakeRabbitMqMetrics:
    def summary(self) -> dict[str, object]:
        return {
            "rabbitmq_management_configured": True,
            "rabbitmq_queue_depth": 5,
            "rabbitmq_unacked_messages": 1,
            "rabbitmq_consumer_count": 2,
            "rabbitmq_dlq_count": 0,
            "rabbitmq_oldest_message_age_seconds": None,
        }


class FakeWorkerMetricsConnection:
    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        normalized = " ".join(sql.lower().split())
        if "from job.runtime_worker_heartbeats" not in normalized:
            return []
        return [
            {
                "worker_id": "host-oa-sync",
                "worker_instance": "oa-sync",
                "worker_kind": "unexpected-kind",
                "status": "idle",
                "heartbeat_lag_seconds": 1.0,
                "payload": {
                    "worker_instance": "oa-sync",
                    "configured_event_types": ["cost_statistics.fact.changed"],
                },
            },
            {
                "worker_id": "host-legacy-relation",
                "worker_instance": "legacy-relation",
                "worker_kind": "legacy-relation-worker",
                "status": "idle",
                "heartbeat_lag_seconds": 999.0,
                "payload": {
                    "worker_instance": "legacy-relation",
                    "configured_event_types": ["cost_statistics.fact.changed"],
                },
            },
            {
                "worker_id": "host-bank-account-balance",
                "worker_instance": "bank-account-balance",
                "worker_kind": "bank-account-balance-read-model",
                "status": "idle",
                "heartbeat_lag_seconds": 2.0,
                "payload": {
                    "worker_instance": "bank-account-balance",
                    "configured_event_types": ["bank_account_balance.fact.changed"],
                },
            },
            {
                "worker_id": "host-import",
                "worker_instance": "import",
                "worker_kind": "import-job",
                "status": "idle",
                "heartbeat_lag_seconds": 3.0,
                "payload": {
                    "worker_instance": "import",
                    "configured_event_types": ["import.process.requested", "import.fact.changed"],
                },
            },
            {
                "worker_id": "host-cost-tax",
                "worker_instance": "cost-tax",
                "worker_kind": "cost-tax-read-model",
                "status": "idle",
                "heartbeat_lag_seconds": 4.0,
                "payload": {
                    "worker_instance": "cost-tax",
                    "configured_event_types": ["cost_statistics.fact.changed", "tax_offset.fact.changed"],
                },
            },
            {
                "worker_id": "operator-cost-statistics-drain-after-deploy-20260606",
                "worker_instance": "cost-tax-read-model",
                "worker_kind": "cost-tax-read-model",
                "status": "processing",
                "heartbeat_lag_seconds": 999999.0,
                "payload": {
                    "worker_instance": "cost-tax-read-model",
                    "configured_event_types": ["cost_statistics.fact.changed"],
                },
            },
        ]

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        return {}


class RuntimeMonitoringRepositoryTests(unittest.TestCase):
    def test_health_summary_reports_backlog_failed_jobs_and_worker_status(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection, rabbitmq_metrics_provider=FakeRabbitMqMetrics())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertNotIn("dirty_scopes", summary)
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["max_pending_age_seconds"], 42.0)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertEqual(summary["missing_required_worker_count"], len(required_worker_instance_names()))
        self.assertEqual(summary["stale_required_worker_count"], 0)
        self.assertEqual(summary["mismatched_required_worker_count"], 0)
        self.assertEqual(summary["worker_metrics"][0]["status"], "missing")
        self.assertNotIn("read_model_refresh_duration_ms", summary)
        self.assertNotIn("read_model_refresh_enqueue_to_fresh_ms", summary)
        self.assertNotIn("read_model_refresh_sample_count", summary)
        self.assertNotIn("read_model_refresh_failure_rate", summary)
        self.assertNotIn("read_model_refresh_by_key", summary)
        self.assertNotIn("read_model_refresh_slow_events", summary)
        self.assertEqual(summary["rabbitmq_publish_status"], {"unpublished": 4, "failed": 2})
        self.assertEqual(summary["rabbitmq_unpublished_backlog"], 4)
        self.assertEqual(summary["rabbitmq_publish_failed_backlog"], 2)
        self.assertEqual(summary["rabbitmq_dispatcher_lag_seconds"], 11.0)
        self.assertEqual(summary["rabbitmq_dispatch_event_types"], list(DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES))
        self.assertEqual(summary["rabbitmq_publish_confirm_latency_ms"], {"p50": 10.0, "p95": 20.0, "p99": 30.0})
        self.assertEqual(summary["rabbitmq_publish_confirm_sample_limit"], 512)
        self.assertEqual(summary["rabbitmq_queue_depth"], 5)
        self.assertEqual(summary["rabbitmq_unacked_messages"], 1)
        self.assertEqual(summary["rabbitmq_consumer_count"], 2)
        self.assertEqual(summary["rabbitmq_dlq_count"], 0)
        self.assertNotIn("stale_dirty_scope_count", summary)
        self.assertNotIn("stale_dirty_scopes", summary)
        self.assertEqual(
            summary["pending_outbox_events_by_scope"],
            [
                {
                    "event_type": "import.fact.changed",
                    "status": "pending",
                    "scope_type": "import",
                    "scope_key": "all",
                    "count": 2,
                    "oldest_age_seconds": 610.0,
                    "attempts": 1,
                    "last_error": "",
                }
            ],
        )
        self.assertNotIn("dirty_scopes_by_scope", summary)
        self.assertNotIn("workbench_read_model", summary)
        normalized_calls = [" ".join(sql.lower().split()) for sql, _ in connection.calls]
        self.assertFalse(any("recent_refresh_events" in sql for sql in normalized_calls))
        self.assertFalse(any("slow_refresh_event_samples" in sql for sql in normalized_calls))
        self.assertFalse(any("current_refresh_event_samples" in sql for sql in normalized_calls))
        publish_confirm_sql = next(sql for sql in normalized_calls if "recent_publish_confirms" in sql)
        self.assertIn("cross join lateral", publish_confirm_sql)
        self.assertIn("limit %s", publish_confirm_sql)
        queue_status_sql = next(
            sql
            for sql in normalized_calls
            if "select e.status, count(*)::bigint as count from job.outbox_events e" in sql
        )
        self.assertIn("where e.status <> 'done'", queue_status_sql)
        self.assertIn("done.status = 'done'", queue_status_sql)
        self.assertNotIn("read_model.app_status_readiness", queue_status_sql)
        self.assertNotIn("readiness.status = 'fresh'", queue_status_sql)
        publish_status_sql = next(
            sql
            for sql in normalized_calls
            if "select e.publish_status, count(*)::bigint as count from job.outbox_events e" in sql
        )
        self.assertIn("done.status = 'done'", publish_status_sql)
        self.assertNotIn("read_model.app_status_readiness", publish_status_sql)
        self.assertNotIn("readiness.status = 'fresh'", publish_status_sql)

    def test_ready_health_summary_uses_lightweight_runtime_contract(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection, rabbitmq_metrics_provider=FakeRabbitMqMetrics())

        summary = repository.ready_health_summary(stale_after_seconds=300)
        executed_sql = "\n".join(sql for sql, _params in connection.calls).lower()

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertNotIn("dirty_scopes", summary)
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertNotIn("read_model_refresh_sample_count", summary)
        self.assertNotIn("read_model_refresh_failure_rate", summary)
        self.assertEqual(summary["rabbitmq_publish_status"], {"unpublished": 4, "failed": 2})
        self.assertEqual(summary["rabbitmq_queue_depth"], 5)
        self.assertNotIn("stale_dirty_scope_count", summary)
        self.assertEqual(summary["pending_outbox_events_by_scope"][0]["event_type"], "import.fact.changed")
        self.assertNotIn("dirty_scopes_by_scope", summary)
        self.assertNotIn("read_model_refresh_duration_ms", summary)
        self.assertNotIn("read_model_refresh_by_key", summary)
        self.assertNotIn("read_model_refresh_slow_events", summary)
        self.assertNotIn("workbench_read_model", summary)
        self.assertNotIn(".read_model.refresh", executed_sql)
        self.assertIn("payload->>'scope_key'", executed_sql)
        self.assertNotIn("job.read_model_dirty_scopes", executed_sql)
        self.assertNotIn("read_model.app_status_readiness", executed_sql)
        self.assertNotIn("{_current_effective_dirty_scope_predicate_sql", executed_sql)
        self.assertNotIn("slow_refresh_event_samples", executed_sql)
        self.assertNotIn("current_refresh_event_samples", executed_sql)
        self.assertNotIn("workbench_generation_status_counts", executed_sql)
        self.assertNotIn("recent_publish_confirms", executed_sql)

    def test_dashboard_outbox_metric_only_scans_current_attention_statuses(self) -> None:
        class OutboxMetricConnection:
            def __init__(self) -> None:
                self.sql = ""

            def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
                self.sql = " ".join(sql.lower().split())
                return {
                    "pending_count": 1,
                    "publishing_count": 0,
                    "failed_count": 0,
                    "publish_failed_count": 0,
                    "oldest_pending_age_seconds": 2.0,
                }

        connection = OutboxMetricConnection()
        repository = RuntimeMonitoringRepository(connection)

        metric = repository.dashboard_outbox_metric()

        self.assertEqual(metric["pending_count"], 1)
        self.assertIn("where ( e.status in ('pending', 'failed', 'dead_lettered')", connection.sql)
        self.assertIn("or e.publish_status in ('publishing', 'failed')", connection.sql)
        self.assertNotIn(".read_model.refresh", connection.sql)
        self.assertIn("count(*) filter (where e.publish_status = 'failed')", connection.sql)
        self.assertIn("done.status = 'done'", connection.sql)
        self.assertNotIn("read_model.app_status_readiness", connection.sql)
        self.assertNotIn("readiness.status = 'fresh'", connection.sql)

    def test_dashboard_worker_metrics_are_registry_instance_aware(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        metrics = repository.dashboard_worker_metrics()
        by_instance = {row["worker_instance"]: row for row in metrics}

        self.assertEqual(by_instance["oa-sync"]["warning_code"], "worker_kind_mismatch")
        self.assertEqual(by_instance["oa-sync"]["expected_worker_kind"], "oa-sync")
        self.assertEqual(by_instance["oa-sync"]["worker_kind"], "unexpected-kind")
        self.assertFalse(by_instance["legacy-relation"]["required"])
        self.assertNotIn("warning_code", by_instance["legacy-relation"])
        self.assertFalse(by_instance["bank-account-balance"]["required"])
        self.assertFalse(by_instance["cost-tax-read-model"]["required"])
        self.assertTrue(by_instance["cost-tax-read-model"]["current_effective"])
        self.assertNotIn("warning_code", by_instance["cost-tax-read-model"])
        self.assertNotIn("warning_code", by_instance["import"])
        self.assertEqual(by_instance["workbench-matching"]["warning_code"], "required_worker_missing")

    def test_app_status_worker_snapshot_ignores_historical_optional_worker_heartbeats(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        snapshot = repository.app_status_runtime_snapshot()

        self.assertIn("cost-tax", snapshot["worker_statuses"])
        self.assertIn("cost-tax-read-model", snapshot["worker_statuses"])

    def test_health_summary_counts_worker_mismatches(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertGreaterEqual(summary["missing_required_worker_count"], 1)
        self.assertEqual(summary["stale_required_worker_count"], 0)
        self.assertEqual(summary["mismatched_required_worker_count"], 1)


if __name__ == "__main__":
    unittest.main()
