from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_special_pair_rule_service import (
    OA_INVOICE_OFFSET_AUTO_MATCH,
    WorkbenchSpecialPairRuleService,
)
from fin_ops_platform.services.workbench_special_rule_detectors import WorkbenchSpecialRuleDetector


class WorkbenchSpecialPairRuleServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = WorkbenchSpecialPairRuleService()

    def test_salary_payment_no_longer_creates_workbench_special_candidate(self) -> None:
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

        self.assertEqual(candidates, [])

    def test_internal_transfer_no_longer_creates_workbench_special_candidate(self) -> None:
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

        self.assertEqual(candidates, [])

    def test_internal_transfer_manual_category_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-tagged-out",
                    "category_code": "internal_transfer",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "未知账户",
                    "account_no": "62220001",
                    "debit_amount": "13,000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "bank-tagged-in",
                    "category_code": "internal_transfer",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "未知账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13,000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(candidates, [])

    def test_detects_configured_oa_attachment_invoice_offset(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "case_id": "CASE-OFFSET-001",
                    "applicant": "周洁莹",
                    "amount": "299.00",
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "invoice-offset-001",
                    "source_kind": "oa_attachment_invoice",
                    "case_id": "CASE-OFFSET-001",
                    "derived_from_oa_id": "oa-offset-001",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["周洁莹"]},
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], OA_INVOICE_OFFSET_AUTO_MATCH)
        self.assertEqual(candidates[0]["special_metadata"]["cost_policy"], "exclude_all")
        self.assertIn("冲", candidates[0]["tags"])

    def test_oa_attachment_invoice_offset_is_limited_to_zhou_jieying(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "applicant": "刘际涛",
                    "amount": "299.00",
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "invoice-offset-001",
                    "source_kind": "oa_attachment_invoice",
                    "derived_from_oa_id": "oa-offset-001",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["刘际涛"]},
        )

        self.assertEqual(candidates, [])

    def test_oa_attachment_invoice_offset_does_not_use_case_id_as_source_link(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "case_id": "CASE-POLLUTED",
                    "applicant": "周洁莹",
                    "amount": "299.00",
                }
            ],
            bank_rows=[],
            invoice_rows=[
                {
                    "id": "invoice-from-another-oa",
                    "source_kind": "oa_attachment_invoice",
                    "case_id": "CASE-POLLUTED",
                    "derived_from_oa_id": "oa-offset-other",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["周洁莹"]},
        )

        self.assertEqual(candidates, [])

    def test_cash_turnover_hint_no_longer_creates_workbench_special_candidate(self) -> None:
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

        self.assertEqual(candidates, [])

    def test_cash_turnover_category_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-tagged-cash",
                    "category_code": "cash_turnover",
                    "debit_amount": "200.00",
                    "credit_amount": "",
                    "remark": "普通备注",
                    "counterparty_name": "普通户名",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(candidates, [])

    def test_bank_offset_category_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-tagged-offset",
                    "category_code": "offset",
                    "debit_amount": "299.00",
                    "credit_amount": "",
                    "remark": "人工标记冲",
                    "counterparty_name": "普通户名",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(candidates, [])

    def test_external_turnover_category_no_longer_creates_workbench_special_candidate(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-tagged-external",
                    "category_code": "borrow_in_company_pending_repayment",
                    "category_label": "公司暂借款：待还款",
                    "category_path": ["借入", "公司往来款", "待还款"],
                    "debit_amount": "",
                    "credit_amount": "3,000.00",
                    "remark": "外部借款",
                    "counterparty_name": "外部客户",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(candidates, [])

    def test_shared_detector_only_returns_oa_invoice_offset_evidence(self) -> None:
        detector = WorkbenchSpecialRuleDetector()

        evaluations = detector.evaluate(
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-salary-001",
                    "debit_amount": "8,500.00",
                    "summary": "工资",
                    "remark": "3月工资",
                    "counterparty_name": "张三",
                },
                {
                    "id": "bank-cash-001",
                    "debit_amount": "200.00",
                    "remark": "备用金",
                    "counterparty_name": "普通户名",
                },
            ],
            invoice_rows=[],
            settings={},
        )

        self.assertEqual(evaluations, [])


if __name__ == "__main__":
    unittest.main()
