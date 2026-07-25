from __future__ import annotations

import hashlib
import json
import os
import re
from typing import Any

from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
)
from fin_ops_platform.services.read_model_freshness import normalize_source_versions


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
PROJECT_SCOPE_ORDER = ("active", "all")


class CostStatisticsRuntimeService:
    def __init__(
        self,
        *,
        queue_repository: Any | None = None,
    ) -> None:
        self._queue_repository = queue_repository

    @staticmethod
    def request_scope_key(month: str, project_scope: str) -> str:
        return f"{str(project_scope or 'active').strip().lower()}:{str(month or 'all').strip() or 'all'}"

    def page_redis_cache_key(
        self,
        scope_key: str,
        query_fingerprint: str,
        *,
        source_versions: dict[str, Any] | None = None,
    ) -> str:
        return self.read_model_redis_cache_key(
            f"cost_statistics:page:{query_fingerprint}",
            scope_key,
            schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            source_versions=source_versions,
        )

    @staticmethod
    def read_model_redis_cache_key(
        prefix: str,
        scope_key: str,
        *,
        schema_version: str,
        source_versions: dict[str, Any] | None,
    ) -> str:
        normalized_source_versions = normalize_source_versions(source_versions)
        source_hash = hashlib.sha256(
            json.dumps(
                normalized_source_versions or {"source_versions": "unknown"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return f"{prefix}:{scope_key}:schema:{schema_version}:sources:{source_hash}"

    @staticmethod
    def redis_ttl_seconds() -> int:
        raw_value = os.getenv("FIN_OPS_COST_STATISTICS_REDIS_TTL_SECONDS", "60").strip()
        try:
            return min(120, max(1, int(raw_value)))
        except ValueError:
            return 60

    def enqueue_read_model_refresh(
        self,
        scope_key: str,
        *,
        reason: str,
        force_refresh: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> bool:
        return bool(
            self.enqueue_read_model_refreshes(
                [scope_key],
                reason=reason,
                force_refresh=force_refresh,
                metadata=metadata,
            )
        )

    def enqueue_read_model_refreshes(
        self,
        scope_keys: list[str],
        *,
        reason: str,
        force_refresh: bool = False,
        metadata: dict[str, object] | None = None,
    ) -> list[str]:
        from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway

        gateway = ReadModelRefreshGateway(queue_repository=self._queue_repository)
        if not gateway.can_enqueue():
            return []
        refresh_metadata = dict(metadata or {})
        if force_refresh:
            refresh_metadata["force_refresh"] = True
        return gateway.enqueue_many(
            "cost_statistics",
            scope_keys,
            reason=reason,
            metadata=refresh_metadata or None,
        )

    @staticmethod
    def months_from_workbench_scope_keys(scope_keys: list[str]) -> set[str]:
        months: set[str] = set()
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key).strip()
            if not scope_key:
                continue
            for part in reversed(scope_key.split(":")):
                normalized_part = str(part).strip()
                if normalized_part == "all" or MONTH_RE.match(normalized_part):
                    months.add(normalized_part)
                    break
        return months

    def invalidate_read_models(self) -> list[str]:
        return self._enqueue_invalidation_scopes(
            ["active:all", "all:all"],
            reason="cost_statistics_read_model_invalidated",
        )

    def invalidate_read_model_scopes(
        self,
        scope_keys: list[str],
        *,
        reason: str = "",
    ) -> list[str]:
        target_scope_keys = self.refresh_scope_keys_from_scope_keys(scope_keys)
        return self._enqueue_invalidation_scopes(
            target_scope_keys,
            reason=reason or "cost_statistics_scope_invalidated",
        )

    def _enqueue_invalidation_scopes(self, scope_keys: list[str], *, reason: str) -> list[str]:
        return [
            scope_key
            for scope_key in self.normalize_scope_keys(scope_keys)
            if self.enqueue_read_model_refresh(
                scope_key,
                reason=reason,
                force_refresh=scope_key.endswith(":all"),
            )
        ]

    def rebuild_read_model_scope(self, scope_key: str) -> dict[str, Any]:
        parsed = self.parse_scope_key(scope_key)
        if parsed is None:
            raise ValueError("cost statistics read model scope_key must be project_scope:month.")
        raise RuntimeError("cost statistics read model refresh must use CostStatisticsReadModelRefreshService.")

    def normalize_scope_keys(self, scope_keys: list[str]) -> list[str]:
        normalized: list[str] = []
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key or "").strip()
            parsed = self.parse_scope_key(scope_key)
            if parsed is None:
                continue
            project_scope, month = parsed
            resolved_scope_key = self.request_scope_key(month, project_scope)
            if resolved_scope_key not in normalized:
                normalized.append(resolved_scope_key)
        return normalized

    @classmethod
    def refresh_scope_keys_from_scope_keys(cls, scope_keys: list[str]) -> list[str]:
        raw_scope_keys = [
            str(scope_key or "").strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key or "").strip()
        ]
        if not raw_scope_keys:
            return []
        parsed_scope_keys: list[str] = []
        all_parseable = True
        for scope_key in raw_scope_keys:
            parsed = cls.parse_scope_key(scope_key)
            if parsed is None:
                all_parseable = False
                break
            project_scope, month = parsed
            resolved_scope_key = cls.request_scope_key(month, project_scope)
            if resolved_scope_key not in parsed_scope_keys:
                parsed_scope_keys.append(resolved_scope_key)
        if all_parseable:
            return parsed_scope_keys

        months = cls.months_from_workbench_scope_keys(raw_scope_keys)
        target_months = sorted(month for month in months if month != "all")
        if "all" in months:
            target_months.append("all")
        return [
            cls.request_scope_key(month, project_scope)
            for month in target_months
            for project_scope in PROJECT_SCOPE_ORDER
        ]

    @staticmethod
    def parse_scope_key(scope_key: str) -> tuple[str, str] | None:
        raw_scope_key = str(scope_key or "").strip()
        if ":" not in raw_scope_key:
            return None
        project_scope, month = raw_scope_key.split(":", 1)
        project_scope = project_scope.strip()
        month = month.strip()
        if project_scope not in PROJECT_SCOPES:
            return None
        if month != "all" and not MONTH_RE.match(month):
            return None
        return project_scope, month
