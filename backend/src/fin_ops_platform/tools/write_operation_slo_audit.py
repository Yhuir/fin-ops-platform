from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
from math import ceil
from pathlib import Path
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings


DEFAULT_TARGET_MS = 5_000.0
DEFAULT_LOOKBACK_HOURS = 24.0
DEFAULT_LIMIT = 2_000


@dataclass(frozen=True)
class OperationExpectation:
    operation: str
    scope_type: str
    reason: str
    action_names: tuple[str, ...] = ()
    required: bool = True


@dataclass(frozen=True)
class OperationExpectationResult:
    operation: str
    scope_type: str
    reason: str
    action_names: tuple[str, ...]
    required: bool
    status: str
    sample_count: int
    failed_sample_count: int
    p95_enqueue_to_done_ms: float | None
    max_enqueue_to_done_ms: float | None
    latest_scope_key: str | None
    latest_event_id: str | None
    latest_action_name: str | None
    latest_event_status: str | None
    latest_dirty_status: str | None
    latest_error: str | None = None


DEFAULT_OPERATION_EXPECTATIONS: tuple[OperationExpectation, ...] = (
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "turnover_ledger",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "workbench",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "workbench_relation",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "cost_statistics",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_manual_closure_or_withdraw",
        "search",
        "turnover_relation_changed",
        ("turnover_relation_zero_difference_closure", "withdraw_relation", "turnover_relation_withdraw"),
    ),
    OperationExpectation(
        "turnover_relation_extra",
        "turnover_ledger",
        "turnover_relation_extra_changed",
        ("relation_extra_update", "turnover_relation_extra_update"),
    ),
    OperationExpectation(
        "turnover_tag_selection",
        "turnover_ledger",
        "turnover_ledger_tag_selection_changed",
        ("turnover_ledger_tag_selection_changed", "turnover_ledger_tag_selection_update"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "bank_detail",
        "bank_transaction_category_changed",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "workbench",
        "workbench_scope_invalidated",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation(
        "bank_row_tags_batch",
        "turnover_ledger",
        "turnover_relation_changed",
        ("bank_row_tags_batch", "turnover_bank_row_tags_batch"),
    ),
    OperationExpectation("bank_auto_tag_rules", "bank_detail", "bank_auto_tag_rules_changed_priority"),
    OperationExpectation("bank_category_confirmation", "bank_detail", "bank_detail_category_confirmation_changed"),
    OperationExpectation("no_oa_tag_selection", "no_oa_bank_batch", "no_oa_bank_batch_tag_selection_changed"),
    OperationExpectation("workbench_relation_withdraw", "workbench", "workbench_scope_invalidated", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "bank_detail", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "workbench_relation", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "invoice_lifecycle", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "pending_invoice", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "input_invoice_usage", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "output_invoice_collection", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "oa_pending_payment", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "cost_statistics", "pair_relation_changed"),
    OperationExpectation("workbench_relation_withdraw", "search", "pair_relation_changed", ("withdraw_link",)),
    OperationExpectation("workbench_relation_withdraw", "tax_offset", "pair_relation_changed"),
    OperationExpectation("no_oa_bank_batch_withdraw", "no_oa_bank_batch", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)),
    OperationExpectation("no_oa_bank_batch_withdraw", "workbench", "workbench_scope_invalidated", ("no_oa_bank_batch_withdraw",)),
    OperationExpectation("no_oa_bank_batch_withdraw", "workbench_relation", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)),
    OperationExpectation("no_oa_bank_batch_withdraw", "cost_statistics", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)),
    OperationExpectation("no_oa_bank_batch_withdraw", "search", "no_oa_bank_batch_changed", ("no_oa_bank_batch_withdraw",)),
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Audit recent real write-operation read model refresh SLO from durable outbox events.",
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This is the default output shape.")
    parser.add_argument("--output", type=Path, help="Optional path to write the JSON report.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--lookback-hours", type=float, default=DEFAULT_LOOKBACK_HOURS)
    parser.add_argument("--target-ms", type=float, default=DEFAULT_TARGET_MS)
    parser.add_argument("--limit", type=int, default=DEFAULT_LIMIT)
    parser.add_argument(
        "--operation",
        action="append",
        default=[],
        help="Limit audit to one operation profile. Repeatable. Defaults to all built-in profiles.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    report = audit_write_operation_slo(
        connection,
        tenant_id=str(args.tenant_id or "default"),
        lookback_hours=max(0.1, float(args.lookback_hours)),
        target_ms=max(1.0, float(args.target_ms)),
        limit=max(1, int(args.limit)),
        operations=args.operation,
    )
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
    return 0 if report["status"] == "pass" else 1


