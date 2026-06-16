import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity


class AuthGuardTests(unittest.TestCase):
    @contextmanager
    def _without_default_test_auth(self):
        previous = os.environ.get("FIN_OPS_TEST_DEFAULT_AUTH")
        os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = "0"
        try:
            yield
        finally:
            if previous is None:
                os.environ.pop("FIN_OPS_TEST_DEFAULT_AUTH", None)
            else:
                os.environ["FIN_OPS_TEST_DEFAULT_AUTH"] = previous

    def test_protected_api_returns_unauthorized_without_oa_token(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            response = app.handle_request("GET", "/api/workbench?month=2026-03")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")

    def test_protected_api_returns_forbidden_for_authenticated_but_unauthorized_user(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="101",
                username="outsider",
                nickname="外部用户",
                display_name="外部用户",
                dept_id="99",
                dept_name="其他部门",
                roles=["guest"],
                permissions=["system:user:list"],
            )

            response = app.handle_request(
                "GET",
                "/api/search?q=%E5%88%98&scope=all&month=all&limit=10",
                headers={"Authorization": "Bearer no-access"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "forbidden")

    def test_import_endpoints_are_also_protected(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def raise_expired(_: str) -> OAUserIdentity:
                raise OASessionExpiredError("登录状态已过期")

            app._oa_identity_service.resolve_identity = raise_expired

            response = app.handle_request(
                "GET",
                "/imports/templates",
                headers={"Authorization": "Bearer expired-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")

    def test_readonly_export_user_can_export_but_cannot_mutate_or_admin(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="401",
                username="READONLY001",
                nickname="只读导出用户",
                display_name="只读导出用户",
                roles=["finance"],
                permissions=[],
            )
            headers = {"Authorization": "Bearer readonly-user"}
            readable_routes = [
                ("GET", "/api/cost-statistics/export-preview?month=all&view=time", None),
                ("GET", "/api/cost-statistics/export?month=all&view=time", None),
                ("GET", "/api/turnover-ledger/export-preview?family=company", None),
                ("GET", "/api/turnover-ledger/export?family=company", None),
                ("GET", "/api/pending-invoices/export-preview?direction=expense", None),
                ("GET", "/api/pending-invoices/export?direction=expense", None),
            ]
            forbidden_routes = [
                ("PUT", "/api/pending-invoices/rules", {}),
                ("PUT", "/api/input-invoice-usage/payment-status-rules", {}),
                ("PUT", "/api/turnover-ledger/tag-selection", {}),
                ("POST", "/api/bank-details/auto-tag-rules/reapply", {}),
                ("POST", "/api/workbench/settings/data-reset", {"scope": "all"}),
            ]

            readable_responses = []
            for method, route, body in readable_routes:
                with self.subTest(route=route):
                    response = app.handle_request(
                        method,
                        route,
                        headers=headers,
                        body=json.dumps(body) if body is not None else None,
                    )
                    readable_responses.append((route, response))
                    self.assertNotIn(response.status_code, {401, 403})
                    if response.headers.get("Content-Type", "").startswith("application/json"):
                        payload = json.loads(response.body)
                        self.assertNotIn(payload.get("error"), {"invalid_oa_session", "forbidden", "admin_only"})

            for method, route, body in forbidden_routes:
                with self.subTest(route=route):
                    response = app.handle_request(
                        method,
                        route,
                        headers=headers,
                        body=json.dumps(body),
                    )
                    payload = json.loads(response.body)
                    self.assertEqual(response.status_code, 403)
                    self.assertIn(payload["error"], {"permission_denied", "admin_only"})

        download_content_types = {
            route: response.headers.get("Content-Type")
            for route, response in readable_responses
            if route.endswith("/export?month=all&view=time") or route.endswith("/export?family=company")
        }
        self.assertEqual(
            download_content_types["/api/cost-statistics/export?month=all&view=time"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        self.assertEqual(
            download_content_types["/api/turnover-ledger/export?family=company"],
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )


if __name__ == "__main__":
    unittest.main()
