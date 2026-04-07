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


if __name__ == "__main__":
    unittest.main()
