from __future__ import annotations

import json
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.app_settings_service import AppSettingsValidationError
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    PaymentStatusEvaluationContext,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService

from tests.app_test_support import build_local_state_application as build_application
from tests.test_pending_invoice_service import FakeOAProjection, FakeWorkbenchRelationFacade


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
    def test_default_rules_are_editable_versioned_payload(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            payload = app._app_settings_service.get_input_invoice_usage_payment_status_rules_payload(can_save=True)

        self.assertEqual(payload["version"], 1)
        self.assertFalse(payload["readOnly"])
        self.assertTrue(payload["permissions"]["canSave"])
        self.assertEqual([rule["id"] for rule in payload["rules"]][:2], ["cash_turnover_chen_xiuyun", "paid_full_match"])
        self.assertEqual(payload["pendingDirections"][0], {"code": "pending", "label": "待处理"})
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
                        "pendingDirections": current["pendingDirections"],
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
                    "pendingDirections": current["pendingDirections"],
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
                "pendingDirections": current["pendingDirections"],
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
            invalid_rules[0]["conditions"] = {"applicantName": "未知申请人"}
            with self.assertRaises(AppSettingsValidationError) as invalid_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        "expectedVersion": first["version"],
                        "idempotencyKey": "rules-save-invalid",
                        "rules": invalid_rules,
                        "pendingDirections": first["pendingDirections"],
                    },
                    actor_id="finance-owner",
                )
            missing_applicant_rules = [dict(rule) for rule in current["rules"]]
            missing_applicant_rules[2]["conditions"] = {
                "hasOa": True,
                "hasBank": False,
                "invoiceOaAmountMatched": True,
            }
            with self.assertRaises(AppSettingsValidationError) as missing_applicant_context:
                app._app_settings_service.update_input_invoice_usage_payment_status_rules(
                    {
                        "expectedVersion": first["version"],
                        "idempotencyKey": "rules-save-missing-applicant",
                        "rules": missing_applicant_rules,
                        "pendingDirections": first["pendingDirections"],
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
        self.assertEqual(invalid_context.exception.error_code, "unsupported_input_invoice_usage_payment_rule_constraint")
        self.assertEqual(missing_applicant_context.exception.error_code, "unsupported_input_invoice_usage_payment_rule_constraint")
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
                    "pendingDirections": current["pendingDirections"],
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
        self.assertEqual(status["code"], "paid")

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
                    "pendingDirections": current["pendingDirections"],
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
                relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
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
