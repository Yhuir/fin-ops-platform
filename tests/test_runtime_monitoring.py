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
                    "event_id": "event-current-workbench-1",
                    "event_type": "workbench.read_model.refresh",
                    "scope_type": "workbench",
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
                    "event_id": "event-search-1",
                    "event_type": "search.read_model.refresh",
                    "scope_type": "search",
                    "scope_key": "2026-03",
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
                    "event_id": "event-workbench-1",
                    "event_type": "workbench.read_model.refresh",
                    "scope_type": "workbench",
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
                    "event_type": "workbench.read_model.refresh",
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
                    "event_type": "tax_offset.read_model.refresh",
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
                    "event_type": "workbench.read_model.refresh",
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
                    "event_type": "workbench.read_model.refresh",
                    "status": "pending",
                    "scope_type": "workbench",
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
                    "scope_type": "workbench",
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
        if "from job.read_model_dirty_scopes" in normalized and "group by status" in normalized:
            return [{"status": "pending", "count": 2}, {"status": "processing", "count": 1}]
        if "from job.read_model_dirty_scopes" in normalized and "updated_at <" in normalized:
            return [
                {
                    "tenant_id": "default",
                    "scope_type": "workbench",
                    "scope_key": "workbench:month:2026-05",
                    "status": "pending",
                    "age_seconds": 600.0,
                    "attempts": 2,
                    "last_error": "boom",
                }
            ]
        return []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "like '%." in normalized:
            raise AssertionError("literal percent signs must be escaped for psycopg SQL")
        if "ready_outbox_snapshot" in normalized:
            return {
                "queue_backlog": {"pending": 3, "failed": 1},
                "max_pending_age_seconds": 42.0,
                "publish_status": {"unpublished": 4, "failed": 2},
                "max_unpublished_age_seconds": 11.0,
                "pending_outbox_events_by_scope": [
                    {
                        "event_type": "workbench.read_model.refresh",
                        "status": "pending",
                        "scope_type": "workbench",
                        "scope_key": "all",
                        "count": 2,
                        "oldest_age_seconds": 610.0,
                        "attempts": 1,
                        "last_error": "",
                    }
                ],
            }
        if "ready_dirty_scope_snapshot" in normalized:
            return {
                "dirty_scopes": {"pending": 2, "processing": 1},
                "stale_dirty_scopes": [
                    {
                        "tenant_id": "default",
                        "scope_type": "workbench",
                        "scope_key": "workbench:month:2026-05",
                        "status": "pending",
                        "age_seconds": 600.0,
                        "attempts": 2,
                        "last_error": "boom",
                        "total_count": 1,
                    }
                ],
                "dirty_scopes_by_scope": [
                    {
                        "scope_type": "workbench",
                        "scope_key": "all",
                        "status": "pending",
                        "count": 1,
                        "oldest_age_seconds": 620.0,
                        "attempts": 2,
                        "last_error": "still refreshing",
                    }
                ],
            }
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
                "worker_id": "host-workbench",
                "worker_instance": "workbench",
                "worker_kind": "unexpected-kind",
                "status": "idle",
                "heartbeat_lag_seconds": 1.0,
                "payload": {
                    "worker_instance": "workbench",
                    "configured_event_types": ["workbench.read_model.refresh"],
                },
            },
            {
                "worker_id": "host-bank-detail",
                "worker_instance": "bank-detail",
                "worker_kind": "bank-detail-read-model",
                "status": "idle",
                "heartbeat_lag_seconds": 999.0,
                "payload": {
                    "worker_instance": "bank-detail",
                    "configured_event_types": ["bank_detail.read_model.refresh"],
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
                    "configured_event_types": ["bank_account_balance.read_model.refresh"],
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
                    "configured_event_types": ["import.process.requested"],
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
                    "configured_event_types": ["tax_offset.read_model.refresh"],
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
                    "configured_event_types": ["cost_statistics.read_model.refresh"],
                },
            },
        ]

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        return {}


