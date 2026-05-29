import unittest

from fin_ops_platform.services.bank_transaction_category_service import (
    BankTransactionCategoryConflictError,
    BankTransactionCategoryValidationError,
    BANK_TRANSACTION_CATEGORY_LABELS,
    BankTransactionCategoryService,
)


class BankTransactionCategoryServiceTests(unittest.TestCase):
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
        self.assertEqual(external_turnover["sort_order"], len(payload["active_rules"]))
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
