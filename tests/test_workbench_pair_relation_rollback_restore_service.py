from __future__ import annotations

import unittest
from typing import Any

from fin_ops_platform.services.workbench_pair_relation_rollback_restore_service import (
    WorkbenchPairRelationRollbackRestoreService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class StateStoreStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.saved: list[dict[str, Any]] = []

    def save_workbench_pair_relations(
        self,
        snapshot: dict[str, Any],
        *,
        changed_case_ids: list[str],
    ) -> None:
        if self.fail:
            raise RuntimeError("save failed")
        self.saved.append({"snapshot": snapshot, "changed_case_ids": list(changed_case_ids)})


class WorkbenchPairRelationRollbackRestoreServiceTests(unittest.TestCase):
    def test_restore_replaces_pair_relation_service_and_saves_snapshot(self) -> None:
        state_store = StateStoreStub()
        replaced: list[WorkbenchPairRelationService] = []
        snapshot = self._snapshot("CASE-ROLLBACK-001")
        service = WorkbenchPairRelationRollbackRestoreService(
            state_store=state_store,
            replace_pair_relation_service=replaced.append,
        )

        service.restore(snapshot, changed_case_ids=["CASE-ROLLBACK-001"])

        self.assertEqual(state_store.saved[0]["changed_case_ids"], ["CASE-ROLLBACK-001"])
        self.assertIsNotNone(replaced[0].get_active_relation_by_case_id("CASE-ROLLBACK-001"))

    def test_restore_swallows_state_store_failure_after_replacing_service(self) -> None:
        replaced: list[WorkbenchPairRelationService] = []
        service = WorkbenchPairRelationRollbackRestoreService(
            state_store=StateStoreStub(fail=True),
            replace_pair_relation_service=replaced.append,
        )

        service.restore(self._snapshot("CASE-ROLLBACK-002"), changed_case_ids=["CASE-ROLLBACK-002"])

        self.assertIsNotNone(replaced[0].get_active_relation_by_case_id("CASE-ROLLBACK-002"))

    @staticmethod
    def _snapshot(case_id: str) -> dict[str, Any]:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id=case_id,
            row_ids=[f"txn-{case_id}", f"oa-{case_id}"],
            row_types=["bank", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            month_scope="2026-01",
        )
        return service.snapshot()


if __name__ == "__main__":
    unittest.main()
