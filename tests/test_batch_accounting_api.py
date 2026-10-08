from __future__ import annotations

import json
import tempfile
import unittest
from copy import deepcopy
from pathlib import Path

from fin_ops_platform.app.auth import OAUserIdentity
from fin_ops_platform.app.routes_batch_accounting import BatchAccountingApiRoutes
from fin_ops_platform.services.batch_accounting_service import BatchAccountingService

from tests.app_test_support import build_local_state_application, configure_access_control


class HistoryRepository:
    def __init__(self):
        self.calls = []
        self.snapshot = {
            "relation_count": 1,
            "transaction_count": 2,
            "available_years": ["2026"],
            "rows": [
                {
                    "relation_id": "CASE-BATCH-1",
                    "trade_time": "2026-01-01",
                    "bank_accounts": [{"bank_name": "建行", "account_last4": "8106"}],
                    "counterparty_names": ["甲"],
                    "bank_amount": "90",
                    "bank_count": 2,
                    "oa_count": 1,
                }
            ],
        }
        self.detail_payload = {
            "relation": {
                "case_id": "CASE-BATCH-1",
                "row_ids": ["bank-a", "bank-b", "oa-a", "inv-a"],
                "row_types": ["bank", "bank", "oa", "invoice"],
                "note": "历史备注",
            },
            "member_rows": [
                {
                    "member_type": "bank",
                    "id": "bank-a",
                    "payload": {"id": "bank-a", "amount": "100", "signed_amount": "-100"},
                },
                {
                    "member_type": "bank",
                    "id": "bank-b",
                    "payload": {"id": "bank-b", "amount": "-10", "signed_amount": "10"},
                },
                {"member_type": "oa", "id": "oa-a", "payload": {"id": "oa-a", "amount": "90"}},
                {
                    "member_type": "invoice",
                    "id": "inv-a",
                    "payload": {"id": "inv-a", "amount": "-10", "total_with_tax": "-11"},
                },
            ],
        }

    def list_snapshot(self, **query):
        self.calls.append(query)
        return deepcopy(self.snapshot)

    def detail_snapshot(self, relation_id):
        return deepcopy(self.detail_payload) if relation_id == "CASE-BATCH-1" else None


