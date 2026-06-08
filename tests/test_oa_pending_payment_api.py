from __future__ import annotations

from decimal import Decimal
import json
from pathlib import Path
import tempfile
from typing import Any
import unittest
from urllib.parse import quote

from fin_ops_platform.app.routes_oa_pending_payments import OaPendingPaymentApiRoutes
from fin_ops_platform.app.server import Application, build_application
from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_pending_payment_read_model_service import OaPendingPaymentReadModelService
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
from fin_ops_platform.services.postgres_repositories.read_models import (
    OA_PENDING_PAYMENT_FILTER_FIELDS,
    _oa_pending_payment_read_model_record,
)
from fin_ops_platform.services.invoice_usage_collection_source_versions import oa_pending_payment_source_versions
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class StaticOAProjection:
    def __init__(self, records: list[OAApplicationRecord]) -> None:
        self.records = records
        self.records_by_id = {record.id: record for record in records}

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        return list(self.records)

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        wanted = {str(row_id) for row_id in row_ids}
        return [record for record in self.records if record.id in wanted]


class FakeRelationFacade:
    def __init__(self, relations: list[dict[str, Any]]) -> None:
        self.relations = [dict(relation) for relation in relations]

    def get_by_row_ids(self, row_ids: list[str], **_kwargs: Any) -> dict[str, Any]:
        wanted = {str(row_id) for row_id in row_ids}
        groups = [self._group(relation) for relation in self.relations if wanted & set(relation.get("row_ids") or [])]
        return self._payload(groups)

    def list_by_month(self, _month: str, **_kwargs: Any) -> dict[str, Any]:
        return self._payload([self._group(relation) for relation in self.relations])

    def _payload(self, groups: list[dict[str, Any]]) -> dict[str, Any]:
        rows: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        for group in groups:
            group_id = str(group["group_id"])
            payload = group["payload"]
            for row_id, row_type in zip(payload["row_ids"], payload["row_types"]):
                key = (str(row_id), group_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"row_id": row_id, "row_type": row_type, "relation_status": "linked", "group_ids": [group_id]})
        return {"status": "fresh", "rows": rows, "groups": groups, "source_versions": {}, "read_model_scope_keys": []}

    @staticmethod
    def _group(relation: dict[str, Any]) -> dict[str, Any]:
        case_id = str(relation.get("case_id") or "")
        row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
        return {
            "group_id": case_id,
            "scope_month": relation.get("month_scope") or "2026-05",
            "oa_row_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "oa"],
            "bank_transaction_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "bank"],
            "input_invoice_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "invoice"],
            "output_invoice_ids": [],
            "payload": {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": row_types,
                "relation_mode": relation.get("relation_mode") or "",
                "amount_check": dict(relation.get("amount_check") or {}),
                "special_metadata": dict(relation.get("special_metadata") or {}),
            },
        }


