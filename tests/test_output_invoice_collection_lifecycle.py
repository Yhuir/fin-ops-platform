from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.output_invoice_collection_lifecycle_service import (
    InMemoryOutputInvoiceCollectionLifecycleRepository,
    OutputInvoiceCollectionLifecycleService,
)
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionError
from fin_ops_platform.services.output_invoice_collection_receipt_service import OutputInvoiceCollectionReceiptService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.postgres_repositories.output_invoice_collection import PostgresOutputInvoiceCollectionLifecycleRepository
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeWorkbenchRelationFacade


class RecordingRefreshQueue:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str, **_: object) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class EmptyPostgresConnection:
    def __init__(self) -> None:
        self.fetch_one_calls: list[tuple[str, tuple[object, ...]]] = []

    def fetch_one(self, sql: str, params: tuple[object, ...] = ()) -> dict[str, object] | None:
        self.fetch_one_calls.append((sql, params))
        return None


class OutputInvoiceCollectionLifecycleTests(unittest.TestCase):
    def test_manual_status_and_reminder_overlay_rows_without_refresh_targets(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        queue = RecordingRefreshQueue()
        invoice = self._invoice("out-override", "1001", "客户A", total_with_tax="100.00")
        query = self._query_service([invoice], repository)
        row = query.list_rows()["rows"][0]
        lifecycle = OutputInvoiceCollectionLifecycleService(
            repository=repository,
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
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
        self.assertEqual(set(status_result), {"override"})
        self.assertEqual(reminder_result["reminder"]["status"], "active")
        self.assertEqual(set(reminder_result), {"reminder"})
        self.assertEqual(refreshed_row["collectionStatus"]["code"], "pending_red_invoice")
        self.assertEqual(refreshed_row["collectionStatus"]["manualOverride"]["note"], "客户确认需要冲红")
        self.assertEqual(refreshed_row["collectionStatus"]["expectedCollectionDate"], "2026-06-20")
        self.assertEqual(refreshed_row["collectionStatus"]["reminder"]["channel"], "oa")
        self.assertEqual(queue.refreshes, [])

    def test_lifecycle_overlays_and_receipt_history_are_tenant_scoped(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        invoice = self._invoice("out-tenant", "1101", "客户Tenant", total_with_tax="100.00")
        bank = self._bank("bank-tenant", "100.00")
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-tenant",
            row_ids=[invoice.id, bank.id],
            row_types=["invoice", "bank"],
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": True},
        )
        query = self._query_service([invoice], repository, transactions=[bank], pair_service=pair_service)
        row = query.list_rows()["rows"][0]
        lifecycle = OutputInvoiceCollectionLifecycleService(
            repository=repository,
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
        )
        receipts = OutputInvoiceCollectionReceiptService(
            repository=repository,
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
        )

        lifecycle.set_collection_status(
            row["id"],
            {"statusCode": "pending_red_invoice", "expectedVersion": 0},
            actor_id="tester",
            tenant_id="tenant-a",
        )
        receipts.create_receipt(
            row["id"],
            {"bankTransactionId": "bank-tenant", "idempotencyKey": "tenant-receipt-1"},
            actor_id="tester",
            tenant_id="tenant-a",
        )

        tenant_a_row = query.list_rows(tenant_id="tenant-a")["rows"][0]
        tenant_b_row = query.list_rows(tenant_id="tenant-b")["rows"][0]
        tenant_a_history = query.receipt_history(invoice_id="out-tenant", tenant_id="tenant-a")
        tenant_b_history = query.receipt_history(invoice_id="out-tenant", tenant_id="tenant-b")

        self.assertEqual(tenant_a_row["collectionStatus"]["code"], "pending_red_invoice")
        self.assertEqual(tenant_a_row["receipt"]["status"], "issued")
        self.assertEqual(tenant_b_row["collectionStatus"]["code"], "collected")
        self.assertEqual(tenant_b_row["receipt"]["status"], "pending")
        self.assertEqual(len(tenant_a_history["receipts"]), 1)
        self.assertEqual(tenant_b_history["receipts"], [])

    def test_red_relation_overlay_adds_manual_evidence(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        invoice = self._invoice("out-blue", "2001", "客户B", total_with_tax="80.00")
        related = self._invoice("out-red", "2002", "客户B", total_with_tax="-80.00", is_positive_invoice="否")
        query = self._query_service([invoice, related], repository)
        row = query.list_rows()["rows"][0]
        lifecycle = OutputInvoiceCollectionLifecycleService(
            repository=repository,
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
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

    def test_postgres_red_relation_revoke_not_found_fails_closed(self) -> None:
        repository = PostgresOutputInvoiceCollectionLifecycleRepository(EmptyPostgresConnection())

        with self.assertRaises(OutputInvoiceCollectionError) as caught:
            repository.revoke_red_relation(
                relation_id="missing-relation",
                actor_id="tester",
                tenant_id="default",
            )

        self.assertEqual(caught.exception.error_code, "relation_not_found")
        self.assertEqual(caught.exception.status_code.value, 404)

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
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
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
        self.assertEqual(set(first), {"receipt"})
        self.assertEqual(set(replay), {"receipt"})
        self.assertEqual(voided["receipt"]["status"], "voided")
        self.assertEqual(reissued["receipt"]["status"], "issued")
        self.assertNotEqual(reissued["receipt"]["id"], first["receipt"]["id"])
        self.assertNotEqual(reissued["receipt"]["receiptNo"], first["receipt"]["receiptNo"])
        self.assertEqual(reissued["receipt"]["reissuedFromReceiptId"], first["receipt"]["id"])
        self.assertTrue(history["sourceAvailable"])
        self.assertEqual([item["status"] for item in history["receipts"]], ["issued", "voided"])

        with self.assertRaises(OutputInvoiceCollectionError) as duplicate_reissue:
            receipts.reissue_receipt(first["receipt"]["id"], {"reason": "重复重开"}, actor_id="tester", tenant_id="default")
        self.assertEqual(duplicate_reissue.exception.error_code, "invalid_receipt_status")

    def test_receipt_numbers_are_unique_under_concurrent_creates_and_reset_periods(self) -> None:
        repository = InMemoryOutputInvoiceCollectionLifecycleRepository()
        invoices = [
            self._invoice(f"out-month-{index}", f"5{index:03d}", f"客户M{index}", total_with_tax="100.00", invoice_date="2026-05-20")
            for index in range(1, 13)
        ]
        invoices.extend(
            [
                self._invoice("out-june", "6001", "客户June", total_with_tax="100.00", invoice_date="2026-06-01"),
                self._invoice("out-year-jan", "7001", "客户Y1", total_with_tax="100.00", invoice_date="2026-01-05"),
                self._invoice("out-year-dec", "7002", "客户Y2", total_with_tax="100.00", invoice_date="2026-12-31"),
                self._invoice("out-year-next", "7003", "客户Y3", total_with_tax="100.00", invoice_date="2027-01-01"),
                self._invoice("out-none-first", "8001", "客户N1", total_with_tax="100.00", invoice_date="2026-05-20"),
                self._invoice("out-none-next", "8002", "客户N2", total_with_tax="100.00", invoice_date="2027-01-01"),
            ]
        )
        banks = [self._bank(f"bank-{invoice.id}", "100.00") for invoice in invoices]
        pair_service = WorkbenchPairRelationService()
        for invoice, bank in zip(invoices, banks, strict=True):
            pair_service.create_active_relation(
                case_id=f"case-{invoice.id}",
                row_ids=[invoice.id, bank.id],
                row_types=["invoice", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
        query = self._query_service(invoices, repository, transactions=banks, pair_service=pair_service)
        rows_by_invoice_id = {str(row["invoice"]["id"]): row for row in query.list_rows(page_size=100)["rows"]}
        receipts = OutputInvoiceCollectionReceiptService(
            repository=repository,
            row_provider=lambda row_id, tenant_id: query.row_by_id(row_id, tenant_id=tenant_id),
        )

        def create_for(invoice_id: str) -> str:
            row = rows_by_invoice_id[invoice_id]
            result = receipts.create_receipt(
                row["id"],
                {
                    "bankTransactionId": f"bank-{invoice_id}",
                    "idempotencyKey": f"receipt-{invoice_id}",
                },
                actor_id="tester",
                tenant_id="default",
            )
            return str(result["receipt"]["receiptNo"])

        month_invoice_ids = [f"out-month-{index}" for index in range(1, 13)]
        with ThreadPoolExecutor(max_workers=6) as executor:
            month_receipt_numbers = list(executor.map(create_for, month_invoice_ids))

        self.assertEqual(
            set(month_receipt_numbers),
            {f"SK202605{index:04d}" for index in range(1, 13)},
        )
        self.assertEqual(create_for("out-june"), "SK2026060001")

        repository.update_receipt_settings(tenant_id="default", prefix="SK", reset_period="yearly", actor_id="tester")
        yearly_numbers = [create_for(invoice_id) for invoice_id in ["out-year-jan", "out-year-dec", "out-year-next"]]
        self.assertEqual(yearly_numbers, ["SK20260001", "SK20260002", "SK20270001"])

        repository.update_receipt_settings(tenant_id="default", prefix="SK", reset_period="none", actor_id="tester")
        never_reset_numbers = [create_for(invoice_id) for invoice_id in ["out-none-first", "out-none-next"]]
        self.assertEqual(never_reset_numbers, ["SK0000000001", "SK0000000002"])
        all_numbers = month_receipt_numbers + ["SK2026060001"] + yearly_numbers + never_reset_numbers
        self.assertEqual(len(all_numbers), len(set(all_numbers)))

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
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service or WorkbenchPairRelationService(),
                transactions=list(transactions or []),
                invoices=invoices,
            ),
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
        invoice_date: str = "2026-05-20",
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
            invoice_date=invoice_date,
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
