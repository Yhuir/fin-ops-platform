from __future__ import annotations

import unittest
from typing import Any

from fin_ops_platform.services.workbench_exception_case_service import WorkbenchExceptionCaseService
from fin_ops_platform.services.workbench_exception_rollback_restore_service import WorkbenchExceptionRollbackRestoreService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchExceptionRollbackRestoreServiceTests(unittest.TestCase):
    def test_restore_pair_snapshots_replaces_exception_and_pair_services(self) -> None:
        replaced: dict[str, object] = {}
        service = WorkbenchExceptionRollbackRestoreService(
            replace_exception_case_service=lambda value: replaced.__setitem__("exception", value),
            replace_pair_relation_service=lambda value: replaced.__setitem__("pair", value),
        )

        service.restore_pair_snapshots(
            previous_exception_snapshot=WorkbenchExceptionCaseService().snapshot(),
            previous_pair_snapshot=self._pair_snapshot("CASE-EX-002"),
        )

        self.assertEqual(set(replaced), {"exception", "pair"})
        self.assertIsInstance(replaced["exception"], WorkbenchExceptionCaseService)
        self.assertIsInstance(replaced["pair"], WorkbenchPairRelationService)

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
