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

    def test_create_active_relation_rejects_active_row_reuse_by_different_case_id(self) -> None:
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

        with self.assertRaisesRegex(ValueError, "row already active"):
            service.create_active_relation(
                case_id="CASE-PAIR-002",
                row_ids=["oa-001", "bk-002"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="YNSYLP005",
                month_scope="all",
                created_at="2026-04-08T11:00:00+00:00",
            )

        self.assertIsNone(service.get_active_relation_by_case_id("CASE-PAIR-002"))
        self.assertEqual(len(service.list_active_relations()), 1)

    def test_create_active_relation_dedupes_duplicate_row_ids_and_keeps_row_types_aligned(self) -> None:
        service = WorkbenchPairRelationService()

        relation = service.create_active_relation(
            case_id="CASE-PAIR-DUPE",
            row_ids=["oa-001", "bk-001", "oa-001", "iv-001"],
            row_types=["oa", "bank", "oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="YNSYLP005",
            month_scope="all",
            created_at="2026-04-08T10:00:00+00:00",
        )

        self.assertEqual(relation["row_ids"], ["oa-001", "bk-001", "iv-001"])
        self.assertEqual(relation["row_types"], ["oa", "bank", "invoice"])
        self.assertEqual(service.get_active_relation_by_row_id("oa-001"), relation)

    def test_create_active_relation_rejects_duplicate_row_id_with_conflicting_type(self) -> None:
        service = WorkbenchPairRelationService()

        with self.assertRaisesRegex(ValueError, "conflicting row type"):
            service.create_active_relation(
                case_id="CASE-PAIR-CONFLICT",
                row_ids=["oa-001", "oa-001"],
                row_types=["oa", "invoice"],
                relation_mode="manual_confirmed",
                created_by="YNSYLP005",
                month_scope="all",
                created_at="2026-04-08T10:00:00+00:00",
            )

        self.assertIsNone(service.get_active_relation_by_case_id("CASE-PAIR-CONFLICT"))

    def test_from_snapshot_dedupes_duplicate_row_ids(self) -> None:
        service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-PAIR-DUPE": {
                        "case_id": "CASE-PAIR-DUPE",
                        "row_ids": ["oa-001", "bk-001", "oa-001"],
                        "row_types": ["oa", "bank", "oa"],
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

        relation = service.get_active_relation_by_case_id("CASE-PAIR-DUPE")
        assert relation is not None
        self.assertEqual(relation["row_ids"], ["oa-001", "bk-001"])
        self.assertEqual(relation["row_types"], ["oa", "bank"])

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

    def test_replace_with_confirmed_relation_does_not_persist_display_only_existing_case_history(self) -> None:
        service = WorkbenchPairRelationService()

        _relation, history = service.replace_with_confirmed_relation(
            case_id="CASE-FULL",
            row_ids=["bank-001", "invoice-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
            before_relations=[
                {
                    "case_id": "CASE-DISPLAY-ONLY",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": "2026-04",
                }
            ],
        )

        self.assertEqual(history["before_relations"], [])

    def test_replace_with_confirmed_relation_marks_owned_active_before_relation_as_restorable(self) -> None:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-PARTIAL",
            row_ids=["oa-001", "invoice-001"],
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )

        _relation, history = service.replace_with_confirmed_relation(
            case_id="CASE-FULL",
            row_ids=["oa-001", "bank-001", "invoice-001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
            before_relations=[
                {
                    "case_id": "CASE-PARTIAL",
                    "row_ids": ["oa-001", "invoice-001"],
                    "row_types": ["oa", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                },
                {
                    "case_id": "CASE-DISPLAY-ONLY",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": "2026-04",
                },
            ],
        )

        self.assertEqual([relation["case_id"] for relation in history["before_relations"]], ["CASE-PARTIAL"])
        self.assertEqual(
            history["before_relations"][0]["special_metadata"]["restorable_on_withdraw"],
            True,
        )

    def test_replace_with_confirmed_relation_does_not_persist_unowned_manual_history(self) -> None:
        service = WorkbenchPairRelationService()

        _relation, history = service.replace_with_confirmed_relation(
            case_id="CASE-FULL",
            row_ids=["bank-001", "invoice-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
            before_relations=[
                {
                    "case_id": "CASE-UNOWNED-MANUAL",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                }
            ],
        )

        self.assertEqual(history["before_relations"], [])

    def test_withdraw_ignores_historical_unmarked_manual_before_relation(self) -> None:
        service = WorkbenchPairRelationService()
        active = service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["bank-001", "invoice-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-UNMARKED-MANUAL",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                }
            ],
            after_relations=[active],
            affected_row_ids=["bank-001", "invoice-001"],
            created_by="finance",
        )

        preview = service.preview_withdraw_for_row_ids(["bank-001"])
        self.assertEqual(preview["after_relations"], [])

        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["bank-001"],
            created_by="finance",
        )
        self.assertEqual(restored_relations, [])
        self.assertEqual(history["after_relations"], [])
        self.assertIsNone(service.get_active_relation_by_case_id("CASE-UNMARKED-MANUAL"))
        self.assertIsNone(service.get_active_relation_by_row_id("bank-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("invoice-001"))

    def test_withdraw_preserves_oa_attachment_binding_without_history(self) -> None:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["oa-exp-2066-2", "txn_imported_0640", "oa-att-inv-oa-exp-2066-2-01"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-05",
        )

        preview = service.preview_withdraw_for_row_ids(["txn_imported_0640"])

        self.assertEqual(len(preview["after_relations"]), 1)
        self.assertEqual(preview["after_relations"][0]["case_id"], "CASE-OA-ATT-oa-exp-2066-2")
        self.assertEqual(
            preview["after_relations"][0]["row_ids"],
            ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
        )

        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["txn_imported_0640"],
            created_by="finance",
        )

        self.assertEqual([relation["case_id"] for relation in restored_relations], ["CASE-OA-ATT-oa-exp-2066-2"])
        self.assertEqual(history["after_relations"][0]["case_id"], "CASE-OA-ATT-oa-exp-2066-2")
        self.assertIsNone(service.get_active_relation_by_row_id("txn_imported_0640"))
        restored = service.get_active_relation_by_row_id("oa-exp-2066-2")
        assert restored is not None
        self.assertEqual(restored["row_ids"], ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"])
        self.assertEqual(
            service.get_active_relation_by_row_id("oa-att-inv-oa-exp-2066-2-01"),
            restored,
        )

    def test_withdraw_preserves_oa_attachment_when_restored_relation_contains_parent_oa(self) -> None:
        service = WorkbenchPairRelationService()
        previous = service.create_active_relation(
            case_id="CASE-OA-BANK",
            row_ids=["oa-exp-2066-2", "txn_imported_0640"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-05",
        )
        service.replace_with_confirmed_relation(
            case_id="CASE-FULL",
            row_ids=["oa-exp-2066-2", "txn_imported_0640", "oa-att-inv-oa-exp-2066-2-01"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-05",
            before_relations=[previous],
        )

        preview = service.preview_withdraw_for_row_ids(["txn_imported_0640"])

        self.assertEqual(len(preview["after_relations"]), 1)
        self.assertEqual(preview["after_relations"][0]["case_id"], "CASE-OA-BANK")
        self.assertEqual(
            preview["after_relations"][0]["row_ids"],
            ["oa-exp-2066-2", "txn_imported_0640", "oa-att-inv-oa-exp-2066-2-01"],
        )
        self.assertTrue(
            preview["after_relations"][0]["special_metadata"]["contains_immutable_oa_attachment_binding"]
        )

    def test_withdraw_rejects_plain_oa_attachment_binding_relation(self) -> None:
        service = WorkbenchPairRelationService()
        service.create_active_relation(
            case_id="CASE-OA-ATT-oa-exp-2066-2",
            row_ids=["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"],
            row_types=["oa", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-05",
        )

        preview = service.preview_withdraw_for_row_ids(["oa-exp-2066-2"])

        self.assertEqual(preview["after_relations"][0]["row_ids"], ["oa-exp-2066-2", "oa-att-inv-oa-exp-2066-2-01"])
        with self.assertRaisesRegex(ValueError, "immutable_oa_attachment_binding"):
            service.withdraw_latest_for_row_ids(["oa-exp-2066-2"], created_by="finance")
        self.assertIsNotNone(service.get_active_relation_by_case_id("CASE-OA-ATT-oa-exp-2066-2"))

    def test_withdraw_ignores_explicit_restorable_snapshot_with_same_row_set(self) -> None:
        service = WorkbenchPairRelationService()
        active = service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["bank-001", "invoice-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-SAME-ROWS",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                    "special_metadata": {"restorable_on_withdraw": True},
                }
            ],
            after_relations=[active],
            affected_row_ids=["bank-001", "invoice-001"],
            created_by="finance",
        )

        preview = service.preview_withdraw_for_row_ids(["bank-001"])

        self.assertEqual(preview["after_relations"], [])

    def test_withdraw_ignores_restorable_snapshot_with_same_canonical_alias_row_set(self) -> None:
        service = WorkbenchPairRelationService()
        active = service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["oa-exp-2156", "bank-001", "invoice-001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-SAME-ALIAS-ROWS",
                    "row_ids": ["oa-exp-69fab21659b12d7d42a50a45", "bank-001", "invoice-001"],
                    "row_types": ["oa", "bank", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                    "special_metadata": {"restorable_on_withdraw": True},
                }
            ],
            after_relations=[active],
            affected_row_ids=["oa-exp-2156", "bank-001", "invoice-001"],
            created_by="finance",
        )

        row_id_aliases = {"oa-exp-69fab21659b12d7d42a50a45": "oa-exp-2156"}
        preview = service.preview_withdraw_for_row_ids(["bank-001"], row_id_aliases=row_id_aliases)
        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["bank-001"],
            created_by="finance",
            row_id_aliases=row_id_aliases,
        )

        self.assertEqual(preview["after_relations"], [])
        self.assertEqual(restored_relations, [])
        self.assertEqual(history["after_relations"], [])
        self.assertIsNone(service.get_active_relation_by_row_id("bank-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("invoice-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("oa-exp-2156"))

    def test_withdraw_restores_explicit_restorable_previous_relation(self) -> None:
        service = WorkbenchPairRelationService()
        active = service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["oa-001", "bank-001", "invoice-001"],
            row_types=["oa", "bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-PARTIAL",
                    "row_ids": ["oa-001", "invoice-001"],
                    "row_types": ["oa", "invoice"],
                    "status": "active",
                    "relation_mode": "manual_confirmed",
                    "month_scope": "2026-04",
                    "special_metadata": {"restorable_on_withdraw": True},
                }
            ],
            after_relations=[active],
            affected_row_ids=["oa-001", "bank-001", "invoice-001"],
            created_by="finance",
        )

        preview = service.preview_withdraw_for_row_ids(["bank-001"])
        self.assertEqual(preview["after_relations"][0]["case_id"], "CASE-PARTIAL")

        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["bank-001"],
            created_by="finance",
        )
        self.assertEqual(restored_relations[0]["case_id"], "CASE-PARTIAL")
        self.assertEqual(history["after_relations"][0]["case_id"], "CASE-PARTIAL")
        self.assertIsNone(service.get_active_relation_by_row_id("bank-001"))
        restored = service.get_active_relation_by_row_id("oa-001")
        assert restored is not None
        self.assertEqual(restored["case_id"], "CASE-PARTIAL")

    def test_withdraw_restores_previous_relations_from_turnover_manual_closure_history(self) -> None:
        service = WorkbenchPairRelationService()
        previous_oa_1 = service.create_active_relation(
            case_id="CASE-OA-1",
            row_ids=["oa-001", "bank-001"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        previous_oa_2 = service.create_active_relation(
            case_id="CASE-OA-2",
            row_ids=["oa-002", "bank-002"],
            row_types=["oa", "bank"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.replace_with_confirmed_relation(
            case_id="turnover:REL-CLOSURE",
            row_ids=["oa-001", "bank-001", "oa-002", "bank-002", "bank-003"],
            row_types=["oa", "bank", "oa", "bank", "bank"],
            relation_mode="turnover_manual_closure",
            created_by="finance",
            month_scope="2026-04",
            before_relations=[previous_oa_1, previous_oa_2],
            operation_type="turnover_manual_closure_confirm",
        )

        preview = service.preview_withdraw_for_row_ids(["bank-003"])
        self.assertEqual(
            [relation["case_id"] for relation in preview["after_relations"]],
            ["CASE-OA-1", "CASE-OA-2"],
        )

        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["bank-003"],
            created_by="finance",
        )

        self.assertEqual(
            [relation["case_id"] for relation in restored_relations],
            ["CASE-OA-1", "CASE-OA-2"],
        )
        self.assertEqual(
            [relation["case_id"] for relation in history["after_relations"]],
            ["CASE-OA-1", "CASE-OA-2"],
        )
        self.assertIsNone(service.get_active_relation_by_case_id("turnover:REL-CLOSURE"))
        self.assertEqual(service.get_active_relation_by_row_id("bank-001")["case_id"], "CASE-OA-1")
        self.assertEqual(service.get_active_relation_by_row_id("bank-002")["case_id"], "CASE-OA-2")
        self.assertIsNone(service.get_active_relation_by_row_id("bank-003"))

    def test_withdraw_ignores_historical_display_only_existing_case_before_relation(self) -> None:
        service = WorkbenchPairRelationService()
        active = service.create_active_relation(
            case_id="CASE-FULL",
            row_ids=["bank-001", "invoice-001"],
            row_types=["bank", "invoice"],
            relation_mode="manual_confirmed",
            created_by="finance",
            month_scope="2026-04",
        )
        service.record_history(
            operation_type="confirm_link",
            before_relations=[
                {
                    "case_id": "CASE-DISPLAY-ONLY",
                    "row_ids": ["bank-001", "invoice-001"],
                    "row_types": ["bank", "invoice"],
                    "status": "active",
                    "relation_mode": "existing_case",
                    "month_scope": "2026-04",
                }
            ],
            after_relations=[active],
            affected_row_ids=["bank-001", "invoice-001"],
            created_by="finance",
        )

        preview = service.preview_withdraw_for_row_ids(["bank-001"])
        self.assertEqual(preview["after_relations"], [])

        restored_relations, history = service.withdraw_latest_for_row_ids(
            ["bank-001"],
            created_by="finance",
        )
        self.assertEqual(restored_relations, [])
        self.assertEqual(history["after_relations"], [])
        self.assertIsNone(service.get_active_relation_by_case_id("CASE-DISPLAY-ONLY"))
        self.assertIsNone(service.get_active_relation_by_row_id("bank-001"))
        self.assertIsNone(service.get_active_relation_by_row_id("invoice-001"))

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
                },
                "pair_relation_history": [
                    {
                        "case_id": "CASE-PAIR-001",
                        "operation_type": "old-case",
                        "after_relations": [{"case_id": "CASE-PAIR-001"}],
                    },
                    {
                        "case_id": "CASE-PAIR-002",
                        "operation_type": "selected-case",
                        "after_relations": [{"case_id": "CASE-PAIR-002"}],
                    },
                ],
            }
        )

        snapshot = service.snapshot_case_ids(["CASE-PAIR-002"])

        self.assertEqual(
            snapshot["pair_relations"],
            {
                "CASE-PAIR-002": service.snapshot()["pair_relations"]["CASE-PAIR-002"],
            },
        )
        self.assertEqual(
            [history["operation_type"] for history in snapshot["pair_relation_history"]],
            ["selected-case"],
        )

    def test_snapshot_case_ids_can_exclude_history_for_command_delta(self) -> None:
        service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-1": {
                        "case_id": "CASE-1",
                        "row_ids": ["bank-1"],
                        "row_types": ["bank"],
                        "status": "active",
                    }
                },
                "pair_relation_history": [
                    {
                        "operation_id": "old-operation",
                        "operation_type": "old",
                        "after_relations": [{"case_id": "CASE-1"}],
                    }
                ],
            }
        )

        snapshot = service.snapshot_case_ids(["CASE-1"], include_history=False)

        self.assertEqual(sorted(snapshot["pair_relations"]), ["CASE-1"])
        self.assertNotIn("pair_relation_history", snapshot)

    def test_append_history_delta_preserves_old_history_and_is_idempotent(self) -> None:
        service = WorkbenchPairRelationService.from_snapshot(
            {
                "pair_relations": {
                    "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1"], "status": "active"},
                    "CASE-2": {"case_id": "CASE-2", "row_ids": ["bank-2"], "status": "active"},
                },
                "pair_relation_history": [
                    {
                        "operation_id": "old-case-1",
                        "operation_type": "old-case-1",
                        "after_relations": [{"case_id": "CASE-1"}],
                    },
                    {
                        "operation_id": "old-case-2",
                        "operation_type": "old-case-2",
                        "after_relations": [{"case_id": "CASE-2"}],
                    },
                ],
            }
        )
        delta = {
            "pair_relations": {
                "CASE-1": {"case_id": "CASE-1", "row_ids": ["bank-1", "oa-1"], "status": "active"}
            },
            "pair_relation_history": [
                {
                    "operation_id": "new-case-1",
                    "operation_type": "new-case-1",
                    "after_relations": [{"case_id": "CASE-1"}],
                }
            ],
        }

        service.apply_snapshot_delta(delta, changed_case_ids=["CASE-1"], replace_history=False)
        service.apply_snapshot_delta(delta, changed_case_ids=["CASE-1"], replace_history=False)

        self.assertEqual(
            [history["operation_type"] for history in service.list_history()],
            ["old-case-1", "old-case-2", "new-case-1"],
        )
        self.assertEqual(service.get_active_relation_by_case_id("CASE-1")["row_ids"], ["bank-1", "oa-1"])


if __name__ == "__main__":
    unittest.main()
