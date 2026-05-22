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
    parser.add_argument("--run-worker", action="store_true", help="Drain runtime read model worker events in this process.")
    parser.add_argument("--max-iterations", type=int, default=200)
    parser.add_argument("--lock-timeout-seconds", type=int, default=30, help="Reclaim stale processing events older than this many seconds while draining.")
    parser.add_argument("--task-timeout-seconds", type=int, default=60, help="Fail and retry a single claimed event after this many wall-clock seconds.")
    parser.add_argument("--statement-timeout-seconds", type=int, default=30)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    connection = PostgresConnection(PostgresSettings.from_env())
    report: dict[str, Any] = {"actions": []}
    if args.backfill_oa_children:
        report["actions"].append(backfill_oa_children(connection))
    if args.enqueue_missing:
        report["actions"].append(enqueue_fact_scopes(connection))
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
        result = worker_main(worker_args)
        report["actions"].append({"action": "run_worker", "exit_code": result})
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


def enqueue_fact_scopes(connection: PostgresConnection) -> dict[str, Any]:
    queue = RuntimeQueueRepository(connection)
    months = fact_months(connection)
    enqueued: list[dict[str, str]] = []
    for month in months:
        for scope_type in ("workbench", "search", "tax_offset"):
            queue.enqueue_read_model_refresh(scope_type=scope_type, scope_key=month, reason="runtime_backfill")
            enqueued.append({"scope_type": scope_type, "scope_key": month})
        for project_scope in ("active", "all"):
            scope_key = f"{project_scope}:{month}"
            queue.enqueue_read_model_refresh(scope_type="cost_statistics", scope_key=scope_key, reason="runtime_backfill")
            enqueued.append({"scope_type": "cost_statistics", "scope_key": scope_key})
    for scope_key in PENDING_INVOICE_SCOPES:
        queue.enqueue_read_model_refresh(scope_type="pending_invoice", scope_key=scope_key, reason="runtime_backfill")
        enqueued.append({"scope_type": "pending_invoice", "scope_key": scope_key})
    queue.enqueue_read_model_refresh(scope_type="workbench", scope_key="all", reason="runtime_backfill")
    enqueued.append({"scope_type": "workbench", "scope_key": "all"})
    return {"action": "enqueue_missing", "month_count": len(months), "months": months, "enqueued_count": len(enqueued)}


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


def coverage_report(connection: PostgresConnection) -> dict[str, Any]:
    fact_scope_keys = set(fact_months(connection))
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
        "dirty": [dict(row) for row in dirty],
        "outbox": [dict(row) for row in outbox],
    }


if __name__ == "__main__":
    raise SystemExit(main())
