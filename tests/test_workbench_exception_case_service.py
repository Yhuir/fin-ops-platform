from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_exception_case_service import (
    EXCEPTION_CASE_DEFINITIONS,
    WorkbenchExceptionCaseService,
)


class WorkbenchExceptionCaseServiceTests(unittest.TestCase):
    def test_case_preserves_aligned_types_for_same_text_id_across_panes(self) -> None:
        service = WorkbenchExceptionCaseService()

        case = service.create_exception_case(
            rows=[
                {"id": "same-id", "type": "bank", "month": "2026-05"},
                {"id": "same-id", "type": "invoice", "month": "2026-05"},
            ],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )

        self.assertEqual(case["row_ids"], ["same-id", "same-id"])
        self.assertEqual(case["row_types"], ["bank", "invoice"])
        self.assertEqual(service.case_ids_for_typed_rows(["same-id"], ["bank"]), [case["id"]])
        self.assertEqual(service.case_ids_for_typed_rows(["same-id"], ["invoice"]), [case["id"]])

    def test_create_oa_bank_exception_case_indexes_rows(self) -> None:
        service = WorkbenchExceptionCaseService()

        case = service.create_exception_case(
            rows=[
                {"id": "oa-001", "type": "oa", "month": "2026-03"},
                {"id": "bank-001", "type": "bank", "pay_receive_time": "2026-03-18 09:10:00"},
            ],
            exception_code="oa_bank_amount_mismatch",
            exception_label="金额不一致，继续异常",
            category="oa_bank",
            comment="付款金额与OA金额不一致",
        )

        self.assertEqual(case["id"], "WEX-000001")
        self.assertEqual(case["status"], "confirmed")
        self.assertEqual(case["exception_code"], "oa_bank_amount_mismatch")
        self.assertEqual(case["exception_label"], "金额不一致，继续异常")
        self.assertEqual(case["category"], "oa_bank")
        self.assertEqual(case["row_ids"], ["oa-001", "bank-001"])
        self.assertEqual(case["row_types"], ["oa", "bank"])
        self.assertEqual(case["scope_months"], ["2026-03"])
        self.assertEqual(case["comment"], "付款金额与OA金额不一致")
        self.assertEqual(case["history"][0]["action"], "created")
        self.assertEqual(service.case_ids_for_rows(["oa-001", "bank-001"]), ["WEX-000001"])
        self.assertEqual(
            service.snapshot()["row_case_index"],
            {"oa\x1foa-001": "WEX-000001", "bank\x1fbank-001": "WEX-000001"},
        )

    def test_create_single_invoice_exception_case(self) -> None:
        service = WorkbenchExceptionCaseService()

        case = service.create_exception_case(
            rows=[{"id": "invoice-001", "type": "invoice", "month": "2026-04"}],
            exception_code="pending_collection",
            exception_label=EXCEPTION_CASE_DEFINITIONS["pending_collection"]["label"],
            category="invoice",
            scope_months=["2026-04"],
        )

        self.assertEqual(case["id"], "WEX-000001")
        self.assertEqual(case["status"], "confirmed")
        self.assertEqual(case["row_ids"], ["invoice-001"])
        self.assertEqual(case["row_types"], ["invoice"])
        self.assertEqual(case["scope_months"], ["2026-04"])
        self.assertEqual(service.case_ids_for_rows(["invoice-001"]), ["WEX-000001"])

    def test_create_settlement_case_records_audit_without_active_row_index(self) -> None:
        service = WorkbenchExceptionCaseService()

        case = service.create_settlement_case(
            rows=[
                {"id": "oa-advance-001", "type": "oa", "month": "2026-03"},
                {"id": "bank-advance-pay-001", "type": "bank", "pay_receive_time": "2026-03-18 09:10:00"},
                {"id": "bank-advance-repay-001", "type": "bank", "pay_receive_time": "2026-03-19 09:10:00"},
            ],
            exception_code="personal_advance_repayment_settlement",
            exception_label="还清个人暂借款",
            category="oa_bank_settlement",
            comment="已确认借款还清",
        )

        self.assertEqual(case["id"], "WEX-000001")
        self.assertEqual(case["status"], "settled")
        self.assertEqual(case["exception_code"], "personal_advance_repayment_settlement")
        self.assertEqual(case["exception_label"], "还清个人暂借款")
        self.assertEqual(case["category"], "oa_bank_settlement")
        self.assertEqual(
            case["row_ids"],
            ["oa-advance-001", "bank-advance-pay-001", "bank-advance-repay-001"],
        )
        self.assertEqual(case["row_types"], ["oa", "bank", "bank"])
        self.assertEqual(case["scope_months"], ["2026-03"])
        self.assertEqual(case["history"][0]["action"], "settled")
        self.assertEqual(
            service.case_ids_for_rows(["oa-advance-001", "bank-advance-pay-001", "bank-advance-repay-001"]),
            [],
        )
        self.assertEqual(service.snapshot()["row_case_index"], {})

    def test_create_case_from_action_writes_v2_fields_and_indexes_open_rows(self) -> None:
        service = WorkbenchExceptionCaseService()

        case = service.create_case_from_action(
            rows=[
                {"id": "oa-001", "type": "oa", "month": "2026-05"},
                {"id": "bank-001", "type": "bank", "month": "2026-05"},
            ],
            scenario={
                "business_line": "expense",
                "scenario_code": "expense_oa_bank_missing_input_invoice_equal",
                "scenario_label": "OA 和支出流水一致，缺进项发票",
                "rule_version": "exception_rules_v1",
            },
            action={
                "action_code": "wait_input_invoice",
                "label": "等待进项发票",
                "result_status": "open",
                "relation_mode": "pending_input_invoice",
            },
            amount_summary={"expense_relation": "oa_equals_bank_missing_input_invoice"},
            workflow_projection={"state": "WAIT_INPUT_INVOICE"},
            actor="finance-user",
            payload={"note": "继续追票"},
            candidate_ids=["candidate-001"],
            source_versions={"workbench_exception_rules_version": "exception_rules_v1"},
            idempotency_key="idem-001",
        )

        self.assertEqual(case["schema_version"], 2)
        self.assertEqual(case["status"], "open")
        self.assertEqual(case["business_line"], "expense")
        self.assertEqual(case["scenario_code"], "expense_oa_bank_missing_input_invoice_equal")
        self.assertEqual(case["rule_version"], "exception_rules_v1")
        self.assertEqual(case["amount_summary"]["expense_relation"], "oa_equals_bank_missing_input_invoice")
        self.assertEqual(case["resolution"]["action_code"], "wait_input_invoice")
        self.assertEqual(case["resolution"]["note"], "继续追票")
        self.assertEqual(case["workflow_projection"], {"state": "WAIT_INPUT_INVOICE"})
        self.assertEqual(case["audit"][0]["event"], "created")
        self.assertEqual(case["audit"][0]["actor"], "finance-user")
        self.assertEqual(case["candidate_ids"], ["candidate-001"])
        self.assertEqual(case["source_versions"], {"workbench_exception_rules_version": "exception_rules_v1"})
        self.assertEqual(service.case_ids_for_rows(["oa-001", "bank-001"]), ["WEX-000001"])
        self.assertEqual(service.find_case_by_idempotency_key("idem-001")["id"], "WEX-000001")

    def test_legacy_confirmed_snapshot_restores_as_active_v2_compatible_case(self) -> None:
        restored = WorkbenchExceptionCaseService.from_snapshot(
            {
                "case_counter": 1,
                "cases": {
                    "WEX-000001": {
                        "id": "WEX-000001",
                        "status": "confirmed",
                        "exception_code": "oa_bank_amount_mismatch",
                        "exception_label": "金额不一致，继续异常",
                        "category": "oa_bank",
                        "row_ids": ["oa-001", "bank-001"],
                        "row_types": ["oa", "bank"],
                        "scope_months": ["2026-05"],
                        "comment": "历史备注",
                        "created_at": "2026-05-11T00:00:00+00:00",
                        "updated_at": "2026-05-11T00:00:00+00:00",
                        "history": [{"action": "created", "at": "2026-05-11T00:00:00+00:00"}],
                    }
                },
                "row_case_index": {"oa-001": "WEX-000001", "bank-001": "WEX-000001"},
            }
        )

        case = restored.snapshot()["cases"]["WEX-000001"]
        self.assertEqual(case["status"], "confirmed")
        self.assertEqual(case["schema_version"], 2)
        self.assertEqual(case["business_line"], "expense")
        self.assertEqual(case["scenario_code"], "oa_bank_amount_mismatch")
        self.assertEqual(case["resolution"]["action_code"], "legacy_confirmed")
        self.assertEqual(restored.case_ids_for_rows(["oa-001", "bank-001"]), ["WEX-000001"])

    def test_cancel_exception_cases_marks_cases_cancelled_and_clears_row_index(self) -> None:
        service = WorkbenchExceptionCaseService()
        service.create_exception_case(
            rows=[
                {"id": "oa-001", "type": "oa", "month": "2026-03"},
                {"id": "bank-001", "type": "bank", "month": "2026-03"},
            ],
            exception_code="oa_missing_bank",
            exception_label="OA缺流水",
            category="oa_bank",
        )

        cancelled_cases = service.cancel_exception_cases(
            rows=[{"id": "oa-001", "type": "oa"}, {"id": "bank-001", "type": "bank"}],
            comment="误处理",
        )

        self.assertEqual([case["id"] for case in cancelled_cases], ["WEX-000001"])
        self.assertEqual(cancelled_cases[0]["status"], "cancelled")
        self.assertEqual(cancelled_cases[0]["history"][-1]["action"], "cancelled")
        self.assertEqual(cancelled_cases[0]["history"][-1]["comment"], "误处理")
        self.assertEqual(service.case_ids_for_rows(["oa-001", "bank-001"]), [])
        self.assertEqual(service.snapshot()["row_case_index"], {})

    def test_cancel_exception_cases_does_not_cancel_same_text_id_in_another_pane(self) -> None:
        service = WorkbenchExceptionCaseService()
        oa_case = service.create_exception_case(
            rows=[{"id": "same-id", "type": "oa", "month": "2026-03"}],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )
        bank_case = service.create_exception_case(
            rows=[{"id": "same-id", "type": "bank", "month": "2026-03"}],
            exception_code="bank_fee",
            exception_label="银行手续费",
            category="bank",
        )

        cancelled = service.cancel_exception_cases(
            rows=[{"id": "same-id", "type": "bank"}],
        )

        self.assertEqual([case["id"] for case in cancelled], [bank_case["id"]])
        self.assertEqual(service.get_case(bank_case["id"])["status"], "cancelled")
        self.assertEqual(service.get_case(oa_case["id"])["status"], "confirmed")
        self.assertEqual(
            service.case_ids_for_typed_rows(["same-id"], ["oa"]),
            [oa_case["id"]],
        )

    def test_ignore_and_unignore_invoice_case_status_and_row_index(self) -> None:
        service = WorkbenchExceptionCaseService()

        ignored_case = service.ignore_row(
            {"id": "invoice-001", "type": "invoice", "month": "2026-05"},
            comment="暂不处理",
        )

        self.assertEqual(ignored_case["id"], "WEX-000001")
        self.assertEqual(ignored_case["status"], "ignored")
        self.assertEqual(ignored_case["exception_code"], "pending_collection")
        self.assertEqual(ignored_case["category"], "invoice")
        self.assertEqual(service.case_ids_for_rows(["invoice-001"]), ["WEX-000001"])

        unignored_case = service.unignore_row({"id": "invoice-001", "type": "invoice"})

        self.assertEqual(unignored_case["id"], "WEX-000001")
        self.assertEqual(unignored_case["status"], "cancelled")
        self.assertEqual(unignored_case["history"][-1]["action"], "unignored")
        self.assertEqual(service.case_ids_for_rows(["invoice-001"]), [])
        self.assertEqual(service.snapshot()["row_case_index"], {})

    def test_ignore_and_unignore_do_not_reuse_same_text_id_from_oa_pane(self) -> None:
        service = WorkbenchExceptionCaseService()
        oa_case = service.create_exception_case(
            rows=[{"id": "same-id", "type": "oa", "month": "2026-05"}],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )

        ignored_case = service.ignore_row(
            {"id": "same-id", "type": "invoice", "month": "2026-05"}
        )
        unignored_case = service.unignore_row(
            {"id": "same-id", "type": "invoice"}
        )

        self.assertNotEqual(ignored_case["id"], oa_case["id"])
        self.assertEqual(unignored_case["id"], ignored_case["id"])
        self.assertEqual(unignored_case["status"], "cancelled")
        self.assertEqual(service.get_case(oa_case["id"])["status"], "confirmed")
        self.assertEqual(
            service.case_ids_for_typed_rows(["same-id"], ["oa"]),
            [oa_case["id"]],
        )

    def test_snapshot_round_trip_preserves_cases_counter_and_index(self) -> None:
        service = WorkbenchExceptionCaseService()
        first = service.create_exception_case(
            rows=[{"id": "oa-001", "type": "oa", "month": "2026-03"}],
            exception_code="manual_review",
            exception_label="人工复核",
            category="manual",
        )
        service.ignore_row({"id": "invoice-001", "type": "invoice", "month": "2026-04"})

        snapshot = service.snapshot()
        snapshot["cases"][first["id"]]["status"] = "mutated"
        snapshot["row_case_index"]["oa\x1foa-001"] = "mutated"

        restored = WorkbenchExceptionCaseService.from_snapshot(service.snapshot())
        third = restored.create_exception_case(
            rows=[{"id": "bank-001", "type": "bank", "month": "2026-05"}],
            exception_code="bank_missing_oa_misc",
            exception_label="银行流水缺OA",
            category="bank",
        )

        restored_snapshot = restored.snapshot()
        self.assertEqual(restored_snapshot["case_counter"], 3)
        self.assertEqual(restored_snapshot["cases"]["WEX-000001"]["status"], "confirmed")
        self.assertEqual(restored_snapshot["row_case_index"]["oa\x1foa-001"], "WEX-000001")
        self.assertEqual(
            restored_snapshot["row_case_index"]["invoice\x1finvoice-001"],
            "WEX-000002",
        )
        self.assertEqual(third["id"], "WEX-000003")


if __name__ == "__main__":
    unittest.main()
