from __future__ import annotations

from http import HTTPStatus
import json
import unittest

from fin_ops_platform.app.routes_workbench_actions import WorkbenchActionApiRoutes
from fin_ops_platform.services.operation_history_semantics import operation_semantics
from fin_ops_platform.services.workbench_idempotency import WorkbenchIdempotencyKeyConflict
from fin_ops_platform.services.workbench_invoice_expense_item_assignment_service import (
    WorkbenchInvoiceExpenseItemAssignmentError,
)
from tests.app_test_support import build_local_state_application


class _Service:
    def __init__(self, *, result: dict[str, object] | None = None, error: Exception | None = None) -> None:
        self.result = result or {"success": True}
        self.error = error
        self.calls: list[dict[str, object]] = []

    def assign(
        self,
        payload: dict[str, object],
        *,
        actor_id: str,
        tenant_id: str,
        request_id: str,
    ) -> dict[str, object]:
        self.calls.append({
            "payload": payload,
            "actor_id": actor_id,
            "tenant_id": tenant_id,
            "request_id": request_id,
        })
        if self.error is not None:
            raise self.error
        return dict(self.result)


class WorkbenchInvoiceExpenseItemAssignmentApiTests(unittest.TestCase):
    @staticmethod
    def _routes(service: _Service | None) -> WorkbenchActionApiRoutes:
        return WorkbenchActionApiRoutes(
            write_facade_provider=lambda: None,
            invoice_expense_item_assignment_service_provider=(
                (lambda: service) if service is not None else None
            ),
        )

    def test_action_forwards_authoritative_actor_tenant_and_request(self) -> None:
        service = _Service(result={
            "success": True,
            "case_id": "CASE-1",
            "invoice_row_id": "invoice-1",
        })
        status, result = self._routes(service).assign_invoice_expense_items(
            {"case_id": "CASE-1"},
            actor_id="finance-user",
            tenant_id="default",
            request_id="request-1",
        )

        self.assertEqual(status, HTTPStatus.OK)
        self.assertTrue(result["success"])
        self.assertEqual(service.calls[0]["actor_id"], "finance-user")
        self.assertEqual(service.calls[0]["request_id"], "request-1")

    def test_action_maps_domain_and_idempotency_conflicts(self) -> None:
        cases = (
            (
                WorkbenchInvoiceExpenseItemAssignmentError(
                    "workbench_anomaly_changed",
                    "异常证据已变化，请刷新后重试。",
                ),
                "workbench_anomaly_changed",
            ),
            (
                WorkbenchInvoiceExpenseItemAssignmentError(
                    "invoice_source_links_changed",
                    "发票归属已发生变化，请刷新后重试。",
                ),
                "invoice_source_links_changed",
            ),
            (
                WorkbenchIdempotencyKeyConflict(
                    idempotency_key="assign-1",
                    existing_fingerprint="old",
                    incoming_fingerprint="new",
                    action_name="assign_invoice_expense_items",
                ),
                "idempotency_key_conflict",
            ),
        )
        for error, code in cases:
            with self.subTest(code=code):
                status, result = self._routes(_Service(error=error)).assign_invoice_expense_items(
                    {},
                    actor_id="finance-user",
                    tenant_id="default",
                    request_id="request-1",
                )
                self.assertEqual(status, HTTPStatus.CONFLICT)
                self.assertEqual(result["error"], code)

    def test_action_fails_closed_when_service_is_unavailable(self) -> None:
        status, result = self._routes(None).assign_invoice_expense_items(
            {},
            actor_id="finance-user",
            tenant_id="default",
            request_id="request-1",
        )

        self.assertEqual(status, HTTPStatus.SERVICE_UNAVAILABLE)
        self.assertEqual(result["error"], "invoice_expense_item_assignment_unavailable")

    def test_operation_history_has_specific_business_semantics(self) -> None:
        semantics = operation_semantics(
            "POST",
            "/api/workbench/actions/assign-invoice-expense-items",
            page_key="reconciliation-workbench",
        )

        self.assertEqual(semantics.action_code, "workbench.invoice_expense_items.assign")
        self.assertEqual(semantics.object_type, "invoice_expense_item_assignment")

    def test_full_handler_enforces_oa_sync_safety_before_assignment(self) -> None:
        app = build_local_state_application()
        service = _Service()
        app._workbench_action_api_routes = self._routes(service)
        app._oa_sync_status_payload = lambda: {
            "status": "refreshing",
            "dirty_scopes": ["2026-07"],
        }

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/assign-invoice-expense-items",
            body='{"case_id":"CASE-1"}',
        )

        self.assertEqual(response.status_code, HTTPStatus.CONFLICT)
        self.assertEqual(service.calls, [])

    def test_full_handler_passes_wrong_target_type_to_domain_validation_as_bad_request(self) -> None:
        app = build_local_state_application()
        service = _Service(error=WorkbenchInvoiceExpenseItemAssignmentError(
            "invalid_invoice_expense_item_assignment",
            "targets 必须至少包含一个 OA 明细目标。",
            status_code=400,
        ))
        app._workbench_action_api_routes = self._routes(service)
        app._oa_sync_status_payload = lambda: {
            "status": "synced",
            "dirty_scopes": [],
        }

        response = app.handle_request(
            "POST",
            "/api/workbench/actions/assign-invoice-expense-items",
            body='{"case_id":"CASE-1","targets":123}',
        )

        self.assertEqual(response.status_code, HTTPStatus.BAD_REQUEST)
        self.assertEqual(
            json.loads(response.body)["error"],
            "invalid_invoice_expense_item_assignment",
        )
        self.assertEqual(service.calls[0]["payload"]["targets"], 123)


if __name__ == "__main__":
    unittest.main()
