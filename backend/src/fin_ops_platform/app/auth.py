from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
import os
from typing import Mapping

from fin_ops_platform.services.access_control_service import AccessControlService, AccessTier
from fin_ops_platform.services.oa_identity_service import OAIdentityService, OAUserIdentity


AUTHORIZATION_HEADER = "authorization"
COOKIE_HEADER = "cookie"
OA_TOKEN_COOKIE_NAME = "Admin-Token"
BEARER_PREFIX = "bearer "
RETIRED_AUTH_ENV_KEYS = (
    "FIN_OPS_TEST_DEFAULT_AUTH",
    "FIN_OPS_DEV_ALLOW_LOCAL_SESSION",
    "FIN_OPS_DEV_USERNAME",
    "FIN_OPS_DEV_OA_PASSWORD",
)


class OAAuthError(RuntimeError):
    pass


class UnauthorizedOASessionError(OAAuthError):
    pass


class ForbiddenOAAccessError(OAAuthError):
    pass


class AuthRuntimeConfigurationError(RuntimeError):
    pass


@dataclass(slots=True)
class OARequestSession:
    token: str
    identity: OAUserIdentity
    allowed: bool
    access_tier: AccessTier
    can_access_app: bool
    can_mutate_data: bool
    can_admin_access: bool


def actor_id_for_session(session: OARequestSession, *, fallback: str = "system") -> str:
    identity = session.identity
    actor_id = str(identity.user_id or identity.username or fallback).strip()
    return actor_id or fallback


def tenant_id_for_session(_: OARequestSession, *, fallback: str = "default") -> str:
    tenant_id = str(fallback or "default").strip()
    return tenant_id or "default"


def assert_safe_auth_runtime_configuration() -> None:
    retired_keys = [key for key in RETIRED_AUTH_ENV_KEYS if key in os.environ]
    if retired_keys:
        raise AuthRuntimeConfigurationError(
            "Retired authentication environment variables must be absent: "
            + ", ".join(retired_keys)
        )


def get_header(headers: Mapping[str, str] | None, name: str) -> str | None:
    if headers is None:
        return None
    target = name.lower()
    for key, value in headers.items():
        if key.lower() == target:
            return value
    return None


def extract_oa_token(headers: Mapping[str, str] | None) -> str | None:
    authorization = get_header(headers, AUTHORIZATION_HEADER)
    if authorization:
        normalized = authorization.strip()
        if normalized.lower().startswith(BEARER_PREFIX):
            token = normalized[len(BEARER_PREFIX) :].strip()
            if token:
                return token

    cookie_header = get_header(headers, COOKIE_HEADER)
    if not cookie_header:
        return None

    cookie = SimpleCookie()
    cookie.load(cookie_header)
    morsel = cookie.get(OA_TOKEN_COOKIE_NAME)
    if morsel is None:
        return None
    token = morsel.value.strip()
    return token or None


def resolve_oa_request_session(
    headers: Mapping[str, str] | None,
    *,
    identity_service: OAIdentityService,
    access_control_service: AccessControlService,
) -> OARequestSession:
    token = extract_oa_token(headers)
    if token is None:
        raise UnauthorizedOASessionError("缺少 OA 登录态，请从 OA 系统进入。")

    identity = identity_service.resolve_identity(token)
    decision = access_control_service.evaluate(identity)
    return OARequestSession(
        token=token,
        identity=identity,
        allowed=decision.allowed,
        access_tier=decision.access_tier,
        can_access_app=decision.can_access_app,
        can_mutate_data=decision.can_mutate_data,
        can_admin_access=decision.can_admin_access,
    )
