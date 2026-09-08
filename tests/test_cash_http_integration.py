"""Loopback HTTP -> Application -> CashRuntime -> real disposable PostgreSQL.

Only the local identity, ordinary App state, clock and unavailable OA configuration
are fixtures. Cash commands, queries, task processing and database transactions
are the production implementations; the caller prepares an isolated test schema.
"""

from __future__ import annotations

import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import unittest
from datetime import date
from functools import partial
from pathlib import Path
from socketserver import ThreadingMixIn
from unittest.mock import patch
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from uuid import uuid4
from wsgiref.simple_server import WSGIRequestHandler, WSGIServer, make_server

from fin_ops_platform.app.cash_runtime import CashRuntime
from fin_ops_platform.app.http_adapter import WsgiHttpAdapter
from fin_ops_platform.services.cash_service import CashService
from fin_ops_platform.services.cash_tasks import CashTaskService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings

from tests.app_test_support import DEFAULT_TEST_OA_TOKEN, build_local_state_application
from tests.postgres_test_utils import apply_test_migrations, assert_safe_test_database_url


class _ThreadingServer(ThreadingMixIn, WSGIServer):
    daemon_threads = False
    block_on_close = True


class _QuietHandler(WSGIRequestHandler):
    def log_message(self, _format, *args):
        # Synthetic fixture values do not need an additional raw HTTP access log.
        pass


def _reset_cash_fixture(connection):
    connection.execute("TRUNCATE cash.settlements,cash.items,cash.flows,cash.task_occurrences,cash.task_templates,cash.accounts,cash.categories,cash.bill_labels,cash.deleted_submission_ids")
    connection.execute("UPDATE cash.settings SET personal_opening_date=NULL,personal_counterparty=NULL,allowed_project_stage_codes='{}',project_selection_configured=false,version=1 WHERE id=1")


