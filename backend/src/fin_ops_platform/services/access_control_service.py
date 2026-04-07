from __future__ import annotations

from dataclasses import dataclass
import os
from typing import Callable, Iterable

from fin_ops_platform.services.oa_identity_service import OAUserIdentity


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

    @classmethod
    def from_environment(
        cls,
        *,
        dynamic_allowed_usernames_provider: Callable[[], list[str]] | None = None,
    ) -> "AccessControlService":
        required_permission = os.getenv("FIN_OPS_OA_REQUIRED_PERMISSION", "finops:app:view").strip() or "finops:app:view"
        return cls(
            required_permission=required_permission,
            allowed_usernames=_parse_csv_environment("FIN_OPS_ALLOWED_USERNAMES"),
            allowed_roles=_parse_csv_environment("FIN_OPS_ALLOWED_ROLES"),
            dynamic_allowed_usernames_provider=dynamic_allowed_usernames_provider,
        )

    def is_allowed(self, identity: OAUserIdentity) -> bool:
        permissions = set(_normalize_values(identity.permissions))
        roles = set(_normalize_values(identity.roles))
        username = identity.username.strip()
        allowed_usernames = set(self.allowed_usernames or [])
        if self.dynamic_allowed_usernames_provider is not None:
            allowed_usernames.update(_normalize_values(self.dynamic_allowed_usernames_provider()))

        if self.required_permission and self.required_permission in permissions:
            return True
        if allowed_usernames and username in allowed_usernames:
            return True
        if self.allowed_roles and roles.intersection(self.allowed_roles):
            return True
        return False
