from __future__ import annotations

from contextlib import contextmanager
from copy import deepcopy
from decimal import Decimal
from http import HTTPStatus
import json
import os
from pathlib import Path
import tempfile
from typing import Any, Callable
import unittest
from unittest.mock import patch
from urllib.parse import quote

from fin_ops_platform.app.routes_oa_pending_payments import OaPendingPaymentApiRoutes
from fin_ops_platform.app.server import Application, Response
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
from fin_ops_platform.services.oa_pending_payment_read_model_service import OaPendingPaymentReadModelService
from fin_ops_platform.services.oa_pending_payment_projection_rows import build_oa_pending_payment_rows
from fin_ops_platform.services.oa_pending_payment_query_contract import OaPendingPaymentError
from fin_ops_platform.services.oa_pending_payment_sql_projection import OA_PENDING_PAYMENT_POSTGRES_PROJECTOR_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import (
    OA_PENDING_PAYMENT_FILTER_FIELDS,
    _oa_pending_payment_read_model_record,
)
from fin_ops_platform.services.invoice_usage_collection_source_versions import oa_pending_payment_source_versions
from fin_ops_platform.services.read_model_freshness import source_version_mismatch_reasons
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService

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
            relation_status = str(group.get("relation_status") or payload.get("relation_status") or "linked")
            for row_id, row_type in zip(payload["row_ids"], payload["row_types"]):
                key = (str(row_id), group_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"row_id": row_id, "row_type": row_type, "relation_status": relation_status, "group_ids": [group_id]})
        return {"status": "fresh", "rows": rows, "groups": groups, "source_versions": {}, "read_model_scope_keys": []}

    @staticmethod
    def _group(relation: dict[str, Any]) -> dict[str, Any]:
        case_id = str(relation.get("case_id") or "")
        row_ids = [str(row_id) for row_id in list(relation.get("row_ids") or [])]
        row_types = [str(row_type) for row_type in list(relation.get("row_types") or [])]
        relation_status = str(relation.get("relation_status") or relation.get("relationStatus") or "linked")
        return {
            "group_id": case_id,
            "scope_month": relation.get("month_scope") or "2026-05",
            "relation_status": relation_status,
            "oa_row_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "oa"],
            "bank_transaction_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "bank"],
            "input_invoice_ids": [row_id for row_id, row_type in zip(row_ids, row_types) if row_type == "invoice"],
            "output_invoice_ids": [],
            "payload": {
                "case_id": case_id,
                "row_ids": row_ids,
                "row_types": row_types,
                "relation_status": relation_status,
                "relation_mode": relation.get("relation_mode") or "",
                "amount_check": dict(relation.get("amount_check") or {}),
                "special_metadata": dict(relation.get("special_metadata") or {}),
            },
        }