def audit_write_operation_slo(
    connection: Any,
    *,
    tenant_id: str = "default",
    lookback_hours: float = DEFAULT_LOOKBACK_HOURS,
    target_ms: float = DEFAULT_TARGET_MS,
    limit: int = DEFAULT_LIMIT,
    operations: Sequence[str] | None = None,
) -> dict[str, Any]:
    expectations = _selected_expectations(operations)
    rows = _recent_read_model_refresh_events(
        connection,
        tenant_id=tenant_id,
        lookback_hours=lookback_hours,
        limit=limit,
    )
    results = evaluate_operation_expectations(rows, expectations=expectations, target_ms=target_ms)
    failures = [result for result in results if result.status != "pass"]
    missing = [result for result in results if result.status == "missing"]
    return {
        "version": 1,
        "status": "pass" if not failures else "fail",
        "generated_at": datetime.now(UTC).isoformat(),
        "tenant_id": tenant_id,
        "lookback_hours": lookback_hours,
        "target_ms": target_ms,
        "event_sample_count": len(rows),
        "expectation_count": len(expectations),
        "failed_expectation_count": len(failures),
        "missing_expectation_count": len(missing),
        "operations": sorted({expectation.operation for expectation in expectations}),
        "results": [asdict(result) for result in results],
    }


def evaluate_operation_expectations(
    rows: Sequence[dict[str, Any]],
    *,
    expectations: Sequence[OperationExpectation],
    target_ms: float,
) -> list[OperationExpectationResult]:
    return [
        _evaluate_expectation(
            expectation,
            rows,
            target_ms=target_ms,
        )
        for expectation in expectations
    ]


def selected_expectations_for_operations(operations: Sequence[str] | None) -> list[OperationExpectation]:
    return _selected_expectations(operations)


def recent_read_model_refresh_events_since(
    connection: Any,
    *,
    tenant_id: str,
    started_at: Any,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          e.id::text as event_id,
          e.tenant_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          coalesce(e.payload->>'reason', e.raw_payload->>'reason', d.reason) as reason,
          coalesce(
            e.payload->>'action_name',
            e.payload->'metadata'->>'action_name',
            e.raw_payload->>'action_name',
            e.raw_payload->'metadata'->>'action_name'
          ) as action_name,
          e.status as event_status,
          e.source_version,
          e.created_at,
          e.processed_at,
          e.updated_at,
          e.last_error as event_last_error,
          e.raw_payload,
          d.status as dirty_status,
          d.last_error as dirty_last_error
        from job.outbox_events e
        left join job.read_model_dirty_scopes d
          on d.tenant_id = e.tenant_id
         and d.scope_type = e.scope_type
         and d.scope_key = e.scope_key
         and d.source_version = e.source_version
        where e.tenant_id = %s
          and e.event_type like '%%.read_model.refresh'
          and e.created_at >= %s
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (tenant_id, started_at, limit),
    )
    return [dict(row) for row in rows]


def _selected_expectations(operations: Sequence[str] | None) -> list[OperationExpectation]:
    requested = {str(operation or "").strip() for operation in list(operations or []) if str(operation or "").strip()}
    available = {expectation.operation for expectation in DEFAULT_OPERATION_EXPECTATIONS}
    unknown = sorted(requested - available)
    if unknown:
        raise ValueError(f"Unknown write-operation SLO profiles: {', '.join(unknown)}")
    return [
        expectation
        for expectation in DEFAULT_OPERATION_EXPECTATIONS
        if not requested or expectation.operation in requested
    ]