class BatchAccountingHistoryTests(unittest.TestCase):
    def setUp(self):
        self.repo = HistoryRepository()
        self.service = BatchAccountingService(query_repository=self.repo)
        self.routes = BatchAccountingApiRoutes(lambda: self.service)

    def test_list_contract_and_pagination(self):
        status, payload = self.routes.list_payload({"bank_year": ["2026"], "page": ["2"], "page_size": ["20"]})
        self.assertEqual(status, 200)
        self.assertEqual(self.repo.calls, [{"bank_year": "2026", "page": 2, "page_size": 20}])
        self.assertEqual(payload["summary"], {"relation_count": 1, "transaction_count": 2, "bank_year": "2026"})
        self.assertEqual(payload["rows"][0]["bank_amount"], "90.00")
        self.assertEqual(payload["pagination"], {"page": 2, "page_size": 20, "total": 1})
        self.assertEqual(set(payload), {"summary", "rows", "pagination", "available_years"})

    def test_all_years_and_empty_history(self):
        self.repo.snapshot.update(rows=[], relation_count=0, transaction_count=0, available_years=[])
        status, payload = self.routes.list_payload({})
        self.assertEqual(status, 200)
        self.assertIsNone(payload["summary"]["bank_year"])
        self.assertEqual(payload["rows"], [])
        self.assertEqual(payload["pagination"]["total"], 0)

    def test_invalid_and_retired_query_parameters_are_rejected(self):
        for query in (
            {"bucket": ["unsubmitted"]},
            {"bank_year": ["26"]},
            {"page": ["0"]},
            {"page": ["1.5"]},
            {"page_size": ["201"]},
            {"page": ["1", "2"]},
            {"bank_year": []},
        ):
            with self.subTest(query=query):
                status, payload = self.routes.list_payload(query)
                self.assertEqual(status, 400)
                self.assertIn("error", payload)
        self.assertEqual(self.repo.calls, [])

    def test_complete_detail_keeps_signed_amounts_and_source_note(self):
        status, payload = self.routes.detail("CASE-BATCH-1")
        self.assertEqual(status, 200)
        self.assertEqual(len(payload["bank_rows"]), 2)
        self.assertEqual(payload["bank_rows"][1]["amount"], "-10.00")
        self.assertEqual(payload["invoice_rows"][0]["total_with_tax"], "-11.00")
        self.assertEqual(
            (payload["bank_amount"], payload["oa_amount"], payload["amount_delta"]), ("90.00", "90.00", "0.00")
        )
        self.assertEqual(payload["note"], "历史备注")

    def test_missing_members_are_explicit_and_not_zero(self):
        self.repo.detail_payload["member_rows"] = self.repo.detail_payload["member_rows"][1:]
        payload = self.service.detail("CASE-BATCH-1")
        self.assertEqual(payload["missing_member_ids"], ["bank-a"])
        self.assertIsNone(payload["bank_amount"])
        self.assertIsNone(payload["amount_delta"])

    def test_null_oa_amount_is_not_zero(self):
        self.repo.detail_payload["member_rows"][2]["payload"]["amount"] = None
        payload = self.service.detail("CASE-BATCH-1")
        self.assertIsNone(payload["oa_rows"][0]["amount"])
        self.assertIsNone(payload["oa_amount"])

    def test_duplicate_members_are_not_summed_twice(self):
        relation = self.repo.detail_payload["relation"]
        relation["row_ids"].append("bank-a")
        relation["row_types"].append("bank")
        self.assertEqual(self.service.detail("CASE-BATCH-1")["bank_amount"], "90.00")

    def test_unknown_history_returns_404(self):
        status, payload = self.routes.detail("CASE-OTHER")
        self.assertEqual(status, 404)
        self.assertEqual(payload["error"], "batch_accounting_relation_not_found")

    def test_missing_repository_returns_503_for_list_and_detail(self):
        routes = BatchAccountingApiRoutes(BatchAccountingService)
        for status, payload in (routes.list_payload({}), routes.detail("CASE-BATCH-1")):
            self.assertEqual(status, 503)
            self.assertEqual(payload["error"], "batch_accounting_canonical_query_unavailable")

    def test_malformed_repository_amount_fails_explicitly(self):
        self.repo.snapshot["rows"][0]["bank_amount"] = "NaN"
        status, payload = self.routes.list_payload({})
        self.assertEqual(status, 503)
        self.assertEqual(payload["error"], "batch_accounting_invalid_amount")

    def test_canonical_type_aliases_are_supported(self):
        for invoice_type in ("input_invoice", "output_invoice", "etc_invoice_summary", " FORMAL "):
            self.repo.detail_payload["relation"]["row_types"] = [
                " BANK_TRANSACTION ",
                "bank",
                "OA_APPLICATION",
                invoice_type,
            ]
            status, payload = self.routes.detail("CASE-BATCH-1")
            self.assertEqual(status, 200)
            self.assertEqual(payload["invoice_rows"][0]["id"], "inv-a")
            self.assertEqual(payload["missing_member_ids"], [])

    def test_malformed_canonical_members_are_unavailable(self):
        for row_types in (["bank"], ["bank", "bank", "oa", "mystery"]):
            self.repo.detail_payload["relation"]["row_types"] = row_types
            status, payload = self.routes.detail("CASE-BATCH-1")
            self.assertEqual(status, 503)
            self.assertEqual(payload["error"], "batch_accounting_invalid_history")

    def test_real_server_history_permissions_and_retired_writes(self):
        with tempfile.TemporaryDirectory() as tmp:
            app = build_local_state_application(data_dir=Path(tmp))
            app._batch_accounting_query_repository = self.repo
            configure_access_control(
                app, page_access={"HISTORY001": ["batch-accounting"], "OTHER001": ["bank-details"]}
            )
            for username, expected in (("HISTORY001", 200), ("OTHER001", 403)):
                app._oa_identity_service.resolve_identity = lambda _token, u=username: OAUserIdentity(
                    user_id=u, username=u, nickname=u, display_name=u, roles=["finance"], permissions=[]
                )
                for path in ("/api/batch-accounting", "/api/batch-accounting/relations/CASE-BATCH-1"):
                    response = app.handle_request("GET", path, headers={"Authorization": f"Bearer {username}"})
                    self.assertEqual(response.status_code, expected, response.body)
                    self.assertIn(
                        "rows" if path.endswith("accounting") else "bank_rows", json.loads(response.body)
                    ) if expected == 200 else self.assertEqual(json.loads(response.body)["error"], "page_access_denied")
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="admin",
                username="YNSYLP005",
                nickname="admin",
                display_name="admin",
                roles=["finance"],
                permissions=[],
            )
            for method, path in (
                ("POST", "/api/batch-accounting/submit"),
                ("POST", "/api/batch-accounting/CASE-BATCH-1/withdraw"),
                ("PUT", "/api/batch-accounting/tag-rules"),
                ("GET", "/api/batch-accounting/tag-rules"),
            ):
                response = app.handle_request(method, path, body="{}", headers={"Authorization": "Bearer admin"})
                self.assertEqual(response.status_code, 404, response.body)
