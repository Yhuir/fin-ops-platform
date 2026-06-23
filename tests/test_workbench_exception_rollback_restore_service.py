from __future__ import annotations

import unittest
from typing import Any

from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_exception_rollback_restore_service import WorkbenchExceptionRollbackRestoreService
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class StateStoreStub:
    def __init__(self, *, fail: bool = False) -> None:
        self.fail = fail
        self.saved_exception_cases: list[dict[str, Any]] = []

    def save_workbench_exception_cases(self, snapshot: dict[str, Any]) -> None:
        if self.fail:
            raise RuntimeError("save failed")
        self.saved_exception_cases.append(snapshot)


class WorkbenchExceptionRollbackRestoreServiceTests(unittest.TestCase):
    def test_restore_write_snapshots_replaces_all_services_and_reconfigures(self) -> None:
        replaced: dict[str, object] = {}
        configured: list[str] = []
        service = self._service(replaced=replaced, configured=configured)

        service.restore_write_snapshots(
            previous_exception_snapshot=WorkbenchExceptionCaseService().snapshot(),
            previous_pair_snapshot=self._pair_snapshot("CASE-EX-001"),
            previous_candidate_snapshot={"candidates": {"candidate-1": {"id": "candidate-1"}}},
            previous_override_snapshot={"row_overrides": {"row-1": {"case_id": "case-1"}}},
        )

        self.assertIsInstance(replaced["exception"], WorkbenchExceptionCaseService)
        self.assertIsInstance(replaced["pair"], WorkbenchPairRelationService)
        self.assertIsInstance(replaced["candidate"], WorkbenchCandidateMatchService)
        self.assertIsInstance(replaced["override"], WorkbenchOverrideService)
        self.assertEqual(configured, ["configured"])

    def test_restore_pair_snapshots_replaces_exception_and_pair_only(self) -> None:
        replaced: dict[str, object] = {}
        configured: list[str] = []
        service = self._service(replaced=replaced, configured=configured)

        service.restore_pair_snapshots(
            previous_exception_snapshot=WorkbenchExceptionCaseService().snapshot(),
            previous_pair_snapshot=self._pair_snapshot("CASE-EX-002"),
        )

        self.assertEqual(set(replaced), {"exception", "pair"})
        self.assertEqual(configured, ["configured"])

    def test_restore_override_snapshots_best_effort_saves_exception_snapshot(self) -> None:
        state_store = StateStoreStub(fail=True)
        replaced: dict[str, object] = {}
        configured: list[str] = []
        service = self._service(replaced=replaced, configured=configured, state_store=state_store)

        service.restore_override_snapshots(
            previous_exception_snapshot=WorkbenchExceptionCaseService().snapshot(),
            previous_override_snapshot={"row_overrides": {"row-3": {"case_id": "case-3"}}},
        )

        self.assertEqual(set(replaced), {"exception", "override"})
        self.assertEqual(configured, [])

    @staticmethod
    def _service(
        *,
        replaced: dict[str, object],
        configured: list[str],
        state_store: StateStoreStub | None = None,
    ) -> WorkbenchExceptionRollbackRestoreService:
        return WorkbenchExceptionRollbackRestoreService(
            state_store=state_store,
            replace_exception_case_service=lambda service: replaced.__setitem__("exception", service),
            replace_pair_relation_service=lambda service: replaced.__setitem__("pair", service),
            replace_candidate_match_service=lambda service: replaced.__setitem__("candidate", service),
            replace_override_service=lambda service: replaced.__setitem__("override", service),
            configure_exception_application_service=lambda: configured.append("configured"),
        )

    @staticmethod
    def _pair_snapshot(case_id: str) -> dict[str, Any]:
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
