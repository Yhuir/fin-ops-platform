from __future__ import annotations

import json
import unittest
from concurrent.futures import ThreadPoolExecutor
from copy import deepcopy
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from fin_ops_platform.postgres import migrate
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    SETTINGS_KEY,
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    InputInvoiceUsagePaymentRulesValidationError,
    PaymentStatusEvaluationContext,
    evaluate_payment_status,
    normalize_payment_status_rules_settings,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.invoice_usage_collection_query import _input_payment_status_case
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from postgres_test_utils import apply_test_migrations, require_postgres_test_database_url, truncate_test_database


class PaymentRulesPostgresTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database_url = require_postgres_test_database_url()
        apply_test_migrations(cls.database_url)

    def setUp(self):
        truncate_test_database(self.database_url)
        self.temp = TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.connection = PostgresConnection(PostgresSettings(database_url=self.database_url, pool_enabled=False))
        self.addCleanup(self.connection.close)
        self.store = PostgresStateStore(data_dir=Path(self.temp.name), connection=self.connection)
        self.provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=self.store, transaction_factory=self.connection.transaction)

    def request(self, key):
        current = self.provider.payment_status_rules_payload()
        return {"expectedVersion": current["version"], "idempotencyKey": key, "rules": deepcopy(current["rules"])}

    def test_sql_and_python_classification_agree_for_custom_rules_and_amount_states(self):
        custom = {"version": 1, "rules": [
            {"id": "custom", "statusCode": "custom_paid", "parentStatus": "paid", "label": "自定义付款", "priority": 1,
             "enabled": True, "conditions": {"hasBank": True, "paymentComparison": "less"}},
            {"id": "offset", "statusCode": "custom_offset", "parentStatus": "unpaid", "label": "自定义冲账", "priority": 2,
             "enabled": True, "conditions": {"hasOa": True, "hasBank": False}},
        ]}
        sign_rules = {"version": 1, "rules": [
            {"id": sign, "statusCode": "custom_" + sign, "label": sign, "priority": index,
             "enabled": True, "conditions": {"invoiceNetSign": sign}} for index, sign in enumerate(("positive", "zero", "negative"), 1)]}
        no_hidden = {"version": 1, "rules": [{"id": "no-hidden", "statusCode": "paid", "label": "原标签", "priority": 1,
                                             "enabled": True, "conditions": {"hasOa": False}}]}
        inclusive_rules = [{"version": 1, "rules": [{"id": "inclusive", "statusCode": "custom_inclusive", "label": "边界", "priority": 1,
                             "enabled": True, "conditions": conditions}]} for conditions in (
                                 {"paymentComparison": "less_equal"}, {"paymentComparison": "greater_equal"},
                                 {"invoiceNetSign": "nonnegative"}, {"invoiceNetSign": "nonpositive"})]
        for raw in (None, custom, sign_rules, no_hidden, {"version": 1, "rules": []}, *inclusive_rules):
            settings = normalize_payment_status_rules_settings(raw)
            expression, params = _input_payment_status_case(settings)
            for has_oa, has_bank in ((False, False), (True, False), (False, True), (True, True)):
                for comparison in (("equal", "less", "greater", "invalid") if has_bank else ("invalid",)):
                    for sign in ("positive", "zero", "negative", None):
                        context = PaymentStatusEvaluationContext(has_oa, has_bank, "陈秀云", comparison == "equal", True, comparison, sign)
                        with self.subTest(custom=raw is not None, context=context):
                            row = self.connection.fetch_one(
                                "with facts as (select %s::boolean has_oa_relation, %s::boolean has_bank_relation, "
                                "%s::text oa_applicant, %s::boolean fully_matched, %s::boolean invoice_oa_amount_matched, "
                                "%s::text payment_comparison, %s::text invoice_net_sign) select " + expression + " code from facts",
                                (has_oa, has_bank, context.applicant_name, context.fully_matched, True, comparison, sign, *params),
                            )
                            self.assertEqual(row["code"], evaluate_payment_status(settings, context)["code"])

    def test_explicit_migration_preserves_rules_and_materializes_old_branches_once(self):
        rules = deepcopy(self.request("legacy-explicit")["rules"][:6])
        rules[0]["enabled"] = False
        rules[0]["priority"] = 20
        rules[1]["conditions"].pop("paymentComparison")
        rules[1]["label"] = "原付款名称"
        self.store.save_app_settings({"keep": {"x": 1}, SETTINGS_KEY: {"version": 7, "rules": rules, "idempotencyRecords": {"old": {}}}})
        sql = Path("backend/src/fin_ops_platform/postgres/migrations/0188_input_invoice_payment_rules_explicit.sql").read_text()
        migrate.run_psql(self.database_url, sql=sql)
        saved = self.store.load_app_settings()
        self.assertEqual(saved["keep"], {"x": 1})
        policy = saved[SETTINGS_KEY]
        self.assertEqual(policy["version"], 8)
        self.assertEqual(policy["idempotencyRecords"], {})
        self.assertEqual(len(policy["rules"]), 10)
        for before, after in zip(rules, policy["rules"][:6]):
            for key in ("id", "statusCode", "label", "priority", "enabled"):
                self.assertEqual(after[key], before[key])
        self.assertEqual(policy["rules"][1]["conditions"]["paymentComparison"], "equal")
        self.assertTrue(all(rule["priority"] > 20 for rule in policy["rules"][6:]))
        self.assertEqual(next(rule for rule in policy["rules"][6:] if rule["statusCode"] == "paid")["label"], "原付款名称")
        request = self.request("clear-all-explicit")
        request["rules"] = []
        self.provider.update_payment_status_rules(request, actor_id="tester")
        self.assertEqual(self.provider.payment_status_rules_payload()["rules"], [])
        self.assertEqual(self.provider.evaluate(PaymentStatusEvaluationContext(True, True, "", True, True, "equal"))["code"], "unclassified")

    def test_custom_category_save_rename_delete_and_invalid_conditions_are_atomic(self):
        request = self.request("custom-category")
        request["rules"] = [{"id": "rule-one", "statusCode": "custom_supplier", "parentStatus": "paid",
                             "label": "供应商付款", "priority": 1, "enabled": True,
                             "conditions": {"hasBank": True, "paymentComparison": "greater_equal", "invoiceNetSign": "nonpositive"}}]
        saved = self.provider.update_payment_status_rules(request, actor_id="tester")
        self.assertNotIn("parentStatus", saved["rules"][0])
        invalid = self.request("invalid-parent")
        invalid["rules"][0]["conditions"]["hasBank"] = "unknown"
        with self.assertRaises(InputInvoiceUsagePaymentRulesValidationError):
            self.provider.update_payment_status_rules(invalid, actor_id="tester")
        self.assertEqual(self.provider.payment_status_rules_payload(), saved)
        rename = self.request("rename-category")
        rename["rules"][0]["label"] = "供应商付款新名称"
        renamed = self.provider.update_payment_status_rules(rename, actor_id="tester")
        self.assertEqual(renamed["rules"][0]["statusCode"], "custom_supplier")
        delete = self.request("delete-category")
        delete["rules"] = []
        self.assertEqual(self.provider.update_payment_status_rules(delete, actor_id="tester")["rules"], [])

    def test_applicant_migration_preserves_other_settings_and_is_repeatable(self):
        rules = self.request("legacy")["rules"]
        for rule in rules:
            names = rule["conditions"].pop("applicantNames", None)
            if names:
                rule["conditions"]["applicantName"] = "刘树刚不付" if rule["id"] == "offset_liu_shugang_no_pay" else names[0]
        self.store.save_app_settings({"unrelated": "keep", SETTINGS_KEY: {"version": 4, "rules": rules, "idempotencyRecords": {"old": {}}}})
        sql = Path("backend/src/fin_ops_platform/postgres/migrations/0183_payment_rule_applicant_names.sql").read_text()
        migrate.run_psql(self.database_url, sql=sql)
        saved = self.store.load_app_settings()
        self.assertEqual(saved["unrelated"], "keep")
        self.assertEqual(saved[SETTINGS_KEY]["version"], 5)
        self.assertEqual(saved[SETTINGS_KEY]["rules"][3]["conditions"]["applicantNames"], ["刘树刚"])
        self.assertTrue(all("applicantName" not in rule["conditions"] for rule in saved[SETTINGS_KEY]["rules"]))
        self.assertEqual(saved[SETTINGS_KEY]["idempotencyRecords"], {})
        migrate.run_psql(self.database_url, sql=sql)
        self.assertEqual(self.store.load_app_settings(), saved)
        self.assertEqual(self.provider.payment_status_rules_payload()["version"], 5)

    def test_concurrent_cas_idempotency_and_unrelated_settings(self):
        self.store.save_app_settings({"unrelated_test_field": {"value": "keep"}})
        requests = [self.request("a"), self.request("b")]
        def save(request):
            try:
                return self.provider.update_payment_status_rules(request, actor_id="tester")
            except InputInvoiceUsagePaymentRulesValidationError as exc:
                return exc.error_code
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(save, requests))
        winner = next(index for index, result in enumerate(results) if isinstance(result, dict))
        self.assertEqual(results[1 - winner], "input_invoice_usage_payment_rules_version_conflict")
        self.assertEqual(save(requests[winner]), results[winner])
        self.assertEqual(self.store.load_app_settings()["unrelated_test_field"], {"value": "keep"})
        count = self.connection.fetch_one("select count(*) n from audit.events where action = %s", ("input_invoice_usage_payment_status_rules_updated",))
        self.assertEqual(count["n"], 1)

    def test_audit_failure_rolls_back_settings(self):
        before = self.provider.payment_status_rules_payload()
        with patch("fin_ops_platform.services.postgres_repositories.operations_audit.PostgresOperationsAuditRepository.append_operation_event", side_effect=RuntimeError("audit unavailable")):
            with self.assertRaisesRegex(RuntimeError, "audit unavailable"):
                self.provider.update_payment_status_rules(self.request("rollback"), actor_id="tester")
        self.assertEqual(self.provider.payment_status_rules_payload(), before)

    def test_migration_preserves_custom_rules_and_removes_dead_configuration(self):
        current = self.request("migration")
        legacy_rules = current["rules"][:6]
        legacy_rules[0]["label"] = "自定义现金"
        legacy_rules[0]["enabled"] = False
        legacy_rules[5]["label"] = "待付款"
        for index, rule in enumerate(legacy_rules[2:5], 2):
            rule["statusCode"] = ("offset_zhou_jieying", "offset_liu_shugang_no_pay", "offset_wei_dailian")[index - 2]
        legacy_rules.append({"id": "pending_default", "statusCode": "pending", "conditions": {"fallback": True}})
        self.store.save_app_settings({SETTINGS_KEY: {"version": 8, "rules": legacy_rules,
            "pendingDirections": [{"code": "pending", "label": "旧文案"}], "idempotencyRecords": {"old": {}}}})
        migration_sql = Path("backend/src/fin_ops_platform/postgres/migrations/0182_input_invoice_payment_rules_editable.sql").read_text()
        migrate.run_psql(self.database_url, sql=migration_sql)
        saved = self.store.load_app_settings()[SETTINGS_KEY]
        self.assertEqual(saved["version"], 9)
        self.assertEqual(len(saved["rules"]), 6)
        self.assertEqual(saved["rules"][0]["label"], "自定义现金")
        self.assertFalse(saved["rules"][0]["enabled"])
        self.assertEqual(saved["rules"][5]["label"], "未关联流水")
        self.assertEqual({rule["statusCode"] for rule in saved["rules"][2:5]}, {"offset"})
        self.assertNotIn("pendingDirections", saved)
        self.assertTrue(all("reason" not in rule and "description" not in rule for rule in saved["rules"]))
        self.assertEqual(saved["idempotencyRecords"], {})
        self.assertEqual(self.provider.payment_status_rules_payload()["version"], 9)

    def test_migration_preserves_custom_waiting_label(self):
        rules = self.request("custom-waiting")["rules"][:6]
        rules[5]["label"] = "财务核验中"
        self.store.save_app_settings({SETTINGS_KEY: {"version": 8, "rules": rules}})
        sql = Path("backend/src/fin_ops_platform/postgres/migrations/0182_input_invoice_payment_rules_editable.sql").read_text()
        migrate.run_psql(self.database_url, sql=sql)
        self.assertEqual(self.provider.payment_status_rules_payload()["rules"][5]["label"], "财务核验中")

    def test_migration_rejects_conflicting_labels_without_changing_settings(self):
        rules = self.request("conflict")["rules"]
        rules[2]["label"] = "不同分类名"
        policy = {"version": 8, "rules": rules, "pendingDirections": []}
        self.store.save_app_settings({SETTINGS_KEY: policy})
        sql = Path("backend/src/fin_ops_platform/postgres/migrations/0182_input_invoice_payment_rules_editable.sql").read_text()
        with self.assertRaises(Exception):
            migrate.run_psql(self.database_url, sql=sql)
        self.assertEqual(json.dumps(self.store.load_app_settings()[SETTINGS_KEY], sort_keys=True), json.dumps(policy, sort_keys=True))
