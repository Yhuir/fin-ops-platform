from __future__ import annotations

import unittest
from dataclasses import dataclass

from fin_ops_platform.services.app_status_domain_registry import APP_STATUS_DOMAIN_REGISTRY
from fin_ops_platform.services.app_status_overview_service import AppStatusOverviewService
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


@dataclass(slots=True)
class FakeSession:
    allowed: bool = True
    can_access_app: bool = True


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
            outbox_statuses={"oa.sync": {"status": "pending", "count": 2, "counts": {"pending": 2}}},
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

class ImportStatusIsolationTests(unittest.TestCase):
    def overview(self, counts, tasks=None, domains=None):
        return AppStatusOverviewService().build_overview(
            session=FakeSession(), active_jobs=[], attention_jobs=tasks or [],
            worker_statuses={"import": {"status": "ready", "required": True}},
            outbox_statuses={"import:invoices": {"affected_domains": domains or ["imports_invoices"],
                                                "counts": counts, "count": sum(counts.values())}},
            app_health_snapshot={"dependencies": healthy_dependencies()},
        )

    def test_missing_queue_count_contract_is_not_reported_as_empty(self):
        with self.assertRaises(KeyError):
            AppStatusOverviewService().build_overview(
                session=FakeSession(), active_jobs=[], attention_jobs=[], worker_statuses={},
                outbox_statuses={"oa.sync": {"status": "failed", "count": 1}},
                app_health_snapshot={"dependencies": healthy_dependencies()},
            )

    def test_failed_invoice_is_not_syncing_and_does_not_pollute_bank(self):
        result = self.overview({"failed": 1})
        by_key = {d['key']:d for d in result['domains']}
        self.assertEqual(by_key['imports_invoices']['status'], 'failed')
        self.assertEqual(by_key['imports_bank_transactions']['status'], 'ready')
        self.assertEqual(result['runtime_summary']['queue']['backlog'], 0)
        self.assertEqual(result['runtime_summary']['queue']['failed'], 1)
        self.assertNotIn('同步', result['overall']['reason'])
        self.assertFalse(result['overall']['blocks_mutations'])

    def test_mixed_counts_remain_exact_and_visible(self):
        result = self.overview({'failed':1,'pending':2,'processing':3,'awaiting_confirmation':4,'needs_review':5})
        queue = result['runtime_summary']['queue']
        self.assertEqual([queue[k] for k in ['failed','pending','processing','backlog','awaiting_confirmation','needs_review']], [1,2,3,5,4,5])
        invoice = next(d for d in result['domains'] if d['key']=='imports_invoices')
        self.assertIn('处理中 3', invoice['details'])
        self.assertIn('失败待处理 1', invoice['details'])

    def test_waiting_confirmation_is_not_executing_and_unknown_does_not_fan_out(self):
        result = self.overview({'awaiting_confirmation':1})
        self.assertEqual(next(d for d in result['domains'] if d['key']=='imports_invoices')['status'], 'awaiting_confirmation')
        unknown = self.overview({'failed':1}, domains=['import_unknown'])
        self.assertEqual(unknown['overall']['level'], 'busy')
        self.assertIn('归属待诊断', unknown['overall']['reason'])
        self.assertTrue(all(d['status']=='ready' for d in unknown['domains']))

    def test_completed_task_does_not_make_domain_busy(self):
        result = self.overview({}, tasks=[{'job_id':'import:done','type':'file_import','status':'succeeded','affected_domains':['imports_invoices']}])
        self.assertEqual(result['overall']['level'], 'ok')
