from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
from threading import RLock
from typing import Any


class WorkbenchReadModelService:
    def __init__(self, *, read_models: dict[str, dict[str, Any]] | None = None) -> None:
        self._lock = RLock()
        self._read_models = self._normalize_read_models(read_models or {})

    @classmethod
    def from_snapshot(cls, snapshot: dict[str, Any] | None) -> "WorkbenchReadModelService":
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

    def get_read_model(self, scope_key: str) -> dict[str, Any] | None:
        resolved_scope_key = str(scope_key).strip()
        if not resolved_scope_key:
            return None
        with self._lock:
            read_model = self._read_models.get(resolved_scope_key)
            if not isinstance(read_model, dict):
                return None
            return deepcopy(read_model)

    def list_scope_keys(self) -> list[str]:
        with self._lock:
            return list(self._read_models.keys())

    def upsert_read_model(
        self,
        *,
        scope_key: str,
        payload: dict[str, Any],
        ignored_rows: list[dict[str, Any]] | None = None,
        generated_at: str | None = None,
    ) -> dict[str, Any]:
        resolved_scope_key = str(scope_key).strip()
        if not resolved_scope_key:
            raise ValueError("scope_key is required for workbench read model.")

        normalized = self._normalize_read_model(
            {
                "scope_key": resolved_scope_key,
                "scope_type": self._scope_type_for_key(resolved_scope_key),
                "generated_at": generated_at or self._timestamp(),
                "payload": deepcopy(payload if isinstance(payload, dict) else {}),
                "ignored_rows": deepcopy(ignored_rows if isinstance(ignored_rows, list) else []),
            },
            fallback_scope_key=resolved_scope_key,
        )
        with self._lock:
            self._read_models[resolved_scope_key] = normalized
            return deepcopy(normalized)

    def delete_read_model(self, scope_key: str) -> bool:
        resolved_scope_key = str(scope_key).strip()
        if not resolved_scope_key:
            return False
        with self._lock:
            return self._read_models.pop(resolved_scope_key, None) is not None

    @classmethod
    def _normalize_read_models(cls, read_models: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
        normalized: dict[str, dict[str, Any]] = {}
        for scope_key, read_model in read_models.items():
            if not isinstance(read_model, dict):
                continue
            normalized_read_model = cls._normalize_read_model(read_model, fallback_scope_key=str(scope_key))
            normalized[str(normalized_read_model["scope_key"])] = normalized_read_model
        return normalized

    @classmethod
    def _normalize_read_model(cls, read_model: dict[str, Any], *, fallback_scope_key: str) -> dict[str, Any]:
        resolved_scope_key = str(read_model.get("scope_key") or fallback_scope_key).strip()
        if not resolved_scope_key:
            raise ValueError("read model requires a non-empty scope_key")

        normalized = deepcopy(read_model)
        normalized["scope_key"] = resolved_scope_key
        normalized["scope_type"] = str(read_model.get("scope_type") or cls._scope_type_for_key(resolved_scope_key))
        normalized["generated_at"] = str(read_model.get("generated_at") or cls._timestamp())
        payload = read_model.get("payload")
        normalized["payload"] = deepcopy(payload if isinstance(payload, dict) else {})
        ignored_rows = read_model.get("ignored_rows")
        normalized["ignored_rows"] = deepcopy(ignored_rows if isinstance(ignored_rows, list) else [])
        return normalized

    @staticmethod
    def _scope_type_for_key(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        terminal_scope = normalized_scope_key.rsplit(":", 1)[-1]
        return "all_time" if terminal_scope == "all" else "month"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
