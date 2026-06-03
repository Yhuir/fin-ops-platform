from __future__ import annotations

from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from openpyxl import load_workbook

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from tests.test_pending_invoice_service import FakeWorkbenchRelationFacade


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records
        self.records_by_id = {record.id: record for record in records}
        self.write_calls: list[str] = []

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def create_draft(self) -> None:
        self.write_calls.append("create_draft")


class InputInvoiceUsageApiTests(unittest.TestCase):
    def test_rows_route_returns_aggregated_rows_with_filters_sort_and_pagination(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(
                app,
                invoices=[
                    self._invoice("inv-api-1", "1001", "甲供应商", total_with_tax="30.00"),
                    self._invoice("inv-api-2", "1002", "乙供应商", total_with_tax="10.00"),
                    self._invoice("inv-api-3", "1003", "甲供应商", total_with_tax="20.00"),
                ],
            )
            filters = quote(json.dumps([{"field": "seller_name", "operator": "in", "values": ["甲供应商"]}]))

            response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows?page=1&page_size=1&filters={filters}&sort_field=total_with_tax&sort_direction=desc",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["pagination"], {"page": 1, "pageSize": 1, "total": 2})
        self.assertEqual(payload["rows"][0]["invoiceId"], "inv-api-1")
        self.assertEqual(payload["rows"][0]["invoice"]["sellerName"], "甲供应商")

    def test_filter_options_payment_rules_details_and_relation_routes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice = self._invoice("inv-detail", "2001", "详情供应商")
            bank = self._bank("bank-detail", "100.00")
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-detail",
                row_ids=[invoice.id, "oa-detail", bank.id],
                row_types=["invoice", "oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            self._install_service(
                app,
                invoices=[invoice],
                transactions=[bank],
                pair_service=pair_service,
                oa_projection=StaticOAProjection([self._oa("oa-detail", "陈秀云", "100.00")]),
            )

            rows_response = app.handle_request("GET", "/api/input-invoice-usage/rows")
            row_id = json.loads(rows_response.body)["rows"][0]["id"]
            filter_response = app.handle_request("GET", "/api/input-invoice-usage/filter-options?month=2026-05")
            rules_response = app.handle_request("GET", "/api/input-invoice-usage/payment-status-rules")
            invoice_response = app.handle_request("GET", "/api/input-invoice-usage/invoices/inv-detail/detail")
            bank_response = app.handle_request("GET", "/api/input-invoice-usage/bank-transactions/bank-detail/detail")
            oa_response = app.handle_request("GET", "/api/input-invoice-usage/oa/oa-detail/detail")
            relation_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows/{row_id}/relation-details?kind=oa",
            )

        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(rules_response.status_code, 200)
        self.assertEqual(invoice_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertIn("payment_status", [field["field"] for field in json.loads(filter_response.body)["fields"]])
        self.assertIn("rules", json.loads(rules_response.body))
        self.assertEqual(json.loads(invoice_response.body)["id"], "inv-detail")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-detail")
        self.assertTrue(json.loads(oa_response.body)["detailAvailable"])
        self.assertEqual(json.loads(relation_response.body)["kind"], "oa")

    def test_oa_reverse_preview_batch_and_missing_client_draft_routes_are_formal_workflow(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            oa_projection = StaticOAProjection([])
            self._install_service(
                app,
                invoices=[self._invoice("inv-preview", "3001", "预览供应商", total_with_tax="99.72")],
                oa_projection=oa_projection,
            )

            response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/preview",
                body=json.dumps(
                    {
                        "source": "explicitSelection",
                        "invoiceIds": ["inv-preview"],
                        "targetApplicantCode": "chen_xiuyun",
                    }
                ),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["invoiceCount"], 1)
        self.assertEqual(payload["totalWithTax"], "99.72")
        self.assertTrue(payload["canCreateDraft"])
        self.assertEqual(payload["nextAction"], "create_batch")
        self.assertEqual(payload["invoiceRows"][0]["invoiceId"], "inv-preview")
        self.assertIn({"code": "chen_xiuyun", "name": "陈秀云"}, payload["targetApplicants"])
        self.assertEqual(len(payload["previewHash"]), 64)
        self.assertEqual(oa_projection.write_calls, [])

        batch_response = app.handle_request(
            "POST",
            "/api/input-invoice-usage/oa-reverse/batches",
            body=json.dumps(
                {
                    "invoiceIds": ["inv-preview"],
                    "targetApplicantCode": "chen_xiuyun",
                    "expectedPreviewHash": payload["previewHash"],
                    "idempotencyKey": "oa-reverse-create-1",
                }
            ),
        )
        batch_payload = json.loads(batch_response.body)

        self.assertEqual(batch_response.status_code, 200)
        self.assertEqual(batch_payload["status"], "draft")
        self.assertEqual(batch_payload["version"], 1)
        self.assertEqual(batch_payload["invoiceRows"][0]["sellerName"], "预览供应商")

        get_response = app.handle_request(
            "GET",
            f"/api/input-invoice-usage/oa-reverse/batches/{batch_payload['batchId']}",
        )
        self.assertEqual(get_response.status_code, 200)
        self.assertEqual(json.loads(get_response.body)["batchId"], batch_payload["batchId"])

        draft_response = app.handle_request(
            "POST",
            f"/api/input-invoice-usage/oa-reverse/batches/{batch_payload['batchId']}/oa-draft",
            body=json.dumps({"expectedVersion": 1, "idempotencyKey": "oa-reverse-draft-1"}),
        )

        self.assertEqual(draft_response.status_code, 503)
        self.assertEqual(json.loads(draft_response.body)["error"], "oa_reverse_missing_oa_client")
        failed_response = app.handle_request(
            "GET",
            f"/api/input-invoice-usage/oa-reverse/batches/{batch_payload['batchId']}",
        )
        failed_payload = json.loads(failed_response.body)
        self.assertEqual(failed_payload["status"], "oa_draft_failed")
        self.assertEqual(failed_payload["version"], 2)

    def test_export_preview_and_download_use_current_input_invoice_usage_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(
                app,
                invoices=[
                    self._invoice("inv-export-1", "4001", "导出供应商甲", total_with_tax="30.00"),
                    self._invoice("inv-export-2", "4002", "导出供应商乙", total_with_tax="10.00"),
                ],
            )
            filters = quote(json.dumps([{"field": "seller_name", "operator": "contains", "value": "甲"}]))

            preview_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/export-preview?filters={filters}&sort_field=total_with_tax&sort_direction=desc",
            )
            export_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/export?filters={filters}&sort_field=total_with_tax&sort_direction=desc",
            )

        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["row_count"], 1)
        self.assertEqual(preview_payload["sample_rows"][0]["发票号码"], "4001")
        self.assertEqual(export_response.status_code, 200)
        self.assertIn(
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            export_response.headers["Content-Type"],
        )
        workbook = load_workbook(BytesIO(export_response.body), data_only=True)
        sheet = workbook["进项发票使用情况"]
        self.assertEqual(sheet["D2"].value, "4001")
        self.assertEqual(sheet["F2"].value, "导出供应商甲")

    def test_export_returns_refreshing_when_sql_read_model_is_not_fresh(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(app, invoices=[])
            app._input_invoice_usage_sql_read_repository = RefreshingInputInvoiceUsageReadRepository()

            preview_response = app.handle_request("GET", "/api/input-invoice-usage/export-preview?month=2026-05")
            export_response = app.handle_request("GET", "/api/input-invoice-usage/export?month=2026-05")

        self.assertEqual(preview_response.status_code, 202)
        self.assertEqual(json.loads(preview_response.body)["readModelStatus"], "refreshing")
        self.assertEqual(export_response.status_code, 202)
        self.assertEqual(json.loads(export_response.body)["readModelStatus"], "refreshing")

    def test_routes_return_structured_validation_and_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_service(app, invoices=[])

            invalid_page = app.handle_request("GET", "/api/input-invoice-usage/rows?page=0")
            invalid_sort = app.handle_request("GET", "/api/input-invoice-usage/rows?sort_field=unknown")
            invalid_filter = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows?filters={quote('[{\"field\":\"bad\",\"operator\":\"equals\",\"value\":\"x\"}]')}",
            )
            missing_detail = app.handle_request("GET", "/api/input-invoice-usage/invoices/missing/detail")

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
        oa_projection: object | None = None,
    ) -> None:
        import_service = ImportNormalizationService(
            existing_invoices=invoices,
            existing_transactions=transactions or [],
        )
        relation_service = pair_service or WorkbenchPairRelationService()
        app._import_service = import_service
        app._workbench_pair_relation_service = relation_service
        app._input_invoice_usage_query_service = InputInvoiceUsageQueryService(
            import_service=import_service,
            relation_facade=FakeWorkbenchRelationFacade.from_pair_service(
                pair_service=relation_service,
                transactions=list(transactions or []),
                invoices=list(invoices),
                oa_projection=oa_projection,
            ),
            oa_projection=oa_projection,
        )

    @staticmethod
    def _invoice(
        invoice_id: str,
        invoice_no: str,
        seller_name: str,
        *,
        total_with_tax: str = "100.00",
    ) -> Invoice:
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
    def _bank(transaction_id: str, amount: str) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="详情供应商",
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


class RefreshingInputInvoiceUsageReadRepository:
    def list_input_invoice_usage_rows(self, **_kwargs: object) -> dict[str, object]:
        return {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "refresh_status": "stale",
        }
