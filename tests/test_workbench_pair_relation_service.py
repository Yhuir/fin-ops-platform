import unittest

from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class WorkbenchPairRelationServiceTests(unittest.TestCase):
    def test_create_active_relation_can_be_looked_up_by_case_id_and_row_id(self) -> None:
        service = WorkbenchPairRelationService()

        relation = service.create_active_relation(
            case_id="CASE-PAIR-001",
            row_ids=["oa-001", "bk-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="all",
            created_at="2026-04-08T10:00:00+00:00",
        )

        self.assertEqual(relation["status"], "active")
        self.assertEqual(service.get_active_relation_by_case_id("CASE-PAIR-001"), relation)
        self.assertEqual(service.get_active_relation_by_row_id("oa-001"), relation)
        self.assertEqual(service.get_active_relation_by_row_id("bk-001"), relation)
        self.assertEqual(
            service.snapshot(),
            {
                "pair_relations": {
                    "CASE-PAIR-001": relation,
                }
            },
        )

    def test_cancel_relation_marks_relation_cancelled_and_removes_active_lookup(self) -> None:
        service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-PAIR-001": {
                        "case_id": "CASE-PAIR-001",
                        "row_ids": ["oa-001", "bk-001"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "YNSYLP005",
                        "created_at": "2026-04-08T10:00:00+00:00",
                        "updated_at": "2026-04-08T10:00:00+00:00",
                    }
                }
            }
        )

        cancelled = service.cancel_relation(
            "CASE-PAIR-001",
            cancelled_at="2026-04-08T11:00:00+00:00",
        )

        self.assertIsNotNone(cancelled)
        assert cancelled is not None
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["updated_at"], "2026-04-08T11:00:00+00:00")
        self.assertIsNone(service.get_active_relation_by_case_id("CASE-PAIR-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("oa-001"))
        self.assertEqual(
            service.snapshot()["pair_relations"]["CASE-PAIR-001"]["status"],
            "cancelled",
        )

    def test_snapshot_case_ids_only_deepcopies_requested_relations(self) -> None:
        service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-PAIR-001": {
                        "case_id": "CASE-PAIR-001",
                        "row_ids": ["oa-001", "bk-001"],
                        "row_types": ["oa", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "YNSYLP005",
                        "created_at": "2026-04-08T10:00:00+00:00",
                        "updated_at": "2026-04-08T10:00:00+00:00",
                    },
                    "CASE-PAIR-002": {
                        "case_id": "CASE-PAIR-002",
                        "row_ids": ["iv-001", "bk-002"],
                        "row_types": ["invoice", "bank"],
                        "status": "active",
                        "relation_mode": "manual_confirmed",
                        "month_scope": "all",
                        "created_by": "YNSYLP005",
                        "created_at": "2026-04-08T10:00:00+00:00",
                        "updated_at": "2026-04-08T10:00:00+00:00",
                    },
                }
            }
        )

        snapshot = service.snapshot_case_ids(["CASE-PAIR-002"])

        self.assertEqual(
            snapshot,
            {
                "pair_relations": {
                    "CASE-PAIR-002": service.snapshot()["pair_relations"]["CASE-PAIR-002"],
                }
            },
        )


if __name__ == "__main__":
    unittest.main()
