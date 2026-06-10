from __future__ import annotations

import json
import unittest
from types import SimpleNamespace

from fin_ops_platform.services.oa_applicant_credentials import OaApplicantLoginCredential
from fin_ops_platform.services.target_oa_applicant_token_provider import (
    OaLoginClient,
    OaLoginClientSettings,
    TargetOaApplicantCredentialMissingError,
    TargetOaApplicantLoginError,
    TargetOaApplicantTokenProvider,
)


class FakeCredentialService:
    def __init__(self, credential: OaApplicantLoginCredential | None) -> None:
        self.credential = credential
        self.requested_codes: list[str] = []

    def resolve_login_credential(self, target_applicant_code: str) -> OaApplicantLoginCredential | None:
        self.requested_codes.append(target_applicant_code)
        return self.credential


class FakeLoginClient:
    def __init__(self, token: str = "target-token") -> None:
        self.token = token
        self.calls: list[tuple[str, str]] = []

    def login(self, username: str, password: str) -> str:
        self.calls.append((username, password))
        return self.token


class FakeEncryptor:
    def __init__(self) -> None:
        self.passwords: list[str] = []

    def encrypt(self, password: str) -> str:
        self.passwords.append(password)
        return f"encrypted::{password}"


class FakeHttpResponse:
    def __init__(self, payload: dict[str, object]) -> None:
        self.payload = payload

    def __enter__(self) -> "FakeHttpResponse":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        return None

    def read(self) -> bytes:
        return json.dumps(self.payload).encode("utf-8")


class OaLoginClientTests(unittest.TestCase):
    def test_login_posts_rsa_encrypted_password_and_extracts_token(self) -> None:
        encryptor = FakeEncryptor()
        requests: list[object] = []

        def urlopen_stub(request: object, *, timeout: float) -> FakeHttpResponse:
            del timeout
            requests.append(request)
            return FakeHttpResponse({"code": 200, "data": "target-token"})

        client = OaLoginClient(
            settings=OaLoginClientSettings(base_url="https://oa.example.test", login_path="/auth/login"),
            password_encryptor=encryptor,
            urlopen_func=urlopen_stub,
        )

        token = client.login("chen_xiuyun", "plain-password")

        self.assertEqual(token, "target-token")
        self.assertEqual(encryptor.passwords, ["plain-password"])
        request = requests[0]
        body = json.loads(request.data.decode("utf-8"))
        self.assertEqual(body["username"], "chen_xiuyun")
        self.assertEqual(body["password"], "encrypted::plain-password")
        self.assertNotEqual(body["password"], "plain-password")
        self.assertTrue(request.full_url.endswith("/auth/login"))

    def test_login_failure_does_not_expose_password(self) -> None:
        encryptor = FakeEncryptor()

        def urlopen_stub(request: object, *, timeout: float) -> FakeHttpResponse:
            del request, timeout
            return FakeHttpResponse({"code": 500, "msg": "密码错误"})

        client = OaLoginClient(
            settings=OaLoginClientSettings(base_url="https://oa.example.test"),
            password_encryptor=encryptor,
            urlopen_func=urlopen_stub,
        )

        with self.assertRaises(TargetOaApplicantLoginError) as context:
            client.login("chen_xiuyun", "plain-password")

        self.assertNotIn("plain-password", str(context.exception))
        self.assertEqual(context.exception.code, "target_oa_login_failed")


class TargetOaApplicantTokenProviderTests(unittest.TestCase):
    def test_provider_uses_target_applicant_credential_and_returns_draft_client(self) -> None:
        credential_service = FakeCredentialService(
            OaApplicantLoginCredential(
                target_applicant_code="chen_xiuyun",
                oa_username="chen_xiuyun",
                password="correct-password",
            )
        )
        login_client = FakeLoginClient(token="target-token")
        created_clients: list[str] = []
        provider = TargetOaApplicantTokenProvider(
            credential_service=credential_service,
            login_client=login_client,
            oa_client_factory=lambda token: created_clients.append(token) or SimpleNamespace(token=token),
        )

        client = provider.draft_client_for("chen_xiuyun")

        self.assertEqual(credential_service.requested_codes, ["chen_xiuyun"])
        self.assertEqual(login_client.calls, [("chen_xiuyun", "correct-password")])
        self.assertEqual(client.token, "target-token")
        self.assertEqual(created_clients, ["target-token"])

    def test_missing_credential_fails_without_login_attempt(self) -> None:
        credential_service = FakeCredentialService(None)
        login_client = FakeLoginClient()
        provider = TargetOaApplicantTokenProvider(
            credential_service=credential_service,
            login_client=login_client,
            oa_client_factory=lambda token: SimpleNamespace(token=token),
        )

        with self.assertRaises(TargetOaApplicantCredentialMissingError):
            provider.draft_client_for("chen_xiuyun")

        self.assertEqual(login_client.calls, [])


if __name__ == "__main__":
    unittest.main()
