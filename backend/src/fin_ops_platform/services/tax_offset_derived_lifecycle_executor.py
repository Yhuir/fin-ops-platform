from __future__ import annotations

import re
from typing import Callable

from fin_ops_platform.services.tax_offset_runtime_service import TaxOffsetRuntimeService


SEARCH_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class TaxOffsetDerivedLifecycleExecutor:
    def __init__(
        self,
        *,
        runtime_service: TaxOffsetRuntimeService,
        clear_month_cache: Callable[[list[str] | None], None],
    ) -> None:
        self._runtime_service = runtime_service
        self._clear_month_cache = clear_month_cache

    def execute_read_model(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        if "all" in scope_keys:
            deleted_scope_keys = self._runtime_service.invalidate_read_models()
        else:
            deleted_scope_keys = self._runtime_service.invalidate_read_model_scopes(
                scope_keys,
                reason=str(domain_plan.get("reason") or "derived_lifecycle_tax_offset"),
            )
        return {
            "deleted_counts": {"tax_offset_cache_scopes": len(deleted_scope_keys)},
            "invalidated_scopes": deleted_scope_keys,
            "enqueued_jobs": ["tax_offset_cache_warmup"] if deleted_scope_keys else [],
        }

    def execute_month_cache(self, domain_plan: dict[str, object]) -> dict[str, object]:
        scope_keys = self._domain_plan_scope_keys(domain_plan)
        months = self._months_from_lifecycle_scope_keys(scope_keys)
        self._clear_month_cache(None if "all" in scope_keys else months)
        return {
            "deleted_counts": {"tax_offset_month_cache": len(months) if months else int("all" in scope_keys)},
            "invalidated_scopes": months or (["all"] if "all" in scope_keys else []),
        }

    @staticmethod
    def _domain_plan_scope_keys(domain_plan: dict[str, object]) -> list[str]:
        return [
            str(scope_key).strip()
            for scope_key in list(domain_plan.get("scope_keys") or [])
            if str(scope_key).strip()
        ]

    @staticmethod
    def _months_from_lifecycle_scope_keys(scope_keys: list[str]) -> list[str]:
        return sorted(
            {
                part
                for scope_key in list(scope_keys or [])
                for part in str(scope_key).split(":")
                if SEARCH_MONTH_RE.match(str(part).strip())
            }
        )
