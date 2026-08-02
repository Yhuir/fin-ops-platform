import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from tests.app_test_support import (
    build_local_state_application as build_application,
    configure_access_control,
    configure_default_test_access,
)
from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity


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

    def test_get_session_me_returns_current_user_roles_permissions_and_allowed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["liuji"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="101",
                username="liuji",
                nickname="刘际涛",
                display_name="刘际涛",
                dept_id="88",
                dept_name="财务部",
                roles=["finance"],
                permissions=["finops:app:view", "system:user:list"],
            )

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer mock-oa-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["user_id"], "101")
        self.assertEqual(payload["user"]["username"], "liuji")
        self.assertEqual(payload["user"]["display_name"], "刘际涛")
        self.assertEqual(payload["user"]["dept_name"], "财务部")
        self.assertEqual(payload["roles"], ["finance"])
        self.assertIn("finops:app:view", payload["permissions"])
        self.assertEqual(payload["access_tier"], "full_access")
        self.assertTrue(payload["can_access_app"])
        self.assertTrue(payload["can_mutate_data"])
        self.assertFalse(payload["can_admin_access"])

    def test_default_test_identity_requires_explicit_canonical_acl_seed(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_default_test_access(app)

            payload = json.loads(app.handle_request("GET", "/api/session/me").body)

        self.assertEqual(payload["user"]["username"], "test_finops_user")
        self.assertEqual(payload["access_tier"], "full_access")

    def test_get_session_me_fails_closed_when_dynamic_settings_provider_is_unavailable(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._access_control_service.access_control_snapshot_provider = lambda: (_ for _ in ()).throw(
                RuntimeError("settings store unavailable")
            )
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="101",
                username="liuji",
                nickname="刘际涛",
                display_name="刘际涛",
                dept_id="88",
                dept_name="财务部",
                roles=["finance"],
                permissions=["finops:app:view"],
            )

            with self.assertLogs("fin_ops_platform.services.access_control_service", level="WARNING") as logs:
                response = app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": "Bearer mock-oa-token"},
                )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["access_tier"], "denied")
        self.assertFalse(payload["can_access_app"])
        self.assertTrue(any("snapshot provider failed" in message for message in logs.output))

    def test_get_session_me_accepts_admin_token_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["cookie-user"])
            observed_tokens: list[str] = []

            def resolve_identity(token: str) -> OAUserIdentity:
                observed_tokens.append(token)
                return OAUserIdentity(
                    user_id="102",
                    username="cookie-user",
                    nickname="Cookie 用户",
                    display_name="Cookie 用户",
                    roles=["finance"],
                    permissions=["finops:app:view"],
                )

            app._oa_identity_service.resolve_identity = resolve_identity

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Cookie": "Admin-Token=cookie-session-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(observed_tokens, ["cookie-session-token"])
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["username"], "cookie-user")

    def test_get_session_me_allows_local_dev_session_without_oa_token_when_enabled(self) -> None:
        with self._temporary_env(
            FIN_OPS_DEV_ALLOW_LOCAL_SESSION="1",
            FIN_OPS_DEV_USERNAME="local_finops_admin",
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["local_finops_admin"])

            response = app.handle_request("GET", "/api/session/me")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["username"], "local_finops_admin")
        self.assertEqual(payload["access_tier"], "full_access")
        self.assertFalse(payload["can_admin_access"])

    def test_get_session_me_allows_username_from_workbench_settings_even_without_permission_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="201",
                username="YNSYLP005",
                nickname="溯源用户",
                display_name="溯源用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer allowed-by-settings"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["username"], "YNSYLP005")
        self.assertEqual(payload["access_tier"], "admin")
        self.assertTrue(payload["can_admin_access"])
        self.assertTrue(payload["can_mutate_data"])

    def test_get_session_me_marks_readonly_export_user_as_non_mutating(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, read_export_only=["READONLY001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="202",
                username="READONLY001",
                nickname="只读用户",
                display_name="只读用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer readonly-user"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["access_tier"], "read_export_only")
        self.assertTrue(payload["can_access_app"])
        self.assertFalse(payload["can_mutate_data"])
        self.assertFalse(payload["can_admin_access"])

    def test_get_session_me_marks_non_admin_allowed_user_as_full_access(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["FULL001"])
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="203",
                username="FULL001",
                nickname="全操作用户",
                display_name="全操作用户",
                roles=["finance"],
                permissions=[],
            )

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer full-access-user"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["access_tier"], "full_access")
        self.assertTrue(payload["can_access_app"])
        self.assertTrue(payload["can_mutate_data"])
        self.assertFalse(payload["can_admin_access"])

    def test_get_session_me_projects_access_tier_matrix_from_settings(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(
                app,
                full_access=["FULL001"],
                read_export_only=["READONLY001"],
            )
            identities = {
                "readonly": OAUserIdentity(
                    user_id="301",
                    username="READONLY001",
                    nickname="只读导出用户",
                    display_name="只读导出用户",
                    roles=["finance"],
                    permissions=[],
                ),
                "full": OAUserIdentity(
                    user_id="302",
                    username="FULL001",
                    nickname="业务用户",
                    display_name="业务用户",
                    roles=["finance"],
                    permissions=[],
                ),
                "admin": OAUserIdentity(
                    user_id="303",
                    username="ADMIN001",
                    nickname="管理员",
                    display_name="管理员",
                    roles=["finance"],
                    permissions=[],
                ),
                "default-admin": OAUserIdentity(
                    user_id="304",
                    username="YNSYLP005",
                    nickname="默认管理员",
                    display_name="默认管理员",
                    roles=["finance"],
                    permissions=[],
                ),
                "006": OAUserIdentity(
                    user_id="305",
                    username="YNSYLP006",
                    nickname="权限码用户",
                    display_name="权限码用户",
                    roles=["finance", "finops_full_access"],
                    permissions=["finops:app:view"],
                ),
                "outsider": OAUserIdentity(
                    user_id="306",
                    username="OUTSIDER001",
                    nickname="未授权用户",
                    display_name="未授权用户",
                    roles=["guest"],
                    permissions=[],
                ),
            }
            app._oa_identity_service.resolve_identity = lambda token: identities[token]

            cases = {
                "readonly": ("read_export_only", True, False, False),
                "full": ("full_access", True, True, False),
                "admin": ("denied", False, False, False),
                "default-admin": ("admin", True, True, True),
                "006": ("denied", False, False, False),
                "outsider": ("denied", False, False, False),
            }
            payloads: dict[str, dict[str, object]] = {}
            for token, expected in cases.items():
                response = app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": f"Bearer {token}"},
                )
                self.assertEqual(response.status_code, 200, token)
                payload = json.loads(response.body)
                payloads[token] = payload
                self.assertEqual(
                    (
                        payload["access_tier"],
                        payload["can_access_app"],
                        payload["can_mutate_data"],
                        payload["can_admin_access"],
                    ),
                    expected,
                    token,
                )

        self.assertTrue(payloads["readonly"]["allowed"])
        self.assertEqual(payloads["006"]["roles"], ["finance", "finops_full_access"])
        self.assertEqual(payloads["006"]["permissions"], ["finops:app:view"])
        self.assertFalse(payloads["outsider"]["allowed"])

    def test_environment_and_oa_identity_roles_cannot_grant_app_access(self) -> None:
        with self._temporary_env(
            FIN_OPS_ALLOWED_USERNAMES="ENV001",
            FIN_OPS_ALLOWED_ROLES="finance",
            FIN_OPS_READONLY_EXPORT_USERNAMES="ENV001",
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda _token: OAUserIdentity(
                user_id="env-user",
                username="ENV001",
                nickname="env user",
                display_name="env user",
                roles=["finance"],
                permissions=["finops:app:view"],
            )

            payload = json.loads(
                app.handle_request(
                    "GET",
                    "/api/session/me",
                    headers={"Authorization": "Bearer env-user"},
                ).body
            )

        self.assertEqual(payload["access_tier"], "denied")
        self.assertEqual(payload["roles"], ["finance"])
        self.assertEqual(payload["permissions"], ["finops:app:view"])

    def test_cached_identity_is_denied_immediately_after_acl_revocation(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, full_access=["CACHED001"])
            identity = OAUserIdentity(
                "cached",
                "CACHED001",
                "cached",
                "cached",
                roles=["finance", "finops_full_access"],
                permissions=["finops:app:view"],
            )
            app._oa_identity_service.resolve_identity = lambda _token: identity
            headers = {"Authorization": "Bearer cached-user"}

            before = json.loads(app.handle_request("GET", "/api/session/me", headers=headers).body)
            configure_access_control(app)
            after = json.loads(app.handle_request("GET", "/api/session/me", headers=headers).body)
            protected_response = app.handle_request("GET", "/api/workbench?month=2026-07", headers=headers)

        self.assertEqual(before["access_tier"], "full_access")
        self.assertEqual(after["access_tier"], "denied")
        self.assertEqual(after["roles"], ["finance", "finops_full_access"])
        self.assertEqual(after["permissions"], ["finops:app:view"])
        self.assertEqual(protected_response.status_code, 403)

    def test_get_session_me_returns_denied_tier_for_visible_but_unauthorized_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: OAUserIdentity(
                user_id="204",
                username="outsider",
                nickname="外部用户",
                display_name="外部用户",
                roles=["guest"],
                permissions=[],
            )

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer outsider"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertFalse(payload["allowed"])
        self.assertEqual(payload["access_tier"], "denied")
        self.assertFalse(payload["can_access_app"])
        self.assertFalse(payload["can_mutate_data"])
        self.assertFalse(payload["can_admin_access"])

    def test_get_session_me_returns_unauthorized_for_expired_oa_session(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))

            def raise_expired(_: str) -> OAUserIdentity:
                raise OASessionExpiredError("登录状态已过期")

            app._oa_identity_service.resolve_identity = raise_expired

            response = app.handle_request(
                "GET",
                "/api/session/me",
                headers={"Authorization": "Bearer expired-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 401)
        self.assertEqual(payload["error"], "invalid_oa_session")


if __name__ == "__main__":
    unittest.main()
