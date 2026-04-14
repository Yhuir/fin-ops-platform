from __future__ import annotations

from dataclasses import dataclass
from http.cookies import SimpleCookie
import os
import sys
from typing import Mapping

from fin_ops_platform.services.access_control_service import AccessControlService, AccessTier
from fin_ops_platform.services.oa_identity_service import OAIdentityService, OAUserIdentity


AUTHORIZATION_HEADER = "authorization"
COOKIE_HEADER = "cookie"
OA_TOKEN_COOKIE_NAME = "Admin-Token"
BEARER_PREFIX = "bearer "


class OAAuthError(RuntimeError):
    pass


class UnauthorizedOASessionError(OAAuthError):
    pass


class ForbiddenOAAccessError(OAAuthError):
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


def _should_enable_default_test_auth() -> bool:
    override = os.getenv("FIN_OPS_TEST_DEFAULT_AUTH")
    if override is not None:
        return override.strip() == "1"
    return "unittest" in sys.modules


def _should_enable_local_dev_auth() -> bool:
    override = os.getenv("FIN_OPS_DEV_ALLOW_LOCAL_SESSION")
    return override is not None and override.strip() == "1"


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
        if _should_enable_local_dev_auth():
            dev_username = os.getenv("FIN_OPS_DEV_USERNAME", "local_finops_admin").strip() or "local_finops_admin"
            local_access_control_service = AccessControlService(
                required_permission=access_control_service.required_permission,
                allowed_usernames=access_control_service.allowed_usernames,
                allowed_roles=access_control_service.allowed_roles,
                dynamic_allowed_usernames_provider=access_control_service.dynamic_allowed_usernames_provider,
                readonly_export_usernames=access_control_service.readonly_export_usernames,
                admin_usernames=[*(access_control_service.admin_usernames or []), dev_username],
                dynamic_readonly_export_usernames_provider=access_control_service.dynamic_readonly_export_usernames_provider,
                dynamic_admin_usernames_provider=access_control_service.dynamic_admin_usernames_provider,
            )
            synthetic_identity = OAUserIdentity(
                user_id="local-dev-user-id",
                username=dev_username,
                nickname="本地开发用户",
                display_name="本地开发用户",
                roles=local_access_control_service.allowed_roles or ["finance"],
                permissions=[local_access_control_service.required_permission],
            )
            decision = local_access_control_service.evaluate(synthetic_identity)
            return OARequestSession(
                token="local-dev-token",
                identity=synthetic_identity,
                allowed=decision.allowed,
                access_tier=decision.access_tier,
                can_access_app=decision.can_access_app,
                can_mutate_data=decision.can_mutate_data,
                can_admin_access=decision.can_admin_access,
            )
        if _should_enable_default_test_auth():
            synthetic_identity = OAUserIdentity(
                user_id="test-user-id",
                username="test_finops_user",
                nickname="测试用户",
                display_name="测试用户",
                roles=access_control_service.allowed_roles or ["finance"],
                permissions=[access_control_service.required_permission],
            )
            decision = access_control_service.evaluate(synthetic_identity)
            return OARequestSession(
                token="test-default-token",
                identity=synthetic_identity,
                allowed=decision.allowed,
                access_tier=decision.access_tier,
                can_access_app=decision.can_access_app,
                can_mutate_data=decision.can_mutate_data,
                can_admin_access=decision.can_admin_access,
            )
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
