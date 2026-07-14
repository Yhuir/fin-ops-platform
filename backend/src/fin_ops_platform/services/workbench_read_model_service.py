from __future__ import annotations

from copy import deepcopy
from datetime import UTC, datetime
import hashlib
import json
from threading import RLock
from typing import Any


WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION = "workbench_read_model_service.v1"
READ_MODEL_SOURCE_VERSION_FIELDS = (
    "exception_rules_version",
    "exception_projection_version",
    "case_snapshot_version",
    "pair_relation_snapshot_version",
    "turnover_relation_snapshot_version",
    "matching_rules_version",
    "bank_auto_tag_rules_version",
    "oa_attachment_invoice_parser_version",
    "oa_projection_sync_version",
)


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
        source_versions: dict[str, Any] | None = None,
        exception_rules_version: str | None = None,
        exception_projection_version: str | None = None,
        case_snapshot_version: str | None = None,
        pair_relation_snapshot_version: str | None = None,
        matching_rules_version: str | None = None,
    ) -> dict[str, Any]:
        resolved_scope_key = str(scope_key).strip()
        if not resolved_scope_key:
            raise ValueError("scope_key is required for workbench read model.")

        resolved_source_versions = self._merge_source_versions(
            source_versions=source_versions,
            exception_rules_version=exception_rules_version,
            exception_projection_version=exception_projection_version,
            case_snapshot_version=case_snapshot_version,
            pair_relation_snapshot_version=pair_relation_snapshot_version,
            matching_rules_version=matching_rules_version,
        )
        resolved_payload = deepcopy(payload if isinstance(payload, dict) else {})
        for field_name, value in resolved_source_versions.items():
            resolved_payload.setdefault(field_name, value)

        normalized = self._normalize_read_model(
            {
                "schema_version": WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION,
                "scope_key": resolved_scope_key,
                "scope_type": self._scope_type_for_key(resolved_scope_key),
                "generated_at": generated_at or self._timestamp(),
                "payload": resolved_payload,
                "ignored_rows": deepcopy(ignored_rows if isinstance(ignored_rows, list) else []),
                "source_versions": resolved_source_versions,
                **resolved_source_versions,
            },
            fallback_scope_key=resolved_scope_key,
        )
        with self._lock:
            self._read_models[resolved_scope_key] = normalized
            return deepcopy(normalized)

    def get_read_model_if_fresh(
        self,
        scope_key: str,
        *,
        source_versions: dict[str, Any] | None = None,
        exception_rules_version: str | None = None,
        exception_projection_version: str | None = None,
        case_snapshot_version: str | None = None,
        pair_relation_snapshot_version: str | None = None,
        matching_rules_version: str | None = None,
    ) -> dict[str, Any] | None:
        if not self.is_read_model_fresh(
            scope_key,
            source_versions=source_versions,
            exception_rules_version=exception_rules_version,
            exception_projection_version=exception_projection_version,
            case_snapshot_version=case_snapshot_version,
            pair_relation_snapshot_version=pair_relation_snapshot_version,
            matching_rules_version=matching_rules_version,
        ):
            return None
        return self.get_read_model(scope_key)

    def is_read_model_fresh(
        self,
        scope_key: str,
        *,
        source_versions: dict[str, Any] | None = None,
        exception_rules_version: str | None = None,
        exception_projection_version: str | None = None,
        case_snapshot_version: str | None = None,
        pair_relation_snapshot_version: str | None = None,
        matching_rules_version: str | None = None,
    ) -> bool:
        expected_versions = self._merge_source_versions(
            source_versions=source_versions,
            exception_rules_version=exception_rules_version,
            exception_projection_version=exception_projection_version,
            case_snapshot_version=case_snapshot_version,
            pair_relation_snapshot_version=pair_relation_snapshot_version,
            matching_rules_version=matching_rules_version,
        )
        read_model = self.get_read_model(scope_key)
        if not isinstance(read_model, dict):
            return False
        if not expected_versions:
            return True
        persisted_versions = read_model.get("source_versions")
        normalized_persisted = persisted_versions if isinstance(persisted_versions, dict) else {}
        for key, expected_value in expected_versions.items():
            if normalized_persisted.get(key) != expected_value:
                return False
        return True

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
            if read_model.get("schema_version") != WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION:
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
        normalized["schema_version"] = WORKBENCH_READ_MODEL_SERVICE_SCHEMA_VERSION
        normalized["scope_key"] = resolved_scope_key
        normalized["scope_type"] = str(read_model.get("scope_type") or cls._scope_type_for_key(resolved_scope_key))
        normalized["generated_at"] = str(read_model.get("generated_at") or cls._timestamp())
        payload = read_model.get("payload")
        normalized["payload"] = deepcopy(payload if isinstance(payload, dict) else {})
        ignored_rows = read_model.get("ignored_rows")
        normalized["ignored_rows"] = deepcopy(ignored_rows if isinstance(ignored_rows, list) else [])
        source_versions = read_model.get("source_versions")
        normalized_source_versions = (
            cls._merge_source_versions(source_versions=source_versions)
            if isinstance(source_versions, dict)
            else cls._source_versions_from_payload(normalized["payload"])
        )
        for field_name in READ_MODEL_SOURCE_VERSION_FIELDS:
            value = read_model.get(field_name, normalized_source_versions.get(field_name))
            if value in (None, ""):
                normalized_source_versions.pop(field_name, None)
                normalized.pop(field_name, None)
                continue
            normalized_value = str(value)
            normalized_source_versions[field_name] = normalized_value
            normalized[field_name] = normalized_value
        normalized.pop("candidate_snapshot_version", None)
        normalized["payload"].pop("candidate_snapshot_version", None)
        normalized["source_versions"] = normalized_source_versions
        return normalized

    @staticmethod
    def snapshot_version(snapshot: Any) -> str:
        encoded = json.dumps(
            snapshot,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        ).encode("utf-8")
        return hashlib.sha256(encoded).hexdigest()

    @staticmethod
    def _merge_source_versions(
        *,
        source_versions: dict[str, Any] | None = None,
        exception_rules_version: str | None = None,
        exception_projection_version: str | None = None,
        case_snapshot_version: str | None = None,
        pair_relation_snapshot_version: str | None = None,
        turnover_relation_snapshot_version: str | None = None,
        matching_rules_version: str | None = None,
        bank_auto_tag_rules_version: str | int | None = None,
        oa_attachment_invoice_parser_version: str | None = None,
        oa_projection_sync_version: str | None = None,
    ) -> dict[str, str]:
        merged: dict[str, str] = {}
        if isinstance(source_versions, dict):
            for key, value in source_versions.items():
                if key not in READ_MODEL_SOURCE_VERSION_FIELDS or value in (None, ""):
                    continue
                merged[key] = str(value)
        explicit_values = {
            "exception_rules_version": exception_rules_version,
            "exception_projection_version": exception_projection_version,
            "case_snapshot_version": case_snapshot_version,
            "pair_relation_snapshot_version": pair_relation_snapshot_version,
            "turnover_relation_snapshot_version": turnover_relation_snapshot_version,
            "matching_rules_version": matching_rules_version,
            "bank_auto_tag_rules_version": bank_auto_tag_rules_version,
            "oa_attachment_invoice_parser_version": oa_attachment_invoice_parser_version,
            "oa_projection_sync_version": oa_projection_sync_version,
        }
        for key, value in explicit_values.items():
            if value in (None, ""):
                continue
            merged[key] = str(value)
        return merged

    @staticmethod
    def _source_versions_from_payload(payload: dict[str, Any]) -> dict[str, str]:
        return {
            field_name: str(payload[field_name])
            for field_name in READ_MODEL_SOURCE_VERSION_FIELDS
            if payload.get(field_name) not in (None, "")
        }

    @staticmethod
    def _scope_type_for_key(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        terminal_scope = normalized_scope_key.rsplit(":", 1)[-1]
        return "all_time" if terminal_scope == "all" else "month"

    @staticmethod
    def _timestamp() -> str:
        return datetime.now(UTC).isoformat()
