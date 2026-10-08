from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from fin_ops_platform.services.oa_identity_service import OAUserIdentity

from tests.app_test_support import (
    build_local_state_application as build_application,
)
from tests.app_test_support import (
    configure_access_control,
)


class OaApplicantCredentialApiTests(unittest.TestCase):
    def test_admin_can_save_list_update_delete_and_directory_without_secret_echo(self) -> None:
        from tests.test_oa_applicant_credentials_service import credential_service
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_identity_resolver(app)
            app._oa_applicant_credential_service_instance = credential_service()
            endpoint = "/api/workbench/settings/oa-applicant-credentials"
            def request(method, path=endpoint, payload=None):
                response = app.handle_request(method, path, headers=self._admin_headers(),
                                            body=json.dumps(payload) if payload is not None else None)
                self.assertNotIn("secret", response.body)
                return response, json.loads(response.body)
            response, users = request("GET", endpoint + "/users")
            self.assertEqual(response.status_code, 200)
            self.assertEqual(users["users"][0]["userId"], "7")
            response, data = request("POST", payload={"oaUserId": "7", "password": "secret", "remark": "差旅"})
            self.assertEqual(response.status_code, 200)
            saved = data["credential"]
            self.assertEqual(saved["oaUserId"], "7")
            self.assertTrue(saved["verifiedAt"])
            self.assertEqual(saved["version"], 1)
            path = endpoint + "/" + saved["targetApplicantCode"]
            _, listed = request("GET")
            self.assertEqual(listed["credentials"], [saved])
            response, data = request("PUT", path, {"oaUserId": "7", "password": "secret", "remark": "新版", "expectedVersion": 1})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data["credential"]["version"], 2)
            response, data = request("DELETE", path, {"expectedVersion": 1})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(data["error"], "oa_applicant_credential_conflict")
            response, data = request("DELETE", path, {"expectedVersion": 2})
            self.assertEqual(response.status_code, 200)
            self.assertEqual(data, {"deleted": True, "targetApplicantCode": saved["targetApplicantCode"]})
            _, listed = request("GET")
            self.assertEqual(listed, {"credentials": []})
            response, data = request("PUT", path, {"oaUserId": "7", "password": "secret", "remark": "", "expectedVersion": 2})
            self.assertEqual(response.status_code, 404)
            self.assertEqual(data["error"], "oa_applicant_credential_not_found")
            response, _ = request("GET", "/api/workbench/settings")
            self.assertEqual(response.status_code, 200)

    def test_api_rejects_old_fields_wrong_types_and_failed_verification(self):
        from fin_ops_platform.services.target_oa_applicant_token_provider import TargetOaApplicantLoginError
        from tests.test_oa_applicant_credentials_service import credential_service
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            self._install_identity_resolver(app)
            app._oa_applicant_credential_service_instance = credential_service(
                login=lambda *args: (_ for _ in ()).throw(TargetOaApplicantLoginError("密码错误")))
            for payload in ({"targetApplicantName": "伪造", "oaUsername": "fake", "password": "wrong"},
                            {"oaUserId": 7, "password": "wrong"}, {"oaUserId": "7", "password": 1},
                            {"oaUserId": "7", "password": "wrong", "remark": False}):
                response = app.handle_request("POST", "/api/workbench/settings/oa-applicant-credentials",
                    headers=self._admin_headers(), body=json.dumps(payload))
                self.assertEqual(response.status_code, 400)
                self.assertEqual(json.loads(response.body)["error"], "invalid_oa_applicant_credential")
            response = app.handle_request("POST", "/api/workbench/settings/oa-applicant-credentials",
                headers=self._admin_headers(), body=json.dumps({"oaUserId": "7", "password": "wrong"}))
            self.assertEqual(response.status_code, 400)
            self.assertEqual(json.loads(response.body), {"error": "oa_applicant_verification_failed", "message": "密码错误"})
            self.assertEqual(app._oa_applicant_credential_service_instance.applicant_options(), [])

    def test_non_admin_cannot_maintain_credentials(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            app = build_application(data_dir=Path(temp_dir))
            configure_access_control(app, usernames=["YNSYLP006"])
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
        self.assertEqual(payload["error"], "admin_access_required")
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
                username="YNSYLP006",
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
