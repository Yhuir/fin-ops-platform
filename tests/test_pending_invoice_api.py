from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import BatchType
from fin_ops_platform.services.oa_identity_service import OAUserIdentity


class PendingInvoiceApiTests(unittest.TestCase):
    def test_rows_endpoint_returns_pending_invoice_rows(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor API")

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=expense&filter=all")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["direction"], "expense")
        self.assertEqual(payload["rows"][0]["id"], transaction_id)
        self.assertEqual(payload["rows"][0]["bank_transaction"]["counterparty_name"], "Vendor API")
        self.assertTrue(payload["rows"][0]["can_create_invoice"])

    def test_income_endpoint_rejects_expense_only_filter(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/pending-invoices/rows?direction=income&filter=requires_invoice")

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_filter_for_income")

    def test_preview_and_confirm_endpoint_create_invoice_and_relation_idempotently(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Confirm")
            payload = {
                "bank_transaction_id": transaction_id,
                "invoice_no": "API-MAN-001",
                "issue_date": "2026-05-20",
                "total_with_tax": "118.00",
                "seller_name": "Vendor Confirm",
                "buyer_name": "云南溯源科技有限公司",
            }

            preview_response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices/preview",
                body=json.dumps(payload),
            )
            self.assertEqual(preview_response.status_code, 200)
            preview_payload = json.loads(preview_response.body)
            confirm_body = {**payload, "preview_id": preview_payload["preview_id"], "request_id": "api-request-001"}
            confirm_response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps(confirm_body),
            )
            retry_response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps(confirm_body),
            )

        confirm_payload = json.loads(confirm_response.body)
        retry_payload = json.loads(retry_response.body)
        self.assertEqual(preview_response.status_code, 200)
        self.assertEqual(preview_payload["target_invoice_type"], "input")
        self.assertEqual(confirm_response.status_code, 200)
        self.assertEqual(retry_response.status_code, 200)
        self.assertEqual(retry_payload, confirm_payload)
        self.assertEqual(confirm_payload["affected_transaction_ids"], [transaction_id])
        self.assertEqual(confirm_payload["row"]["invoices"][0]["invoice_no"], "API-MAN-001")

    def test_confirm_endpoint_uses_session_actor_not_request_body_actor(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Actor")
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FINANCE001"],
                readonly_export_usernames=[],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="finance-user-id",
                username="FINANCE001",
                nickname="财务用户",
                display_name="财务用户",
                roles=["finance"],
                permissions=[],
            )
            payload = {
                "bank_transaction_id": transaction_id,
                "invoice_no": "API-MAN-ACTOR",
                "issue_date": "2026-05-20",
                "total_with_tax": "118.00",
                "seller_name": "Vendor Actor",
                "buyer_name": "云南溯源科技有限公司",
                "actor_id": "SPOOFED_USER",
            }
            preview = json.loads(
                app.handle_request(
                    "POST",
                    "/api/pending-invoices/manual-invoices/preview",
                    body=json.dumps(payload),
                ).body
            )

            response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps({**payload, "preview_id": preview["preview_id"], "request_id": "api-actor"}),
                headers={"Authorization": "Bearer finance-user"},
            )

        result = json.loads(response.body)
        relation = app._workbench_pair_relation_service.get_active_relation_by_case_id(result["relation_case_id"])
        audit_entry = next(
            entry for entry in app._audit_service.list_entries()
            if entry.action == "pending_invoice_manual_invoice_confirmed"
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(relation["created_by"], "FINANCE001")
        self.assertEqual(audit_entry.actor_id, "FINANCE001")
        self.assertEqual(audit_entry.metadata["actor_id"], "FINANCE001")

    def test_confirm_endpoint_requires_write_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Forbidden")
            payload = {
                "bank_transaction_id": transaction_id,
                "invoice_no": "API-MAN-FORBIDDEN",
                "issue_date": "2026-05-20",
                "total_with_tax": "118.00",
                "seller_name": "Vendor Forbidden",
                "buyer_name": "云南溯源科技有限公司",
            }
            preview = json.loads(
                (preview_response := app.handle_request(
                    "POST",
                    "/api/pending-invoices/manual-invoices/preview",
                    body=json.dumps(payload),
                )).body
            )
            self.assertEqual(preview_response.status_code, 200)
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="readonly-user-id",
                username="READONLY001",
                nickname="只读用户",
                display_name="只读用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/api/pending-invoices/manual-invoices",
                body=json.dumps({**payload, "preview_id": preview["preview_id"], "request_id": "api-forbidden"}),
                headers={"Authorization": "Bearer readonly-user"},
            )

        response_payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response_payload["error"], "permission_denied")

    def test_settings_update_requires_write_permission(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            settings = app._app_settings_service.get_settings_payload()
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="readonly-user-id",
                username="READONLY001",
                nickname="只读用户",
                display_name="只读用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps({
                    "completed_project_ids": [],
                    "bank_account_mappings": [],
                    "allowed_usernames": ["READONLY001"],
                    "readonly_export_usernames": ["READONLY001"],
                    "admin_usernames": [],
                    "workbench_column_layouts": settings["workbench_column_layouts"],
                    "oa_retention": settings["oa_retention"],
                    "oa_import": settings["oa_import"],
                    "oa_invoice_offset": settings["oa_invoice_offset"],
                    "bank_transaction_tags": settings["bank_transaction_tags"],
                    "pending_invoice_tag_groups": settings["pending_invoice_tag_groups"],
                }),
                headers={"Authorization": "Bearer readonly-user"},
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")

    def test_recoverable_manual_invoice_failure_persists_command_log(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            data_dir = Path(temp_dir)
            app = build_application(data_dir=data_dir)
            transaction_id = self._create_bank_transaction(app, counterparty_name="Vendor Recoverable")
            payload = {
                "bank_transaction_id": transaction_id,
                "invoice_no": "API-MAN-RECOVER",
                "issue_date": "2026-05-20",
                "total_with_tax": "118.00",
                "seller_name": "Vendor Recoverable",
                "buyer_name": "云南溯源科技有限公司",
            }
            preview = json.loads(
                app.handle_request(
                    "POST",
                    "/api/pending-invoices/manual-invoices/preview",
                    body=json.dumps(payload),
                ).body
            )
            app._pending_invoice_application_service._fault_injector = (
                lambda phase, _command: (_ for _ in ()).throw(RuntimeError("boom"))
                if phase == "after_invoice_created"
                else None
            )

            with self.assertRaises(RuntimeError):
                app.handle_request(
                    "POST",
                    "/api/pending-invoices/manual-invoices",
                    body=json.dumps({**payload, "preview_id": preview["preview_id"], "request_id": "api-recoverable"}),
                )

            reloaded = build_application(data_dir=data_dir, bootstrap_mode="legacy")

        command = reloaded._pending_invoice_commands["api-recoverable"]
        self.assertEqual(command["status"], "failed_recoverable")
        self.assertEqual(command["last_successful_status"], "invoice_created")

    @staticmethod
    def _create_bank_transaction(app: object, *, counterparty_name: str, credit: bool = False) -> str:
        preview = app._import_service.preview_import(
            batch_type=BatchType.BANK_TRANSACTION,
            source_name="api-bank.json",
            imported_by="api-test",
            rows=[
                {
                    "account_no": "622200001234",
                    "txn_date": "2026-05-20",
                    "trade_time": "2026-05-20 10:00:00",
                    "counterparty_name": counterparty_name,
                    "debit_amount": "" if credit else "118.00",
                    "credit_amount": "118.00" if credit else "",
                    "bank_serial_no": f"SERIAL-{counterparty_name}",
                    "selected_bank_name": "工商银行",
                    "selected_bank_last4": "1234",
                }
            ],
        )
        app._import_service.confirm_import(preview.id)
        return str(preview.row_results[0].linked_object_id)


if __name__ == "__main__":
    unittest.main()