def _recent_read_model_refresh_events(
    connection: Any,
    *,
    tenant_id: str,
    lookback_hours: float,
    limit: int,
) -> list[dict[str, Any]]:
    rows = connection.fetch_all(
        """
        select
          e.id::text as event_id,
          e.tenant_id,
          e.event_type,
          e.scope_type,
          e.scope_key,
          coalesce(e.payload->>'reason', e.raw_payload->>'reason', d.reason) as reason,
          coalesce(
            e.payload->>'action_name',
            e.payload->'metadata'->>'action_name',
            e.raw_payload->>'action_name',
            e.raw_payload->'metadata'->>'action_name'
          ) as action_name,
          e.status as event_status,
          e.source_version,
          e.created_at,
          e.processed_at,
          e.updated_at,
          e.last_error as event_last_error,
          e.raw_payload,
          d.status as dirty_status,
          d.last_error as dirty_last_error
        from job.outbox_events e
        left join job.read_model_dirty_scopes d
          on d.tenant_id = e.tenant_id
         and d.scope_type = e.scope_type
         and d.scope_key = e.scope_key
         and d.source_version = e.source_version
        where e.tenant_id = %s
          and e.event_type like '%%.read_model.refresh'
          and e.created_at >= now() - (%s * interval '1 hour')
        order by e.created_at desc, e.id desc
        limit %s
        """,
        (tenant_id, lookback_hours, limit),
    )
    return [dict(row) for row in rows]


def _evaluate_expectation(
    expectation: OperationExpectation,
    rows: Sequence[dict[str, Any]],
    *,
    target_ms: float,
) -> OperationExpectationResult:
    samples = [
        row
        for row in rows
        if str(row.get("scope_type") or "") == expectation.scope_type
        and str(row.get("reason") or "") == expectation.reason
        and (
            not expectation.action_names
            or str(row.get("action_name") or "") in set(expectation.action_names)
        )
    ]
    latest = samples[0] if samples else {}
    if not samples:
        return OperationExpectationResult(
            operation=expectation.operation,
            scope_type=expectation.scope_type,
            reason=expectation.reason,
            action_names=expectation.action_names,
            required=expectation.required,
            status="missing" if expectation.required else "skipped",
            sample_count=0,
            failed_sample_count=0,
            p95_enqueue_to_done_ms=None,
            max_enqueue_to_done_ms=None,
            latest_scope_key=None,
            latest_event_id=None,
            latest_action_name=None,
            latest_event_status=None,
            latest_dirty_status=None,
            latest_error="no_recent_required_write_refresh_event" if expectation.required else None,
        )
    durations = [
        duration
        for duration in (_duration_ms(row.get("created_at"), row.get("processed_at")) for row in samples)
        if duration is not None
    ]
    failed_samples = [
        row
        for row in samples
        if str(row.get("event_status") or "") != "done"
        or str(row.get("dirty_status") or "") not in {"", "done"}
    ]
    p95 = _percentile(durations, 0.95)
    max_duration = max(durations) if durations else None
    latest_error = str(latest.get("event_last_error") or latest.get("dirty_last_error") or "").strip() or None
    if failed_samples:
        status = "fail"
    elif p95 is None:
        status = "fail"
        latest_error = latest_error or "missing_processed_at"
    elif p95 > target_ms:
        status = "fail"
        latest_error = latest_error or f"p95_enqueue_to_done_ms_exceeded_target:{p95}>{target_ms}"
    else:
        status = "pass"
    return OperationExpectationResult(
        operation=expectation.operation,
        scope_type=expectation.scope_type,
        reason=expectation.reason,
        action_names=expectation.action_names,
        required=expectation.required,
        status=status,
        sample_count=len(samples),
        failed_sample_count=len(failed_samples),
        p95_enqueue_to_done_ms=p95,
        max_enqueue_to_done_ms=round(max_duration, 3) if max_duration is not None else None,
        latest_scope_key=str(latest.get("scope_key") or "") or None,
        latest_event_id=str(latest.get("event_id") or "") or None,
        latest_action_name=str(latest.get("action_name") or "") or None,
        latest_event_status=str(latest.get("event_status") or "") or None,
        latest_dirty_status=str(latest.get("dirty_status") or "") or None,
        latest_error=latest_error,
    )


def _duration_ms(start: Any, end: Any) -> float | None:
    started = _coerce_datetime(start)
    ended = _coerce_datetime(end)
    if started is None or ended is None:
        return None
    return round(max(0.0, (ended - started).total_seconds() * 1000), 3)


def _coerce_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        if value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value
    if not value:
        return None
    text = str(value).strip().replace(" ", "T", 1)
    try:
        return datetime.fromisoformat(text)
    except ValueError:
        return None


def _percentile(values: Sequence[float], percentile: float) -> float | None:
    if not values:
        return None
    ordered = sorted(float(value) for value in values)
    index = max(0, min(len(ordered) - 1, ceil(percentile * len(ordered)) - 1))
    return round(ordered[index], 3)


if __name__ == "__main__":
    raise SystemExit(main())
