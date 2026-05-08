from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_special_pair_rule_service import (
    CASH_TURNOVER_DETECTED,
    INTERNAL_TRANSFER_PAIR,
    OA_INVOICE_OFFSET_AUTO_MATCH,
    SALARY_PERSONAL_AUTO_MATCH,
    WorkbenchSpecialPairRuleService,
)


class WorkbenchSpecialPairRuleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchSpecialPairRuleService()

    def test_detects_salary_payment_to_personal_counterparty(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-salary-001",
                    "debit_amount": "8,500.00",
                    "credit_amount": "",
                    "summary": "工资",
                    "remark": "3月工资",
                    "counterparty_name": "张三",
                }
            ],
            invoice_rows=[],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], SALARY_PERSONAL_AUTO_MATCH)
        self.assertEqual(candidates[0]["status"], "auto_closed")
        self.assertIn("工资", candidates[0]["tags"])

    def test_detects_internal_transfer_by_company_identity_without_exact_name_equality(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-out-001",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220001",
                    "debit_amount": "13,000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "bank-in-001",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13,000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], INTERNAL_TRANSFER_PAIR)
        self.assertEqual(candidates[0]["special_metadata"]["cost_policy"], "exclude_all")

    def test_detects_configured_oa_attachment_invoice_offset(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "case_id": "CASE-OFFSET-001",
                    "applicant": "刘际涛",
                    "amount": "299.00",
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "invoice-offset-001",
                    "source_kind": "oa_attachment_invoice",
                    "case_id": "CASE-OFFSET-001",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["刘际涛"]},
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], OA_INVOICE_OFFSET_AUTO_MATCH)
        self.assertEqual(candidates[0]["special_metadata"]["cost_policy"], "exclude_all")
        self.assertIn("冲", candidates[0]["tags"])

    def test_cash_turnover_hint_uses_or_semantics_and_keeps_cost_policy_hint_only(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-cash-remark",
                    "debit_amount": "200.00",
                    "credit_amount": "",
                    "remark": "备用金",
                    "counterparty_name": "普通户名",
                },
                {
                    "id": "bank-cash-counterparty",
                    "debit_amount": "300.00",
                    "credit_amount": "",
                    "remark": "日常支出",
                    "counterparty_name": "陈秀云",
                },
                {
                    "id": "bank-cash-fulltext",
                    "debit_amount": "400.00",
                    "credit_amount": "",
                    "remark": "张双文公积金",
                    "counterparty_name": "普通户名",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual([candidate["rule_code"] for candidate in candidates], [CASH_TURNOVER_DETECTED] * 3)
        for candidate in candidates:
            self.assertEqual(candidate["status"], "needs_review")
            self.assertEqual(candidate["special_metadata"]["cost_policy"], "hint_only")
            self.assertFalse(candidate["special_metadata"]["cost_excluded"])
            self.assertIn("现金往来", candidate["tags"])


if __name__ == "__main__":
    unittest.main()