class OaPendingPaymentReadModelRepositoryPortTests(unittest.TestCase):
    def test_port_excludes_unrelated_read_model_methods(self) -> None:
        class Underlying:
            def list_oa_pending_payment_rows(self, **_kwargs: object) -> dict[str, object]:
                return {"rows": [], "refresh_status": "fresh"}

            def save_oa_pending_payment_rows(self, **_kwargs: object) -> None:
                return None

            def mark_oa_pending_payment_scope(self, **_kwargs: object) -> None:
                return None

            def prune_oa_pending_payment_scope_shards(self, _current_scope_keys: list[str]) -> None:
                return None

            def get_oa_pending_payment_row_by_row_id(self, _row_id: str) -> dict[str, object]:
                return {"row": {}}

            def get_oa_pending_payment_row_by_oa_id(self, _oa_id: str) -> dict[str, object]:
                return {"row": {}}

            def get_oa_pending_payment_row_by_bank_transaction_id(self, _bank_transaction_id: str) -> dict[str, object]:
                return {"row": {}}

            def get_oa_pending_payment_row_by_invoice_id(self, _invoice_id: str) -> dict[str, object]:
                return {"row": {}}

            def list_pending_invoice_rows(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("OA pending payment port must not expose pending invoice reads.")

            def workbench_relation_source_versions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("OA pending payment port must not expose workbench relation source versions.")

        port = OaPendingPaymentReadModelRepositoryPort(Underlying())

        self.assertEqual(port.list_oa_pending_payment_rows()["rows"], [])
        self.assertFalse(hasattr(port, "list_pending_invoice_rows"))
        self.assertFalse(hasattr(port, "workbench_relation_source_versions"))


class FakeCommandService:
    def __init__(self) -> None:
        self.link_calls: list[tuple[dict[str, Any], str]] = []

    def link_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        self.link_calls.append((dict(payload), actor_id))
        return {
            "success": True,
            "action": "oa_pending_payment_link_bank_transactions",
            "oaRowIds": payload.get("oa_row_ids") or payload.get("oaRowIds") or [],
            "bankTransactionIds": payload.get("bank_transaction_ids") or payload.get("bankTransactionIds") or [],
            "relation": {"status": "confirmed"},
            "autoWriteback": {"code": "written", "label": "已写回", "matched": True, "writebackCount": 1},
            "oaPaymentWritebacks": [{"code": "written", "label": "已写回", "flowId": "proc-api"}],
        }

    def writeback_paid(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        self.link_calls.append(({"writeback_paid": dict(payload)}, actor_id))
        return {
            "success": True,
            "action": "oa_pending_payment_writeback_paid",
            "oaRowIds": payload.get("oa_row_ids") or payload.get("oaRowIds") or [],
            "writebackCount": 1,
            "oaPaymentWriteback": {"code": "written", "label": "已写回", "flowId": "proc-api"},
            "oaPaymentWritebacks": [{"code": "written", "label": "已写回", "flowId": "proc-api"}],
        }


class FakeQueryService:
    def __init__(self) -> None:
        self.candidate_queries: list[tuple[dict[str, list[str]], str]] = []

    def bank_transaction_candidates(
        self,
        query: dict[str, list[str]],
        *,
        tenant_id: str,
    ) -> dict[str, Any]:
        self.candidate_queries.append((dict(query), tenant_id))
        return {
            "rows": [
                {
                    "id": "bank-api",
                    "counterpartyName": "API供应商",
                    "tradeTime": "2026-05-21 10:00:00",
                    "amount": "100.00",
                    "relationStatus": query.get("relation_status", ["all"])[0],
                    "relationStatusLabel": "未配对",
                    "linkedOaRowIds": query.get("oa_row_ids", []),
                }
            ],
            "pagination": {"page": 1, "pageSize": 100, "total": 1},
        }


class FakeRelationCommandService:
    def __init__(self) -> None:
        self.active_relations: list[dict[str, object]] = []
        self.confirm_calls: list[dict[str, object]] = []

    def active_relations_for_row_ids(self, row_ids: list[str]) -> list[dict[str, object]]:
        wanted = {str(row_id) for row_id in row_ids}
        return [
            relation
            for relation in self.active_relations
            if wanted & {str(row_id) for row_id in list(relation.get("row_ids") or [])}
        ]

    def confirm_relation(self, **kwargs: object) -> dict[str, object]:
        self.confirm_calls.append(dict(kwargs))
        relation = {
            "case_id": kwargs["case_id"],
            "row_ids": list(kwargs["row_ids"]),  # type: ignore[arg-type]
            "row_types": list(kwargs["row_types"]),  # type: ignore[arg-type]
            "relation_mode": kwargs["relation_mode"],
            "amount_check": dict(kwargs["amount_check"]),  # type: ignore[arg-type]
            "month_scope": kwargs["month_scope"],
        }
        self.active_relations.append(relation)
        return {
            "status": "confirmed",
            "relation": relation,
            "changed_case_ids": [kwargs["case_id"]],
            "affected_months": [kwargs["month_scope"]],
        }


class OaPendingPaymentApiTests(unittest.TestCase):
    def test_rows_service_preserves_pre_wrapped_repository_port(self) -> None:
        repository = ConditionalOaRowsRepository()
        service = OaPendingPaymentReadModelService(
            repository=OaPendingPaymentReadModelRepositoryPort(repository),
            queue_repository=QueueRecorder(),
            source_versions_provider=oa_pending_payment_source_versions,
        )

        result = service.conditional_rows(
            {"page": ["1"], "page_size": ["20"]},
            tenant_id="default",
            if_none_match=None,
        )

        self.assertEqual(result.status, HTTPStatus.OK)
        self.assertEqual(result.payload["read_model_status"], "fresh")
        self.assertEqual(result.payload["statistics"]["oa_count"], 1)
        self.assertEqual(repository.state_calls, 2)
        self.assertEqual(repository.data_calls, 1)
        self.assertEqual(repository.snapshot_entries, 1)

    def test_rows_cache_keeps_freshness_gate_and_skips_repeated_payload_query(self) -> None:
        repository = ConditionalOaRowsRepository()
        redis = OaRowsRedisRecorder()
        service = OaPendingPaymentReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            redis_helper=redis,
            source_versions_provider=oa_pending_payment_source_versions,
        )
        query = {"page": ["1"], "page_size": ["20"], "view_mode": ["in_progress"]}

        first = service.conditional_rows(query, tenant_id="tenant-a", if_none_match=None)
        second = service.conditional_rows(query, tenant_id="tenant-a", if_none_match=None)
        not_modified = service.conditional_rows(query, tenant_id="tenant-a", if_none_match=first.etag)

        self.assertEqual(first.status, HTTPStatus.OK)
        self.assertEqual(second.status, HTTPStatus.OK)
        self.assertEqual(not_modified.status, HTTPStatus.NOT_MODIFIED)
        self.assertEqual(repository.state_calls, 4)
        self.assertEqual(repository.data_calls, 1)
        self.assertEqual(repository.snapshot_entries, 1)
        self.assertEqual(len(redis.gets), 2)
        self.assertEqual(len(redis.sets), 1)
        self.assertEqual(first.payload, second.payload)
        self.assertNotIn("read_model_schema_version", second.payload)
        self.assertNotIn("refresh_enqueued", second.payload)

    def test_rows_cache_isolated_by_version_tenant_and_query(self) -> None:
        repository = ConditionalOaRowsRepository()
        redis = OaRowsRedisRecorder()
        service = OaPendingPaymentReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            redis_helper=redis,
            source_versions_provider=oa_pending_payment_source_versions,
        )
        first_query = {"page": ["1"], "page_size": ["20"]}

        service.conditional_rows(first_query, tenant_id="tenant-a", if_none_match=None)
        service.conditional_rows(first_query, tenant_id="tenant-b", if_none_match=None)
        service.conditional_rows({"page": ["2"], "page_size": ["20"]}, tenant_id="tenant-a", if_none_match=None)
        repository.version_token = "read-model-version-8"
        service.conditional_rows(first_query, tenant_id="tenant-a", if_none_match=None)

        self.assertEqual(repository.state_calls, 8)
        self.assertEqual(repository.data_calls, 4)
        self.assertEqual(repository.snapshot_entries, 4)
        self.assertEqual(len(redis.values), 4)
        self.assertEqual(len(set(redis.values.keys())), 4)

    def test_rows_cache_failure_falls_back_to_postgres_without_changing_contract(self) -> None:
        repository = ConditionalOaRowsRepository()
        service = OaPendingPaymentReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            redis_helper=FailingOaRowsRedis(),
            source_versions_provider=oa_pending_payment_source_versions,
        )
        query = {"page": ["1"], "page_size": ["20"]}

        first = service.conditional_rows(query, tenant_id="default", if_none_match=None)
        second = service.conditional_rows(query, tenant_id="default", if_none_match=None)

        self.assertEqual(first.status, HTTPStatus.OK)
        self.assertEqual(second.status, HTTPStatus.OK)
        self.assertEqual(repository.state_calls, 4)
        self.assertEqual(repository.data_calls, 2)
        self.assertEqual(repository.snapshot_entries, 2)
        self.assertEqual(first.payload, second.payload)

    def test_rows_cache_miss_rejects_a_version_change_before_payload_read(self) -> None:
        class RacingRepository(ConditionalOaRowsRepository):
            def oa_pending_payment_query_state(self, **kwargs: object) -> dict[str, object]:
                state = super().oa_pending_payment_query_state(**kwargs)
                if self.state_calls > 1:
                    state["version_token"] = "read-model-version-8"
                return state

        repository = RacingRepository()
        redis = OaRowsRedisRecorder()
        service = OaPendingPaymentReadModelService(
            repository=repository,
            queue_repository=QueueRecorder(),
            redis_helper=redis,
            source_versions_provider=oa_pending_payment_source_versions,
        )

        result = service.conditional_rows(
            {"page": ["1"], "page_size": ["20"]},
            tenant_id="default",
            if_none_match=None,
        )

        self.assertEqual(result.status, HTTPStatus.ACCEPTED)
        self.assertEqual(result.payload["read_model_status"], "refreshing")
        self.assertIsNone(result.payload["statistics"])
        self.assertEqual(repository.state_calls, 2)
        self.assertEqual(repository.data_calls, 0)
        self.assertEqual(repository.snapshot_entries, 1)
        self.assertEqual(redis.sets, [])

    def test_production_service_wires_page_query_repository_from_postgres_connection(self) -> None:
        connection = object()
        app = object.__new__(Application)
        app._state_store = type("StateStore", (), {"_connection": connection})()

        service = Application._oa_pending_payment_query_service(app)

        self.assertIs(service, Application._oa_pending_payment_query_service(app))
        self.assertIs(service._repository._connection, connection)  # type: ignore[union-attr]

    def test_rows_ignore_legacy_conditional_headers_and_return_canonical_contract(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            repository = ConditionalOaRowsRepository()
            app._oa_pending_payment_api_routes = _read_model_routes(
                repository=repository,
                queue=QueueRecorder(),
            )

            first = app.handle_request("GET", "/api/oa-pending-payments/rows?page=1&page_size=20")
            second = app.handle_request(
                "GET",
                "/api/oa-pending-payments/rows?page=1&page_size=20",
                headers={"If-None-Match": '"obsolete-read-model-version"'},
            )

        self.assertEqual(first.status_code, 200)
        self.assertEqual(second.status_code, 200)
        self.assertNotIn("ETag", first.headers)
        payload = json.loads(first.body)
        self.assertNotIn("readModelStatus", payload)
        self.assertNotIn("read_model_status", payload)
        self.assertNotIn("sourceVersions", payload)
        self.assertNotIn("operationBarrierTargets", payload)
        self.assertEqual(repository.state_calls, 4)
        self.assertEqual(repository.data_calls, 2)
        self.assertEqual(repository.snapshot_entries, 2)

    def test_rows_authentication_precedes_conditional_etag(self) -> None:
        repository = ConditionalOaRowsRepository()
        routes = _read_model_routes(repository=repository, queue=QueueRecorder())
        unauthorized = Response(status_code=401, body='{"error":"unauthorized"}')
        routes.configure_platform_ports(
            resolve_read_session=lambda _headers: (None, unauthorized),
            resolve_read_tenant=lambda _session: "default",
            write_auth_context=lambda _headers: ("tester", "default"),
            json_response=_json_test_response,
            load_json_body=lambda _body: ({}, None),
            error_response=_oa_pending_payment_error_test_response,
        )

        response = routes.route(
            "GET",
            "/api/oa-pending-payments/rows",
            {"page": ["1"]},
            None,
            {"If-None-Match": '"oa-pending-payment-forged"'},
        )

        self.assertIs(response, unauthorized)
        self.assertEqual(repository.state_calls, 0)
        self.assertEqual(repository.data_calls, 0)

    def test_rows_filter_options_and_detail_routes_delegate_to_module_route_facade(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_pending_payment_api_routes = _read_model_routes(
                repository=OaRowsRepository([_read_model_row()]),
                queue=QueueRecorder(),
            )

            rows_response = app.handle_request("GET", "/api/oa-pending-payments/rows?page=1&page_size=20")
            filter_response = app.handle_request("GET", "/api/oa-pending-payments/filter-options")
            oa_response = app.handle_request("GET", "/api/oa-pending-payments/oa/oa-api/detail")
            bank_response = app.handle_request("GET", "/api/oa-pending-payments/bank-transactions/bank-api/detail")
            row_id = json.loads(rows_response.body)["rows"][0]["id"]
            relation_response = app.handle_request(
                "GET",
                f"/api/oa-pending-payments/rows/{row_id}/relation-details?kind=bank",
            )
            oa_relation_response = app.handle_request(
                "GET",
                f"/api/oa-pending-payments/rows/{row_id}/relation-details?kind=oa",
            )

        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(filter_response.status_code, 404)
        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(oa_relation_response.status_code, 200)
        self.assertEqual(json.loads(rows_response.body)["rows"][0]["paymentStatus"]["code"], "paid")
        self.assertEqual(json.loads(rows_response.body)["rows"][0]["oa"]["applicationTime"], "2026-05-20")
        self.assertIn("oa_applicant", [field["field"] for field in json.loads(rows_response.body)["filterConfig"]])
        self.assertIn("bank_account", json.loads(rows_response.body)["filterOptions"])
        self.assertEqual(json.loads(oa_response.body)["id"], "oa-api")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-api")
        self.assertEqual(json.loads(relation_response.body)["kind"], "bank")
        self.assertEqual(json.loads(oa_relation_response.body)["kind"], "oa")

    def test_confirm_paid_route_is_removed_from_route_owner(self) -> None:
        routes = OaPendingPaymentApiRoutes(command_service=FakeCommandService())

        response = routes.route(
            "POST",
            "/api/oa-pending-payments/confirm-paid",
            {},
            json.dumps({"oa_row_id": "oa-api", "bank_transaction_id": "bank-api"}),
            {},
        )

        self.assertIsNone(response)
        self.assertFalse(hasattr(routes, "confirm_paid"))

        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app_response = app.handle_request(
                "POST",
                "/api/oa-pending-payments/confirm-paid",
                body=json.dumps({"oa_row_id": "oa-api", "bank_transaction_id": "bank-api"}),
            )

        self.assertEqual(app_response.status_code, 404)

    def test_link_bank_transactions_route_delegates_to_command_service_with_write_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(command_service=command_service)
            app._workbench_write_auth_context = lambda _headers: ("tester", "default")  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/oa-pending-payments/link-bank-transactions",
                body=json.dumps({"oa_row_ids": ["oa-api"], "bank_transaction_ids": ["bank-api"]}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_pending_payment_link_bank_transactions")
        self.assertEqual(payload["autoWriteback"]["label"], "已写回")
        self.assertNotIn("readModelRefresh", payload)
        self.assertEqual(command_service.link_calls, [({"oa_row_ids": ["oa-api"], "bank_transaction_ids": ["bank-api"]}, "tester")])

    def test_writeback_paid_route_delegates_to_command_service_with_write_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(command_service=command_service)
            app._workbench_write_auth_context = lambda _headers: ("tester", "default")  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/oa-pending-payments/writeback-paid",
                body=json.dumps({"oa_row_ids": ["oa-api"]}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["action"], "oa_pending_payment_writeback_paid")
        self.assertEqual(payload["writebackCount"], 1)
        self.assertNotIn("readModelRefresh", payload)
        self.assertEqual(payload["oaPaymentWriteback"]["flowId"], "proc-api")
        self.assertEqual(command_service.link_calls, [({"writeback_paid": {"oa_row_ids": ["oa-api"]}}, "tester")])

    def test_bank_transaction_candidates_route_delegates_to_tenant_query_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            query_service = FakeQueryService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(query_service=query_service)  # type: ignore[arg-type]

            response = app.handle_request(
                "GET",
                "/api/oa-pending-payments/bank-transaction-candidates?relation_status=unmatched&oa_row_ids=oa-api&oa_row_ids=oa-extra",
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["rows"][0]["id"], "bank-api")
        self.assertEqual(payload["rows"][0]["relationStatus"], "unmatched")
        self.assertEqual(payload["rows"][0]["linkedOaRowIds"], ["oa-api", "oa-extra"])
        query, tenant_id = query_service.candidate_queries[0]
        self.assertEqual(query["oa_row_ids"], ["oa-api", "oa-extra"])
        self.assertEqual(tenant_id, "default")

    def test_canonical_query_runtime_failure_returns_service_unavailable(self) -> None:
        class FailingQueryService:
            def rows(self, _query: dict[str, list[str]], *, tenant_id: str) -> dict[str, Any]:
                raise RuntimeError(f"canonical PostgreSQL unavailable for {tenant_id}")

        routes = OaPendingPaymentApiRoutes(query_service=FailingQueryService())  # type: ignore[arg-type]
        routes.configure_platform_ports(
            resolve_read_session=lambda _headers: (object(), None),
            resolve_read_tenant=lambda _session: "tenant-a",
            write_auth_context=lambda _headers: ("tester", "tenant-a"),
            json_response=_json_test_response,
            load_json_body=lambda _body: ({}, None),
            error_response=_oa_pending_payment_error_test_response,
        )

        response = routes.route(
            "GET",
            "/api/oa-pending-payments/rows",
            {"page": ["1"]},
            None,
            {},
        )

        self.assertEqual(response.status_code, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(
            json.loads(response.body)["error"]["code"],
            "oa_pending_payment_service_unavailable",
        )

    def test_candidate_bank_relation_is_not_visible_or_marked_paid(self) -> None:
        bank = BankTransaction(
            id="bank-candidate",
            account_no="622200001234",
            txn_direction=TransactionDirection.OUTFLOW,
            counterparty_name_raw="候选供应商",
            amount=Decimal("100.00"),
            signed_amount=Decimal("-100.00"),
            txn_date="2026-05-21",
            trade_time="2026-05-21 10:00:00",
        )
        rows = build_oa_pending_payment_rows(
            records=[self._oa("oa-candidate", "候选申请人", "100.00", detail_fields={"申请日期": "2026-05-20"})],
            relations=[
                {
                    "case_id": "candidate-oa-bank",
                    "row_ids": ["oa-candidate", "bank-candidate"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "unlinked_evidence",
                    "relation_status": "unlinked",
                    "amount_check": {"matched": True},
                }
            ],
            bank_transactions=[bank],
            invoices=[],
            payment_statuses_by_flow_id={},
            flow_id_resolver=lambda _record: None,
            scope_key="2026-05",
        )
        row = rows[0]

        self.assertEqual(row["bankTransaction"]["relationCount"], 0)
        self.assertEqual(row["bankTransaction"]["summaries"], [])
        self.assertEqual(row["bankTransaction"]["paidTotal"], "0.00")
        self.assertNotEqual(row["paymentStatus"]["code"], "paid")

    def test_rows_route_passes_in_progress_view_mode_to_read_model_repository(self) -> None:
        completed = _read_model_row()
        progress = deepcopy(_read_model_row())
        progress["id"] = "oa-payment-row-progress"
        progress["oa"]["id"] = "oa-progress"  # type: ignore[index]
        progress["oa"]["workflowStatus"] = "in_progress"  # type: ignore[index]
        routes = _read_model_routes(
            repository=OaRowsRepository([completed, progress]),
            queue=QueueRecorder(),
        )

        payload = routes.rows({"view_mode": ["in_progress"], "page": ["1"], "page_size": ["20"]})

        self.assertEqual([row["oa"]["id"] for row in payload["rows"]], ["oa-progress"])
        self.assertEqual(payload["viewMode"], "in_progress")

    def test_routes_return_structured_validation_and_not_found_errors(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_pending_payment_api_routes = _read_model_routes(
                repository=OaRowsRepository([_read_model_row()]),
                queue=QueueRecorder(),
            )

            invalid_page = app.handle_request("GET", "/api/oa-pending-payments/rows?page=0")
            invalid_sort = app.handle_request("GET", "/api/oa-pending-payments/rows?sort_field=bad")
            missing_oa = app.handle_request("GET", "/api/oa-pending-payments/oa/missing/detail")

        self.assertEqual(invalid_page.status_code, 400)
        self.assertEqual(json.loads(invalid_page.body)["error"]["code"], "invalid_paging")
        self.assertEqual(invalid_sort.status_code, 400)
        self.assertEqual(json.loads(invalid_sort.body)["error"]["code"], "invalid_sort_field")
        self.assertEqual(missing_oa.status_code, 404)
        self.assertEqual(json.loads(missing_oa.body)["error"]["code"], "oa_not_found")

    def test_read_model_bank_account_and_direction_filter_options_and_and_filters(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            matching_row = _read_model_row()
            matching_row["oa"]["id"] = "oa-account-api"  # type: ignore[index]
            other_row = deepcopy(_read_model_row())
            other_row["id"] = "oa-payment-row-other"
            other_row["oa"]["id"] = "oa-other-api"  # type: ignore[index]
            other_row["oa"]["applicantName"] = "李四"  # type: ignore[index]
            other_row["bankTransaction"]["primaryBankTransactionId"] = "bank-other-api"  # type: ignore[index]
            other_row["bankTransaction"]["bankName"] = "工商银行"  # type: ignore[index]
            other_row["bankTransaction"]["accountLast4"] = "9999"  # type: ignore[index]
            other_row["bankTransaction"]["accountNo"] = "622200009999"  # type: ignore[index]
            other_row["bankTransaction"]["bankAccount"] = "工商银行 9999"  # type: ignore[index]
            other_row["bankTransaction"]["direction"] = "outflow"  # type: ignore[index]
            app._oa_pending_payment_api_routes = _read_model_routes(
                repository=OaRowsRepository([matching_row, other_row]),
                queue=QueueRecorder(),
            )
            filters = quote(json.dumps([
                {"field": "bank_account", "operator": "in", "values": ["建设银行 1234"]},
                {"field": "bank_direction", "operator": "in", "values": ["outflow"]},
            ], ensure_ascii=False))
            mismatch_filters = quote(json.dumps([
                {"field": "bank_account", "operator": "in", "values": ["建设银行 1234"]},
                {"field": "bank_direction", "operator": "in", "values": ["inflow"]},
            ], ensure_ascii=False))

            filter_response = app.handle_request("GET", "/api/oa-pending-payments/rows?page=1&page_size=20")
            rows_response = app.handle_request("GET", f"/api/oa-pending-payments/rows?filters={filters}")
            mismatch_response = app.handle_request("GET", f"/api/oa-pending-payments/rows?filters={mismatch_filters}")

        filter_payload = json.loads(filter_response.body)
        fields = {field["field"]: field for field in filter_payload["filterConfig"]}
        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(fields["bank_account"]["label"], "银行账户")
        self.assertIn(
            {"value": "建设银行 1234", "label": "建设银行 1234", "count": 1},
            filter_payload["filterOptions"]["bank_account"],
        )
        self.assertEqual(fields["bank_direction"]["label"], "收支")
        self.assertIn(
            {"value": "outflow", "label": "支出", "count": 2},
            filter_payload["filterOptions"]["bank_direction"],
        )
        self.assertEqual(rows_response.status_code, 200)
        rows_payload = json.loads(rows_response.body)
        self.assertEqual(rows_payload["pagination"]["total"], 1)
        self.assertEqual(rows_payload["rows"][0]["oa"]["applicantName"], "张三")
        self.assertEqual(mismatch_response.status_code, 200)
        self.assertEqual(json.loads(mismatch_response.body)["pagination"]["total"], 0)

    def test_expected_source_versions_are_static_and_do_not_query_runtime_repositories(self) -> None:
        class OaRepo:
            def workbench_relation_source_versions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("expected versions must not query the OA repository")

        class WorkbenchRelationRepo:
            def workbench_relation_source_versions(self, **_kwargs: object) -> dict[str, object]:
                raise AssertionError("expected versions must not query the relation repository")

        app = object.__new__(Application)
        app._oa_pending_payment_sql_read_repository = OaRepo()
        app._workbench_relation_sql_read_repository = WorkbenchRelationRepo()

        payload = app._oa_pending_payment_expected_source_versions(scope_key="2026-05")

        self.assertEqual(
            payload["oa_pending_payment_postgres_projector_version"],
            OA_PENDING_PAYMENT_POSTGRES_PROJECTOR_VERSION,
        )
        self.assertNotIn("workbench_relation_source_versions", payload)

    def test_production_rows_passes_view_mode_to_sql_read_repository(self) -> None:
        queue = QueueRecorder()
        seen_kwargs: dict[str, object] = {}

        class OaRepo:
            def list_oa_pending_payment_rows(self, **kwargs: object) -> dict[str, object]:
                seen_kwargs.update(kwargs)
                return {
                    "rows": [_read_model_row()],
                    "pagination": {"page": 1, "pageSize": 50, "total": 1},
                    "summary": {"rowCount": 1},
                    "filterOptions": {},
                    "refresh_status": "fresh",
                    "source_versions": oa_pending_payment_source_versions(),
                }

        routes = _read_model_routes(repository=OaRepo(), queue=queue)

        payload = routes.rows({"view_mode": ["in_progress"], "page": ["1"], "page_size": ["50"]})

        self.assertEqual(seen_kwargs["view_mode"], "in_progress")
        self.assertEqual(payload["viewMode"], "in_progress")

    def test_legacy_application_rebuild_helpers_are_removed(self) -> None:
        removed_helpers = [
            "list_oa_pending_payment_scope_shards",
            "mark_oa_pending_payment_scope_empty",
            "rebuild_oa_pending_payment_read_model_scope",
            "_oa_pending_payment_live_rows",
            "_oa_pending_payment_live_rows_for_view",
        ]

        for helper_name in removed_helpers:
            with self.subTest(helper_name=helper_name):
                self.assertFalse(hasattr(Application, helper_name))

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
                "/api/oa-pending-payments/oa/oa-api/detail",
                "/api/oa-pending-payments/bank-transactions/bank-api/detail",
                "/api/oa-pending-payments/invoices/inv-api/detail",
                "/api/oa-pending-payments/rows/row-api/relation-details?kind=bank",
                "/api/oa-pending-payments/rows/row-api/relation-details?kind=oa",
            ]

            responses = [
                app.handle_request("GET", endpoint, headers={"Authorization": "Bearer blocked-token"})
                for endpoint in endpoints
            ]

        self.assertTrue(all(response.status_code == 403 for response in responses))
        self.assertTrue(all(json.loads(response.body)["error"] in {"forbidden", "permission_denied"} for response in responses))

    def test_module_owned_access_control_resolves_identity_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            repository = ConditionalOaRowsRepository()
            app._oa_pending_payment_api_routes = _read_model_routes(
                repository=repository,
                queue=QueueRecorder(),
            )
            identity_calls = 0

            def resolve_identity(_token: str) -> OAUserIdentity:
                nonlocal identity_calls
                identity_calls += 1
                return OAUserIdentity(
                    user_id="oa-reader-id",
                    username="OA_READER",
                    nickname="OA读取用户",
                    display_name="OA读取用户",
                    roles=["finance"],
                    permissions=[app._access_control_service.required_permission],
                )

            app._oa_identity_service.resolve_identity = resolve_identity
            response = app.handle_request(
                "GET",
                "/api/oa-pending-payments/rows?page=1&page_size=20",
                headers={"Authorization": "Bearer oa-reader-token"},
            )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(identity_calls, 1)

    def test_all_module_endpoints_require_module_owned_authentication(self) -> None:
        requests = [
            ("GET", "/api/oa-pending-payments/rows", None),
            ("GET", "/api/oa-pending-payments/bank-transaction-candidates", None),
            ("GET", "/api/oa-pending-payments/oa/oa-api/detail", None),
            ("GET", "/api/oa-pending-payments/bank-transactions/bank-api/detail", None),
            ("GET", "/api/oa-pending-payments/invoices/inv-api/detail", None),
            ("GET", "/api/oa-pending-payments/rows/row-api/relation-details?kind=bank", None),
            (
                "POST",
                "/api/oa-pending-payments/link-bank-transactions",
                {"oa_row_ids": ["oa-api"], "bank_transaction_ids": ["bank-api"]},
            ),
            ("POST", "/api/oa-pending-payments/writeback-paid", {"oa_row_ids": ["oa-api"]}),
        ]
        with patch.dict(os.environ, {"FIN_OPS_TEST_DEFAULT_AUTH": "0"}), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            responses = [
                app.handle_request(method, route, body=json.dumps(body) if body is not None else None)
                for method, route, body in requests
            ]

        self.assertTrue(all(response.status_code == HTTPStatus.UNAUTHORIZED for response in responses))
        self.assertTrue(all(json.loads(response.body)["error"] == "invalid_oa_session" for response in responses))

    def test_module_owned_write_auth_rejects_readonly_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["OA_READONLY"],
                readonly_export_usernames=["OA_READONLY"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="oa-readonly-id",
                username="OA_READONLY",
                nickname="OA只读用户",
                display_name="OA只读用户",
                roles=[],
                permissions=[],
            )
            headers = {"Authorization": "Bearer oa-readonly-token"}
            responses = [
                app.handle_request(
                    "POST",
                    "/api/oa-pending-payments/link-bank-transactions",
                    headers=headers,
                    body=json.dumps({"oa_row_ids": ["oa-api"], "bank_transaction_ids": ["bank-api"]}),
                ),
                app.handle_request(
                    "POST",
                    "/api/oa-pending-payments/writeback-paid",
                    headers=headers,
                    body=json.dumps({"oa_row_ids": ["oa-api"]}),
                ),
            ]

        self.assertTrue(all(response.status_code == HTTPStatus.FORBIDDEN for response in responses))
        self.assertTrue(all(json.loads(response.body)["error"] == "permission_denied" for response in responses))

    def test_production_detail_routes_use_sql_read_model_without_live_scan(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=_read_model_row())
        app._oa_pending_payment_api_routes = _read_model_routes(repository=app._oa_pending_payment_sql_read_repository, queue=queue)

        oa_response = _json_test_response_for_payload(app._oa_pending_payment_api_routes.oa_detail("oa-api"))
        bank_response = _json_test_response_for_payload(app._oa_pending_payment_api_routes.bank_transaction_detail("bank-api"))
        invoice_response = _json_test_response_for_payload(app._oa_pending_payment_api_routes.invoice_detail("inv-api"))
        relation_response = _json_test_response_for_payload(
            app._oa_pending_payment_api_routes.relation_details("oa-payment-row-api", {"kind": ["invoice"]})
        )
        oa_relation_response = _json_test_response_for_payload(
            app._oa_pending_payment_api_routes.relation_details("oa-payment-row-api", {"kind": ["oa"]})
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
        self.assertEqual(oa_relation_response.status_code, 200)
        self.assertEqual(json.loads(oa_relation_response.body)["kind"], "oa")
        self.assertEqual(json.loads(oa_relation_response.body)["title"], "OA关联明细")
        self.assertEqual(queue.refreshes, [])

    def test_production_detail_fresh_miss_returns_not_found_and_invalid_relation_kind_is_400(self) -> None:
        queue = QueueRecorder()
        app = object.__new__(Application)
        app._bootstrap_mode = "production"
        app._state_store = type("StateStore", (), {"storage_backend": "postgres"})()
        app._runtime_repositories = type("RuntimeRepos", (), {"queue_repository": queue})()
        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=None, has_scope=True)
        app._oa_pending_payment_api_routes = _read_model_routes(
            repository=app._oa_pending_payment_sql_read_repository,
            queue=app._runtime_repositories.queue_repository,
        )

        try:
            missing_response = _json_test_response_for_payload(app._oa_pending_payment_api_routes.oa_detail("missing-oa"))
        except Exception as exc:
            missing_response = _oa_pending_payment_error_test_response(exc)

        app._oa_pending_payment_sql_read_repository = OaDetailRepository(row=_read_model_row())
        app._oa_pending_payment_api_routes = _read_model_routes(
            repository=app._oa_pending_payment_sql_read_repository,
            queue=app._runtime_repositories.queue_repository,
        )
        try:
            invalid_kind_response = _json_test_response_for_payload(
                app._oa_pending_payment_api_routes.relation_details("oa-payment-row-api", {"kind": ["bad"]})
            )
        except Exception as exc:
            invalid_kind_response = _oa_pending_payment_error_test_response(exc)

        self.assertEqual(missing_response.status_code, 404)
        self.assertEqual(json.loads(missing_response.body)["error"]["code"], "oa_not_found")
        self.assertEqual(invalid_kind_response.status_code, 400)
        self.assertEqual(json.loads(invalid_kind_response.body)["error"]["code"], "invalid_relation_kind")
        self.assertEqual(queue.refreshes, [])

    def test_oa_source_versions_cover_relation_and_import_fact_dependencies(self) -> None:
        versions = oa_pending_payment_source_versions()

        self.assertIn("oa_pending_payment_source_version", versions)
        self.assertIn("oa_pending_payment_canonical_relation_schema_version", versions)
        self.assertIn("oa_pending_payment_bank_import_fact_schema_version", versions)
        self.assertIn("oa_pending_payment_input_invoice_import_fact_schema_version", versions)
        self.assertIn("oa_projection_sync_version", versions)

    def test_sql_read_model_records_expose_bank_account_and_direction_filters(self) -> None:
        record = _oa_pending_payment_read_model_record(_read_model_row(), "2026-05")

        self.assertIn("bank_account", OA_PENDING_PAYMENT_FILTER_FIELDS)
        self.assertIn("bank_direction", OA_PENDING_PAYMENT_FILTER_FIELDS)
        self.assertEqual(record["oa_workflow_status"], "completed")
        self.assertEqual(record["bank_account"], "建设银行 1234")
        self.assertEqual(record["bank_direction"], "outflow")

    @staticmethod
    def _oa(
        oa_id: str,
        applicant: str,
        amount: str,
        *,
        detail_fields: dict[str, object] | None = None,
        workflow_status: str | None = "completed",
    ) -> OAApplicationRecord:
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
            workflow_status=workflow_status,
            detail_fields=detail_fields or {},
            project_name_display="API项目",
        )


class QueueRecorder:
    def __init__(self) -> None:
        self.refreshes: list[tuple[str, str, str]] = []

    def enqueue_read_model_refresh(self, *, scope_type: str, scope_key: str, reason: str) -> None:
        self.refreshes.append((scope_type, scope_key, reason))


class OaRowsRedisRecorder:
    def __init__(self) -> None:
        self.values: dict[str, dict[str, object]] = {}
        self.gets: list[str] = []
        self.sets: list[tuple[str, int]] = []

    def get_json(self, key: str) -> dict[str, object] | None:
        self.gets.append(key)
        value = self.values.get(key)
        return deepcopy(value) if value is not None else None

    def set_json(self, key: str, value: dict[str, object], *, ttl_seconds: int) -> bool:
        self.values[key] = deepcopy(value)
        self.sets.append((key, ttl_seconds))
        return True


class FailingOaRowsRedis:
    def get_json(self, _key: str) -> dict[str, object] | None:
        raise RuntimeError("redis unavailable")

    def set_json(self, _key: str, _value: dict[str, object], *, ttl_seconds: int) -> bool:
        del ttl_seconds
        raise RuntimeError("redis unavailable")


class ConditionalOaRowsRepository:
    def __init__(self) -> None:
        self.state_calls = 0
        self.data_calls = 0
        self.snapshot_entries = 0
        self.version_token = "read-model-version-7"

    @contextmanager
    def oa_pending_payment_read_snapshot(self):
        self.snapshot_entries += 1
        yield self

    def oa_pending_payment_query_state(self, **_kwargs: object) -> dict[str, object]:
        self.state_calls += 1
        return {
            "status": "fresh",
            "scope_key": "all",
            "blocking_scope_keys": [],
            "stale_reasons": [],
            "version_token": self.version_token,
            "source_versions": oa_pending_payment_source_versions(),
        }

    def list_oa_pending_payment_rows(self, **kwargs: object) -> dict[str, object]:
        self.data_calls += 1
        page = int(kwargs.get("page") or 1)
        page_size = int(kwargs.get("page_size") or 50)
        return {
            "rows": [_read_model_row()],
            "pagination": {"page": page, "pageSize": page_size, "total": 1},
            "summary": {"rowCount": 1, "viewCounts": {"completed": 1, "in_progress": 0}},
            "statistics": {"oa_count": 1, "bank_transaction_count": 1},
            "filterOptions": {},
            "read_model_scope_key": "all",
        }


class OaRowsRepository:
    def __init__(self, rows: list[dict[str, object]]) -> None:
        self.rows = [deepcopy(row) for row in rows]

    def list_oa_pending_payment_rows(
        self,
        *,
        filters: str | None = None,
        page: int | str = 1,
        page_size: int | str = 50,
        view_mode: str | None = None,
        **_kwargs: object,
    ) -> dict[str, object]:
        filtered_rows = [deepcopy(row) for row in self.rows]
        if view_mode:
            filtered_rows = [row for row in filtered_rows if _row_oa(row).get("workflowStatus") == view_mode]
        for filter_spec in _decode_test_filters(filters):
            field = str(filter_spec.get("field") or "")
            values = {str(value) for value in list(filter_spec.get("values") or [])}
            if not values:
                continue
            if field == "bank_account":
                filtered_rows = [row for row in filtered_rows if _row_bank_account_label(row) in values]
            elif field == "bank_direction":
                filtered_rows = [row for row in filtered_rows if _row_bank_direction(row) in values]
        page_number = int(page)
        page_limit = int(page_size)
        start = (page_number - 1) * page_limit
        page_rows = filtered_rows[start : start + page_limit]
        bank_account_counts: dict[str, int] = {}
        bank_direction_counts: dict[str, int] = {}
        for row in filtered_rows:
            account = _row_bank_account_label(row)
            direction = _row_bank_direction(row)
            if account:
                bank_account_counts[account] = bank_account_counts.get(account, 0) + 1
            if direction:
                bank_direction_counts[direction] = bank_direction_counts.get(direction, 0) + 1
        return {
            "rows": page_rows,
            "pagination": {"page": page_number, "pageSize": page_limit, "total": len(filtered_rows)},
            "summary": {
                "rowCount": len(filtered_rows),
                "viewCounts": {
                    "completed": sum(1 for row in filtered_rows if _row_oa(row).get("workflowStatus") == "completed"),
                    "in_progress": sum(1 for row in filtered_rows if _row_oa(row).get("workflowStatus") == "in_progress"),
                },
            },
            "filterOptions": {
                "bank_account": [
                    {"value": value, "label": value, "count": count}
                    for value, count in sorted(bank_account_counts.items())
                ],
                "bank_direction": [
                    {
                        "value": value,
                        "label": "支出" if value == "outflow" else "收入" if value == "inflow" else value,
                        "count": count,
                    }
                    for value, count in sorted(bank_direction_counts.items())
                ],
            },
            "refresh_status": "fresh",
            "source_versions": oa_pending_payment_source_versions(),
            "read_model_scope_key": "all",
        }

    def get_oa_pending_payment_row_by_row_id(self, row_id: str) -> dict[str, object] | None:
        return self._payload(lambda row: str(row.get("id") or "") == row_id)

    def get_oa_pending_payment_row_by_oa_id(self, oa_id: str) -> dict[str, object] | None:
        return self._payload(lambda row: str(_row_oa(row).get("id") or "") == oa_id)

    def get_oa_pending_payment_row_by_bank_transaction_id(self, bank_transaction_id: str) -> dict[str, object] | None:
        return self._payload(lambda row: str(_row_bank(row).get("primaryBankTransactionId") or "") == bank_transaction_id)

    def get_oa_pending_payment_row_by_invoice_id(self, invoice_id: str) -> dict[str, object] | None:
        return self._payload(lambda row: str(_row_invoice(row).get("primaryInvoiceId") or "") == invoice_id)

    def _payload(self, predicate: Callable[[dict[str, object]], bool]) -> dict[str, object] | None:
        for row in self.rows:
            if predicate(row):
                return {
                    "row": deepcopy(row),
                    "refresh_status": "fresh",
                    "source_versions": oa_pending_payment_source_versions(),
                    "read_model_scope_key": "all",
                }
        return {
            "row": None,
            "refresh_status": "fresh",
            "source_versions": oa_pending_payment_source_versions(),
            "read_model_scope_key": "all",
        }


def _decode_test_filters(filters: str | None) -> list[dict[str, object]]:
    if not filters:
        return []
    decoded = json.loads(filters)
    return [dict(item) for item in decoded if isinstance(item, dict)] if isinstance(decoded, list) else []


def _row_oa(row: dict[str, object]) -> dict[str, object]:
    payload = row.get("oa")
    return payload if isinstance(payload, dict) else {}


def _row_bank(row: dict[str, object]) -> dict[str, object]:
    payload = row.get("bankTransaction")
    return payload if isinstance(payload, dict) else {}


def _row_invoice(row: dict[str, object]) -> dict[str, object]:
    payload = row.get("invoice")
    return payload if isinstance(payload, dict) else {}


def _row_bank_account_label(row: dict[str, object]) -> str:
    bank = _row_bank(row)
    bank_account = str(bank.get("bankAccount") or "").strip()
    if bank_account:
        return bank_account
    bank_name = str(bank.get("bankName") or "").strip()
    last4 = str(bank.get("accountLast4") or "").strip()
    return f"{bank_name} {last4}".strip()


def _row_bank_direction(row: dict[str, object]) -> str:
    bank = _row_bank(row)
    direction = str(bank.get("direction") or "").strip()
    if direction:
        return direction
    direction_label = str(bank.get("directionLabel") or "").strip()
    return "outflow" if direction_label == "支出" else "inflow" if direction_label == "收入" else direction_label


def _read_model_routes(
    *,
    repository: object | None,
    queue: QueueRecorder,
    source_versions_provider: object | None = None,
) -> OaPendingPaymentApiRoutes:
    service = OaPendingPaymentReadModelService(
        repository=_StateAwareOaRepository(repository) if repository is not None else None,
        queue_repository=queue,
        source_versions_provider=source_versions_provider or oa_pending_payment_source_versions,  # type: ignore[arg-type]
    )
    return OaPendingPaymentApiRoutes(
        query_service=_ReadModelQueryServiceTestAdapter(service),  # type: ignore[arg-type]
    )


class _ReadModelQueryServiceTestAdapter:
    """Keep legacy projector fixtures usable while route tests assert the new HTTP contract."""

    def __init__(self, service: OaPendingPaymentReadModelService) -> None:
        self._service = service

    def rows(self, query: dict[str, list[str]], *, tenant_id: str) -> dict[str, Any]:
        result = self._service.conditional_rows(query, tenant_id=tenant_id, if_none_match=None)
        if result.status != HTTPStatus.OK:
            raise RuntimeError("canonical OA pending payment facts are unavailable")
        return {
            key: value
            for key, value in result.payload.items()
            if key
            not in {
                "operationBarrierTargets",
                "readModelStatus",
                "read_model_scope_key",
                "read_model_stale_reasons",
                "read_model_status",
                "sourceVersions",
                "source_versions",
            }
        }

    def oa_detail(
        self,
        oa_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None,
    ) -> dict[str, Any]:
        del tenant_id
        return self._service.oa_detail(oa_id, requested_scope_key=requested_scope_key)

    def bank_transaction_detail(
        self,
        bank_transaction_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None,
    ) -> dict[str, Any]:
        del tenant_id
        return self._service.bank_transaction_detail(
            bank_transaction_id,
            requested_scope_key=requested_scope_key,
        )

    def invoice_detail(
        self,
        invoice_id: str,
        *,
        tenant_id: str,
        requested_scope_key: str | None,
    ) -> dict[str, Any]:
        del tenant_id
        return self._service.invoice_detail(invoice_id, requested_scope_key=requested_scope_key)

    def relation_details(
        self,
        row_id: str,
        *,
        kind: str,
        tenant_id: str,
        requested_scope_key: str | None,
    ) -> dict[str, Any]:
        del tenant_id
        return self._service.relation_details(
            row_id,
            kind=kind,
            requested_scope_key=requested_scope_key,
        )


class _StateAwareOaRepository:
    """Test adapter for legacy fixture repositories; production repositories own this proof."""

    def __init__(self, repository: object) -> None:
        self._repository = repository

    def __getattr__(self, name: str) -> object:
        return getattr(self._repository, name)

    def oa_pending_payment_query_state(
        self,
        *,
        scope_key: str,
        tenant_id: str,
        base_source_versions: dict[str, object],
    ) -> dict[str, object]:
        explicit_state = getattr(self._repository, "oa_pending_payment_query_state", None)
        if callable(explicit_state):
            return dict(
                explicit_state(
                    scope_key=scope_key,
                    tenant_id=tenant_id,
                    base_source_versions=base_source_versions,
                )
            )
        del tenant_id
        list_rows = getattr(self._repository, "list_oa_pending_payment_rows", None)
        payload = list_rows(
            month=None if scope_key == "all" else scope_key,
            page=1,
            page_size=1,
        ) if callable(list_rows) else None
        if payload is None and hasattr(self._repository, "source_versions"):
            payload = {
                "refresh_status": getattr(self._repository, "refresh_status", "fresh"),
                "source_versions": getattr(self._repository, "source_versions", {}),
            }
        actual_versions = (
            dict(payload.get("source_versions") or {})
            if isinstance(payload, dict) and isinstance(payload.get("source_versions"), dict)
            else {}
        )
        stale_reasons = [
            f"{scope_key}:{reason}"
            for reason in source_version_mismatch_reasons(
                expected=base_source_versions,
                actual=actual_versions,
            )
        ]
        if not isinstance(payload, dict) or str(payload.get("refresh_status") or "fresh") != "fresh":
            stale_reasons.append(f"{scope_key}:refresh_status")
        return {
            "status": "refreshing" if stale_reasons else "fresh",
            "scope_key": scope_key,
            "blocking_scope_keys": [scope_key] if stale_reasons else [],
            "stale_reasons": stale_reasons,
            "version_token": json.dumps(actual_versions, ensure_ascii=False, sort_keys=True),
            "source_versions": actual_versions,
        }


def _json_test_response(
    status_code: HTTPStatus,
    payload: dict[str, Any],
    response_headers: dict[str, str] | None = None,
) -> Response:
    response = Response(
        status_code=int(status_code),
        body="" if status_code == HTTPStatus.NOT_MODIFIED else json.dumps(payload, ensure_ascii=False),
    )
    response.headers.update(response_headers or {})
    return response


def _json_test_response_for_payload(payload: dict[str, Any]) -> Response:
    status_code = HTTPStatus.ACCEPTED if payload.get("read_model_status") == "refreshing" else HTTPStatus.OK
    return _json_test_response(status_code, payload)


def _oa_pending_payment_error_test_response(exc: Exception) -> Response:
    if not isinstance(exc, OaPendingPaymentError):
        raise exc
    return _json_test_response(
        exc.status_code,
        {
            "error": {
                "code": exc.error_code,
                "message": str(exc),
                "details": exc.details,
            }
        },
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
            "primaryOaId": "oa-api",
            "applicantName": "张三",
            "applicationType": "报销",
            "projectName": "API项目",
            "applicationTime": "2026-05-20",
            "amount": "100.00",
            "month": "2026-05",
            "workflowStatus": "completed",
            "reason": "API测试",
            "counterpartyName": "API供应商",
            "detailAvailable": True,
            "relationCount": 1,
            "hasMultiple": False,
            "detailMode": "single",
            "summaries": [
                {
                    "oaId": "oa-api",
                    "applicantName": "张三",
                    "applicationType": "报销",
                    "projectName": "API项目",
                    "applicationTime": "2026-05-20",
                    "amount": "100.00",
                    "workflowStatus": "completed",
                    "relationCaseId": "case-api",
                }
            ],
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
            "bankAccount": "建设银行 1234",
            "direction": "outflow",
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
