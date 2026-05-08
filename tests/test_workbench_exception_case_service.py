from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_exception_case_service import (
    EXCEPTION_CASE_DEFINITIONS,
    WorkbenchExceptionCaseService,
)


class WorkbenchExceptionCaseServiceTests(unittest.TestCase):
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
        self.assertEqual(service.snapshot()["row_case_index"], {"oa-001": "WEX-000001", "bank-001": "WEX-000001"})

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
        snapshot["row_case_index"]["oa-001"] = "mutated"

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
        self.assertEqual(restored_snapshot["row_case_index"]["oa-001"], "WEX-000001")
        self.assertEqual(restored_snapshot["row_case_index"]["invoice-001"], "WEX-000002")
        self.assertEqual(third["id"], "WEX-000003")


if __name__ == "__main__":
    unittest.main()
