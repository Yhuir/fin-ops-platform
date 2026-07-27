import json
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import Response, _build_handler_factory
from tests.app_test_support import build_local_state_application as build_application


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
        self.assertIn("/metrics", payload["entrypoints"])
        self.assertIn("/ledgers", payload["entrypoints"])
        self.assertIn("/integrations/oa", payload["entrypoints"])
        self.assertIn("/integrations/oa/sync", payload["entrypoints"])
        self.assertIn("/projects", payload["entrypoints"])
        self.assertIn("/projects/assign", payload["entrypoints"])
        self.assertIn("/api/workbench", payload["entrypoints"])
        self.assertIn("/api/session/me", payload["entrypoints"])
        self.assertIn("/api/tax-offset", payload["entrypoints"])
        self.assertIn("/api/tax-offset/calculate", payload["entrypoints"])
        self.assertIn("/api/cost-statistics/explorer", payload["entrypoints"])
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
        self.assertNotIn("input_invoice_usage_read_model", payload["capabilities"])
        self.assertNotIn("output_invoice_collection_read_model", payload["capabilities"])
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
        self.assertIn("entrypoint_count", payload)
        self.assertNotIn("entrypoints", payload)
        self.assertNotIn("workbench_api_self_test", payload)

    def test_ready_endpoint_bounds_api_performance_payload(self) -> None:
        app = build_application()
        for index in range(25):
            app._api_performance_recorder.record_request(
                method="GET",
                route_path=f"/api/example-{index:02d}",
                status_code=200,
                duration_ms=float(index),
            )

        response = app.handle_request("GET", "/health/ready")
        payload = json.loads(response.body)
        api_performance = payload["api_performance"]

        self.assertEqual(response.status_code, 200)
        self.assertEqual(api_performance["endpoint_count"], 25)
        self.assertEqual(api_performance["omitted_endpoint_count"], 5)
        self.assertEqual(len(api_performance["endpoints"]), 20)
        self.assertIn("GET /api/example-24", api_performance["endpoints"])
        self.assertNotIn("GET /api/example-00", api_performance["endpoints"])

    @patch.dict("os.environ", {"FIN_OPS_PROMETHEUS_BEARER_TOKEN": ""})
    def test_metrics_endpoint_is_hidden_when_token_is_not_configured(self) -> None:
        app = build_application()

        response = app.handle_request("GET", "/metrics")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error"], "not_found")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)

    @patch.dict("os.environ", {"FIN_OPS_PROMETHEUS_BEARER_TOKEN": "metric-token"})
    def test_metrics_endpoint_rejects_missing_or_wrong_token(self) -> None:
        app = build_application()

        missing_response = app.handle_request("GET", "/metrics")
        wrong_response = app.handle_request("GET", "/metrics", headers={"Authorization": "Bearer wrong-token"})

        self.assertEqual(missing_response.status_code, 403)
        self.assertEqual(wrong_response.status_code, 403)
        self.assertNotIn("Access-Control-Allow-Origin", missing_response.headers)
        self.assertNotIn("Access-Control-Allow-Origin", wrong_response.headers)

    @patch.dict("os.environ", {"FIN_OPS_PROMETHEUS_BEARER_TOKEN": "metric-token"})
    def test_metrics_endpoint_exports_prometheus_text_without_workbench_api_self_test(self) -> None:
        app = build_application()

        class FailingWorkbenchRepository:
            def get_workbench_summary(self, *, scope_key: str):
                raise AssertionError("/metrics must not run deep workbench self-test")

            def get_workbench_groups_page(self, **kwargs):
                raise AssertionError("/metrics must not run deep workbench self-test")

        app._workbench_sql_read_repository = FailingWorkbenchRepository()

        response = app.handle_request("GET", "/metrics", headers={"Authorization": "Bearer metric-token"})
        body = response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["Content-Type"], "text/plain; version=0.0.4; charset=utf-8")
        self.assertNotIn("Access-Control-Allow-Origin", response.headers)
        self.assertIn("# TYPE finops_ready gauge", body)
        self.assertIn("finops_ready", body)

    @patch.dict("os.environ", {"FIN_OPS_PROMETHEUS_BEARER_TOKEN": "metric-token"})
    def test_metrics_endpoint_exports_full_api_performance_payload(self) -> None:
        app = build_application()
        for index in range(25):
            app._api_performance_recorder.record_request(
                method="GET",
                route_path=f"/api/example-{index:02d}",
                status_code=200,
                duration_ms=float(index),
            )

        response = app.handle_request("GET", "/metrics", headers={"Authorization": "Bearer metric-token"})
        body = response.body.decode("utf-8") if isinstance(response.body, bytes) else str(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn('endpoint="GET /api/example-00"', body)
        self.assertIn('endpoint="GET /api/example-24"', body)

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

    def test_http_handler_ignores_stream_client_disconnect_without_traceback(self) -> None:
        class FakeApp:
            def handle_request(self, method, path, body=None, headers=None):  # noqa: ANN001
                self.request = {
                    "method": method,
                    "path": path,
                    "body": body,
                    "headers": dict(headers or {}),
                }
                return Response(
                    status_code=200,
                    body=iter(["data: ok\n\n"]),
                    stream=True,
                    headers={"Content-Type": "text/event-stream"},
                )

        class ClosedWfile:
            def write(self, _data):  # noqa: ANN001
                raise BrokenPipeError()

            def flush(self) -> None:
                raise AssertionError("flush should not run after a failed write")

        fake_app = FakeApp()
        handler_class = _build_handler_factory(fake_app)
        handler = handler_class.__new__(handler_class)
        handler.headers = {"X-Test": "1"}
        handler.rfile = BytesIO()
        handler.path = "/api/app-health/stream"
        handler.wfile = ClosedWfile()
        handler.send_response = lambda status_code: None
        handler.send_header = lambda key, value: None
        handler.end_headers = lambda: None

        with patch("fin_ops_platform.app.server.traceback.print_exc") as print_exc:
            handler._dispatch("GET")

        self.assertEqual(fake_app.request["method"], "GET")
        print_exc.assert_not_called()


if __name__ == "__main__":
    unittest.main()
