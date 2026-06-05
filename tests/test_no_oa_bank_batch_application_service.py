from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.no_oa_bank_batch_application_service import NoOaBankBatchApplicationService


class NoOaBankBatchApplicationServiceTests(unittest.TestCase):
    def test_after_mutation_persists_changed_cases_and_expanded_workbench_scopes(self) -> None:
        lifecycle_events: list[dict[str, object]] = []
        cache_clears: list[str] = []

        class StateStore:
            def __init__(self) -> None:
                self.saved_mutations: list[dict[str, object]] = []

            def save_no_oa_bank_batch_mutation(self, **kwargs: object) -> None:
                self.saved_mutations.append(dict(kwargs))

        state_store = StateStore()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {"batches": {}}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_service=SimpleNamespace(
                snapshot=lambda: {"relations": "all"},
                snapshot_case_ids=lambda case_ids: {"relations": list(case_ids)},
            ),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {"workbench": "snapshot"}),
            state_store=state_store,
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
            expand_workbench_read_model_scope_keys_for_base_scopes=lambda scope_keys: [
                f"expanded:{scope_key}" for scope_key in scope_keys
            ],
            search_cache_clearer=lambda: cache_clears.append("search"),
        )

        changed = service.after_mutation(
            ["2026-05", "not-a-month", "2026-06"],
            changed_case_ids=["case-001", "case-002"],
            persist=True,
        )

        self.assertTrue(changed)
        self.assertEqual(
            lifecycle_events,
            [
                {
                    "event_type": "no_oa_bank_batch_changed",
                    "months": ["2026-05", "2026-06"],
                    "metadata": {"source": "no_oa_bank_batch"},
                    "schedule_cost_warmup": False,
                }
            ],
        )
        self.assertEqual(cache_clears, ["search"])
        self.assertEqual(len(state_store.saved_mutations), 1)
        saved = state_store.saved_mutations[0]
        self.assertEqual(saved["changed_case_ids"], ["case-001", "case-002"])
        self.assertEqual(saved["changed_scope_keys"], ["expanded:all", "expanded:2026-05", "expanded:2026-06"])
        self.assertEqual(saved["pair_relation_snapshot"], {"relations": ["case-001", "case-002"]})
        self.assertEqual(saved["no_oa_bank_batch_snapshot"], {"batches": {}})
        self.assertEqual(saved["workbench_read_model_snapshot"], {"workbench": "snapshot"})

    def test_after_mutation_without_persist_only_emits_lifecycle_event(self) -> None:
        lifecycle_events: list[dict[str, object]] = []

        class StateStore:
            def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
                raise AssertionError("persist=False must not save no-OA mutation snapshots")

        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(snapshot=lambda: {}),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_service=SimpleNamespace(snapshot=lambda: {}, snapshot_case_ids=lambda _case_ids: {}),
            workbench_read_model_service=SimpleNamespace(snapshot=lambda: {}),
            state_store=StateStore(),
            execute_derived_data_lifecycle_event=lambda event_type, **kwargs: lifecycle_events.append(
                {"event_type": event_type, **kwargs}
            ),
        )

        changed = service.after_mutation(["2026-05"], changed_case_ids=["case-001"], persist=False)

        self.assertTrue(changed)
        self.assertEqual(lifecycle_events[0]["event_type"], "no_oa_bank_batch_changed")
        self.assertEqual(lifecycle_events[0]["months"], ["2026-05"])

    def test_enqueue_background_refresh_uses_durable_queue_boundary(self) -> None:
        class QueueRepository:
            def __init__(self) -> None:
                self.enqueued: list[dict[str, object]] = []

            def enqueue_read_model_refresh(self, **kwargs: object) -> None:
                self.enqueued.append(dict(kwargs))

        queue = QueueRepository()
        service = NoOaBankBatchApplicationService(
            import_service=SimpleNamespace(),
            effective_category_provider=SimpleNamespace(),
            no_oa_bank_batch_service=SimpleNamespace(),
            app_settings_service=SimpleNamespace(),
            bank_transaction_category_service=SimpleNamespace(),
            pair_relation_service=SimpleNamespace(),
            workbench_read_model_service=SimpleNamespace(),
            state_store=None,
            queue_repository=queue,
        )

        enqueued = service.enqueue_background_refresh(["all", "", "2026-05"], reason="unit_test")

        self.assertTrue(enqueued)
        self.assertEqual(
            queue.enqueued,
            [
                {"scope_type": "no_oa_bank_batch", "scope_key": "all", "reason": "unit_test"},
                {"scope_type": "no_oa_bank_batch", "scope_key": "2026-05", "reason": "unit_test"},
            ],
        )


if __name__ == "__main__":
    unittest.main()
