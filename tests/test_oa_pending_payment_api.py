from __future__ import annotations

from decimal import Decimal
from http import HTTPStatus
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
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID, PAY_STATUS_PENDING
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
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
            relation_status = str(group.get("relation_status") or payload.get("relation_status") or "linked")
            for row_id, row_type in zip(payload["row_ids"], payload["row_types"]):
                key = (str(row_id), group_id)
                if key in seen:
                    continue
                seen.add(key)
                rows.append({"row_id": row_id, "row_type": row_type, "relation_status": relation_status, "group_ids": [group_id]})
        return {"status": "fresh", "rows": rows, "groups": groups, "source_versions": {}}

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


class FakeCommandService:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []
        self.link_calls: list[tuple[dict[str, Any], str]] = []
        self.candidate_queries: list[dict[str, list[str]]] = []

    def confirm_paid(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        self.calls.append((dict(payload), actor_id))
        return {
            "success": True,
            "action": "oa_pending_payment_confirm_paid",
            "oaRowId": payload.get("oa_row_id") or payload.get("oaRowId"),
            "bankTransactionIds": [payload.get("bank_transaction_id") or payload.get("bankTransactionId")],
            "paymentStatus": {"code": "paid", "label": "已支付", "reason": "支出流水合计等于OA金额"},
            "oaPaymentWriteback": {"code": "written", "label": "已写回", "flowId": "proc-api"},
            "affected_scope_keys": ["2026-05", "all"],
        }

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
            "affected_scope_keys": ["2026-05", "all"],
        }

    def auto_reconcile_bank_transactions(self, payload: dict[str, Any], *, actor_id: str) -> dict[str, Any]:
        self.link_calls.append(({"auto_reconcile": dict(payload)}, actor_id))
        return {
            "success": True,
            "action": "oa_pending_payment_auto_reconcile_bank_transactions",
            "month": payload.get("month") or "all",
            "autoMatchedCount": 1,
            "writebackCount": 1,
            "autoMatchedRelations": [{"oaRowIds": ["oa-api"], "bankTransactionIds": ["bank-api"]}],
            "skippedAutoMatches": [
                {
                    "oaRowIds": ["oa-skipped"],
                    "bankTransactionIds": ["bank-skipped"],
                    "ruleCode": "oa_bank_exact_amount",
                    "errorCode": "oa_flow_id_not_found",
                }
            ],
            "oaPaymentWritebacks": [{"code": "written", "label": "已写回", "flowId": "proc-api"}],
            "affected_scope_keys": ["2026-05", "all"],
        }

    def bank_transaction_candidates(self, query: dict[str, list[str]]) -> dict[str, Any]:
        self.candidate_queries.append(dict(query))
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


