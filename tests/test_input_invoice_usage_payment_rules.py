from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import Mock

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    PaymentStatusEvaluationContext,
    InputInvoiceUsagePaymentRulesValidationError,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_role_sync_service import OAUserSummary, OARoleSyncExecutionError
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService

from tests.app_test_support import build_local_state_application as build_application
from tests.test_pending_invoice_service import FakeCanonicalRelationReader, FakeOAProjection


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class InputInvoiceUsagePaymentRulesTests(unittest.TestCase):
    def test_directory_merges_whitespace_and_same_name_users_excludes_disabled(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            directory = Mock()
            directory.list_active_users.return_value = [
                OAUserSummary("A", "黄  亮", True), OAUserSummary("B", "黄 亮", True),
                OAUserSummary("C", "刘树刚", True), OAUserSummary("D", "刘树刚", True),
                OAUserSummary("YNSYLP005", "刘涵静", True), OAUserSummary("X", "停用人员", False),
            ]
            app._app_settings_service._oa_role_sync_service = directory
            response = app.handle_request("GET", "/api/input-invoice-usage/payment-status-rules")
            self.assertEqual(response.status_code, 200)
            payload = json.loads(response.body)
            self.assertEqual(payload["applicantOptions"], ["刘树刚", "刘涵静", "黄亮"])
            self.assertNotIn("applicantName", payload["rules"][0]["conditions"])
            directory.list_active_users.side_effect = OARoleSyncExecutionError("unavailable")
            failure = app.handle_request("GET", "/api/input-invoice-usage/payment-status-rules")
            self.assertEqual(failure.status_code, 503)
            self.assertEqual(json.loads(failure.body)["error"], "oa_applicant_directory_unavailable")

    def test_multiple_applicants_match_any_and_invalid_lists_fail(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=app._state_store)
            rule = {"id": "multi", "statusCode": "offset", "label": "冲", "priority": 1, "enabled": True,
                    "conditions": {"hasOa": True, "applicantNames": ["黄 亮", "李四", "黄  亮"]}}
            saved = provider.update_payment_status_rules({"expectedVersion": 1, "idempotencyKey": "multi", "rules": [rule]}, actor_id="tester")
            self.assertEqual(saved["rules"][0]["conditions"]["applicantNames"], ["李四", "黄亮"])
            for name in ["李四", "黄  亮", "黄\u3000亮", "黄\u200b亮"]:
                self.assertEqual(provider.evaluate(PaymentStatusEvaluationContext(True, False, name, False, False))["code"], "offset")
            self.assertEqual(provider.evaluate(PaymentStatusEvaluationContext(True, False, "王五", False, False))["code"], "pending")
            for invalid in [[], "李四", [None], ["  "]]:
                rule["conditions"]["applicantNames"] = invalid
                with self.assertRaises(InputInvoiceUsagePaymentRulesValidationError):
                    provider.update_payment_status_rules({"expectedVersion": 2, "idempotencyKey": "bad", "rules": [rule]}, actor_id="tester")

    def test_new_disabled_applicant_rejected_but_existing_condition_preserved(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = app._app_settings_service
            directory = Mock()
            directory.list_active_users.return_value = []
            service._oa_role_sync_service = directory
            current = service.get_input_invoice_usage_payment_status_rules_payload()
            rules = current["rules"]
            rules[0]["label"] = "现金往来保留"
            service.update_input_invoice_usage_payment_status_rules({"expectedVersion": 1, "idempotencyKey": "keep", "rules": rules}, actor_id="tester")
            directory.list_active_users.assert_not_called()
            rules[0]["conditions"]["applicantNames"].append("停用人员")
            with self.assertRaises(AppSettingsValidationError) as caught:
                service.update_input_invoice_usage_payment_status_rules({"expectedVersion": 2, "idempotencyKey": "bad", "rules": rules}, actor_id="tester")
            self.assertEqual(caught.exception.error_code, "inactive_payment_rule_applicant")
            self.assertEqual(service.get_input_invoice_usage_payment_status_rules_payload()["version"], 2)

    def test_default_rules_are_editable_versioned_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)

        self.assertEqual(payload["version"], 1)
        self.assertFalse(payload["readOnly"])
        self.assertTrue(payload["permissions"]["canSave"])
        self.assertEqual([rule["id"] for rule in payload["rules"]][:2], ["cash_turnover_chen_xiuyun", "paid_full_match"])
        self.assertNotIn("pendingDirections", payload)
        self.assertEqual(len(payload["rules"]), 6)
        self.assertEqual(
            payload["sourceMetadata"]["settingsKey"],
            "input_invoice_usage_payment_status_rules",
        )

    def test_put_rules_handler_saves_and_enqueues_refresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            queue = QueueRecorder()
            app._runtime_repositories = type("RuntimeRepositories", (), {"queue_repository": queue})()
            current = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            next_rules = [dict(rule) for rule in current["rules"]]
            next_rules[1]["label"] = "已支付"

            response = app.handle_request(
                "PUT",
                "/api/input-invoice-usage/payment-status-rules",
                body=json.dumps(
                    {
                        "expectedVersion": current["version"],
                        "idempotencyKey": "rules-save-api",
                        "rules": next_rules,
                    }
                ),
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(queue.refreshes, [])

    def test_rules_update_persists_audits_and_returns_invalidation_event(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            current = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            next_rules = [dict(rule) for rule in current["rules"]]
            next_rules[1]["label"] = "已支付"

            updated = app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                {
                    "expectedVersion": current["version"],
                    "idempotencyKey": "rules-save-1",
                    "rules": next_rules,
                },
                actor_id="finance-owner",
            )
            reloaded = build_application(
                data_dir=data_dir,
            )._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)

        self.assertEqual(updated["version"], 2)
        self.assertEqual(reloaded["rules"][1]["label"], "已支付")
        audit = app._audit_service.as_dicts()[-1]
        self.assertEqual(audit["actor_id"], "finance-owner")
        self.assertEqual(audit["action"], "input_invoice_usage_payment_status_rules_updated")
        self.assertEqual(audit["metadata"]["old_version"], 1)
        self.assertEqual(audit["metadata"]["new_version"], 2)

    def test_rules_update_validates_version_idempotency_and_supported_constraints(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            next_rules = [dict(rule) for rule in current["rules"]]
            next_rules[0]["description"] = "陈秀云 OA + 流水 + 完全匹配"
            request = {
                "expectedVersion": current["version"],
                "idempotencyKey": "rules-save-2",
                "rules": next_rules,
            }

            first = app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                request,
                actor_id="finance-owner",
            )
            repeated = app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                request,
                actor_id="finance-owner",
            )
            with self.assertRaises(AppSettingsValidationError) as stale_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        **request,
                        "idempotencyKey": "rules-save-stale",
                    },
                    actor_id="finance-owner",
                )
            invalid_rules = [dict(rule) for rule in current["rules"]]
            invalid_rules[0]["conditions"] = {"hasOa": "false"}
            with self.assertRaises(AppSettingsValidationError) as invalid_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        "expectedVersion": first["version"],
                        "idempotencyKey": "rules-save-invalid",
                        "rules": invalid_rules,
                    },
                    actor_id="finance-owner",
                )
            missing_applicant_rules = [dict(rule) for rule in current["rules"]]
            missing_applicant_rules[2]["conditions"] = {
                "hasOa": False,
                "hasBank": False,
                "invoiceOaAmountMatched": True,
            }
            with self.assertRaises(AppSettingsValidationError) as missing_applicant_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        "expectedVersion": first["version"],
                        "idempotencyKey": "rules-save-missing-applicant",
                        "rules": missing_applicant_rules,
                    },
                    actor_id="finance-owner",
                )
            with self.assertRaises(AppSettingsValidationError) as idempotency_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        **request,
                        "rules": [*next_rules[:-1], {**next_rules[-1], "label": "人工待处理"}],
                    },
                    actor_id="finance-owner",
                )

        self.assertEqual(repeated, first)
        self.assertEqual(stale_context.exception.error_code, "input_invoice_usage_payment_rules_version_conflict")
        self.assertEqual(invalid_context.exception.error_code, "invalid_input_invoice_usage_payment_rule_condition")
        self.assertEqual(missing_applicant_context.exception.error_code, "contradictory_input_invoice_usage_payment_rule_conditions")
        self.assertEqual(idempotency_context.exception.error_code, "input_invoice_usage_payment_rules_idempotency_conflict")

    def test_rules_update_persists_exact_boolean_conditions(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            current = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            next_rules = json.loads(json.dumps(current["rules"]))
            next_rules[1]["conditions"] = {"hasOa": True, "hasBank": True}

            updated = app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                {
                    "expectedVersion": current["version"],
                    "idempotencyKey": "rules-save-exact-conditions",
                    "rules": next_rules,
                },
                actor_id="finance-owner",
            )
            reloaded_app = build_application(data_dir=data_dir)
            reloaded = reloaded_app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=reloaded_app._state_store)
            status = provider.evaluate(
                PaymentStatusEvaluationContext(
                    has_oa=True,
                    has_bank=True,
                    applicant_name="李四",
                    fully_matched=False,
                    invoice_oa_amount_matched=False,
                )
            )

        self.assertNotIn("fullyMatched", updated["rules"][1]["conditions"])
        self.assertNotIn("fullyMatched", reloaded["rules"][1]["conditions"])
        self.assertEqual(status["code"], "pending")

    def test_query_service_uses_injected_rules_provider_for_payload_and_row_status(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            current = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)
            next_rules = [dict(rule) for rule in current["rules"]]
            next_rules[1]["label"] = "已支付"
            app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                {
                    "expectedVersion": current["version"],
                    "idempotencyKey": "rules-save-query",
                    "rules": next_rules,
                },
                actor_id="finance-owner",
            )
            provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=app._state_store)
            invoice = self._invoice("inv-paid", "9002", "供应商", total_with_tax="80.00")
            bank = self._bank_transaction("bank-paid", "80.00")
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-paid",
                row_ids=[invoice.id, "oa-paid", bank.id],
                row_types=["invoice", "oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            oa_projection = FakeOAProjection([self._oa("oa-paid", "李四", "80.00")])
            service = InputInvoiceUsageQueryService(
                import_service=ImportNormalizationService(existing_invoices=[invoice], existing_transactions=[bank]),
                relation_reader=FakeCanonicalRelationReader.from_pair_service(
                    pair_service=pair_service,
                    transactions=[bank],
                    invoices=[invoice],
                    oa_projection=oa_projection,
                ),
                oa_projection=oa_projection,
                payment_rules_provider=provider,
            )

            row = service.list_rows()["rows"][0]
            rules_payload = service.payment_status_rules()

        self.assertEqual(row["paymentStatus"]["code"], "paid")
        self.assertEqual(row["paymentStatus"]["label"], "已支付")
        self.assertEqual(rules_payload["rules"][1]["label"], "已支付")

    def test_add_edit_delete_and_empty_rules_persist_without_defaults(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=app._state_store)
            current = provider.payment_status_rules_payload()
            rule = {
                "id": "custom-applicant", "statusCode": "offset", "label": "冲",
                "priority": 1, "enabled": True,
                "conditions": {"hasOa": True, "hasBank": False, "applicantNames": ["李四"]},
                "reason": "must not persist", "description": "must not persist",
            }
            saved = provider.update_payment_status_rules(
                {"expectedVersion": current["version"], "idempotencyKey": "add", "rules": [rule]}, actor_id="tester",
            )
            self.assertEqual([r["id"] for r in saved["rules"]], ["custom-applicant"])
            self.assertIn("李四", saved["rules"][0]["reason"])
            raw = app._state_store.load_app_settings()["input_invoice_usage_payment_status_rules"]["rules"][0]
            self.assertNotIn("reason", raw)
            self.assertNotIn("description", raw)
            rule["conditions"]["applicantNames"] = ["王五"]
            edited = provider.update_payment_status_rules(
                {"expectedVersion": saved["version"], "idempotencyKey": "edit", "rules": [rule]}, actor_id="tester",
            )
            self.assertEqual(provider.evaluate(PaymentStatusEvaluationContext(True, False, "王五", False, False))["code"], "offset")
            provider.update_payment_status_rules(
                {"expectedVersion": edited["version"], "idempotencyKey": "delete", "rules": []}, actor_id="tester",
            )
            self.assertEqual(provider.payment_status_rules_payload()["rules"], [])
            result = provider.evaluate(PaymentStatusEvaluationContext(True, False, "王五", False, False))
            self.assertEqual(result["label"], "待核对")
            self.assertEqual(result["matchedRuleId"], "")

    def test_priority_disabled_and_amount_guard_are_explicit(self) -> None:
        from fin_ops_platform.services.input_invoice_usage_payment_rules import evaluate_payment_status
        rules = [
            {"id": "later", "statusCode": "waiting_payment", "label": "待付款", "priority": 2,
             "enabled": True, "conditions": {"hasOa": True}},
            {"id": "first", "statusCode": "offset", "label": "冲", "priority": 1,
             "enabled": True, "conditions": {"hasOa": True}},
        ]
        settings = {"version": 1, "rules": rules}
        context = PaymentStatusEvaluationContext(True, False, "", False, False)
        self.assertEqual(evaluate_payment_status(settings, context)["matchedRuleId"], "first")
        rules[1]["enabled"] = False
        self.assertEqual(evaluate_payment_status(settings, context)["matchedRuleId"], "later")
        unmatched = evaluate_payment_status(settings, PaymentStatusEvaluationContext(True, True, "", False, True))
        self.assertEqual(unmatched["code"], "pending")
        self.assertEqual(unmatched["matchedRuleId"], "")

    def test_invalid_rule_values_fail_without_restoring_defaults(self) -> None:
        from fin_ops_platform.services.input_invoice_usage_payment_rules import (
            InputInvoiceUsagePaymentRulesValidationError,
            normalize_payment_status_rules_settings,
        )
        for invalid in ({"version": 1}, {"version": 1, "rules": None}, "bad"):
            with self.subTest(invalid=invalid), self.assertRaises(InputInvoiceUsagePaymentRulesValidationError):
                normalize_payment_status_rules_settings(invalid)
        rule = {"id": "r", "statusCode": "paid", "label": "已付款", "priority": 1,
                "enabled": True, "conditions": {"hasOa": True}}
        for patch in ({"enabled": "false"}, {"priority": True}, {"priority": 1.2},
                      {"statusCode": "unknown"}, {"conditions": {}}, {"conditions": {"fallback": True}}):
            with self.subTest(patch=patch), self.assertRaises(InputInvoiceUsagePaymentRulesValidationError):
                normalize_payment_status_rules_settings({"version": 1, "rules": [{**rule, **patch}]})
        for duplicate in ([rule, rule], [rule, {**rule, "id": "other"}]):
            with self.assertRaises(InputInvoiceUsagePaymentRulesValidationError):
                normalize_payment_status_rules_settings({"version": 1, "rules": duplicate})

    @staticmethod
    def _invoice(invoice_id: str, invoice_no: str, seller_name: str, *, total_with_tax: str) -> Invoice:
        counterparty = Counterparty(
            id=f"cp-{invoice_id}",
            name=seller_name,
            normalized_name=seller_name,
            counterparty_type="supplier",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.INPUT,
            invoice_no=invoice_no,
            counterparty=counterparty,
            amount=Decimal(total_with_tax),
            signed_amount=Decimal(total_with_tax),
            invoice_date="2026-05-20",
            seller_name=seller_name,
            buyer_name="云南溯源科技有限公司",
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal("0.00"),
            total_with_tax=Decimal(total_with_tax),
            taxable_item_name="服务费",
        )

    @staticmethod
    def _bank_transaction(transaction_id: str, amount: str) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="供应商",
            amount=Decimal(amount),
            signed_amount=-Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            imported_bank_name="中国银行",
            imported_bank_last4="1234",
        )

    @staticmethod
    def _oa(oa_id: str, applicant: str, amount: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="进行中",
            case_id=f"OA-{oa_id}",
            applicant=applicant,
            project_name="项目名称",
            apply_type="报销",
            amount=amount,
            counterparty_name="供应商",
            reason="费用报销",
            relation_code="in_progress",
            relation_label="进行中",
            relation_tone="success",
        )


if __name__ == "__main__":
    unittest.main()
