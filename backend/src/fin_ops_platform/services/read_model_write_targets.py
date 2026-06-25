from __future__ import annotations

from typing import Any


def normalized_scope_keys(scope_keys: Any, *, fallback: str | None = None) -> list[str]:
    result: list[str] = []
    if isinstance(scope_keys, str):
        candidates = [scope_keys]
    elif isinstance(scope_keys, list | tuple | set):
        candidates = list(scope_keys)
    else:
        candidates = []
    for scope_key in candidates:
        text = str(scope_key or "").strip()
        if text and text not in result:
            result.append(text)
    if not result and fallback:
        result.append(fallback)
    return result


def freshness_targets(
    read_model_key: str,
    scope_keys: Any,
    *,
    scope_type: str | None = None,
    fallback_scope_key: str | None = None,
) -> list[dict[str, str]]:
    targets: list[dict[str, str]] = []
    for scope_key in normalized_scope_keys(scope_keys, fallback=fallback_scope_key):
        target = {
            "read_model_key": read_model_key,
            "scope_key": scope_key,
        }
        if scope_type:
            target["scope_type"] = scope_type
        targets.append(target)
    return targets


def write_target_envelope(
    *,
    read_model_key: str | None = None,
    scope_keys: Any = None,
    targets: Any = None,
    scope_type: str | None = None,
    fallback_scope_key: str | None = None,
) -> dict[str, object]:
    target_payloads = _normalized_targets(
        targets
        if targets is not None
        else freshness_targets(
            str(read_model_key or ""),
            scope_keys,
            scope_type=scope_type,
            fallback_scope_key=fallback_scope_key,
        )
    )
    target_scope_keys = normalized_scope_keys(
        scope_keys,
        fallback=fallback_scope_key if not target_payloads else None,
    )
    if not target_scope_keys:
        target_scope_keys = normalized_scope_keys([target["scope_key"] for target in target_payloads])
    return {
        "affected_scope_keys": target_scope_keys,
        "read_model_scope_keys": target_scope_keys,
        "freshness_targets": target_payloads,
        "operation_barrier_targets": list(target_payloads),
    }


def _normalized_targets(targets: Any) -> list[dict[str, str]]:
    if not isinstance(targets, list):
        return []
    normalized: list[dict[str, str]] = []
    seen: set[tuple[str, str, str]] = set()
    for target in targets:
        if not isinstance(target, dict):
            continue
        read_model_key = str(target.get("read_model_key") or target.get("readModelKey") or "").strip()
        scope_key = str(target.get("scope_key") or target.get("scopeKey") or "all").strip() or "all"
        scope_type = str(target.get("scope_type") or target.get("scopeType") or "").strip()
        if not read_model_key:
            continue
        dedupe_key = (read_model_key, scope_key, scope_type)
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        payload = {
            "read_model_key": read_model_key,
            "scope_key": scope_key,
        }
        if scope_type:
            payload["scope_type"] = scope_type
        normalized.append(payload)
    return normalized
