from __future__ import annotations

import base64
from dataclasses import dataclass
import json
import os
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory
from typing import Any, Callable, Protocol
from urllib.error import HTTPError, URLError
from urllib.parse import urljoin
from urllib.request import Request, urlopen

from fin_ops_platform.services.etc_service import EtcOAHttpClientSettings, HttpEtcOAClient


OA_LOGIN_RSA_PUBLIC_KEY_ENV = "FIN_OPS_OA_LOGIN_RSA_PUBLIC_KEY"


class TargetOaApplicantTokenProviderError(RuntimeError):
    code = "target_oa_applicant_token_error"


class TargetOaApplicantCredentialMissingError(TargetOaApplicantTokenProviderError):
    code = "target_oa_applicant_credential_missing"


class TargetOaApplicantLoginError(TargetOaApplicantTokenProviderError):
    code = "target_oa_login_failed"


class TargetOaApplicantConfigurationError(TargetOaApplicantTokenProviderError):
    code = "target_oa_login_unavailable"


class OaPasswordEncryptor(Protocol):
    def encrypt(self, password: str) -> str:
        ...


class OaLoginCredentialService(Protocol):
    def resolve_login_credential(self, target_applicant_code: str) -> object | None:
        ...


@dataclass(slots=True, frozen=True)
class OaLoginClientSettings:
    base_url: str | None
    login_path: str = "/auth/login"
    request_timeout_ms: int = 20000

    @classmethod
    def from_environment(cls) -> "OaLoginClientSettings":
        return cls(
            base_url=os.getenv("FIN_OPS_OA_BASE_URL"),
            login_path=os.getenv("FIN_OPS_OA_LOGIN_PATH", "/auth/login").strip() or "/auth/login",
            request_timeout_ms=int(os.getenv("FIN_OPS_OA_LOGIN_REQUEST_TIMEOUT_MS", os.getenv("FIN_OPS_OA_REQUEST_TIMEOUT_MS", "20000"))),
        )


class OpenSslRsaPasswordEncryptor:
    def __init__(self, *, public_key: str | None = None, openssl_binary: str | None = None) -> None:
        self._public_key = public_key
        self._openssl_binary = openssl_binary

    def encrypt(self, password: str) -> str:
        public_key = str(self._public_key or os.getenv(OA_LOGIN_RSA_PUBLIC_KEY_ENV) or "").strip()
        if not public_key:
            raise TargetOaApplicantConfigurationError(f"{OA_LOGIN_RSA_PUBLIC_KEY_ENV} is required for target OA login.")
        openssl_binary = self._openssl_binary or shutil.which("openssl")
        if not openssl_binary:
            raise TargetOaApplicantConfigurationError("openssl is required for target OA login RSA encryption.")
        with TemporaryDirectory() as temp_dir:
            key_path = Path(temp_dir) / "oa-login-public-key.pem"
            key_path.write_text(_public_key_pem(public_key), encoding="utf-8")
            completed = subprocess.run(
                [
                    openssl_binary,
                    "pkeyutl",
                    "-encrypt",
                    "-pubin",
                    "-inkey",
                    str(key_path),
                    "-pkeyopt",
                    "rsa_padding_mode:pkcs1",
                ],
                input=str(password or "").encode("utf-8"),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                check=False,
            )
        if completed.returncode != 0:
            raise TargetOaApplicantConfigurationError("OA login RSA encryption failed.")
        return base64.b64encode(completed.stdout).decode("ascii")


