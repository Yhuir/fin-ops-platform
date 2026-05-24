from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class OutputInvoiceCollectionApiTests(unittest.TestCase):
    def test_rows_route_returns_output_invoice_collection_read_model(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(
                app,
                invoices=[
                    self._invoice("out-api-1", "1001", "甲客户", total_with_tax="30.00"),
                    self._invoice("out-api-2", "1002", "乙客户", total_with_tax="10.00"),
                    self._invoice("out-api-3", "1003", "甲客户", total_with_tax="20.00"),
                ],
            )
            filters = quote(json.dumps([{"field": "buyer_name", "operator": "in", "values": ["甲客户"]}]))

            response = app.handle_request(
                "GET",
                f"/api/output-invoice-collections/rows?page=1&page_size=1&filters={filters}&sort_field=total_with_tax&sort_direction=desc",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["readModelStatus"], "live_query")
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["invoiceId"], "out-api-1")
        self.assertEqual(payload["rows"][0]["invoice"]["buyerName"], "甲客户")

    def test_detail_rules_preview_history_and_relation_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice = self._invoice("out-detail", "2001", "详情客户")
            bank = self._bank("bank-detail", "100.00", TransactionDirection.INFLOW)
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-detail",
                row_ids=[invoice.id, bank.id],
                row_types=["invoice", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            self._install_service(app, invoices=[invoice], transactions=[bank], pair_service=pair_service)

            rows_response = app.handle_request("GET", "/api/output-invoice-collections/rows")
            row = json.loads(rows_response.body)["rows"][0]
            filter_response = app.handle_request("GET", "/api/output-invoice-collections/filter-options?month=2026-05")
            rules_response = app.handle_request("GET", "/api/output-invoice-collections/status-rules")
            invoice_response = app.handle_request("GET", "/api/output-invoice-collections/invoices/out-detail/detail")
            bank_response = app.handle_request("GET", "/api/output-invoice-collections/bank-transactions/bank-detail/detail")
            relation_response = app.handle_request(
                "GET",
                f"/api/output-invoice-collections/rows/{row['id']}/relation-details?kind=bank",
            )
            preview_response = app.handle_request(
                "POST",
                "/api/output-invoice-collections/receipt-preview",
                body=json.dumps({"rowId": row["id"]}),
            )
            history_response = app.handle_request(
                "GET",
                "/api/output-invoice-collections/receipts/history?invoice_id=out-detail",
            )

        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(rules_response.status_code, 200)
        self.assertEqual(invoice_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(history_response.status_code, 200)
        self.assertIn("collection_status", [field["field"] for field in json.loads(filter_response.body)["fields"]])
        self.assertEqual(json.loads(rules_response.body)["rules"][0]["label"], "开票已收款，冲红并退款")
        self.assertEqual(json.loads(invoice_response.body)["id"], "out-detail")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-detail")
        self.assertEqual(json.loads(relation_response.body)["kind"], "bank")
        self.assertTrue(json.loads(preview_response.body)["canPreview"])
        self.assertFalse(json.loads(history_response.body)["sourceAvailable"])
        self.assertEqual(json.loads(history_response.body)["receipts"], [])

    def test_routes_return_structured_validation_and_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(app, invoices=[])

            invalid_page = app.handle_request("GET", "/api/output-invoice-collections/rows?page=0")
            invalid_sort = app.handle_request("GET", "/api/output-invoice-collections/rows?sort_field=unknown")
            invalid_filter = app.handle_request(
                "GET",
                f"/api/output-invoice-collections/rows?filters={quote('[{\"field\":\"bad\",\"operator\":\"equals\",\"value\":\"x\"}]')}",
            )
            missing_detail = app.handle_request("GET", "/api/output-invoice-collections/invoices/missing/detail")

        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(json.loads(invalid_page.body)["error"]["code"], "invalid_paging")
        self.assertEqual(invalid_sort.status_code, 400)
        self.assertEqual(json.loads(invalid_sort.body)["error"]["code"], "invalid_sort_field")
        self.assertEqual(invalid_filter.status_code, 400)
        self.assertEqual(json.loads(invalid_filter.body)["error"]["code"], "invalid_filter_field")
        self.assertEqual(missing_detail.status_code, 404)
        self.assertEqual(json.loads(missing_detail.body)["error"]["code"], "invoice_not_found")

    @staticmethod
    def _install_service(
        app: object,
        *,
        invoices: list[Invoice],
        transactions: list[BankTransaction] | None = None,
        pair_service: WorkbenchPairRelationService | None = None,
    ) -> None:
        import_service = ImportNormalizationService(
            existing_invoices=invoices,
            existing_transactions=transactions or [],
        )
        relation_service = pair_service or WorkbenchPairRelationService()
        app._import_service = import_service
        app._workbench_pair_relation_service = relation_service
        app._output_invoice_collection_query_service = OutputInvoiceCollectionQueryService(
            import_service=import_service,
            pair_relation_service=relation_service,
        )

    @staticmethod
    def _invoice(invoice_id: str, invoice_no: str, buyer_name: str, *, total_with_tax: str = "100.00") -> Invoice:
        counterparty = Counterparty(
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
            counterparty=counterparty,
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
            is_positive_invoice="是",
        )

    @staticmethod
    def _bank(transaction_id: str, amount: str, direction: TransactionDirection) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=direction,
            counterparty_name_raw="详情客户",
            amount=Decimal(amount),
            signed_amount=Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            imported_bank_name="中国银行",
            imported_bank_last4="1234",
            summary="服务费",
        )
