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

from psycopg_pool import PoolTimeout

from fin_ops_platform.app.http_adapter import WsgiHttpAdapter
from fin_ops_platform.app.routes_cash import CashApiRoutes
from fin_ops_platform.app.server import Application, Response
from fin_ops_platform.services.cash_domain import CashError
from test_http_adapter import FakeApplication, invoke
from tests.app_test_support import build_local_state_application, configure_access_control
from fin_ops_platform.services.oa_identity_service import OAUserIdentity


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

    def test_strict_json_and_duplicate_query(self):
        for body in ('{"amount": NaN}', '{"id":"a","id":"b"}', '[]', ''):
            with self.subTest(body=body):
                self.assertEqual(self.call("POST", body=body).status_code, 400)
        self.assertEqual(self.call(query={"page": ["1", "2"]}).status_code, 400)
        self.service.create_flow.assert_not_called()

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

    def test_missing_cash_configuration_does_not_break_ordinary_session(self):
        with tempfile.TemporaryDirectory() as temporary, patch.dict(os.environ, {"FIN_OPS_CASH_POSTGRES_DATABASE_URL": ""}):
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
