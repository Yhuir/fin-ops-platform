from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.bank_account_balance_projection import BankAccountBalanceProjectionBuilder
from fin_ops_platform.services.bank_account_balance_read_model_refresh import BankAccountBalanceReadModelRefreshService
from fin_ops_platform.services.bank_account_balance_read_model_refresh_producer import BankAccountBalanceReadModelRefreshProducer
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.runtime_worker import RuntimeWorker, RuntimeWorkerConfig


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill or enqueue the bank account balance SQL read model.")
    parser.add_argument("--rebuild-now", action="store_true", help="Rebuild read_model.bank_account_balances synchronously.")
    parser.add_argument("--enqueue", action="store_true", help="Enqueue a bank_account_balance.read_model.refresh event.")
    parser.add_argument("--worker-drain", action="store_true", help="Drain bank_account_balance.read_model.refresh events after enqueueing.")
    parser.add_argument("--max-iterations", type=int, default=10)
    parser.add_argument("--dry-run", action="store_true", help="Print plan without rebuilding, enqueueing or draining.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    plan = {
        "scope_type": "bank_account_balance",
        "scope_key": "all",
        "rebuild_now": bool(args.rebuild_now),
        "enqueue": bool(args.enqueue),
        "worker_drain": bool(args.worker_drain),
        "dry_run": bool(args.dry_run),
    }
    rebuild_result: dict[str, object] | None = None
    enqueued = False
    drain_result: list[str] = []
    if args.dry_run:
        print(
            json.dumps(
                {
                    "plan": plan,
                    "rebuild_result": rebuild_result,
                    "enqueued": enqueued,
                    "drain_result": drain_result,
                },
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
        )
        return 0
    connection = PostgresConnection(PostgresSettings.from_env())
    queue = RuntimeQueueRepository(connection)
    refresh_gateway = ReadModelRefreshGateway(queue_repository=queue)
    refresh_producer = BankAccountBalanceReadModelRefreshProducer(refresh_gateway_provider=lambda: refresh_gateway)
    projection_builder = BankAccountBalanceProjectionBuilder(connection=connection)
    if args.rebuild_now:
        rebuild_result = projection_builder.rebuild_bank_account_balance_read_model()
    if args.enqueue:
        refresh_producer.enqueue_all(reason="bank_account_balance_backfill")
        enqueued = True
    if args.worker_drain:
        refresh_service = BankAccountBalanceReadModelRefreshService(
            projection_builder=projection_builder,
            queue_repository=queue,
        )
        worker = RuntimeWorker(
            queue_repository=queue,
            config=RuntimeWorkerConfig(
                worker_kind="bank-account-balance-read-model",
                event_types=["bank_account_balance.read_model.refresh"],
                max_iterations=args.max_iterations,
            ),
            handlers={"bank_account_balance.read_model.refresh": refresh_service.handle_runtime_event},
        )
        for _index in range(max(0, int(args.max_iterations))):
            result = worker.run_once()
            result_value = str(getattr(result, "value", result))
            drain_result.append(result_value)
            if result_value == "idle":
                break
    print(
        json.dumps(
            {
                "plan": plan,
                "rebuild_result": rebuild_result,
                "enqueued": enqueued,
                "drain_result": drain_result,
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
