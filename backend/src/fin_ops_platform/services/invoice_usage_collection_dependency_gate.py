from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    invoice_relation_dependency_status,
)
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
)


class InvoiceUsageCollectionDependencyGate:
    """Resolve exact input/output invoice page dependencies before payload SQL."""

    def __init__(
        self,
        *,
        scope_state_loader: Callable[..., dict[str, object]] | None,
        relation_reader: Any | None,
        expected_source_versions: Callable[..., dict[str, object]],
        requires_sql_runtime: Callable[[], bool],
        context: str,
    ) -> None:
        self._scope_state_loader = scope_state_loader
        self._relation_reader = relation_reader
        self._expected_source_versions = expected_source_versions
        self._requires_sql_runtime = requires_sql_runtime
        self._context = str(context or "invoice_usage_collection").strip()

    def resolve(
        self,
        scope_key: str,
        *,
        reason: str,
    ) -> dict[str, object]:
        if not self._requires_sql_runtime():
            return self._result(status="fresh")
        relation_loader = getattr(
            self._relation_reader,
            "source_versions_for_scopes",
            None,
        )
        if not callable(self._scope_state_loader) or not callable(relation_loader):
            return self._result(
                status="unavailable",
                blocking_scope_keys=(
                    [scope_key]
                    if self.is_concrete_scope_key(scope_key)
                    else []
                ),
                stale_reasons=["workbench_relation_dependency_port_unavailable"],
            )
        scope_state = self._scope_state_loader(
            scope_key=scope_key,
            tenant_id="default",
        )
        if not isinstance(scope_state, dict):
            return self._result(
                status="unavailable",
                blocking_scope_keys=(
                    [scope_key]
                    if self.is_concrete_scope_key(scope_key)
                    else []
                ),
                stale_reasons=[
                    f"{self._context}_scope_state_unavailable"
                ],
            )
        scope_keys = self.concrete_scope_keys(
            list(scope_state.get("scope_keys") or [])
        )
        if not scope_keys:
            return self._result(status="fresh")
        relation_state = relation_loader(
            scope_keys,
            require_fresh=True,
            reason=reason,
        )
        if not isinstance(relation_state, dict):
            relation_state = {
                "status": "unavailable",
                "refresh_scope_keys": scope_keys,
                "stale_reasons": ["workbench_relation_status_unavailable"],
            }
        return invoice_relation_dependency_status(
            scope_state=scope_state,
            relation_state=relation_state,
            base_source_versions=require_expected_source_versions(
                self._expected_source_versions(scope_key="all"),
                context=self._context,
            ),
        )

    @staticmethod
    def is_concrete_scope_key(scope_key: object) -> bool:
        normalized = str(scope_key or "").strip()
        return len(normalized) == 7 and normalized[4] == "-"

    @classmethod
    def concrete_scope_keys(cls, scope_keys: list[object]) -> list[str]:
        return list(
            dict.fromkeys(
                str(scope_key).strip()
                for scope_key in list(scope_keys or [])
                if cls.is_concrete_scope_key(scope_key)
            )
        )

    @staticmethod
    def _result(
        *,
        status: str,
        scope_keys: list[str] | None = None,
        blocking_scope_keys: list[str] | None = None,
        refresh_scope_keys: list[str] | None = None,
        stale_reasons: list[str] | None = None,
    ) -> dict[str, object]:
        blocking = list(blocking_scope_keys or [])
        return {
            "status": status,
            "scope_keys": list(scope_keys or []),
            "blocking_scope_keys": blocking,
            "refresh_scope_keys": (
                list(refresh_scope_keys)
                if refresh_scope_keys is not None
                else blocking
            ),
            "stale_reasons": list(stale_reasons or []),
        }
