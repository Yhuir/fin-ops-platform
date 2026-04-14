import json
import unittest
from unittest.mock import patch

from fin_ops_platform.services.oa_identity_service import OAIdentityService, OAIdentitySettings


class _FakeResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self._body = json.dumps(payload, ensure_ascii=False).encode("utf-8")

    def __enter__(self) -> "_FakeResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return self._body


class OAIdentityServicePasswordVerificationTests(unittest.TestCase):
    def _service(self) -> OAIdentityService:
        return OAIdentityService(
            OAIdentitySettings(
                base_url="https://oa.example.test",
                password_verify_path="/system/user/profile/updatePwd",
                request_timeout_ms=1000,
                cache_ttl_seconds=0,
            )
        )

    def test_verify_current_user_password_treats_same_new_password_rejection_as_success(self) -> None:
        requests = []

        def fake_urlopen(request, timeout):
            requests.append(request)
            return _FakeResponse({"code": 500, "msg": "新密码不能与旧密码相同"})

        with patch("fin_ops_platform.services.oa_identity_service.urlopen", fake_urlopen):
            result = self._service().verify_current_user_password("session-token", "secret-password")

        self.assertTrue(result)
        self.assertEqual(len(requests), 1)
        request = requests[0]
        self.assertEqual(request.get_method(), "PUT")
        self.assertEqual(request.get_header("Authorization"), "Bearer session-token")
        self.assertEqual(request.get_header("Content-type"), "application/x-www-form-urlencoded")
        self.assertIn("/system/user/profile/updatePwd", request.full_url)
        self.assertNotIn("secret-password", request.full_url)
        form_body = request.data.decode("utf-8")
        self.assertIn("oldPassword=secret-password", form_body)
        self.assertIn("newPassword=secret-password", form_body)
        self.assertNotIn("username", request.full_url)

    def test_verify_current_user_password_returns_false_for_wrong_old_password(self) -> None:
        def fake_urlopen(request, timeout):
            return _FakeResponse({"code": 500, "msg": "修改密码失败，旧密码错误"})

        with patch("fin_ops_platform.services.oa_identity_service.urlopen", fake_urlopen):
            result = self._service().verify_current_user_password("session-token", "wrong-password")

        self.assertFalse(result)


if __name__ == "__main__":
    unittest.main()