@unittest.skipUnless(os.environ.get("FIN_OPS_CASH_TEST_DATABASE_URL"), "Explicit disposable cash PostgreSQL DSN required")
class CashHttpPostgresTests(unittest.TestCase):
    period = "date_from=2026-09-01&date_to=2026-09-30"

    @classmethod
    def setUpClass(cls):
        dsn = os.environ["FIN_OPS_CASH_TEST_DATABASE_URL"]
        connection = PostgresConnection(PostgresSettings(dsn, pool_enabled=False))
        cls.addClassCleanup(connection.close)
        if not connection.fetch_one("SELECT current_database() AS name")["name"].startswith("fin_ops_cash_test_"):
            raise RuntimeError("HTTP writes require an explicit fin_ops_cash_test_* database")
        apply_test_migrations(dsn)

    def setUp(self):
        dsn = os.environ["FIN_OPS_CASH_TEST_DATABASE_URL"]
        assert_safe_test_database_url(dsn)
        connection = PostgresConnection(PostgresSettings(dsn, pool_enabled=False))
        self.addCleanup(connection.close)
        actual = connection.fetch_one("SELECT current_database() AS name")["name"]
        if not actual.startswith("fin_ops_cash_test_"):
            raise RuntimeError("HTTP writes require an explicit fin_ops_cash_test_* database")
        _reset_cash_fixture(connection)
        self.addCleanup(_reset_cash_fixture, connection)
        self.connection = connection
        temporary = tempfile.TemporaryDirectory(prefix="finops-cash-http-")
        self.addCleanup(temporary.cleanup)
        # Existing ordinary App fixture; no production identity, role or OA write.
        with patch.dict(os.environ, {"FIN_OPS_POSTGRES_DATABASE_URL": "", "DATABASE_URL": ""}):
            application = build_local_state_application(data_dir=Path(temporary.name))
        self.addCleanup(application.close)
        for target, value in (
            ("load_mongo_oa_settings", lambda _: None),
            ("CashService", partial(CashService, today=lambda: date(2026, 9, 7))),
            ("CashTaskService", partial(CashTaskService, today=lambda: date(2026, 9, 7))),
        ):
            patcher = patch("fin_ops_platform.app.cash_runtime." + target, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        with patch.dict(os.environ, {"FIN_OPS_POSTGRES_DATABASE_URL": dsn}):
            application._cash_runtime = CashRuntime(None)
        self.application = application
        server = make_server("127.0.0.1", 0, WsgiHttpAdapter(application), _ThreadingServer, _QuietHandler)
        thread = threading.Thread(target=server.serve_forever, kwargs={"poll_interval": 0.05}, name="cash-http-test")
        thread.start()

        def close_server():
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)
            self.assertFalse(thread.is_alive(), "Local HTTP server must stop before fixture cleanup")

        self.addCleanup(close_server)
        self.base_url = f"http://127.0.0.1:{server.server_port}"
        self.account = self.call("POST", "/settings/accounts", {
            "id": self.uid(), "name": "Synthetic HTTP cash", "kind": "cash",
            "opening_date": "2026-01-01", "opening_amount": "1000.00",
        }, status=201)["account"]
        self.category = self.call("POST", "/settings/categories", {
            "id": self.uid(), "name": "Synthetic HTTP turnover", "group": "turnover",
        }, status=201)["category"]
        self.payment_category = self.call("POST", "/settings/categories", {
            "id": self.uid(), "name": "Synthetic HTTP expense", "group": "payment",
        }, status=201)["category"]

    @staticmethod
    def uid():
        return str(uuid4())

    def call(self, method, path, body=None, *, status=200):
        request = Request(self.base_url + "/api/cash" + path,
                          data=json.dumps(body).encode() if body is not None else None,
                          headers={"Authorization": "Bearer " + DEFAULT_TEST_OA_TOKEN,
                                   "Content-Type": "application/json"}, method=method)
        try:
            response = urlopen(request, timeout=10)
        except HTTPError as error:
            response = error
        with response:
            payload = json.load(response)
            self.assertEqual(response.status, status, payload)
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            self.assertTrue(response.headers["X-Request-ID"])
            return payload

    def flow_payload(self, *, amount="100.00", kind="payment", **changes):
        # CashFlowDrawer + flowCompositionPayload shape, including explicit nulls.
        return {"id": self.uid(), "occurred_on": "2026-09-03", "kind": kind, "amount": amount,
                "from_account_id": self.account["id"] if kind == "payment" else None,
                "to_account_id": self.account["id"] if kind == "receipt" else None,
                "category_id": self.category["id"], "content": "Synthetic HTTP flow",
                "person_name": None, "remark": None, "project_mode": "selection", "oa_project_id": None,
                "related_items": [], "origin_items": [], "allocations": [], **changes}

    def loan_payload(self):
        return {"id": self.uid(), "type": "loan", "origin_date": "2026-09-03", "original_amount": "100.00",
                "content": "Synthetic HTTP loan", "oa_project_id": None, "counterparty": "Synthetic company",
                "ledger_group": "company", "obligation_direction": "receivable"}

    def item(self, identity):
        return self.call("GET", "/items/" + identity)

    def flow(self, identity):
        return self.call("GET", "/flows/" + identity)

    def assert_balance(self, expected, *, flow_count):
        rows = self.call("GET", "/flows?" + self.period + "&account_id=" + self.account["id"])
        self.assertEqual(rows["pagination"]["total"], flow_count)
        self.assertEqual(rows["summary"]["account_balances"][0]["ending_balance"], expected)

    def delete_flow(self, identity, **corrections):
        flow = self.flow(identity)["flow"]
        return self.call("POST", f"/flows/{identity}/delete", {"expected_version": flow["version"], **corrections})

    def repayment_payload(self, loan_id, amount):
        loan = self.item(loan_id)["item"]
        flow = self.flow_payload(amount=amount, kind="receipt", project_mode="existing_item",
                                 project_item_id=loan_id, expected_project_item_version=loan["version"],
                                 allocations=[{"id": self.uid(), "item_id": loan_id, "target_is_new": False,
                                               "expected_item_version": loan["version"], "kind": "cash_repayment", "amount": amount}])
        del flow["oa_project_id"]
        del flow["related_items"]
        del flow["origin_items"]
        return flow

    def assert_empty_reports(self):
        for report in ("turnover", "ticket-payments"):
            result = self.call("GET", "/reports/" + report + "?" + self.period)
            self.assertEqual(result["rows"], [])
            self.assertEqual(result["pagination"]["total"], 0)
        personal = self.call("GET", "/reports/personal?year=2026")
        self.assertIsNone(personal["summary"]["remaining_obligation_amount"])
        self.assertEqual(self.call("GET", "/items?purpose=list")["pagination"]["total"], 0)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.settlements")["n"], 0)

    def test_ui_flow_task_replay_delete_correction_and_atomic_failures(self):
        ordinary_before = self.connection.fetch_one("SELECT (SELECT count(*) FROM app.bank_transactions) AS bank_count,(SELECT count(*) FROM audit.events) AS audit_count")
        loan = self.loan_payload()
        expense = {"id": self.uid(), "type": "expense", "origin_date": "2026-09-03", "original_amount": "100.00",
                   "content": "Synthetic HTTP expense", "oa_project_id": None, "category_id": self.payment_category["id"]}
        payload = self.flow_payload(related_items=[loan, expense])
        source = self.call("POST", "/flows", payload, status=201)["flow"]
        self.assertEqual(source["source_kind"], "manual")
        self.assertEqual(self.item(expense["id"])["amounts"]["paid_amount"], "100.00")
        self.assertEqual(self.item(loan["id"])["amounts"]["remaining_obligation_amount"], "100.00")
        self.assert_balance("900.00", flow_count=1)
        turnover = self.call("GET", "/reports/turnover?" + self.period)
        self.assertEqual(turnover["summary"]["principal_amount"], "100.00")
        self.assertEqual(turnover["summary"]["cash_paid_amount"], "100.00")
        # Invalid allocation occurs after creation has begun; the whole command rolls back.
        invalid_expense = {**expense, "id": self.uid()}
        invalid_flow = self.flow_payload(related_items=[invalid_expense], allocations=[{
            "id": self.uid(), "item_id": invalid_expense["id"], "target_is_new": True, "expected_item_version": None,
            "kind": "expense_payment", "amount": "100.00",
        }])
        failure = self.call("POST", "/flows", invalid_flow, status=409)
        self.assertEqual(failure["error"], "cash_allocation_conflict")
        self.assertEqual(self.call("GET", "/items?purpose=list")["pagination"]["total"], 2)
        self.call("GET", "/flows/" + invalid_flow["id"], status=404)
        conflict = self.call("PUT", "/flows/" + source["id"], {"expected_version": 999, "amount": "80.00"}, status=409)
        self.assertEqual(conflict["error"], "cash_version_conflict")
        self.assert_balance("900.00", flow_count=1)
        malformed = self.call("POST", "/flows", self.flow_payload(amount=1.5), status=400)
        self.assertEqual(malformed["error"], "cash_invalid_input")

        template = self.call("POST", "/tasks", {
            "id": self.uid(), "title": "Synthetic HTTP repayment", "kind": "receipt", "execution_day": 5,
            "remind_days": 2, "effective_from_month": "2026-09", "default_amount": "100.00",
            "default_account_id": self.account["id"], "default_category_id": self.category["id"],
            "instructions": "Synthetic monthly instructions",
        }, status=201)["template"]
        identity = {"template_id": template["id"], "month": "2026-09", "expected_version": None,
                    "expected_template_version": template["version"]}
        # Wrong cash direction must not materialize even the first task occurrence.
        self.call("POST", "/task-occurrences/confirm", {**identity, "mode": "new_flow", "new_flow": self.flow_payload()}, status=400)
        virtual = self.call("GET", "/task-occurrences?month=2026-09")["rows"][0]
        self.assertIsNone(virtual["occurrence_id"])
        self.assertEqual(virtual["instructions"], "Synthetic monthly instructions")
        first_payload = {**identity, "mode": "new_flow", "new_flow": self.repayment_payload(loan["id"], "30.00")}
        first = self.call("POST", "/task-occurrences/confirm", first_payload)
        self.assertEqual(first["occurrence"]["state"], "partial")
        self.assertEqual(first["occurrence"]["actual_amount"], "30.00")
        self.assertEqual(first["flow"]["source_kind"], "monthly_task")
        replay = self.call("POST", "/task-occurrences/confirm", first_payload)
        self.assertEqual(replay["flow"]["id"], first["flow"]["id"])
        self.assertEqual(replay["occurrence"]["flow_count"], 1)
        self.assert_balance("930.00", flow_count=2)
        second = self.call("POST", "/task-occurrences/confirm", {
            "template_id": template["id"], "month": "2026-09", "expected_version": first["version"],
            "mode": "new_flow", "new_flow": self.repayment_payload(loan["id"], "70.00"),
        })
        self.assertEqual(second["occurrence"]["state"], "completed")
        self.assertEqual(self.item(loan["id"])["amounts"]["remaining_obligation_amount"], "0.00")
        self.assert_balance("1000.00", flow_count=3)
        self.delete_flow(first["flow"]["id"])
        partial_again = self.call("GET", "/task-occurrences?month=2026-09")["rows"][0]
        self.assertEqual(partial_again["state"], "partial")
        self.assertEqual(partial_again["actual_amount"], "70.00")
        self.delete_flow(second["flow"]["id"])
        pending = self.call("GET", "/task-occurrences?month=2026-09")["rows"][0]
        self.assertEqual(pending["state"], "pending")
        self.assertEqual(pending["actual_amount"], "0.00")
        self.assertEqual(pending["flow_count"], 0)
        unpaid = self.call("POST", "/task-occurrences/mark-unpaid", {
            "template_id": template["id"], "month": "2026-09", "expected_version": pending["version"],
        })
        self.assertTrue(unpaid["occurrence"]["marked_unpaid"])
        self.assertEqual(self.item(loan["id"])["amounts"]["remaining_obligation_amount"], "100.00")
        self.assert_balance("900.00", flow_count=1)
        self.delete_flow(source["id"])
        self.assert_balance("1000.00", flow_count=0)
        self.assert_empty_reports()

        # A real later repayment must survive explicit independent-source correction.
        retained_loan = self.loan_payload()
        retained_source = self.call("POST", "/flows", self.flow_payload(related_items=[retained_loan]), status=201)["flow"]
        later = self.call("POST", "/flows", self.repayment_payload(retained_loan["id"], "20.00"), status=201)["flow"]
        self.call("POST", f"/flows/{retained_source['id']}/delete", {"expected_version": retained_source["version"]}, status=409)
        self.assert_balance("920.00", flow_count=2)
        current = self.item(retained_loan["id"])["item"]
        self.delete_flow(retained_source["id"], source_corrections=[{
            "action": "keep_independent", "item_id": current["id"], "expected_version": current["version"],
        }])
        retained = self.item(current["id"])
        self.assertIsNone(retained["item"]["origin_flow_id"])
        self.assertEqual(retained["amounts"]["remaining_obligation_amount"], "80.00")
        self.assertEqual(self.flow(later["id"])["flow"]["amount"], "20.00")
        self.assert_balance("1020.00", flow_count=1)
        self.delete_flow(later["id"])
        item = self.item(current["id"])["item"]
        self.call("POST", f"/items/{item['id']}/remove", {"expected_version": item["version"]})
        self.assert_balance("1000.00", flow_count=0)
        self.assert_empty_reports()
        self.assertEqual(self.connection.fetch_one("SELECT (SELECT count(*) FROM app.bank_transactions) AS bank_count,(SELECT count(*) FROM audit.events) AS audit_count"), ordinary_before)

    def test_plural_filters_cross_the_real_http_boundary(self):
        other = self.call("POST", "/settings/accounts", {
            "id": self.uid(), "name": "Synthetic second HTTP account", "kind": "savings",
            "opening_date": "2026-01-01", "opening_amount": "0.00",
        }, status=201)["account"]
        self.call("POST", "/flows", self.flow_payload(), status=201)
        self.call("POST", "/flows", self.flow_payload(kind="receipt", amount="40.00", to_account_id=other["id"]), status=201)
        self.call("POST", "/flows", self.flow_payload(kind="transfer", amount="25.00", from_account_id=self.account["id"], to_account_id=other["id"], category_id=None), status=201)
        plural = urlencode({"account_ids": json.dumps([self.account["id"], other["id"]])})
        all_rows = self.call("GET", "/flows?" + self.period + "&" + plural)
        self.assertEqual(all_rows["pagination"]["total"], 3)
        self.assertEqual(all_rows["summary"]["filtered_totals"], {
            "flow_count": 3, "income_amount": "40.00", "expense_amount": "100.00", "transfer_amount": "25.00",
        })
        self.assertTrue(all(row["account_running_balance"] is None for row in all_rows["rows"]))
        nullable = urlencode({"category_ids": json.dumps([None, self.category["id"]]), "project_ids": "[null]"})
        first_page = self.call("GET", "/flows?" + self.period + "&" + plural + "&" + nullable + "&page_size=1")
        self.assertEqual(len(first_page["rows"]), 1)
        self.assertEqual(first_page["pagination"]["total"], 3)
        self.assertEqual(first_page["summary"]["filtered_totals"], all_rows["summary"]["filtered_totals"])
        for invalid in ("account_ids=[]", "account_ids=invalid", plural + "&account_id=" + self.account["id"], plural + "&" + plural):
            self.assertEqual(self.call("GET", "/flows?" + self.period + "&" + invalid, status=400)["error"], "cash_invalid_input")


    def test_personal_task_cash_noncash_and_undo_are_one_real_http_chain(self):
        ordinary_before = self.connection.fetch_one("SELECT (SELECT count(*) FROM app.bank_transactions) AS bank_count,(SELECT count(*) FROM audit.events) AS audit_count")
        configured = self.call("PUT", "/settings/personal-opening", {"expected_version": 1, "opening_date": "2026-01-01", "counterparty": "Synthetic owner"})
        self.assertEqual(configured["counterparty"], "Synthetic owner")
        self.assertEqual(self.call("GET", "/settings/personal-opening")["counterparty"], "Synthetic owner")
        opening = {**self.loan_payload(), "origin_date": "2026-01-01", "original_amount": "1000.00", "is_opening": True,
                   "ledger_group": "personal", "counterparty": "Synthetic owner"}
        self.call("POST", "/items", opening, status=201)
        task = self.call("POST", "/tasks", {"id": self.uid(), "title": "Synthetic card repayment", "kind": "payment",
            "execution_day": 5, "remind_days": 2, "effective_from_month": "2026-09", "default_amount": "2000.00",
            "default_account_id": self.account["id"], "default_category_id": self.category["id"]}, status=201)["template"]
        advance = {**self.loan_payload(), "original_amount": "2000.00", "ledger_group": "personal", "counterparty": "Synthetic owner"}
        confirm = {"template_id": task["id"], "month": "2026-09", "expected_version": None,
                   "expected_template_version": task["version"], "mode": "new_flow",
                   "new_flow": self.flow_payload(amount="2000.00", related_items=[advance])}
        paid = self.call("POST", "/task-occurrences/confirm", confirm)
        self.assertEqual(paid["flow"]["source_kind"], "monthly_task")
        self.assertEqual(paid["occurrence"]["actual_amount"], "2000.00")
        self.assertEqual(self.call("POST", "/task-occurrences/confirm", confirm)["flow"]["id"], paid["flow"]["id"])
        repaid = self.call("POST", "/flows", self.repayment_payload(opening["id"], "300.00"), status=201)
        ticket = self.call("POST", "/items", {"id": self.uid(), "type": "ticket_source", "origin_date": "2026-09-03",
            "original_amount": "500.00", "ticket_provider": "Synthetic owner", "ticket_provided_on": "2026-09-03",
            "ticket_description": "Synthetic categorized tickets", "category_id": self.payment_category["id"],
            "content": "Synthetic categorized tickets"}, status=201)["item"]
        target = self.item(opening["id"])["item"]
        offset = self.call("POST", "/settlements", {"id": self.uid(), "kind": "ticket_offset", "amount": "400.00", "occurred_on": "2026-09-03",
            "item_id": target["id"], "expected_item_version": target["version"], "source_item_id": ticket["id"],
            "expected_source_item_version": ticket["version"]}, status=201)["settlement"]
        self.assertIsNone(offset["category_id"])
        target = self.item(opening["id"])["item"]
        adjustment = self.call("POST", "/settlements", {"id": self.uid(), "kind": "non_ticket_offset", "amount": "100.00",
            "occurred_on": "2026-09-03", "item_id": target["id"], "expected_item_version": target["version"],
            "remark": "Explicit independent adjustment", "category_id": self.category["id"]}, status=201)["settlement"]
        self.assertEqual(self.item(opening["id"])["amounts"]["remaining_obligation_amount"], "200.00")
        personal = self.call("GET", "/reports/personal?year=2026")
        self.assertEqual(personal["summary"]["remaining_obligation_amount"], "2200.00")
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.flows")["n"], 2)
        self.assertEqual(self.connection.fetch_one("SELECT count(*) AS n FROM cash.items WHERE type='loan'")["n"], 2)
        # Remove the explicit adjustment, then a real receipt: all reports re-read the same facts.
        target = self.item(opening["id"])["item"]
        self.call("POST", f"/settlements/{adjustment['id']}/remove", {"expected_version": adjustment["version"],
            "expected_related_versions": {"items": [{"id": target["id"], "version": target["version"]}]}})
        self.delete_flow(repaid["flow"]["id"])
        self.assertEqual(self.call("GET", "/reports/personal?year=2026")["summary"]["remaining_obligation_amount"], "2600.00")
        self.delete_flow(paid["flow"]["id"])
        self.assertEqual(self.call("GET", "/task-occurrences?month=2026-09")["rows"][0]["actual_amount"], "0.00")
        self.assertEqual(self.call("GET", "/reports/personal?year=2026")["summary"]["remaining_obligation_amount"], "600.00")
        self.assertEqual(self.connection.fetch_one("SELECT (SELECT count(*) FROM app.bank_transactions) AS bank_count,(SELECT count(*) FROM audit.events) AS audit_count"), ordinary_before)


