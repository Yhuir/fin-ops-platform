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

    def test_create_active_relation_rejects_active_case_id_reuse_for_different_rows(self) -> None:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-PAIR-001",
            row_ids=["oa-001", "bk-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="all",
            created_at="2026-04-08T10:00:00+00:00",
        )

        with self.assertRaisesRegex(ValueError, "already active"):
            service.create_active_relation(
                case_id="CASE-PAIR-001",
                row_ids=["oa-002", "bk-002"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="YNSYLP005",
                month_scope="all",
                created_at="2026-04-08T11:00:00+00:00",
            )

        active_relation = service.get_active_relation_by_case_id("CASE-PAIR-001")
        assert active_relation is not None
        self.assertCountEqual(active_relation["row_ids"], ["oa-001", "bk-001"])

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

    def test_cancel_active_relations_for_row_ids_does_not_restore_prior_oa_bank_relation(self) -> None:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-ETC-DELETE-OLD",
            row_ids=["oa-001", "bank-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
            created_at="2026-04-08T10:00:00+00:00",
        )
        service.replace_with_confirmed_relation(
            case_id="CASE-ETC-DELETE",
            row_ids=["oa-001", "bank-001", "etc-summary-etc_20260520_001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
            note="ETC三栏配对",
            amount_check={"status": "matched", "external_etc_batch_id": "etc_20260520_001"},
            created_at="2026-04-08T11:00:00+00:00",
        )

        cancelled, history = service.cancel_active_relations_for_row_ids(
            ["etc-summary-etc_20260520_001"],
            created_by="system",
            note="删除 ETC 批次，取消 summary 关联",
            created_at="2026-04-08T12:00:00+00:00",
            operation_type="etc_summary_unmerged",
        )

        self.assertEqual([relation["case_id"] for relation in cancelled], ["CASE-ETC-DELETE"])
        self.assertEqual(history["operation_type"], "etc_summary_unmerged")
        self.assertEqual(history["after_relations"], [])
        self.assertIsNone(service.get_active_relation_by_row_id("etc-summary-etc_20260520_001"))
        self.assertIsNone(service.get_active_relation_by_row_id("oa-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("bank-001"))
        self.assertEqual(
            service.snapshot()["pair_relations"]["CASE-ETC-DELETE"]["status"],
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
