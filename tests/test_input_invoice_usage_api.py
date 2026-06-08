from __future__ import annotations

from decimal import Decimal
from io import BytesIO
import json
from pathlib import Path
import tempfile
from types import SimpleNamespace
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


class FakeOaDraftClient:
    def __init__(self) -> None:
        self.requests: list[dict[str, object]] = []

    def create_form_draft(self, *, form_id: int, payload: dict[str, object]) -> tuple[str, str]:
        self.requests.append({"form_id": form_id, "payload": payload})
        return "oa-draft-api-001", "https://oa.example.test/drafts/oa-draft-api-001"


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

    def test_bank_filter_options_and_invoice_date_sort_are_http_contract_fields(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice = self._invoice("inv-bank-filter", "2101", "筛选供应商甲", invoice_date="2026-05-22")
            other_invoice = self._invoice("inv-bank-other", "2102", "筛选供应商乙", invoice_date="2026-05-10")
            bank = self._bank("bank-filter", "100.00", bank_name="交通银行", account_last4="3847")
            other_bank = self._bank("bank-other", "100.00", bank_name="招商银行", account_last4="0011")
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-bank-filter",
                row_ids=[invoice.id, "oa-bank-filter", bank.id],
                row_types=["invoice", "oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            pair_service.create_active_relation(
                case_id="case-bank-other",
                row_ids=[other_invoice.id, "oa-bank-other", other_bank.id],
                row_types=["invoice", "oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            self._install_service(
                app,
                invoices=[invoice, other_invoice],
                transactions=[bank, other_bank],
                pair_service=pair_service,
                oa_projection=StaticOAProjection(
                    [
                        self._oa("oa-bank-filter", "樊祖芳", "100.00", apply_type="支付申请"),
                        self._oa("oa-bank-other", "王会计", "100.00", apply_type="报销"),
                    ]
                ),
            )

            filter_response = app.handle_request("GET", "/api/input-invoice-usage/filter-options")
            filters = quote(
                json.dumps(
                    [
                        {"field": "bank_account", "operator": "in", "values": ["交通银行 3847"]},
                        {"field": "bank_direction", "operator": "in", "values": ["outflow"]},
                        {"field": "oa_applicant", "operator": "in", "values": ["樊祖芳"]},
                        {"field": "oa_application_type", "operator": "in", "values": ["支付申请"]},
                    ]
                )
            )
            rows_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows?filters={filters}&sort_field=invoice_date&sort_direction=desc",
            )

        filter_payload = json.loads(filter_response.body)
        fields = {field["field"]: field for field in filter_payload["fields"]}
        bank_account_options = fields["bank_account"]["options"]
        bank_direction_options = fields["bank_direction"]["options"]
        rows_payload = json.loads(rows_response.body)

        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(rows_response.status_code, 200)
        self.assertIn("bank_account", fields)
        self.assertIn("bank_direction", fields)
        self.assertIn({"value": "交通银行 3847", "label": "交通银行 3847", "count": 1}, bank_account_options)
        self.assertIn({"value": "outflow", "label": "支出", "count": 2}, bank_direction_options)
        self.assertEqual(rows_payload["pagination"]["total"], 1)
        self.assertEqual(rows_payload["rows"][0]["invoiceId"], "inv-bank-filter")
        self.assertEqual(rows_payload["rows"][0]["bankTransactions"]["bankAccount"], "交通银行 3847")
        self.assertEqual(rows_payload["rows"][0]["bankTransactions"]["directionLabel"], "支出")

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

    def test_oa_reverse_draft_route_creates_draft_then_waits_for_user_submission_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            client = FakeOaDraftClient()
            app._etc_service = SimpleNamespace(oa_client=client)
            self._install_service(
                app,
                invoices=[self._invoice("inv-preview", "3001", "预览供应商", total_with_tax="99.72")],
                oa_projection=StaticOAProjection([]),
            )
            preview_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/preview",
                body=json.dumps(
                    {
                        "source": "explicitSelection",
                        "invoiceIds": ["inv-preview"],
                        "targetApplicantCode": "zhou_jieying",
                    }
                ),
            )
            preview_payload = json.loads(preview_response.body)
            batch_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/batches",
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-preview"],
                        "targetApplicantCode": "zhou_jieying",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-create-api-1",
                    }
                ),
            )
            batch_payload = json.loads(batch_response.body)
            draft_response = app.handle_request(
                "POST",
                f"/api/input-invoice-usage/oa-reverse/batches/{batch_payload['batchId']}/oa-draft",
                body=json.dumps({"expectedVersion": 1, "idempotencyKey": "oa-reverse-draft-api-1"}),
            )
            draft_payload = json.loads(draft_response.body)
            confirm_response = app.handle_request(
                "POST",
                f"/api/input-invoice-usage/oa-reverse/batches/{batch_payload['batchId']}/manual-oa-status",
                body=json.dumps(
                    {
                        "decision": "submitted",
                        "expectedVersion": draft_payload["version"],
                        "idempotencyKey": "oa-reverse-submit-confirm-api-1",
                    }
                ),
            )

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["status"], "oa_draft_created")
        self.assertEqual(draft_payload["oaDetectionStatus"], "draft_created")
        self.assertTrue(draft_payload["canConfirmSubmission"])
        self.assertFalse(draft_payload["canRefreshStatus"])
        self.assertEqual(client.requests[0]["payload"]["data"]["userName"], "周洁莹")
        self.assertEqual(confirm_response.status_code, 200)
        confirmed_payload = json.loads(confirm_response.body)
        self.assertEqual(confirmed_payload["status"], "oa_submission_detecting")
        self.assertEqual(confirmed_payload["oaDetectionStatus"], "user_confirmed_submitted")
        self.assertTrue(confirmed_payload["canRefreshStatus"])

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
            invalid_filters = quote(json.dumps([{"field": "bad", "operator": "equals", "value": "x"}]))
            invalid_filter = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows?filters={invalid_filters}",
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
        invoice_date: str = "2026-05-20",
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
            invoice_date=invoice_date,
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
    def _bank(
        transaction_id: str,
        amount: str,
        *,
        bank_name: str = "中国银行",
        account_last4: str = "1234",
    ) -> BankTransaction:
        return BankTransaction(
            id=transaction_id,
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="详情供应商",
            amount=Decimal(amount),
            signed_amount=-Decimal(amount),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
            imported_bank_name=bank_name,
            imported_bank_last4=account_last4,
        )

    @staticmethod
    def _oa(oa_id: str, applicant: str, amount: str, *, apply_type: str = "报销") -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="进行中",
            case_id=f"OA-{oa_id}",
            applicant=applicant,
            project_name="项目名称",
            apply_type=apply_type,
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
