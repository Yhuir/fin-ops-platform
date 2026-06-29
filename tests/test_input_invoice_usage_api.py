from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus
from io import BytesIO
import json
from pathlib import Path
import tempfile
import unittest
from urllib.parse import quote

from openpyxl import load_workbook

from fin_ops_platform.app.server import Application
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import InvoiceType, TransactionDirection
from fin_ops_platform.domain.models import BankTransaction, Counterparty, Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import InputInvoiceUsageOaReverseStatus
from fin_ops_platform.services.input_invoice_usage_read_model_detail_service import (
    InputInvoiceUsageReadModelDetailService,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.invoice_usage_collection_source_versions import input_invoice_usage_source_versions
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.target_oa_applicant_token_provider import TargetOaApplicantTokenProvider
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService
from fin_ops_platform.services.workbench_relation_command_service import WorkbenchRelationCommandError
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


class FakeTargetOaDraftClientProvider:
    def __init__(self, client: FakeOaDraftClient | None = None, *, fail: bool = False) -> None:
        self.client = client or FakeOaDraftClient()
        self.fail = fail
        self.requested_codes: list[str] = []

    def draft_client_for(self, target_applicant_code: str) -> FakeOaDraftClient:
        self.requested_codes.append(target_applicant_code)
        if self.fail:
            from fin_ops_platform.services.input_invoice_usage_oa_reverse_service import (
                InputInvoiceUsageOaReverseMissingClientError,
            )

            raise InputInvoiceUsageOaReverseMissingClientError("目标 OA 申请人凭据未配置。")
        return self.client


class RecordingOaLoginClient:
    def __init__(self, token: str = "target-applicant-token") -> None:
        self.token = token
        self.calls: list[tuple[str, str]] = []

    def login(self, username: str, password: str) -> str:
        self.calls.append((username, password))
        return self.token


class FailingRelationCommandService:
    def __init__(self) -> None:
        self.confirm_calls: list[dict[str, object]] = []

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        raise WorkbenchRelationCommandError(
            "workbench_relation_read_model_not_fresh",
            "Workbench relation read model is not fresh. Refresh and retry the mutation.",
            payload={
                "read_model_status": "stale",
                "read_model_stale_reasons": ["dirty_scope:2026-05"],
                "read_model_scope_keys": ["2026-05"],
                "refresh_enqueued": True,
            },
        )


class StaticInputInvoiceUsageReadRepository:
    def __init__(self, row: dict[str, object], *, refresh_status: str = "fresh") -> None:
        self.row = dict(row)
        self.refresh_status = refresh_status
        self.row_id_calls: list[str] = []

    def get_input_invoice_usage_row_by_row_id(self, row_id: str) -> dict[str, object] | None:
        self.row_id_calls.append(str(row_id))
        if str(self.row.get("id")) != str(row_id):
            return None
        return {
            "row": dict(self.row),
            "refresh_status": self.refresh_status,
            "source_versions": input_invoice_usage_source_versions(),
            "read_model_scope_key": "2026-05",
        }


class FailingInputInvoiceUsageQueryService(InputInvoiceUsageQueryService):
    def row_relation_details(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("relation detail must be served from input_invoice_usage read model")


class RecordingReadModelRefreshQueue:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, **kwargs: object) -> None:
        self.refreshes.append(
            (
                str(kwargs.get("scope_type") or ""),
                str(kwargs.get("scope_key") or ""),
                str(kwargs.get("reason") or ""),
            )
        )


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

    def test_rows_and_relation_details_return_multi_relation_totals_for_oa_bank_and_invoice(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice_a = self._invoice("inv-multi-a", "2201", "多关系供应商A", total_with_tax="40.00")
            invoice_b = self._invoice("inv-multi-b", "2202", "多关系供应商B", total_with_tax="60.00")
            bank_a = self._bank("bank-multi-a", "40.00")
            bank_b = self._bank("bank-multi-b", "60.00")
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-multi-relation",
                row_ids=[invoice_a.id, invoice_b.id, "oa-multi-a", "oa-multi-b", bank_a.id, bank_b.id],
                row_types=["invoice", "invoice", "oa", "oa", "bank", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            self._install_service(
                app,
                invoices=[invoice_a, invoice_b],
                transactions=[bank_a, bank_b],
                pair_service=pair_service,
                oa_projection=StaticOAProjection(
                    [
                        self._oa("oa-multi-a", "刘际涛", "40.00", apply_type="支付申请"),
                        self._oa("oa-multi-b", "张三", "60.00", apply_type="支付申请"),
                    ]
                ),
            )

            rows_response = app.handle_request("GET", "/api/input-invoice-usage/rows?sort_field=invoice_no&sort_direction=asc")
            rows_payload = json.loads(rows_response.body)
            row = next(item for item in rows_payload["rows"] if item["invoiceId"] == invoice_a.id)
            row_id = row["id"]
            oa_detail_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows/{row_id}/relation-details?kind=oa",
            )
            bank_detail_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows/{row_id}/relation-details?kind=bank",
            )
            invoice_detail_response = app.handle_request(
                "GET",
                f"/api/input-invoice-usage/rows/{row_id}/relation-details?kind=invoice",
            )

        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(row["oa"]["relationCount"], 2)
        self.assertEqual(row["oa"]["amount"], "100.00")
        self.assertEqual(row["oa"]["hasMultiple"], True)
        self.assertEqual(row["bankTransactions"]["relationCount"], 2)
        self.assertEqual(row["bankTransactions"]["amount"], "100.00")
        self.assertEqual(row["bankTransactions"]["hasMultiple"], True)
        self.assertEqual(row["invoiceRelations"]["relationCount"], 2)
        self.assertEqual(row["invoiceRelations"]["totalWithTax"], "100.00")
        self.assertEqual(row["invoiceRelations"]["hasMultiple"], True)
        self.assertEqual(oa_detail_response.status_code, 200)
        self.assertEqual(bank_detail_response.status_code, 200)
        self.assertEqual(invoice_detail_response.status_code, 200)
        self.assertEqual(len(json.loads(oa_detail_response.body)["summaries"]), 2)
        self.assertEqual(len(json.loads(bank_detail_response.body)["summaries"]), 2)
        self.assertEqual(len(json.loads(invoice_detail_response.body)["summaries"]), 2)

    def test_relation_details_use_input_invoice_usage_read_model_row_without_live_rebuild(self) -> None:
        row = {
            "id": "usage-row-read-model",
            "invoiceId": "inv-read-model",
            "oa": {
                "relationCount": 2,
                "hasMultiple": True,
                "detailMode": "list",
                "summaries": [
                    {"oaId": "oa-a", "applicantName": "刘际涛", "amount": "40.00", "relationStatus": "linked"},
                    {"oaId": "oa-b", "applicantName": "张三", "amount": "60.00", "relationStatus": "linked"},
                ],
            },
            "bankTransactions": {"relationCount": 0, "summaries": []},
            "invoiceRelations": {"relationCount": 1, "summaries": [{"invoiceId": "inv-read-model"}]},
        }
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            repository = StaticInputInvoiceUsageReadRepository(row)
            app._input_invoice_usage_sql_read_repository = repository
            app._input_invoice_usage_query_service = FailingInputInvoiceUsageQueryService(
                import_service=ImportNormalizationService()
            )

            response = app.handle_request(
                "GET",
                "/api/input-invoice-usage/rows/usage-row-read-model/relation-details?kind=oa",
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.row_id_calls, ["usage-row-read-model"])
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["rowId"], "usage-row-read-model")
        self.assertEqual(payload["relationCount"], 2)
        self.assertEqual([summary["oaId"] for summary in payload["summaries"]], ["oa-a", "oa-b"])

    def test_relation_details_require_sql_repository_in_production_without_live_rebuild(self) -> None:
        queue = RecordingReadModelRefreshQueue()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._input_invoice_usage_sql_read_repository = None
        app._input_invoice_usage_query_service = FailingInputInvoiceUsageQueryService(
            import_service=ImportNormalizationService()
        )

        response = app._handle_api_input_invoice_usage_relation_details(
            "usage-row-missing-repository",
            {"kind": ["oa"]},
        )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, int(HTTPStatus.ACCEPTED))
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["readModelStatus"], "refreshing")
        self.assertEqual(payload["detailAvailable"], False)
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(
            queue.refreshes,
            [("input_invoice_usage", "all", "api_detail_sql_repository_unavailable")],
        )

    def test_relation_details_compare_source_versions_with_row_scope(self) -> None:
        current_versions = {
            **input_invoice_usage_source_versions(),
            "workbench_relation_source_versions": {"source_version": "2026-05-current"},
        }
        stale_all_versions = {
            **input_invoice_usage_source_versions(),
            "workbench_relation_source_versions": {"source_version": "all-stale"},
        }
        row = {
            "id": "usage-row-scoped",
            "invoiceId": "inv-scoped",
            "oa": {
                "relationCount": 2,
                "hasMultiple": True,
                "detailMode": "list",
                "summaries": [
                    {"oaId": "oa-a", "applicantName": "刘际涛", "amount": "40.00", "relationStatus": "linked"},
                    {"oaId": "oa-b", "applicantName": "张三", "amount": "60.00", "relationStatus": "linked"},
                ],
            },
            "bankTransactions": {"relationCount": 0, "summaries": []},
            "invoiceRelations": {"relationCount": 1, "summaries": [{"invoiceId": "inv-scoped"}]},
        }
        repository = type(
            "ScopedInputInvoiceUsageReadRepository",
            (),
            {
                "get_input_invoice_usage_row_by_row_id": lambda _self, _row_id: {
                    "row": row,
                    "refresh_status": "fresh",
                    "source_versions": current_versions,
                    "read_model_scope_key": "2026-05",
                }
            },
        )()
        provider_calls: list[str | None] = []

        def source_versions_provider(*, scope_key: str | None = None) -> dict[str, object]:
            provider_calls.append(scope_key)
            return current_versions if scope_key == "2026-05" else stale_all_versions

        refreshes: list[tuple[str, str]] = []
        service = InputInvoiceUsageReadModelDetailService(
            repository=repository,
            enqueue_refresh=lambda scope_key, reason: refreshes.append((scope_key, reason)) is None,
            source_versions_provider=source_versions_provider,
        )

        payload = service.relation_details("usage-row-scoped", kind="oa")

        self.assertEqual(provider_calls, ["2026-05"])
        self.assertEqual(refreshes, [])
        assert payload is not None
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["rowId"], "usage-row-scoped")
        self.assertEqual(payload["relationCount"], 2)

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

    def test_oa_reverse_preview_marks_candidate_oa_relation_as_non_selectable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            invoice = self._invoice("inv-candidate-oa", "3002", "候选供应商", total_with_tax="109.00")
            oa_projection = StaticOAProjection([self._oa("oa-candidate-existing", "胡蓉", "109.00")])
            relation_facade = FakeWorkbenchRelationFacade(
                [
                    {
                        "row_id": invoice.id,
                        "row_type": "input_invoice",
                        "relation_status": "candidate",
                        "group_ids": ["decision-open-oa-candidate"],
                        "linked_oa": [],
                        "linked_bank_transactions": [],
                        "linked_input_invoices": [],
                        "linked_output_invoices": [],
                    }
                ],
                groups=[
                    {
                        "group_id": "decision-open-oa-candidate",
                        "scope_month": "2026-05",
                        "relation_source": "automatic_decision",
                        "relation_status": "candidate",
                        "oa_row_ids": ["oa-candidate-existing"],
                        "bank_transaction_ids": [],
                        "input_invoice_ids": [invoice.id],
                        "output_invoice_ids": [],
                        "payload": {
                            "group_id": "decision-open-oa-candidate",
                            "row_ids": ["oa-candidate-existing", invoice.id],
                            "row_types": ["oa", "invoice"],
                            "relation_mode": "automatic_decision",
                            "relation_status": "candidate",
                            "amount_check": {"matched": True},
                        },
                    }
                ],
            )
            self._install_service(
                app,
                invoices=[invoice],
                oa_projection=oa_projection,
                relation_facade=relation_facade,
            )

            response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/preview",
                body=json.dumps(
                    {
                        "source": "explicitSelection",
                        "invoiceIds": [invoice.id],
                        "targetApplicantCode": "chen_xiuyun",
                    }
                ),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["invoiceCount"], 0)
        self.assertFalse(payload["canCreateDraft"])
        self.assertEqual(payload["nextAction"], "no_valid_candidates")
        self.assertEqual(payload["invoiceRows"], [])
        self.assertEqual(len(payload["rejectedInvoices"]), 1)
        rejected = payload["rejectedInvoices"][0]
        self.assertEqual(rejected["invoiceId"], invoice.id)
        self.assertEqual(rejected["invoiceNo"], "3002")
        self.assertEqual(rejected["reasonCode"], "already_has_candidate_oa")
        self.assertEqual(rejected["oaRelationStatus"], "candidate")

    def test_oa_reverse_draft_route_creates_draft_then_waits_for_user_submission_confirmation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            client = FakeOaDraftClient()
            provider = FakeTargetOaDraftClientProvider(client)
            app._target_oa_applicant_token_provider_instance = provider
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
            history_response = app.handle_request("GET", "/api/input-invoice-usage/oa-reverse/submitted-history")

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["status"], "oa_draft_created")
        self.assertEqual(draft_payload["oaDetectionStatus"], "draft_created")
        self.assertTrue(draft_payload["canConfirmSubmission"])
        self.assertFalse(draft_payload["canRefreshStatus"])
        self.assertEqual(provider.requested_codes, ["zhou_jieying"])
        self.assertEqual(client.requests[0]["payload"]["data"]["userName"], "周洁莹")
        self.assertEqual(confirm_response.status_code, 200)
        confirmed_payload = json.loads(confirm_response.body)
        self.assertEqual(confirmed_payload["status"], "submitted_confirmed")
        self.assertEqual(confirmed_payload["oaDetectionStatus"], "user_confirmed_submitted")
        self.assertFalse(confirmed_payload["canRefreshStatus"])
        history_payload = json.loads(history_response.body)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_payload["items"][0]["targetApplicantName"], "周洁莹")
        self.assertEqual(history_payload["items"][0]["invoiceCount"], 1)
        self.assertNotIn("batchId", history_payload["items"][0])
        self.assertNotIn("invoiceIds", history_payload["items"][0])

    def test_oa_reverse_one_step_draft_route_uses_target_applicant_provider(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            client = FakeOaDraftClient()
            provider = FakeTargetOaDraftClientProvider(client)
            app._target_oa_applicant_token_provider_instance = provider
            self._install_service(
                app,
                invoices=[self._invoice("inv-one-step", "3101", "一步供应商", total_with_tax="188.00")],
                oa_projection=StaticOAProjection([]),
            )
            preview_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/preview",
                body=json.dumps(
                    {
                        "source": "explicitSelection",
                        "invoiceIds": ["inv-one-step"],
                        "targetApplicantCode": "chen_xiuyun",
                    }
                ),
            )
            preview_payload = json.loads(preview_response.body)

            draft_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/oa-draft",
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-one-step"],
                        "targetApplicantCode": "chen_xiuyun",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-one-step-api-1",
                    }
                ),
            )
            draft_payload = json.loads(draft_response.body)

        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["status"], "oa_draft_created")
        self.assertEqual(provider.requested_codes, ["chen_xiuyun"])
        self.assertEqual(client.requests[0]["payload"]["data"]["applicant"], "陈秀云")
        self.assertEqual(client.requests[0]["payload"]["isDraft"], True)

    def test_oa_reverse_staged_drafts_route_returns_created_drafts_for_recovery(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = FakeTargetOaDraftClientProvider()
            app._target_oa_applicant_token_provider_instance = provider
            self._install_service(
                app,
                invoices=[self._invoice("inv-staged-api", "3151", "暂存供应商", total_with_tax="188.00")],
                oa_projection=StaticOAProjection([]),
            )
            preview_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/preview",
                    body=json.dumps({"invoiceIds": ["inv-staged-api"], "targetApplicantCode": "chen_xiuyun"}),
                ).body
            )
            draft_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/oa-draft",
                    body=json.dumps(
                        {
                            "invoiceIds": ["inv-staged-api"],
                            "targetApplicantCode": "chen_xiuyun",
                            "expectedPreviewHash": preview_payload["previewHash"],
                            "idempotencyKey": "oa-reverse-staged-api",
                        }
                    ),
                ).body
            )
            staged_response = app.handle_request(
                "GET",
                "/api/input-invoice-usage/oa-reverse/staged-drafts",
            )

        self.assertEqual(staged_response.status_code, 200)
        staged_payload = json.loads(staged_response.body)
        self.assertEqual([item["batchId"] for item in staged_payload["items"]], [draft_payload["batchId"]])
        self.assertEqual(staged_payload["items"][0]["status"], "oa_draft_created")
        self.assertTrue(staged_payload["items"][0]["canConfirmSubmission"])
        self.assertEqual(staged_payload["items"][0]["invoiceRows"][0]["invoiceNo"], "3151")
        self.assertNotIn("submittedAt", staged_payload["items"][0])

    def test_oa_reverse_full_flow_uses_admin_saved_target_applicant_credential(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_identity_resolver(app)
            client = FakeOaDraftClient()
            login_client = RecordingOaLoginClient()
            created_tokens: list[str] = []
            app._target_oa_applicant_token_provider_instance = TargetOaApplicantTokenProvider(
                credential_service=app._oa_applicant_credential_service(),
                login_client=login_client,
                oa_client_factory=lambda token: created_tokens.append(token) or client,
            )
            self._install_service(
                app,
                invoices=[self._invoice("inv-full-flow", "3201", "闭环供应商", total_with_tax="288.00")],
                oa_projection=StaticOAProjection([]),
            )

            save_response = app.handle_request(
                "PUT",
                "/api/workbench/settings/oa-applicant-credentials/chen_xiuyun",
                headers=self._admin_headers(),
                body=json.dumps(
                    {
                        "targetApplicantName": "陈秀云",
                        "oaUsername": "chen_xiuyun_login",
                        "password": "correct-password",
                    }
                ),
            )
            preview_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/preview",
                    headers=self._full_access_headers(),
                    body=json.dumps(
                        {
                            "source": "explicitSelection",
                            "invoiceIds": ["inv-full-flow"],
                            "targetApplicantCode": "chen_xiuyun",
                        }
                    ),
                ).body
            )
            draft_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/oa-draft",
                headers=self._full_access_headers(),
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-full-flow"],
                        "targetApplicantCode": "chen_xiuyun",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-full-flow-api-1",
                    }
                ),
            )
            draft_payload = json.loads(draft_response.body)
            confirm_response = app.handle_request(
                "POST",
                f"/api/input-invoice-usage/oa-reverse/batches/{draft_payload['batchId']}/manual-oa-status",
                headers=self._full_access_headers(),
                body=json.dumps(
                    {
                        "decision": "submitted",
                        "expectedVersion": draft_payload["version"],
                        "idempotencyKey": "oa-reverse-full-flow-confirm-1",
                    }
                ),
            )
            history_response = app.handle_request(
                "GET",
                "/api/input-invoice-usage/oa-reverse/submitted-history",
                headers=self._full_access_headers(),
            )

        self.assertEqual(save_response.status_code, 200)
        self.assertNotIn("correct-password", save_response.body)
        self.assertEqual(draft_response.status_code, 200)
        self.assertEqual(draft_payload["status"], "oa_draft_created")
        self.assertNotIn("correct-password", draft_response.body)
        self.assertNotIn("target-applicant-token", draft_response.body)
        self.assertEqual(login_client.calls, [("chen_xiuyun_login", "correct-password")])
        self.assertEqual(created_tokens, ["target-applicant-token"])
        self.assertEqual(client.requests[0]["payload"]["data"]["applicant"], "陈秀云")
        self.assertEqual(client.requests[0]["payload"]["invoiceRows"][0]["invoiceNo"], "3201")
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(json.loads(confirm_response.body)["status"], "submitted_confirmed")
        history_payload = json.loads(history_response.body)
        self.assertEqual(history_response.status_code, 200)
        self.assertEqual(history_payload["items"][0]["targetApplicantName"], "陈秀云")
        self.assertEqual(history_payload["items"][0]["invoiceCount"], 1)
        self.assertEqual(history_payload["items"][0]["invoices"][0]["invoiceNo"], "3201")
        self.assertNotIn("batchId", history_payload["items"][0])
        self.assertNotIn("oaDraftId", history_payload["items"][0])

    def test_oa_reverse_one_step_draft_route_returns_missing_credential_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = FakeTargetOaDraftClientProvider(fail=True)
            app._target_oa_applicant_token_provider_instance = provider
            self._install_service(
                app,
                invoices=[self._invoice("inv-one-step", "3101", "一步供应商", total_with_tax="188.00")],
                oa_projection=StaticOAProjection([]),
            )
            preview_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/preview",
                    body=json.dumps({"invoiceIds": ["inv-one-step"], "targetApplicantCode": "chen_xiuyun"}),
                ).body
            )

            draft_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/oa-draft",
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-one-step"],
                        "targetApplicantCode": "chen_xiuyun",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-one-step-missing-credential",
                    }
                ),
            )
            payload = json.loads(draft_response.body)

        self.assertEqual(draft_response.status_code, 503)
        self.assertEqual(payload["error"], "oa_reverse_missing_oa_client")
        self.assertEqual(provider.requested_codes, ["chen_xiuyun"])

    def test_oa_reverse_not_submitted_api_flow_returns_to_create_ready_and_recreates(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = FakeTargetOaDraftClientProvider()
            app._target_oa_applicant_token_provider_instance = provider
            self._install_service(
                app,
                invoices=[self._invoice("inv-recreate", "3301", "重建供应商", total_with_tax="388.00")],
                oa_projection=StaticOAProjection([]),
            )
            preview_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/preview",
                    body=json.dumps({"invoiceIds": ["inv-recreate"], "targetApplicantCode": "chen_xiuyun"}),
                ).body
            )
            first_draft_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/oa-draft",
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-recreate"],
                        "targetApplicantCode": "chen_xiuyun",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-recreate-first",
                    }
                ),
            )
            first_draft_payload = json.loads(first_draft_response.body)
            not_submitted_response = app.handle_request(
                "POST",
                f"/api/input-invoice-usage/oa-reverse/batches/{first_draft_payload['batchId']}/manual-oa-status",
                body=json.dumps(
                    {
                        "decision": "not_submitted",
                        "expectedVersion": first_draft_payload["version"],
                        "idempotencyKey": "oa-reverse-recreate-not-submitted",
                    }
                ),
            )
            recreate_response = app.handle_request(
                "POST",
                "/api/input-invoice-usage/oa-reverse/oa-draft",
                body=json.dumps(
                    {
                        "invoiceIds": ["inv-recreate"],
                        "targetApplicantCode": "chen_xiuyun",
                        "expectedPreviewHash": preview_payload["previewHash"],
                        "idempotencyKey": "oa-reverse-recreate-second",
                    }
                ),
            )

        self.assertEqual(first_draft_response.status_code, 200)
        marked_payload = json.loads(not_submitted_response.body)
        self.assertEqual(not_submitted_response.status_code, 200)
        self.assertEqual(marked_payload["status"], "not_submitted")
        self.assertTrue(marked_payload["canCreateDraft"])
        self.assertIsNone(marked_payload["oaDraftId"])
        self.assertIsNone(marked_payload["oaDraftUrl"])
        recreated_payload = json.loads(recreate_response.body)
        self.assertEqual(recreate_response.status_code, 200)
        self.assertEqual(recreated_payload["status"], "oa_draft_created")
        self.assertNotEqual(recreated_payload["batchId"], first_draft_payload["batchId"])
        self.assertEqual(provider.requested_codes, ["chen_xiuyun", "chen_xiuyun"])

    def test_oa_reverse_status_refresh_returns_relation_command_conflict_without_saving_detected_batch(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            provider = FakeTargetOaDraftClientProvider()
            app._target_oa_applicant_token_provider_instance = provider
            relation_command = FailingRelationCommandService()
            app._workbench_relation_command_service = lambda *args, **kwargs: relation_command
            oa_projection = StaticOAProjection([])
            self._install_service(
                app,
                invoices=[self._invoice("inv-refresh", "3401", "刷新供应商", total_with_tax="99.72")],
                oa_projection=oa_projection,
            )
            preview_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/preview",
                    body=json.dumps({"invoiceIds": ["inv-refresh"], "targetApplicantCode": "chen_xiuyun"}),
                ).body
            )
            draft_payload = json.loads(
                app.handle_request(
                    "POST",
                    "/api/input-invoice-usage/oa-reverse/oa-draft",
                    body=json.dumps(
                        {
                            "invoiceIds": ["inv-refresh"],
                            "targetApplicantCode": "chen_xiuyun",
                            "expectedPreviewHash": preview_payload["previewHash"],
                            "idempotencyKey": "oa-reverse-refresh-conflict",
                        }
                    ),
                ).body
            )
            oa_projection.records.append(
                self._oa(
                    "oa-refresh-409",
                    "陈秀云",
                    "99.72",
                    reason=f"created from {draft_payload['oaDraftId']}",
                )
            )
            service = app._input_invoice_usage_oa_reverse_service()
            batch = service._repository.get_batch(str(draft_payload["batchId"]))
            batch.status = InputInvoiceUsageOaReverseStatus.OA_SUBMISSION_DETECTING.value
            batch.oa_detection_status = "legacy_detection_pending"
            batch.version = int(draft_payload["version"]) + 1
            service._repository.save_batch(batch)

            refresh_response = app.handle_request(
                "POST",
                f"/api/input-invoice-usage/oa-reverse/batches/{draft_payload['batchId']}/oa-status/refresh",
                body=json.dumps({"expectedVersion": batch.version}),
            )
            saved_batch = service._repository.get_batch(str(draft_payload["batchId"]))

        payload = json.loads(refresh_response.body)
        self.assertEqual(refresh_response.status_code, 409)
        self.assertEqual(payload["error"], "workbench_relation_read_model_not_fresh")
        self.assertEqual(payload["details"]["read_model_status"], "stale")
        self.assertTrue(payload["details"]["refresh_enqueued"])
        self.assertEqual(len(relation_command.confirm_calls), 1)
        self.assertEqual(relation_command.confirm_calls[0]["relation_mode"], "input_invoice_oa_reverse")
        self.assertEqual(saved_batch.status, InputInvoiceUsageOaReverseStatus.OA_SUBMISSION_DETECTING.value)
        self.assertEqual(saved_batch.version, int(draft_payload["version"]) + 1)
        self.assertIsNone(saved_batch.oa_row_id)
        self.assertEqual(saved_batch.oa_detection_status, "legacy_detection_pending")

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
        relation_facade: object | None = None,
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
            relation_facade=relation_facade
            or FakeWorkbenchRelationFacade.from_pair_service(
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
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        apply_type: str = "报销",
        reason: str = "费用报销",
    ) -> OAApplicationRecord:
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
            reason=reason,
            relation_code="in_progress",
            relation_label="进行中",
            relation_tone="success",
        )

    @staticmethod
    def _install_identity_resolver(app: object) -> None:
        def resolve_identity(token: str) -> OAUserIdentity:
            if token == "admin-token":
                return OAUserIdentity(
                    user_id="101",
                    username="YNSYLP005",
                    nickname="管理员",
                    display_name="管理员",
                    roles=["finance"],
                    permissions=["finops:app:view"],
                )
            return OAUserIdentity(
                user_id="102",
                username="FULL001",
                nickname="全操作用户",
                display_name="全操作用户",
                roles=["finance"],
                permissions=["finops:app:view"],
            )

        app._oa_identity_service.resolve_identity = resolve_identity

    @staticmethod
    def _admin_headers() -> dict[str, str]:
        return {"Authorization": "Bearer admin-token"}

    @staticmethod
    def _full_access_headers() -> dict[str, str]:
        return {"Authorization": "Bearer full-token"}


class RefreshingInputInvoiceUsageReadRepository:
    def list_input_invoice_usage_rows(self, **_kwargs: object) -> dict[str, object]:
        return {
            "rows": [],
            "pagination": {"page": 1, "pageSize": 50, "total": 0},
            "refresh_status": "stale",
        }
