import unittest

from fin_ops_platform.services.oa_identity_service import (
    OAIdentityConfigurationError,
    OAIdentityService,
    OAIdentitySettings,
    OAUserIdentity,
)
from fin_ops_platform.services.target_oa_applicant_token_provider import (
    TargetOaApplicantConfigurationError,
    TargetOaApplicantLoginError,
)


def _identity(*, user_id: str = "admin-id", username: str = "YNSYLP005") -> OAUserIdentity:
    return OAUserIdentity(
        user_id=user_id,
        username=username,
        nickname="管理员",
        display_name="管理员",
    )


class _LoginClient:
    def __init__(self, result: str | Exception) -> None:
        self.result = result
        self.calls: list[tuple[str, str]] = []

    def login(self, username: str, password: str) -> str:
        self.calls.append((username, password))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


class OAIdentityServicePasswordVerificationTests(unittest.TestCase):
    def _service(self, login_client: _LoginClient) -> OAIdentityService:
        service = OAIdentityService(
            OAIdentitySettings(base_url="https://oa.example.test", cache_ttl_seconds=0),
            login_client=login_client,
        )
        identities = {
            "session-token": _identity(),
            "verified-token": _identity(),
            "other-token": _identity(user_id="other-id", username="YNSYLP006"),
        }
        service.resolve_identity = lambda token: identities[token]  # type: ignore[method-assign]
        return service

    def test_verify_current_user_password_requires_login_and_matching_identity(self) -> None:
        login_client = _LoginClient("verified-token")

        result = self._service(login_client).verify_current_user_password(
            "session-token", "secret-password"
        )

        self.assertTrue(result)
        self.assertEqual(login_client.calls, [("YNSYLP005", "secret-password")])

    def test_verify_current_user_password_rejects_wrong_password(self) -> None:
        service = self._service(_LoginClient(TargetOaApplicantLoginError("wrong password")))

        self.assertFalse(service.verify_current_user_password("session-token", "wrong-password"))

    def test_verify_current_user_password_rejects_login_for_another_identity(self) -> None:
        service = self._service(_LoginClient("other-token"))

        self.assertFalse(service.verify_current_user_password("session-token", "secret-password"))

    def test_verify_current_user_password_fails_closed_when_login_is_unconfigured(self) -> None:
        service = self._service(
            _LoginClient(TargetOaApplicantConfigurationError("missing public key"))
        )

        with self.assertRaises(OAIdentityConfigurationError):
            service.verify_current_user_password("session-token", "secret-password")


if __name__ == "__main__":
    unittest.main()