class OaPendingPaymentApiTests(unittest.TestCase):
    def test_rows_filter_options_and_detail_routes_delegate_to_module_route_facade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            bank = BankTransaction(
                id="bank-api",
                account_no="622200001234",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="API供应商",
                amount=Decimal("100.00"),
                signed_amount=Decimal("-100.00"),
                txn_date="2026-05-21",
                trade_time="2026-05-21 10:00:00",
            )
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-api",
                row_ids=["oa-api", "bank-api"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            import_service = ImportNormalizationService(existing_transactions=[bank])
            service = OaPendingPaymentQueryService(
                import_service=import_service,
                relation_facade=FakeRelationFacade(pair_service.list_active_relations()),
                oa_projection=StaticOAProjection([self._oa("oa-api", "张三", "100.00")]),
            )
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(service)

            rows_response = app.handle_request("GET", "/api/oa-pending-payments/rows?page=1&page_size=20")
            filter_response = app.handle_request("GET", "/api/oa-pending-payments/filter-options")
            oa_response = app.handle_request("GET", "/api/oa-pending-payments/oa/oa-api/detail")
            bank_response = app.handle_request("GET", "/api/oa-pending-payments/bank-transactions/bank-api/detail")
            row_id = json.loads(rows_response.body)["rows"][0]["id"]
            relation_response = app.handle_request(
                "GET",
                f"/api/oa-pending-payments/rows/{row_id}/relation-details?kind=bank",
            )

        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(json.loads(rows_response.body)["rows"][0]["paymentStatus"]["code"], "paid")
        self.assertIn("oa_applicant", [field["field"] for field in json.loads(filter_response.body)["fields"]])
        self.assertEqual(json.loads(oa_response.body)["id"], "oa-api")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-api")
        self.assertEqual(json.loads(relation_response.body)["kind"], "bank")

    def test_routes_return_structured_validation_and_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                oa_projection=StaticOAProjection([]),
            )
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(service)

            invalid_page = app.handle_request("GET", "/api/oa-pending-payments/rows?page=0")
            invalid_sort = app.handle_request("GET", "/api/oa-pending-payments/rows?sort_field=bad")
            missing_oa = app.handle_request("GET", "/api/oa-pending-payments/oa/missing/detail")

        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(json.loads(invalid_page.body)["error"]["code"], "invalid_paging")
        self.assertEqual(invalid_sort.status_code, 400)
        self.assertEqual(json.loads(invalid_sort.body)["error"]["code"], "invalid_sort_field")
        self.assertEqual(missing_oa.status_code, 404)
        self.assertEqual(json.loads(missing_oa.body)["error"]["code"], "oa_not_found")

    def test_live_query_bank_account_and_direction_filter_options_and_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            matching_bank = BankTransaction(
                id="bank-account-api",
                account_no="622200001234",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="API供应商",
                amount=Decimal("100.00"),
                signed_amount=Decimal("-100.00"),
                txn_date="2026-05-21",
                trade_time="2026-05-21 10:00:00",
                imported_bank_name="建设银行",
                imported_bank_last4="1234",
            )
            other_bank = BankTransaction(
                id="bank-other-api",
                account_no="622200009999",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="其他供应商",
                amount=Decimal("200.00"),
                signed_amount=Decimal("-200.00"),
                txn_date="2026-05-22",
                trade_time="2026-05-22 10:00:00",
                imported_bank_name="工商银行",
                imported_bank_last4="9999",
            )
            pair_service = WorkbenchPairRelationService()
            pair_service.create_active_relation(
                case_id="case-account-api",
                row_ids=["oa-account-api", "bank-account-api"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            pair_service.create_active_relation(
                case_id="case-other-api",
                row_ids=["oa-other-api", "bank-other-api"],
                row_types=["oa", "bank"],
                relation_mode="manual_confirmed",
                created_by="tester",
                amount_check={"matched": True},
            )
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(existing_transactions=[matching_bank, other_bank]),
                relation_facade=FakeRelationFacade(pair_service.list_active_relations()),
                oa_projection=StaticOAProjection([
                    self._oa("oa-account-api", "张三", "100.00"),
                    self._oa("oa-other-api", "李四", "200.00"),
                ]),
            )
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(service)
            filters = quote(json.dumps([
                {"field": "bank_account", "operator": "in", "values": ["建设银行 1234"]},
                {"field": "bank_direction", "operator": "in", "values": ["outflow"]},
            ], ensure_ascii=False))
            mismatch_filters = quote(json.dumps([
                {"field": "bank_account", "operator": "in", "values": ["建设银行 1234"]},
                {"field": "bank_direction", "operator": "in", "values": ["inflow"]},
            ], ensure_ascii=False))

            filter_response = app.handle_request("GET", "/api/oa-pending-payments/filter-options")
            rows_response = app.handle_request("GET", f"/api/oa-pending-payments/rows?filters={filters}")
            mismatch_response = app.handle_request("GET", f"/api/oa-pending-payments/rows?filters={mismatch_filters}")

        fields = {field["field"]: field for field in json.loads(filter_response.body)["fields"]}
        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(fields["bank_account"]["label"], "银行账户")
        self.assertIn({"value": "建设银行 1234", "label": "建设银行 1234", "count": 1}, fields["bank_account"]["options"])
        self.assertEqual(fields["bank_direction"]["label"], "收支")
        self.assertIn({"value": "outflow", "label": "支出", "count": 2}, fields["bank_direction"]["options"])
        self.assertEqual(rows_response.status_code, 200)
        rows_payload = json.loads(rows_response.body)
        self.assertEqual(rows_payload["pagination"]["total"], 1)
        self.assertEqual(rows_payload["rows"][0]["oa"]["applicantName"], "张三")
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertEqual(json.loads(mismatch_response.body)["pagination"]["total"], 0)

    def test_production_rows_repository_unavailable_enqueues_refresh_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = None
        app._oa_pending_payment_api_routes = _read_model_routes(repository=None, queue=queue)

        response = app._handle_api_oa_pending_payments_rows({"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(payload["read_model_scope_key"], "2026-05")
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "api_sql_repository_unavailable")])

    def test_production_rows_source_version_stale_enqueues_refresh_without_stale_rows(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = type(
            "OaRepo",
            (),
            {
                "list_oa_pending_payment_rows": lambda *_args, **_kwargs: {
                    "rows": [{"id": "stale-row", "oa": {}, "paymentStatus": {}, "bankTransaction": {}, "invoice": {}}],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"rowCount": 1},
                    "refresh_status": "fresh",
                    "source_versions": {},
                }
            },
        )()
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)

        response = app._handle_api_oa_pending_payments_rows({"month": ["2026-05"], "page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertIn("oa_pending_payment_source_version_missing", payload["read_model_stale_reasons"])
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "api_source_versions_stale")])

    def test_production_filter_options_miss_enqueues_refresh_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = type(
            "OaRepo",
            (),
            {"list_oa_pending_payment_rows": lambda *_args, **_kwargs: None},
        )()
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)

        response = app._handle_api_oa_pending_payments_filter_options({"month": ["2026-05"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 202)
        self.assertEqual(payload["read_model_status"], "refreshing")
        self.assertEqual(queue.refreshes, [("oa_pending_payment", "2026-05", "api_miss")])

    def test_production_all_scope_fresh_rows_do_not_require_all_scope_row_or_enqueue_refresh(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = type(
            "OaRepo",
            (),
            {
                "list_oa_pending_payment_rows": lambda *_args, **_kwargs: {
                    "rows": [_read_model_row()],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"rowCount": 1},
                    "refresh_status": "fresh",
                    "source_versions": oa_pending_payment_source_versions(),
                    "read_model_scope_key": "all",
                }
            },
        )()
        app._oa_pending_payment_api_routes = _read_model_routes(
            repository=app._oa_pending_payment_sql_read_repository,
            queue=queue,
            query_service=_empty_query_service(),
        )

        response = app._handle_api_oa_pending_payments_rows({"page": ["1"], "page_size": ["50"]})
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["read_model_status"], "fresh")
        self.assertEqual(payload["read_model_scope_key"], "all")
        self.assertEqual(payload["rows"][0]["id"], "oa-payment-row-api")
        self.assertEqual(queue.refreshes, [])

    def test_read_endpoints_require_fin_ops_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["OTHER_USER"],
                readonly_export_usernames=[],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="blocked-user-id",
                username="BLOCKED_USER",
                nickname="未授权用户",
                display_name="未授权用户",
                roles=["finance"],
                permissions=[],
            )
            endpoints = [
                "/api/oa-pending-payments/rows",
                "/api/oa-pending-payments/filter-options",
                "/api/oa-pending-payments/oa/oa-api/detail",
                "/api/oa-pending-payments/bank-transactions/bank-api/detail",
                "/api/oa-pending-payments/invoices/inv-api/detail",
                "/api/oa-pending-payments/rows/row-api/relation-details?kind=bank",
            ]

            responses = [
                app.handle_request("GET", endpoint, headers={"Authorization": "Bearer blocked-token"})
                for endpoint in endpoints
            ]

        self.assertTrue(all(response.status_code == 403 for response in responses))
        self.assertTrue(all(json.loads(response.body)["error"] in {"forbidden", "permission_denied"} for response in responses))

    def test_production_detail_routes_use_sql_read_model_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=_read_model_row())
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)

        oa_response = app._handle_api_oa_pending_payments_oa_detail("oa-api")
        bank_response = app._handle_api_oa_pending_payments_bank_transaction_detail("bank-api")
        invoice_response = app._handle_api_oa_pending_payments_invoice_detail("inv-api")
        relation_response = app._handle_api_oa_pending_payments_relation_details(
            "oa-payment-row-api",
            {"kind": ["invoice"]},
        )

        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(json.loads(oa_response.body)["id"], "oa-api")
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-api")
        self.assertEqual(invoice_response.status_code, 200)
        self.assertEqual(json.loads(invoice_response.body)["id"], "inv-api")
        invoice_fields = json.loads(invoice_response.body)["sections"][0]["fields"]
        self.assertIn({"label": "进项发票方名称", "value": "API供应商"}, invoice_fields)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(json.loads(relation_response.body)["kind"], "invoice")
        self.assertEqual(queue.refreshes, [])

    def test_production_detail_stale_or_missing_read_model_refreshes_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=_read_model_row(), refresh_status="stale")
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)

        stale_response = app._handle_api_oa_pending_payments_oa_detail("oa-api")
        stale_payload = json.loads(stale_response.body)

        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=None, has_scope=False)
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)
        missing_scope_response = app._handle_api_oa_pending_payments_oa_detail("oa-api")
        missing_scope_payload = json.loads(missing_scope_response.body)

        self.assertEqual(stale_response.status_code, 202)
        self.assertEqual(stale_payload["read_model_status"], "refreshing")
        self.assertEqual(stale_payload["sections"], [])
        self.assertEqual(missing_scope_response.status_code, 202)
        self.assertEqual(missing_scope_payload["read_model_status"], "refreshing")
        self.assertEqual(missing_scope_payload["sections"], [])
        self.assertEqual(
            queue.refreshes,
            [
                ("oa_pending_payment", "2026-05", "api_detail_stale"),
                ("oa_pending_payment", "all", "api_detail_miss"),
            ],
        )

    def test_production_detail_fresh_miss_returns_not_found_and_invalid_relation_kind_is_400(self) -> None:
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": QueueRecorder()})()
        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=None, has_scope=True)
        app._oa_pending_payment_api_routes = _read_model_routes(
            repository=app._oa_pending_payment_sql_read_repository,
            queue=app._runtime_repositories.queue_repository,
        )

        missing_response = app._handle_api_oa_pending_payments_oa_detail("missing-oa")

        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=_read_model_row())
        app._oa_pending_payment_api_routes = _read_model_routes(
            repository=app._oa_pending_payment_sql_read_repository,
            queue=app._runtime_repositories.queue_repository,
        )
        invalid_kind_response = app._handle_api_oa_pending_payments_relation_details(
            "oa-payment-row-api",
            {"kind": ["bad"]},
        )

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(json.loads(missing_response.body)["error"]["code"], "oa_not_found")
        self.assertEqual(invalid_kind_response.status_code, 400)
        self.assertEqual(json.loads(invalid_kind_response.body)["error"]["code"], "invalid_relation_kind")

    def test_oa_source_versions_cover_relation_and_import_fact_dependencies(self) -> None:
        versions = oa_pending_payment_source_versions()

        self.assertIn("oa_pending_payment_source_version", versions)
        self.assertIn("oa_pending_payment_workbench_relation_schema_version", versions)
        self.assertIn("oa_pending_payment_bank_import_fact_schema_version", versions)
        self.assertIn("oa_pending_payment_input_invoice_import_fact_schema_version", versions)
        self.assertIn("oa_projection_sync_version", versions)

    def test_sql_read_model_records_expose_bank_account_and_direction_filters(self) -> None:
        record = _oa_pending_payment_read_model_record(_read_model_row(), "2026-05")

        self.assertIn("bank_account", OA_PENDING_PAYMENT_FILTER_FIELDS)
        self.assertIn("bank_direction", OA_PENDING_PAYMENT_FILTER_FIELDS)
        self.assertEqual(record["bank_account"], "建设银行 1234")
        self.assertEqual(record["bank_direction"], "outflow")

    @staticmethod
    def _oa(oa_id: str, applicant: str, amount: str) -> OAApplicationRecord:
        return OAApplicationRecord(
            id=oa_id,
            month="2026-05",
            section="审批通过",
            case_id=None,
            applicant=applicant,
            project_name="API项目",
            apply_type="报销",
            amount=amount,
            counterparty_name="API供应商",
            reason="API测试",
            relation_code="",
            relation_label="",
            relation_tone="",
            project_name_display="API项目",
        )


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class ExplodingOaPendingPaymentService:
    def list_rows(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production API must not live scan")

    def filter_options(self, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production filter options must not live scan")

    def oa_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production OA detail must not live scan")

    def bank_transaction_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production bank detail must not live scan")

    def invoice_detail(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production invoice detail must not live scan")

    def row_relation_details(self, *_args: object, **_kwargs: object) -> dict[str, object]:
        raise AssertionError("OA pending payment production relation detail must not live scan")


def _read_model_routes(
    *,
    repository: object | None,
    queue: QueueRecorder,
    query_service: object | None = None,
) -> OaPendingPaymentApiRoutes:
    query_service = query_service or ExplodingOaPendingPaymentService()
    return OaPendingPaymentApiRoutes(
        query_service,  # type: ignore[arg-type]
        read_model_service=OaPendingPaymentReadModelService(
            repository=repository,
            queue_repository=queue,
            query_service=query_service,  # type: ignore[arg-type]
            source_versions_provider=oa_pending_payment_source_versions,
        ),
    )


def _empty_query_service() -> OaPendingPaymentQueryService:
    return OaPendingPaymentQueryService(
        import_service=ImportNormalizationService(),
        oa_projection=StaticOAProjection([]),
    )


class OaDetailRepository:
    def __init__(
        self,
        *,
        row: dict[str, object] | None,
        refresh_status: str = "fresh",
        has_scope: bool = True,
        source_versions: dict[str, object] | None = None,
    ) -> None:
        self.row = row
        self.refresh_status = refresh_status
        self.has_scope = has_scope
        self.source_versions = source_versions if source_versions is not None else oa_pending_payment_source_versions()

    def get_oa_pending_payment_row_by_oa_id(self, _oa_id: str) -> dict[str, object] | None:
        return self._payload()

    def get_oa_pending_payment_row_by_bank_transaction_id(self, _bank_transaction_id: str) -> dict[str, object] | None:
        return self._payload()

    def get_oa_pending_payment_row_by_invoice_id(self, _invoice_id: str) -> dict[str, object] | None:
        return self._payload()

    def get_oa_pending_payment_row_by_row_id(self, _row_id: str) -> dict[str, object] | None:
        return self._payload()

    def _payload(self) -> dict[str, object] | None:
        if self.row is None and not self.has_scope:
            return None
        return {
            "row": self.row,
            "refresh_status": self.refresh_status,
            "source_versions": self.source_versions,
            "read_model_scope_key": "2026-05",
        }


def _read_model_row() -> dict[str, object]:
    return {
        "id": "oa-payment-row-api",
        "oa": {
            "id": "oa-api",
            "applicantName": "张三",
            "applicationType": "报销",
            "projectName": "API项目",
            "amount": "100.00",
            "month": "2026-05",
            "reason": "API测试",
            "counterpartyName": "API供应商",
            "detailAvailable": True,
        },
        "paymentStatus": {"code": "paid", "label": "已支付", "reason": "支出流水合计等于OA金额"},
        "bankTransaction": {
            "primaryBankTransactionId": "bank-api",
            "accountDetailNo": "detail-no-api",
            "enterpriseSerialNo": "enterprise-api",
            "voucherKind": "电子转账凭证",
            "voucherNo": "voucher-api",
            "bankName": "建设银行",
            "accountNo": "622200001234",
            "accountLast4": "1234",
            "directionLabel": "支出",
            "accountName": "云南溯源科技有限公司",
            "tradeTime": "2026-05-21 10:00:00",
            "debitAmount": "100.00",
            "creditAmount": "0.00",
            "balance": "900.00",
            "currency": "人民币元",
            "counterpartyName": "API供应商",
            "counterpartyAccountNo": "6222",
            "counterpartyBankName": "建设银行昆明支行",
            "bookedDate": "2026-05-21",
            "summary": "API测试流水",
            "remark": "API测试备注",
            "relationCount": 1,
            "hasMultiple": False,
            "detailMode": "single",
            "summaries": [
                {
                    "bankTransactionId": "bank-api",
                    "accountDetailNo": "detail-no-api",
                    "bankName": "建设银行",
                    "accountNo": "622200001234",
                    "accountLast4": "1234",
                    "directionLabel": "支出",
                    "tradeTime": "2026-05-21 10:00:00",
                    "amount": "100.00",
                    "counterpartyName": "API供应商",
                    "summary": "API测试流水",
                    "remark": "API测试备注",
                    "relationCaseId": "case-api",
                }
            ],
        },
        "invoice": {
            "primaryInvoiceId": "inv-api",
            "digitalInvoiceNo": "INV-API",
            "sellerName": "API供应商",
            "invoiceDate": "2026-05-22",
            "totalWithTax": "100.00",
            "relationCount": 1,
            "hasMultiple": False,
            "detailMode": "single",
            "summaries": [
                {
                    "invoiceId": "inv-api",
                    "digitalInvoiceNo": "INV-API",
                    "sellerName": "API供应商",
                    "invoiceDate": "2026-05-22",
                    "totalWithTax": "100.00",
                    "relationCaseId": "case-api",
                }
            ],
        },
    }


if __name__ == "__main__":
    unittest.main()
