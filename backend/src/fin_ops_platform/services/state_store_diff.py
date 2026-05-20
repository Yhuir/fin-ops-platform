from __future__ import annotations

from dataclasses import asdict, dataclass, fields, is_dataclass
from decimal import Decimal
from datetime import date, datetime
from enum import Enum
import re
from typing import Any


SECRET_KEY_MARKERS = (
    "password",
    "passwd",
    "token",
    "secret",
    "authorization",
    "cookie",
    "database_url",
    "mongo_uri",
    "postgres_uri",
    "postgres_url",
    "uri",
)
DEFAULT_IGNORED_FIELDS = {
    "updated_at",
    "created_at",
    "generated_at",
    "postgres_id",
    "internal_id",
    "pg_id",
    "uuid",
}


@dataclass(frozen=True)
class StateStoreDiffResult:
    matched: bool
    domain: str
    primary_count: int | None
    shadow_count: int | None
    mismatch_count: int
    mismatches: list[dict[str, object]]
    redacted: bool = True

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def diff_state_snapshots(
    primary: Any,
    shadow: Any,
    *,
    domain: str | None = None,
    ignored_paths: set[str] | None = None,
    max_mismatches: int = 20,
) -> StateStoreDiffResult:
    mismatches: list[dict[str, object]] = []
    ignored = set(ignored_paths or set())
    root_path = "" if isinstance(primary, (dict, list)) and isinstance(shadow, type(primary)) else str(domain or "state")
    _diff_values(primary, shadow, path=root_path, mismatches=mismatches, ignored_paths=ignored, max_mismatches=max_mismatches)
    return StateStoreDiffResult(
        matched=not mismatches,
        domain=str(domain or "state"),
        primary_count=_collection_count(primary),
        shadow_count=_collection_count(shadow),
        mismatch_count=len(mismatches),
        mismatches=mismatches,
        redacted=True,
    )


def redact_diff_payload(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            key_text = str(key)
            if _is_secret_key(key_text):
                continue
            else:
                redacted[key_text] = redact_diff_payload(item)
        return redacted
    if isinstance(value, list):
        return [redact_diff_payload(item) for item in value]
    if isinstance(value, tuple):
        return [redact_diff_payload(item) for item in value]
    if isinstance(value, str):
        return _redact_string(value)
    return value


def _diff_values(
    primary: Any,
    shadow: Any,
    *,
    path: str,
    mismatches: list[dict[str, object]],
    ignored_paths: set[str],
    max_mismatches: int,
) -> None:
    primary = _comparison_value(primary)
    shadow = _comparison_value(shadow)
    if len(mismatches) >= max_mismatches or _is_ignored_path(path, ignored_paths):
        return
    if isinstance(primary, dict) and isinstance(shadow, dict):
        keys = sorted(set(primary) | set(shadow), key=str)
        for key in keys:
            child_path = f"{path}.{key}" if path else str(key)
            if _is_ignored_path(child_path, ignored_paths):
                continue
            if key not in primary:
                _append_mismatch(mismatches, child_path, "missing_in_primary", None, shadow.get(key), max_mismatches)
                continue
            if key not in shadow:
                _append_mismatch(mismatches, child_path, "missing_in_shadow", primary.get(key), None, max_mismatches)
                continue
            _diff_values(primary[key], shadow[key], path=child_path, mismatches=mismatches, ignored_paths=ignored_paths, max_mismatches=max_mismatches)
            if len(mismatches) >= max_mismatches:
                return
        return
    if isinstance(primary, list) and isinstance(shadow, list):
        if len(primary) != len(shadow):
            _append_mismatch(mismatches, f"{path}.length", "length_mismatch", len(primary), len(shadow), max_mismatches)
        for index, (primary_item, shadow_item) in enumerate(zip(primary, shadow, strict=False)):
            _diff_values(primary_item, shadow_item, path=f"{path}[{index}]", mismatches=mismatches, ignored_paths=ignored_paths, max_mismatches=max_mismatches)
            if len(mismatches) >= max_mismatches:
                return
        return
    if not _scalars_equal(primary, shadow):
        _append_mismatch(mismatches, path, "value_mismatch", primary, shadow, max_mismatches)


def _append_mismatch(
    mismatches: list[dict[str, object]],
    path: str,
    kind: str,
    primary: Any,
    shadow: Any,
    max_mismatches: int,
) -> None:
    if len(mismatches) >= max_mismatches:
        return
    mismatches.append(
        {
            "path": path,
            "kind": kind,
            "primary": redact_diff_payload(primary),
            "shadow": redact_diff_payload(shadow),
        }
    )


def _is_ignored_path(path: str, ignored_paths: set[str]) -> bool:
    normalized = path.replace("[", ".").replace("]", "")
    segments = [segment for segment in normalized.split(".") if segment]
    if not segments:
        return False
    if normalized in ignored_paths or path in ignored_paths:
        return True
    if any(normalized.startswith(f"{item}.") or f".{item}." in normalized for item in ignored_paths):
        return True
    if segments[-1] in DEFAULT_IGNORED_FIELDS:
        return True
    if len(segments) >= 2 and segments[-2:] == ["raw_payload", "migration_metadata"]:
        return True
    return any(normalized.endswith(f".{item}") for item in ignored_paths)


def _collection_count(value: Any) -> int | None:
    if isinstance(value, (dict, list, tuple, set)):
        return len(value)
    return None


def _canonical_scalar(value: Any) -> Any:
    value = _comparison_value(value)
    if isinstance(value, Decimal):
        return str(value)
    return value


def _scalars_equal(primary: Any, shadow: Any) -> bool:
    if _canonical_scalar(primary) == _canonical_scalar(shadow):
        return True
    if isinstance(primary, str) and isinstance(shadow, str):
        return False
    primary_decimal = _numeric_decimal(primary)
    shadow_decimal = _numeric_decimal(shadow)
    return primary_decimal is not None and shadow_decimal is not None and primary_decimal == shadow_decimal


def _numeric_decimal(value: Any) -> Decimal | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float, str)):
        return _decimal_from_string(str(value))
    return None


def _decimal_from_string(value: str) -> Decimal | None:
    try:
        return Decimal(value)
    except Exception:
        return None


def _comparison_value(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return {field.name: _comparison_value(getattr(value, field.name)) for field in fields(value)}
    if isinstance(value, dict):
        return {key: _comparison_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_comparison_value(item) for item in value]
    if isinstance(value, tuple):
        return [_comparison_value(item) for item in value]
    if isinstance(value, set):
        return sorted((_comparison_value(item) for item in value), key=str)
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _is_secret_key(key: str) -> bool:
    lowered = key.lower()
    return any(marker in lowered for marker in SECRET_KEY_MARKERS)


def _redact_string(value: str) -> str:
    if "://" in value:
        return re.sub(r"[a-zA-Z][a-zA-Z0-9+.-]*://\S+", "<redacted-uri>", value)
    redacted = re.sub(r"(?i)(password|token|secret|authorization|cookie)=([^\s&]+)", r"\1=<redacted-secret>", value)
    return redacted
