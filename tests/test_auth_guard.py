import inspect
import json
import tempfile
import unittest
from pathlib import Path

import fin_ops_platform.app.auth as auth_module
from fin_ops_platform.app.server import Application
from fin_ops_platform.services.access_control_service import AccessControlService
from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity
from tests.app_test_support import build_local_state_application as build_application
from tests.app_test_support import configure_access_control


class AuthGuardTests(unittest.TestCase):
    @staticmethod
    def _identity(username: str) -> OAUserIdentity:
        return OAUserIdentity(f"id-{username}", username, username, username, roles=["finance"], permissions=["finops:app:view"])

    def test_runtime_auth_and_reset_have_no_synthetic_identity_or_default_secret(self) -> None:
        auth_source = inspect.getsource(auth_module)
        reset_source = inspect.getsource(Application._verify_reset_oa_password)
        for retired_marker in (
            "synthetic_identity",
            "local-dev-token",
            "test-default-token",
            "FIN_OPS_TEST_DEFAULT_AUTH",
            "FIN_OPS_DEV_ALLOW_LOCAL_SESSION",
            "FIN_OPS_DEV_USERNAME",
            "FIN_OPS_DEV_OA_PASSWORD",
        ):
            self.assertNotIn(retired_marker, auth_source)
        self.assertNotIn("local-dev-password", reset_source)

    def test_access_control_uses_one_snapshot_and_never_creates_second_admin(self) -> None:
        reads = 0

        def snapshot_provider() -> dict[str, object]:
            nonlocal reads
            reads += 1
            return {
                "page_access_accounts": [{"username": "ATTACKER", "page_keys": ["bank-details"]}],
                "access_control_version": 1,
            }

        decision = AccessControlService(access_control_snapshot_provider=snapshot_provider).evaluate(self._identity("ATTACKER"))
        self.assertEqual(reads, 1)
        self.assertTrue(decision.can_access_page("bank-details"))
        self.assertFalse(decision.can_access_page("settings"))
        self.assertFalse(decision.can_admin_access)

    def test_protected_admin_skips_snapshot_and_provider_failure_denies_others(self) -> None:
        def failing_provider() -> dict[str, object]:
            raise RuntimeError("provider secret must not be logged")

        service = AccessControlService(access_control_snapshot_provider=failing_provider)
        admin = service.evaluate(self._identity("YNSYLP005"))
        with self.assertLogs("fin_ops_platform.services.access_control_service", level="WARNING") as logs:
            denied = service.evaluate(self._identity("OUTSIDER001"))

        self.assertTrue(admin.can_admin_access)
        self.assertTrue(admin.can_access_page("operation-history"))
        self.assertFalse(denied.can_access_app)
        self.assertNotIn("provider secret", "\n".join(logs.output))

    def test_local_fixture_admits_default_identity_without_persisting_acl(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            default = app._access_control_service.evaluate(self._identity("test_finops_user"))
            outsider = app._access_control_service.evaluate(self._identity("OUTSIDER001"))
            persisted = app._app_settings_service.get_access_control_payload()

        self.assertTrue(default.can_access_app)
        self.assertFalse(outsider.can_access_app)
        self.assertEqual(persisted["accounts"], [])

    def test_missing_or_expired_oa_token_is_unauthorized(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            missing = app.handle_request("GET", "/api/workbench?month=2026-03")

            def raise_expired(_: str) -> OAUserIdentity:
                raise OASessionExpiredError("登录状态已过期")

            app._oa_identity_service.resolve_identity = raise_expired
            expired = app.handle_request("GET", "/imports/templates", headers={"Authorization": "Bearer expired"})

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(expired.status_code, 401)

    def test_oa_roles_and_permission_markers_cannot_grant_app_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("YNSYLP006")
            response = app.handle_request(
                "GET",
                "/api/workbench?month=2026-07",
                headers={"Authorization": "Bearer no-access"},
            )
        self.assertEqual(response.status_code, 403)

    def test_page_permission_applies_equally_to_reads_and_writes(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, page_access={"USER001": ["pending-invoices"]})
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            headers = {"Authorization": "Bearer user"}
            write = app.handle_request("PUT", "/api/pending-invoices/rules", headers=headers, body="{}")
            denied = app.handle_request("GET", "/api/bank-details", headers=headers)

        self.assertNotEqual(write.status_code, 403)
        self.assertEqual(denied.status_code, 403)
        self.assertEqual(json.loads(denied.body)["error"], "page_access_denied")

    def test_unknown_protected_route_fails_closed_for_every_account(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, usernames=["USER001"])
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            response = app.handle_request(
                "POST",
                "/api/future-write-route",
                headers={"Authorization": "Bearer user"},
                body="{}",
            )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(json.loads(response.body)["error"], "page_access_policy_missing")

    def test_etc_reconciliation_actor_comes_from_authenticated_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir), install_test_session=False)
            configure_access_control(app, page_access={"USER001": ["etc-tickets"]})
            app._oa_identity_service.resolve_identity = lambda _token: self._identity("USER001")
            response = app.handle_request(
                "POST",
                "/api/etc/reconciliation-tasks",
                headers={"Authorization": "Bearer user"},
                body=json.dumps({"title": "actor test", "createdBy": "spoofed-user"}),
            )
            task_id = json.loads(response.body)["taskId"]
            task = app._etc_reconciliation_task_service.get_task(task_id)

        self.assertEqual(response.status_code, 201)
        self.assertEqual(task.created_by, "USER001")


if __name__ == "__main__":
    unittest.main()
