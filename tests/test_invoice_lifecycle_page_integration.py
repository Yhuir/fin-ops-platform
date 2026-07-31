from __future__ import annotations

import unittest
from decimal import Decimal

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.bank_transaction_category_service import BankTransactionCategoryService
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import AppSettingsInputInvoiceUsagePaymentRulesProvider
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_pending_payment_canonical_rows import build_oa_pending_payment_rows
from fin_ops_platform.services.pending_invoice_service import PendingInvoiceQueryService


class FakeLifecyclePolicy:
    def __init__(self) -> None:
        self.pending_calls = 0
        self.input_calls = 0
        self.oa_calls = 0

    def evaluate_pending_invoice_acquisition(self, **_: object) -> dict[str, object]:
        self.pending_calls += 1
        return {
            "code": "policy_pending_invoice",
            "label": "统一待找发票",
            "reason": "from lifecycle policy",
            "severity": "info",
            "primary_action": "none",
            "matched_rule": None,
        }

    def evaluate_input_invoice_payment(self, **_: object) -> dict[str, object]:
        self.input_calls += 1
        return {
            "code": "policy_input_payment",
            "label": "统一进项付款",
            "reason": "from lifecycle policy",
            "matchedRuleId": "invoice_lifecycle_policy",
            "severity": "info",
        }

    def evaluate_oa_payment(self, **_: object) -> dict[str, object]:
        self.oa_calls += 1
        return {
            "code": "policy_oa_payment",
            "label": "统一OA付款",
            "reason": "from lifecycle policy",
            "severity": "info",
        }


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = list(records)

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class InvoiceLifecyclePageIntegrationTests(unittest.TestCase):
    def test_pending_invoice_rows_delegate_acquisition_status_to_lifecycle_policy(self) -> None:
        policy = FakeLifecyclePolicy()
        transaction = _bank("bank-expense", "88.00", TransactionDirection.OUTFLOW)
        service = PendingInvoiceQueryService(
            import_service=ImportNormalizationService(existing_transactions=[transaction]),
            category_service=BankTransactionCategoryService(),
            app_settings_provider=lambda: {},
            lifecycle_policy=policy,
        )

        row = service.row_for_transaction(transaction.id, direction="expense")

        self.assertEqual(row["invoice_acquisition_status"]["code"], "policy_pending_invoice")
        self.assertEqual(policy.pending_calls, 1)

    def test_input_invoice_usage_rows_delegate_payment_status_to_lifecycle_policy(self) -> None:
        policy = FakeLifecyclePolicy()
        service = InputInvoiceUsageQueryService(
            payment_rules_provider=AppSettingsInputInvoiceUsagePaymentRulesProvider(state_store=None),
            import_service=ImportNormalizationService(
                existing_invoices=[_invoice("inv-in", InvoiceType.INPUT, "88.00")]
            ),
            lifecycle_policy=policy,
        )

        row = service.list_rows()["rows"][0]

        self.assertEqual(row["paymentStatus"]["code"], "policy_input_payment")
        self.assertEqual(policy.input_calls, 1)

    def test_oa_pending_payment_rows_delegate_payment_status_to_lifecycle_policy(self) -> None:
        policy = FakeLifecyclePolicy()
        rows = build_oa_pending_payment_rows(
            records=[_oa("oa-1", "88.00")],
            relations=[],
            bank_transactions=[],
            invoices=[],
            payment_statuses_by_flow_id={},
            flow_id_resolver=lambda _record: None,
            scope_key="2026-01",
            lifecycle_policy=policy,
        )
        row = rows[0]

        self.assertEqual(row["paymentStatus"]["code"], "policy_oa_payment")
        self.assertEqual(policy.oa_calls, 1)


def _counterparty() -> Counterparty:
    return Counterparty(id="cp-1", name="测试往来方", normalized_name="测试往来方", counterparty_type="supplier")


def _invoice(invoice_id: str, invoice_type: InvoiceType, total: str) -> Invoice:
    return Invoice(
        id=invoice_id,
        invoice_type=invoice_type,
        invoice_no=f"NO-{invoice_id}",
        counterparty=_counterparty(),
        amount=Decimal(total),
        signed_amount=Decimal(total),
        tax_amount=Decimal("0.00"),
        total_with_tax=Decimal(total),
        invoice_date="2026-01-10",
        seller_name="测试销方",
        buyer_name="测试购方",
    )


def _bank(transaction_id: str, amount: str, direction: TransactionDirection) -> BankTransaction:
    return BankTransaction(
        id=transaction_id,
        account_no="622200001234",
        txn_direction=direction,
        counterparty_name_raw="测试往来方",
        amount=Decimal(amount),
        signed_amount=Decimal(amount),
        txn_date="2026-01-10",
        trade_time="2026-01-10 10:00:00",
    )


def _oa(oa_id: str, amount: str) -> OAApplicationRecord:
    return OAApplicationRecord(
        id=oa_id,
        month="2026-01",
        section="进行中",
        case_id=f"OA-{oa_id}",
        applicant="测试申请人",
        project_name="测试项目",
        apply_type="报销",
        amount=amount,
        counterparty_name="测试往来方",
        reason="测试",
        relation_code="in_progress",
        relation_label="进行中",
        relation_tone="success",
    )


if __name__ == "__main__":
    unittest.main()
