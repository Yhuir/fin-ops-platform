from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
import json
import os
from time import monotonic
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urljoin
from urllib.request import Request, urlopen


def _normalize_string(value: Any) -> str:
    return str(value or "").strip()


def _normalize_unique_list(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = _normalize_string(value)
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


class OAIdentityServiceError(RuntimeError):
    pass


class OAIdentityConfigurationError(OAIdentityServiceError):
    pass


class OASessionExpiredError(OAIdentityServiceError):
    pass


@dataclass(slots=True)
class OAUserIdentity:
    user_id: str
    username: str
    nickname: str
    display_name: str
    dept_id: str | None = None
    dept_name: str | None = None
    avatar: str | None = None
    roles: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OAIdentitySettings:
    base_url: str | None
    user_info_path: str = "/system/user/getInfo"
    password_verify_path: str = "/system/user/profile/updatePwd"
    request_timeout_ms: int = 5000
    cache_ttl_seconds: int = 300

    @classmethod
    def from_environment(cls) -> "OAIdentitySettings":
        return cls(
            base_url=os.getenv("FIN_OPS_OA_BASE_URL"),
            user_info_path=os.getenv("FIN_OPS_OA_USER_INFO_PATH", "/system/user/getInfo").strip() or "/system/user/getInfo",
            password_verify_path=(
                os.getenv("FIN_OPS_OA_PASSWORD_VERIFY_PATH", "/system/user/profile/updatePwd").strip()
                or "/system/user/profile/updatePwd"
            ),
            request_timeout_ms=int(os.getenv("FIN_OPS_OA_REQUEST_TIMEOUT_MS", "5000")),
            cache_ttl_seconds=max(int(os.getenv("FIN_OPS_OA_SESSION_CACHE_TTL_SECONDS", "300")), 0),
        )


class OAIdentityService:
    def __init__(self, settings: OAIdentitySettings | None = None) -> None:
        self._settings = settings or OAIdentitySettings.from_environment()
        self._cache: dict[str, tuple[float, OAUserIdentity]] = {}

    def clear_cache(self) -> None:
        self._cache.clear()

    def resolve_identity(self, token: str) -> OAUserIdentity:
        normalized_token = _normalize_string(token)
        if not normalized_token:
            raise OASessionExpiredError("缺少 OA 登录态，请从 OA 系统进入。")

        cached_identity = self._cache.get(normalized_token)
        current_time = monotonic()
        if cached_identity is not None and self._settings.cache_ttl_seconds > 0:
            cached_at, identity = cached_identity
            if current_time - cached_at < self._settings.cache_ttl_seconds:
                return deepcopy(identity)

        payload = self._fetch_user_info(normalized_token)
        identity = self._normalize_identity(payload)
        if self._settings.cache_ttl_seconds > 0:
            self._cache[normalized_token] = (current_time, deepcopy(identity))
        return identity

    def verify_current_user_password(self, token: str, password: str) -> bool:
        normalized_token = _normalize_string(token)
        normalized_password = str(password or "")
        if not normalized_token:
            raise OASessionExpiredError("缺少 OA 登录态，请从 OA 系统进入。")
        if not normalized_password:
            return False

        base_url = _normalize_string(self._settings.base_url)
        if not base_url:
            raise OAIdentityConfigurationError("未配置 OA 用户密码复核服务地址。")

        # OA has no read-only password-check endpoint. Calling updatePwd with
        # oldPassword == newPassword verifies the old password and is rejected
        # before any password mutation when the password is correct.
        url = urljoin(f"{base_url.rstrip('/')}/", self._settings.password_verify_path.lstrip("/"))
        form_body = urlencode({"oldPassword": normalized_password, "newPassword": normalized_password}).encode("utf-8")
        request = Request(
            url,
            data=form_body,
            headers={
                "Authorization": f"Bearer {normalized_token}",
                "Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded",
            },
            method="PUT",
        )
        timeout_seconds = max(self._settings.request_timeout_ms / 1000, 1)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            raw_body = error.read().decode("utf-8", errors="ignore")
            if error.code in {401, 403}:
                raise OASessionExpiredError(self._extract_error_message(raw_body) or "OA 登录状态已过期。") from error
            return False
        except URLError as error:
            raise OAIdentityServiceError("无法连接 OA 用户密码复核服务。") from error

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise OAIdentityServiceError("OA 用户密码复核服务返回了无效 JSON。") from error
        if not isinstance(payload, dict):
            raise OAIdentityServiceError("OA 用户密码复核服务返回格式不正确。")

        response_code = payload.get("code", 200)
        message = _normalize_string(payload.get("msg") or payload.get("message"))
        if response_code in {401, 403}:
            raise OASessionExpiredError(message or "OA 登录状态已过期。")
        if "新密码不能与旧密码相同" in message:
            return True
        if "旧密码错误" in message or "密码错误" in message:
            return False
        return response_code in {0, 200, "0", "200"}

    def _fetch_user_info(self, token: str) -> dict[str, Any]:
        base_url = _normalize_string(self._settings.base_url)
        if not base_url:
            raise OAIdentityConfigurationError("未配置 OA 用户信息服务地址。")

        url = urljoin(f"{base_url.rstrip('/')}/", self._settings.user_info_path.lstrip("/"))
        request = Request(
            url,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
            },
            method="GET",
        )
        timeout_seconds = max(self._settings.request_timeout_ms / 1000, 1)
        try:
            with urlopen(request, timeout=timeout_seconds) as response:
                raw_body = response.read().decode("utf-8")
        except HTTPError as error:
            raw_body = error.read().decode("utf-8", errors="ignore")
            if error.code in {401, 403}:
                raise OASessionExpiredError(self._extract_error_message(raw_body) or "OA 登录状态已过期。") from error
            raise OAIdentityServiceError(self._extract_error_message(raw_body) or "OA 用户信息查询失败。") from error
        except URLError as error:
            raise OAIdentityServiceError("无法连接 OA 用户信息服务。") from error

        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError as error:
            raise OAIdentityServiceError("OA 用户信息服务返回了无效 JSON。") from error
        if not isinstance(payload, dict):
            raise OAIdentityServiceError("OA 用户信息服务返回格式不正确。")
        return payload

    def _normalize_identity(self, payload: dict[str, Any]) -> OAUserIdentity:
        response_code = payload.get("code", 200)
        if response_code in {401, 403}:
            raise OASessionExpiredError(_normalize_string(payload.get("msg")) or "OA 登录状态已过期。")
        if response_code not in {0, 200, "0", "200", None}:
            raise OAIdentityServiceError(_normalize_string(payload.get("msg")) or "OA 用户信息查询失败。")

        data_payload = payload.get("data")
        user_payload = payload.get("user")
        if not isinstance(user_payload, dict) and isinstance(data_payload, dict):
            nested_user = data_payload.get("user")
            user_payload = nested_user if isinstance(nested_user, dict) else data_payload
        if not isinstance(user_payload, dict):
            raise OAIdentityServiceError("OA 用户信息返回缺少 user。")

        dept_payload = user_payload.get("dept")
        dept_id = _normalize_string(user_payload.get("deptId"))
        dept_name = _normalize_string(user_payload.get("deptName"))
        if isinstance(dept_payload, dict):
            dept_id = dept_id or _normalize_string(dept_payload.get("deptId"))
            dept_name = dept_name or _normalize_string(dept_payload.get("deptName"))

        user_id = _normalize_string(user_payload.get("userId") or user_payload.get("id"))
        username = _normalize_string(user_payload.get("userName") or user_payload.get("username"))
        nickname = _normalize_string(user_payload.get("nickName") or user_payload.get("nickname"))
        display_name = nickname or username
        if not user_id or not username:
            raise OAIdentityServiceError("OA 用户信息缺少 userId 或 username。")

        roles = _normalize_unique_list(payload.get("roles"))
        permissions = _normalize_unique_list(payload.get("permissions"))
        if not roles and isinstance(data_payload, dict):
            roles = _normalize_unique_list(data_payload.get("roles"))
        if not permissions and isinstance(data_payload, dict):
            permissions = _normalize_unique_list(data_payload.get("permissions"))

        avatar = _normalize_string(user_payload.get("avatar")) or None
        return OAUserIdentity(
            user_id=user_id,
            username=username,
            nickname=nickname,
            display_name=display_name,
            dept_id=dept_id or None,
            dept_name=dept_name or None,
            avatar=avatar,
            roles=roles,
            permissions=permissions,
        )

    @staticmethod
    def _extract_error_message(raw_body: str) -> str | None:
        try:
            payload = json.loads(raw_body)
        except json.JSONDecodeError:
            return raw_body.strip() or None
        if isinstance(payload, dict):
            message = _normalize_string(payload.get("msg") or payload.get("message"))
            return message or None
        return None