def browser_e2e() -> int:
    """Run the real browser against this existing disposable HTTP/PG fixture."""
    dsn = os.environ.get("FIN_OPS_CASH_TEST_DATABASE_URL", "")
    if not dsn:
        raise RuntimeError("--browser-e2e requires FIN_OPS_CASH_TEST_DATABASE_URL; no skipped success")
    database = assert_safe_test_database_url(dsn)
    if not database.startswith("fin_ops_cash_test_"):
        raise RuntimeError("Browser writes require an explicit fin_ops_cash_test_* database")
    apply_test_migrations(dsn)
    fixture = CashHttpPostgresTests()
    try:
        fixture.setUp()
        with socket.socket() as port:
            port.bind(("127.0.0.1", 0))
            frontend_port = port.getsockname()[1]
        with tempfile.TemporaryDirectory(prefix="finops-cash-browser-") as output:
            environment = {**os.environ,
                           "FIN_OPS_CASH_REAL_E2E": "1", "FIN_OPS_E2E_PORT": str(frontend_port),
                           "PLAYWRIGHT_BASE_URL": f"http://127.0.0.1:{frontend_port}",
                           "VITE_API_PROXY_TARGET": fixture.base_url, "FIN_OPS_E2E_SKIP_WEBSERVER": "0",
                           "FIN_OPS_CASH_REAL_TOKEN": DEFAULT_TEST_OA_TOKEN,
                           "FIN_OPS_CASH_REAL_ACCOUNT": json.dumps(fixture.account),
                           "FIN_OPS_CASH_REAL_CATEGORY": json.dumps(fixture.category)}
            process = subprocess.Popen(
                ["npm", "run", "e2e", "--", "e2e/cash-real-api-flow.spec.ts", "--project=chromium", "--output=" + output],
                cwd=Path(__file__).resolve().parents[1] / "web", env=environment, start_new_session=True,
            )
            try:
                return process.wait(timeout=300)
            finally:
                # Stop this runner's process group, including Vite/Chromium on timeout.
                try:
                    os.killpg(process.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    os.killpg(process.pid, signal.SIGKILL)
                    process.wait()
    finally:
        # Same TestCase cleanup stack: HTTP threads first, then runtime and PG.
        if not fixture.doCleanups():
            raise RuntimeError("Real browser fixture cleanup failed")


if __name__ == "__main__":
    if sys.argv[1:] == ["--browser-e2e"]:
        raise SystemExit(browser_e2e())
    unittest.main()
