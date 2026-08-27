from __future__ import annotations

import unittest
from unittest.mock import patch

from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository, readiness_blockers


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "ready_outbox_snapshot" in normalized:
            return {
                "queue_backlog": {"pending": 3, "failed": 1},
                "max_pending_age_seconds": 42.0,
                "critical_failed_outbox_count": 1,
                "pending_outbox_events_by_scope": [
                    {
                        "event_type": "oa.sync",
                        "status": "pending",
                        "scope_type": "oa",
                        "scope_key": "all",
                        "count": 2,
                        "oldest_age_seconds": 10.0,
                        "attempts": 1,
                        "last_error": "",
                    }
                ],
            }
        if "from job.runtime_worker_heartbeats" in normalized:
            return {"max_worker_heartbeat_lag_seconds": 8.0}
        if "from job.outbox_events" in normalized and "pending_count" in normalized:
            return {
                "pending_count": 1,
                "processing_count": 0,
                "failed_count": 0,
                "oldest_pending_age_seconds": 2.0,
            }
        raise AssertionError(sql)

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from job.runtime_worker_heartbeats" in normalized:
            return [
                _worker(
                    "host-oa",
                    "oa-sync",
                    "oa-sync",
                    ["oa.sync", "oa.payment_status.reconcile"],
                    lag=1.0,
                ),
                _worker("host-match", "workbench-matching", "workbench-matching", [], lag=2.0),
                _worker("host-import", "import", "import-job", ["import.process.requested"], lag=3.0),
                _worker(
                    "host-settings",
                    "settings-maintenance",
                    "settings-maintenance",
                    [
                        "settings.data_reset.requested",
                        "settings.bank_relation_requirements.recalculate.requested",
                    ],
                    lag=4.0,
                ),
                _worker("historical", "retired-worker", "retired-worker", ["retired.event"], lag=9999.0),
            ]
        if "from job.outbox_events" in normalized:
            return [
                {
                    "event_type": "oa.sync",
                    "scope_type": "oa",
                    "scope_key": "all",
                    "status": "failed",
                    "count": 1,
                    "last_error": "boom",
                    "updated_at": "2026-08-15T00:00:00+00:00",
                }
            ]
        raise AssertionError(sql)


def _worker(
    worker_id: str,
    instance: str,
    kind: str,
    event_types: list[str],
    *,
    lag: float,
) -> dict[str, object]:
    return {
        "worker_id": worker_id,
        "worker_instance": instance,
        "worker_kind": kind,
        "status": "idle",
        "heartbeat_lag_seconds": lag,
        "payload": {"worker_instance": instance, "configured_event_types": event_types},
    }


class RuntimeMonitoringRepositoryTests(unittest.TestCase):
    def test_ready_health_summary_uses_outbox_and_worker_contract_only(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection)

        summary = repository.ready_health_summary(stale_after_seconds=300)
        executed_sql = "\n".join(sql for sql, _params in connection.calls).lower()

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["oldest_pending_event_age_seconds"], 42.0)
        self.assertEqual(summary["worker_heartbeat_lag_seconds"], 8.0)
        self.assertNotIn("rabbitmq_publish_status", summary)
        self.assertNotIn("rabbitmq_queue_depth", summary)
        self.assertEqual(summary["critical_failed_outbox_count"], 1)
        self.assertEqual(summary["pending_outbox_events_by_scope"][0]["event_type"], "oa.sync")
        self.assertEqual(summary["missing_required_worker_count"], 0)
        self.assertNotIn("read_models", summary)
        self.assertNotIn("dirty_scopes", summary)
        self.assertEqual(executed_sql.count("ready_outbox_snapshot"), 1)
        self.assertIn("payload->>'operation'", executed_sql)
        self.assertIn("refresh_attachments", executed_sql)
        self.assertNotIn("read_model", executed_sql)

    def test_readiness_blockers_only_reject_current_platform_failures(self) -> None:
        healthy_runtime = {
            "missing_required_worker_count": 0,
            "stale_required_worker_count": 0,
            "mismatched_required_worker_count": 0,
            "critical_failed_outbox_count": 0,
            "queue_backlog": {"pending": 4},
        }
        common = {
            "storage_backend": "postgres",
            "postgres_status": "ready",
            "runtime_release": {"consistent": True},
            "production_runtime_guard": {"consistent": True},
        }

        self.assertEqual(readiness_blockers(**common, runtime_infrastructure=healthy_runtime), {})
        blocked = dict(healthy_runtime, missing_required_worker_count=2, critical_failed_outbox_count=1)
        self.assertEqual(
            readiness_blockers(**common, runtime_infrastructure=blocked),
            {"required_worker_missing": 2, "critical_outbox_failed": 1},
        )
        self.assertEqual(
            readiness_blockers(**dict(common, postgres_status="error"), runtime_infrastructure=healthy_runtime),
            {"postgres_unavailable": "error"},
        )

    def test_ready_health_summary_scopes_required_workers_for_release_preflight(self) -> None:
        repository = RuntimeMonitoringRepository(FakeConnection())
        expected_instances = {"import", "oa-sync"}

        with patch.object(repository, "dashboard_worker_metrics", return_value=[]) as worker_metrics:
            repository.ready_health_summary(required_worker_instances=expected_instances)

        worker_metrics.assert_called_once_with(worker_instances=expected_instances)

    def test_dashboard_outbox_metric_scans_only_current_attention_statuses(self) -> None:
        connection = FakeConnection()
        repository = RuntimeMonitoringRepository(connection)

        metric = repository.dashboard_outbox_metric()
        sql = " ".join(connection.calls[-1][0].lower().split())

        self.assertEqual(metric["pending_count"], 1)
        self.assertIn("from job.outbox_events", sql)
        self.assertIn("status in ('pending', 'processing', 'failed', 'dead_lettered')", sql)
        self.assertNotIn("publish_status", sql)
        self.assertNotIn("read_model", sql)

    def test_dashboard_workers_follow_the_four_registered_instances(self) -> None:
        repository = RuntimeMonitoringRepository(FakeConnection())

        metrics = repository.dashboard_worker_metrics()
        by_instance = {row["worker_instance"]: row for row in metrics}

        self.assertEqual(
            {name for name, row in by_instance.items() if row["required"]},
            {"oa-sync", "workbench-matching", "import", "settings-maintenance"},
        )
        self.assertEqual(by_instance["oa-sync"]["status"], "available")
        self.assertEqual(by_instance["retired-worker"]["status"], "available")
        self.assertFalse(by_instance["retired-worker"]["required"])

    def test_app_status_snapshot_ignores_historical_optional_worker(self) -> None:
        repository = RuntimeMonitoringRepository(FakeConnection())

        snapshot = repository.app_status_runtime_snapshot()

        self.assertEqual(snapshot["outbox_statuses"]["oa.sync"]["status"], "failed")
        self.assertEqual(
            set(snapshot["worker_statuses"]),
            {"oa-sync", "workbench-matching", "import", "settings-maintenance"},
        )
        self.assertNotIn("retired-worker", snapshot["worker_statuses"])

        app_status_sql = " ".join(
            sql.lower()
            for sql, _params in repository._connection.calls
            if "from job.outbox_events" in sql.lower()
        )
        self.assertIn("payload->>'operation'", app_status_sql)
        self.assertIn("refresh_attachments", app_status_sql)


if __name__ == "__main__":
    unittest.main()
