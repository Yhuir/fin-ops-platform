import json
import unittest

from tests.app_test_support import build_local_state_application as build_application
from tests.app_test_support import seed_confirmed_import


class MatchingApiTests(unittest.TestCase):
    def test_run_list_and_detail_matching_results(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "077001",
                    "invoice_no": "E5001",
                    "counterparty_name": "Echo Client",
                    "amount": "150.00",
                    "invoice_date": "2026-03-26",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        self._preview_and_confirm(
            app,
            "bank_transaction",
            [
                {
                    "account_no": "62224444",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Echo Client",
                    "debit_amount": "",
                    "credit_amount": "150.00",
                    "bank_serial_no": "MATCH-API-001",
                    "summary": "echo receipt",
                }
            ],
        )

        run_response = app.handle_request(
            "POST",
            "/matching/run",
            json.dumps({"triggered_by": "user_finance_01"}),
        )
        self.assertEqual(run_response.status_code, 200)
        run_payload = json.loads(run_response.body)
        self.assertEqual(run_payload["run"]["automatic_count"], 1)

        list_response = app.handle_request("GET", "/matching/results")
        self.assertEqual(list_response.status_code, 200)
        list_payload = json.loads(list_response.body)
        self.assertEqual(len(list_payload["runs"]), 1)
        self.assertEqual(len(list_payload["results"]), 1)

        result_id = list_payload["results"][0]["id"]
        detail_response = app.handle_request("GET", f"/matching/results/{result_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["result"]["rule_code"], "exact_counterparty_amount_one_to_one")

    def _preview_and_confirm(self, app, batch_type: str, rows: list[dict[str, str]]) -> None:
        seed_confirmed_import(
            app,
            batch_type=batch_type,
            source_name=f"{batch_type}.json",
            imported_by="user_finance_01",
            rows=rows,
        )


if __name__ == "__main__":
    unittest.main()
