from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable


class ReadModelScopeError(ValueError):
    """Raised when a read model refresh scope violates its registered contract."""


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


@dataclass(frozen=True)
class ReadModelScopePolicy:
    scope_type: str
    normalize_many: Callable[[list[str]], list[str]]
    validate_one: Callable[[str], None]

    def normalize_and_validate(self, raw_scope_keys: list[str]) -> list[str]:
        normalized_scope_keys = self.normalize_many(raw_scope_keys)
        deduped_scope_keys = _dedupe_text(normalized_scope_keys)
        for scope_key in deduped_scope_keys:
            self.validate_one(scope_key)
        return deduped_scope_keys


class ReadModelScopePolicyRegistry:
    def __init__(self, policies: dict[str, ReadModelScopePolicy] | None = None) -> None:
        self._policies = dict(policies or {})

    def policy_for(self, scope_type: str) -> ReadModelScopePolicy:
        normalized_scope_type = str(scope_type or "").strip()
        if not normalized_scope_type:
            raise ReadModelScopeError("read model refresh scope_type is required.")
        return self._policies.get(normalized_scope_type, _generic_scope_policy(normalized_scope_type))

    def normalize_and_validate(self, scope_type: str, scope_keys: list[str]) -> list[str]:
        return self.policy_for(scope_type).normalize_and_validate(scope_keys)


def _generic_scope_policy(scope_type: str) -> ReadModelScopePolicy:
    return ReadModelScopePolicy(
        scope_type=scope_type,
        normalize_many=_dedupe_text,
        validate_one=lambda scope_key: _validate_non_empty(scope_type, scope_key),
    )


def _cost_statistics_scope_policy() -> ReadModelScopePolicy:
    return ReadModelScopePolicy(
        scope_type="cost_statistics",
        normalize_many=_normalize_cost_statistics_scope_keys,
        validate_one=_validate_cost_statistics_scope_key,
    )


def _month_or_all_scope_policy(scope_type: str) -> ReadModelScopePolicy:
    return ReadModelScopePolicy(
        scope_type=scope_type,
        normalize_many=_dedupe_text,
        validate_one=lambda scope_key: _validate_month_or_all_scope_key(scope_type, scope_key),
    )


def _normalize_cost_statistics_scope_keys(raw_scope_keys: list[str]) -> list[str]:
    from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

    cleaned_scope_keys = _dedupe_text(raw_scope_keys)
    for scope_key in cleaned_scope_keys:
        if _cost_statistics_raw_scope_is_supported(scope_key):
            continue
        raise ReadModelScopeError(f"Invalid cost_statistics read model scope_key: {scope_key}")
    return CostStatisticsRuntimeService.refresh_scope_keys_from_scope_keys(cleaned_scope_keys)


def _cost_statistics_raw_scope_is_supported(scope_key: str) -> bool:
    from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

    if CostStatisticsRuntimeService.parse_scope_key(scope_key) is not None:
        return True
    return scope_key == "all" or bool(MONTH_RE.match(scope_key))


def _validate_cost_statistics_scope_key(scope_key: str) -> None:
    from fin_ops_platform.services.cost_statistics_runtime_service import CostStatisticsRuntimeService

    if CostStatisticsRuntimeService.parse_scope_key(scope_key) is None:
        raise ReadModelScopeError(f"Invalid cost_statistics read model scope_key: {scope_key}")


def _validate_month_or_all_scope_key(scope_type: str, scope_key: str) -> None:
    normalized_scope_key = str(scope_key or "").strip()
    if normalized_scope_key == "all" or bool(MONTH_RE.match(normalized_scope_key)):
        return
    raise ReadModelScopeError(f"Invalid {scope_type} read model scope_key: {scope_key}")


def _validate_non_empty(scope_type: str, scope_key: str) -> None:
    if not str(scope_key or "").strip():
        raise ReadModelScopeError(f"{scope_type} read model refresh scope_key is required.")


def _dedupe_text(values: list[str]) -> list[str]:
    deduped: list[str] = []
    for value in list(values or []):
        text = str(value or "").strip()
        if text and text not in deduped:
            deduped.append(text)
    return deduped


DEFAULT_READ_MODEL_SCOPE_POLICY_REGISTRY = ReadModelScopePolicyRegistry(
    {
        "cost_statistics": _cost_statistics_scope_policy(),
        "no_oa_bank_batch": _month_or_all_scope_policy("no_oa_bank_batch"),
    }
)
