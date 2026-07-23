from __future__ import annotations

import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.app.server import Application
from tests.app_test_support import build_local_state_application as build_application
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.oa_manual_import_service import OAManualImportService
from tests.test_oa_manual_import_service import (
    MemoryManualImportStore,
    RecordingOAAdapter,
    RecordingWorkbenchQueryService,
    oa_record,
)


class OAManualImportApiTests(unittest.TestCase):
    def setUp(self) -> None:
        self._temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self._temp_dir.cleanup)

    def _build_app_with_service(
        self,
        *,
        adapter: RecordingOAAdapter,
        store: MemoryManualImportStore | None = None,
        workbench: RecordingWorkbenchQueryService | None = None,
    ) -> Application:
        app = build_application(data_dir=Path(self._temp_dir.name))
        self.addCleanup(app.shutdown_background_jobs)
        app._workbench_query_service._oa_adapter = adapter
        app._oa_manual_import_service = OAManualImportService(
            state_store=store or MemoryManualImportStore(),
            oa_adapter=adapter,
            workbench_query_service=workbench or RecordingWorkbenchQueryService(),
        )
        return app

    def _readonly_identity(self) -> OAUserIdentity:
        return OAUserIdentity(
            user_id="readonly-user-id",
            username="READONLY001",
            nickname="只读用户",
            display_name="只读用户",
            roles=["finance"],
            permissions=["finops:access"],
        )

    def _assert_oa_manual_targets(self, payload: dict[str, object], *, month: str) -> None:
        self.assertEqual(payload["freshness_targets"], [])
        self.assertEqual(payload["operation_barrier_targets"], [])
        self.assertIn(month, payload["affected_scope_keys"])
        self.assertIn(month, payload["read_model_scope_keys"])

    def test_search_endpoint_returns_early_rows_ignoring_global_cutoff_and_supports_paging(self) -> None:
        app = self._build_app_with_service(
            adapter=RecordingOAAdapter(
                [
                    oa_record("oa-exp-1981", month="2025-12", applicant="陈雄兵"),
                    oa_record("oa-exp-1982", month="2025-12", applicant="陈雄兵"),
                ]
            )
        )
        app._app_settings_service.update_settings(
            completed_project_ids=[],
            bank_account_mappings=[],
            allowed_usernames=[],
            readonly_export_usernames=[],
            admin_usernames=[],
            oa_retention={"cutoff_date": "2026-03-01"},
        )

        response = app.handle_request(
            "GET",
            "/api/workbench/settings/oa/manual-search"
            "?q=%E9%99%88%E9%9B%84%E5%85%B5&form_types=expense_claim"
            "&statuses=completed&page=1&page_size=1",
        )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["total"], 2)
        self.assertEqual(payload["page"], 1)
        self.assertEqual(payload["page_size"], 1)
        self.assertEqual([row["row_id"] for row in payload["rows"]], ["oa-exp-1982"])

    def test_search_endpoint_rejects_invalid_pagination_bounds(self) -> None:
        app = self._build_app_with_service(adapter=RecordingOAAdapter([]))

        negative_page = app.handle_request("GET", "/api/workbench/settings/oa/manual-search?page=-1")
        oversize_page = app.handle_request("GET", "/api/workbench/settings/oa/manual-search?page_size=101")

        self.assertEqual(negative_page.status_code, 400)
        self.assertEqual(json.loads(negative_page.body)["error"], "invalid_oa_manual_search_request")
        self.assertEqual(oversize_page.status_code, 400)
        self.assertEqual(json.loads(oversize_page.body)["error"], "invalid_oa_manual_search_request")

    def test_refresh_endpoint_returns_counts_and_invalidates_affected_scopes(self) -> None:
        app = self._build_app_with_service(adapter=RecordingOAAdapter([oa_record("oa-exp-1981", month="2025-12", invoices=[])]))

        with (
            patch.object(app, "_refresh_workbench_read_model_scopes_for_maintenance") as invalidate,
            patch.object(app._search_service, "clear_cache") as clear_cache,
        ):
            response = app.handle_request(
                "POST",
                "/api/workbench/settings/oa/manual-search/refresh-attachments",
                json.dumps({"row_ids": ["oa-exp-1981"]}),
            )

        self.assertEqual(response.status_code, 200)
        payload = json.loads(response.body)
        self.assertEqual(payload["rows"][0]["row_id"], "oa-exp-1981")
        self.assertEqual(payload["rows"][0]["importable_invoice_count"], 1)
        self._assert_oa_manual_targets(payload, month="2025-12")
        invalidate.assert_not_called()
        clear_cache.assert_called_once()

    def test_import_endpoint_imports_completed_rejects_in_progress_and_is_idempotent(self) -> None:
        adapter = RecordingOAAdapter(
            [
                oa_record("oa-exp-1981", status="已完成"),
                oa_record("oa-pay-2048", apply_type="支付申请", status="进行中"),
            ]
        )
        store = MemoryManualImportStore()
        workbench = RecordingWorkbenchQueryService()
        app = self._build_app_with_service(adapter=adapter, store=store, workbench=workbench)

        first = app.handle_request(
            "POST",
            "/api/workbench/settings/oa/manual-imports",
            json.dumps({"row_ids": ["oa-exp-1981", "oa-pay-2048"], "actor_id": "tester"}),
        )
        second = app.handle_request(
            "POST",
            "/api/workbench/settings/oa/manual-imports",
            json.dumps({"row_ids": ["oa-exp-1981"], "actor_id": "tester"}),
        )

        self.assertEqual(first.status_code, 200)
        first_payload = json.loads(first.body)
        self.assertEqual(first_payload["imported"], ["oa-exp-1981"])
        self.assertEqual(first_payload["failed"][0]["code"], "not_completed")
        self._assert_oa_manual_targets(first_payload, month="2025-12")
        self.assertEqual(json.loads(second.body)["already_imported"], ["oa-exp-1981"])
        self.assertEqual(workbench.synced_row_ids, [["oa-exp-1981"], ["oa-exp-1981"]])

    def test_list_and_delete_manual_imports_endpoint_removes_marker_and_invalidates(self) -> None:
        store = MemoryManualImportStore()
        store.add_manual_oa_imports(["oa-exp-1981"], "tester", {})
        app = self._build_app_with_service(adapter=RecordingOAAdapter([oa_record("oa-exp-1981")]), store=store)

        list_response = app.handle_request("GET", "/api/workbench/settings/oa/manual-imports")
        with (
            patch.object(app, "_refresh_workbench_read_model_scopes_for_maintenance") as invalidate,
            patch.object(app._search_service, "clear_cache") as clear_cache,
        ):
            delete_response = app.handle_request(
                "DELETE",
                "/api/workbench/settings/oa/manual-imports/oa-exp-1981",
                json.dumps({"actor_id": "tester"}),
            )

        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(json.loads(list_response.body)["row_ids"], ["oa-exp-1981"])
        self.assertEqual(delete_response.status_code, 200)
        delete_payload = json.loads(delete_response.body)
        self.assertEqual(delete_payload["removed"], True)
        self.assertEqual(delete_payload["row_id"], "oa-exp-1981")
        self._assert_oa_manual_targets(delete_payload, month="2025-12")
        self.assertEqual(store.load_manual_oa_imports()["row_ids"], [])
        invalidate.assert_not_called()
        clear_cache.assert_called_once()

    def test_manual_import_mutation_endpoints_reject_readonly_session_even_with_spoofed_actor(self) -> None:
        with patch.dict(os.environ, {"FIN_OPS_TEST_DEFAULT_AUTH": "0"}):
            store = MemoryManualImportStore()
            store.add_manual_oa_imports(["oa-exp-1981"], "tester", {})
            app = self._build_app_with_service(
                adapter=RecordingOAAdapter([oa_record("oa-exp-1981")]),
                store=store,
            )
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda _token: self._readonly_identity()
            headers = {"Authorization": "Bearer readonly-token"}

            with (
                patch.object(app._oa_manual_import_service, "refresh_attachments") as refresh_attachments,
                patch.object(app._oa_manual_import_service, "import_row_ids") as import_row_ids,
                patch.object(app._oa_manual_import_service, "remove_manual_import") as remove_manual_import,
            ):
                refresh_response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/oa/manual-search/refresh-attachments",
                    body=json.dumps({"row_ids": ["oa-exp-1981"]}),
                    headers=headers,
                )
                import_response = app.handle_request(
                    "POST",
                    "/api/workbench/settings/oa/manual-imports",
                    body=json.dumps({"row_ids": ["oa-exp-1981"], "actor_id": "spoofed-owner"}),
                    headers=headers,
                )
                delete_response = app.handle_request(
                    "DELETE",
                    "/api/workbench/settings/oa/manual-imports/oa-exp-1981",
                    body=json.dumps({"actor_id": "spoofed-owner"}),
                    headers=headers,
                )

        self.assertEqual(refresh_response.status_code, 403)
        self.assertEqual(json.loads(refresh_response.body)["error"], "permission_denied")
        self.assertEqual(import_response.status_code, 403)
        self.assertEqual(json.loads(import_response.body)["error"], "permission_denied")
        self.assertEqual(delete_response.status_code, 403)
        self.assertEqual(json.loads(delete_response.body)["error"], "permission_denied")
        refresh_attachments.assert_not_called()
        import_row_ids.assert_not_called()
        remove_manual_import.assert_not_called()
        self.assertEqual(store.load_manual_oa_imports()["row_ids"], ["oa-exp-1981"])


if __name__ == "__main__":
    unittest.main()
