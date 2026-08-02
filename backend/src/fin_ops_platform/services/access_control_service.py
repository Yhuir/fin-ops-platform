from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable, Literal

from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.state_store_protocol import (
    PROTECTED_ADMIN_USERNAME,
    settings_access_control_from_payload,
    settings_username_comparison_key,
)


DEFAULT_ADMIN_USERNAME = PROTECTED_ADMIN_USERNAME
AccessTier = Literal["denied", "read_export_only", "full_access", "admin"]
logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AccessControlService:
    access_control_snapshot_provider: Callable[[], dict[str, Any]] | None = None

    @classmethod
    def from_environment(
        cls,
        *,
        access_control_snapshot_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> "AccessControlService":
        return cls(access_control_snapshot_provider=access_control_snapshot_provider)

    def is_allowed(self, identity: OAUserIdentity) -> bool:
        return self.evaluate(identity).allowed

    def evaluate(self, identity: OAUserIdentity) -> "AccessDecision":
        username = identity.username.strip()

        if username == PROTECTED_ADMIN_USERNAME:
            return AccessDecision(
                access_tier="admin",
                can_access_app=True,
                can_mutate_data=True,
                can_admin_access=True,
            )

        snapshot = self._load_access_control_snapshot()
        if snapshot is None:
            return AccessDecision(
                access_tier="denied",
                can_access_app=False,
                can_mutate_data=False,
                can_admin_access=False,
            )

        try:
            username_key = settings_username_comparison_key(username)
        except ValueError:
            return AccessDecision(
                access_tier="denied",
                can_access_app=False,
                can_mutate_data=False,
                can_admin_access=False,
            )

        if username_key in {
            settings_username_comparison_key(name) for name in snapshot["readonly_export_usernames"]
        }:
            return AccessDecision(
                access_tier="read_export_only",
                can_access_app=True,
                can_mutate_data=False,
                can_admin_access=False,
            )

        if username_key in {
            settings_username_comparison_key(name) for name in snapshot["full_access_usernames"]
        }:
            return AccessDecision(
                access_tier="full_access",
                can_access_app=True,
                can_mutate_data=True,
                can_admin_access=False,
            )
        return AccessDecision(
            access_tier="denied",
            can_access_app=False,
            can_mutate_data=False,
            can_admin_access=False,
        )

    def _load_access_control_snapshot(self) -> dict[str, Any] | None:
        provider = self.access_control_snapshot_provider
        if provider is None:
            return None
        try:
            return settings_access_control_from_payload(provider())
        except Exception:
            logger.warning("Access control snapshot provider failed; access denied.")
            return None


@dataclass(slots=True, frozen=True)
class AccessDecision:
    access_tier: AccessTier
    can_access_app: bool
    can_mutate_data: bool
    can_admin_access: bool

    @property
    def allowed(self) -> bool:
        return self.can_access_app
