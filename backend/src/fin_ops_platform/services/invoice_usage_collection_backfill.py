from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.runtime_queue import PRIORITY_VALUES


INPUT_INVOICE_USAGE_SCOPE_TYPE = "input_invoice_usage"
OUTPUT_INVOICE_COLLECTION_SCOPE_TYPE = "output_invoice_collection"
INVOICE_USAGE_COLLECTION_SCOPE_TYPES = (
    INPUT_INVOICE_USAGE_SCOPE_TYPE,
    OUTPUT_INVOICE_COLLECTION_SCOPE_TYPE,
)

_TARGET_ALIASES = {
    "input": (INPUT_INVOICE_USAGE_SCOPE_TYPE,),
    INPUT_INVOICE_USAGE_SCOPE_TYPE: (INPUT_INVOICE_USAGE_SCOPE_TYPE,),
    "output": (OUTPUT_INVOICE_COLLECTION_SCOPE_TYPE,),
    OUTPUT_INVOICE_COLLECTION_SCOPE_TYPE: (OUTPUT_INVOICE_COLLECTION_SCOPE_TYPE,),
    "both": INVOICE_USAGE_COLLECTION_SCOPE_TYPES,
    "all": INVOICE_USAGE_COLLECTION_SCOPE_TYPES,
}


@dataclass(frozen=True)
class InvoiceUsageCollectionBackfillTask:
    scope_type: str
    scope_key: str
    reason: str
    priority: str = "normal"
    trace_id: str | None = None

    @property
    def event_type(self) -> str:
        return f"{self.scope_type}.read_model.refresh"

    def to_report(self) -> dict[str, object]:
        return {
            "event_type": self.event_type,
            "scope_type": self.scope_type,
            "scope_key": self.scope_key,
            "reason": self.reason,
            "priority": self.priority,
            "trace_id": self.trace_id,
        }


def build_invoice_usage_collection_backfill_plan(
    *,
    targets: Iterable[str] | None = None,
    scope_keys: Iterable[str] | None = None,
    expand_all: bool = False,
    shard_provider: Any | None = None,
    reason: str = "invoice_usage_collection_backfill",
    priority: str = "normal",
    trace_id: str | None = None,
) -> list[InvoiceUsageCollectionBackfillTask]:
    normalized_targets = _normalize_targets(targets)
    normalized_scope_keys = _normalize_scope_keys(scope_keys)
    normalized_reason = str(reason or "").strip() or "invoice_usage_collection_backfill"
    normalized_priority = _normalize_priority(priority)
    normalized_trace_id = str(trace_id or "").strip() or None

    tasks: list[InvoiceUsageCollectionBackfillTask] = []
    seen: set[tuple[str, str]] = set()
    for scope_type in normalized_targets:
        for scope_key in _expand_scope_keys(
            scope_type=scope_type,
            scope_keys=normalized_scope_keys,
            expand_all=expand_all,
            shard_provider=shard_provider,
        ):
            dedupe_key = (scope_type, scope_key)
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            tasks.append(
                InvoiceUsageCollectionBackfillTask(
                    scope_type=scope_type,
                    scope_key=scope_key,
                    reason=normalized_reason,
                    priority=normalized_priority,
                    trace_id=normalized_trace_id,
                )
            )
    return tasks


def execute_invoice_usage_collection_backfill_plan(
    queue_repository: Any,
    plan: Iterable[InvoiceUsageCollectionBackfillTask],
    *,
    dry_run: bool = False,
) -> dict[str, object]:
    tasks = list(plan)
    events: list[dict[str, object]] = []
    if not dry_run:
        enqueue = getattr(queue_repository, "enqueue_read_model_refresh", None)
        if not callable(enqueue):
            raise RuntimeError("queue_repository must expose enqueue_read_model_refresh.")
        for task in tasks:
            event = enqueue(
                scope_type=task.scope_type,
                scope_key=task.scope_key,
                reason=task.reason,
                priority=task.priority,
                trace_id=task.trace_id,
            )
            event_report: dict[str, object] = {}
            event_id = getattr(event, "event_id", None)
            source_version = getattr(event, "source_version", None)
            if event_id is not None:
                event_report["event_id"] = str(event_id)
            if source_version is not None:
                event_report["source_version"] = int(source_version)
            if event_report:
                events.append(event_report)
    return {
        "action": "enqueue_invoice_usage_collection",
        "dry_run": bool(dry_run),
        "planned_count": len(tasks),
        "enqueued_count": 0 if dry_run else len(tasks),
        "tasks": [task.to_report() for task in tasks],
        "events": events,
    }


def invoice_usage_collection_worker_args() -> list[str]:
    return [
        "--enable-input-invoice-usage-read-model-refresh",
        "--enable-output-invoice-collection-read-model-refresh",
        "--event-type",
        "input_invoice_usage.read_model.refresh",
        "--event-type",
        "output_invoice_collection.read_model.refresh",
    ]


def _normalize_targets(targets: Iterable[str] | None) -> tuple[str, ...]:
    raw_targets = list(targets or ["both"])
    normalized: list[str] = []
    for raw_target in raw_targets:
        target = str(raw_target or "").strip()
        mapped = _TARGET_ALIASES.get(target)
        if mapped is None:
            raise ValueError(f"unsupported invoice read model target: {raw_target}")
        for scope_type in mapped:
            if scope_type not in normalized:
                normalized.append(scope_type)
    return tuple(normalized)


def _normalize_scope_keys(scope_keys: Iterable[str] | None) -> tuple[str, ...]:
    raw_scope_keys = list(scope_keys or ["all"])
    normalized: list[str] = []
    for raw_scope_key in raw_scope_keys:
        scope_key = _normalize_scope_key(raw_scope_key)
        if scope_key not in normalized:
            normalized.append(scope_key)
    return tuple(normalized)


def _normalize_scope_key(raw_scope_key: object) -> str:
    scope_key = str(raw_scope_key or "").strip()
    if scope_key == "all" or MONTH_SCOPE_RE.match(scope_key):
        return scope_key
    raise ValueError(f"invoice read model scope must be 'all' or YYYY-MM: {raw_scope_key}")


def _normalize_priority(priority: str) -> str:
    normalized_priority = str(priority or "").strip() or "normal"
    if normalized_priority not in PRIORITY_VALUES:
        raise ValueError(f"unsupported runtime queue priority: {priority}")
    return normalized_priority


def _expand_scope_keys(
    *,
    scope_type: str,
    scope_keys: Iterable[str],
    expand_all: bool,
    shard_provider: Any | None,
) -> list[str]:
    expanded: list[str] = []
    for scope_key in scope_keys:
        if scope_key != "all" or not expand_all:
            expanded.append(scope_key)
            continue
        if shard_provider is None:
            raise ValueError("shard_provider is required when expand_all=True.")
        list_method_name = (
            "list_input_invoice_usage_scope_shards"
            if scope_type == INPUT_INVOICE_USAGE_SCOPE_TYPE
            else "list_output_invoice_collection_scope_shards"
        )
        list_shards = getattr(shard_provider, list_method_name, None)
        if not callable(list_shards):
            raise RuntimeError(f"shard_provider must expose {list_method_name}.")
        shard_keys = [_normalize_scope_key(item) for item in list(list_shards("all") or [])]
        expanded.extend(shard_keys or ["all"])
    return _dedupe_preserve_order(expanded)


def _dedupe_preserve_order(items: Iterable[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        if item not in result:
            result.append(item)
    return result
