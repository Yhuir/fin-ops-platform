import json
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_identity_service import OAUserIdentity


class LedgerApiTests(unittest.TestCase):
    def _install_user_auth(self, app, username: str = "user_finance_01") -> dict[str, str]:
        app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
            user_id=f"{username}-id",
            username=username,
            nickname=username,
            display_name=username,
            roles=["finance"],
            permissions=["finops:app:view"],
        )
        return {"Authorization": "Bearer ledger-token"}

    def test_workbench_confirm_auto_creates_ledger_and_supports_due_views(self) -> None:
        app = build_application()
        headers = self._install_user_auth(app)
        self._preview_and_confirm(
            app,
            "output_invoice",
            [
                {
                    "invoice_code": "033201",
                    "invoice_no": "API-LEDGER-001",
                    "counterparty_name": "Ledger API Client",
                    "amount": "100.00",
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
                    "account_no": "62149999",
                    "txn_date": "2026-03-27",
                    "counterparty_name": "Ledger API Client",
                    "debit_amount": "",
                    "credit_amount": "60.00",
                    "bank_serial_no": "API-LEDGER-BANK-001",
                    "summary": "partial receipt",
                }
            ],
        )
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
                    "remark": "partial receivable settlement",
                }
            ),
        )
        self.assertEqual(confirm_response.status_code, 200)
        confirm_payload = json.loads(confirm_response.body)
        self.assertEqual(confirm_payload["ledgers"][0]["ledger_type"], "payment_collection")

        ledgers_response = app.handle_request("GET", "/ledgers?view=all", headers=headers)
        self.assertEqual(ledgers_response.status_code, 200)
        ledgers_payload = json.loads(ledgers_response.body)
        self.assertEqual(len(ledgers_payload["ledgers"]), 1)
        self.assertEqual(ledgers_payload["ledgers"][0]["counterparty_name"], "Ledger API Client")
        self.assertNotIn("source_object_id", ledgers_payload["ledgers"][0])
        self.assertNotIn("owner_id", ledgers_payload["ledgers"][0])

        overdue_response = app.handle_request("GET", "/ledgers?view=overdue&as_of=2026-04-10", headers=headers)
        self.assertEqual(overdue_response.status_code, 200)
        overdue_payload = json.loads(overdue_response.body)
        self.assertEqual(len(overdue_payload["ledgers"]), 1)

    def test_reminder_run_and_ledger_status_update_round_trip(self) -> None:
        app = build_application()
        headers = self._install_user_auth(app)
        self._preview_and_confirm(
            app,
            "bank_transaction",
            [
                {
                    "account_no": "62140009",
                    "txn_date": "2026-03-28",
                    "counterparty_name": "No Invoice Yet",
                    "debit_amount": "",
                    "credit_amount": "88.00",
                    "bank_serial_no": "API-LEDGER-BANK-002",
                    "summary": "receipt before invoice",
                }
            ],
        )
        workbench_before = json.loads(app.handle_request("GET", "/workbench?month=2026-03").body)
        transaction_id = workbench_before["open"]["bank"][0]["id"]

        exception_response = app.handle_request(
            "POST",
            "/workbench/actions/exception",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "biz_side": "receivable",
                    "invoice_ids": [],
                    "transaction_ids": [transaction_id],
                    "exception_code": "SO-B",
                    "resolution_action": "create_follow_up_ledger",
                    "note": "money received before invoice issued",
                }
            ),
        )
        self.assertEqual(exception_response.status_code, 200)
        exception_payload = json.loads(exception_response.body)
        ledger_id = exception_payload["ledgers"][0]["id"]

        run_response = app.handle_request(
            "POST",
            "/reminders/run",
            json.dumps({"as_of": "2026-04-10", "actor_id": "user_finance_01"}),
            headers=headers,
        )
        self.assertEqual(run_response.status_code, 202)
        run_payload = json.loads(run_response.body)
        self.assertEqual(run_payload["job"]["type"], "reminder_run")
        self.assertEqual(run_payload["job"]["owner_user_id"], "user_finance_01")

        app._ledger_service.run_reminders(as_of="2026-04-10")
        reminders_response = app.handle_request("GET", "/reminders?as_of=2026-04-10&status=sent", headers=headers)
        self.assertEqual(reminders_response.status_code, 200)
        reminders_payload = json.loads(reminders_response.body)
        self.assertEqual(len(reminders_payload["reminders"]), 1)
        self.assertNotIn("channel", reminders_payload["reminders"][0])
        self.assertRegex(reminders_payload["reminders"][0]["remind_at"], r"T")

        update_response = app.handle_request(
            "POST",
            f"/ledgers/{ledger_id}/status",
            json.dumps(
                {
                    "actor_id": "user_finance_01",
                    "status": "resolved",
                    "note": "invoice issued and closed",
                    "expected_date": "2026-04-12",
                }
            ),
            headers=headers,
        )
        self.assertEqual(update_response.status_code, 200)
        update_payload = json.loads(update_response.body)
        self.assertEqual(update_payload["ledger"]["status"], "resolved")
        self.assertEqual(update_payload["ledger"]["events"][0]["event_type"], "status_changed")
        self.assertEqual(update_payload["ledger"]["events"][0]["event_payload"]["note"], "invoice issued and closed")
        self.assertNotIn("latest_note", update_payload["ledger"])

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
