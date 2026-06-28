import unittest
from types import SimpleNamespace

from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerDerivedLifecycle


class NoPageRefreshQueue:
    pass


class RuntimeWorkerReadModelRefreshScopeTests(unittest.TestCase):
    def _lifecycle(
        self,
        queue: NoPageRefreshQueue,
    ) -> _RuntimeWorkerDerivedLifecycle:
        return _RuntimeWorkerDerivedLifecycle(
            queue_repository=queue,
            state_store=SimpleNamespace(),
            search_service=SimpleNamespace(clear_cache=lambda: None),
            workbench_source_versions_provider=lambda: {},
        )

    def test_worker_lifecycle_no_longer_enqueues_cost_statistics_read_model_refresh(self) -> None:
        queue = NoPageRefreshQueue()
        lifecycle = self._lifecycle(queue)

        lifecycle.execute_event(
            "etc_business_batch_changed",
            months=["2026-03", "2026-04"],
            metadata={"reason": "unit_test"},
        )

    def test_import_state_no_longer_enqueues_page_read_model_refresh(self) -> None:
        queue = NoPageRefreshQueue()
        lifecycle = self._lifecycle(queue)
        snapshot_service = SimpleNamespace(snapshot=lambda: {})

        lifecycle.persist_import_state(
            import_service=snapshot_service,
            file_import_service=snapshot_service,
            etc_service=snapshot_service,
            etc_reconciliation_task_service=snapshot_service,
            tax_certified_import_service=snapshot_service,
            cost_statistics_scope_keys=["2026-03"],
        )

    def test_import_state_no_longer_enqueues_bank_detail_or_account_balance_read_model_refresh(self) -> None:
        queue = NoPageRefreshQueue()
        lifecycle = self._lifecycle(queue)
        snapshot_service = SimpleNamespace(snapshot=lambda: {})

        lifecycle.persist_import_state(
            import_service=snapshot_service,
            file_import_service=snapshot_service,
            etc_service=snapshot_service,
            etc_reconciliation_task_service=snapshot_service,
            tax_certified_import_service=snapshot_service,
        )

    def test_lifecycle_bank_import_no_longer_enqueues_bank_account_balance_read_model_refresh(self) -> None:
        queue = NoPageRefreshQueue()
        lifecycle = self._lifecycle(queue)

        result = lifecycle.execute_event(
            "bank_import_confirmed",
            months=["2026-03"],
            metadata={"reason": "unit_test"},
        )

        self.assertNotIn("bank_account_balance.read_model.refresh", result["enqueued_jobs"])
        self.assertIn("all", result["invalidated_scopes"])

    def test_worker_lifecycle_no_longer_enqueues_tax_offset_read_model_refresh(self) -> None:
        queue = NoPageRefreshQueue()
        lifecycle = self._lifecycle(queue)

        lifecycle.execute_event(
            "etc_business_batch_changed",
            months=["2026-03"],
            metadata={"reason": "unit_test"},
        )


if __name__ == "__main__":
    unittest.main()
