import unittest
from types import SimpleNamespace

from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerDerivedLifecycle


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class RuntimeWorkerReadModelRefreshScopeTests(unittest.TestCase):
    def _lifecycle(self, queue: QueueRecorder) -> _RuntimeWorkerDerivedLifecycle:
        return _RuntimeWorkerDerivedLifecycle(
            queue_repository=queue,
            state_store=SimpleNamespace(),
            search_service=SimpleNamespace(clear_cache=lambda: None),
            workbench_source_versions_provider=lambda: {},
        )

    def test_worker_lifecycle_normalizes_cost_statistics_refresh_scopes(self) -> None:
        queue = QueueRecorder()
        lifecycle = self._lifecycle(queue)

        lifecycle.execute_event(
            "etc_business_batch_changed",
            months=["2026-03", "2026-04"],
            metadata={"reason": "unit_test"},
        )

        cost_refreshes = [refresh for refresh in queue.refreshes if refresh[0] == "cost_statistics"]
        self.assertEqual(
            cost_refreshes,
            [
                ("cost_statistics", "active:2026-03", "unit_test"),
                ("cost_statistics", "all:2026-03", "unit_test"),
                ("cost_statistics", "active:2026-04", "unit_test"),
                ("cost_statistics", "all:2026-04", "unit_test"),
                ("cost_statistics", "active:all", "unit_test"),
                ("cost_statistics", "all:all", "unit_test"),
            ],
        )
        self.assertNotIn(("cost_statistics", "2026-03", "unit_test"), cost_refreshes)
        self.assertNotIn(("cost_statistics", "2026-04", "unit_test"), cost_refreshes)
        self.assertNotIn(("cost_statistics", "all", "unit_test"), cost_refreshes)

    def test_worker_lifecycle_does_not_apply_cost_scope_rules_to_other_read_models(self) -> None:
        queue = QueueRecorder()
        lifecycle = self._lifecycle(queue)

        lifecycle.execute_event(
            "etc_business_batch_changed",
            months=["2026-03"],
            metadata={"reason": "unit_test"},
        )

        tax_refreshes = [refresh for refresh in queue.refreshes if refresh[0] == "tax_offset"]
        self.assertEqual(
            tax_refreshes,
            [
                ("tax_offset", "2026-03", "unit_test"),
                ("tax_offset", "all", "unit_test"),
            ],
        )


if __name__ == "__main__":
    unittest.main()
