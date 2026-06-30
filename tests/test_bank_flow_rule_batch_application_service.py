from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_batch_application_service import BankBatchPersistenceError
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


class BankFlowRuleBatchApplicationServiceTests(unittest.TestCase):
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
