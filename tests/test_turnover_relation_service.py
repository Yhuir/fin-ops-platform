import unittest

from fin_ops_platform.services.turnover_relation_service import (
    TurnoverRelationService,
    TurnoverRelationValidationError,
)


def bank_row(
    transaction_id: str,
    *,
    category_code: str,
    counterparty_name: str = "贾小花",
    debit_amount: str = "",
    credit_amount: str = "",
    transaction_at: str = "2026-02-04T13:20:48",
) -> dict[str, str]:
    return {
        "id": transaction_id,
        "category_code": category_code,
        "counterparty_name": counterparty_name,
        "debit_amount": debit_amount,
        "credit_amount": credit_amount,
        "transaction_at": transaction_at,
        "account_name": "测试账户",
    }


class TurnoverRelationServiceTests(unittest.TestCase):
    def test_borrow_in_unique_exact_closed_generates_deterministic_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row(
                    "txn-in-1",
                    category_code="borrow_in_personal_pending_repayment",
                    credit_amount="200000.00",
                ),
                bank_row(
                    "txn-out-1",
                    category_code="borrow_in_personal_repaid",
                    debit_amount="200000.00",
                    transaction_at="2026-03-04T15:24:58",
                ),
            ]
        )

        self.assertEqual(len(relations), 1)
        relation = relations[0]
        self.assertEqual(relation["status"], "deterministic")
        self.assertEqual(relation["category_family"], "personal")
        self.assertEqual(relation["business_type"], "borrow_in")
        self.assertTrue(relation["sync_to_workbench"])
        self.assertEqual(relation["principal_amount"], "200000.00")
        self.assertEqual(relation["settled_amount"], "200000.00")
        self.assertEqual(relation["balance_amount"], "0.00")
        self.assertEqual(set(relation["bank_row_ids"]), {"txn-in-1", "txn-out-1"})
        self.assertEqual(service.relations(), relations)

    def test_borrow_in_partial_repayment_is_suggested_and_not_synced(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "suggested")
        self.assertFalse(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[0]["balance_amount"], "100000.00")
        self.assertEqual(relations[0]["evidence"]["auto_confirm_reason"], "partial_closed")

    def test_borrow_in_single_principal_multiple_repayments_unique_closed_is_deterministic(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="80000.00"),
                bank_row("txn-out-2", category_code="borrow_in_personal_repaid", debit_amount="120000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "deterministic")
        self.assertTrue(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[0]["balance_amount"], "0.00")
        self.assertEqual(relations[0]["evidence"]["auto_confirm_reason"], "unique_exact_fifo_closed")

    def test_borrow_out_multiple_principals_single_collection_unique_closed_is_deterministic(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-out-1", category_code="borrow_out_company_lent", debit_amount="60000.00"),
                bank_row("txn-out-2", category_code="borrow_out_company_lent", debit_amount="40000.00"),
                bank_row("txn-in-1", category_code="borrow_out_company_pending_collection", credit_amount="100000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "deterministic")
        self.assertEqual(relations[0]["category_family"], "company")
        self.assertTrue(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[0]["balance_amount"], "0.00")
        self.assertEqual(relations[0]["evidence"]["auto_confirm_reason"], "unique_exact_fifo_closed")

    def test_same_counterparty_multiple_solutions_are_suggested_and_not_synced(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_company_pending_repayment", credit_amount="100000.00"),
                bank_row("txn-in-2", category_code="borrow_in_company_pending_repayment", credit_amount="100000.00"),
                bank_row("txn-out-1", category_code="borrow_in_company_repaid", debit_amount="100000.00"),
                bank_row("txn-out-2", category_code="borrow_in_company_repaid", debit_amount="100000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "suggested")
        self.assertFalse(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[0]["balance_amount"], "0.00")
        self.assertEqual(relations[0]["evidence"]["auto_confirm_reason"], "multiple_solutions")

    def test_category_family_mapping_covers_personal_company_bank_and_business(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row(
                    "txn-personal-in",
                    category_code="borrow_in_personal_pending_repayment",
                    counterparty_name="个人户名",
                    credit_amount="10.00",
                ),
                bank_row(
                    "txn-personal-out",
                    category_code="borrow_in_personal_repaid",
                    counterparty_name="个人户名",
                    debit_amount="10.00",
                ),
                bank_row(
                    "txn-company-in",
                    category_code="borrow_in_company_pending_repayment",
                    counterparty_name="公司户名",
                    credit_amount="20.00",
                ),
                bank_row(
                    "txn-company-out",
                    category_code="borrow_in_company_repaid",
                    counterparty_name="公司户名",
                    debit_amount="20.00",
                ),
                bank_row(
                    "txn-bank-in",
                    category_code="borrow_in_bank_pending_repayment",
                    counterparty_name="银行户名",
                    credit_amount="30.00",
                ),
                bank_row(
                    "txn-bank-out",
                    category_code="borrow_in_bank_repaid",
                    counterparty_name="银行户名",
                    debit_amount="30.00",
                ),
                bank_row(
                    "txn-business-out",
                    category_code="business_warranty_pending_collection",
                    counterparty_name="业务户名",
                    debit_amount="40.00",
                ),
                bank_row(
                    "txn-business-in",
                    category_code="business_warranty_pending_collection",
                    counterparty_name="业务户名",
                    credit_amount="40.00",
                ),
            ]
        )

        family_by_counterparty = {
            relation["counterparty_name"]: relation["category_family"]
            for relation in relations
        }
        self.assertEqual(family_by_counterparty["个人户名"], "personal")
        self.assertEqual(family_by_counterparty["公司户名"], "company")
        self.assertEqual(family_by_counterparty["银行户名"], "bank")
        self.assertEqual(family_by_counterparty["业务户名"], "business")

    def test_borrow_out_unique_exact_closed_generates_deterministic_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-out-1", category_code="borrow_out_personal_lent", debit_amount="100000.00"),
                bank_row(
                    "txn-in-1",
                    category_code="borrow_out_personal_pending_collection",
                    credit_amount="100000.00",
                    transaction_at="2026-03-05T12:00:00",
                ),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "deterministic")
        self.assertEqual(relations[0]["business_type"], "borrow_out")
        self.assertTrue(relations[0]["sync_to_workbench"])

    def test_business_unique_exact_closed_generates_deterministic_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-out-1", category_code="business_warranty_pending_collection", debit_amount="50000.00"),
                bank_row(
                    "txn-in-1",
                    category_code="business_warranty_pending_collection",
                    credit_amount="50000.00",
                    transaction_at="2026-03-05T12:00:00",
                ),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "deterministic")
        self.assertEqual(relations[0]["category_family"], "business")
        self.assertEqual(relations[0]["business_type"], "business_receivable")
        self.assertTrue(relations[0]["sync_to_workbench"])

    def test_business_different_category_codes_do_not_mix_into_deterministic_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-out-1", category_code="business_warranty_pending_collection", debit_amount="50000.00"),
                bank_row(
                    "txn-in-1",
                    category_code="business_bid_bond_pending_collection",
                    credit_amount="50000.00",
                    transaction_at="2026-03-05T12:00:00",
                ),
            ]
        )

        self.assertEqual(len(relations), 2)
        self.assertEqual({tuple(relation["category_codes"]) for relation in relations}, {
            ("business_warranty_pending_collection",),
            ("business_bid_bond_pending_collection",),
        })
        self.assertTrue(all(relation["status"] == "suggested" for relation in relations))
        self.assertTrue(all(not relation["sync_to_workbench"] for relation in relations))

    def test_confirm_relation_rejects_mixed_business_category_codes(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-out-1", category_code="business_warranty_pending_collection", debit_amount="50000.00"),
                bank_row(
                    "txn-in-1",
                    category_code="business_bid_bond_pending_collection",
                    credit_amount="50000.00",
                    transaction_at="2026-03-05T12:00:00",
                ),
            ],
        )

        with self.assertRaises(TurnoverRelationValidationError) as context:
            service.confirm_relation(["txn-out-1", "txn-in-1"], actor="YNSYLP005")

        self.assertEqual(context.exception.error_code, "category_code_conflict")

    def test_confirm_relation_creates_confirmed_synced_relation_and_audit_entry(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ],
        )

        relation = service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005", note="人工确认")

        self.assertEqual(relation["status"], "confirmed")
        self.assertEqual(relation["source"], "manual")
        self.assertTrue(relation["sync_to_workbench"])
        self.assertEqual(relation["bank_row_ids"], ["txn-in-1", "txn-out-1"])
        self.assertEqual(relation["balance_amount"], "100000.00")
        self.assertEqual(service.audit_log()[0]["action"], "confirm_relation")
        self.assertEqual(service.audit_log()[0]["actor"], "YNSYLP005")
        self.assertEqual(service.audit_log()[0]["note"], "人工确认")

    def test_confirm_relation_replaces_same_row_system_suggestion(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ],
        )
        suggested = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ]
        )[0]

        confirmed = service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        self.assertEqual(confirmed["relation_id"], suggested["relation_id"])
        self.assertEqual(len(service.relations()), 1)
        self.assertEqual(service.relations()[0]["source"], "manual")
        self.assertEqual(service.relations()[0]["status"], "confirmed")

    def test_confirm_relation_rejects_rows_already_in_syncable_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)
        service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="200000.00"),
            ]
        )

        with self.assertRaises(TurnoverRelationValidationError) as context:
            service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        self.assertEqual(context.exception.error_code, "relation_row_conflict")

    def test_confirm_relation_rejects_duplicate_confirmed_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ],
        )
        service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        with self.assertRaises(TurnoverRelationValidationError) as context:
            service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        self.assertEqual(context.exception.error_code, "relation_row_conflict")

    def test_confirm_relation_rejects_single_sided_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
            ],
        )

        with self.assertRaises(TurnoverRelationValidationError) as context:
            service.confirm_relation(["txn-in-1"], actor="YNSYLP005")

        self.assertEqual(context.exception.error_code, "single_sided_relation")

    def test_rebuild_suppresses_system_relation_overlapping_active_manual_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ],
        )
        confirmed = service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["relation_id"], confirmed["relation_id"])
        self.assertEqual(relations[0]["status"], "confirmed")

    def test_withdraw_relation_marks_relation_withdrawn_and_audits(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="200000.00"),
            ],
        )
        relation = service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        withdrawn = service.withdraw_relation(relation["relation_id"], actor="YNSYLP006", note="撤销归并")

        self.assertEqual(withdrawn["status"], "withdrawn")
        self.assertFalse(withdrawn["sync_to_workbench"])
        self.assertEqual(service.audit_log()[-1]["action"], "withdraw_relation")
        self.assertEqual(service.audit_log()[-1]["old_status"], "confirmed")
        self.assertEqual(service.audit_log()[-1]["new_status"], "withdrawn")

    def test_invalidate_for_transaction_ids_marks_related_relation_stale_and_not_synced(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)
        relation = service.rebuild_from_bank_rows(
            [
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="200000.00"),
            ]
        )[0]

        updated = service.invalidate_for_transaction_ids(["txn-in-1"], actor="system")

        self.assertEqual(updated[0]["relation_id"], relation["relation_id"])
        self.assertEqual(updated[0]["status"], "stale")
        self.assertFalse(updated[0]["sync_to_workbench"])
        self.assertEqual(service.audit_log()[-1]["action"], "invalidate_relation")

    def test_invalidate_confirmed_relation_marks_conflict_and_not_synced(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="200000.00"),
            ],
        )
        relation = service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        updated = service.invalidate_for_transaction_ids(["txn-in-1"], actor="system")

        self.assertEqual(updated[0]["relation_id"], relation["relation_id"])
        self.assertEqual(updated[0]["status"], "conflict")
        self.assertFalse(updated[0]["sync_to_workbench"])
        self.assertEqual(service.audit_log()[-1]["old_status"], "confirmed")
        self.assertEqual(service.audit_log()[-1]["new_status"], "conflict")

    def test_invalid_direction_generates_conflict_relation_not_synced(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-bad-1", category_code="borrow_in_personal_pending_repayment", debit_amount="200000.00"),
            ]
        )

        self.assertEqual(len(relations), 1)
        self.assertEqual(relations[0]["status"], "conflict")
        self.assertFalse(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[0]["evidence"]["conflict_reason"], "invalid_direction")

    def test_confirm_relation_rejects_invalid_direction(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-bad-1", category_code="borrow_out_personal_lent", credit_amount="100000.00"),
            ],
        )

        with self.assertRaises(TurnoverRelationValidationError) as context:
            service.confirm_relation(["txn-bad-1"], actor="YNSYLP005")

        self.assertEqual(context.exception.error_code, "invalid_direction")

    def test_internal_transfer_legacy_tag_does_not_enter_relation(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        relations = service.rebuild_from_bank_rows(
            [
                bank_row("txn-internal-1", category_code="internal_transfer", debit_amount="100000.00"),
                bank_row("txn-internal-2", category_code="internal_transfer", credit_amount="100000.00"),
            ]
        )

        self.assertEqual(relations, [])

    def test_snapshot_round_trips_relations_and_audit_log(self) -> None:
        service = TurnoverRelationService.from_snapshot(
            None,
            bank_rows=[
                bank_row("txn-in-1", category_code="borrow_in_personal_pending_repayment", credit_amount="200000.00"),
                bank_row("txn-out-1", category_code="borrow_in_personal_repaid", debit_amount="100000.00"),
            ],
        )
        service.confirm_relation(["txn-in-1", "txn-out-1"], actor="YNSYLP005")

        restored = TurnoverRelationService.from_snapshot(service.snapshot())

        self.assertEqual(restored.relations()[0]["status"], "confirmed")
        self.assertEqual(restored.audit_log()[0]["action"], "confirm_relation")

    def test_snapshot_normalizes_sync_to_workbench_by_status_and_preserves_explicit_false(self) -> None:
        restored = TurnoverRelationService.from_snapshot(
            {
                "relations": [
                    {
                        "relation_id": "turnover_rel_dirty_suggested",
                        "status": "suggested",
                        "bank_row_ids": ["txn-in-1"],
                        "principal_row_ids": ["txn-in-1"],
                        "settlement_row_ids": [],
                        "sync_to_workbench": True,
                    },
                    {
                        "relation_id": "turnover_rel_dirty_status",
                        "status": "unexpected",
                        "bank_row_ids": ["txn-in-2"],
                        "principal_row_ids": ["txn-in-2"],
                        "settlement_row_ids": [],
                        "sync_to_workbench": True,
                    },
                    {
                        "relation_id": "turnover_rel_dirty_confirmed",
                        "status": "confirmed",
                        "bank_row_ids": ["txn-in-3", "txn-out-3"],
                        "principal_row_ids": ["txn-in-3"],
                        "settlement_row_ids": ["txn-out-3"],
                        "sync_to_workbench": False,
                    },
                    {
                        "relation_id": "turnover_rel_legacy_confirmed",
                        "status": "confirmed",
                        "bank_row_ids": ["txn-in-4", "txn-out-4"],
                        "principal_row_ids": ["txn-in-4"],
                        "settlement_row_ids": ["txn-out-4"],
                    },
                ]
            }
        )

        relations = restored.relations()
        self.assertFalse(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[1]["status"], "conflict")
        self.assertFalse(relations[1]["sync_to_workbench"])
        self.assertFalse(relations[2]["sync_to_workbench"])
        self.assertTrue(relations[3]["sync_to_workbench"])

    def test_snapshot_degrades_active_relation_without_both_sides(self) -> None:
        restored = TurnoverRelationService.from_snapshot(
            {
                "relations": [
                    {
                        "relation_id": "turnover_rel_single_sided",
                        "status": "confirmed",
                        "bank_row_ids": ["txn-in-1"],
                        "principal_row_ids": ["txn-in-1"],
                        "settlement_row_ids": [],
                        "sync_to_workbench": True,
                    }
                ]
            }
        )

        relation = restored.relations()[0]
        self.assertEqual(relation["status"], "conflict")
        self.assertFalse(relation["sync_to_workbench"])
        self.assertEqual(relation["evidence"]["snapshot_degraded_reason"], "malformed_syncable_relation")

    def test_snapshot_degrades_overlapping_active_syncable_relations(self) -> None:
        restored = TurnoverRelationService.from_snapshot(
            {
                "relations": [
                    {
                        "relation_id": "turnover_rel_first",
                        "status": "confirmed",
                        "bank_row_ids": ["txn-in-1", "txn-out-1"],
                        "principal_row_ids": ["txn-in-1"],
                        "settlement_row_ids": ["txn-out-1"],
                        "sync_to_workbench": True,
                    },
                    {
                        "relation_id": "turnover_rel_second",
                        "status": "deterministic",
                        "bank_row_ids": ["txn-in-1", "txn-out-2"],
                        "principal_row_ids": ["txn-in-1"],
                        "settlement_row_ids": ["txn-out-2"],
                        "sync_to_workbench": True,
                    },
                ]
            }
        )

        relations = restored.relations()
        self.assertTrue(relations[0]["sync_to_workbench"])
        self.assertEqual(relations[1]["status"], "conflict")
        self.assertFalse(relations[1]["sync_to_workbench"])
        self.assertEqual(relations[1]["evidence"]["snapshot_degraded_reason"], "active_syncable_overlap")

    def test_relation_id_is_stable_across_status_and_source(self) -> None:
        service = TurnoverRelationService.from_snapshot(None)

        self.assertEqual(
            service._relation_id(status="suggested", source="system", row_ids=["txn-2", "txn-1"]),
            service._relation_id(status="confirmed", source="manual", row_ids=["txn-1", "txn-2"]),
        )


if __name__ == "__main__":
    unittest.main()
