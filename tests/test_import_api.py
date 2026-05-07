import json
import unittest
from unittest.mock import patch

from fin_ops_platform.app.server import build_application


class ImportApiTests(unittest.TestCase):
    def test_preview_confirm_and_fetch_batch_round_trip(self) -> None:
        app = build_application()

        preview_response = app.handle_request(
            "POST",
            "/imports/preview",
            json.dumps(
                {
                    "batch_type": "output_invoice",
                    "source_name": "api-output-demo.json",
                    "imported_by": "user_finance_01",
                    "rows": [
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9801",
                            "counterparty_name": "API Corp",
                            "amount": "150.00",
                            "invoice_date": "2026-03-26",
                            "invoice_status_from_source": "valid",
                        },
                        {
                            "invoice_code": "033001",
                            "invoice_no": "9802",
                            "counterparty_name": "Broken Corp",
                            "amount": "oops",
                            "invoice_date": "2026-03-26",
                        },
                    ],
                }
            ),
        )

        self.assertEqual(preview_response.status_code, 200)
        preview_payload = json.loads(preview_response.body)
        self.assertEqual(preview_payload["batch"]["row_count"], 2)
        self.assertEqual(preview_payload["batch"]["success_count"], 1)
        self.assertEqual(preview_payload["row_results"][1]["decision"], "error")

        with patch.object(app, "_run_workbench_auto_matching_for_scopes", return_value=None) as auto_match:
            confirm_response = app.handle_request(
                "POST",
                "/imports/confirm",
                json.dumps({"batch_id": preview_payload["batch"]["id"]}),
            )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["batch"]["status"], "completed_with_errors")
        auto_match.assert_called_once()
        self.assertEqual(auto_match.call_args.kwargs["reason"], "import_confirm")
        self.assertEqual(auto_match.call_args.args[0], ["2026-02", "2026-03", "2026-04"])

        batch_response = app.handle_request(
            "GET",
            f"/imports/batches/{preview_payload['batch']['id']}",
        )
        self.assertEqual(batch_response.status_code, 200)
        batch_payload = json.loads(batch_response.body)
        self.assertEqual(batch_payload["batch"]["source_name"], "api-output-demo.json")
        self.assertEqual(len(batch_payload["row_results"]), 2)


if __name__ == "__main__":
    unittest.main()
