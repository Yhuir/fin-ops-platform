from __future__ import annotations

import json
import tempfile
import time
import unittest
from decimal import Decimal
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.domain.enums import TransactionDirection
from fin_ops_platform.domain.models import BankTransaction
from fin_ops_platform.services.imports import ImportNormalizationService


def bank_transaction(
    transaction_id: str,
    *,
    category_code: str = "fee",
    direction: TransactionDirection = TransactionDirection.OUTFLOW,
    amount: str = "12.34",
    account_no: str = "6222000000008106",
    bank_name: str = "建行",
    account_last4: str = "8106",
    trade_time: str = "2026-03-10T09:00:00",
) -> BankTransaction:
    signed_amount = Decimal(amount) if direction == TransactionDirection.INFLOW else -Decimal(amount)
    return BankTransaction(
        id=transaction_id,
        account_no=account_no,
        txn_direction=direction,
        counterparty_name_raw="云南三源",
        amount=Decimal(amount),
        signed_amount=signed_amount,
        txn_date=trade_time[:10],
        trade_time=trade_time,
        pay_receive_time=trade_time,
        imported_bank_name=bank_name,
        imported_bank_last4=account_last4,
        summary=category_code,
        remark=category_code,
    )


class NoOaBankBatchApiTests(unittest.TestCase):
    def _app_with_transactions(self, transactions: list[BankTransaction], categories: dict[str, str] | None = None):
        app = build_application()
        app._import_service = ImportNormalizationService(existing_transactions=transactions)
        updates = [
            {"transaction_id": transaction.id, "category_code": (categories or {}).get(transaction.id, "fee")}
            for transaction in transactions
        ]
        if updates:
            app._bank_transaction_category_service.apply_updates(updates, actor="tester")
        return app

    def _list_batches(self, app):
        response = app.handle_request("GET", "/api/no-oa-bank-batches")
        self.assertEqual(response.status_code, 200, response.body)
        return json.loads(response.body)

    def test_list_returns_summary_and_batches(self) -> None:
        app = self._app_with_transactions(
            [
                bank_transaction("bank-202603-fee-1", amount="3.00"),
                bank_transaction("bank-202603-fee-2", amount="2.50"),
            ]
        )

        payload = self._list_batches(app)

        self.assertEqual(payload["summary"]["total"], 1)
        self.assertEqual(payload["summary"]["draft"], 1)
        self.assertEqual(payload["batches"][0]["row_count"], 2)
        self.assertEqual(payload["batches"][0]["total_amount"], "5.50")

    def test_detail_returns_batch_and_serialized_rows(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch_id = self._list_batches(app)["batches"][0]["batch_id"]

        response = app.handle_request("GET", f"/api/no-oa-bank-batches/{batch_id}")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["batch"]["batch_id"], batch_id)
        self.assertEqual(payload["rows"][0]["id"], "bank-202603-fee-1")
        self.assertEqual(payload["rows"][0]["category_code"], "fee")

    def test_submit_persists_batch_and_pair_relation_and_invalidates_workbench(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
            app._state_store = build_application(data_dir=Path(temp_dir))._state_store
            batch = self._list_batches(app)["batches"][0]

            response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
                body=json.dumps({"expected_version": batch["version"], "note": "确认免OA"}),
            )
            payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(payload["batch"]["status"], "submitted")
            self.assertEqual(payload["pair_relation"]["relation_mode"], "no_oa_bank_batch")
            self.assertEqual(payload["affected_months"], ["2026-03"])
            self.assertTrue(payload["workbench_rebuild_queued"])
            self.assertEqual(payload["results"][0]["status"], "submitted")
            self.assertEqual(app._state_store.load_no_oa_bank_batches()["batches"][batch["batch_id"]]["status"], "submitted")
            pair_relations = app._state_store.load().get("workbench_pair_relations", {}).get("pair_relations", {})
            self.assertIn(payload["pair_relation"]["case_id"], pair_relations)

    def test_withdraw_cancels_pair_relation_and_persists_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
            app._state_store = build_application(data_dir=Path(temp_dir))._state_store
            batch = self._list_batches(app)["batches"][0]
            submit_response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
                body=json.dumps({"expected_version": batch["version"]}),
            )
            submitted = json.loads(submit_response.body)["batch"]

            response = app.handle_request(
                "POST",
                f"/api/no-oa-bank-batches/{submitted['batch_id']}/withdraw",
                body=json.dumps({"expected_version": submitted["version"], "reason": "误提交"}),
            )
            payload = json.loads(response.body)

            self.assertEqual(response.status_code, 200, response.body)
            self.assertEqual(payload["batch"]["status"], "withdrawn")
            self.assertEqual(payload["pair_relation"]["status"], "cancelled")
            self.assertIsNone(app._workbench_pair_relation_service.get_active_relation_by_case_id(submitted["relation_case_id"]))
            self.assertEqual(app._state_store.load_no_oa_bank_batches()["batches"][submitted["batch_id"]]["status"], "withdrawn")

    def test_bulk_submit_returns_partial_results(self) -> None:
        transactions = [
            bank_transaction("bank-202603-fee-1", amount="3.00"),
            bank_transaction(
                "bank-202604-salary-1",
                category_code="salary",
                amount="1000.00",
                trade_time="2026-04-10T09:00:00",
            ),
        ]
        app = self._app_with_transactions(
            transactions,
            categories={"bank-202603-fee-1": "fee", "bank-202604-salary-1": "salary"},
        )
        batches = self._list_batches(app)["batches"]
        draft_by_type = {batch["batch_type"]: batch for batch in batches}

        response = app.handle_request(
            "POST",
            "/api/no-oa-bank-batches/submit",
            body=json.dumps(
                {
                    "batches": [
                        {
                            "batch_id": draft_by_type["fee"]["batch_id"],
                            "expected_version": draft_by_type["fee"]["version"],
                        },
                        {
                            "batch_id": draft_by_type["salary"]["batch_id"],
                            "expected_version": 999,
                        },
                    ]
                }
            ),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200, response.body)
        self.assertEqual(payload["summary"]["submitted"], 1)
        self.assertEqual(payload["summary"]["failed"], 1)
        self.assertEqual([result["status"] for result in payload["results"]], ["submitted", "failed"])
        self.assertEqual(payload["results"][1]["error"], "no_oa_bank_batch_version_conflict")

    def test_submit_version_conflict_returns_409(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]

        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body=json.dumps({"expected_version": 999}),
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 409)
        self.assertEqual(payload["error"], "no_oa_bank_batch_version_conflict")

    def test_invalid_json_body_returns_json_error(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])
        batch = self._list_batches(app)["batches"][0]

        response = app.handle_request(
            "POST",
            f"/api/no-oa-bank-batches/{batch['batch_id']}/submit",
            body="{bad json",
        )
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(payload["error"], "invalid_json_body")

    def test_unknown_batch_returns_404(self) -> None:
        app = self._app_with_transactions([bank_transaction("bank-202603-fee-1", amount="3.00")])

        response = app.handle_request("GET", "/api/no-oa-bank-batches/no_oa_batch_missing")
        payload = json.loads(response.body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error"], "unknown_no_oa_bank_batch")


if __name__ == "__main__":
    unittest.main()
