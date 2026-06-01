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
        if "publish_status" in normalized:
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
        if "from job.runtime_worker_heartbeats" in normalized:
            return {"max_worker_heartbeat_lag_seconds": 8.0}
        if "rabbitmq_publish" in normalized:
            return {"p50_ms": 10.0, "p95_ms": 20.0, "p99_ms": 30.0}
        if "percentile_cont" in normalized:
            return {"p50_ms": 120.0, "p95_ms": 300.0, "p99_ms": 450.0}
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


class RuntimeMonitoringRepositoryTests(unittest.TestCase):
    def test_health_summary_reports_backlog_failed_jobs_and_stale_dirty_scopes(self) -> None:
        repository = RuntimeMonitoringRepository(FakeConnection(), rabbitmq_metrics_provider=FakeRabbitMqMetrics())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertEqual(summary["dirty_scopes"], {"pending": 2, "processing": 1})
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["max_pending_age_seconds"], 42.0)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertEqual(summary["missing_required_worker_count"], len(required_worker_instance_names()))
        self.assertEqual(summary["stale_required_worker_count"], 0)
        self.assertEqual(summary["worker_metrics"][0]["status"], "missing")
        self.assertEqual(summary["read_model_refresh_duration_ms"], {"p50": 120.0, "p95": 300.0, "p99": 450.0})
        self.assertEqual(summary["read_model_refresh_failure_rate"], 0.1)
        self.assertEqual(summary["rabbitmq_publish_status"], {"unpublished": 4, "failed": 2})
        self.assertEqual(summary["rabbitmq_unpublished_backlog"], 4)
        self.assertEqual(summary["rabbitmq_publish_failed_backlog"], 2)
        self.assertEqual(summary["rabbitmq_dispatcher_lag_seconds"], 11.0)
        self.assertEqual(summary["rabbitmq_dispatch_event_types"], list(DEFAULT_RABBITMQ_DISPATCH_EVENT_TYPES))
        self.assertEqual(summary["rabbitmq_publish_confirm_latency_ms"], {"p50": 10.0, "p95": 20.0, "p99": 30.0})
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


if __name__ == "__main__":
    unittest.main()
