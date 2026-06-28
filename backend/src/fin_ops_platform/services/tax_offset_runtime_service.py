from __future__ import annotations

from datetime import datetime
import hashlib
import json
import os
import re
from typing import Any, Callable

from fin_ops_platform.services.read_model_freshness import normalize_source_versions


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
TAX_OFFSET_READ_MODEL_SCHEMA_VERSION = "2026-05-tax-offset-month-v1"


class TaxOffsetRuntimeService:
    def __init__(
        self,
        *,
        queue_repository: Any | None = None,
        redis_helper: Any | None = None,
        source_versions_provider: Callable[[], dict[str, Any]] | None = None,
        month_cache_clearer: Callable[[list[str] | None], None] | None = None,
        schedule_cache_warmup: Callable[[list[str], str], None] | None = None,
        cache_error_emitter: Callable[..., None] | None = None,
        now_provider: Callable[[], datetime] | None = None,
    ) -> None:
        self._queue_repository = queue_repository
        self._redis_helper = redis_helper
        self._source_versions_provider = source_versions_provider
        self._month_cache_clearer = month_cache_clearer
        self._schedule_cache_warmup = schedule_cache_warmup
        self._cache_error_emitter = cache_error_emitter
        self._now_provider = now_provider or datetime.now

    @staticmethod
    def request_scope_key(month: str) -> str:
        normalized_month = str(month or "").strip()
        if not MONTH_RE.match(normalized_month):
            raise ValueError("month must be YYYY-MM for tax offset read model.")
        return normalized_month

    def expected_source_versions(self) -> dict[str, Any]:
        if callable(self._source_versions_provider):
            return dict(self._source_versions_provider() or {})
        return {"tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION}

    def redis_cache_key(self, scope_key: str, *, source_versions: dict[str, Any] | None = None) -> str:
        return self.read_model_redis_cache_key(
            "tax_offset:month",
            scope_key,
            schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            source_versions=source_versions,
        )

    def summary_redis_cache_key(self, scope_key: str, *, source_versions: dict[str, Any] | None = None) -> str:
        return self.read_model_redis_cache_key(
            "tax_offset:summary",
            scope_key,
            schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            source_versions=source_versions,
        )

    @staticmethod
    def read_model_redis_cache_key(
        prefix: str,
        scope_key: str,
        *,
        schema_version: str,
        source_versions: dict[str, Any] | None,
    ) -> str:
        normalized_source_versions = normalize_source_versions(source_versions)
        source_hash = hashlib.sha256(
            json.dumps(
                normalized_source_versions or {"source_versions": "unknown"},
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()[:16]
        return f"{prefix}:{scope_key}:schema:{schema_version}:sources:{source_hash}"

    @staticmethod
    def redis_ttl_seconds() -> int:
        raw_value = os.getenv("FIN_OPS_TAX_OFFSET_REDIS_TTL_SECONDS", "60").strip()
        try:
            return min(120, max(1, int(raw_value)))
        except ValueError:
            return 60

    def scope_key(self, month: str, *, stored_payload: dict[str, Any] | None = None) -> str:
        if isinstance(stored_payload, dict):
            scope_key = str(stored_payload.get("scope_key", "")).strip()
            if scope_key:
                return scope_key
        return self.request_scope_key(month)

    def invalidate_read_models(self) -> list[str]:
        self._clear_month_cache(None)
        warmup_months = self.default_warmup_months()
        if not self.enqueue_refresh_for_months(warmup_months, reason="tax_offset_read_model_invalidated"):
            self._schedule_warmup(warmup_months, "tax_offset_read_model_invalidated")
        return []

    def invalidate_read_model_scopes(self, scope_keys: list[str], *, reason: str = "") -> list[str]:
        months = self.months_from_scope_keys(scope_keys)
        if not months:
            return []
        ordered_months = sorted(months)
        self._clear_month_cache(ordered_months)
        refresh_job_enqueued = self.enqueue_refresh_for_months(
            ordered_months,
            reason=reason or "tax_offset_scope_invalidated",
        )
        if not refresh_job_enqueued:
            self._schedule_warmup(ordered_months, reason or "tax_offset_scope_invalidated")
        return []

    def enqueue_refresh_for_months(self, months: list[str], *, reason: str) -> bool:
        for month in sorted(self.months_from_scope_keys(months)):
            self.delete_redis_cache(month)
        return False

    def delete_redis_cache(self, scope_key: str) -> None:
        source_versions = self.expected_source_versions()
        self.redis_delete_best_effort(self.redis_cache_key(scope_key, source_versions=source_versions))
        self.redis_delete_best_effort(self.summary_redis_cache_key(scope_key, source_versions=source_versions))
        self.redis_delete_best_effort(f"tax_offset:month:{scope_key}")
        self.redis_delete_best_effort(f"tax_offset:summary:{scope_key}")

    def redis_get_json_best_effort(self, cache_key: str) -> dict[str, Any] | None:
        get_cached = getattr(self._redis_helper, "get_json", None)
        if not callable(get_cached):
            return None
        try:
            cached = get_cached(cache_key)
        except Exception as exc:  # pragma: no cover - concrete Redis exception classes vary by client version.
            self._emit_cache_error(operation="get_json", cache_key=cache_key, error=exc)
            return None
        return cached if isinstance(cached, dict) else None

    def redis_set_json_best_effort(self, cache_key: str, payload: dict[str, Any], *, ttl_seconds: int) -> bool:
        set_cached = getattr(self._redis_helper, "set_json", None)
        if not callable(set_cached):
            return False
        try:
            return bool(set_cached(cache_key, payload, ttl_seconds=ttl_seconds))
        except Exception as exc:  # pragma: no cover - concrete Redis exception classes vary by client version.
            self._emit_cache_error(operation="set_json", cache_key=cache_key, error=exc)
            return False

    def redis_delete_best_effort(self, cache_key: str) -> bool:
        delete = getattr(self._redis_helper, "delete", None)
        if not callable(delete):
            return False
        try:
            return bool(delete(cache_key))
        except Exception as exc:  # pragma: no cover - concrete Redis exception classes vary by client version.
            self._emit_cache_error(operation="delete", cache_key=cache_key, error=exc)
            return False

    @staticmethod
    def empty_month_payload(month: str) -> dict[str, Any]:
        return {
            "month": month,
            "summary": {
                "output_tax": "0.00",
                "input_tax": "0.00",
                "planned_input_tax": "0.00",
                "certified_input_tax": "0.00",
                "deductible_tax": "0.00",
                "result_label": "本月留抵税额",
                "result_amount": "0.00",
            },
            "output_items": [],
            "input_plan_items": [],
            "certified_items": [],
            "certified_matched_rows": [],
            "certified_outside_plan_rows": [],
            "locked_certified_input_ids": [],
            "default_selected_output_ids": [],
            "default_selected_input_ids": [],
        }

    @staticmethod
    def summary_payload(payload: dict[str, Any], *, scope_key: str) -> dict[str, Any]:
        item_list_keys = (
            "output_items",
            "input_plan_items",
            "certified_items",
            "certified_matched_rows",
            "certified_outside_plan_rows",
            "locked_certified_input_ids",
            "default_selected_output_ids",
            "default_selected_input_ids",
        )
        summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
        result: dict[str, Any] = {
            "month": str(payload.get("month") or scope_key),
            "summary": dict(summary),
            "item_counts": {
                key: len(value) if isinstance(value, list) else 0
                for key in item_list_keys
                for value in [payload.get(key)]
            },
        }
        for key in ("error",):
            if payload.get(key):
                result[key] = payload.get(key)
        if isinstance(payload.get("source_versions"), dict):
            result["source_versions"] = payload.get("source_versions")
        return result

    @staticmethod
    def month_entry_count(payload: dict[str, Any]) -> int:
        return (
            _list_count(payload.get("output_items"))
            + _list_count(payload.get("input_plan_items"))
            + _list_count(payload.get("certified_items"))
        )

    @classmethod
    def months_from_scope_keys(cls, scope_keys: list[str]) -> set[str]:
        months: set[str] = set()
        for raw_scope_key in list(scope_keys or []):
            scope_key = str(raw_scope_key).strip()
            if MONTH_RE.match(scope_key):
                months.add(scope_key)
        return months

    @classmethod
    def warmup_months_from_scope_keys(cls, scope_keys: list[str]) -> list[str]:
        return sorted(
            {
                str(scope_key).strip()
                for scope_key in list(scope_keys or [])
                if MONTH_RE.match(str(scope_key).strip())
            }
        )

    @staticmethod
    def default_warmup_months() -> list[str]:
        current_month = datetime.now().strftime("%Y-%m")
        current_year = int(current_month[:4])
        current_month_number = int(current_month[5:7])
        if current_month_number == 1:
            previous_month = f"{current_year - 1}-12"
        else:
            previous_month = f"{current_year}-{current_month_number - 1:02d}"
        return [previous_month, current_month]

    def _clear_month_cache(self, months: list[str] | None) -> None:
        if callable(self._month_cache_clearer):
            self._month_cache_clearer(months)

    def _schedule_warmup(self, months: list[str], reason: str) -> None:
        if callable(self._schedule_cache_warmup):
            self._schedule_cache_warmup(months, reason)

    def _emit_cache_error(self, *, operation: str, cache_key: str, error: Exception) -> None:
        if callable(self._cache_error_emitter):
            self._cache_error_emitter(operation=operation, cache_key=cache_key, error=error)


def _list_count(value: Any) -> int:
    return len(value) if isinstance(value, list) else 0
