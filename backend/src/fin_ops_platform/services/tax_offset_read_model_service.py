from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import re
from threading import RLock
from typing import Any


TAX_OFFSET_READ_MODEL_SCHEMA_VERSION = "2026-05-tax-offset-month-v1"
MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class TaxOffsetReadModelService:
    def __init__(self, *, read_models: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._read_models = self._normalize_read_models(read_models or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "TaxOffsetReadModelService":
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
    def scope_key(cls, month: str) -> str:
        return cls._normalize_month(month)

    def get_read_model(self, month: str) -> dict[str, Any] | None:
        return self.get_read_model_by_scope_key(self.scope_key(month))

    def get_read_model_by_scope_key(self, scope_key: str) -> dict[str, Any] | None:
        try:
            resolved_scope_key = self._parse_scope_key(scope_key)
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
        payload: dict[str, Any],
        *,
        generated_at: str | None = None,
        source_scope_keys: list[str] | None = None,
        cache_status: str = "ready",
    ) -> dict[str, Any]:
        resolved_scope_key = self.scope_key(month)
        normalized_payload = deepcopy(payload if isinstance(payload, dict) else {})
        normalized = self._normalize_read_model(
            {
                "scope_key": resolved_scope_key,
                "scope_type": "month",
                "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
                "month": resolved_scope_key,
                "generated_at": generated_at or self._timestamp(),
                "cache_status": str(cache_status or "ready"),
                "output_count": self._item_count(normalized_payload, "output_items"),
                "input_plan_count": self._item_count(normalized_payload, "input_plan_items"),
                "certified_count": self._item_count(normalized_payload, "certified_items"),
                "payload": normalized_payload,
                "source_scope_keys": self._normalize_source_scope_keys(source_scope_keys),
            },
            fallback_scope_key=resolved_scope_key,
        )
        with self._lock:
            self._read_models[resolved_scope_key] = normalized
            return deepcopy(normalized)

    def delete_read_model(self, month: str) -> bool:
        return self.delete_read_model_by_scope_key(self.scope_key(month))

    def delete_read_model_by_scope_key(self, scope_key: str) -> bool:
        try:
            resolved_scope_key = self._parse_scope_key(scope_key)
        except ValueError:
            return False
        with self._lock:
            return self._read_models.pop(resolved_scope_key, None) is not None

    def delete_scope_keys(self, scope_keys: list[str]) -> list[str]:
        deleted: list[str] = []
        for scope_key in list(scope_keys or []):
            try:
                resolved_scope_key = self._parse_scope_key(scope_key)
            except ValueError:
                continue
            with self._lock:
                if self._read_models.pop(resolved_scope_key, None) is not None:
                    deleted.append(resolved_scope_key)
        return deleted

    def invalidate_months(self, months: list[str]) -> list[str]:
        scope_keys: list[str] = []
        for month in list(months or []):
            resolved_scope_key = self.scope_key(month)
            if resolved_scope_key not in scope_keys:
                scope_keys.append(resolved_scope_key)
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
                        "generated_at",
                        "cache_status",
                        "output_count",
                        "input_plan_count",
                        "certified_count",
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
            if read_model.get("schema_version") != TAX_OFFSET_READ_MODEL_SCHEMA_VERSION:
                continue
            try:
                normalized_read_model = cls._normalize_read_model(read_model, fallback_scope_key=str(scope_key))
            except ValueError:
                continue
            normalized[str(normalized_read_model["scope_key"])] = normalized_read_model
        return normalized

    @classmethod
    def _normalize_read_model(cls, read_model: dict[str, Any], *, fallback_scope_key: str) -> dict[str, Any]:
        resolved_scope_key = cls._parse_scope_key(read_model.get("scope_key") or fallback_scope_key)
        payload = read_model.get("payload")
        normalized_payload = deepcopy(payload if isinstance(payload, dict) else {})
        return {
            "scope_key": resolved_scope_key,
            "scope_type": "month",
            "schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            "month": resolved_scope_key,
            "generated_at": str(read_model.get("generated_at") or cls._timestamp()),
            "cache_status": str(read_model.get("cache_status") or "ready"),
            "output_count": cls._item_count(normalized_payload, "output_items"),
            "input_plan_count": cls._item_count(normalized_payload, "input_plan_items"),
            "certified_count": cls._item_count(normalized_payload, "certified_items"),
            "payload": normalized_payload,
            "source_scope_keys": cls._normalize_source_scope_keys(read_model.get("source_scope_keys")),
        }

    @classmethod
    def _parse_scope_key(cls, scope_key: Any) -> str:
        return cls._normalize_month(scope_key)

    @staticmethod
    def _normalize_month(month: Any) -> str:
        resolved_month = str(month or "").strip()
        if not resolved_month:
            raise ValueError("month is required for tax offset read model.")
        if MONTH_RE.match(resolved_month):
            return resolved_month
        raise ValueError("month must be YYYY-MM for tax offset read model.")

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
    def _item_count(payload: dict[str, Any], key: str) -> int:
        items = payload.get(key)
        if not isinstance(items, list):
            raise ValueError(f"payload.{key} must be a list for tax offset read model.")
        return len(items)

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
