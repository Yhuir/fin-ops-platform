import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity
from tests.app_test_support import build_local_state_application as build_application
from tests.app_test_support import configure_access_control


class SessionApiTests(unittest.TestCase):
    @contextmanager
    def _temporary_env(self, **updates: str | None):
        previous = {key: os.environ.get(key) for key in updates}
        try:
            for key, value in updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            yield
        finally:
            for key, value in previous.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

    @staticmethod
    def _identity(username: str) -> OAUserIdentity:
        return OAUserIdentity(
            user_id=f"id-{username}",
            username=username,
            nickname=f"{username} 姓名",
            display_name=f"{username} 姓名",
            dept_id="88",
            dept_name="财务部",
            roles=["finance"],
            permissions=["finops:app:view"],
        )

    def test_session_returns_page_permissions_and_identity(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(
                app,
                page_access={"USER001": ["bank-details", "pending-invoices"]},
            )
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer user-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["username"], "USER001")
        self.assertEqual(payload["user"]["display_name"], "USER001 姓名")
        self.assertTrue(payload["can_access_app"])
        self.assertFalse(payload["can_admin_access"])
        self.assertEqual(payload["allowed_page_keys"], ["bank-details", "pending-invoices"])
        self.assertNotIn("access_tier", payload)
        self.assertNotIn("can_mutate_data", payload)

    def test_fixed_005_administrator_has_all_pages_without_acl_row(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("YNSYLP005")
            payload = json.loads(
                app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": "Bearer admin-token"},
                ).body
            )

        self.assertTrue(payload["allowed"])
        self.assertTrue(payload["can_admin_access"])
        self.assertIn("settings", payload["allowed_page_keys"])
        self.assertIn("operation-history", payload["allowed_page_keys"])

    def test_unconfigured_user_is_visible_but_denied(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("OUTSIDER001")
            payload = json.loads(
                app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": "Bearer outsider"},
                ).body
            )

        self.assertFalse(payload["allowed"])
        self.assertFalse(payload["can_access_app"])
        self.assertFalse(payload["can_admin_access"])
        self.assertEqual(payload["allowed_page_keys"], [])

    def test_page_grant_allows_same_page_writes_and_denies_other_pages(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, page_access={"USER001": ["pending-invoices"]})
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            headers = {"Authorization": "Bearer user-token"}

            same_page = app.handle_request(
                "PUT",
                "/api/pending-invoices/rules",
                headers=headers,
                body=json.dumps({}),
            )
            other_page = app.handle_request("GET", "/api/bank-details", headers=headers)

        self.assertNotEqual(same_page.status_code, 403)
        self.assertEqual(other_page.status_code, 403)
        self.assertEqual(json.loads(other_page.body)["error"], "page_access_denied")

    def test_only_005_can_open_access_account_control_plane(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, page_access={"USER001": ["settings"]})
            identities = {
                "user": self._identity("USER001"),
                "admin": self._identity("YNSYLP005"),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[token]

            user_response = app.handle_request(
                "GET",
                "/api/workbench/settings/access-control",
                headers={"Authorization": "Bearer user"},
            )
            admin_response = app.handle_request(
                "GET",
                "/api/workbench/settings/access-control",
                headers={"Authorization": "Bearer admin"},
            )

        self.assertEqual(user_response.status_code, 403)
        self.assertEqual(json.loads(user_response.body)["error"], "admin_access_required")
        self.assertEqual(admin_response.status_code, 200)

    def test_each_request_reads_access_control_snapshot_once(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, page_access={"USER001": ["bank-details"]})
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            provider = app._access_control_service.access_control_snapshot_provider
            reads = 0

            def counted_provider():
                nonlocal reads
                reads += 1
                return provider()

            app._access_control_service.access_control_snapshot_provider = counted_provider
            response = app.handle_request(
                "GET",
                "/api/bank-details",
                headers={"Authorization": "Bearer user-token"},
            )

        self.assertNotEqual(response.status_code, 403)
        self.assertEqual(reads, 1)

    def test_provider_failure_fails_closed_without_disclosing_error(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._access_control_service.access_control_snapshot_provider = lambda: (_ for _ in ()).throw(
                RuntimeError("secret provider detail")
            )
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer user-token"},
            )
            payload = json.loads(response.body)

        self.assertFalse(payload["allowed"])
        self.assertNotIn("secret provider detail", response.body)

    def test_expired_oa_session_is_unauthorized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def raise_expired(_: str) -> OAUserIdentity:
                raise OASessionExpiredError("登录状态已过期")

            app._oa_identity_service.resolve_identity = raise_expired
            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer expired"},
            )

        self.assertEqual(response.status_code, 401)

    def test_retired_environment_variables_cannot_grant_access(self) -> None:
        with self._temporary_env(
            FIN_OPS_ALLOWED_USERNAMES="ENV001",
            FIN_OPS_ALLOWED_ROLES="finance",
            FIN_OPS_READONLY_EXPORT_USERNAMES="ENV001",
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("ENV001")
            payload = json.loads(
                app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": "Bearer env-user"},
                ).body
            )

        self.assertFalse(payload["allowed"])


if __name__ == "__main__":
    unittest.main()
