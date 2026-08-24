from __future__ import annotations

from dataclasses import dataclass
import unittest

from fin_ops_platform.services.app_status_domain_registry import APP_STATUS_DOMAIN_REGISTRY
from fin_ops_platform.services.app_status_overview_service import AppStatusOverviewService
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


@dataclass(slots=True)
class FakeSession:
    allowed: bool = True
    can_access_app: bool = True
    can_mutate_data: bool = True


def healthy_dependencies() -> dict[str, dict[str, object]]:
    return {
        "oa_identity": {"status": "available"},
        "oa_sync": {"status": "available"},
        "background_jobs": {"status": "available"},
        "state_store": {"status": "available"},
        "postgres": {"status": "ready"},
        "redis": {"status": "ready"},
        "object_storage": {"status": "available"},
        "oa_mongo": {"status": "available"},
    }


class AppStatusOverviewServiceTests(unittest.TestCase):
    def test_stale_matching_scope_overrides_ready_worker_without_blocking_writes(self) -> None:
        payload = AppStatusOverviewService().build_overview(
            session=FakeSession(),
            active_jobs=[],
            attention_jobs=[],
            worker_statuses={"workbench-matching": {"status": "ready", "required": True}},
            outbox_statuses={},
            app_health_snapshot={
                "generated_at": "2026-08-24T10:00:00+08:00",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
                "workbench_matching": {
                    "status": "stale",
                    "last_matching_error": "Invalid canonical fact date",
                },
            },
        )

        workbench = next(domain for domain in payload["domains"] if domain["key"] == "workbench")
        self.assertEqual(workbench["level"], "busy")
        self.assertEqual(workbench["status"], "stale")
        self.assertIn("Invalid canonical fact date", workbench["details"])
        self.assertEqual(payload["overall"]["level"], "busy")
        self.assertFalse(payload["overall"]["blocks_mutations"])

    def test_overview_contains_only_worker_and_queue_runtime_summary(self) -> None:
        service = AppStatusOverviewService(domains=APP_STATUS_DOMAIN_REGISTRY)
        payload = service.build_overview(
            session=FakeSession(),
            active_jobs=[],
            attention_jobs=[],
            worker_statuses={
                "oa-sync": {"status": "ready", "required": True},
                "workbench-matching": {"status": "working", "required": True},
            },
            outbox_statuses={"oa.sync": {"status": "pending", "count": 2}},
            app_health_snapshot={
                "generated_at": "2026-08-15T10:00:00+08:00",
                "status": "ok",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertNotIn("read_models", payload)
        self.assertNotIn("read_models", payload["runtime_summary"])
        self.assertEqual(payload["runtime_summary"]["workers"]["working"], 1)
        self.assertEqual(payload["runtime_summary"]["queue"]["pending"], 2)

    def test_runtime_unavailable_blocks_overall_status(self) -> None:
        payload = AppStatusOverviewService().build_overview(
            session=FakeSession(),
            active_jobs=[],
            attention_jobs=[],
            worker_statuses={"__runtime__": {"status": "unavailable", "last_error": "postgres unavailable"}},
            outbox_statuses={},
            app_health_snapshot={
                "generated_at": "2026-08-15T10:00:00+08:00",
                "dependencies": healthy_dependencies(),
                "alerts": {"active": []},
            },
        )

        self.assertEqual(payload["overall"]["level"], "blocked")
        self.assertIn("postgres unavailable", payload["overall"]["reason"])

    def test_runtime_repository_reports_unavailable_snapshot_in_both_boundaries(self) -> None:
        class BrokenConnection:
            def fetch_all(self, sql: str, params: tuple[object, ...] = ()):
                raise RuntimeError("postgres unavailable")

        snapshot = RuntimeMonitoringRepository(BrokenConnection()).app_status_runtime_snapshot()

        self.assertEqual(snapshot["worker_statuses"]["__runtime__"]["status"], "unavailable")
        self.assertEqual(snapshot["outbox_statuses"]["__runtime__"]["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
