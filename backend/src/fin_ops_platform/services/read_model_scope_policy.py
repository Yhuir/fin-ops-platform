from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Callable


class ReadModelScopeError(ValueError):
    """Raised when a read model refresh scope violates its registered contract."""


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PENDING_INVOICE_EXPENSE_FILTERS = frozenset({"all", "requires_invoice", "bank_statement_as_invoice", "no_invoice_required"})
PENDING_INVOICE_INCOME_FILTERS = frozenset({"all", "requires_invoice", "no_invoice_required", "cash_income"})


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

    def registered_scope_types(self) -> tuple[str, ...]:
        return tuple(self._policies)


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


def _all_only_scope_policy(scope_type: str) -> ReadModelScopePolicy:
    return ReadModelScopePolicy(
        scope_type=scope_type,
        normalize_many=_dedupe_text,
        validate_one=lambda scope_key: _validate_all_only_scope_key(scope_type, scope_key),
    )


def _pending_invoice_scope_policy() -> ReadModelScopePolicy:
    return ReadModelScopePolicy(
        scope_type="pending_invoice",
        normalize_many=_dedupe_text,
        validate_one=_validate_pending_invoice_scope_key,
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


def _validate_all_only_scope_key(scope_type: str, scope_key: str) -> None:
    normalized_scope_key = str(scope_key or "").strip()
    if normalized_scope_key == "all":
        return
    raise ReadModelScopeError(f"Invalid {scope_type} read model scope_key: {scope_key}; only 'all' is supported.")


def _validate_pending_invoice_scope_key(scope_key: str) -> None:
    normalized_scope_key = str(scope_key or "").strip()
    parts = [part.strip() for part in normalized_scope_key.split(":")]
    if len(parts) not in {2, 3}:
        raise ReadModelScopeError(f"Invalid pending_invoice read model scope_key: {scope_key}")
    direction, filter_group = parts[0], parts[1]
    if direction not in {"expense", "income"}:
        raise ReadModelScopeError("pending_invoice read model scope direction must be expense or income.")
    if not filter_group:
        raise ReadModelScopeError(f"Invalid pending_invoice read model scope_key: {scope_key}")
    valid_filters = PENDING_INVOICE_EXPENSE_FILTERS if direction == "expense" else PENDING_INVOICE_INCOME_FILTERS
    if filter_group not in valid_filters:
        raise ReadModelScopeError(
            f"pending_invoice read model scope filter is not supported for {direction}: {filter_group}"
        )
    if len(parts) == 3 and not MONTH_RE.match(parts[2]):
        raise ReadModelScopeError(f"Invalid pending_invoice read model month scope_key: {scope_key}")


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
        "bank_account_balance": _all_only_scope_policy("bank_account_balance"),
        "bank_detail": _month_or_all_scope_policy("bank_detail"),
        "bank_flow_rule_batch": _month_or_all_scope_policy("bank_flow_rule_batch"),
        "cost_statistics": _cost_statistics_scope_policy(),
        "input_invoice_usage": _month_or_all_scope_policy("input_invoice_usage"),
        "invoice_lifecycle": _month_or_all_scope_policy("invoice_lifecycle"),
        "no_oa_bank_batch": _month_or_all_scope_policy("no_oa_bank_batch"),
        "oa_pending_payment": _month_or_all_scope_policy("oa_pending_payment"),
        "output_invoice_collection": _month_or_all_scope_policy("output_invoice_collection"),
        "pending_invoice": _pending_invoice_scope_policy(),
        "search": _month_or_all_scope_policy("search"),
        "tax_offset": _month_or_all_scope_policy("tax_offset"),
        "workbench": _month_or_all_scope_policy("workbench"),
        "workbench_relation": _month_or_all_scope_policy("workbench_relation"),
    }
)