class FakePaymentStatusRepository:
    def __init__(
        self,
        *,
        flow_id: str,
        pay_status: int = PAY_STATUS_PENDING,
    ) -> None:
        self.flow_id = flow_id
        self.pay_status = pay_status
        self.marked_flow_ids: list[str] = []

    def list_payment_statuses(self) -> dict[str, OAPaymentStatusRecord]:
        return {
            self.flow_id: OAPaymentStatusRecord(
                flow_id=self.flow_id,
                pay_status=self.pay_status,
            )
        }

    def resolve_flow_id(self, _record: OAApplicationRecord) -> str:
        return self.flow_id

    def get_payment_status(self, flow_id: str) -> OAPaymentStatusRecord | None:
        if flow_id != self.flow_id:
            return None
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=self.pay_status)

    def mark_paid(self, flow_id: str) -> OAPaymentStatusRecord:
        self.marked_flow_ids.append(flow_id)
        return OAPaymentStatusRecord(flow_id=flow_id, pay_status=PAY_STATUS_PAID)


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
                oa_projection=StaticOAProjection([
                    self._oa("oa-api", "张三", "100.00", detail_fields={"申请日期": "2026-05-20"}),
                ]),
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
            oa_relation_response = app.handle_request(
                "GET",
                f"/api/oa-pending-payments/rows/{row_id}/relation-details?kind=oa",
            )

        self.assertEqual(rows_response.status_code, 200)
        self.assertEqual(filter_response.status_code, 200)
        self.assertEqual(oa_response.status_code, 200)
        self.assertEqual(bank_response.status_code, 200)
        self.assertEqual(relation_response.status_code, 200)
        self.assertEqual(oa_relation_response.status_code, 200)
        rows_payload = json.loads(rows_response.body)
        self.assertEqual(rows_payload["rows"][0]["paymentStatus"]["code"], "paid")
        self.assertEqual(rows_payload["rows"][0]["oa"]["applicationTime"], "2026-05-20")
        self.assertNotIn("read_model_status", rows_payload)
        self.assertNotIn("readModelStatus", rows_payload)
        self.assertNotIn("read_model_scope_keys", rows_payload)
        self.assertNotIn("refresh_enqueued", rows_payload)
        self.assertIn("oa_applicant", [field["field"] for field in json.loads(filter_response.body)["fields"]])
        self.assertEqual(json.loads(oa_response.body)["id"], "oa-api")
        self.assertEqual(json.loads(bank_response.body)["id"], "bank-api")
        relation_payload = json.loads(relation_response.body)
        oa_relation_payload = json.loads(oa_relation_response.body)
        self.assertEqual(relation_payload["kind"], "bank")
        self.assertEqual(oa_relation_payload["kind"], "oa")
        for payload in (relation_payload, oa_relation_payload):
            self.assertNotIn("read_model_status", payload)
            self.assertNotIn("readModelStatus", payload)
            self.assertNotIn("read_model_scope_keys", payload)
            self.assertNotIn("refresh_enqueued", payload)

    def test_confirm_paid_route_delegates_to_command_service_with_write_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                oa_projection=StaticOAProjection([]),
            )
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(
                service,
                command_service=command_service,
            )
            app._workbench_write_auth_context = lambda _headers: ("tester", "default")  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/oa-pending-payments/confirm-paid",
                body=json.dumps({"oa_row_id": "oa-api", "bank_transaction_id": "bank-api"}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["paymentStatus"]["code"], "paid")
        self.assertEqual(payload["oaPaymentWriteback"]["label"], "已写回")
        self.assertEqual(command_service.calls, [({"oa_row_id": "oa-api", "bank_transaction_id": "bank-api"}, "tester")])

    def test_link_bank_transactions_route_delegates_to_command_service_with_write_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                oa_projection=StaticOAProjection([]),
            )
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(
                service,
                command_service=command_service,
            )
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
        self.assertEqual(command_service.link_calls, [({"oa_row_ids": ["oa-api"], "bank_transaction_ids": ["bank-api"]}, "tester")])

    def test_auto_reconcile_route_delegates_to_command_service_with_write_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                oa_projection=StaticOAProjection([]),
            )
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(
                service,
                command_service=command_service,
            )
            app._workbench_write_auth_context = lambda _headers: ("tester", "default")  # type: ignore[method-assign]

            response = app.handle_request(
                "POST",
                "/api/oa-pending-payments/auto-reconcile-bank-transactions",
                body=json.dumps({"month": "2026-06"}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertTrue(payload["success"])
        self.assertEqual(payload["autoMatchedCount"], 1)
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["skippedAutoMatches"][0]["errorCode"], "oa_flow_id_not_found")
        self.assertEqual(command_service.link_calls, [({"auto_reconcile": {"month": "2026-06"}}, "tester")])

    def test_auto_reconcile_uses_payment_admitted_source_after_completed_projection_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), bootstrap_mode="lightweight")
            target_oa = self._oa(
                "oa-pay-flow-auto",
                "陈秀云",
                "163000.00",
                workflow_status="in_progress",
            )
            target_bank = BankTransaction(
                id="bank-flow-auto",
                account_no="622200001234",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="API供应商",
                amount=Decimal("163000.00"),
                signed_amount=Decimal("-163000.00"),
                txn_date="2026-05-21",
                trade_time="2026-05-21 10:00:00",
            )
            relation_command = FakeRelationCommandService()
            payment_repository = FakePaymentStatusRepository(flow_id="flow-auto")
            app._import_service = ImportNormalizationService(existing_transactions=[target_bank])
            app._oa_payment_status_repository_instance = payment_repository
            app._oa_pending_payment_source_adapter_instance = StaticOAProjection([target_oa])
            app._postgres_oa_projection_repository = lambda: StaticOAProjection([])  # type: ignore[method-assign]
            app._workbench_relation_command_service = lambda **_kwargs: relation_command  # type: ignore[method-assign]
            app._invoice_lifecycle_policy = lambda: InvoiceLifecyclePolicy()  # type: ignore[method-assign]

            app._oa_pending_payment_projection(
                source_adapter=StaticOAProjection([]),
                use_lazy_source=False,
            )

            payload = app._oa_pending_payment_command_service().auto_reconcile_bank_transactions(
                {"month": "2026-05"},
                actor_id="tester",
            )
            pending_snapshot = app._state_store.load_oa_pending_payment_bank_relations()

        self.assertEqual(payload["autoMatchedCount"], 1)
        self.assertEqual(payload["writebackCount"], 1)
        self.assertEqual(payload["autoMatchedRelations"][0]["oaRowIds"], ["oa-pay-flow-auto"])
        self.assertEqual(payload["autoMatchedRelations"][0]["bankTransactionIds"], ["bank-flow-auto"])
        self.assertEqual(payment_repository.marked_flow_ids, ["flow-auto"])
        self.assertEqual(relation_command.confirm_calls, [])
        pending_relations = list((pending_snapshot.get("relations") or {}).values())
        self.assertTrue(
            any(
                set(relation.get("oa_row_ids") or []) == {"oa-pay-flow-auto"}
                and set(relation.get("bank_transaction_ids") or []) == {"bank-flow-auto"}
                and (relation.get("amount_check") or {}).get("rule_code") == "oa_bank_exact_amount"
                for relation in pending_relations
                if isinstance(relation, dict)
            )
        )

    def test_auto_reconcile_persists_relation_and_reload_is_noop(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            target_oa = self._oa(
                "oa-pay-flow-persist",
                "陈秀云",
                "163000.00",
                workflow_status="in_progress",
            )
            target_bank = BankTransaction(
                id="bank-flow-persist",
                account_no="622200001234",
                txn_direction=TransactionDirection.OUTFLOW,
                counterparty_name_raw="API供应商",
                amount=Decimal("163000.00"),
                signed_amount=Decimal("-163000.00"),
                txn_date="2026-05-21",
                trade_time="2026-05-21 10:00:00",
            )

            app = build_application(data_dir=data_dir)
            payment_repository = FakePaymentStatusRepository(flow_id="flow-persist")
            app._import_service = ImportNormalizationService(existing_transactions=[target_bank])
            app._oa_payment_status_repository_instance = payment_repository
            app._oa_pending_payment_source_adapter_instance = StaticOAProjection([target_oa])
            app._postgres_oa_projection_repository = lambda: StaticOAProjection([])  # type: ignore[method-assign]

            first_payload = app._oa_pending_payment_command_service().auto_reconcile_bank_transactions(
                {"month": "2026-05"},
                actor_id="tester",
            )
            persisted_snapshot = app._state_store.load_oa_pending_payment_bank_relations()
            persisted_workbench_snapshot = app._state_store.load_workbench_pair_relations()

            reloaded = build_application(data_dir=data_dir)
            reloaded_payment_repository = FakePaymentStatusRepository(
                flow_id="flow-persist",
                pay_status=PAY_STATUS_PAID,
            )
            reloaded._import_service = ImportNormalizationService(existing_transactions=[target_bank])
            reloaded._oa_payment_status_repository_instance = reloaded_payment_repository
            reloaded._oa_pending_payment_source_adapter_instance = StaticOAProjection([target_oa])
            reloaded._postgres_oa_projection_repository = lambda: StaticOAProjection([])  # type: ignore[method-assign]

            second_payload = reloaded._oa_pending_payment_command_service().auto_reconcile_bank_transactions(
                {"month": "2026-05"},
                actor_id="tester",
            )

        pair_relations = persisted_workbench_snapshot.get("pair_relations")
        self.assertFalse(pair_relations)
        pending_relations = persisted_snapshot.get("relations")
        self.assertIsInstance(pending_relations, dict)
        persisted_relations = list(pending_relations.values()) if isinstance(pending_relations, dict) else []
        self.assertEqual(first_payload["autoMatchedCount"], 1)
        self.assertEqual(first_payload["writebackCount"], 1)
        self.assertTrue(
            any(
                set(relation.get("oa_row_ids") or []) == {"oa-pay-flow-persist"}
                and set(relation.get("bank_transaction_ids") or []) == {"bank-flow-persist"}
                for relation in persisted_relations
                if isinstance(relation, dict)
            )
        )
        self.assertEqual(payment_repository.marked_flow_ids, ["flow-persist"])
        self.assertEqual(second_payload["autoMatchedCount"], 0)
        self.assertEqual(second_payload["writebackCount"], 0)
        self.assertNotIn("readModelRefresh", second_payload)
        self.assertEqual(reloaded_payment_repository.marked_flow_ids, [])

    def test_bank_transaction_candidates_route_delegates_to_command_service(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            service = OaPendingPaymentQueryService(
                import_service=ImportNormalizationService(),
                oa_projection=StaticOAProjection([]),
            )
            command_service = FakeCommandService()
            app._oa_pending_payment_api_routes = OaPendingPaymentApiRoutes(
                service,
                command_service=command_service,
            )

            response = app.handle_request(
                "GET",
                "/api/oa-pending-payments/bank-transaction-candidates?relation_status=unmatched&oa_row_ids=oa-api&oa_row_ids=oa-extra",
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["rows"][0]["id"], "bank-api")
        self.assertEqual(payload["rows"][0]["relationStatus"], "unmatched")
        self.assertEqual(payload["rows"][0]["linkedOaRowIds"], ["oa-api", "oa-extra"])
        self.assertEqual(command_service.candidate_queries[0]["oa_row_ids"], ["oa-api", "oa-extra"])

    def test_candidate_bank_relation_is_visible_without_marking_oa_paid(self) -> None:
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
        service = OaPendingPaymentQueryService(
            import_service=ImportNormalizationService(existing_transactions=[bank]),
            relation_facade=FakeRelationFacade([
                {
                    "case_id": "candidate-oa-bank",
                    "row_ids": ["oa-candidate", "bank-candidate"],
                    "row_types": ["oa", "bank"],
                    "relation_mode": "automatic_decision",
                    "relation_status": "candidate",
                    "amount_check": {"matched": True},
                }
            ]),
            oa_projection=StaticOAProjection([
                self._oa("oa-candidate", "候选申请人", "100.00", detail_fields={"申请日期": "2026-05-20"}),
            ]),
        )

        row = service.list_rows(page_size=20)["rows"][0]

        self.assertEqual(row["bankTransaction"]["relationCount"], 1)
        self.assertEqual(row["bankTransaction"]["summaries"][0]["relationStatus"], "candidate")
        self.assertEqual(row["bankTransaction"]["paidTotal"], "0.00")
        self.assertNotEqual(row["paymentStatus"]["code"], "paid")

    def test_rows_route_passes_in_progress_view_mode_to_query_service(self) -> None:
        service = OaPendingPaymentQueryService(
            import_service=ImportNormalizationService(),
            oa_projection=StaticOAProjection([
                self._oa("oa-completed", "张三", "100.00", workflow_status="completed"),
                self._oa("oa-progress", "李四", "120.00", workflow_status="in_progress"),
            ]),
        )
        routes = OaPendingPaymentApiRoutes(service)

        status, payload = routes.rows({"view_mode": ["in_progress"], "page": ["1"], "page_size": ["20"]})
        filter_status, filter_payload = routes.filter_options({"view_mode": ["in_progress"]})

        self.assertEqual(status, HTTPStatus.OK)
        self.assertEqual([row["oa"]["id"] for row in payload["rows"]], ["oa-progress"])
        self.assertEqual(payload["viewMode"], "in_progress")
        self.assertEqual(filter_status, HTTPStatus.OK)
        self.assertEqual(filter_payload["context"]["viewMode"], "in_progress")

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

    def test_expected_source_versions_do_not_read_workbench_relation_read_model(self) -> None:
        app = object.__new__(Application)

        payload = app._oa_pending_payment_expected_source_versions(scope_key="2026-05")

        self.assertNotIn("workbench_relation_source_versions", payload)


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
                "/api/oa-pending-payments/filter-options",
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

    def test_oa_source_versions_cover_relation_and_import_fact_dependencies(self) -> None:
        versions = oa_pending_payment_source_versions()

        self.assertIn("oa_pending_payment_source_version", versions)
        self.assertIn("oa_pending_payment_workbench_relation_schema_version", versions)
        self.assertIn("oa_pending_payment_bank_import_fact_schema_version", versions)
        self.assertIn("oa_pending_payment_input_invoice_import_fact_schema_version", versions)
        self.assertIn("oa_projection_sync_version", versions)
