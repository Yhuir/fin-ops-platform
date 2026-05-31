from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.output_invoice_collection_lifecycle_service import (
    InMemoryOutputInvoiceCollectionLifecycleRepository,
    OutputInvoiceCollectionLifecycleService,
)
from fin_ops_platform.services.output_invoice_collection_receipt_service import OutputInvoiceCollectionReceiptService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class RecordingRefreshQueue:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_: object) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class OutputInvoiceCollectionLifecycleTests(unittest.TestCase):
    def test_manual_status_and_reminder_overlay_rows_and_enqueue_month_scope(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        queue = RecordingRefreshQueue()
        invoice = self._invoice("out-override", "1001", "客户A", total_with_tax="100.00")
        query = self._query_service([invoice], repository)
        row = query.list_rows()["rows"][0]
        lifecycle = OutputInvoiceCollectionLifecycleService(
            repository=repository,
            row_provider=lambda row_id: query.row_by_id(row_id),
            queue_repository=queue,
        )

        status_result = lifecycle.set_collection_status(
            row["id"],
            {
                "statusCode": "pending_red_invoice",
                "expectedCollectionDate": "2026-06-20",
                "note": "客户确认需要冲红",
                "expectedVersion": 0,
            },
            actor_id="tester",
            tenant_id="default",
        )
        reminder_result = lifecycle.upsert_collection_reminder(
            row["id"],
            {"remindAt": "2026-06-15T09:00:00+08:00", "channel": "oa", "note": "到期提醒"},
            actor_id="tester",
            tenant_id="default",
        )

        refreshed_row = query.list_rows()["rows"][0]
        self.assertEqual(status_result["override"]["version"], 1)
        self.assertEqual(reminder_result["reminder"]["status"], "active")
        self.assertEqual(refreshed_row["collectionStatus"]["code"], "pending_red_invoice")
        self.assertEqual(refreshed_row["collectionStatus"]["manualOverride"]["note"], "客户确认需要冲红")
        self.assertEqual(refreshed_row["collectionStatus"]["expectedCollectionDate"], "2026-06-20")
        self.assertEqual(refreshed_row["collectionStatus"]["reminder"]["channel"], "oa")
        self.assertEqual(queue.refreshes, [("output_invoice_collection", "2026-05", "lifecycle_status_changed"), ("output_invoice_collection", "2026-05", "lifecycle_reminder_changed")])

    def test_red_relation_overlay_adds_manual_evidence(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        invoice = self._invoice("out-blue", "2001", "客户B", total_with_tax="80.00")
        related = self._invoice("out-red", "2002", "客户B", total_with_tax="-80.00", is_positive_invoice="否")
        query = self._query_service([invoice, related], repository)
        row = query.list_rows()["rows"][0]
        lifecycle = OutputInvoiceCollectionLifecycleService(
            repository=repository,
            row_provider=lambda row_id: query.row_by_id(row_id),
            queue_repository=RecordingRefreshQueue(),
        )

        result = lifecycle.confirm_red_invoice_relation(
            row["id"],
            {
                "relatedInvoiceIdentityKey": "id:out-red",
                "relatedInvoiceId": "out-red",
                "relationType": "red_invoice",
                "evidence": "客户邮件确认红冲",
                "confidence": "manual_confirmed",
            },
            actor_id="tester",
            tenant_id="default",
        )

        refreshed_row = query.list_rows()["rows"][0]
        manual = [item for item in refreshed_row["redInvoiceRelation"]["summaries"] if item["source"] == "manual"]
        self.assertEqual(result["relation"]["status"], "active")
        self.assertEqual(manual[0]["evidence"], "客户邮件确认红冲")
        self.assertEqual(manual[0]["confidence"], "manual_confirmed")

    def test_receipts_are_idempotent_and_history_is_real(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        invoice = self._invoice("out-receipt", "3001", "客户C", total_with_tax="120.00")
        bank = self._bank("bank-receipt", "120.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-receipt",
            row_ids=[invoice.id, bank.id],
            row_types=["invoice", "bank"],
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": True},
        )
        query = self._query_service([invoice], repository, transactions=[bank], pair_service=pair_service)
        row = query.list_rows()["rows"][0]
        receipts = OutputInvoiceCollectionReceiptService(
            repository=repository,
            row_provider=lambda row_id: query.row_by_id(row_id),
            queue_repository=RecordingRefreshQueue(),
        )

        first = receipts.create_receipt(
            row["id"],
            {"bankTransactionId": "bank-receipt", "idempotencyKey": "receipt-key-1"},
            actor_id="tester",
            tenant_id="default",
        )
        replay = receipts.create_receipt(
            row["id"],
            {"bankTransactionId": "bank-receipt", "idempotencyKey": "receipt-key-1"},
            actor_id="tester",
            tenant_id="default",
        )
        voided = receipts.void_receipt(first["receipt"]["id"], {"reason": "作废测试"}, actor_id="tester", tenant_id="default")
        reissued = receipts.reissue_receipt(first["receipt"]["id"], {"reason": "重开测试"}, actor_id="tester", tenant_id="default")

        history = query.receipt_history(invoice_id="out-receipt")
        self.assertEqual(first["receipt"]["id"], replay["receipt"]["id"])
        self.assertEqual(first["receipt"]["receiptNo"], replay["receipt"]["receiptNo"])
        self.assertEqual(voided["receipt"]["status"], "voided")
        self.assertEqual(reissued["receipt"]["status"], "issued")
        self.assertTrue(history["sourceAvailable"])
        self.assertEqual([item["status"] for item in history["receipts"]], ["issued", "voided"])

    @staticmethod
    def _query_service(
        invoices: list[Invoice],
        repository: InMemoryOutputInvoiceCollectionLifecycleRepository,
        *,
        transactions: list[BankTransaction] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
    ) -> OutputInvoiceCollectionQueryService:
        return OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=invoices,
                existing_transactions=transactions or [],
            ),
            pair_relation_service=pair_service or WorkbenchPairRelationService(),
            lifecycle_repository=repository,
        )

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        buyer_name: str,
        *,
        total_with_tax: str,
        is_positive_invoice: str = "是",
    ) -> Invoice:
        buyer = Counterparty(
            id=f"cp-{invoice_id}",
            name=buyer_name,
            normalized_name=buyer_name,
            counterparty_type="customer",
            tax_no="91530000BUYER",
        )
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.OUTPUT,
            invoice_no=invoice_no,
            counterparty=buyer,
            amount=Decimal(total_with_tax),
            signed_amount=Decimal(total_with_tax),
            invoice_date="2026-05-20",
            seller_name="云南溯源科技有限公司",
            buyer_name=buyer_name,
            seller_tax_no="91530000SELLER",
            buyer_tax_no="91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal("0.00"),
            total_with_tax=Decimal(total_with_tax),
            taxable_item_name="服务费",
            is_positive_invoice=is_positive_invoice,
        )

    @staticmethod
    def _bank(transaction_id: str, amount: str) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=TransactionDirection.INFLOW,
            counterparty_name_raw="客户C",
            amount=Decimal(amount),
            signed_amount=Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            imported_bank_name="中国银行",
            imported_bank_last4="1234",
            summary="服务费",
        )


if __name__ == "__main__":
    unittest.main()
