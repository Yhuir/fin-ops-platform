from __future__ import annotations

from dataclasses import dataclass
import logging
from typing import Any, Callable

from fin_ops_platform.services.oa_identity_service import OAUserIdentity
from fin_ops_platform.services.state_store_protocol import (
    PROTECTED_ADMIN_USERNAME,
    settings_access_control_from_payload,
    settings_username_comparison_key,
)


DEFAULT_ADMIN_USERNAME = PROTECTED_ADMIN_USERNAME
ASSIGNABLE_PAGE_KEYS = frozenset(
    {
        "reconciliation-workbench",
        "cost-statistics",
        "bank-details",
        "oa-pending-payments",
        "bank-flow-rule-batches",
        "batch-accounting",
        "turnover-ledger",
        "etc-tickets",
        "tax-offset",
        "pending-invoices",
        "input-invoice-usage",
        "output-invoice-collections",
        "settings",
        "app-health-operations",
        "imports.bank-transactions",
        "imports.invoices",
        "imports.etc-invoices",
    }
)
ADMIN_ONLY_PAGE_KEYS = frozenset({"operation-history"})
ALL_PAGE_KEYS = ASSIGNABLE_PAGE_KEYS | ADMIN_ONLY_PAGE_KEYS
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
                can_access_app=True,
                can_admin_access=True,
                allowed_page_keys=ALL_PAGE_KEYS,
            )

        snapshot = self._load_access_control_snapshot()
        if snapshot is None:
            return AccessDecision(
                can_access_app=False,
                can_admin_access=False,
                allowed_page_keys=frozenset(),
            )

        try:
            username_key = settings_username_comparison_key(username)
        except ValueError:
            return AccessDecision(
                can_access_app=False,
                can_admin_access=False,
                allowed_page_keys=frozenset(),
            )
        for account in snapshot["page_access_accounts"]:
            if settings_username_comparison_key(account["username"]) != username_key:
                continue
            allowed_page_keys = frozenset(account["page_keys"])
            return AccessDecision(
                can_access_app=bool(allowed_page_keys),
                can_admin_access=False,
                allowed_page_keys=allowed_page_keys,
            )
        return AccessDecision(
            can_access_app=False,
            can_admin_access=False,
            allowed_page_keys=frozenset(),
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
    can_access_app: bool
    can_admin_access: bool
    allowed_page_keys: frozenset[str]

    @property
    def allowed(self) -> bool:
        return self.can_access_app

    def can_access_page(self, page_key: str) -> bool:
        return self.can_admin_access or page_key in self.allowed_page_keys
