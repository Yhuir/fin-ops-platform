import json
import unittest

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
        self.assertIn("oa_session_foundation", payload["capabilities"])
        self.assertIn("project_costing_foundation", payload["capabilities"])
        self.assertIn("workbench_v2_backend_contracts", payload["capabilities"])
        self.assertIn("cost_statistics_foundation", payload["capabilities"])
        self.assertIn("cost_statistics_export", payload["capabilities"])
        self.assertIn("workbench_global_search_foundation", payload["capabilities"])


if __name__ == "__main__":
    unittest.main()
