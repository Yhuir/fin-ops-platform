import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path

from fin_ops_platform.app.server import build_application
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

    def test_get_session_me_does_not_fail_when_dynamic_settings_provider_is_unavailable_for_permitted_user(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._access_control_service.dynamic_allowed_usernames_provider = lambda: (_ for _ in ()).throw(
                RuntimeError("settings store unavailable")
            )
            app._access_control_service.dynamic_readonly_export_usernames_provider = lambda: (_ for _ in ()).throw(
                RuntimeError("settings store unavailable")
            )
            app._access_control_service.dynamic_admin_usernames_provider = lambda: (_ for _ in ()).throw(
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
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["access_tier"], "full_access")
        self.assertTrue(payload["can_access_app"])
        self.assertTrue(any("dynamic provider failed" in message for message in logs.output))

    def test_get_session_me_accepts_admin_token_cookie(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
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

            response = app.handle_request("GET", "/api/session/me")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(payload["allowed"])
        self.assertEqual(payload["user"]["username"], "local_finops_admin")
        self.assertEqual(payload["access_tier"], "admin")
        self.assertTrue(payload["can_admin_access"])

    def test_get_session_me_allows_username_from_workbench_settings_even_without_permission_code(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["YNSYLP005"],
            )
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
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
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
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001"],
                readonly_export_usernames=[],
                admin_usernames=[],
            )
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
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001", "FULL001"],
                readonly_export_usernames=["READONLY001", "ADMIN001"],
                admin_usernames=["ADMIN001"],
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
                "permission": OAUserIdentity(
                    user_id="305",
                    username="PERMISSION001",
                    nickname="权限码用户",
                    display_name="权限码用户",
                    roles=["finance"],
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
                "admin": ("admin", True, True, True),
                "default-admin": ("admin", True, True, True),
                "permission": ("full_access", True, True, False),
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
        self.assertFalse(payloads["outsider"]["allowed"])

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
