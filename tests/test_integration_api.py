import json
import unittest
from dataclasses import replace
from types import SimpleNamespace
from unittest.mock import patch

from tests.app_test_support import build_local_state_application as build_application


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

        enqueued: list[dict[str, object]] = []

        class QueueRepository:
            def enqueue(self, **kwargs: object) -> SimpleNamespace:
                enqueued.append(dict(kwargs))
                return SimpleNamespace(event_id="evt-oa-sync-001")

        app._runtime_repositories = replace(app._runtime_repositories, queue_repository=QueueRepository())

        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None) as auto_match:
            sync_response = app.handle_request(
                "POST",
                "/integrations/oa/sync",
                json.dumps({"actor_id": "user_finance_01", "scope": "all"}),
            )
        auto_match.assert_not_called()
        self.assertEqual(sync_response.status_code, 202)
        sync_payload = json.loads(sync_response.body)
        self.assertEqual(sync_payload["status"], "queued")
        self.assertEqual(sync_payload["event_id"], "evt-oa-sync-001")
        self.assertEqual(sync_payload["scope_key"], "all")
        self.assertEqual(enqueued[0]["event_type"], "oa.sync")
        self.assertEqual(enqueued[0]["scope_key"], "all")
        self.assertEqual(enqueued[0]["payload"]["triggered_by"], "user_finance_01")

        dashboard_response = app.handle_request("GET", "/integrations/oa")
        self.assertEqual(dashboard_response.status_code, 200)
        dashboard_payload = json.loads(dashboard_response.body)
        self.assertEqual(dashboard_payload["source_system"], "oa")
        self.assertEqual(dashboard_payload["summary"]["run_count"], 0)
        self.assertEqual(dashboard_payload["runs"], [])

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
