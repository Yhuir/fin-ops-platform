from __future__ import annotations

from decimal import Decimal
import unittest

from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.output_invoice_collection_service import (
    OutputInvoiceCollectionError,
    OutputInvoiceCollectionQueryService,
)
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeOAProjection, FakeWorkbenchRelationFacade


class RepositoryOnlyOutputInvoiceFacts:
    def __init__(self, invoices: list[Invoice], transactions: list[BankTransaction] | None = None) -> None:
        self.invoices = invoices
        self.transactions = list(transactions or [])
        self.invoice_page_calls: list[dict[str, object]] = []
        self.transaction_page_calls: list[dict[str, object]] = []

    def list_invoices_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        month: str | None = None,
        invoice_type: str | None = None,
        status: str | None = None,
        keyword: str | None = None,
    ) -> tuple[list[Invoice], int]:
        self.invoice_page_calls.append(
            {
                "page": page,
                "page_size": page_size,
                "month": month,
                "invoice_type": invoice_type,
                "status": status,
                "keyword": keyword,
            }
        )
        return list(self.invoices), len(self.invoices)

    def list_bank_transactions_page(
        self,
        *,
        page: int = 1,
        page_size: int = 100,
        **_: object,
    ) -> tuple[list[BankTransaction], int]:
        self.transaction_page_calls.append({"page": page, "page_size": page_size})
        return list(self.transactions), len(self.transactions)


