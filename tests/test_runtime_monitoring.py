from __future__ import annotations

import unittest

from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


class FakeConnection:
    def __init__(self) -> None:
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
        self.calls.append((sql, params))
        normalized = " ".join(sql.lower().split())
        if "from job.outbox_events" in normalized:
            return [{"status": "pending", "count": 3}, {"status": "failed", "count": 1}]
        if "from job.read_model_dirty_scopes" in normalized:
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
        return {"max_pending_age_seconds": 42.0}


class RuntimeMonitoringRepositoryTests(unittest.TestCase):
    def test_health_summary_reports_backlog_failed_jobs_and_stale_dirty_scopes(self) -> None:
        repository = RuntimeMonitoringRepository(FakeConnection())

        summary = repository.health_summary(stale_after_seconds=300)

        self.assertEqual(summary["queue_backlog"], {"pending": 3, "failed": 1})
        self.assertEqual(summary["failed_jobs"], 1)
        self.assertEqual(summary["max_pending_age_seconds"], 42.0)
        self.assertEqual(summary["stale_dirty_scope_count"], 1)
        self.assertEqual(summary["stale_dirty_scopes"][0]["scope_key"], "workbench:month:2026-05")


if __name__ == "__main__":
    unittest.main()
