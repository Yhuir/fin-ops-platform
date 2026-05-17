import json
import os
import tempfile
import unittest
from contextlib import contextmanager
from pathlib import Path
from unittest.mock import patch

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_identity_service import OASessionExpiredError, OAUserIdentity


class AuthGuardTests(unittest.TestCase):
    def _identity(
        self,
        *,
        username: str = "YNSYLP005",
        roles: list[str] | None = None,
        permissions: list[str] | None = None,
    ) -> OAUserIdentity:
        return OAUserIdentity(
            user_id=f"{username}-id",
            username=username,
            nickname=username,
            display_name=username,
            dept_id="01",
            dept_name="财务部",
            roles=roles if roles is not None else ["finance"],
            permissions=permissions if permissions is not None else ["finops:app:view"],
        )

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

    def test_auth_guard_accepts_authorization_x_oa_token_and_admin_token_cookie(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            seen_tokens: list[str] = []

            def resolve(token: str) -> OAUserIdentity:
                seen_tokens.append(token)
                return self._identity(username="YNSYLP005")

            app._oa_identity_service.resolve_identity = resolve

            authorization_response = app.handle_request(
                "GET",
                "/projects",
                headers={"Authorization": "Bearer authorization-token"},
            )
            x_oa_token_response = app.handle_request(
                "GET",
                "/projects",
                headers={"X-OA-Token": "x-oa-token"},
            )
            cookie_response = app.handle_request(
                "GET",
                "/projects",
                headers={"Cookie": "Admin-Token=cookie-token"},
            )

        self.assertEqual(authorization_response.status_code, 200)
        self.assertEqual(x_oa_token_response.status_code, 200)
        self.assertEqual(cookie_response.status_code, 200)
        self.assertEqual(seen_tokens, ["authorization-token", "x-oa-token", "cookie-token"])

    def test_readonly_user_cannot_call_platform_write_route(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["READONLY001"],
                readonly_export_usernames=["READONLY001"],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda token: self._identity(
                username="READONLY001",
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/projects/assign",
                body=json.dumps(
                    {
                        "actor_id": "READONLY001",
                        "object_type": "bank_transaction",
                        "object_id": "missing-object",
                        "project_id": "missing-project",
                    }
                ),
                headers={"Authorization": "Bearer readonly-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")

    def test_non_admin_user_cannot_call_platform_admin_route(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._app_settings_service.update_settings(
                completed_project_ids=[],
                bank_account_mappings=[],
                allowed_usernames=["FULL001"],
                readonly_export_usernames=[],
                admin_usernames=[],
            )
            app._oa_identity_service.resolve_identity = lambda token: self._identity(
                username="FULL001",
                permissions=[],
            )

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": [],
                        "readonly_export_usernames": [],
                        "admin_usernames": [],
                        "workbench_column_layouts": {},
                    }
                ),
                headers={"Authorization": "Bearer full-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "admin_only")

    def test_shadow_runtime_user_from_environment_can_call_admin_route(self) -> None:
        with self._without_default_test_auth(), patch.dict(
            os.environ,
            {"FIN_OPS_SHADOW_OA_USERNAME": "test"},
            clear=False,
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: self._identity(username="test")

            response = app.handle_request(
                "POST",
                "/api/workbench/settings",
                body=json.dumps(
                    {
                        "completed_project_ids": [],
                        "bank_account_mappings": [],
                        "allowed_usernames": ["test"],
                        "readonly_export_usernames": [],
                        "admin_usernames": ["test"],
                        "workbench_column_layouts": {},
                    }
                ),
                headers={"Authorization": "Bearer shadow-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertIn("test", payload["access_control"]["admin_usernames"])

    def test_shadow_runtime_reload_endpoint_requires_explicit_token(self) -> None:
        with self._without_default_test_auth(), patch.dict(
            os.environ,
            {"FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN": "reload-secret"},
            clear=False,
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            response = app.handle_request(
                "POST",
                "/__shadow/reload-runtime",
                headers={"X-Fin-Ops-Shadow-Reload-Token": "reload-secret"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["status"], "reloaded")

    def test_shadow_runtime_reload_endpoint_is_not_available_without_token(self) -> None:
        with self._without_default_test_auth(), patch.dict(
            os.environ,
            {"FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN": ""},
            clear=False,
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            response = app.handle_request("POST", "/__shadow/reload-runtime")
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 404)
        self.assertEqual(payload["error"], "not_found")

    def test_shadow_runtime_reload_endpoint_rejects_wrong_token(self) -> None:
        with self._without_default_test_auth(), patch.dict(
            os.environ,
            {"FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN": "reload-secret"},
            clear=False,
        ), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            response = app.handle_request(
                "POST",
                "/__shadow/reload-runtime",
                headers={"X-Fin-Ops-Shadow-Reload-Token": "wrong"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "shadow_reload_forbidden")

    def test_platform_write_rejects_body_actor_spoofing_before_business_write(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: self._identity(username="YNSYLP005")

            response = app.handle_request(
                "POST",
                "/projects",
                body=json.dumps(
                    {
                        "actor_id": "OTHER001",
                        "project_code": "SPOOF-001",
                        "project_name": "Spoofed Actor Project",
                    }
                ),
                headers={"Authorization": "Bearer admin-token"},
            )
            payload = json.loads(response.body)
            projects_payload = json.loads(
                app.handle_request(
                    "GET",
                    "/projects",
                    headers={"Authorization": "Bearer admin-token"},
                ).body
            )

        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "actor_mismatch")
        self.assertEqual(projects_payload["projects"], [])

    def test_background_acknowledge_uses_authenticated_oa_owner(self) -> None:
        with self._without_default_test_auth(), tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            app._oa_identity_service.resolve_identity = lambda token: self._identity(username="ack-user")
            job = app._background_job_service.create_job(
                job_type="shadow_ack",
                label="Shadow acknowledge",
                owner_user_id="ack-user",
                visibility="owner",
                phase="failed",
                current=1,
                total=1,
                message="ready",
            )
            app._background_job_service.fail_job(job.job_id, "ready", "failed")

            response = app.handle_request(
                "POST",
                f"/api/background-jobs/{job.job_id}/acknowledge",
                body=json.dumps({"reason": "done"}),
                headers={"Authorization": "Bearer ack-token"},
            )
            payload = json.loads(response.body)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(payload["job"]["status"], "acknowledged")


if __name__ == "__main__":
    unittest.main()
