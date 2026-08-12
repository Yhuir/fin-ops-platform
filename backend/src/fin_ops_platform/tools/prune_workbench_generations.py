from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prune old non-active Workbench read model generations.")
    parser.add_argument("--keep-recent-generations-per-scope", type=int, default=1)
    parser.add_argument("--keep-days", type=int, default=0)
    parser.add_argument("--limit", type=int, default=500)
    parser.add_argument("--delete-batch-size", type=int, default=1)
    parser.add_argument("--statement-timeout-seconds", type=positive_int, default=60)
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Preview candidates without deleting them. This is the default.")
    mode.add_argument("--execute", action="store_true", help="Delete eligible non-active generations.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO | None = None) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    connection = PostgresConnection(PostgresSettings.from_env())
    connection.set_statement_timeout_ms(args.statement_timeout_seconds * 1000)
    repository = PostgresReadModelRepository(connection)
    result = repository.prune_workbench_generations(
        keep_recent_generations_per_scope=args.keep_recent_generations_per_scope,
        keep_days=args.keep_days,
        limit=args.limit,
        dry_run=not bool(args.execute),
        delete_batch_size=args.delete_batch_size,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
