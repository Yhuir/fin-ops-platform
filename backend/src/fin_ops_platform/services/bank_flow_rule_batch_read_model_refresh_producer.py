from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.search_service import MONTH_RE as SEARCH_MONTH_RE


BANK_FLOW_RULE_BATCH_SCOPE_TYPE = "bank_flow_rule_batch"


class BankFlowRuleBatchReadModelRefreshProducer:
    def __init__(self, *, refresh_gateway_provider: Callable[[], Any]) -> None:
        self._refresh_gateway_provider = refresh_gateway_provider

    def enqueue(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return bool(self.enqueue_scope_keys(scope_keys, reason=reason, metadata=metadata))

    def enqueue_scope_keys(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        refresh_gateway = self._refresh_gateway_provider()
        if not refresh_gateway.can_enqueue():
            return []
        return list(
            refresh_gateway.enqueue_many(
                BANK_FLOW_RULE_BATCH_SCOPE_TYPE,
                self.normalize_scope_keys(scope_keys),
                reason=reason,
                metadata=metadata,
            )
            or []
        )

    @staticmethod
    def normalize_scope_keys(scope_keys: list[str]) -> list[str]:
        normalized: list[str] = []
        for item in list(scope_keys or []):
            scope_key = str(item).strip()
            if scope_key == "all" or SEARCH_MONTH_RE.match(scope_key):
                normalized.append(scope_key)
        return list(dict.fromkeys(normalized or ["all"]))
