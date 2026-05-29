from __future__ import annotations

from dataclasses import dataclass
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
        normalized[normalized_key] = str(value)
    return normalized


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
    if (
        expected_schema_version not in (None, "")
        and actual_schema_version not in (None, "")
        and str(expected_schema_version) != str(actual_schema_version)
    ):
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
