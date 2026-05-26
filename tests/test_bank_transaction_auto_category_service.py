from __future__ import annotations

import unittest

from fin_ops_platform.services.bank_transaction_auto_category_service import (
    BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION,
    BankTransactionAutoCategoryService,
    resolve_effective_category,
)
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService


class BankTransactionAutoCategoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BankTransactionAutoCategoryService()

    def test_detects_fee_from_counterparty_summary_or_remark_only(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-fee-remark",
                    "summary": "普通转账",
                    "remark": "网银手续费",
                    "detail_fields": {"补充说明": "转账手续费"},
                },
                {
                    "id": "txn-fee-counterparty",
                    "counterparty_name": "中国建设银行手续费专户",
                    "summary": "普通转账",
                    "remark": "",
                },
            ]
        )

        suggestion = suggestions["txn-fee-remark"]
        self.assertEqual(suggestion["category_code"], "fee")
        self.assertEqual(suggestion["category_label"], "手续费")
        self.assertEqual(suggestion["category_path"], ["自动识别", "手续费"])
        self.assertEqual(suggestion["source"], "auto")
        self.assertEqual(suggestion["rule_code"], "fee_text_keyword")
        self.assertEqual(suggestion["confidence"], "high")
        self.assertEqual(suggestion["rule_version"], BANK_TRANSACTION_AUTO_CATEGORY_RULE_VERSION)
        self.assertEqual(suggestions["txn-fee-counterparty"]["category_code"], "fee")

    def test_plain_service_fee_text_is_not_bank_fee(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-service-fee",
                    "summary": "服务费",
                    "remark": "",
                    "counterparty_name": "昆明市盘龙区精正空调设备维修服务部",
                    "debit_amount": "10000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-04-23 17:33:58",
                },
                {
                    "id": "txn-detail-fee-only",
                    "summary": "普通转账",
                    "remark": "",
                    "detail_fields": {"补充说明": "转账手续费"},
                },
            ]
        )

        self.assertNotIn("txn-service-fee", suggestions)
        self.assertNotIn("txn-detail-fee-only", suggestions)

    def test_detects_sms_service_fee_as_bank_fee_without_broadening_service_fee(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {"id": "txn-sms-service-fee", "summary": "短信服务费", "remark": ""},
                {"id": "txn-plain-service-fee", "summary": "服务费", "remark": ""},
            ]
        )

        self.assertEqual(suggestions["txn-sms-service-fee"]["category_code"], "fee")
        self.assertEqual(suggestions["txn-sms-service-fee"]["rule_code"], "fee_text_keyword")
        self.assertNotIn("txn-plain-service-fee", suggestions)

    def test_detects_salary_from_text_keyword_without_workbench_detector(self) -> None:
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
        self.assertEqual(suggestion["rule_code"], "salary_text_keyword")
        self.assertEqual(suggestion["source"], "auto")
        self.assertNotIn("workbench_special_rule_detector", suggestion["reason"])

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

    def test_detects_tax_treasury_tax_collection_and_social_security_from_keywords(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {"id": "txn-tax", "summary": "税款扣缴"},
                {"id": "txn-treasury-tax", "remark": "代理国库税收收缴"},
                {"id": "txn-social-security", "purpose": "社保款缴纳"},
            ]
        )

        self.assertEqual(suggestions["txn-tax"]["category_code"], "tax_payment")
        self.assertEqual(suggestions["txn-tax"]["category_label"], "税款")
        self.assertEqual(suggestions["txn-tax"]["rule_code"], "tax_payment_text_keyword")
        self.assertEqual(suggestions["txn-treasury-tax"]["category_code"], "treasury_tax_collection")
        self.assertEqual(suggestions["txn-treasury-tax"]["category_label"], "代理国库税收收缴")
        self.assertEqual(suggestions["txn-treasury-tax"]["rule_code"], "treasury_tax_collection_text_keyword")
        self.assertEqual(suggestions["txn-social-security"]["category_code"], "social_security")
        self.assertEqual(suggestions["txn-social-security"]["category_label"], "社保款")
        self.assertEqual(suggestions["txn-social-security"]["rule_code"], "social_security_text_keyword")

    def test_tax_and_social_security_rules_do_not_match_broad_generic_words(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {"id": "txn-tax-fee", "summary": "税费咨询服务"},
                {"id": "txn-tax-deduct", "remark": "员工扣税差额"},
                {"id": "txn-social-insurance", "purpose": "社会保险咨询"},
                {"id": "txn-condolence", "note": "员工慰问金"},
                {"id": "txn-holiday-generic", "note": "节日慰问金"},
                {"id": "txn-tax-social-security", "summary": "社保及税款"},
                {"id": "txn-treasury-generic", "remark": "税收收缴"},
            ]
        )

        self.assertEqual(suggestions, {})

    def test_internal_transfer_pair_is_classified_before_text_rules(self) -> None:
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
                    "summary": "手续费",
                },
                {
                    "id": "txn-transfer-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                    "remark": "工资",
                },
            ]
        )

        self.assertEqual(suggestions["txn-transfer-out"]["category_code"], "internal_transfer")
        self.assertEqual(suggestions["txn-transfer-in"]["category_code"], "internal_transfer")
        self.assertEqual(suggestions["txn-transfer-out"]["category_label"], "内部往来款")
        self.assertEqual(suggestions["txn-transfer-out"]["rule_code"], "internal_transfer_pair")
        self.assertIn("txn-transfer-in", suggestions["txn-transfer-out"]["reason"])
        self.assertNotEqual(suggestions["txn-transfer-out"]["category_code"], "fee")
        self.assertNotEqual(suggestions["txn-transfer-in"]["category_code"], "salary")

    def test_internal_transfer_rejects_ineligible_pairs(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-same-account-out",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220001",
                    "debit_amount": "1000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "txn-same-account-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220001",
                    "debit_amount": "",
                    "credit_amount": "1000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
                {
                    "id": "txn-amount-out",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220003",
                    "debit_amount": "2000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "txn-amount-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220004",
                    "debit_amount": "",
                    "credit_amount": "2001.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
                {
                    "id": "txn-window-out",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220005",
                    "debit_amount": "3000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "txn-window-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220006",
                    "debit_amount": "",
                    "credit_amount": "3000.00",
                    "pay_receive_time": "2026-03-12 10:00:01",
                },
                {
                    "id": "txn-single-sided",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220007",
                    "debit_amount": "4000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
            ]
        )

        self.assertEqual(suggestions, {})

    def test_internal_transfer_multi_solution_does_not_guess(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-transfer-out-a",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220001",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:00:00",
                },
                {
                    "id": "txn-transfer-out-b",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司建设银行账户",
                    "account_no": "62220003",
                    "debit_amount": "13000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-03-10 10:05:00",
                },
                {
                    "id": "txn-transfer-in-a",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220002",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "pay_receive_time": "2026-03-10 12:00:00",
                },
                {
                    "id": "txn-transfer-in-b",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司工商银行账户",
                    "account_no": "62220004",
                    "debit_amount": "",
                    "credit_amount": "13000.00",
                    "pay_receive_time": "2026-03-10 12:05:00",
                },
            ]
        )

        self.assertEqual(suggestions, {})

    def test_effective_category_ignores_manual_history_when_auto_exists(self) -> None:
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

        self.assertEqual(effective["effective_category_code"], "fee")
        self.assertEqual(effective["effective_category_label"], "手续费")
        self.assertEqual(effective["effective_category_source"], "auto")

    def test_effective_category_ignores_manual_clear_when_auto_exists(self) -> None:
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

        self.assertEqual(effective["effective_category_code"], "fee")
        self.assertEqual(effective["effective_category_label"], "手续费")
        self.assertEqual(effective["effective_category_path"], ["自动识别", "手续费"])
        self.assertEqual(effective["effective_category_source"], "auto")


if __name__ == "__main__":
    unittest.main()
