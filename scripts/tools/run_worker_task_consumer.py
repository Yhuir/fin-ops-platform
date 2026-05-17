#!/usr/bin/env python3
from __future__ import annotations

import argparse
import asyncio
import os
import sys
from datetime import UTC, datetime
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_SRC = REPO_ROOT / "backend" / "src"
if str(BACKEND_SRC) not in sys.path:
    sys.path.insert(0, str(BACKEND_SRC))

from fin_ops_platform.app.server import build_application
from fin_ops_platform.services.settings_data_reset_worker import (
    ALLOW_DATA_RESET_WORKER_ENV,
    SETTINGS_DATA_RESET_TASK_TYPE,
    SettingsDataResetWorkerHandler,
)
from fin_ops_platform.services.state_store import default_data_dir
from fin_ops_platform.services.worker_task_consumer import consume_nats_forever
from fin_ops_platform.services.worker_task_postgres_repository import PostgresWorkerTaskRepository
from fin_ops_platform.services.worker_task_protocol import PermanentWorkerError, WorkerTaskContext, WorkerTaskEnvelope


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the PostgreSQL-backed NATS worker task consumer.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    parser.add_argument("--nats-url", default=os.environ.get("NATS_URL"))
    parser.add_argument("--subject", default=os.environ.get("WORKER_NATS_SUBJECT", "finops.jobs.>"))
    parser.add_argument("--stream", default=os.environ.get("WORKER_NATS_STREAM", "FINOPS_JOBS"))
    parser.add_argument("--durable", default=os.environ.get("WORKER_NATS_DURABLE", "finops-python-workers"))
    parser.add_argument("--worker-id", default=os.environ.get("WORKER_ID", f"python-worker-{os.getpid()}"))
    parser.add_argument("--batch-size", type=int, default=int(os.environ.get("WORKER_BATCH_SIZE", "1")))
    parser.add_argument("--data-dir", default=os.environ.get("FIN_OPS_DATA_DIR"))
    parser.add_argument(
        "--allow-data-reset-worker",
        action="store_true",
        help=f"Allow destructive settings_data_reset worker execution. Equivalent to {ALLOW_DATA_RESET_WORKER_ENV}=1.",
    )
    parser.add_argument(
        "--smoke-succeed",
        action="store_true",
        help="Mark consumed tasks succeeded. Use only for staging smoke tasks with disposable payloads.",
    )
    args = parser.parse_args()
    if not args.database_url:
        raise SystemExit("DATABASE_URL or --database-url is required.")
    if not args.nats_url:
        raise SystemExit("NATS_URL or --nats-url is required.")

    repository = PostgresWorkerTaskRepository.from_database_url(args.database_url)
    if args.smoke_succeed:
        handler = smoke_success_handler
    else:
        data_dir = Path(args.data_dir) if args.data_dir else default_data_dir()
        app = build_application(data_dir=data_dir)
        settings_data_reset_handler = SettingsDataResetWorkerHandler(
            reset_executor=app._execute_settings_data_reset,
            allow_destructive=args.allow_data_reset_worker or os.environ.get(ALLOW_DATA_RESET_WORKER_ENV) == "1",
        )
        handler = dispatch_worker_task_handler(settings_data_reset_handler)
    asyncio.run(
        consume_nats_forever(
            nats_url=args.nats_url,
            subject=args.subject,
            durable=args.durable,
            stream=args.stream,
            repository=repository,
            worker_id=args.worker_id,
            handler=handler,
            batch_size=args.batch_size,
        )
    )
    return 0


def dispatch_worker_task_handler(settings_data_reset_handler):
    def handler(envelope: WorkerTaskEnvelope, context: WorkerTaskContext) -> dict[str, object]:
        if envelope.task_type == SETTINGS_DATA_RESET_TASK_TYPE:
            return dict(settings_data_reset_handler(envelope, context))
        return unsupported_task_handler(envelope, context)

    return handler


def unsupported_task_handler(envelope: WorkerTaskEnvelope, _context: WorkerTaskContext) -> dict[str, object]:
    raise PermanentWorkerError(
        "WORKER_TASK_HANDLER_NOT_CONFIGURED",
        f"No Python worker handler is configured for task_type={envelope.task_type}.",
    )


def smoke_success_handler(envelope: WorkerTaskEnvelope, context: WorkerTaskContext) -> dict[str, object]:
    if envelope.task_type == SETTINGS_DATA_RESET_TASK_TYPE:
        raise PermanentWorkerError(
            "DATA_RESET_SMOKE_HANDLER_FORBIDDEN",
            "settings_data_reset tasks require the formal worker handler; --smoke-succeed is forbidden.",
        )
    context.heartbeat()
    return {
        "smoke_consumed": True,
        "task_type": envelope.task_type,
        "consumed_at": datetime.now(UTC).isoformat(),
    }


if __name__ == "__main__":
    raise SystemExit(main())
