from __future__ import annotations

import json
import os
import tempfile
import unittest
from datetime import timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch
from urllib.parse import urlencode
from uuid import uuid4

from fin_ops_platform.app.http_adapter import WsgiHttpAdapter
from fin_ops_platform.app.routes_cash import CashApiRoutes
from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.cash_domain import CashError
from fin_ops_platform.services.cash_queries import CashQueryService
from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from psycopg_pool import PoolTimeout
from test_http_adapter import FakeApplication, invoke

from tests.app_test_support import build_local_state_application, configure_access_control


def session(*, allowed=True, admin=False):
    return SimpleNamespace(
        can_admin_access=admin, allowed_page_keys=frozenset({"cash"} if allowed else set()),
        identity=SimpleNamespace(username="CASH_TEST", display_name="Test"), token="test-token",
    )


class CashApiTests(unittest.TestCase):
    def test_gunicorn_cash_request_atom_is_private_and_ordinary_is_unchanged(self):
        from fin_ops_platform.app.cash_access_logger import CashAccessLogger
        logger = CashAccessLogger.__new__(CashAccessLogger)
        response = SimpleNamespace(status="200 OK", headers=[], sent=2)
        for path, expected in (("/api/cash/flows/private-id", "/api/cash"),
                               ("/api/bank-details", "/api/bank-details?keyword=normal")):
            atoms = logger.atoms(response, [], {"REQUEST_METHOD": "GET", "PATH_INFO": path,
                "RAW_URI": path + "?keyword=normal", "QUERY_STRING": "keyword=normal",
                "SERVER_PROTOCOL": "HTTP/1.1"}, timedelta(milliseconds=1))
            self.assertEqual(atoms["r"], f"GET {expected} HTTP/1.1")
            if path.startswith("/api/cash"):
                self.assertEqual(atoms["q"], "")
                self.assertNotIn("private-id", atoms["r"])

    def setUp(self):
        self.service, self.queries, self.tasks, self.projects = (Mock() for _ in range(4))
        self.routes = CashApiRoutes(self.service, self.queries, self.tasks, self.projects,
                                   Application._json_response)

    def call(self, method="GET", path="/api/cash/flows", *, query=None, body=None, identity=None):
        return self.routes.route(method, path, query or {}, body,
                                 session=identity or session())

    def test_exact_money_dto_and_no_cache(self):
        self.queries.list_flows.return_value = {"rows": [{"amount": Decimal("1.20")}], "total": 1}
        response = self.call(query={"date_from": ["2026-01-01"], "date_to": ["2026-12-31"]})
        self.assertEqual(json.loads(response.body)["rows"][0]["amount"], "1.20")
        self.assertEqual(response.headers["Cache-Control"], "no-store")

    def test_no_authority_no_dependency_io(self):
        response = self.call(identity=session(allowed=False))
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "cash_access_denied")
        self.queries.list_flows.assert_not_called()

    def test_personal_opening_owner_is_explicit_in_read_and_write_dto(self):
        expected = {"opening_date": "2026-01-01", "counterparty": "Synthetic owner", "version": 2}
        self.service.get_personal_opening.return_value = expected
        response = self.call(path="/api/cash/settings/personal-opening")
        self.assertEqual(json.loads(response.body), expected)
        payload = {"expected_version": 1, "opening_date": "2026-01-01", "counterparty": "Synthetic owner"}
        self.service.update_personal_opening.return_value = {**expected, "changed": True}
        response = self.call("PUT", "/api/cash/settings/personal-opening", body=json.dumps(payload))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["counterparty"], "Synthetic owner")
        self.service.update_personal_opening.assert_called_once_with(payload)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        denied = self.call("PUT", "/api/cash/settings/personal-opening", body=json.dumps(payload), identity=session(allowed=False))
        self.assertEqual(denied.status_code, 403)
        self.service.update_personal_opening.assert_called_once()

    def test_unsettled_and_pending_collection_dtos_keep_exact_money_and_view(self):
        row = {"item_id": str(uuid4()), "origin_date": "2025-01-01", "remaining_amount": Decimal("800.00")}
        self.queries.query_turnover.return_value = {"view": "unsettled", "rows": [row],
            "summary": {"item_count": 1, "remaining_obligation_amount": {"receivable": Decimal("800.00"), "payable": Decimal("0.00")}},
            "pagination": {"page": 1, "page_size": 50, "total": 1}}
        response = self.call(path="/api/cash/reports/turnover", query={"view": ["unsettled"], "date_to": ["2026-09-07"]})
        self.assertEqual(response.status_code, 200)
        result = json.loads(response.body)
        self.assertEqual(result["view"], "unsettled")
        self.assertEqual(result["rows"][0]["remaining_amount"], "800.00")
        self.assertEqual(result["summary"]["remaining_obligation_amount"], {"receivable": "800.00", "payable": "0.00"})
        self.queries.query_turnover.assert_called_once_with({"view": "unsettled", "date_to": "2026-09-07"})
        self.queries.query_tickets.return_value = {"view": "pending_collection", "rows": [{"remaining_receivable_amount": Decimal("150.00"),
            "noncash_settled_amount": Decimal("50.00"), "collection_state": "partial"}], "summary": {}, "pagination": {"total": 1}}
        tickets = self.call(path="/api/cash/reports/ticket-payments", query={"view": ["pending_collection"], "date_to": ["2026-09-07"]})
        self.assertEqual(tickets.status_code, 200)
        self.assertEqual(json.loads(tickets.body)["rows"], [{"remaining_receivable_amount": "150.00", "noncash_settled_amount": "50.00", "collection_state": "partial"}])
        self.assertEqual(tickets.headers["Cache-Control"], "no-store")

    def test_new_view_incompatible_filters_fail_before_repository_io(self):
        repository = Mock()
        self.routes.queries = CashQueryService(repository)
        for report, view, invalid in (("turnover", "unsettled", "date_from"),
                                       ("turnover", "unsettled", "category_id"),
                                       ("turnover", "unsettled", "personal_variant"),
                                       ("ticket-payments", "pending_collection", "date_from"),
                                       ("ticket-payments", "pending_collection", "state")):
            value = {"date_from": "2026-01-01", "category_id": "null", "personal_variant": "principal", "state": "unused"}[invalid]
            with self.subTest(report=report, invalid=invalid):
                response = self.call(path="/api/cash/reports/" + report,
                    query={"view": [view], "date_to": ["2026-09-07"], invalid: [value]})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.body)["error"], "cash_invalid_input")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        repository.query_turnover.assert_not_called()
        repository.query_tickets.assert_not_called()

    def test_turnover_preserves_ui_projections_and_nullable_money(self):
        row = {"row_id": "settlement:synthetic", "row_kind": "settlement", "category": {"id": "synthetic", "name": "Income", "group": "receipt"},
               "remark": None, "ticket_collection_state": "partial", "original_amount": None,
               "reimbursement_received_amount": Decimal("30.00"), "remaining_after_event": Decimal("70.00")}
        result = {"rows": [row], "summary": {"event_count": 1}, "pagination": {"page": 1, "page_size": 50, "total": 1}}
        self.queries.query_turnover.return_value = result
        query = {"date_from": ["2026-09-01"], "date_to": ["2026-09-30"]}
        response = self.call(path="/api/cash/reports/turnover", query=query)
        self.assertEqual(response.status_code, 200)
        body = json.loads(response.body)
        self.assertEqual(body["rows"], [{**row, "reimbursement_received_amount": "30.00", "remaining_after_event": "70.00"}])
        self.assertEqual(body["pagination"], result["pagination"])
        self.assertEqual(body["summary"], result["summary"])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.queries.query_turnover.assert_called_once_with({"date_from": "2026-09-01", "date_to": "2026-09-30"})

    def test_turnover_personal_variant_rejects_incompatible_context_before_io(self):
        repository = Mock()
        self.routes.queries = CashQueryService(repository)
        period = {"date_from": ["2026-09-01"], "date_to": ["2026-09-30"]}
        for extra in ({"personal_variant": ["principal"]},
                      {"personal_variant": ["principal"], "ledger_group": ["company"]},
                      {"personal_variant": ["orange"], "ledger_group": ["personal"]},
                      {"personal_variant": ["principal", "settlement"], "ledger_group": ["personal"]}):
            with self.subTest(extra=extra):
                response = self.call(path="/api/cash/reports/turnover", query={**period, **extra})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.body)["error"], "cash_invalid_input")
        repository.query_turnover.assert_not_called()
        repository.query_turnover.return_value = {"rows": [], "summary": {}, "pagination": {"page": 1, "page_size": 50, "total": 0}}
        response = self.call(path="/api/cash/reports/turnover", query={**period, "ledger_group": ["personal"], "personal_variant": ["settlement"]})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(repository.query_turnover.call_args.args[0]["personal_variant"], "settlement")

    def test_strict_json_and_duplicate_query(self):
        for body in ('{"amount": NaN}', '{"id":"a","id":"b"}', '[]', ''):
            with self.subTest(body=body):
                self.assertEqual(self.call("POST", body=body).status_code, 400)
        self.assertEqual(self.call(query={"page": ["1", "2"]}).status_code, 400)
        self.service.create_flow.assert_not_called()

    def test_multi_query_arrays_normalize_without_changing_scalar_contract(self):
        repository = Mock()
        repository.list_flows.return_value = {"rows": []}
        self.routes.queries = CashQueryService(repository)
        identity = str(uuid4())
        period = {"date_from": ["2026-09-01"], "date_to": ["2026-09-30"]}
        response = self.call(query={**period, "account_ids": [json.dumps([identity])],
            "project_ids": ['[null,"historical"]'], "category_ids": ['[null]'],
            "kinds": ['["receipt","payment"]'], "sources": ['["manual"]']})
        self.assertEqual(response.status_code, 200)
        normalized = repository.list_flows.call_args.args[0]
        self.assertEqual(normalized["account_id"], [identity])
        self.assertEqual(normalized["project_id"], [None, "historical"])
        self.assertEqual(normalized["category_id"], [None])
        self.assertEqual(normalized["kind"], ["receipt", "payment"])
        self.assertEqual(normalized["source"], ["manual"])
        self.assertNotIn("project_ids", normalized)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertEqual(self.call(query={**period, "account_id": [identity]}).status_code, 200)
        self.assertEqual(repository.list_flows.call_args.args[0]["account_id"], identity)

    def test_invalid_multi_values_and_mixed_parameters_fail_before_repository(self):
        repository = Mock()
        self.routes.queries = CashQueryService(repository)
        period = {"date_from": ["2026-09-01"], "date_to": ["2026-09-30"]}
        invalid_values = ["[]", "{}", "null", '"text"', "[true]", "[12]", "[NaN]",
                          "[Infinity]", "[[]]", "[{}]", '[""]', '[" "]', '["a","a"]',
                          '[null,null]', '["a",]', json.dumps(["x" * 201]),
                          json.dumps(["\x00"]), json.dumps(["\ud800"]),
                          json.dumps([str(n) for n in range(51)])]
        for value in invalid_values:
            with self.subTest(value=value):
                response = self.call(query={**period, "project_ids": [value]})
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.body)["error"], "cash_invalid_input")
                self.assertEqual(response.headers["Cache-Control"], "no-store")
        for query in ({"project_id": ["a"], "project_ids": ['["b"]']},
                      {"project_ids": ['["a"]', '["b"]']}, {"account_ids": ['[null]']},
                      {"account_ids": ['["bad-uuid"]']}, {"kinds": ['["check"]']},
                      {"sources": ['["oa"]']}, {"groups": ['["payment"]']}):
            with self.subTest(query=query):
                self.assertEqual(self.call(query={**period, **query}).status_code, 400)
        repository.list_flows.assert_not_called()

    def test_multi_total_limit_and_encoded_query_length_are_explicit(self):
        repository = Mock()
        repository.list_flows.return_value = {"rows": []}
        self.routes.queries = CashQueryService(repository)
        maximum = {"date_from": "2026-09-01", "date_to": "2026-09-30",
            "account_ids": json.dumps([str(uuid4()) for _ in range(50)]),
            "category_ids": json.dumps([str(uuid4()) for _ in range(50)])}
        self.routes.queries.list_flows(maximum)
        normalized = repository.list_flows.call_args.args[0]
        self.assertEqual(len(normalized["account_id"]) + len(normalized["category_id"]), 100)
        repository.reset_mock()
        with self.assertRaises(CashError):
            self.routes.queries.list_flows({**maximum, "kinds": '["payment"]'})
        # URL length is checked before service/dependency I/O, including encoded Unicode.
        response = self.call(query={"project_ids": [json.dumps(["项" * 150] * 5, ensure_ascii=False)]})
        self.assertEqual(response.status_code, 400)
        self.assertIn("过长", json.loads(response.body)["message"])
        repository.list_flows.assert_not_called()

    def test_query_3500_bytes_is_valid_and_3501_is_json_no_store_before_io(self):
        repository = Mock()
        repository.list_flows.return_value = {"rows": [], "pagination": {"page": 1, "page_size": 50, "total": 0}}
        self.routes.queries = CashQueryService(repository)
        query = {"date_from": ["2026-09-01"], "date_to": ["2026-09-30"],
            "project_ids": [json.dumps(["p" * 190 + str(index) for index in range(17)], separators=(",", ":"))],
            "keyword": [""]}
        query["keyword"] = ["x" * (3500 - len(urlencode(query, doseq=True)))]
        self.assertLessEqual(len(query["keyword"][0]), 200)
        self.assertEqual(len(urlencode(query, doseq=True)), 3500)
        response = self.call(query=query)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(json.loads(response.body)["rows"], [])
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        repository.list_flows.assert_called_once()
        repository.reset_mock()

        query["keyword"][0] += "x"
        self.assertEqual(len(urlencode(query, doseq=True)), 3501)
        response = self.call(query=query)
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.headers["Cache-Control"], "no-store")
        self.assertIn("application/json", response.headers["Content-Type"])
        self.assertEqual(json.loads(response.body), {
            "error": "cash_invalid_input", "message": "查询条件过长，请减少选择项。",
        })
        repository.list_flows.assert_not_called()

    def test_multi_endpoint_whitelists_and_enum_sets(self):
        repository = Mock()
        queries = CashQueryService(repository)
        period = {"date_from": "2026-09-01", "date_to": "2026-09-30"}
        for method, raw, target in (
            (queries.query_turnover, {**period, "states": '["open","settled"]', "category_ids": '[null]'}, repository.query_turnover),
            (queries.query_tickets, {**period, "states": '["unused","partial"]', "project_ids": '[null]'}, repository.query_tickets),
            (queries.query_personal, {"year": "2026", "bill_label_ids": '[null]'}, repository.query_personal),
            (lambda raw: queries.list_configuration("categories", raw), {"groups": '["payment","turnover"]'}, repository.list_configuration),
        ):
            target.return_value = {"rows": []}
            method(raw)
            self.assertTrue(any(isinstance(value, list) for value in target.call_args.args[-1].values()))
        for method, raw in ((queries.query_turnover, {**period, "states": '["used"]'}),
                            (queries.query_tickets, {**period, "states": '["settled"]'}),
                            (queries.query_personal, {"year": "2026", "category_ids": '[null]'}),
                            (queries.list_items, {"account_ids": '[null]'})):
            with self.subTest(raw=raw), self.assertRaises(CashError):
                method(raw)

    def test_create_retry_status_and_trusted_actor(self):
        for created, status in ((True, 201), (False, 200)):
            self.service.create_flow.return_value = {"created": created, "flow": {"id": "test"}, "version": 1}
            response = self.call("POST", body='{"flow":{}}')
            self.assertEqual(response.status_code, status)
            self.assertNotIn("created", json.loads(response.body))
            self.service.create_flow.assert_called_with({"flow": {}}, {"account": "CASH_TEST", "name": "Test"})

    def test_known_conflict_and_storage_failure_are_safe(self):
        self.service.create_flow.side_effect = CashError("cash_version_conflict", "请刷新。", 409)
        response = self.call("POST", body='{}')
        self.assertEqual(response.status_code, 409)
        self.service.create_flow.side_effect = PoolTimeout("sensitive SQL secret")
        response = self.call("POST", body='{}')
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("secret", response.body)

    def test_cash_logs_do_not_include_ids_queries_or_exception_body(self):
        application = FakeApplication(error=RuntimeError("private-amount-and-person"))
        with self.assertLogs("fin_ops_platform.http", level="INFO") as captured:
            status, headers, body = invoke(WsgiHttpAdapter(application),
                path="/fin-ops-api/api/cash/flows/private-id?keyword=private-person")
        self.assertEqual(status, "500 Internal Server Error")
        self.assertEqual(headers["Cache-Control"], "no-store")
        logs = "\n".join(captured.output)
        for text in ("private-id", "private-person", "private-amount-and-person", "Traceback"):
            self.assertNotIn(text, logs)
            self.assertNotIn(text, body.decode())
        self.assertIn('"path": "/api/cash"', logs)

    def test_body_limit_errors_are_also_no_store(self):
        from fin_ops_platform.app.http_adapter import HttpRequestLimits
        status, headers, _ = invoke(WsgiHttpAdapter(FakeApplication(), limits=HttpRequestLimits(json_bytes=1)),
                                   method="POST", path="/api/cash/flows", body=b"{}")
        self.assertTrue(status.startswith("413"))
        self.assertEqual(headers["Cache-Control"], "no-store")


