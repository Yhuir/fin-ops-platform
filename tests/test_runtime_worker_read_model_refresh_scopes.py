import unittest
from types import SimpleNamespace

from fin_ops_platform.services.runtime_worker_handlers import _RuntimeWorkerDerivedLifecycle


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class RuntimeWorkerReadModelRefreshScopeTests(unittest.TestCase):
    def _lifecycle(
        self,
        queue: QueueRecorder,
        *,
        search_read_model_refresh_producer: object | None = None,
        bank_account_balance_read_model_refresh_producer: object | None = None,
    ) -> _RuntimeWorkerDerivedLifecycle:
        return _RuntimeWorkerDerivedLifecycle(
            queue_repository=queue,
            state_store=SimpleNamespace(),
            search_service=SimpleNamespace(clear_cache=lambda: None),
            workbench_source_versions_provider=lambda: {},
            search_read_model_refresh_producer=search_read_model_refresh_producer,
            bank_account_balance_read_model_refresh_producer=bank_account_balance_read_model_refresh_producer,
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

    def test_import_state_search_refresh_uses_search_producer_boundary(self) -> None:
        queue = QueueRecorder()
        search_producer = FakeSearchRefreshProducer()
        lifecycle = self._lifecycle(queue, search_read_model_refresh_producer=search_producer)
        snapshot_service = SimpleNamespace(snapshot=lambda: {})

        lifecycle.persist_import_state(
            import_service=snapshot_service,
            file_import_service=snapshot_service,
            etc_service=snapshot_service,
            etc_reconciliation_task_service=snapshot_service,
            tax_certified_import_service=snapshot_service,
            cost_statistics_scope_keys=["2026-03"],
        )

        self.assertEqual(search_producer.calls, [(["2026-03"], "import_state_changed")])
        self.assertNotIn(("search", "2026-03", "import_state_changed"), queue.refreshes)
        self.assertIn(("workbench_relation", "2026-03", "import_state_changed"), queue.refreshes)
        self.assertIn(("input_invoice_usage", "2026-03", "import_state_changed"), queue.refreshes)
        self.assertIn(("output_invoice_collection", "2026-03", "import_state_changed"), queue.refreshes)
        self.assertIn(("oa_pending_payment", "2026-03", "import_state_changed"), queue.refreshes)

    def test_import_state_bank_account_balance_refresh_uses_producer_boundary(self) -> None:
        queue = QueueRecorder()
        bank_account_balance_producer = FakeBankAccountBalanceRefreshProducer()
        lifecycle = self._lifecycle(
            queue,
            bank_account_balance_read_model_refresh_producer=bank_account_balance_producer,
        )
        snapshot_service = SimpleNamespace(snapshot=lambda: {})

        lifecycle.persist_import_state(
            import_service=snapshot_service,
            file_import_service=snapshot_service,
            etc_service=snapshot_service,
            etc_reconciliation_task_service=snapshot_service,
            tax_certified_import_service=snapshot_service,
            bank_detail_scope_keys=["2026-03"],
        )

        self.assertEqual(bank_account_balance_producer.calls, [(["all"], "import_state_changed")])
        self.assertNotIn(("bank_account_balance", "all", "import_state_changed"), queue.refreshes)
        self.assertIn(("bank_detail", "2026-03", "import_facts_changed"), queue.refreshes)

    def test_lifecycle_bank_account_balance_refresh_uses_all_only_producer_boundary(self) -> None:
        queue = QueueRecorder()
        bank_account_balance_producer = FakeBankAccountBalanceRefreshProducer()
        lifecycle = self._lifecycle(
            queue,
            bank_account_balance_read_model_refresh_producer=bank_account_balance_producer,
        )

        result = lifecycle.execute_event(
            "bank_import_confirmed",
            months=["2026-03"],
            metadata={"reason": "unit_test"},
        )

        self.assertEqual(bank_account_balance_producer.calls, [(["2026-03", "all"], "unit_test")])
        self.assertNotIn(("bank_account_balance", "2026-03", "unit_test"), queue.refreshes)
        self.assertNotIn(("bank_account_balance", "all", "unit_test"), queue.refreshes)
        self.assertIn("bank_account_balance.read_model.refresh", result["enqueued_jobs"])
        self.assertIn("all", result["invalidated_scopes"])

    def test_lifecycle_bank_flow_rule_batch_refresh_has_runtime_executor(self) -> None:
        queue = QueueRecorder()
        lifecycle = self._lifecycle(queue)

        result = lifecycle.execute_event(
            "bank_flow_rule_batch_changed",
            months=["2026-03"],
            metadata={"reason": "unit_test"},
        )

        self.assertIn(("bank_flow_rule_batch", "2026-03", "unit_test"), queue.refreshes)
        self.assertIn(("bank_flow_rule_batch", "all", "unit_test"), queue.refreshes)
        self.assertIn("bank_flow_rule_batch.read_model.refresh", result["enqueued_jobs"])

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


class FakeSearchRefreshProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def enqueue(self, scope_keys: list[str], *, reason: str, **_kwargs: object) -> bool:
        self.calls.append((list(scope_keys), reason))
        return True


class FakeBankAccountBalanceRefreshProducer:
    def __init__(self) -> None:
        self.calls: list[tuple[list[str], str]] = []

    def enqueue_all(self, *, reason: str, **_kwargs: object) -> bool:
        self.calls.append((["all"], reason))
        return True

    def enqueue_scope_keys(self, scope_keys: list[str], *, reason: str, **_kwargs: object) -> list[str]:
        self.calls.append((list(scope_keys), reason))
        return ["all"]


if __name__ == "__main__":
    unittest.main()
