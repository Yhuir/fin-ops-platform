from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.bank_detail_read_model_refresh import BankDetailReadModelRefreshService
from fin_ops_platform.services.bank_detail_sql_projection import BankDetailSqlProjectionBuilder
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill or enqueue bank detail SQL read model refresh scopes.")
    parser.add_argument("--scope-key", action="append", default=[], help="YYYY-MM scope to inspect or enqueue. Repeatable.")
    parser.add_argument("--enqueue-missing", action="store_true", help="Enqueue missing/stale/schema-mismatch month scopes.")
    parser.add_argument("--enqueue-all", action="store_true", help="Enqueue the umbrella all scope; worker will fan out to month shards.")
    parser.add_argument("--worker-drain", action="store_true", help="Drain bank_detail.read_model.refresh events after enqueueing.")
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without enqueueing or draining.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.dry_run and args.scope_key:
        scope_keys = _scope_keys(args.scope_key, projection_builder=None)
        plan = {
            "scope_keys": scope_keys,
            "enqueue_missing": bool(args.enqueue_missing),
            "enqueue_all": bool(args.enqueue_all),
            "worker_drain": bool(args.worker_drain),
            "dry_run": bool(args.dry_run),
        }
        print(json.dumps({"plan": plan, "enqueued_scope_keys": [], "drain_result": []}, ensure_ascii=False, indent=2, sort_keys=True))
        return 0
    connection = PostgresConnection(PostgresSettings.from_env())
    queue = RuntimeQueueRepository(connection)
    refresh_gateway = ReadModelRefreshGateway(queue_repository=queue)
    projection_builder = BankDetailSqlProjectionBuilder(connection=connection)
    scope_keys = _scope_keys(args.scope_key, projection_builder)
    plan = {
        "scope_keys": scope_keys,
        "enqueue_missing": bool(args.enqueue_missing),
        "enqueue_all": bool(args.enqueue_all),
        "worker_drain": bool(args.worker_drain),
        "dry_run": bool(args.dry_run),
    }
    enqueued: list[str] = []
    if not args.dry_run:
        if args.enqueue_all:
            refresh_gateway.enqueue_one("bank_detail", "all", reason="bank_detail_backfill_all")
            enqueued.append("all")
        if args.enqueue_missing:
            for scope_key in scope_keys:
                refresh_gateway.enqueue_one("bank_detail", scope_key, reason="bank_detail_backfill_missing")
                enqueued.append(scope_key)
    drain_result: list[str] = []
    if args.worker_drain and not args.dry_run:
        refresh_service = BankDetailReadModelRefreshService(projection_builder=projection_builder, queue_repository=queue)
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_kind="bank-detail-read-model",
                event_types=["bank_detail.read_model.refresh"],
                max_iterations=args.max_iterations,
            ),
            handlers={"bank_detail.read_model.refresh": refresh_service.handle_runtime_event},
        )
        for _index in range(max(0, int(args.max_iterations))):
            result = worker.run_once()
            result_value = str(getattr(result, "value", result))
            drain_result.append(result_value)
            if result_value == "idle":
                break
    print(json.dumps({"plan": plan, "enqueued_scope_keys": enqueued, "drain_result": drain_result}, ensure_ascii=False, indent=2, sort_keys=True))
    return 0


def _scope_keys(raw_scope_keys: list[str], projection_builder: BankDetailSqlProjectionBuilder | None) -> list[str]:
    explicit = [str(scope_key).strip() for scope_key in list(raw_scope_keys or []) if str(scope_key).strip()]
    if explicit:
        return explicit
    if projection_builder is None:
        return ["all"]
    return projection_builder.list_bank_detail_scope_shards("all")


if __name__ == "__main__":
    raise SystemExit(main())