class CashGlobalIsolationTests(unittest.TestCase):
    def test_real_dispatch_authorizes_before_cash_initialization_and_skips_both_audits(self):
        with tempfile.TemporaryDirectory() as temporary:
            app = build_local_state_application(data_dir=Path(temporary), install_test_session=False)
            configure_access_control(app, page_access={"CASH_TEST": ["cash"], "ORDINARY_TEST": ["bank-details"]})
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(token, token, "", "Test")
            app._audit_service = Mock(is_durable=True)
            with patch.object(app, "_handle_cash_request", return_value=Response(201, '{}')) as dispatch:
                denied = app.handle_request("POST", "/api/cash/flows", body='{}',
                    headers={"Authorization": "Bearer ORDINARY_TEST"})
                self.assertEqual(denied.status_code, 403)
                dispatch.assert_not_called()
                allowed = app.handle_request("POST", "/api/cash/flows", body='{}',
                    headers={"Authorization": "Bearer CASH_TEST"})
                self.assertEqual(allowed.status_code, 201)
                dispatch.assert_called_once()
            app._audit_service.record_action.assert_not_called()
            self.assertIsNone(app._cash_runtime)
            app.close()

    def test_missing_postgres_configuration_does_not_break_existing_local_session(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"FIN_OPS_POSTGRES_DATABASE_URL": "", "DATABASE_URL": ""}):
            app = build_local_state_application(data_dir=Path(temporary), install_test_session=False)
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity("005", "YNSYLP005", "", "Test")
            headers = {"Authorization": "Bearer admin"}
            self.assertEqual(app.handle_request("GET", "/api/session/me", headers=headers).status_code, 200)
            cash = app.handle_request("GET", "/api/cash/settings/project-selection", headers=headers)
            self.assertEqual(cash.status_code, 503)
            self.assertEqual(json.loads(cash.body)["error"], "cash_dependency_unavailable")
            self.assertEqual(app.handle_request("GET", "/api/session/me", headers=headers).status_code, 200)
            app.close()

    def test_cash_success_failure_and_denied_never_write_global_audit_or_page_metrics(self):
        for status in (200, 400, 403, 409, 503):
            app = Application.__new__(Application)
            app._audit_service = Mock(is_durable=True)
            app._api_performance_recorder = Mock()
            app._handle_request_untracked = Mock(return_value=Response(status, '{}'))
            response = app.handle_request("POST", "/api/cash/flows", body='{}')
            self.assertEqual(response.headers["Cache-Control"], "no-store")
            app._audit_service.record_action.assert_not_called()
            app._api_performance_recorder.record_request.assert_not_called()

    def test_ordinary_page_metrics_still_record(self):
        app = Application.__new__(Application)
        app._audit_service = Mock(is_durable=True)
        app._api_performance_recorder = Mock()
        app._handle_request_untracked = Mock(return_value=Response(200, '{}'))
        app.handle_request("GET", "/api/bank-details")
        app._api_performance_recorder.record_request.assert_called_once()


if __name__ == "__main__":
    unittest.main()
