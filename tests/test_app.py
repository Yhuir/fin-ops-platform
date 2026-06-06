import json
from pathlib import Path
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application


class AppTests(unittest.TestCase):
    def test_health_endpoint_reports_current_and_future_capabilities(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["service"], "fin-ops-platform-api")
        self.assertIn("reconciliation", payload["capabilities"])
        self.assertIn("manual_workbench", payload["capabilities"])
        self.assertIn("follow_up_ledgers", payload["capabilities"])
        self.assertIn("reminder_scheduler", payload["capabilities"])
        self.assertIn("advanced_exceptions", payload["capabilities"])
        self.assertIn("oa_integration_foundation", payload["capabilities"])
        self.assertIn("/workbench", payload["entrypoints"])
        self.assertIn("/ledgers", payload["entrypoints"])
        self.assertIn("/workbench/actions/difference", payload["entrypoints"])
        self.assertIn("/workbench/actions/offset", payload["entrypoints"])
        self.assertIn("/integrations/oa", payload["entrypoints"])
        self.assertIn("/integrations/oa/sync", payload["entrypoints"])
        self.assertIn("/projects", payload["entrypoints"])
        self.assertIn("/projects/assign", payload["entrypoints"])
        self.assertIn("/api/workbench", payload["entrypoints"])
        self.assertIn("/api/session/me", payload["entrypoints"])
        self.assertIn("/api/tax-offset", payload["entrypoints"])
        self.assertIn("/api/tax-offset/calculate", payload["entrypoints"])
        self.assertIn("/api/cost-statistics", payload["entrypoints"])
        self.assertIn("/api/cost-statistics/export", payload["entrypoints"])
        self.assertIn("/api/search", payload["entrypoints"])
        self.assertIn("/api/pending-invoices/rows", payload["entrypoints"])
        self.assertIn("/api/pending-invoices/invoice-candidates", payload["entrypoints"])
        self.assertIn("/api/pending-invoices/rules", payload["entrypoints"])
        self.assertIn("/api/pending-invoices/export", payload["entrypoints"])
        self.assertIn("/api/input-invoice-usage/rows", payload["entrypoints"])
        self.assertIn("/api/output-invoice-collections/rows", payload["entrypoints"])
        self.assertIn("/api/no-oa-bank-batches", payload["entrypoints"])
        self.assertIn("/api/no-oa-bank-batches/submit", payload["entrypoints"])
        self.assertIn("/api/no-oa-bank-batches/{batch_id}", payload["entrypoints"])
        self.assertIn("/api/no-oa-bank-batches/{batch_id}/submit", payload["entrypoints"])
        self.assertIn("/api/no-oa-bank-batches/{batch_id}/withdraw", payload["entrypoints"])
        self.assertIn("oa_session_foundation", payload["capabilities"])
        self.assertIn("project_costing_foundation", payload["capabilities"])
        self.assertIn("workbench_v2_backend_contracts", payload["capabilities"])
        self.assertIn("cost_statistics_foundation", payload["capabilities"])
        self.assertIn("cost_statistics_export", payload["capabilities"])
        self.assertIn("workbench_global_search_foundation", payload["capabilities"])
        self.assertIn("input_invoice_usage_read_model", payload["capabilities"])
        self.assertIn("output_invoice_collection_read_model", payload["capabilities"])
        self.assertIn("no_oa_bank_batch_processing", payload["capabilities"])
        runtime_release = payload["runtime_release"]
        self.assertEqual(runtime_release["consistent"], True)
        self.assertIn("working_directory", runtime_release)
        self.assertIn("package_file", runtime_release)
        self.assertIn("expected_source_root", runtime_release)
        self.assertIn("pythonpath", runtime_release)
        self.assertNotIn("workbench_api_self_test", payload)

    def test_health_endpoint_does_not_run_workbench_api_self_test(self) -> None:
        app = build_application()

        class FailingWorkbenchRepository:
            def get_workbench_summary(self, *, scope_key: str):
                raise AssertionError("/health must stay a lightweight liveness endpoint")

            def get_workbench_groups_page(self, **kwargs):
                raise AssertionError("/health must stay a lightweight liveness endpoint")

        app._workbench_sql_read_repository = FailingWorkbenchRepository()

        response = app.handle_request("GET", "/health")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["service"], "fin-ops-platform-api")
        self.assertNotIn("workbench_api_self_test", payload)

    def test_ready_endpoint_reports_readiness_without_workbench_api_self_test(self) -> None:
        app = build_application()

        class FailingWorkbenchRepository:
            def get_workbench_summary(self, *, scope_key: str):
                raise AssertionError("/health/ready must not run deep workbench self-test")

            def get_workbench_groups_page(self, **kwargs):
                raise AssertionError("/health/ready must not run deep workbench self-test")

        app._workbench_sql_read_repository = FailingWorkbenchRepository()

        response = app.handle_request("GET", "/health/ready")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn("storage", payload)
        self.assertIn("production_runtime_guard", payload)
        self.assertNotIn("workbench_api_self_test", payload)

    def test_health_endpoint_marks_release_import_path_mismatch_not_ready(self) -> None:
        app = build_application()

        with patch("fin_ops_platform.app.server.Path.cwd", return_value=Path("/opt/fin-ops/releases/main-test/src")):
            response = app.handle_request("GET", "/health")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "not_ready")
        runtime_release = payload["runtime_release"]
        self.assertEqual(runtime_release["is_release_runtime"], True)
        self.assertEqual(runtime_release["consistent"], False)
        self.assertIn("package_import_path_mismatch", runtime_release["problems"])
        self.assertIn("release_metadata_missing_or_invalid", runtime_release["problems"])

    def test_deep_health_endpoint_reports_workbench_api_self_test_counts(self) -> None:
        app = build_application()

        class WorkbenchRepository:
            def get_workbench_summary(self, *, scope_key: str):
                self.summary_scope_key = scope_key
                return {
                    "read_model_status": "fresh",
                    "summary": {"paired_count": 2, "open_count": 3},
                }

            def get_workbench_groups_page(self, **kwargs):
                self.last_page_size = kwargs["page_size"]
                zone = kwargs["zone"]
                return {
                    "read_model_status": "fresh",
                    "zone": zone,
                    "total": 10 if zone == "paired" else 20,
                    "groups": [{"id": f"{zone}-1"}],
                }

        repository = WorkbenchRepository()
        app._workbench_sql_read_repository = repository

        response = app.handle_request("GET", "/health/deep")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.last_page_size, 200)
        self.assertEqual(
            payload["workbench_api_self_test"],
            {
                "scope_key": "all",
                "status": "ok",
                "summary_status": "fresh",
                "summary_counts": {"paired_count": 2, "open_count": 3},
                "groups": {
                    "paired": {"status": "fresh", "total": 10, "returned_count": 1},
                    "open": {"status": "fresh", "total": 20, "returned_count": 1},
                },
                "errors": [],
            },
        )


if __name__ == "__main__":
    unittest.main()
