from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
from typing import Any


FRESHNESS_STATUSES = {"fresh", "refreshing", "stale", "failed", "missing", "schema_mismatch", "unavailable"}


def normalize_source_versions(source_versions: Any) -> dict[str, str]:
    if not isinstance(source_versions, dict):
        return {}
    normalized: dict[str, str] = {}
    for key, value in source_versions.items():
        normalized_key = str(key or "").strip()
        if not normalized_key or value in (None, ""):
            continue
        if isinstance(value, (dict, list)):
            normalized[normalized_key] = json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)
        else:
            normalized[normalized_key] = str(value)
    return normalized


def require_expected_source_versions(source_versions: Any, *, context: str) -> dict[str, str]:
    normalized = normalize_source_versions(source_versions)
    if not normalized:
        raise ValueError(f"{context} missing expected source versions.")
    return normalized


def read_model_freshness_token(
    *,
    scope_type: str,
    scope_key: str,
    expected_source_versions: Any,
) -> str:
    normalized_scope_type = str(scope_type or "").strip()
    normalized_scope_key = str(scope_key or "").strip()
    if not normalized_scope_type or not normalized_scope_key:
        raise ValueError("read model freshness token requires scope_type and scope_key.")
    payload = {
        "scope_type": normalized_scope_type,
        "scope_key": normalized_scope_key,
        "source_versions": require_expected_source_versions(
            expected_source_versions,
            context=f"{normalized_scope_type}:{normalized_scope_key}",
        ),
    }
    return hashlib.sha256(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def source_version_mismatch_reasons(
    *,
    expected: dict[str, Any] | None,
    actual: dict[str, Any] | None,
) -> list[str]:
    expected_versions = normalize_source_versions(expected)
    actual_versions = normalize_source_versions(actual)
    reasons: list[str] = []
    for key in sorted(expected_versions):
        expected_value = expected_versions[key]
        actual_value = actual_versions.get(key)
        if actual_value is None:
            reasons.append(f"{key}_missing")
        elif actual_value != expected_value:
            reasons.append(f"{key}_mismatch")
    return reasons


def source_versions_match(*, expected: dict[str, Any] | None, actual: dict[str, Any] | None) -> bool:
    return not source_version_mismatch_reasons(expected=expected, actual=actual)


@dataclass(frozen=True)
class ReadModelFreshness:
    status: str
    stale_reasons: tuple[str, ...] = ()

    def as_payload(self) -> dict[str, object]:
        payload: dict[str, object] = {"read_model_status": self.status}
        if self.stale_reasons:
            payload["read_model_stale_reasons"] = list(self.stale_reasons)
        return payload


def resolve_read_model_freshness(
    *,
    expected_schema_version: Any | None = None,
    actual_schema_version: Any | None = None,
    expected_source_versions: dict[str, Any] | None = None,
    actual_source_versions: dict[str, Any] | None = None,
    dirty_status: str | None = None,
    missing: bool = False,
    unavailable: bool = False,
) -> ReadModelFreshness:
    if unavailable:
        return ReadModelFreshness("unavailable")
    if missing:
        return ReadModelFreshness("missing")
    normalized_dirty_status = str(dirty_status or "").strip().lower()
    if normalized_dirty_status in {"pending", "processing", "queued", "running", "refreshing"}:
        return ReadModelFreshness("refreshing")
    if normalized_dirty_status in {"failed", "dead_lettered"}:
        return ReadModelFreshness("failed", ("dirty_scope_failed",))
    if expected_schema_version not in (None, ""):
        if actual_schema_version in (None, ""):
            return ReadModelFreshness("schema_mismatch", ("schema_version_missing",))
        if str(expected_schema_version) != str(actual_schema_version):
            return ReadModelFreshness("schema_mismatch", ("schema_version_mismatch",))
    mismatch_reasons = source_version_mismatch_reasons(
        expected=expected_source_versions,
        actual=actual_source_versions,
    )
    if mismatch_reasons:
        return ReadModelFreshness("stale", tuple(mismatch_reasons))
    if normalized_dirty_status in {"stale", "dirty"}:
        return ReadModelFreshness("stale", ("dirty_scope_stale",))
    return ReadModelFreshness("fresh")
