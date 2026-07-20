from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_repository_adapter import (
    WorkbenchRelationCommandRepositoryAdapter,
)


class CaptureRepository:
    def __init__(self) -> None:
        self.saved: list[dict[str, object]] = []
        self.snapshot: dict[str, object] = {}
        self.scoped_loads: list[dict[str, object]] = []

    def load_workbench_pair_relations(self) -> dict[str, object]:
        return self.snapshot

    def load_workbench_pair_relations_for_row_ids(
        self,
        row_ids: list[str],
        *,
        case_ids: list[str] | None = None,
    ) -> dict[str, object]:
        self.scoped_loads.append({"row_ids": list(row_ids), "case_ids": list(case_ids or [])})
        return WorkbenchPairRelationService.from_snapshot(
            self.snapshot
        ).snapshot_for_row_ids(list(row_ids), case_ids=list(case_ids or []))

    def save_workbench_pair_relations(self, snapshot: dict[str, object], *, changed_case_ids: list[str]) -> None:
        self.saved.append({"snapshot": snapshot, "changed_case_ids": list(changed_case_ids)})


class SnapshotBlockingPairRelationService(WorkbenchPairRelationService):
    def snapshot(self) -> dict[str, object]:
        raise AssertionError("changed-case apply must not rebuild the global snapshot")


class WorkbenchRelationCommandRepositoryAdapterTests(unittest.TestCase):
    def test_load_prefers_repository_when_repository_is_configured(self) -> None:
        pair_service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "MEMORY": {"case_id": "MEMORY", "row_ids": ["bank-memory"], "row_types": ["bank"], "status": "active"},
                },
            }
        )
        repository = CaptureRepository()
        repository.snapshot = {
            "pair_relations": {
                "DURABLE": {"case_id": "DURABLE", "row_ids": ["bank-db"], "row_types": ["bank"], "status": "active"},
            },
        }
        adapter = WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=pair_service,
            repository=repository,
        )

        self.assertEqual(sorted(adapter.load_workbench_pair_relations()["pair_relations"]), ["DURABLE"])

    def test_scoped_load_prefers_repository_scope_boundary(self) -> None:
        pair_service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "MEMORY": {"case_id": "MEMORY", "row_ids": ["bank-memory"], "row_types": ["bank"], "status": "active"},
                },
            }
        )
        repository = CaptureRepository()
        repository.snapshot = {
            "pair_relations": {
                "DURABLE": {"case_id": "DURABLE", "row_ids": ["bank-db"], "row_types": ["bank"], "status": "active"},
                "OTHER": {"case_id": "OTHER", "row_ids": ["bank-other"], "row_types": ["bank"], "status": "active"},
            },
        }
        adapter = WorkbenchRelationCommandRepositoryAdapter(
            pair_relation_service=pair_service,
            repository=repository,
        )

        snapshot = adapter.load_workbench_pair_relations_for_row_ids(["bank-db"], case_ids=["DURABLE"])

        self.assertEqual(sorted(snapshot["pair_relations"]), ["DURABLE"])
        self.assertEqual(repository.scoped_loads, [{"row_ids": ["bank-db"], "case_ids": ["DURABLE"]}])

    def test_scoped_load_filters_in_memory_snapshot_when_repository_has_no_scope_boundary(self) -> None:
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
        adapter = WorkbenchRelationCommandRepositoryAdapter(pair_relation_service=pair_service)

        snapshot = adapter.load_workbench_pair_relations_for_row_ids(["bank-2"])

        self.assertEqual(sorted(snapshot["pair_relations"]), ["CASE-2"])
        self.assertEqual([item["operation_type"] for item in snapshot["pair_relation_history"]], ["old-2"])

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

    def test_changed_case_delta_does_not_read_global_snapshot_and_can_delete_case(self) -> None:
        pair_service = SnapshotBlockingPairRelationService(
            pair_relations={
                "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"], "row_types": ["bank"], "status": "active"},
                "CASE-2": {"case_id": "CASE-2", "row_ids": ["bank-2"], "row_types": ["bank"], "status": "active"},
            },
            pair_relation_history=[
                {"operation_type": "old-1", "after_relations": [{"case_id": "CASE-1"}]},
                {"operation_type": "old-2", "after_relations": [{"case_id": "CASE-2"}]},
            ],
        )
        adapter = WorkbenchRelationCommandRepositoryAdapter(pair_relation_service=pair_service)

        adapter.save_workbench_pair_relations(
            {
                "pair_relations": {},
                "pair_relation_history": [
                    {"operation_type": "withdraw-1", "before_relations": [{"case_id": "CASE-1"}]},
                ],
            },
            changed_case_ids=["CASE-1"],
        )

        self.assertIsNone(pair_service.get_active_relation_by_case_id("CASE-1"))
        self.assertEqual(
            pair_service.get_active_relation_by_case_id("CASE-2")["row_ids"],
            ["bank-2"],
        )
        self.assertEqual(
            [item["operation_type"] for item in pair_service.list_history()],
            ["old-2", "withdraw-1"],
        )

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