class OaLoginClient:
    def __init__(
        self,
        *,
        settings: OaLoginClientSettings | None = None,
        password_encryptor: OaPasswordEncryptor | None = None,
        urlopen_func: Callable[..., Any] | None = None,
    ) -> None:
        self._settings = settings or OaLoginClientSettings.from_environment()
        self._password_encryptor = password_encryptor or OpenSslRsaPasswordEncryptor()
        self._urlopen = urlopen_func or urlopen

    def login(self, username: str, password: str) -> str:
        normalized_username = str(username or "").strip()
        if not normalized_username or not str(password or ""):
            raise TargetOaApplicantLoginError("目标 OA 申请人账号或密码为空。")
        base_url = str(self._settings.base_url or "").strip()
        if not base_url:
            raise TargetOaApplicantConfigurationError("未配置 OA 登录服务地址。")
        encrypted_password = self._password_encryptor.encrypt(str(password or ""))
        url = urljoin(f"{base_url.rstrip('/')}/", self._settings.login_path.lstrip("/"))
        request = Request(
            url,
            data=json.dumps(
                {
                    "username": normalized_username,
                    "password": encrypted_password,
                },
                ensure_ascii=False,
            ).encode("utf-8"),
            headers={
                "Accept": "application/json",
                "Content-Type": "application/json;charset=utf-8",
            },
            method="POST",
        )
        timeout_seconds = max(self._settings.request_timeout_ms / 1000, 1)
        try:
            with self._urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            raw_body = error.read().decode("utf-8", errors="ignore")
            raise TargetOaApplicantLoginError(_extract_error_message(raw_body) or "目标 OA 申请人登录失败。") from error
        except URLError as error:
            raise TargetOaApplicantLoginError("无法连接 OA 登录服务。") from error

        try:
            payload = json.loads(raw_body) if raw_body.strip() else {}
        except json.JSONDecodeError as error:
            raise TargetOaApplicantLoginError("OA 登录服务返回了无效 JSON。") from error
        if not isinstance(payload, dict):
            raise TargetOaApplicantLoginError("OA 登录服务返回格式不正确。")
        code = payload.get("code", 200)
        if code not in {0, 200, "0", "200", None}:
            raise TargetOaApplicantLoginError(_extract_error_message(payload) or "目标 OA 申请人登录失败。")
        token = _extract_token(payload)
        if not token:
            raise TargetOaApplicantLoginError("OA 登录响应没有返回 token。")
        return token


class TargetOaApplicantTokenProvider:
    def __init__(
        self,
        *,
        credential_service: OaLoginCredentialService,
        login_client: OaLoginClient,
        oa_client_factory: Callable[[str], object] | None = None,
    ) -> None:
        self._credential_service = credential_service
        self._login_client = login_client
        self._oa_client_factory = oa_client_factory or (
            lambda token: HttpEtcOAClient(token=token, settings=EtcOAHttpClientSettings.from_environment())
        )

    def draft_client_for(self, target_applicant_code: str) -> object:
        normalized_code = str(target_applicant_code or "").strip()
        if not normalized_code:
            raise TargetOaApplicantCredentialMissingError("目标 OA 申请人不能为空。")
        credential = self._credential_service.resolve_login_credential(normalized_code)
        if credential is None:
            raise TargetOaApplicantCredentialMissingError("目标 OA 申请人凭据未配置。")
        oa_username = str(getattr(credential, "oa_username", "") or "").strip()
        password = str(getattr(credential, "password", "") or "")
        if not oa_username or not password:
            raise TargetOaApplicantCredentialMissingError("目标 OA 申请人凭据未配置。")
        token = self._login_client.login(oa_username, password)
        return self._oa_client_factory(token)


def _public_key_pem(value: str) -> str:
    normalized = value.strip().replace("\\n", "\n")
    if "BEGIN PUBLIC KEY" in normalized:
        return normalized if normalized.endswith("\n") else f"{normalized}\n"
    compact = "".join(normalized.split())
    lines = [compact[index : index + 64] for index in range(0, len(compact), 64)]
    return "-----BEGIN PUBLIC KEY-----\n" + "\n".join(lines) + "\n-----END PUBLIC KEY-----\n"


def _extract_token(payload: dict[str, Any]) -> str | None:
    data = payload.get("data")
    if isinstance(data, str) and data.strip():
        return data.strip()
    if isinstance(data, dict):
        for key in ("access_token", "accessToken", "token", "Admin-Token"):
            value = data.get(key)
            if value not in (None, ""):
                return str(value).strip()
    for key in ("access_token", "accessToken", "token", "Admin-Token"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value).strip()
    return None


def _extract_error_message(payload: object) -> str | None:
    if isinstance(payload, str):
        try:
            payload = json.loads(payload)
        except json.JSONDecodeError:
            return payload.strip() or None
    if not isinstance(payload, dict):
        return None
    for key in ("msg", "message", "error"):
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None
