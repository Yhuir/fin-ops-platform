from __future__ import annotations

import argparse
from collections.abc import Callable, Sequence
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


AuditFunction = Callable[..., dict[str, Any]]


def run_invoice_read_model_audit(
    argv: Sequence[str] | None,
    *,
    tool_name: str,
    description: str,
    audit: AuditFunction,
    connection: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--json", action="store_true", help="Print JSON output. This tool is read-only either way.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when blocking samples exist.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue code.")
    args = parser.parse_args(argv)
    output = stdout or sys.stdout
    try:
        active_connection = connection or _connection_from_env()
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(tool=tool_name, message=str(exc))
        report["required_env"] = [
            "FIN_OPS_POSTGRES_READ_DATABASE_URL",
            "FIN_OPS_POSTGRES_DATABASE_URL",
            "DATABASE_URL",
        ]
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=output)
        return 2
    report = audit(
        active_connection,
        tenant_id=str(args.tenant_id or "default"),
        example_limit=max(int(args.limit or 50), 1),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=output)
    if args.fail_on_issues and int(report["summary"].get("blocking_issue_sample_count") or 0):
        return 1
    return 0


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(60_000)
    return connection
