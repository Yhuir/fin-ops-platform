from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.workbench_page_audit import (
    audit_workbench_relation_display,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Read-only unified page Audit for active Workbench relation display generations."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report. The audit is always read-only.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 for blocking issues.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue code.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    _ = stderr
    args = build_parser().parse_args(argv)
    active_connection = connection or _connection_from_env()
    report = audit_workbench_relation_display(
        active_connection,
        tenant_id=str(args.tenant_id or "default"),
        example_limit=max(int(args.limit or 50), 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout or sys.stdout)
    return 1 if args.fail_on_issues and int(report["summary"].get("blocking_issue_count") or 0) else 0


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(30_000)
    return connection


if __name__ == "__main__":
    raise SystemExit(main())
