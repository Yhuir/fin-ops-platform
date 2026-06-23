from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)


class CaptureRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []

    def save_workbench_pair_relations(self, snapshot: dict[str, object], *, changed_case_ids: list[str]) -> None:
        self.saved.append({"snapshot": snapshot, "changed_case_ids": list(changed_case_ids)})


class WorkbenchRelationCommandRepositoryAdapterTests(unittest.TestCase):
    def test_save_forwards_to_repository_and_applies_changed_case_delta(self) -> None:
        after_apply_calls: list[str] = []
        pair_service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"], "row_types": ["bank"], "status": "active"},
                    "CASE-2": {"case_id": "CASE-2", "row_ids": ["bank-2"], "row_types": ["bank"], "status": "active"},
                },
                "pair_relation_history": [
                    {"operation_type": "old-1", "after_relations": [{"case_id": "CASE-1"}]},
                    {"operation_type": "old-2", "after_relations": [{"case_id": "CASE-2"}]},
                ],
            }
        )
        repository = CaptureRepository()
        adapter = WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=pair_service,
            repository=repository,
            after_apply=lambda: after_apply_calls.append("called"),
        )
        snapshot = {
            "pair_relations": {
                "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1", "oa-1"], "row_types": ["bank", "oa"], "status": "active"},
            },
            "pair_relation_history": [
                {"operation_type": "new-1", "after_relations": [{"case_id": "CASE-1"}]},
            ],
        }

        adapter.save_workbench_pair_relations(snapshot, changed_case_ids={"CASE-1"})

        self.assertEqual(repository.saved[0]["changed_case_ids"], ["CASE-1"])
        current = pair_service.snapshot()
        self.assertEqual(current["pair_relations"]["CASE-1"]["row_ids"], ["bank-1", "oa-1"])
        self.assertEqual(current["pair_relations"]["CASE-2"]["row_ids"], ["bank-2"])
        self.assertEqual(
            [item["operation_type"] for item in current["pair_relation_history"]],
            ["old-2", "new-1"],
        )
        self.assertEqual(after_apply_calls, ["called"])

    def test_save_without_changed_cases_merges_incoming_relations_and_preserves_history(self) -> None:
        pair_service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"], "row_types": ["bank"], "status": "active"},
                },
                "pair_relation_history": [
                    {"operation_type": "old-1", "after_relations": [{"case_id": "CASE-1"}]},
                ],
            }
        )
        adapter = WorkbenchRelationCommandRepositoryAdapter(pair_relation_service=pair_service)

        adapter.save_workbench_pair_relations(
            {
                "pair_relations": {
                    "CASE-2": {"case_id": "CASE-2", "row_ids": ["bank-2"], "row_types": ["bank"], "status": "active"},
                },
                "pair_relation_history": [
                    {"operation_type": "new-2", "after_relations": [{"case_id": "CASE-2"}]},
                ],
            },
            changed_case_ids=[],
        )

        current = pair_service.snapshot()
        self.assertEqual(sorted(current["pair_relations"]), ["CASE-1", "CASE-2"])
        self.assertEqual(
            [item["operation_type"] for item in current["pair_relation_history"]],
            ["old-1", "new-2"],
        )


if __name__ == "__main__":
    unittest.main()
