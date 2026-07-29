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
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings  # noqa: E402
from fin_ops_platform.services.postgres_repositories.oa_projection import PostgresOAProjectionRepository  # noqa: E402
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway  # noqa: E402
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository  # noqa: E402


ACTIVE_READ_MODEL_SCOPE_TYPES = ("workbench", "workbench_relation", "search", "no_oa_bank_batch")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Maintain active shared read models."
    )
    parser.add_argument("--backfill-oa-children", action="store_true", help="Populate app.oa_application_items and app.oa_attachments from existing OA application payloads.")
    parser.add_argument("--enqueue-missing", action="store_true", help="Enqueue fan-out refresh commands for the three active shared read models.")
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
            )
        )
    if args.run_worker:
        worker_args = [
            "--worker-id",
            "runtime-read-model-backfill",
            "--enable-workbench-relation-read-model-refresh",
            "--enable-search-read-model-refresh",
            "--enable-no-oa-bank-batch-read-model-refresh",
            "--event-type",
            "workbench_relation.read_model.refresh",
            "--event-type",
            "search.read_model.refresh",
            "--event-type",
            "no_oa_bank_batch.read_model.refresh",
            "--max-iterations",
            str(max(1, args.max_iterations)),
            "--max-events-per-iteration",
            "24",
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
) -> dict[str, Any]:
    queue = RuntimeQueueRepository(connection)
    refresh_gateway = ReadModelRefreshGateway(queue_repository=queue)
    enqueued: list[dict[str, str]] = []
    for scope_type in ACTIVE_READ_MODEL_SCOPE_TYPES:
        _enqueue_read_model_refresh(
            refresh_gateway,
            enqueued,
            scope_type=scope_type,
            scope_key="all",
            reason=reason,
            dry_run=dry_run,
            priority=priority,
            trace_id=trace_id,
        )
    return {
        "action": "enqueue_missing",
        "dry_run": bool(dry_run),
        "enqueued_count": 0 if dry_run else len(enqueued),
        "planned_count": len(enqueued),
        "scope_types": list(ACTIVE_READ_MODEL_SCOPE_TYPES),
    }


def _enqueue_read_model_refresh(
    refresh_gateway: ReadModelRefreshGateway,
    enqueued: list[dict[str, str]],
    *,
    scope_type: str,
    scope_key: str,
    reason: str,
    dry_run: bool,
    priority: str,
    trace_id: str | None,
) -> None:
    gateway = ReadModelRefreshGateway(queue_repository=None) if dry_run else refresh_gateway
    normalized_scope_keys = gateway.enqueue_many(
        scope_type,
        [scope_key],
        reason=reason,
        priority=priority,
        trace_id=trace_id,
    )
    for normalized_scope_key in normalized_scope_keys:
        enqueued.append({"scope_type": scope_type, "scope_key": normalized_scope_key})


def coverage_report(connection: PostgresConnection) -> dict[str, Any]:
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
        "active_scope_types": list(ACTIVE_READ_MODEL_SCOPE_TYPES),
        "dirty": [dict(row) for row in dirty],
        "outbox": [dict(row) for row in outbox],
    }


if __name__ == "__main__":
    raise SystemExit(main())