class RuntimeMonitoringRepositoryTests(unittest.TestCase):
    def test_health_summary_reports_backlog_failed_jobs_and_stale_dirty_scopes(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection, rabbitmq_metrics_provider=FakeRabbitMqMetrics())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertEqual(summary["dirty_scopes"], {"pending": 2, "processing": 1})
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["max_pending_age_seconds"], 42.0)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertEqual(summary["missing_required_worker_count"], len(required_worker_instance_names()))
        self.assertEqual(summary["stale_required_worker_count"], 0)
        self.assertEqual(summary["mismatched_required_worker_count"], 0)
        self.assertEqual(summary["worker_metrics"][0]["status"], "missing")
        self.assertEqual(summary["read_model_refresh_duration_ms"], {"p50": 120.0, "p95": 300.0, "p99": 450.0})
        self.assertEqual(summary["read_model_refresh_enqueue_to_fresh_ms"], {"p50": 180.0, "p95": 350.0, "p99": 500.0})
        self.assertEqual(summary["read_model_refresh_sample_count"], 10)
        self.assertEqual(summary["read_model_refresh_failure_rate"], 0.1)
        self.assertEqual(summary["read_model_refresh_by_key"][0]["key"], "workbench")
        self.assertEqual(summary["read_model_refresh_by_key"][0]["event_type"], "workbench.read_model.refresh")
        self.assertEqual(summary["read_model_refresh_by_key"][0]["duration_ms"]["p95"], 500.0)
        self.assertEqual(summary["read_model_refresh_by_key"][0]["enqueue_to_fresh_ms"]["p95"], 550.0)
        self.assertEqual(summary["read_model_refresh_by_key"][0]["sample_count"], 5)
        self.assertEqual(summary["read_model_refresh_by_key"][0]["failure_rate"], 0.2)
        self.assertEqual(summary["read_model_refresh_by_key"][0]["last_fresh_at"], "2026-06-13 03:00:01+08")
        self.assertEqual(summary["read_model_refresh_by_key"][1]["key"], "tax_offset")
        self.assertEqual(summary["read_model_refresh_slow_events"][0]["event_id"], "event-search-1")
        self.assertEqual(summary["read_model_refresh_slow_events"][0]["key"], "search")
        self.assertEqual(summary["read_model_refresh_slow_events"][0]["scope_key"], "2026-03")
        self.assertEqual(summary["read_model_refresh_slow_events"][0]["enqueue_to_fresh_ms"], 35150.0)
        self.assertFalse(summary["read_model_refresh_slow_events"][0]["skipped"])
        self.assertEqual(summary["read_model_refresh_current_slow_events"][0]["event_id"], "event-current-workbench-1")
        self.assertEqual(summary["read_model_refresh_current_slow_events"][0]["key"], "workbench")
        self.assertEqual(summary["read_model_refresh_current_slow_events"][0]["scope_key"], "all")
        self.assertEqual(summary["read_model_refresh_current_slow_events"][0]["duration_ms"], 28000.0)
        self.assertEqual(summary["read_model_refresh_current_windows"]["recent_15m"]["sample_count"], 3)
        self.assertEqual(
            summary["read_model_refresh_current_windows"]["recent_15m"]["enqueue_to_fresh_ms"]["p95"],
            160.0,
        )
        self.assertEqual(summary["read_model_refresh_current_windows"]["recent_1h"]["sample_count"], 0)
        self.assertEqual(summary["read_model_refresh_by_key_current_windows"][0]["window"], "recent_15m")
        self.assertEqual(summary["read_model_refresh_by_key_current_windows"][0]["key"], "workbench")
        self.assertEqual(
            summary["read_model_refresh_by_key_current_windows"][0]["enqueue_to_fresh_ms"]["p95"],
            170.0,
        )
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
        self.assertEqual(summary["stale_dirty_scope_count"], 1)
        self.assertEqual(summary["stale_dirty_scopes"][0]["scope_key"], "workbench:month:2026-05")
        self.assertEqual(
            summary["pending_outbox_events_by_scope"],
            [
                {
                    "event_type": "workbench.read_model.refresh",
                    "status": "pending",
                    "scope_type": "workbench",
                    "scope_key": "all",
                    "count": 2,
                    "oldest_age_seconds": 610.0,
                    "attempts": 1,
                    "last_error": "",
                }
            ],
        )
        self.assertEqual(
            summary["dirty_scopes_by_scope"],
            [
                {
                    "scope_type": "workbench",
                    "scope_key": "all",
                    "status": "pending",
                    "count": 1,
                    "oldest_age_seconds": 620.0,
                    "attempts": 2,
                    "last_error": "still refreshing",
                }
            ],
        )
        self.assertEqual(
            summary["workbench_read_model"],
            {
                "generation_status_counts": {"active": 3, "building": 1},
                "active_scope_count": 3,
                "active_row_count": 150,
                "active_group_count": 45,
                "active_summary_count": 3,
                "building_scope_count": 1,
                "failed_scope_count": 0,
                "latest_generated_at": "2026-05-29 21:00:00+08",
                "all_scope": {
                    "status": "building",
                    "row_count": 0,
                    "group_count": 0,
                    "summary_count": 0,
                    "updated_at": "2026-05-29 21:02:00+08",
                    "last_error": "",
                },
            },
        )
        normalized_calls = [" ".join(sql.lower().split()) for sql, _ in connection.calls]
        refresh_metric_sql = next(sql for sql in normalized_calls if "recent_refresh_events" in sql)
        self.assertIn("cross join lateral", refresh_metric_sql)
        self.assertIn("order by updated_at desc", refresh_metric_sql)
        self.assertIn("limit %s", refresh_metric_sql)
        self.assertIn("processed_at - refresh_event.created_at", refresh_metric_sql)
        self.assertIn("metric_windows(window_name, started_at)", refresh_metric_sql)
        self.assertIn("recent_15m", refresh_metric_sql)
        self.assertNotIn("from job.outbox_events where event_type like", refresh_metric_sql)
        slow_event_sql = next(sql for sql in normalized_calls if "slow_refresh_event_samples" in sql)
        self.assertIn("cross join lateral", slow_event_sql)
        self.assertIn("limit %s", slow_event_sql)
        self.assertIn("order by greatest(coalesce(enqueue_to_fresh_ms, 0)", slow_event_sql)
        current_slow_event_sql = next(sql for sql in normalized_calls if "current_refresh_event_samples" in sql)
        self.assertIn("created_at >= now() - interval '6 hours'", current_slow_event_sql)
        self.assertIn("duration_ms desc nulls last", current_slow_event_sql)
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
        self.assertIn("readiness.status = 'fresh'", queue_status_sql)
        self.assertIn("readiness.updated_at > e.updated_at", queue_status_sql)
        publish_status_sql = next(
            sql
            for sql in normalized_calls
            if "select e.publish_status, count(*)::bigint as count from job.outbox_events e" in sql
        )
        self.assertIn("readiness.updated_at > e.updated_at", publish_status_sql)
        self.assertIn("done.status = 'done'", publish_status_sql)
        self.assertIn("readiness.status = 'fresh'", publish_status_sql)

    def test_ready_health_summary_uses_lightweight_runtime_contract(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection, rabbitmq_metrics_provider=FakeRabbitMqMetrics())

        summary = repository.ready_health_summary(stale_after_seconds=300)
        executed_sql = "\n".join(sql for sql, _params in connection.calls).lower()

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertEqual(summary["dirty_scopes"], {"pending": 2, "processing": 1})
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertNotIn("read_model_refresh_sample_count", summary)
        self.assertNotIn("read_model_refresh_failure_rate", summary)
        self.assertEqual(summary["rabbitmq_publish_status"], {"unpublished": 4, "failed": 2})
        self.assertEqual(summary["rabbitmq_queue_depth"], 5)
        self.assertEqual(summary["stale_dirty_scope_count"], 1)
        self.assertEqual(summary["pending_outbox_events_by_scope"][0]["event_type"], "workbench.read_model.refresh")
        self.assertEqual(summary["dirty_scopes_by_scope"][0]["scope_key"], "all")
        self.assertNotIn("read_model_refresh_duration_ms", summary)
        self.assertNotIn("read_model_refresh_by_key", summary)
        self.assertNotIn("read_model_refresh_slow_events", summary)
        self.assertNotIn("workbench_read_model", summary)
        self.assertIn("event_type = 'cost_statistics.read_model.refresh'", executed_sql)
        self.assertIn("dirty.scope_key = 'all' or dirty.scope_key ~ '^[0-9]{4}-[0-9]{2}$'", executed_sql)
        self.assertIn("payload->>'scope_key'", executed_sql)
        self.assertNotIn("{_current_effective_dirty_scope_predicate_sql", executed_sql)
        self.assertNotIn("slow_refresh_event_samples", executed_sql)
        self.assertNotIn("current_refresh_event_samples", executed_sql)
        self.assertNotIn("recent_refresh_events", executed_sql)
        self.assertNotIn("workbench_generation_status_counts", executed_sql)
        self.assertNotIn("recent_publish_confirms", executed_sql)
        self.assertEqual(executed_sql.count("ready_outbox_snapshot"), 1)
        self.assertEqual(executed_sql.count("ready_dirty_scope_snapshot"), 1)
        self.assertIn("current_events as materialized", executed_sql)
        self.assertIn("current_dirty_scopes as materialized", executed_sql)
        self.assertIn(
            "dirty_counts as ( select status, count(*)::bigint as count from current_dirty_scopes",
            " ".join(executed_sql.split()),
        )

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
        self.assertIn("where e.status in ('pending', 'failed', 'dead_lettered')", connection.sql)
        self.assertIn("where e.publish_status = 'publishing'", connection.sql)
        self.assertNotIn("where e.publish_status = 'failed'", connection.sql)
        self.assertIn("e.event_type = 'cost_statistics.read_model.refresh'", connection.sql)
        self.assertIn("count(*) filter (where publish_status = 'failed')", connection.sql)
        self.assertIn("done.status = 'done'", connection.sql)
        self.assertIn("readiness.status = 'fresh'", connection.sql)
        self.assertIn("readiness.updated_at > e.updated_at", connection.sql)

    def test_dashboard_worker_metrics_are_registry_instance_aware(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        metrics = repository.dashboard_worker_metrics()
        by_instance = {row["worker_instance"]: row for row in metrics}

        self.assertEqual(by_instance["workbench"]["warning_code"], "worker_kind_mismatch")
        self.assertEqual(by_instance["workbench"]["expected_worker_kind"], "workbench-read-model")
        self.assertEqual(by_instance["workbench"]["worker_kind"], "unexpected-kind")
        self.assertEqual(by_instance["bank-detail"]["warning_code"], "worker_heartbeat_stale")
        self.assertEqual(by_instance["bank-detail"]["status"], "stale")
        self.assertTrue(by_instance["bank-account-balance"]["required"])
        self.assertEqual(by_instance["bank-account-balance"]["status"], "available")
        self.assertFalse(by_instance["cost-tax-read-model"]["required"])
        self.assertFalse(by_instance["cost-tax-read-model"]["current_effective"])
        self.assertEqual(by_instance["cost-tax-read-model"]["warning_code"], "worker_event_type_mismatch")
        self.assertNotIn("warning_code", by_instance["import"])
        self.assertEqual(by_instance["oa-sync"]["warning_code"], "required_worker_missing")

    def test_app_status_worker_snapshot_ignores_historical_optional_worker_heartbeats(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        snapshot = repository.app_status_runtime_snapshot()

        self.assertIn("cost-tax", snapshot["worker_statuses"])
        self.assertNotIn("cost-tax-read-model", snapshot["worker_statuses"])

    def test_app_status_readiness_summary_does_not_load_unconsumed_source_versions(self) -> None:
        class ReadinessSummaryConnection:
            def __init__(self) -> None:
                self.sql = ""

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
                self.sql = " ".join(sql.lower().split())
                return [
                    {
                        "read_model_key": "turnover_ledger",
                        "scope_type": "turnover_ledger",
                        "scope_key": "2026-02",
                        "status": "fresh",
                        "schema_version": "7",
                        "row_count": 2,
                        "generated_at": "2026-07-20T01:00:00+00:00",
                        "updated_at": "2026-07-20T01:00:01+00:00",
                        "last_error": None,
                    }
                ]

        connection = ReadinessSummaryConnection()
        repository = RuntimeMonitoringRepository(connection)

        statuses = repository._app_status_readiness_statuses()

        self.assertEqual(statuses["turnover_ledger"]["status"], "fresh")
        self.assertEqual(statuses["turnover_ledger"]["generated_at"], "2026-07-20T01:00:00+00:00")
        self.assertNotIn("source_versions", connection.sql)
        self.assertNotIn("source_versions", statuses["turnover_ledger"])

    def test_operation_barrier_runtime_snapshot_queries_only_requested_scopes(self) -> None:
        class TargetScopedConnection:
            def __init__(self) -> None:
                self.calls: list[tuple[str, tuple[object, ...]]] = []

            def fetch_all(self, sql: str, params: tuple[object, ...] = ()) -> list[dict[str, object]]:
                self.calls.append((sql, params))
                normalized = " ".join(sql.lower().split())
                if "from read_model.app_status_readiness" in normalized and "select read_model_key" in normalized:
                    return [
                        {
                            "read_model_key": "turnover_ledger",
                            "scope_type": "turnover_ledger",
                            "scope_key": "2026-02",
                            "status": "fresh",
                            "schema_version": "7",
                            "row_count": 2,
                            "generated_at": "2026-07-20T01:00:00+00:00",
                            "updated_at": "2026-07-20T01:00:01+00:00",
                            "last_error": None,
                        }
                    ]
                if "from job.read_model_dirty_scopes dirty" in normalized:
                    return []
                if "from job.outbox_events event" in normalized and "cross join lateral" in normalized:
                    return []
                if "from job.runtime_worker_heartbeats" in normalized:
                    return [
                        {
                            "worker_id": "worker-turnover",
                            "worker_instance": "turnover-ledger",
                            "worker_kind": "turnover-ledger-read-model",
                            "status": "running",
                            "heartbeat_lag_seconds": 1.0,
                            "payload": {"worker_instance": "turnover-ledger"},
                        }
                    ]
                raise AssertionError(normalized)

        connection = TargetScopedConnection()
        repository = RuntimeMonitoringRepository(connection)

        snapshot = repository.operation_barrier_runtime_snapshot(
            [
                {
                    "read_model_key": "turnover_ledger",
                    "scope_type": "turnover_ledger",
                    "scope_key": "2026-02",
                },
                {
                    "read_model_key": "turnover_ledger",
                    "scope_type": "turnover_ledger",
                    "scope_key": "2026-02",
                },
            ]
        )

        self.assertEqual(snapshot["read_model_statuses"]["turnover_ledger"]["status"], "fresh")
        self.assertEqual(snapshot["worker_statuses"]["turnover-ledger"]["status"], "ready")
        self.assertEqual(set(snapshot["read_model_statuses"]), {"turnover_ledger"})
        generic_scoped_calls = [
            call
            for call in connection.calls
            if "as barrier_target(target_key, target_scope_type, target_scope_key)" in " ".join(call[0].split())
        ]
        self.assertEqual(len(generic_scoped_calls), 2)
        for sql, params in generic_scoped_calls:
            self.assertIn(
                "as barrier_target(target_key, target_scope_type, target_scope_key)",
                " ".join(sql.split()),
            )
            self.assertEqual(params[1], ["turnover_ledger"])
            self.assertEqual(params[2], ["2026-02"])
        outbox_call = next(call for call in connection.calls if "cross join lateral" in call[0])
        self.assertIn("candidate_scope", outbox_call[0])
        self.assertIn("limit 1", outbox_call[0])
        self.assertIn("event.created_at desc, event.id desc", outbox_call[0])
        self.assertNotIn("_current_effective_outbox_attention", outbox_call[0])
        self.assertEqual(outbox_call[1][0], ["turnover_ledger.read_model.refresh"])
        self.assertEqual(outbox_call[1][1], ["turnover_ledger"])
        self.assertEqual(outbox_call[1][2], ["2026-02"])
        worker_call = next(call for call in connection.calls if "from job.runtime_worker_heartbeats" in call[0])
        self.assertEqual(worker_call[1][0], ["turnover-ledger"])
        self.assertEqual(worker_call[1][1], ["turnover-ledger-read-model"])

    def test_health_summary_counts_worker_mismatches(self) -> None:
        repository = RuntimeMonitoringRepository(FakeWorkerMetricsConnection())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertGreaterEqual(summary["missing_required_worker_count"], 1)
        self.assertEqual(summary["stale_required_worker_count"], 1)
        self.assertEqual(summary["mismatched_required_worker_count"], 1)


if __name__ == "__main__":
    unittest.main()
