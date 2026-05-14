from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
    BankTransactionAutoCategoryService,
    resolve_effective_category,
)
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.workbench_special_rule_detectors import (
    INTERNAL_TRANSFER_PAIR,
    SALARY_PERSONAL_AUTO_MATCH,
)


class BankTransactionAutoCategoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BankTransactionAutoCategoryService()

    def test_detects_fee_from_summary_remark_and_nested_fields(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-fee",
                    "summary": "普通转账",
                    "remark": "网银手续费",
                    "detail_fields": {"补充说明": "转账手续费"},
                }
            ]
        )

        suggestion = suggestions["txn-fee"]
        self.assertEqual(suggestion["category_code"], "fee")
        self.assertEqual(suggestion["category_label"], "手续费")
        self.assertEqual(suggestion["category_path"], ["自动识别", "手续费"])
        self.assertEqual(suggestion["source"], "auto")
        self.assertEqual(suggestion["rule_code"], "fee_text_keyword")
        self.assertEqual(suggestion["confidence"], "high")
        self.assertEqual(suggestion["rule_version"], BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION)

    def test_detects_salary_by_reusing_workbench_special_rule_detector(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-salary",
                    "debit_amount": "8500.00",
                    "credit_amount": "",
                    "summary": "工资",
                    "remark": "4月工资",
                    "counterparty_name": "张三",
                }
            ]
        )

        suggestion = suggestions["txn-salary"]
        self.assertEqual(suggestion["category_code"], "salary")
        self.assertEqual(suggestion["category_label"], "工资")
        self.assertEqual(suggestion["rule_code"], SALARY_PERSONAL_AUTO_MATCH)
        self.assertIn("workbench_special_rule_detector", suggestion["reason"])

    def test_detects_holiday_bonus_from_keywords(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [{"id": "txn-holiday", "purpose": "中秋过节费", "note": "员工慰问金"}]
        )

        self.assertEqual(suggestions["txn-holiday"]["category_code"], "holiday_bonus")
        self.assertEqual(suggestions["txn-holiday"]["category_label"], "过节费")
        self.assertEqual(suggestions["txn-holiday"]["rule_code"], "holiday_bonus_text_keyword")

    def test_detects_bonus_from_keywords(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [{"id": "txn-bonus", "summary_fields": {"用途": "2025年终奖"}}]
        )

        self.assertEqual(suggestions["txn-bonus"]["category_code"], "bonus")
        self.assertEqual(suggestions["txn-bonus"]["category_label"], "奖金")
        self.assertEqual(suggestions["txn-bonus"]["rule_code"], "bonus_text_keyword")

    def test_detects_internal_transfer_pair_by_reusing_detector_semantics(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-transfer-out",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220001",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "txn-transfer-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
            ]
        )

        self.assertCountEqual(list(suggestions), ["txn-transfer-out", "txn-transfer-in"])
        for suggestion in suggestions.values():
            self.assertEqual(suggestion["category_code"], "internal_transfer")
            self.assertEqual(suggestion["category_label"], "内部往来款")
            self.assertEqual(suggestion["category_path"], ["自动识别", "内部往来款"])
            self.assertEqual(suggestion["rule_code"], INTERNAL_TRANSFER_PAIR)
            self.assertIn("workbench_special_rule_detector", suggestion["reason"])

    def test_effective_category_uses_manual_before_auto(self) -> None:
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-fee",
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-fee", "category_code": "bonus", "expected_version": 0}],
            actor="YNSYLP005",
        )
        auto = self.service.suggest_for_rows([{"id": "txn-fee", "summary": "网银手续费"}])["txn-fee"]

        effective = resolve_effective_category(category_service.get("txn-fee"), auto)

        self.assertEqual(effective["effective_category_code"], "bonus")
        self.assertEqual(effective["effective_category_label"], "奖金")
        self.assertEqual(effective["effective_category_source"], "manual")

    def test_effective_category_respects_manual_clear_before_auto(self) -> None:
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-fee",
        )
        category_service.apply_updates(
            [{"transaction_id": "txn-fee", "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )
        auto = self.service.suggest_for_rows([{"id": "txn-fee", "summary": "网银手续费"}])["txn-fee"]

        effective = resolve_effective_category(category_service.get("txn-fee"), auto)

        self.assertEqual(effective["effective_category_code"], None)
        self.assertEqual(effective["effective_category_label"], None)
        self.assertEqual(effective["effective_category_path"], [])
        self.assertEqual(effective["effective_category_source"], "")


if __name__ == "__main__":
    unittest.main()
