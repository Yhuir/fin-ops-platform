from __future__ import annotations

import unittest
from unittest.mock import patch

from fin_ops_platform.services.bank_transaction_auto_category_service import BankTransactionAutoCategoryService, resolve_effective_category
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService


class BankTransactionAutoCategoryServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.service = BankTransactionAutoCategoryService()

    def test_bulk_suggestions_copy_rules_once_without_deepcopying_rows(self) -> None:
        class NoDeepcopy:
            def __deepcopy__(self, _memo):
                raise AssertionError("bank rows must not be recursively copied")

        category_service = BankTransactionCategoryService()
        service = BankTransactionAutoCategoryService(category_service=category_service)
        with patch.object(
            category_service,
            "tag_dictionary_payload",
            wraps=category_service.tag_dictionary_payload,
        ) as payload:
            suggestions = service.suggest_for_rows(
                [
                    {"id": "txn-1", "summary": "网银手续费", "raw_payload": NoDeepcopy()},
                    {"id": "txn-2", "summary": "4月工资", "raw_payload": NoDeepcopy()},
                ]
            )

        self.assertEqual(payload.call_count, 1)
        self.assertEqual(suggestions["txn-1"]["category_code"], "fee")
        self.assertEqual(suggestions["txn-2"]["category_code"], "salary")

    def test_bulk_suggestions_normalize_each_row_value_once_across_rules(self) -> None:
        rows = [
            {
                "id": f"txn-{index}",
                "counterparty_name": f"供应商 {index}",
                "summary": "普通转账",
                "remark": "项目费用",
            }
            for index in range(100)
        ]

        with patch.object(
            BankTransactionAutoCategoryService,
            "_normalize_match_text",
            wraps=BankTransactionAutoCategoryService._normalize_match_text,
        ) as normalizer:
            self.service.suggest_for_rows(rows)

        self.assertLess(normalizer.call_count, 500)

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
        self.assertEqual(suggestion["category_primary_label"], "费用")
        self.assertEqual(suggestion["category_sub_label"], "手续费")
        self.assertEqual(suggestion["category_label_path"], ["费用", "手续费"])
        self.assertEqual(suggestion["category_path"], ["自动识别", "手续费"])
        self.assertEqual(suggestion["source"], "auto")
        self.assertEqual(suggestion["rule_code"], "fee_text_keyword")
        self.assertEqual(suggestion["confidence"], "high")
        self.assertEqual(suggestion["rule_version"], "bank-auto-tag-rules:1")
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

    def test_uses_configured_label_semantic_fields_excludes_priority_and_evidence(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 12,
                "definitions": [
                    {
                        "code": "salary",
                        "label": "人员薪酬",
                        "path": ["自动识别", "人员薪酬"],
                        "source": "system",
                        "status": "active",
                        "priority": 10,
                        "rules": {
                            "match_fields": ["note_text"],
                            "exact": [],
                            "contains": ["工资"],
                            "excludes": ["社保代扣"],
                        },
                    },
                    {
                        "code": "bonus",
                        "label": "奖金",
                        "path": ["自动识别", "奖金"],
                        "source": "system",
                        "status": "active",
                        "priority": 20,
                        "rules": {
                            "match_fields": ["all_text"],
                            "exact": ["工资"],
                            "contains": ["奖金"],
                            "excludes": [],
                        },
                    },
                ],
            }
        )

        suggestions = self.service.suggest_for_rows(
            [
                {"id": "txn-salary-note", "customer_note": "4月工资", "summary": "普通转账"},
                {"id": "txn-excluded", "customer_note": "工资 社保代扣", "summary": "奖金"},
                {"id": "txn-exact", "summary": "工资"},
            ]
        )

        salary = suggestions["txn-salary-note"]
        self.assertEqual(salary["category_code"], "salary")
        self.assertEqual(salary["category_label"], "人员薪酬")
        evidence = salary["auto_category_evidence"]
        self.assertEqual(evidence["tag_code"], "salary")
        self.assertEqual(evidence["tag_label"], "人员薪酬")
        self.assertEqual(evidence["rule_code"], "salary_text_keyword")
        self.assertEqual(evidence["rule_version"], "bank-auto-tag-rules:12")
        self.assertEqual(evidence["condition_type"], "contains_any")
        self.assertEqual(evidence["semantic_field"], "note_text")
        self.assertEqual(evidence["semantic_field_label"], "备注/附言/客户附言")
        self.assertEqual(evidence["raw_field_key"], "customer_note")
        self.assertIsNone(evidence["raw_field_label"])
        self.assertEqual(evidence["matched_text"], "工资")
        self.assertEqual(suggestions["txn-excluded"]["category_code"], "bonus")
        self.assertEqual(suggestions["txn-exact"]["category_code"], "bonus")

    def test_rule_engine_supports_direction_combined_conditions_regex_and_normalized_text(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 13,
                "definitions": [
                    {
                        "code": "fee",
                        "label": "手续费",
                        "path": ["自动识别", "手续费"],
                        "source": "system",
                        "status": "active",
                        "priority": 10,
                        "direction": "expense",
                        "rules": {
                            "match_fields": ["summary_text", "note_text"],
                            "exact_any": [],
                            "contains_any": ["手续费"],
                            "contains_all": ["对公人民币转账", "跨行"],
                            "none_of": ["退手续费"],
                            "regex_any": ["短信\\s*服务费"],
                        },
                    }
                ],
            }
        )

        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-normalized-fee",
                    "debit_amount": "9.00",
                    "summary": " 手 续 费 ",
                    "remark": "对公人民币转账、汇款（含退汇）-跨行异地",
                },
                {
                    "id": "txn-regex-fee",
                    "debit_amount": "10.00",
                    "summary": "短信　服务费",
                    "remark": "对公人民币转账-跨行",
                },
                {
                    "id": "txn-income-not-fee",
                    "credit_amount": "9.00",
                    "summary": "手续费",
                    "remark": "对公人民币转账-跨行",
                },
                {
                    "id": "txn-excluded-fee",
                    "debit_amount": "9.00",
                    "summary": "手续费",
                    "remark": "退手续费 对公人民币转账-跨行",
                },
            ]
        )

        self.assertEqual(suggestions["txn-normalized-fee"]["category_code"], "fee")
        self.assertEqual(suggestions["txn-normalized-fee"]["auto_category_evidence"]["condition_type"], "contains_any")
        self.assertEqual(suggestions["txn-regex-fee"]["category_code"], "fee")
        self.assertEqual(suggestions["txn-regex-fee"]["auto_category_evidence"]["condition_type"], "regex_any")
        self.assertNotIn("txn-income-not-fee", suggestions)
        self.assertNotIn("txn-excluded-fee", suggestions)

    def test_contains_all_can_be_the_only_positive_condition(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 14,
                "definitions": [
                    {
                        "code": "online_banking_certificate_fee",
                        "label": "网银证书服务费",
                        "path": ["自动识别", "网银证书服务费"],
                        "source": "custom",
                        "status": "active",
                        "priority": 10,
                        "direction": "any",
                        "rules": {
                            "match_fields": ["all_text"],
                            "exact_any": [],
                            "contains_any": [],
                            "contains_all": ["网银", "服务费"],
                            "none_of": [],
                            "regex_any": [],
                        },
                    }
                ],
            }
        )

        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-online-banking-certificate-fee",
                    "debit_amount": "100.00",
                    "summary": "网银证书服务费",
                },
                {
                    "id": "txn-only-online-banking",
                    "debit_amount": "100.00",
                    "summary": "网银证书",
                },
            ]
        )

        suggestion = suggestions["txn-online-banking-certificate-fee"]
        self.assertEqual(suggestion["category_code"], "online_banking_certificate_fee")
        self.assertEqual(suggestion["auto_category_evidence"]["condition_type"], "contains_all")
        self.assertEqual(suggestion["auto_category_evidence"]["matched_text"], "网银、服务费")
        self.assertNotIn("txn-only-online-banking", suggestions)

    def test_single_ordinary_rule_match_marks_auto_matched_and_candidate_code(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 15,
                "definitions": [
                    {
                        "code": "custom_office",
                        "label": "办公",
                        "path": ["自动识别", "办公"],
                        "source": "custom",
                        "status": "active",
                        "priority": 10,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "exact_any": [],
                            "contains_any": ["办公用品"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    }
                ],
            }
        )

        suggestion = self.service.suggest_for_rows([{"id": "txn-office", "summary": "购买办公用品"}])["txn-office"]

        self.assertEqual(suggestion["category_resolution_status"], "auto_matched")
        self.assertEqual(suggestion["category_code"], "custom_office")
        self.assertEqual(suggestion["auto_category_code"], "custom_office")
        self.assertEqual(suggestion["auto_candidate_category_codes"], ["custom_office"])
        self.assertEqual(suggestion["auto_candidate_categories"][0]["category_code"], "custom_office")

    def test_multiple_ordinary_rule_matches_require_confirmation_in_rule_order(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 16,
                "definitions": [
                    {
                        "code": "custom_project_insurance",
                        "label": "保证金保险",
                        "path": ["自动识别", "保证金保险"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 2,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "exact_any": [],
                            "contains_any": ["保险"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                    {
                        "code": "custom_staff_insurance",
                        "label": "人员保险",
                        "path": ["自动识别", "人员保险"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 1,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "exact_any": [],
                            "contains_any": ["保险费"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                ],
            }
        )

        suggestion = self.service.suggest_for_rows([{"id": "txn-insurance", "summary": "保险费"}])["txn-insurance"]

        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        self.assertIsNone(suggestion["category_code"])
        self.assertIsNone(suggestion["auto_category_code"])
        self.assertEqual(
            suggestion["auto_candidate_category_codes"],
            ["custom_staff_insurance", "custom_project_insurance"],
        )
        self.assertEqual(
            [item["category_code"] for item in suggestion["auto_candidate_categories"]],
            ["custom_staff_insurance", "custom_project_insurance"],
        )
        self.assertEqual(suggestion["rule_version"], "bank-auto-tag-rules:16")

    def test_higher_priority_match_stops_lower_priority_candidates(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 17,
                "definitions": [
                    {
                        "code": "custom_staff_insurance",
                        "label": "人员保险",
                        "path": ["自动识别", "人员保险"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 1,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "exact_any": [],
                            "contains_any": ["保险费"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                    {
                        "code": "custom_project_insurance",
                        "label": "保证金保险",
                        "path": ["自动识别", "保证金保险"],
                        "source": "custom",
                        "status": "active",
                        "priority": 3,
                        "sort_order": 2,
                        "rules": {
                            "match_fields": ["summary_text"],
                            "exact_any": [],
                            "contains_any": ["保险"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                ],
            }
        )

        suggestion = self.service.suggest_for_rows([{"id": "txn-insurance", "summary": "保险费"}])["txn-insurance"]

        self.assertEqual(suggestion["category_resolution_status"], "auto_matched")
        self.assertEqual(suggestion["category_code"], "custom_staff_insurance")
        self.assertEqual(suggestion["auto_candidate_category_codes"], ["custom_staff_insurance"])

    def test_external_turnover_candidate_runs_after_specific_business_rules(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-tax-refund",
                    "credit_amount": "472.71",
                    "summary": "电子退库[纳税人编码=",
                    "note": "电子退库[纳税人编码=915300007194052520]",
                },
                {
                    "id": "txn-bank-loan",
                    "debit_amount": "5833.33",
                    "summary": "贷款扣款",
                    "purpose": "批量还款",
                },
                {
                    "id": "txn-bid-bond",
                    "debit_amount": "30000.00",
                    "remark": "投标保证金（招标代理机构项目编号：TC260H00H）",
                },
            ]
        )

        self.assertEqual(suggestions["txn-bank-loan"]["category_code"], "external_turnover")
        self.assertEqual(suggestions["txn-bank-loan"]["auto_category_evidence"]["route_to"], "turnover_ledger_pending")
        self.assertTrue(suggestions["txn-bank-loan"]["auto_category_evidence"]["review_required"])
        self.assertEqual(suggestions["txn-bid-bond"]["category_code"], "external_turnover")
        self.assertNotEqual(suggestions.get("txn-tax-refund", {}).get("category_code"), "external_turnover")

    def test_external_turnover_rule_with_legacy_third_label_still_requires_confirmation(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 21,
                "definitions": [
                    {
                        "code": "custom_external_borrow_out_company",
                        "label": "借出款",
                        "path": ["自动识别", "借出款"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "direction": "expense",
                        "output_primary_label": "外部往来款付款",
                        "output_sub_label": "借出款",
                        "output_third_label": "公司往来",
                        "turnover_action_type": "pending_collection",
                        "rules": {
                            "match_fields": ["summary_text", "purpose_text"],
                            "exact_any": [],
                            "contains_any": ["借出周转款"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    }
                ],
            }
        )

        suggestion = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-external-company-out",
                    "debit_amount": "8000.00",
                    "summary": "借出周转款",
                }
            ]
        )["txn-external-company-out"]

        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        self.assertIsNone(suggestion["category_code"])
        self.assertIsNone(suggestion["auto_category_code"])
        candidates = suggestion["auto_candidate_categories"]
        self.assertEqual([candidate["category_code"] for candidate in candidates], ["custom_external_borrow_out_company"] * 4)
        self.assertEqual(
            [candidate["category_third_label"] for candidate in candidates],
            ["个人往来", "公司往来", "银行往来", "业务往来"],
        )
        self.assertEqual(suggestion["turnover_action_type"], "pending_collection")
        self.assertEqual({candidate["turnover_action_type"] for candidate in candidates}, {"pending_collection"})

    def test_external_turnover_rule_without_third_label_requires_confirmation_candidates(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 22,
                "definitions": [
                    {
                        "code": "custom_external_borrow_out_missing_third",
                        "label": "借出款",
                        "path": ["自动识别", "借出款"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "direction": "expense",
                        "output_primary_label": "外部往来款付款",
                        "output_sub_label": "借出款",
                        "turnover_action_type": "pending_collection",
                        "rules": {
                            "match_fields": ["summary_text", "purpose_text"],
                            "exact_any": [],
                            "contains_any": ["借出周转款"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    }
                ],
            }
        )

        suggestion = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-external-missing-third",
                    "debit_amount": "8000.00",
                    "summary": "借出周转款",
                }
            ]
        )["txn-external-missing-third"]

        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        self.assertIsNone(suggestion["category_code"])
        self.assertIsNone(suggestion["auto_category_code"])
        candidates = suggestion["auto_candidate_categories"]
        self.assertEqual([candidate["category_code"] for candidate in candidates], ["custom_external_borrow_out_missing_third"] * 4)
        self.assertEqual(
            [candidate["category_third_label"] for candidate in candidates],
            ["个人往来", "公司往来", "银行往来", "业务往来"],
        )
        self.assertEqual(
            [candidate["category_label_path"] for candidate in candidates],
            [
                ["外部往来款付款", "借出款", "个人往来"],
                ["外部往来款付款", "借出款", "公司往来"],
                ["外部往来款付款", "借出款", "银行往来"],
                ["外部往来款付款", "借出款", "业务往来"],
            ],
        )
        self.assertEqual({candidate["turnover_action_type"] for candidate in candidates}, {"pending_collection"})

    def test_multiple_external_turnover_rule_matches_expand_each_sub_label_to_third_level_candidates(self) -> None:
        self.service.configure_tag_dictionary(
            {
                "version": 23,
                "definitions": [
                    {
                        "code": "external_borrow_out_pending_collection",
                        "label": "借出款",
                        "path": ["自动识别", "借出款"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 1,
                        "direction": "expense",
                        "output_primary_label": "外部往来款付款",
                        "output_sub_label": "借出款",
                        "turnover_action_type": "pending_collection",
                        "rules": {
                            "match_fields": ["summary_text", "purpose_text"],
                            "exact_any": [],
                            "contains_any": ["共同外部往来测试词"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                    {
                        "code": "external_borrow_in_repaid",
                        "label": "归还借款",
                        "path": ["自动识别", "归还借款"],
                        "source": "custom",
                        "status": "active",
                        "priority": 2,
                        "sort_order": 2,
                        "direction": "expense",
                        "output_primary_label": "外部往来款付款",
                        "output_sub_label": "归还借款",
                        "turnover_action_type": "repaid",
                        "rules": {
                            "match_fields": ["summary_text", "purpose_text"],
                            "exact_any": [],
                            "contains_any": ["共同外部往来测试词"],
                            "contains_all": [],
                            "none_of": [],
                            "regex_any": [],
                        },
                    },
                ],
            }
        )

        suggestion = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-external-multi-sub",
                    "debit_amount": "240000.00",
                    "summary": "共同外部往来测试词",
                }
            ]
        )["txn-external-multi-sub"]

        self.assertEqual(suggestion["category_resolution_status"], "needs_confirmation")
        candidates = suggestion["auto_candidate_categories"]
        self.assertEqual(len(candidates), 8)
        self.assertEqual(
            [
                (candidate["category_code"], candidate["category_sub_label"], candidate["category_third_label"])
                for candidate in candidates
            ],
            [
                ("external_borrow_out_pending_collection", "借出款", "个人往来"),
                ("external_borrow_out_pending_collection", "借出款", "公司往来"),
                ("external_borrow_out_pending_collection", "借出款", "银行往来"),
                ("external_borrow_out_pending_collection", "借出款", "业务往来"),
                ("external_borrow_in_repaid", "归还借款", "个人往来"),
                ("external_borrow_in_repaid", "归还借款", "公司往来"),
                ("external_borrow_in_repaid", "归还借款", "银行往来"),
                ("external_borrow_in_repaid", "归还借款", "业务往来"),
            ],
        )

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
        self.assertEqual(suggestions["txn-transfer-out"]["category_resolution_status"], "internal_transfer")
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

    def test_internal_transfer_explicit_self_account_rows_pair_when_amount_repeats(self) -> None:
        suggestions = self.service.suggest_for_rows(
            [
                {
                    "id": "txn-self-account-out-a",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "民生银行",
                    "account_last4": "9486",
                    "debit_amount": "500000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-02-01 10:00:00",
                    "summary": "电子转账",
                    "purpose": "本公司帐户",
                },
                {
                    "id": "txn-self-account-in-a",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "debit_amount": "",
                    "credit_amount": "500000.00",
                    "pay_receive_time": "2026-02-01 10:01:00",
                    "summary": "本公司帐户",
                },
                {
                    "id": "txn-self-account-out-b",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "民生银行",
                    "account_last4": "9486",
                    "debit_amount": "500000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-02-01 10:05:00",
                    "summary": "电子转账",
                    "purpose": "本公司帐户",
                },
                {
                    "id": "txn-self-account-in-b",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "debit_amount": "",
                    "credit_amount": "500000.00",
                    "pay_receive_time": "2026-02-01 10:06:00",
                    "summary": "本公司帐户",
                },
                {
                    "id": "txn-self-tax-out",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "民生银行",
                    "account_last4": "9486",
                    "debit_amount": "4000.00",
                    "credit_amount": "",
                    "pay_receive_time": "2026-04-16 11:09:13",
                    "summary": "本公司税户",
                    "purpose": "本公司税户",
                },
                {
                    "id": "txn-self-tax-in",
                    "account_name": "云南溯源科技有限公司",
                    "counterparty_name": "云南溯源科技有限公司",
                    "bank_name": "工商银行",
                    "account_last4": "6386",
                    "debit_amount": "",
                    "credit_amount": "4000.00",
                    "pay_receive_time": "2026-04-16 11:09:16",
                    "summary": "本公司税户",
                    "purpose": "本公司税户",
                },
            ]
        )

        self.assertEqual(set(suggestions), {
            "txn-self-account-out-a",
            "txn-self-account-in-a",
            "txn-self-account-out-b",
            "txn-self-account-in-b",
            "txn-self-tax-out",
            "txn-self-tax-in",
        })
        self.assertEqual(
            suggestions["txn-self-account-out-a"]["counterpart_id"],
            "txn-self-account-in-a",
        )
        self.assertEqual(
            suggestions["txn-self-account-out-b"]["counterpart_id"],
            "txn-self-account-in-b",
        )
        self.assertEqual(suggestions["txn-self-tax-out"]["counterpart_id"], "txn-self-tax-in")
        self.assertEqual({item["category_code"] for item in suggestions.values()}, {"internal_transfer"})

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
        self.assertEqual(effective["effective_category_primary_label"], "费用")
        self.assertEqual(effective["effective_category_sub_label"], "手续费")
        self.assertEqual(effective["effective_category_label_path"], ["费用", "手续费"])
        self.assertEqual(effective["effective_category_source"], "auto")

    def test_effective_category_uses_manual_category_when_auto_is_missing(self) -> None:
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-manual",
        )
        category_service.assign_manual_category(
            transaction_id="txn-manual",
            category_code="salary",
            actor="YNSYLP005",
        )

        effective = resolve_effective_category(category_service.get("txn-manual"), None)

        self.assertEqual(effective["effective_category_code"], "salary")
        self.assertEqual(effective["effective_category_label"], "工资")
        self.assertEqual(effective["effective_category_primary_label"], "工资")
        self.assertEqual(effective["effective_category_sub_label"], None)
        self.assertEqual(effective["effective_category_label_path"], ["工资"])
        self.assertEqual(effective["effective_category_source"], "manual")

    def test_effective_category_preserves_confirmed_external_turnover_third_label(self) -> None:
        category_service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-external-confirmed",
        )
        category_service.confirm_auto_category(
            transaction_id="txn-external-confirmed",
            category_code="external_turnover",
            category_third_label="公司往来",
            category_label_path=["外部往来款付款", "借出款", "公司往来"],
            turnover_action_type="pending_collection",
            turnover_family="company",
            candidate_category_codes=["external_turnover"],
            rule_version="bank-auto-tag-rules:22",
            actor="YNSYLP005",
        )

        effective = resolve_effective_category(category_service.get("txn-external-confirmed"), None)

        self.assertEqual(effective["effective_category_code"], "external_turnover")
        self.assertEqual(effective["effective_category_label"], "借出款")
        self.assertEqual(effective["effective_category_primary_label"], "外部往来款付款")
        self.assertEqual(effective["effective_category_sub_label"], "借出款")
        self.assertEqual(effective["effective_category_third_label"], "公司往来")
        self.assertEqual(effective["effective_category_label_path"], ["外部往来款付款", "借出款", "公司往来"])
        self.assertEqual(effective["turnover_action_type"], "pending_collection")
        self.assertEqual(effective["turnover_family"], "company")

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
