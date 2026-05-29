import unittest
import json
from pathlib import Path

from fin_ops_platform.services.bank_transaction_category_service import (
    BankAutoTagRulesValidationError,
    BankTransactionCategoryConflictError,
    BankTransactionCategoryValidationError,
    BANK_TRANSACTION_CATEGORY_LABELS,
    BankTransactionCategoryService,
)


class BankTransactionCategoryServiceTests(unittest.TestCase):
    def test_parse_normalized_bank_flow_fixture_into_file_rules(self) -> None:
        fixture_path = Path("fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json")
        source = json.loads(fixture_path.read_text(encoding="utf-8"))

        parsed = BankTransactionCategoryService.parse_auto_tag_rule_file_source(source)

        self.assertEqual(parsed["source"]["source_name"], "银行流水标签ui2.numbers")
        self.assertEqual(parsed["source"]["source_version"], "2026-05-29-ui2-normalized")
        self.assertTrue(parsed["source"]["source_hash"].startswith("sha256:"))
        self.assertEqual(parsed["source"]["field_mapping_version"], "2026-05-29-bank-auto-tag-field-mapping-v1")
        self.assertEqual(len(parsed["active_rules"]), 37)
        self.assertNotIn("内部往来款", [rule["output_primary_label"] for rule in parsed["active_rules"]])

        fee = next(
            rule
            for rule in parsed["active_rules"]
            if rule["output_primary_label"] == "费用" and rule["output_sub_label"] == "手续费"
        )
        self.assertEqual(
            fee["rules"]["match_fields"],
            ["purpose_text", "summary_text", "note_text", "detail_text"],
        )
        self.assertEqual(
            fee["rules"]["contains_any"],
            ["手续费", "短信服务费", "收费", "网银证书服务费", "企业网银服务费"],
        )

        housing_fund = next(
            rule
            for rule in parsed["active_rules"]
            if rule["output_primary_label"] == "薪资社保福利" and rule["output_sub_label"] == "公积金"
        )
        self.assertEqual(housing_fund["rules"]["match_fields"], ["counterparty_name"])

        management = next(
            rule
            for rule in parsed["active_rules"]
            if rule["output_primary_label"] == "费用" and rule["output_sub_label"] == "管理"
        )
        self.assertEqual(
            management["rules"]["none_of"],
            ["保证金", "投标保证金", "履约保证金", "押金", "往来款", "暂借款", "还暂借款"],
        )

    def test_parse_worksheet_rows_maps_headers_aliases_and_ignores_oa_type(self) -> None:
        rows = [
            ["流水类型", "分类（一级）", "银行流水标签（贰级）", "选择查询的项", "包含", "必须同时包含", "精准命中", "不包含字样", "优先级", "OA中的类型"],
            ["支出或收入", "内部往来款", "系统说明", "", "", "", "", "", "1", "忽略"],
            ["支出", "费用", "手续费", "用途/交易用途、摘要、备注/附言/客户附言", "手续费、短信服务费", "网银\n服务费", "账户管理费，证书费", "退款；退回", "2", "忽略"],
            ["支出", "薪资社保福利", "公积金", "对方户", "昆明市住房公积金管理中心", "", "", "", "2", "忽略"],
        ]

        parsed = BankTransactionCategoryService.parse_auto_tag_rule_file_source(
            rows,
            source_name="worksheet.xlsx",
            source_version="test-version",
        )

        self.assertEqual(len(parsed["active_rules"]), 2)
        fee = parsed["active_rules"][0]
        self.assertEqual(fee["output_primary_label"], "费用")
        self.assertEqual(fee["output_sub_label"], "手续费")
        self.assertEqual(fee["rules"]["contains_any"], ["手续费", "短信服务费"])
        self.assertEqual(fee["rules"]["contains_all"], ["网银", "服务费"])
        self.assertEqual(fee["rules"]["exact_any"], ["账户管理费", "证书费"])
        self.assertEqual(fee["rules"]["none_of"], ["退款", "退回"])
        self.assertEqual(parsed["active_rules"][1]["rules"]["match_fields"], ["counterparty_name"])

    def test_parse_file_rules_rejects_unknown_query_field_with_structured_error(self) -> None:
        rows = [
            ["流水类型", "分类（一级）", "银行流水标签（贰级）", "选择查询的项", "包含", "必须同时包含", "精准命重", "不包含字样"],
            ["支出", "费用", "手续费", "未知字段", "手续费", "", "", ""],
        ]

        with self.assertRaises(BankAutoTagRulesValidationError) as context:
            BankTransactionCategoryService.parse_auto_tag_rule_file_source(rows)

        self.assertEqual(context.exception.error_code, "invalid_bank_auto_tag_rule_file")
        self.assertIn(
            {"path": "rows[1].选择查询的项", "message": "未知的查询字段：未知字段"},
            context.exception.field_errors,
        )

    def test_compare_file_rule_sources_ignores_header_alias_and_oa_type_only(self) -> None:
        ui2_rows = [
            ["流水类型", "分类（一级）", "银行流水标签（贰级）", "选择查询的项", "包含", "必须同时包含", "精准命重", "不包含字样", "OA中的类型"],
            ["支出", "费用", "手续费", "用途/交易用途、摘要、备注/附言/客户附言", "手续费", "", "账户管理费", "", "旧OA"],
        ]
        xlsx_rows = [
            ["流水类型", "主标签", "子标签", "选择查询的项", "包含", "必须同时包含", "精准命中", "不包含字样", "OA中的类型"],
            ["支出", "费用", "手续费", "用途/交易用途、摘要、备注/附言/客户附言", "手续费", "", "账户管理费", "", "新OA"],
        ]

        self.assertEqual(
            BankTransactionCategoryService.compare_auto_tag_rule_file_sources(ui2_rows, xlsx_rows),
            {"matched": True, "diffs": []},
        )

        changed_rows = [list(row) for row in xlsx_rows]
        changed_rows[1][4] = "账户费"
        with self.assertRaises(BankAutoTagRulesValidationError) as context:
            BankTransactionCategoryService.compare_auto_tag_rule_file_sources(ui2_rows, changed_rows)

        self.assertEqual(context.exception.error_code, "bank_auto_tag_rule_file_diff")
        self.assertEqual(context.exception.field_errors[0]["path"], "rules[0]")

    def test_file_replacement_reuses_matching_label_code_archives_external_rules_and_audits_source(self) -> None:
        fixture_path = Path("fixtures/bank_auto_tag_rules/bank_flow_tag_rules_ui2.normalized.json")
        source = json.loads(fixture_path.read_text(encoding="utf-8"))
        previous = BankTransactionCategoryService.from_snapshot(None).tag_dictionary_payload()
        previous["version"] = 8
        previous["definitions"].append(
            {
                "code": "custom_old_office",
                "label": "办公",
                "path": ["自动识别", "办公"],
                "source": "custom",
                "status": "active",
                "direction": "any",
                "account_scope": {"type": "any", "values": []},
                "output_primary_label": "费用",
                "output_sub_label": "办公",
                "rules": {
                    "match_fields": ["all_text"],
                    "exact_any": [],
                    "contains_any": ["旧办公"],
                    "contains_all": [],
                    "none_of": [],
                    "regex_any": [],
                },
                "rule_code": "custom_old_office",
            }
        )

        result = BankTransactionCategoryService.normalize_auto_tag_rules_file_replacement(
            source,
            previous_tag_dictionary=previous,
        )

        payload = BankTransactionCategoryService.auto_tag_rules_payload(result["tag_dictionary"])
        office = next(rule for rule in payload["active_rules"] if rule["output_primary_label"] == "费用" and rule["output_sub_label"] == "办公")
        self.assertEqual(office["code"], "custom_old_office")
        self.assertEqual(office["rules"]["contains_any"], ["办公", "办公用品", "资料费", "打印复印费", "复印费", "招标文件", "电信", "通信费", "电话费"])
        self.assertIn("salary", [rule["code"] for rule in payload["archived_rules"]])
        self.assertEqual(result["old_version"], 8)
        self.assertEqual(result["new_version"], 9)
        self.assertEqual(result["changes"]["source"]["source_name"], "银行流水标签ui2.numbers")
        self.assertEqual(result["changes"]["source"]["field_mapping_version"], "2026-05-29-bank-auto-tag-field-mapping-v1")
        self.assertIn("custom_old_office", result["changes"]["reused_codes"])
        self.assertIn("salary", result["changes"]["archived_codes"])
        self.assertTrue(result["changes"]["added_codes"])

    def test_apply_updates_persists_category_with_version_and_audit_fields(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1"},
        )

        result = service.apply_updates(
            [
                {
                    "transaction_id": "txn-1",
                    "category_code": "borrow_in_company_pending_repayment",
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_transaction_ids"], ["txn-1"])
        self.assertEqual(result["updated_categories"][0]["category_label"], "公司暂借款：待还款")
        self.assertEqual(result["updated_categories"][0]["category_path"], ["借入", "公司往来款", "待还款"])
        self.assertEqual(result["updated_categories"][0]["version"], 1)
        stored = service.get("txn-1")
        self.assertEqual(stored["category_code"], "borrow_in_company_pending_repayment")
        self.assertEqual(stored["category_label"], "公司暂借款：待还款")
        self.assertEqual(stored["category_path"], ["借入", "公司往来款", "待还款"])
        self.assertEqual(stored["category_version"], 1)
        self.assertEqual(stored["updated_by"], "YNSYLP005")

    def test_apply_updates_rejects_invalid_category_code_atomically(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1", "txn-2"},
        )

        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_updates(
                [
                    {"transaction_id": "txn-1", "category_code": "borrow_out_personal_lent", "expected_version": 0},
                    {"transaction_id": "txn-2", "category_code": "unsupported", "expected_version": 0},
                ],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "invalid_category_code")
        self.assertEqual(service.snapshot()["categories"], {})

    def test_auto_business_category_codes_are_valid_manual_choices(self) -> None:
        self.assertEqual(BANK_TRANSACTION_CATEGORY_LABELS["fee"], "手续费")
        self.assertEqual(BANK_TRANSACTION_CATEGORY_LABELS["salary"], "工资")
        self.assertEqual(BANK_TRANSACTION_CATEGORY_LABELS["holiday_bonus"], "过节费")
        self.assertEqual(BANK_TRANSACTION_CATEGORY_LABELS["bonus"], "奖金")

        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-fee", "txn-salary"},
        )

        result = service.apply_updates(
            [
                {"transaction_id": "txn-fee", "category_code": "fee", "expected_version": 0},
                {"transaction_id": "txn-salary", "category_code": "salary", "expected_version": 0},
            ],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_label"], "手续费")
        self.assertEqual(result["updated_categories"][0]["category_path"], ["自动识别", "手续费"])
        self.assertEqual(result["updated_categories"][1]["category_label"], "工资")
        self.assertEqual(result["updated_categories"][1]["category_path"], ["自动识别", "工资"])

    def test_system_categories_are_exposed_as_seed_tag_definitions(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(None)

        payload = service.tag_dictionary_payload()
        definitions_by_code = {
            definition["code"]: definition
            for definition in payload["definitions"]
        }

        self.assertEqual(payload["version"], 1)
        self.assertEqual(
            definitions_by_code["borrow_in_company_pending_repayment"],
            {
                "code": "borrow_in_company_pending_repayment",
                "label": "公司暂借款：待还款",
                "path": ["借入", "公司往来款", "待还款"],
                "source": "system",
                "status": "active",
            },
        )
        self.assertEqual(definitions_by_code["fee"]["source"], "system")
        self.assertEqual(definitions_by_code["fee"]["status"], "active")
        self.assertEqual(definitions_by_code["fee"]["path"], ["自动识别", "手续费"])
        self.assertEqual(definitions_by_code["fee"]["rules"]["match_fields"], ["counterparty_name", "summary_text", "note_text"])
        self.assertEqual(definitions_by_code["fee"]["rules"]["contains"], ["手续费", "短信服务费"])
        self.assertNotIn("rules", definitions_by_code["internal_transfer"])
        self.assertIn("internal_transfer", definitions_by_code)

    def test_auto_tag_rules_payload_exposes_production_rule_fields_without_hidden_system_controls(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(None)

        payload = service.auto_tag_rules_payload(service.tag_dictionary_payload())
        external_turnover = next(rule for rule in payload["active_rules"] if rule["code"] == "external_turnover")

        self.assertEqual(external_turnover["direction"], "any")
        self.assertEqual(external_turnover["account_scope"], {"type": "any", "values": []})
        self.assertEqual(external_turnover["sort_order"], len(payload["active_rules"]) + 1)
        self.assertIn("contains_any", external_turnover["rules"])
        self.assertIn("contains_all", external_turnover["rules"])
        self.assertIn("none_of", external_turnover["rules"])
        self.assertIn("regex_any", external_turnover["rules"])
        self.assertNotIn("stop_on_match", external_turnover)
        self.assertNotIn("review_required", external_turnover)
        self.assertNotIn("route_to", external_turnover)
        self.assertNotIn("audit", external_turnover)

    def test_auto_tag_rules_update_validates_identity_labels_and_rules(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(None)
        current = service.auto_tag_rules_payload(service.tag_dictionary_payload())
        salary = next(rule for rule in current["active_rules"] if rule["code"] == "salary")

        with self.assertRaisesRegex(ValueError, "自动标签规则校验失败"):
            BankTransactionCategoryService.normalize_auto_tag_rules_update(
                {
                    "expected_version": current["version"],
                    "active_rules": [
                        {
                            **salary,
                            "label": "人员薪酬",
                            "rules": {
                                "match_fields": [],
                                "exact": [],
                                "contains": [],
                                "excludes": ["社保代扣"],
                            },
                        }
                    ],
                    "archived_rules": [],
                },
                previous_tag_dictionary=service.tag_dictionary_payload(),
            )

        next_active = [
            (
                {
                    **rule,
                    "label": "人员薪酬",
                    "rules": {
                        "match_fields": ["all_text"],
                        "exact": [],
                        "contains": ["工资"],
                        "excludes": [],
                    },
                }
                if rule["code"] == "salary"
                else rule
            )
            for rule in current["active_rules"]
        ]
        result = BankTransactionCategoryService.normalize_auto_tag_rules_update(
            {
                "expected_version": current["version"],
                "active_rules": next_active,
                "archived_rules": [],
            },
            previous_tag_dictionary=service.tag_dictionary_payload(),
        )

        updated = BankTransactionCategoryService.auto_tag_rules_payload(result["tag_dictionary"])
        updated_salary = next(rule for rule in updated["active_rules"] if rule["code"] == "salary")
        self.assertEqual(updated_salary["code"], "salary")
        self.assertEqual(updated_salary["label"], "人员薪酬")
        self.assertEqual(result["changes"]["renamed_tags"][0]["code"], "salary")

    def test_auto_tag_rules_update_accepts_direction_account_scope_combined_conditions_and_regex(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(None)
        current = service.auto_tag_rules_payload(service.tag_dictionary_payload())
        fee = next(rule for rule in current["active_rules"] if rule["code"] == "fee")
        next_active = [
            (
                {
                    **rule,
                    "direction": "expense",
                    "account_scope": {"type": "bank", "values": ["建行"]},
                    "rules": {
                        "match_fields": ["summary_text", "note_text"],
                        "exact_any": [],
                        "contains_any": ["手续费"],
                        "contains_all": ["对公人民币转账", "跨行"],
                        "none_of": ["退手续费"],
                        "regex_any": ["短信\\s*服务费"],
                    },
                }
                if rule["code"] == "fee"
                else rule
            )
            for rule in current["active_rules"]
        ]

        result = BankTransactionCategoryService.normalize_auto_tag_rules_update(
            {
                "expected_version": current["version"],
                "active_rules": next_active,
                "archived_rules": [],
            },
            previous_tag_dictionary=service.tag_dictionary_payload(),
        )

        updated = BankTransactionCategoryService.auto_tag_rules_payload(result["tag_dictionary"])
        updated_fee = next(rule for rule in updated["active_rules"] if rule["code"] == "fee")
        self.assertEqual(updated_fee["direction"], "expense")
        self.assertEqual(updated_fee["account_scope"], {"type": "bank", "values": ["建行"]})
        self.assertEqual(updated_fee["rules"]["contains_any"], ["手续费"])
        self.assertEqual(updated_fee["rules"]["contains_all"], ["对公人民币转账", "跨行"])
        self.assertEqual(updated_fee["rules"]["none_of"], ["退手续费"])
        self.assertEqual(updated_fee["rules"]["regex_any"], ["短信\\s*服务费"])

    def test_auto_tag_rules_update_allows_duplicate_archived_labels(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(None)
        previous = service.tag_dictionary_payload()
        previous_tag_dictionary = {
            "version": 14,
            "definitions": [
                *previous["definitions"],
                {
                    "code": "custom_online_cert_fee_old",
                    "label": "网银证书服务费",
                    "path": ["自动识别", "网银证书服务费"],
                    "source": "custom",
                    "status": "archived",
                    "direction": "any",
                    "account_scope": {"type": "any", "values": []},
                    "rules": {
                        "match_fields": ["all_text"],
                        "exact_any": ["网银证书服务费"],
                        "contains_any": [],
                        "contains_all": [],
                        "none_of": [],
                        "regex_any": [],
                    },
                    "rule_code": "custom_online_cert_fee_old",
                },
                {
                    "code": "custom_online_cert_fee_new",
                    "label": "网银证书服务费",
                    "path": ["自动识别", "网银证书服务费"],
                    "source": "custom",
                    "status": "active",
                    "priority": 90,
                    "direction": "any",
                    "account_scope": {"type": "any", "values": []},
                    "rules": {
                        "match_fields": ["all_text"],
                        "exact_any": [],
                        "contains_any": [],
                        "contains_all": ["网银", "服务费"],
                        "none_of": [],
                        "regex_any": [],
                    },
                    "rule_code": "custom_online_cert_fee_new",
                },
            ],
        }
        current = BankTransactionCategoryService.auto_tag_rules_payload(previous_tag_dictionary)
        target = next(rule for rule in current["active_rules"] if rule["code"] == "custom_online_cert_fee_new")

        result = BankTransactionCategoryService.normalize_auto_tag_rules_update(
            {
                "expected_version": current["version"],
                "active_rules": [
                    rule
                    for rule in current["active_rules"]
                    if rule["code"] != "custom_online_cert_fee_new"
                ],
                "archived_rules": [*current["archived_rules"], target],
            },
            previous_tag_dictionary=previous_tag_dictionary,
        )

        updated = BankTransactionCategoryService.auto_tag_rules_payload(result["tag_dictionary"])
        archived_online_cert_fee_codes = [
            rule["code"]
            for rule in updated["archived_rules"]
            if rule["label"] == "网银证书服务费"
        ]
        self.assertEqual(
            archived_online_cert_fee_codes,
            ["custom_online_cert_fee_new", "custom_online_cert_fee_old"],
        )

    def test_configured_custom_tag_is_valid_manual_choice(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-custom",
        )
        service.configure_tag_dictionary(
            {
                "version": 3,
                "definitions": [
                    {
                        "code": "custom_meal_without_invoice",
                        "label": "餐费无需发票",
                        "path": ["自定义", "餐费"],
                        "source": "custom",
                        "status": "active",
                    }
                ],
            }
        )

        result = service.apply_updates(
            [
                {
                    "transaction_id": "txn-custom",
                    "category_code": "custom_meal_without_invoice",
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_label"], "餐费无需发票")
        self.assertEqual(result["updated_categories"][0]["category_path"], ["自定义", "餐费"])
        self.assertEqual(service.get("txn-custom")["category_code"], "custom_meal_without_invoice")

    def test_archived_tag_remains_resolvable_but_cannot_be_new_manual_choice(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            {
                "categories": {
                    "txn-archived": {
                        "transaction_id": "txn-archived",
                        "category_code": "custom_archived_tag",
                        "source": "manual",
                        "version": 2,
                    }
                }
            },
            transaction_exists=lambda transaction_id: transaction_id in {"txn-archived", "txn-new"},
        )
        service.configure_tag_dictionary(
            {
                "version": 4,
                "definitions": [
                    {
                        "code": "custom_archived_tag",
                        "label": "历史停用标签",
                        "path": ["历史"],
                        "source": "custom",
                        "status": "archived",
                    }
                ],
            }
        )

        self.assertEqual(service.get("txn-archived")["category_label"], "历史停用标签")
        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_updates(
                [
                    {
                        "transaction_id": "txn-new",
                        "category_code": "custom_archived_tag",
                        "expected_version": 0,
                    }
                ],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "archived_category_code")

    def test_apply_updates_rejects_unknown_transaction(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )

        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_updates(
                [{"transaction_id": "missing-txn", "category_code": "business_warranty_pending_collection", "expected_version": 0}],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "unknown_transaction_id")

    def test_apply_updates_rejects_expected_version_conflict(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "business_bid_bond_pending_collection", "expected_version": 0}],
            actor="YNSYLP005",
        )

        with self.assertRaises(BankTransactionCategoryConflictError) as context:
            service.apply_updates(
                [{"transaction_id": "txn-1", "category_code": "borrow_in_bank_repaid", "expected_version": 0}],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "category_version_conflict")
        self.assertEqual(service.get("txn-1")["category_code"], "business_bid_bond_pending_collection")

    def test_clear_category_keeps_next_version_and_counts_uncategorized(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1", "txn-2"},
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "borrow_out_company_pending_collection", "expected_version": 0}],
            actor="YNSYLP005",
        )

        result = service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": None, "expected_version": 1}],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_code"], None)
        self.assertEqual(result["updated_categories"][0]["category_label"], None)
        self.assertEqual(result["updated_categories"][0]["version"], 2)
        self.assertEqual(service.get("txn-1")["category_version"], 2)
        counts = service.category_counts(["txn-1", "txn-2"])
        self.assertEqual(counts["borrow_out_company_pending_collection"], 0)
        self.assertEqual(counts["uncategorized"], 2)

    def test_clear_category_without_existing_record_persists_manual_clear_override(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-uncategorized",
        )

        result = service.apply_updates(
            [{"transaction_id": "txn-uncategorized", "category_code": None, "expected_version": 0}],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_code"], None)
        self.assertEqual(result["updated_categories"][0]["category_label"], None)
        self.assertEqual(result["updated_categories"][0]["version"], 1)
        stored = service.get("txn-uncategorized")
        self.assertEqual(stored["category_code"], None)
        self.assertEqual(stored["source"], "manual")
        self.assertEqual(stored["category_version"], 1)

    def test_snapshot_round_trips_categories(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )
        service.apply_updates(
            [{"transaction_id": "txn-1", "category_code": "borrow_in_personal_repaid", "expected_version": 0}],
            actor="YNSYLP005",
        )

        restored = BankTransactionCategoryService.from_snapshot(
            service.snapshot(),
            transaction_exists=lambda transaction_id: transaction_id == "txn-1",
        )

        self.assertEqual(restored.get("txn-1")["category_label"], "个人暂借款：已还款")
        self.assertEqual(restored.get("txn-1")["category_path"], ["借入", "个人往来款", "已还款"])
        self.assertEqual(restored.get("txn-1")["category_version"], 1)

    def test_apply_turnover_updates_allows_only_turnover_leaf_tags_atomically(self) -> None:
        service = BankTransactionCategoryService.from_snapshot(
            None,
            transaction_exists=lambda transaction_id: transaction_id in {"txn-1", "txn-2"},
        )

        with self.assertRaises(BankTransactionCategoryValidationError) as context:
            service.apply_turnover_updates(
                [
                    {"transaction_id": "txn-1", "category_code": "borrow_in_personal_pending_repayment", "expected_version": 0},
                    {"transaction_id": "txn-2", "category_code": "fee", "expected_version": 0},
                ],
                actor="YNSYLP005",
            )

        self.assertEqual(context.exception.error_code, "invalid_turnover_category_code")
        self.assertEqual(service.get("txn-1")["category_code"], None)
        self.assertEqual(service.get("txn-2")["category_code"], None)

        result = service.apply_turnover_updates(
            [
                {
                    "transaction_id": "txn-1",
                    "category_code": "borrow_in_personal_pending_repayment",
                    "expected_version": 0,
                }
            ],
            actor="YNSYLP005",
        )

        self.assertEqual(result["updated_categories"][0]["category_code"], "borrow_in_personal_pending_repayment")
        self.assertEqual(service.get("txn-1")["source"], "turnover_ledger")


if __name__ == "__main__":
    unittest.main()
