from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.bank_batch_application_service import BankBatchPersistenceError
from fin_ops_platform.services.bank_batch_service import BANK_FLOW_RULE_BATCH_RELATION_MODE
from fin_ops_platform.services.bank_flow_rule_batch_application_service import BankFlowRuleBatchApplicationService
from fin_ops_platform.services.bank_flow_rule_batch_read_model_refresh import BankFlowRuleBatchReadModelPersistencePort


class RecordingStateStore:
    def __init__(self) -> None:
        self.bank_flow_mutations: list[dict[str, object]] = []
        self.bank_flow_snapshots: list[dict[str, object]] = []
        self.bank_flow_scopes: list[dict[str, object]] = []

    def save_bank_flow_rule_batch_mutation(self, **kwargs: object) -> None:
        self.bank_flow_mutations.append(dict(kwargs))

    def save_bank_flow_rule_batches(self, snapshot: dict[str, object]) -> None:
        self.bank_flow_snapshots.append(dict(snapshot))

    def save_bank_flow_rule_batches_scope(self, snapshot: dict[str, object], *, scope_key: str) -> None:
        self.bank_flow_scopes.append({"snapshot": dict(snapshot), "scope_key": scope_key})

    def save_no_oa_bank_batch_mutation(self, **_kwargs: object) -> None:
        raise AssertionError("bank-flow mutation must not call no-OA persistence")

    def save_no_oa_bank_batches(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("bank-flow refresh must not call no-OA snapshot persistence")

    def save_no_oa_bank_batches_scope(self, *_args: object, **_kwargs: object) -> None:
        raise AssertionError("bank-flow refresh must not call no-OA scoped persistence")


class RecordingPairSnapshotPort:
    def snapshot_case_ids(self, case_ids: list[str]) -> dict[str, object]:
        return {"case_ids": list(case_ids)}

    def snapshot(self) -> dict[str, object]:
        return {"all": True}


class RecordingWorkbenchReadModelService:
    def snapshot(self) -> dict[str, object]:
        return {"workbench": True}


class RefreshAwareBatchService:
    def __init__(self, refresh_calls: list[dict[str, object]]) -> None:
        self._refresh_calls = refresh_calls
        self.withdraw_calls: list[dict[str, object]] = []

    def get_batch(self, batch_id: str) -> dict[str, object]:
        if not self._refresh_calls:
            raise KeyError("stale_runtime_snapshot")
        return {
            "batch_id": batch_id,
            "batch_type": "fee",
            "batch_label": "手续费",
            "status": "submitted",
            "status_bucket": "submitted",
            "version": 2,
            "row_ids": ["bank-1"],
            "row_count": 1,
            "relation_case_id": batch_id,
            "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
        }

    def snapshot(self) -> dict[str, object]:
        return {"batches": {}}

    def withdraw_batch(
        self,
        batch_id: str,
        *,
        actor: str,
        expected_version: int | None,
        reason: str | None,
    ) -> dict[str, object]:
        self.withdraw_calls.append(
            {
                "batch_id": batch_id,
                "actor": actor,
                "expected_version": expected_version,
                "reason": reason,
            }
        )
        return {**self.get_batch(batch_id), "status": "withdrawn"}


class BankFlowRuleBatchApplicationServiceTests(unittest.TestCase):
    @staticmethod
    def _service_with_refresh_aware_batch() -> tuple[
        BankFlowRuleBatchApplicationService,
        RefreshAwareBatchService,
        list[dict[str, object]],
    ]:
        refresh_calls: list[dict[str, object]] = []
        batch_service = RefreshAwareBatchService(refresh_calls)
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = batch_service
        service.refresh_batches = (  # type: ignore[method-assign]
            lambda **kwargs: refresh_calls.append(dict(kwargs)) or ([], {})
        )
        service._public_batch = lambda batch: dict(batch)  # type: ignore[method-assign]
        service.no_oa_bank_transaction_rows_by_ids = lambda _row_ids: []  # type: ignore[method-assign]
        service.effective_categories_for_rows = lambda _rows: {}  # type: ignore[method-assign]
        service._workbench_relation_rows_by_id = lambda _row_ids: {}  # type: ignore[method-assign]
        service.detail_rows = lambda *_args: []  # type: ignore[method-assign]
        service._apply_submitted_row_tag_snapshot = lambda _batch, rows: rows  # type: ignore[method-assign]
        service._apply_relation_status_to_detail_rows = (  # type: ignore[method-assign]
            lambda rows, _relations: rows
        )
        service._detail_categories_by_transaction_id = lambda *_args: {}  # type: ignore[method-assign]
        service._workbench_relation_source_versions = lambda: {}  # type: ignore[method-assign]
        service.resolve_labels = lambda batches: batches  # type: ignore[method-assign]
        service._pair_relation_snapshot_port = SimpleNamespace(snapshot=lambda: {}, restore=lambda _snapshot: None)
        service._cancel_relation_for_batch = lambda *_args, **_kwargs: None  # type: ignore[method-assign]
        service._mutation_result = lambda batch, **_kwargs: {"batch": dict(batch)}  # type: ignore[method-assign]
        return service, batch_service, refresh_calls

    def test_detail_refreshes_bank_flow_runtime_snapshot_before_lookup(self) -> None:
        service, _batch_service, refresh_calls = self._service_with_refresh_aware_batch()

        detail = service.detail_payload("batch-1")

        self.assertEqual(detail["batch"]["batch_id"], "batch-1")
        self.assertEqual(
            refresh_calls,
            [
                {
                    "apply_relation_repairs": False,
                    "scope_key": "all",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            ],
        )

    def test_withdraw_refreshes_bank_flow_runtime_snapshot_before_lookup(self) -> None:
        service, batch_service, refresh_calls = self._service_with_refresh_aware_batch()

        result = service.withdraw_batch(
            "batch-1",
            actor="finance-user",
            expected_version=2,
            reason="误提交",
        )

        self.assertEqual(result["batch"]["status"], "withdrawn")
        self.assertEqual(batch_service.withdraw_calls[0]["batch_id"], "batch-1")
        self.assertEqual(
            refresh_calls,
            [
                {
                    "apply_relation_repairs": False,
                    "scope_key": "all",
                    "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE,
                }
            ],
        )

    def test_submitted_candidate_lookup_is_relation_mode_scoped(self) -> None:
        class BatchService:
            def __init__(self) -> None:
                self.filters: list[dict[str, object]] = []

            def list_batches(self, filters: dict[str, object]) -> list[dict[str, object]]:
                self.filters.append(dict(filters))
                return [{"batch_id": "batch-1", "status": "submitted"}]

        batch_service = BatchService()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._bank_batch_service = batch_service

        candidates = service._submitted_batches_for_relation_mode(BANK_FLOW_RULE_BATCH_RELATION_MODE)

        self.assertEqual(candidates, [{"batch_id": "batch-1", "status": "submitted"}])
        self.assertEqual(
            batch_service.filters,
            [{"bucket": "submitted", "relation_mode": BANK_FLOW_RULE_BATCH_RELATION_MODE}],
        )

    def test_persist_mutation_uses_bank_flow_state_store_boundary(self) -> None:
        state_store = RecordingStateStore()
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = state_store
        service._search_cache_clearer = lambda: None
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._workbench_read_model_service = RecordingWorkbenchReadModelService()
        service._bank_batch_public_snapshot = lambda: {"batches": {"batch-1": {"batch_id": "batch-1"}}}

        service.persist_mutation(changed_case_ids=["case-1"], changed_scope_keys=["2026-05"])

        self.assertEqual(len(state_store.bank_flow_mutations), 1)
        mutation = state_store.bank_flow_mutations[0]
        self.assertEqual(mutation["pair_relation_snapshot"], {"case_ids": ["case-1"]})
        self.assertEqual(mutation["bank_flow_rule_batch_snapshot"], {"batches": {"batch-1": {"batch_id": "batch-1"}}})
        self.assertEqual(mutation["workbench_read_model_snapshot"], {"workbench": True})
        self.assertEqual(mutation["changed_case_ids"], ["case-1"])
        self.assertEqual(mutation["changed_scope_keys"], ["2026-05"])

    def test_persist_mutation_fails_fast_without_bank_flow_boundary(self) -> None:
        service = object.__new__(BankFlowRuleBatchApplicationService)
        service._state_store = object()
        service._search_cache_clearer = lambda: None
        service._pair_relation_snapshot_port = RecordingPairSnapshotPort()
        service._workbench_read_model_service = RecordingWorkbenchReadModelService()
        service._bank_batch_public_snapshot = lambda: {"batches": {}}

        with self.assertRaises(BankBatchPersistenceError):
            service.persist_mutation(changed_case_ids=[], changed_scope_keys=["all"])

    def test_refresh_persistence_uses_bank_flow_scope_boundary(self) -> None:
        state_store = RecordingStateStore()
        port = BankFlowRuleBatchReadModelPersistencePort(state_store)

        port.save_public_snapshot({"batches": {}}, scope_key="2026-05")

        self.assertEqual(state_store.bank_flow_scopes, [{"snapshot": {"batches": {}}, "scope_key": "2026-05"}])
        self.assertEqual(state_store.bank_flow_snapshots, [])


if __name__ == "__main__":
    unittest.main()
