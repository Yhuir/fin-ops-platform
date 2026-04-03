import json
import unittest

from fin_ops_platform.app.server import build_application


class WorkbenchApiTests(unittest.TestCase):
    def test_workbench_query_and_confirm_action_round_trip(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "033001",
                    "invoice_no": "API-WB-001",
                    "counterparty_name": "Workbench API Client",
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
                    "account_no": "62228888",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Workbench API Client",
                    "debit_amount": "",
                    "credit_amount": "150.00",
                    "bank_serial_no": "API-WB-001",
                    "summary": "api receipt",
                }
            ],
        )

        run_response = app.handle_request(
            "POST",
            "/matching/run",
            json.dumps({"triggered_by": "user_finance_01"}),
        )
        run_payload = json.loads(run_response.body)
        result = run_payload["results"][0]

        workbench_before = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        invoice_id = workbench_before["open"]["invoice"][0]["id"]
        transaction_id = workbench_before["open"]["bank"][0]["id"]

        confirm_response = app.handle_request(
            "POST",
            "/workbench/actions/confirm",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "invoice_ids": [invoice_id],
                    "transaction_ids": [transaction_id],
                    "source_result_id": result["id"],
                    "oa_ids": ["OA-202603-120"],
                    "remark": "confirmed in API test",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["case"]["status"], "confirmed")
        self.assertEqual(len(confirm_payload["case"]["lines"]), 2)

        case_id = confirm_payload["case"]["id"]
        detail_response = app.handle_request("GET", f"/reconciliation/cases/{case_id}")
        self.assertEqual(detail_response.status_code, 200)
        detail_payload = json.loads(detail_response.body)
        self.assertEqual(detail_payload["case"]["source_result_id"], result["id"])

        workbench_after = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        self.assertEqual(len(workbench_after["paired"]["invoice"]), 1)
        self.assertEqual(len(workbench_after["paired"]["bank"]), 1)

    def test_exception_and_offline_actions_are_exposed_via_http(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "033002",
                    "invoice_no": "API-EXC-001",
                    "counterparty_name": "Exception API Client",
                    "amount": "90.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        workbench_payload = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        invoice_id = workbench_payload["open"]["invoice"][0]["id"]

        exception_response = app.handle_request(
            "POST",
            "/workbench/actions/exception",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "biz_side": "receivable",
                    "invoice_ids": [invoice_id],
                    "transaction_ids": [],
                    "exception_code": "SO-B",
                    "resolution_action": "create_follow_up_ledger",
                    "oa_ids": ["OA-202603-121"],
                    "note": "customer has not paid",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)
        exception_payload = json.loads(exception_response.body)
        self.assertEqual(exception_payload["exception_record"]["exception_code"], "SO-B")

        offline_response = app.handle_request(
            "POST",
            "/workbench/actions/offline",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "biz_side": "receivable",
                    "invoice_ids": [invoice_id],
                    "amount": "30.00",
                    "payment_method": "cash",
                    "occurred_on": "2026-03-29",
                    "note": "cash repayment",
                }
            ),
        )
        self.assertEqual(offline_response.status_code, 200)
        offline_payload = json.loads(offline_response.body)
        self.assertEqual(offline_payload["offline_record"]["payment_method"], "cash")

        cases_response = app.handle_request("GET", "/reconciliation/cases")
        self.assertEqual(cases_response.status_code, 200)
        cases_payload = json.loads(cases_response.body)
        self.assertEqual(len(cases_payload["cases"]), 2)

    def test_difference_and_offset_actions_are_exposed_via_http(self) -> None:
        app = build_application()
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "033101",
                    "invoice_no": "API-DIFF-001",
                    "counterparty_name": "Difference API Client",
                    "amount": "100.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "valid",
                },
                {
                    "invoice_code": "033102",
                    "invoice_no": "API-OFFSET-OUT-001",
                    "counterparty_name": "Offset API Counterparty",
                    "amount": "80.00",
                    "invoice_date": "2026-03-28",
                    "invoice_status_from_source": "valid",
                },
            ],
        )
        self._preview_and_confirm(
            app,
            "input_invoice",
            [
                {
                    "invoice_code": "044101",
                    "invoice_no": "API-OFFSET-IN-001",
                    "counterparty_name": "Offset API Counterparty",
                    "amount": "80.00",
                    "invoice_date": "2026-03-29",
                    "invoice_status_from_source": "valid",
                }
            ],
        )
        self._preview_and_confirm(
            app,
            "bank_transaction",
            [
                {
                    "account_no": "62227777",
                    "txn_date": "2026-03-29",
                    "counterparty_name": "Difference API Client",
                    "debit_amount": "",
                    "credit_amount": "99.50",
                    "bank_serial_no": "API-DIFF-BANK-001",
                    "summary": "receipt after fee",
                }
            ],
        )

        workbench_payload = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        difference_invoice_id = next(item["id"] for item in workbench_payload["open"]["invoice"] if item["sellerName"] == "杭州溯源科技有限公司" and item["buyerName"] == "Difference API Client")
        offset_receivable_id = next(item["id"] for item in workbench_payload["open"]["invoice"] if item["buyerName"] == "Offset API Counterparty")
        offset_payable_id = next(item["id"] for item in workbench_payload["open"]["invoice"] if item["sellerName"] == "Offset API Counterparty")
        transaction_id = workbench_payload["open"]["bank"][0]["id"]

        difference_response = app.handle_request(
            "POST",
            "/workbench/actions/difference",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "invoice_ids": [difference_invoice_id],
                    "transaction_ids": [transaction_id],
                    "difference_reason": "fee",
                    "difference_note": "0.50 bank fee",
                }
            ),
        )
        self.assertEqual(difference_response.status_code, 200)
        difference_payload = json.loads(difference_response.body)
        self.assertEqual(difference_payload["case"]["difference_reason"], "fee")

        offset_response = app.handle_request(
            "POST",
            "/workbench/actions/offset",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "receivable_invoice_ids": [offset_receivable_id],
                    "payable_invoice_ids": [offset_payable_id],
                    "reason": "same_counterparty_setoff",
                    "note": "api offset",
                }
            ),
        )
        self.assertEqual(offset_response.status_code, 200)
        offset_payload = json.loads(offset_response.body)
        self.assertEqual(offset_payload["offset_note"]["reason"], "same_counterparty_setoff")

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
