from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Iterable, Literal

from fin_ops_platform.services.oa_identity_service import OAUserIdentity


DEFAULT_ADMIN_USERNAME = "YNSYLP005"
AccessTier = Literal["denied", "read_export_only", "full_access", "admin"]


def _normalize_values(values: Iterable[str]) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for value in values:
        item = str(value).strip()
        if not item or item in seen:
            continue
        normalized.append(item)
        seen.add(item)
    return normalized


def _parse_csv_environment(name: str) -> list[str]:
    raw = os.getenv(name, "")
    if not raw.strip():
        return []
    return _normalize_values(part.strip() for part in raw.split(","))


@dataclass(slots=True)
class AccessControlService:
    required_permission: str = "finops:app:view"
    allowed_usernames: list[str] | None = None
    allowed_roles: list[str] | None = None
    dynamic_allowed_usernames_provider: Callable[[], list[str]] | None = None
    readonly_export_usernames: list[str] | None = None
    admin_usernames: list[str] | None = None
    dynamic_readonly_export_usernames_provider: Callable[[], list[str]] | None = None
    dynamic_admin_usernames_provider: Callable[[], list[str]] | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        dynamic_allowed_usernames_provider: Callable[[], list[str]] | None = None,
        dynamic_readonly_export_usernames_provider: Callable[[], list[str]] | None = None,
        dynamic_admin_usernames_provider: Callable[[], list[str]] | None = None,
    ) -> "AccessControlService":
        required_permission = os.getenv("FIN_OPS_OA_REQUIRED_PERMISSION", "finops:app:view").strip() or "finops:app:view"
        return cls(
            required_permission=required_permission,
            allowed_usernames=_parse_csv_environment("FIN_OPS_ALLOWED_USERNAMES"),
            allowed_roles=_parse_csv_environment("FIN_OPS_ALLOWED_ROLES"),
            dynamic_allowed_usernames_provider=dynamic_allowed_usernames_provider,
            readonly_export_usernames=_parse_csv_environment("FIN_OPS_READONLY_EXPORT_USERNAMES"),
            admin_usernames=_parse_csv_environment("FIN_OPS_ADMIN_USERNAMES"),
            dynamic_readonly_export_usernames_provider=dynamic_readonly_export_usernames_provider,
            dynamic_admin_usernames_provider=dynamic_admin_usernames_provider,
        )

    def is_allowed(self, identity: OAUserIdentity) -> bool:
        return self.evaluate(identity).allowed

    def evaluate(self, identity: OAUserIdentity) -> "AccessDecision":
        permissions = set(_normalize_values(identity.permissions))
        roles = set(_normalize_values(identity.roles))
        username = identity.username.strip()

        allowed_usernames = set(_normalize_values(self.allowed_usernames or []))
        if self.dynamic_allowed_usernames_provider is not None:
            allowed_usernames.update(_normalize_values(self.dynamic_allowed_usernames_provider()))
        readonly_export_usernames = set(_normalize_values(self.readonly_export_usernames or []))
        if self.dynamic_readonly_export_usernames_provider is not None:
            readonly_export_usernames.update(_normalize_values(self.dynamic_readonly_export_usernames_provider()))
        admin_usernames = {DEFAULT_ADMIN_USERNAME}
        admin_usernames.update(_normalize_values(self.admin_usernames or []))
        if self.dynamic_admin_usernames_provider is not None:
            admin_usernames.update(_normalize_values(self.dynamic_admin_usernames_provider()))

        if self.required_permission and self.required_permission in permissions:
            can_access_app = True
        elif allowed_usernames and username in allowed_usernames:
            can_access_app = True
        elif self.allowed_roles and roles.intersection(self.allowed_roles):
            can_access_app = True
        else:
            can_access_app = False

        if not can_access_app:
            return AccessDecision(
                access_tier="denied",
                can_access_app=False,
                can_mutate_data=False,
                can_admin_access=False,
            )

        if username in admin_usernames:
            return AccessDecision(
                access_tier="admin",
                can_access_app=True,
                can_mutate_data=True,
                can_admin_access=True,
            )

        if username in readonly_export_usernames:
            return AccessDecision(
                access_tier="read_export_only",
                can_access_app=True,
                can_mutate_data=False,
                can_admin_access=False,
            )

        return AccessDecision(
            access_tier="full_access",
            can_access_app=True,
            can_mutate_data=True,
            can_admin_access=False,
        )


@dataclass(slots=True, frozen=True)
class AccessDecision:
    access_tier: AccessTier
    can_access_app: bool
    can_mutate_data: bool
    can_admin_access: bool

    @property
    def allowed(self) -> bool:
        return self.can_access_app
