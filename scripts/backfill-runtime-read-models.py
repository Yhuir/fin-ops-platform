#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.app.worker import main as worker_main  # noqa: E402
from fin_ops_platform.services.invoice_usage_collection_backfill import (  # noqa: E402
    build_invoice_usage_collection_backfill_plan,
    execute_invoice_usage_collection_backfill_plan,
    invoice_usage_collection_worker_args,
)
from fin_ops_platform.services.invoice_usage_collection_sql_projection import (  # noqa: E402
    InvoiceUsageCollectionSqlProjectionBuilder,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings  # noqa: E402
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository  # noqa: E402
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository  # noqa: E402


PENDING_INVOICE_SCOPES = [
    "expense:all",
    "expense:requires_invoice",
    "expense:bank_statement_as_invoice",
    "expense:no_invoice_required",
    "income:all",
]


def main() -> int:
    parser = argparse.ArgumentParser(description="Backfill runtime SQL read models from PostgreSQL facts.")
    parser.add_argument("--backfill-oa-children", action="store_true", help="Populate app.oa_application_items and app.oa_attachments from existing OA application payloads.")
    parser.add_argument("--enqueue-missing", action="store_true", help="Enqueue read model refreshes for all fact-backed scopes.")
    parser.add_argument("--enqueue-invoice-usage-collection", action="store_true", help="Enqueue only input invoice usage and output invoice collection read model refreshes.")
    parser.add_argument(
        "--invoice-target",
        action="append",
        default=[],
        choices=["both", "all", "input", "output", "input_invoice_usage", "output_invoice_collection"],
        help="Invoice read model target. Repeatable. Defaults to both.",
    )
    parser.add_argument("--invoice-scope", action="append", default=[], help="Invoice read model scope: all or YYYY-MM. Repeatable. Defaults to all.")
    parser.add_argument("--invoice-expand-all", action="store_true", help="Expand invoice all scope into current invoice month shards before enqueue.")
    parser.add_argument("--run-worker", action="store_true", help="Drain runtime read model worker events in this process.")
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--lock-timeout-seconds", type=int, default=30, help="Reclaim stale processing events older than this many seconds while draining.")
    parser.add_argument("--task-timeout-seconds", type=int, default=60, help="Fail and retry a single claimed event after this many wall-clock seconds.")
    parser.add_argument("--statement-timeout-seconds", type=int, default=30)
    parser.add_argument("--dry-run", action="store_true", help="Preview mutating actions without writing read model queues or OA child tables.")
    parser.add_argument("--reason", default="runtime_backfill", help="Reason written to dirty scopes and outbox payloads.")
    parser.add_argument("--priority", default="normal", help="Runtime queue priority: low, normal, high or urgent.")
    parser.add_argument("--trace-id", default=None, help="Optional trace id attached to enqueued refresh events.")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    connection = PostgresConnection(PostgresSettings.from_env())
    report: dict[str, Any] = {"actions": []}
    if args.backfill_oa_children:
        report["actions"].append(backfill_oa_children_plan(connection) if args.dry_run else backfill_oa_children(connection))
    if args.enqueue_missing:
        report["actions"].append(
            enqueue_fact_scopes(
                connection,
                dry_run=args.dry_run,
                reason=args.reason,
                priority=args.priority,
                trace_id=args.trace_id,
                invoice_targets=args.invoice_target or ["both"],
                invoice_scope_keys=args.invoice_scope or ["all"],
                invoice_expand_all=args.invoice_expand_all,
            )
        )
    elif args.enqueue_invoice_usage_collection:
        report["actions"].append(
            enqueue_invoice_usage_collection_scopes(
                connection,
                targets=args.invoice_target or ["both"],
                scope_keys=args.invoice_scope or ["all"],
                expand_all=args.invoice_expand_all,
                dry_run=args.dry_run,
                reason=args.reason,
                priority=args.priority,
                trace_id=args.trace_id,
            )
        )
    if args.run_worker:
        worker_args = [
            "--worker-id",
            "runtime-read-model-backfill",
            "--enable-workbench-read-model-refresh",
            "--enable-search-read-model-refresh",
            "--enable-pending-invoice-read-model-refresh",
            "--enable-cost-statistics-read-model-refresh",
            "--enable-tax-offset-read-model-refresh",
            "--event-type",
            "workbench.read_model.refresh",
            "--event-type",
            "search.read_model.refresh",
            "--event-type",
            "pending_invoice.read_model.refresh",
            "--event-type",
            "cost_statistics.read_model.refresh",
            "--event-type",
            "tax_offset.read_model.refresh",
            *invoice_usage_collection_worker_args(),
            "--max-iterations",
            str(max(1, args.max_iterations)),
            "--poll-interval-seconds",
            "0.2",
            "--lock-timeout-seconds",
            str(max(1, args.lock_timeout_seconds)),
            "--task-timeout-seconds",
            str(max(1, args.task_timeout_seconds)),
            "--statement-timeout-seconds",
            str(max(1, args.statement_timeout_seconds)),
        ]
        if args.dry_run:
            report["actions"].append({"action": "run_worker", "dry_run": True, "worker_args": worker_args})
        else:
            result = worker_main(worker_args)
            report["actions"].append({"action": "run_worker", "exit_code": result, "worker_args": worker_args})
    report["coverage"] = coverage_report(connection)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


def backfill_oa_children(connection: PostgresConnection) -> dict[str, Any]:
    repository = PostgresOAProjectionRepository(connection)
    records = repository.list_all_application_records()
    by_month: dict[str, list[Any]] = {}
    for record in records:
        by_month.setdefault(str(record.month or "all"), []).append(record)
    upserted = 0
    for month, month_records in sorted(by_month.items()):
        upserted += repository.upsert_application_records(month_records, scope_key=month)
    counts = connection.fetch_one(
        """
        select
          (select count(*) from app.oa_application_items) as oa_application_items,
          (select count(*) from app.oa_attachments) as oa_attachments
        """
    ) or {}
    return {"action": "backfill_oa_children", "records": len(records), "upserted": upserted, **dict(counts)}


def backfill_oa_children_plan(connection: PostgresConnection) -> dict[str, Any]:
    repository = PostgresOAProjectionRepository(connection)
    records = repository.list_all_application_records()
    counts = connection.fetch_one(
        """
        select
          (select count(*) from app.oa_application_items) as oa_application_items,
          (select count(*) from app.oa_attachments) as oa_attachments
        """
    ) or {}
    return {
        "action": "backfill_oa_children",
        "dry_run": True,
        "records": len(records),
        "upserted": 0,
        **dict(counts),
    }


def enqueue_fact_scopes(
    connection: PostgresConnection,
    *,
    dry_run: bool = False,
    reason: str = "runtime_backfill",
    priority: str = "normal",
    trace_id: str | None = None,
    invoice_targets: list[str] | None = None,
    invoice_scope_keys: list[str] | None = None,
    invoice_expand_all: bool = False,
) -> dict[str, Any]:
    queue = RuntimeQueueRepository(connection)
    months = fact_months(connection)
    enqueued: list[dict[str, str]] = []
    for month in months:
        for scope_type in ("workbench", "search", "tax_offset"):
            _enqueue_read_model_refresh(
                queue,
                enqueued,
                scope_type=scope_type,
                scope_key=month,
                reason=reason,
                dry_run=dry_run,
                priority=priority,
                trace_id=trace_id,
            )
        for project_scope in ("active", "all"):
            scope_key = f"{project_scope}:{month}"
            _enqueue_read_model_refresh(
                queue,
                enqueued,
                scope_type="cost_statistics",
                scope_key=scope_key,
                reason=reason,
                dry_run=dry_run,
                priority=priority,
                trace_id=trace_id,
            )
    for scope_key in PENDING_INVOICE_SCOPES:
        _enqueue_read_model_refresh(
            queue,
            enqueued,
            scope_type="pending_invoice",
            scope_key=scope_key,
            reason=reason,
            dry_run=dry_run,
            priority=priority,
            trace_id=trace_id,
        )
    _enqueue_read_model_refresh(
        queue,
        enqueued,
        scope_type="workbench",
        scope_key="all",
        reason=reason,
        dry_run=dry_run,
        priority=priority,
        trace_id=trace_id,
    )
    invoice_report = enqueue_invoice_usage_collection_scopes(
        connection,
        targets=invoice_targets or ["both"],
        scope_keys=invoice_scope_keys or ["all"],
        expand_all=invoice_expand_all,
        dry_run=dry_run,
        reason=reason,
        priority=priority,
        trace_id=trace_id,
    )
    return {
        "action": "enqueue_missing",
        "dry_run": bool(dry_run),
        "month_count": len(months),
        "months": months,
        "enqueued_count": 0 if dry_run else len(enqueued) + int(invoice_report["enqueued_count"]),
        "planned_count": len(enqueued) + int(invoice_report["planned_count"]),
        "invoice_usage_collection": invoice_report,
    }


def enqueue_invoice_usage_collection_scopes(
    connection: PostgresConnection,
    *,
    targets: list[str] | None = None,
    scope_keys: list[str] | None = None,
    expand_all: bool = False,
    dry_run: bool = False,
    reason: str = "runtime_backfill",
    priority: str = "normal",
    trace_id: str | None = None,
) -> dict[str, object]:
    shard_provider = InvoiceUsageCollectionSqlProjectionBuilder(connection=connection) if expand_all else None
    plan = build_invoice_usage_collection_backfill_plan(
        targets=targets or ["both"],
        scope_keys=scope_keys or ["all"],
        expand_all=expand_all,
        shard_provider=shard_provider,
        reason=reason,
        priority=priority,
        trace_id=trace_id,
    )
    queue = RuntimeQueueRepository(connection)
    return execute_invoice_usage_collection_backfill_plan(queue, plan, dry_run=dry_run)


def _enqueue_read_model_refresh(
    queue: RuntimeQueueRepository,
    enqueued: list[dict[str, str]],
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    dry_run: bool,
    priority: str,
    trace_id: str | None,
) -> None:
    if not dry_run:
        queue.enqueue_read_model_refresh(
            scope_type=scope_type,
            scope_key=scope_key,
            reason=reason,
            priority=priority,
            trace_id=trace_id,
        )
    enqueued.append({"scope_type": scope_type, "scope_key": scope_key})


def fact_months(connection: PostgresConnection) -> list[str]:
    rows = connection.fetch_all(
        """
        select scope_key
        from (
            select distinct to_char(invoice_month, 'YYYY-MM') as scope_key
            from app.invoices
            where invoice_month is not null and status <> 'deleted'
            union
            select distinct to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where txn_month is not null and status <> 'deleted'
            union
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from app.oa_applications
            where scope_month is not null
        ) scopes
        where scope_key is not null
        order by scope_key
        """
    )
    return [str(row.get("scope_key")) for row in rows if str(row.get("scope_key") or "").strip()]


def invoice_fact_months(connection: PostgresConnection, invoice_type: str) -> list[str]:
    rows = connection.fetch_all(
        """
        select distinct to_char(coalesce(invoice_month, date_trunc('month', invoice_date)), 'YYYY-MM') as scope_key
        from app.invoices
        where invoice_type = %s
          and coalesce(invoice_month, invoice_date) is not null
          and status <> 'deleted'
        order by scope_key
        """,
        (invoice_type,),
    )
    return [str(row.get("scope_key")) for row in rows if str(row.get("scope_key") or "").strip()]


def read_model_scope_counts(connection: PostgresConnection, table_name: str) -> list[dict[str, Any]]:
    if table_name not in {"read_model.input_invoice_usage_rows", "read_model.output_invoice_collection_rows"}:
        raise ValueError(f"unsupported read model count table: {table_name}")
    rows = connection.fetch_all(
        f"""
        select scope_key, count(*)::int as row_count
        from {table_name}
        where scope_key <> 'all'
        group by scope_key
        order by scope_key
        """
    )
    return [dict(row) for row in rows]


def coverage_report(connection: PostgresConnection) -> dict[str, Any]:
    fact_scope_keys = set(fact_months(connection))
    input_invoice_months = set(invoice_fact_months(connection, "input"))
    output_invoice_months = set(invoice_fact_months(connection, "output"))
    workbench_rows = connection.fetch_all(
        """
        select scope_key, count(*)::int as row_count
        from read_model.workbench_rows
        where scope_key <> 'all'
        group by scope_key
        order by scope_key
        """
    )
    workbench_scope_keys = {str(row.get("scope_key")) for row in workbench_rows}
    input_invoice_usage_rows = read_model_scope_counts(connection, "read_model.input_invoice_usage_rows")
    input_invoice_usage_scope_keys = {str(row.get("scope_key")) for row in input_invoice_usage_rows}
    output_invoice_collection_rows = read_model_scope_counts(connection, "read_model.output_invoice_collection_rows")
    output_invoice_collection_scope_keys = {str(row.get("scope_key")) for row in output_invoice_collection_rows}
    dirty = connection.fetch_all(
        """
        select scope_type, status, count(*)::int as count
        from job.read_model_dirty_scopes
        where status in ('pending', 'processing', 'failed')
        group by scope_type, status
        order by scope_type, status
        """
    )
    outbox = connection.fetch_all(
        """
        select event_type, status, count(*)::int as count
        from job.outbox_events
        where status in ('pending', 'processing', 'failed')
        group by event_type, status
        order by event_type, status
        """
    )
    return {
        "fact_months": sorted(fact_scope_keys),
        "workbench_months": sorted(workbench_scope_keys),
        "missing_workbench_months": sorted(fact_scope_keys - workbench_scope_keys),
        "workbench_rows": [dict(row) for row in workbench_rows],
        "input_invoice_usage_months": sorted(input_invoice_usage_scope_keys),
        "missing_input_invoice_usage_months": sorted(input_invoice_months - input_invoice_usage_scope_keys),
        "input_invoice_usage_rows": input_invoice_usage_rows,
        "output_invoice_collection_months": sorted(output_invoice_collection_scope_keys),
        "missing_output_invoice_collection_months": sorted(output_invoice_months - output_invoice_collection_scope_keys),
        "output_invoice_collection_rows": output_invoice_collection_rows,
        "dirty": [dict(row) for row in dirty],
        "outbox": [dict(row) for row in outbox],
    }


if __name__ == "__main__":
    raise SystemExit(main())
