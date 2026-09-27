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
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
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
        legacy_rules = current["rules"]
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
        rules = self.request("custom-waiting")["rules"]
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
