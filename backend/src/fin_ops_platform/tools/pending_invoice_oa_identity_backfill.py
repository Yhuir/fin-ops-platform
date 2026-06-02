from __future__ import annotations

import argparse
import json
from collections.abc import Sequence

from fin_ops_platform.services.pending_invoice_oa_identity_backfill import PendingInvoiceOaIdentityBackfillService
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.pending_invoice_oa_identity import (
    PendingInvoiceOaIdentityRepository,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and enqueue pending invoice OA identity read-model repairs.")
    parser.add_argument("--enqueue", action="store_true", help="Enqueue affected pending_invoice read model scopes.")
    parser.add_argument("--reason", default="pending_invoice_oa_identity_backfill")
    parser.add_argument("--json", action="store_true")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    queue = RuntimeQueueRepository(connection)
    repository = PendingInvoiceOaIdentityRepository(connection)
    service = PendingInvoiceOaIdentityBackfillService(repository=repository, queue_repository=queue)
    report = service.inspect()
    report["enqueued_scope_keys"] = service.enqueue_affected_scopes(reason=args.reason) if args.enqueue else []
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
