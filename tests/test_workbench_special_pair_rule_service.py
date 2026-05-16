from __future__ import annotations

import unittest

from fin_ops_platform.services.workbench_special_pair_rule_service import (
    CASH_TURNOVER_DETECTED,
    INTERNAL_TRANSFER_PAIR,
    OA_INVOICE_OFFSET_AUTO_MATCH,
    SALARY_PERSONAL_AUTO_MATCH,
    WorkbenchSpecialPairRuleService,
)
from fin_ops_platform.services.workbench_special_rule_detectors import WorkbenchSpecialRuleDetector


EXTERNAL_TURNOVER_EVIDENCE = "external_turnover_evidence"


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
        self.assertEqual(candidates[0]["status"], "suppressed")
        self.assertIn("工资", candidates[0]["tags"])
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["suggested_action_code"],
            "auto_close_salary_payment",
        )
        self.assertTrue(candidates[0]["special_metadata"]["no_oa_managed"])
        self.assertEqual(candidates[0]["special_metadata"]["managed_batch_type"], "salary")

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
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["suggested_action_code"],
            "auto_close_internal_transfer",
        )

    def test_internal_transfer_category_is_evidence_but_still_requires_distinct_accounts(self) -> None:
        valid_candidates = self.service.generate_candidates(
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

        self.assertEqual(len(valid_candidates), 1)
        self.assertEqual(valid_candidates[0]["rule_code"], INTERNAL_TRANSFER_PAIR)
        self.assertIn("category_code", valid_candidates[0]["special_metadata"]["evidence"]["matched_fields"])

        invalid_candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[],
            bank_rows=[
                {
                    "id": "bank-same-account-out",
                    "category_code": "internal_transfer",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "未知账户",
                    "account_no": "62220001",
                    "debit_amount": "13,000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "bank-same-account-in",
                    "category_code": "internal_transfer",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "未知账户",
                    "account_no": "62220001",
                    "debit_amount": "",
                    "credit_amount": "13,000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
            ],
            invoice_rows=[],
        )

        self.assertEqual(invalid_candidates, [])

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
                    "derived_from_oa_id": "oa-offset-001",
                    "total_with_tax": "299.00",
                }
            ],
            settings={"offset_applicant_names": ["刘际涛"]},
        )

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], OA_INVOICE_OFFSET_AUTO_MATCH)
        self.assertEqual(candidates[0]["special_metadata"]["cost_policy"], "exclude_all")
        self.assertIn("冲", candidates[0]["tags"])

    def test_oa_attachment_invoice_offset_does_not_use_case_id_as_source_link(self) -> None:
        candidates = self.service.generate_candidates(
            "2026-03",
            oa_rows=[
                {
                    "id": "oa-offset-001",
                    "case_id": "CASE-POLLUTED",
                    "applicant": "刘际涛",
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
            settings={"offset_applicant_names": ["刘际涛"]},
        )

        self.assertEqual(candidates, [])

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
            self.assertEqual(
                candidate["special_metadata"]["evidence"]["suggested_action_code"],
                "review_cash_turnover",
            )

    def test_cash_turnover_category_directly_creates_review_evidence(self) -> None:
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

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], CASH_TURNOVER_DETECTED)
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertEqual(candidates[0]["special_metadata"]["cost_policy"], "hint_only")
        self.assertIn("现金往来", candidates[0]["tags"])
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["category_code"],
            "cash_turnover",
        )

    def test_offset_category_reuses_existing_offset_rule_code_without_auto_closing(self) -> None:
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

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], OA_INVOICE_OFFSET_AUTO_MATCH)
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertIn("冲", candidates[0]["tags"])
        self.assertFalse(candidates[0]["special_metadata"]["cost_excluded"])
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["category_code"],
            "offset",
        )

    def test_external_turnover_category_enters_metadata_without_fake_closed_loop(self) -> None:
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

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["rule_code"], EXTERNAL_TURNOVER_EVIDENCE)
        self.assertEqual(candidates[0]["status"], "needs_review")
        self.assertNotEqual(candidates[0]["status"], "auto_closed")
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["category_code"],
            "borrow_in_company_pending_repayment",
        )
        self.assertEqual(
            candidates[0]["special_metadata"]["evidence"]["category_path"],
            ["借入", "公司往来款", "待还款"],
        )
        self.assertIn("公司暂借款：待还款", candidates[0]["tags"])

    def test_shared_detector_returns_standard_evidence_for_classifier_reuse(self) -> None:
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

        salary = next(item for item in evaluations if item["rule_code"] == SALARY_PERSONAL_AUTO_MATCH)
        cash = next(item for item in evaluations if item["rule_code"] == CASH_TURNOVER_DETECTED)
        self.assertEqual(
            salary,
            {
                "rule_code": SALARY_PERSONAL_AUTO_MATCH,
                "confidence": "high",
                "suggested_action_code": "auto_close_salary_payment",
                "row_ids": ["bank-salary-001"],
                "oa_row_ids": [],
                "bank_row_ids": ["bank-salary-001"],
                "invoice_row_ids": [],
                "amount": "8500.00",
                "status": "auto_closed",
                "evidence": {
                    "matched_fields": ["summary", "remark"],
                    "amount": "8500.00",
                    "counterparty_name": "张三",
                    "summary": "工资 3月工资",
                },
                "display_tags": ["工资"],
                "cost_policy": "normal",
            },
        )
        self.assertEqual(cash["confidence"], "medium")
        self.assertEqual(cash["suggested_action_code"], "review_cash_turnover")
        self.assertEqual(cash["status"], "needs_review")
        self.assertEqual(cash["display_tags"], ["现金往来"])


if __name__ == "__main__":
    unittest.main()
