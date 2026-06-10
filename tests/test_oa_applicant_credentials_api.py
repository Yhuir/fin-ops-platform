from __future__ import annotations

import json
from pathlib import Path
import tempfile
import unittest

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.oa_identity_service import OAUserIdentity


class OaApplicantCredentialApiTests(unittest.TestCase):
    def test_admin_can_save_list_and_delete_credentials_without_password_echo_or_settings_leak(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_identity_resolver(app)

            save_response = app.handle_request(
                "PUT",
                "/api/workbench/settings/oa-applicant-credentials/chen_xiuyun",
                headers=self._admin_headers(),
                body=json.dumps(
                    {
                        "targetApplicantName": "陈秀云",
                        "oaUsername": "chen_xiuyun",
                        "password": "correct-password",
                    }
                ),
            )
            list_response = app.handle_request(
                "GET",
                "/api/workbench/settings/oa-applicant-credentials",
                headers=self._admin_headers(),
            )
            settings_response = app.handle_request("GET", "/api/workbench/settings")
            delete_response = app.handle_request(
                "DELETE",
                "/api/workbench/settings/oa-applicant-credentials/chen_xiuyun",
                headers=self._admin_headers(),
            )

        saved = json.loads(save_response.body)
        listed = json.loads(list_response.body)
        deleted = json.loads(delete_response.body)

        self.assertEqual(save_response.status_code, 200)
        self.assertEqual(saved["credential"]["credentialStatus"], "configured")
        self.assertTrue(saved["credential"]["hasCredential"])
        self.assertNotIn("password", saved["credential"])
        self.assertNotIn("correct-password", save_response.body)
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(listed["credentials"], [saved["credential"]])
        self.assertNotIn("correct-password", list_response.body)
        self.assertEqual(settings_response.status_code, 200)
        self.assertNotIn("correct-password", settings_response.body)
        self.assertEqual(delete_response.status_code, 200)
        self.assertEqual(deleted["credential"]["credentialStatus"], "unconfigured")

    def test_full_access_non_admin_cannot_maintain_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_identity_resolver(app)

            response = app.handle_request(
                "PUT",
                "/api/workbench/settings/oa-applicant-credentials/chen_xiuyun",
                headers=self._full_access_headers(),
                body=json.dumps(
                    {
                        "targetApplicantName": "陈秀云",
                        "oaUsername": "chen_xiuyun",
                        "password": "correct-password",
                    }
                ),
            )
            list_response = app.handle_request(
                "GET",
                "/api/workbench/settings/oa-applicant-credentials",
                headers=self._full_access_headers(),
            )

        payload = json.loads(response.body)
        self.assertEqual(response.status_code, 403)
        self.assertEqual(payload["error"], "permission_denied")
        self.assertEqual(list_response.status_code, 403)

    @staticmethod
    def _install_identity_resolver(app: object) -> None:
        def resolve_identity(token: str) -> OAUserIdentity:
            if token == "admin-token":
                return OAUserIdentity(
                    user_id="101",
                    username="YNSYLP005",
                    nickname="管理员",
                    display_name="管理员",
                    roles=["finance"],
                    permissions=["finops:app:view"],
                )
            return OAUserIdentity(
                user_id="102",
                username="FULL001",
                nickname="全操作用户",
                display_name="全操作用户",
                roles=["finance"],
                permissions=["finops:app:view"],
            )

        app._oa_identity_service.resolve_identity = resolve_identity

    @staticmethod
    def _admin_headers() -> dict[str, str]:
        return {"Authorization": "Bearer admin-token"}

    @staticmethod
    def _full_access_headers() -> dict[str, str]:
        return {"Authorization": "Bearer full-token"}


if __name__ == "__main__":
    unittest.main()
