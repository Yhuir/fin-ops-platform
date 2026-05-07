import json
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application


class OAIntegrationApiTests(unittest.TestCase):
    def test_dashboard_sync_and_retry_round_trip(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "033601",
                    "invoice_no": "OA-API-001",
                    "counterparty_name": "Acme Supplies",
                    "amount": "180.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )

        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None) as auto_match:
            sync_response = app.handle_request(
                "POST",
                "/integrations/oa/sync",
                json.dumps({"actor_id": "user_finance_01", "scope": "all"}),
            )
        auto_match.assert_called_once()
        self.assertEqual(auto_match.call_args.kwargs["reason"], "oa_integration_sync")
        self.assertEqual(sync_response.status_code, 200)
        sync_payload = json.loads(sync_response.body)
        run_id = sync_payload["run"]["id"]
        self.assertEqual(sync_payload["run"]["scope"], "all")

        dashboard_response = app.handle_request("GET", "/integrations/oa")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = json.loads(dashboard_response.body)
        self.assertGreaterEqual(dashboard_payload["summary"]["project_count"], 2)
        self.assertGreaterEqual(dashboard_payload["summary"]["document_count"], 4)
        self.assertEqual(dashboard_payload["mappings"][0]["source_system"], "oa")

        runs_response = app.handle_request("GET", "/integrations/oa/sync-runs")
        self.assertEqual(runs_response.status_code, 200)
        runs_payload = json.loads(runs_response.body)
        self.assertEqual(len(runs_payload["runs"]), 1)

        detail_response = app.handle_request("GET", f"/integrations/oa/sync-runs/{run_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["run"]["id"], run_id)

        retry_response = app.handle_request(
            "POST",
            "/integrations/oa/sync",
            json.dumps({"actor_id": "user_finance_01", "retry_run_id": run_id}),
        )
        self.assertEqual(retry_response.status_code, 200)
        retry_payload = json.loads(retry_response.body)
        self.assertEqual(retry_payload["run"]["retry_of_run_id"], run_id)

    def _preview_and_confirm(self, app, batch_type: str, rows: list[dict[str, str]]) -> None:
        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": batch_type,
                    "source_name": f"{batch_type}.json",
                    "imported_by": "user_finance_01",
                    "rows": rows,
                }
            ),
        )
        preview_payload = json.loads(preview_response.body)
        app.handle_request(
            "POST",
            "/imports/confirm",
            json.dumps({"batch_id": preview_payload["batch"]["id"]}),
        )


if __name__ == "__main__":
    unittest.main()
