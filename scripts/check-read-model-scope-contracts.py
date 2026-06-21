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

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings  # noqa: E402
from fin_ops_platform.services.postgres_repositories.read_model_scope_contracts import (  # noqa: E402
    PostgresReadModelScopeContractRepository,
)
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway  # noqa: E402
from fin_ops_platform.services.read_model_scope_contract import ReadModelScopeContractService  # noqa: E402
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Check read model refresh scope contract violations and classify current-effective outbox failures "
            "in PostgreSQL runtime state."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply the selected repair. Without --apply, the command is read-only.",
    )
    parser.add_argument(
        "--repair",
        choices=("cost-statistics", "orphaned-import-facts", "invalid-read-model-scopes"),
        default="cost-statistics",
        help="Repair/check target. Defaults to cost-statistics scope contract.",
    )
    parser.add_argument(
        "--no-enqueue-replacements",
        action="store_true",
        help="With --apply --repair cost-statistics, delete old rows without enqueueing normalized replacement refreshes.",
    )
    parser.add_argument("--reason", default="read_model_scope_contract_repair", help="Reason for audit and replacement refresh events.")
    parser.add_argument("--json", action="store_true", help="Print JSON. This is currently the only output format.")
    args = parser.parse_args(argv)

    connection = PostgresConnection(PostgresSettings.from_env())
    repository = PostgresReadModelScopeContractRepository(connection)
    service = ReadModelScopeContractService(repository)
    if args.repair == "orphaned-import-facts":
        report = service.repair_orphaned_import_fact_dirty_scopes(
            apply=bool(args.apply),
            reason=args.reason,
        )
    elif args.repair == "invalid-read-model-scopes":
        report = service.repair_invalid_read_model_refresh_scopes(
            apply=bool(args.apply),
            reason=args.reason,
        )
    elif args.apply:
        refresh_gateway = None
        if not args.no_enqueue_replacements:
            refresh_gateway = ReadModelRefreshGateway(queue_repository=RuntimeQueueRepository(connection))
        report = service.repair_cost_statistics_contract(
            apply=True,
            refresh_gateway=refresh_gateway,
            enqueue_replacements=not args.no_enqueue_replacements,
            reason=args.reason,
        )
    else:
        report = service.check_cost_statistics_contract()

    print(_json(report))
    if args.apply:
        return 0
    return 0 if report.get("ok") else 1


def _json(report: dict[str, Any]) -> str:
    return json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)


if __name__ == "__main__":
    raise SystemExit(main())
