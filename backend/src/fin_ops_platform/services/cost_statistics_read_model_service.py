from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from threading import RLock
from typing import Any


COST_STATISTICS_READ_MODEL_SCHEMA_VERSION = "2026-05-cost-statistics-explorer-v1"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}


class CostStatisticsReadModelService:
    def __init__(self, *, read_models: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._read_models = self._normalize_read_models(read_models or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "CostStatisticsReadModelService":
        if not snapshot:
            return cls()
        read_models = snapshot.get("read_models")
        return cls(read_models=read_models if isinstance(read_models, dict) else {})

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            return {"read_models": deepcopy(self._read_models)}

    def snapshot_scope_keys(self, scope_keys: list[str]) -> dict[str, Any]:
        normalized_scope_keys = {
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        }
        with self._lock:
            return {
                "read_models": {
                    scope_key: deepcopy(read_model)
                    for scope_key, read_model in self._read_models.items()
                    if scope_key in normalized_scope_keys
                }
            }

    @classmethod
    def scope_key(cls, month: str, project_scope: str) -> str:
        resolved_month = cls._normalize_month(month)
        resolved_project_scope = cls._normalize_project_scope(project_scope)
        return f"{resolved_project_scope}:{resolved_month}"

    def get_read_model(self, month: str, project_scope: str) -> dict[str, Any] | None:
        return self.get_read_model_by_scope_key(self.scope_key(month, project_scope))

    def get_read_model_by_scope_key(self, scope_key: str) -> dict[str, Any] | None:
        try:
            resolved_scope_key, _, _ = self._parse_scope_key(scope_key)
        except ValueError:
            return None
        with self._lock:
            read_model = self._read_models.get(resolved_scope_key)
            if not isinstance(read_model, dict):
                return None
            return deepcopy(read_model)

    def upsert_read_model(
        self,
        month: str,
        project_scope: str,
        payload: dict[str, Any],
        *,
        generated_at: str | None = None,
        source_scope_keys: list[str] | None = None,
        cache_status: str = "ready",
    ) -> dict[str, Any]:
        resolved_scope_key = self.scope_key(month, project_scope)
        resolved_project_scope, resolved_month = resolved_scope_key.split(":", 1)
        normalized = self._normalize_read_model(
            {
                "scope_key": resolved_scope_key,
                "scope_type": self._scope_type_for_month(resolved_month),
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "month": resolved_month,
                "project_scope": resolved_project_scope,
                "generated_at": generated_at or self._timestamp(),
                "cache_status": str(cache_status or "ready"),
                "entry_count": self._entry_count(payload),
                "payload": deepcopy(payload if isinstance(payload, dict) else {}),
                "source_scope_keys": self._normalize_source_scope_keys(source_scope_keys),
            },
            fallback_scope_key=resolved_scope_key,
        )
        with self._lock:
            self._read_models[resolved_scope_key] = normalized
            return deepcopy(normalized)

    def delete_read_model(self, month: str, project_scope: str) -> bool:
        return self.delete_read_model_by_scope_key(self.scope_key(month, project_scope))

    def delete_read_model_by_scope_key(self, scope_key: str) -> bool:
        try:
            resolved_scope_key, _, _ = self._parse_scope_key(scope_key)
        except ValueError:
            return False
        with self._lock:
            return self._read_models.pop(resolved_scope_key, None) is not None

    def delete_scope_keys(self, scope_keys: list[str]) -> list[str]:
        deleted: list[str] = []
        for scope_key in list(scope_keys or []):
            try:
                resolved_scope_key, _, _ = self._parse_scope_key(scope_key)
            except ValueError:
                continue
            with self._lock:
                if self._read_models.pop(resolved_scope_key, None) is not None:
                    deleted.append(resolved_scope_key)
        return deleted

    def invalidate_months(
        self,
        months: list[str],
        *,
        project_scopes: list[str] | None = None,
        include_all: bool = True,
    ) -> list[str]:
        resolved_project_scopes = self._normalize_project_scopes(project_scopes)
        month_targets: list[str] = []
        for month in list(months or []):
            if not str(month or "").strip():
                continue
            resolved_month = self._normalize_month(month)
            if resolved_month == "all":
                continue
            if resolved_month not in month_targets:
                month_targets.append(resolved_month)

        scope_keys: list[str] = []
        for month in month_targets:
            for project_scope in resolved_project_scopes:
                scope_keys.append(self.scope_key(month, project_scope))
        if include_all:
            for project_scope in resolved_project_scopes:
                scope_keys.append(self.scope_key("all", project_scope))
        return self.delete_scope_keys(scope_keys)

    def clear(self) -> list[str]:
        with self._lock:
            deleted = list(self._read_models.keys())
            self._read_models.clear()
            return deleted

    def list_scope_keys(self) -> list[str]:
        with self._lock:
            return list(self._read_models.keys())

    def list_read_model_metadata(self) -> list[dict[str, Any]]:
        with self._lock:
            return [
                {
                    key: deepcopy(read_model.get(key))
                    for key in (
                        "scope_key",
                        "scope_type",
                        "schema_version",
                        "month",
                        "project_scope",
                        "generated_at",
                        "cache_status",
                        "entry_count",
                        "source_scope_keys",
                    )
                }
                for read_model in self._read_models.values()
            ]

    @classmethod
    def _normalize_read_models(cls, read_models: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for scope_key, read_model in read_models.items():
            if not isinstance(read_model, dict):
                continue
            if read_model.get("schema_version") != COST_STATISTICS_READ_MODEL_SCHEMA_VERSION:
                continue
            try:
                normalized_read_model = cls._normalize_read_model(read_model, fallback_scope_key=str(scope_key))
            except ValueError:
                continue
            normalized[str(normalized_read_model["scope_key"])] = normalized_read_model
        return normalized

    @classmethod
    def _normalize_read_model(cls, read_model: dict[str, Any], *, fallback_scope_key: str) -> dict[str, Any]:
        resolved_scope_key, project_scope, month = cls._parse_scope_key(read_model.get("scope_key") or fallback_scope_key)
        payload = read_model.get("payload")
        normalized_payload = deepcopy(payload if isinstance(payload, dict) else {})
        return {
            "scope_key": resolved_scope_key,
            "scope_type": cls._scope_type_for_month(month),
            "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "month": month,
            "project_scope": project_scope,
            "generated_at": str(read_model.get("generated_at") or cls._timestamp()),
            "cache_status": str(read_model.get("cache_status") or "ready"),
            "entry_count": cls._entry_count(normalized_payload),
            "payload": normalized_payload,
            "source_scope_keys": cls._normalize_source_scope_keys(read_model.get("source_scope_keys")),
        }

    @classmethod
    def _parse_scope_key(cls, scope_key: Any) -> tuple[str, str, str]:
        raw_scope_key = str(scope_key or "").strip()
        if not raw_scope_key or ":" not in raw_scope_key:
            raise ValueError("cost statistics read model scope_key must use project_scope:month.")
        project_scope, month = raw_scope_key.split(":", 1)
        resolved_project_scope = cls._normalize_project_scope(project_scope)
        resolved_month = cls._normalize_month(month)
        return f"{resolved_project_scope}:{resolved_month}", resolved_project_scope, resolved_month

    @staticmethod
    def _normalize_month(month: Any) -> str:
        resolved_month = str(month or "").strip()
        if not resolved_month:
            raise ValueError("month is required for cost statistics read model.")
        if resolved_month == "all" or MONTH_RE.match(resolved_month):
            return resolved_month
        raise ValueError("month must be YYYY-MM or all for cost statistics read model.")

    @staticmethod
    def _normalize_project_scope(project_scope: Any) -> str:
        resolved_project_scope = str(project_scope or "").strip()
        if not resolved_project_scope:
            raise ValueError("project_scope is required for cost statistics read model.")
        if resolved_project_scope not in PROJECT_SCOPES:
            raise ValueError("project_scope must be active or all for cost statistics read model.")
        return resolved_project_scope

    @staticmethod
    def _normalize_project_scopes(project_scopes: list[str] | None) -> list[str]:
        if project_scopes is None:
            return ["active", "all"]
        resolved: list[str] = []
        for project_scope in list(project_scopes or []):
            normalized = CostStatisticsReadModelService._normalize_project_scope(project_scope)
            if normalized not in resolved:
                resolved.append(normalized)
        return resolved or ["active", "all"]

    @staticmethod
    def _normalize_source_scope_keys(source_scope_keys: Any) -> list[str]:
        normalized: list[str] = []
        if not isinstance(source_scope_keys, list):
            return normalized
        for scope_key in source_scope_keys:
            resolved_scope_key = str(scope_key or "").strip()
            if resolved_scope_key and resolved_scope_key not in normalized:
                normalized.append(resolved_scope_key)
        return normalized

    @staticmethod
    def _scope_type_for_month(month: str) -> str:
        return "all_time" if month == "all" else "month"

    @staticmethod
    def _entry_count(payload: Any) -> int:
        if not isinstance(payload, dict):
            return 0
        summary = payload.get("summary")
        if isinstance(summary, dict):
            try:
                return int(summary.get("transaction_count"))
            except (TypeError, ValueError):
                pass
        time_rows = payload.get("time_rows")
        return len(time_rows) if isinstance(time_rows, list) else 0

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