class OutputInvoiceCollectionQueryServiceTests(unittest.TestCase):
    def test_default_rows_read_repository_output_invoice_facts_when_memory_snapshot_is_empty(self) -> None:
        buyer = self._counterparty("buyer", "生产库客户")
        invoice = self._invoice("out-postgres", "PG-OUT-001", buyer, total_with_tax="218.00")
        repository = RepositoryOnlyOutputInvoiceFacts([invoice])
        service = OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.list_rows()

        self.assertEqual(payload["pagination"]["total"], 1)
        self.assertEqual(payload["rows"][0]["invoiceId"], "out-postgres")
        self.assertEqual(payload["rows"][0]["invoice"]["buyerName"], "生产库客户")
        self.assertEqual(repository.invoice_page_calls[0]["month"], None)
        self.assertEqual(repository.invoice_page_calls[0]["invoice_type"], InvoiceType.OUTPUT.value)

    def test_list_rows_batches_repository_bank_reads_across_all_invoice_rows(self) -> None:
        buyer = self._counterparty("buyer", "生产库客户")
        invoices = [
            self._invoice(f"out-postgres-{index}", f"PG-OUT-{index:03d}", buyer, total_with_tax="218.00")
            for index in range(1, 6)
        ]
        bank = self._bank("bank-postgres-1", "218.00", TransactionDirection.INFLOW)
        repository = RepositoryOnlyOutputInvoiceFacts(invoices, transactions=[bank])
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-output-postgres-1", [invoices[0].id, bank.id], amount_matched=True)
        service = OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=pair_service,
                transactions=[bank],
                invoices=invoices,
            ),
        )

        payload = service.list_rows(page_size=20)

        self.assertEqual(payload["pagination"]["total"], 5)
        self.assertEqual(repository.invoice_page_calls[0]["invoice_type"], InvoiceType.OUTPUT.value)
        self.assertEqual(len(repository.transaction_page_calls), 1)

    def test_filter_options_are_built_from_all_matching_rows_not_first_page_only(self) -> None:
        buyer = self._counterparty("buyer", "生产库客户")
        invoices = [
            self._invoice(f"out-postgres-{index}", f"PG-OUT-{index:03d}", buyer, total_with_tax="1.00")
            for index in range(1, 202)
        ]
        repository = RepositoryOnlyOutputInvoiceFacts(invoices)
        service = OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(fact_repository=repository),
        )

        payload = service.filter_options()

        buyer_options = {
            option["value"]: option["count"]
            for field in payload["fields"]
            if field["field"] == "buyer_name"
            for option in field["options"]
        }
        self.assertEqual(buyer_options["生产库客户"], 201)

    def test_rows_are_one_formal_output_invoice_with_read_model_shape(self) -> None:
        buyer = self._counterparty("buyer", "昆明客户有限公司", tax_no="91530000BUYER")
        line_1 = self._invoice(
            "out-line-1",
            "8001-A",
            buyer,
            digital_invoice_no="26372000000990000001",
            taxable_item_name="软件服务费",
            amount="80.00",
            tax_amount="4.80",
            total_with_tax="84.80",
        )
        line_2 = self._invoice(
            "out-line-2",
            "8001-B",
            buyer,
            digital_invoice_no="26372000000990000001",
            taxable_item_name="技术服务费",
            amount="20.00",
            tax_amount="1.20",
            total_with_tax="21.20",
        )
        service = self._service(invoices=[line_2, line_1])

        payload = service.list_rows()

        self.assertEqual(payload["readModelStatus"], "live_query")
        self.assertEqual(payload["sourceVersion"], "output-invoice-collections:v3")
        self.assertIn("generatedAt", payload)
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 50, "total": 1})
        row = payload["rows"][0]
        self.assertEqual(row["invoiceId"], "out-line-1")
        self.assertEqual(row["invoiceIdentityKey"], "digital:26372000000990000001")
        self.assertEqual(row["invoice"]["buyerName"], "昆明客户有限公司")
        self.assertEqual(row["invoice"]["totalWithTax"], "106.00")
        self.assertEqual(row["invoice"]["lineItemCount"], 2)
        self.assertEqual(row["collectionStatus"]["code"], "pending_collection")
        self.assertEqual(row["receipt"]["status"], "not_available")

    def test_unified_relation_payload_exposes_multiple_oa_bank_and_output_invoices(self) -> None:
        buyer = self._counterparty("buyer", "统一事实源客户")
        invoice_a = self._invoice("out-unified-a", "9101", buyer, total_with_tax="100.00")
        invoice_b = self._invoice("out-unified-b", "9102", buyer, total_with_tax="200.00")
        invoice_c = self._invoice("out-unified-c", "9103", buyer, total_with_tax="300.00")
        bank_a = self._bank("bank-unified-a", "100.00", TransactionDirection.INFLOW)
        bank_b = self._bank("bank-unified-b", "500.00", TransactionDirection.INFLOW)
        oa_projection = FakeOAProjection([
            self._oa_record("oa-unified-a", applicant="申请人甲", amount="100.00"),
            self._oa_record("oa-unified-b", applicant="申请人乙", amount="500.00"),
        ])
        pair_service = WorkbenchPairRelationService()
        pair_service.create_active_relation(
            case_id="case-unified-output",
            row_ids=[invoice_a.id, invoice_b.id, invoice_c.id, bank_a.id, bank_b.id, "oa-unified-a", "oa-unified-b"],
            row_types=["invoice", "invoice", "invoice", "bank", "bank", "oa", "oa"],
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": True},
        )
        relation_facade = FakeWorkbenchRelationFacade.from_pair_service(
            pair_service=pair_service,
            transactions=[bank_a, bank_b],
            invoices=[invoice_a, invoice_b, invoice_c],
            oa_projection=oa_projection,
        )
        service = OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(
                existing_invoices=[invoice_a, invoice_b, invoice_c],
                existing_transactions=[bank_a, bank_b],
            ),
            relation_facade=relation_facade,
            oa_projection=oa_projection,
        )

        row = service.list_rows(page_size=20)["rows"][0]

        self.assertEqual(row["oa"]["relationCount"], 2)
        self.assertEqual([summary["oaId"] for summary in row["oa"]["summaries"]], ["oa-unified-a", "oa-unified-b"])
        self.assertEqual(row["bankTransactions"]["relationCount"], 2)
        self.assertEqual(row["bankTransactions"]["receivedTotal"], "600.00")
        self.assertEqual(row["invoiceRelations"]["relationCount"], 3)
        self.assertEqual(row["invoiceRelations"]["totalWithTax"], "600.00")
        self.assertEqual(
            {summary["invoiceId"] for summary in row["invoiceRelations"]["summaries"]},
            {"out-unified-a", "out-unified-b", "out-unified-c"},
        )

        oa_details = service.row_relation_details(row["id"], kind="oa")
        invoice_details = service.row_relation_details(row["id"], kind="invoice")
        self.assertEqual(oa_details["relationCount"], 2)
        self.assertEqual(invoice_details["relationCount"], 3)
        self.assertEqual(
            {summary["invoiceId"] for summary in invoice_details["summaries"]},
            {"out-unified-a", "out-unified-b", "out-unified-c"},
        )

    def test_collection_status_uses_red_refund_priority_before_collected_and_pending_rules(self) -> None:
        buyer = self._counterparty("buyer", "客户")
        paid_invoice = self._invoice("out-paid", "9001", buyer, total_with_tax="100.00")
        partial_invoice = self._invoice("out-partial", "9002", buyer, total_with_tax="100.00")
        pending_invoice = self._invoice("out-pending", "9003", buyer, total_with_tax="100.00")
        red_invoice = self._invoice(
            "out-red",
            "9004",
            buyer,
            amount="-94.34",
            tax_amount="-5.66",
            total_with_tax="-100.00",
            is_positive_invoice="否",
        )
        paid_bank = self._bank("bank-paid", "100.00", TransactionDirection.INFLOW)
        partial_bank = self._bank("bank-partial", "40.00", TransactionDirection.INFLOW)
        refund_bank = self._bank("bank-refund", "100.00", TransactionDirection.OUTFLOW)
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-paid", [paid_invoice.id, paid_bank.id], amount_matched=True)
        self._relation(pair_service, "case-partial", [partial_invoice.id, partial_bank.id], amount_matched=False)
        self._relation(pair_service, "case-refund", [red_invoice.id, refund_bank.id], amount_matched=True)
        service = self._service(
            invoices=[pending_invoice, red_invoice, partial_invoice, paid_invoice],
            transactions=[paid_bank, partial_bank, refund_bank],
            pair_service=pair_service,
        )

        rows = {row["invoiceId"]: row for row in service.list_rows(page_size=20)["rows"]}

        self.assertEqual(rows["out-paid"]["collectionStatus"]["code"], "collected_red_refunded")
        self.assertEqual(rows["out-paid"]["collectionStatus"]["label"], "开票已收款，冲红并退款")
        self.assertEqual(rows["out-partial"]["collectionStatus"]["code"], "partial_collected")
        self.assertEqual(rows["out-partial"]["collectionStatus"]["collectedAmount"], "40.00")
        self.assertEqual(rows["out-partial"]["collectionStatus"]["pendingAmount"], "60.00")
        self.assertEqual(rows["out-pending"]["collectionStatus"]["code"], "pending_collection")
        self.assertEqual(rows["out-red"]["collectionStatus"]["code"], "collected_red_refunded")
        self.assertEqual(rows["out-paid"]["redInvoiceRelation"]["relationCount"], 1)

    def test_candidate_bank_relation_is_visible_without_marking_invoice_collected(self) -> None:
        buyer = self._counterparty("buyer", "候选客户")
        invoice = self._invoice("out-candidate", "9005", buyer, total_with_tax="100.00")
        bank = self._bank("bank-candidate", "100.00", TransactionDirection.INFLOW)
        relation_facade = FakeWorkbenchRelationFacade(
            [
                {
                    "row_id": invoice.id,
                    "row_type": "invoice",
                    "relation_status": "candidate",
                    "group_ids": ["candidate-output-bank"],
                    "linked_oa": [],
                    "linked_bank_transactions": [
                        {
                            "id": bank.id,
                            "amount": "100.00",
                            "direction": "inflow",
                            "relation_case_id": "candidate-output-bank",
                            "relation_status": "candidate",
                        }
                    ],
                    "linked_input_invoices": [],
                    "linked_output_invoices": [{"id": invoice.id, "relation_case_id": "candidate-output-bank", "relation_status": "candidate"}],
                }
            ],
            groups=[
                {
                    "group_id": "candidate-output-bank",
                    "relation_status": "candidate",
                    "payload": {
                        "group_id": "candidate-output-bank",
                        "row_ids": [invoice.id, bank.id],
                        "row_types": ["invoice", "bank"],
                        "relation_status": "candidate",
                        "relation_mode": "automatic_decision",
                        "amount_check": {"matched": True},
                    },
                    "oa_row_ids": [],
                    "bank_transaction_ids": [bank.id],
                    "input_invoice_ids": [],
                    "output_invoice_ids": [invoice.id],
                }
            ],
        )
        service = OutputInvoiceCollectionQueryService(
            import_service=ImportNormalizationService(existing_invoices=[invoice], existing_transactions=[bank]),
            relation_facade=relation_facade,
        )

        row = service.list_rows(page_size=20)["rows"][0]

        self.assertEqual(row["bankTransactions"]["relationCount"], 1)
        self.assertEqual(row["bankTransactions"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["bankTransactions"]["receivedTotal"], "0.00")
        self.assertEqual(row["collectionStatus"]["code"], "pending_collection")
        self.assertEqual(row["receipt"]["status"], "not_available")

    def test_pagination_filter_sort_and_filter_options_are_server_side_contracts(self) -> None:
        buyer_a = self._counterparty("buyer-a", "甲客户")
        buyer_b = self._counterparty("buyer-b", "乙客户")
        service = self._service(
            invoices=[
                self._invoice("out-1", "1001", buyer_a, total_with_tax="30.00", invoice_date="2026-05-01"),
                self._invoice("out-2", "1002", buyer_b, total_with_tax="10.00", invoice_date="2026-05-02"),
                self._invoice("out-3", "1003", buyer_a, total_with_tax="20.00", invoice_date="2026-05-03"),
            ]
        )

        payload = service.list_rows(
            page=1,
            page_size=1,
            filters='[{"field":"buyer_name","operator":"in","values":["甲客户"]}]',
            sort_field="total_with_tax",
            sort_direction="desc",
        )
        options = service.filter_options(month="2026-05")

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["invoiceId"], "out-1")
        self.assertEqual(payload["summary"]["invoiceCount"], 2)
        self.assertEqual(payload["summary"]["totalWithTax"], "50.00")
        self.assertIn("collection_status", [field["field"] for field in options["fields"]])
        self.assertIn("receipt_status", [field["field"] for field in options["fields"]])

    def test_page_size_limit_protects_first_screen_slo(self) -> None:
        buyer = self._counterparty("buyer-large", "大数据客户")
        service = self._service(
            invoices=[
                self._invoice(
                    f"out-large-{index}",
                    f"OUT-LG-{index:04d}",
                    buyer,
                    digital_invoice_no=f"2637200000099{index:07d}",
                    total_with_tax="1.00",
                )
                for index in range(250)
            ]
        )

        payload = service.list_rows(page=1, page_size=200)

        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 200, "total": 250})
        self.assertEqual(len(payload["rows"]), 200)
        with self.assertRaises(OutputInvoiceCollectionError) as context:
            service.list_rows(page=1, page_size=201)
        self.assertEqual(context.exception.error_code, "invalid_paging")

    def test_receipt_preview_uses_single_income_transaction_or_requires_selection(self) -> None:
        buyer = self._counterparty("buyer", "客户")
        single_invoice = self._invoice("out-single", "2001", buyer, total_with_tax="80.00")
        multi_invoice = self._invoice("out-multi", "2002", buyer, total_with_tax="100.00")
        single_bank = self._bank("bank-single", "80.00", TransactionDirection.INFLOW)
        bank_a = self._bank("bank-a", "40.00", TransactionDirection.INFLOW, trade_time="2026-05-02 10:00:00")
        bank_b = self._bank("bank-b", "60.00", TransactionDirection.INFLOW, trade_time="2026-05-03 10:00:00")
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-single", [single_invoice.id, single_bank.id], amount_matched=True)
        self._relation(pair_service, "case-multi", [multi_invoice.id, bank_a.id, bank_b.id], amount_matched=False)
        service = self._service(
            invoices=[multi_invoice, single_invoice],
            transactions=[single_bank, bank_a, bank_b],
            pair_service=pair_service,
        )

        rows = {row["invoiceId"]: row for row in service.list_rows(page_size=20)["rows"]}
        single_preview = service.receipt_preview({"rowId": rows["out-single"]["id"]})
        multi_preview = service.receipt_preview({"rowId": rows["out-multi"]["id"]})
        selected_preview = service.receipt_preview(
            {"rowId": rows["out-multi"]["id"], "selectedBankTransactionId": "bank-b"}
        )

        self.assertTrue(single_preview["canPreview"])
        self.assertEqual(single_preview["receipt"]["amount"], "80.00")
        self.assertEqual(single_preview["receipt"]["payerName"], "客户")
        self.assertEqual(single_preview["receipt"]["templateVersion"], "sheet7-static-v1")
        self.assertFalse(multi_preview["canPreview"])
        self.assertEqual(multi_preview["reasonCode"], "bank_selection_required")
        self.assertEqual([candidate["bankTransactionId"] for candidate in multi_preview["candidates"]], ["bank-b", "bank-a"])
        self.assertTrue(selected_preview["canPreview"])
        self.assertEqual(selected_preview["receipt"]["amount"], "60.00")

    def test_receipt_preview_blocks_no_income_and_red_refund_rows_without_fake_history(self) -> None:
        buyer = self._counterparty("buyer", "客户")
        no_income = self._invoice("out-no-income", "3001", buyer, total_with_tax="100.00")
        paid = self._invoice("out-paid", "3002", buyer, total_with_tax="100.00")
        red = self._invoice(
            "out-red",
            "3003",
            buyer,
            amount="-94.34",
            tax_amount="-5.66",
            total_with_tax="-100.00",
            is_positive_invoice="否",
        )
        income = self._bank("bank-income", "100.00", TransactionDirection.INFLOW)
        refund = self._bank("bank-refund", "100.00", TransactionDirection.OUTFLOW)
        pair_service = WorkbenchPairRelationService()
        self._relation(pair_service, "case-income", [paid.id, income.id], amount_matched=True)
        self._relation(pair_service, "case-refund", [red.id, refund.id], amount_matched=True)
        service = self._service(
            invoices=[red, paid, no_income],
            transactions=[income, refund],
            pair_service=pair_service,
        )

        rows = {row["invoiceId"]: row for row in service.list_rows(page_size=20)["rows"]}
        no_income_preview = service.receipt_preview({"rowId": rows["out-no-income"]["id"]})
        refund_preview = service.receipt_preview({"rowId": rows["out-paid"]["id"]})
        history = service.receipt_history(invoice_id="out-paid")

        self.assertFalse(no_income_preview["canPreview"])
        self.assertEqual(no_income_preview["reasonCode"], "no_income_transaction")
        self.assertEqual(no_income_preview["pendingAmount"], "100.00")
        self.assertFalse(refund_preview["canPreview"])
        self.assertEqual(refund_preview["reasonCode"], "red_refund_blocked")
        self.assertFalse(history["sourceAvailable"])
        self.assertEqual(history["receipts"], [])

    def test_validation_rejects_unknown_filter_sort_and_relation_kind(self) -> None:
        service = self._service(invoices=[])

        with self.assertRaises(OutputInvoiceCollectionError) as field_context:
            service.list_rows(filters='[{"field":"unknown","operator":"equals","value":"x"}]')
        with self.assertRaises(OutputInvoiceCollectionError) as sort_context:
            service.list_rows(sort_field="unknown")
        with self.assertRaises(OutputInvoiceCollectionError) as relation_context:
            service.row_relation_details("missing", kind="unknown")

        self.assertEqual(field_context.exception.error_code, "invalid_filter_field")
        self.assertEqual(sort_context.exception.error_code, "invalid_sort_field")
        self.assertEqual(relation_context.exception.error_code, "invalid_relation_kind")

    @staticmethod
    def _counterparty(counterparty_id: str, name: str, *, tax_no: str | None = None) -> Counterparty:
        return Counterparty(
            id=counterparty_id,
            name=name,
            normalized_name=name,
            counterparty_type="customer",
            tax_no=tax_no,
        )

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        buyer: Counterparty,
        *,
        invoice_code: str | None = None,
        digital_invoice_no: str | None = None,
        amount: str = "94.34",
        tax_amount: str = "5.66",
        total_with_tax: str = "100.00",
        invoice_date: str = "2026-05-20",
        taxable_item_name: str = "服务费",
        is_positive_invoice: str = "是",
    ) -> Invoice:
        return Invoice(
            id=invoice_id,
            invoice_type=InvoiceType.OUTPUT,
            invoice_no=invoice_no,
            invoice_code=invoice_code,
            digital_invoice_no=digital_invoice_no,
            counterparty=buyer,
            amount=Decimal(amount),
            signed_amount=Decimal(total_with_tax),
            invoice_date=invoice_date,
            seller_name="云南溯源科技有限公司",
            buyer_name=buyer.name,
            seller_tax_no="91530000SELLER",
            buyer_tax_no=buyer.tax_no or "91530000BUYER",
            tax_rate="6%",
            tax_amount=Decimal(tax_amount),
            total_with_tax=Decimal(total_with_tax),
            specific_business_type="信息技术服务",
            taxable_item_name=taxable_item_name,
            invoice_source="import",
            invoice_kind="增值税专用发票",
            invoice_status_from_source="valid",
            is_positive_invoice=is_positive_invoice,
            risk_level="低",
            issuer="开票人",
            source_batch_id="batch-output",
            source_links=[{"kind": "import_batch", "id": "batch-output"}],
        )

    @staticmethod
    def _bank(
        transaction_id: str,
        amount: str,
        direction: TransactionDirection,
        *,
        trade_time: str = "2026-05-21 10:00:00",
    ) -> BankTransaction:
        signed_amount = Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount)
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw="客户",
            amount=Decimal(amount),
            signed_amount=signed_amount,
            txn_date=trade_time[:10],
            trade_time=trade_time,
            currency="CNY",
            counterparty_account_no="622233334444",
            counterparty_bank_name="开户行",
            booked_date=trade_time[:10],
            summary="服务费",
            remark="银行备注",
            imported_bank_name="中国银行",
            imported_bank_last4="1234",
            bank_text_fields=[{"label": "摘要", "value": "服务费"}],
        )

    @staticmethod
    def _oa_record(oa_id: str, *, applicant: str, amount: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="已完成",
            case_id=oa_id,
            applicant=applicant,
            project_name=f"{applicant}项目",
            apply_type="付款申请",
            amount=amount,
            counterparty_name="统一事实源客户",
            reason="销项收款测试",
            relation_code="linked",
            relation_label="已关联",
            relation_tone="success",
        )

    @staticmethod
    def _relation(
        pair_service: WorkbenchPairRelationService,
        case_id: str,
        row_ids: list[str],
        *,
        amount_matched: bool,
    ) -> None:
        pair_service.create_active_relation(
            case_id=case_id,
            row_ids=row_ids,
            row_types=["invoice" if row_id.startswith("out") else "bank" for row_id in row_ids],
            relation_mode="manual_confirmed",
            created_by="tester",
            amount_check={"matched": amount_matched},
        )

    @staticmethod
    def _service(
        *,
        invoices: list[Invoice],
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
                invoices=list(invoices),
            ),
        )
