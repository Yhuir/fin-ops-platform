from __future__ import annotations

import argparse
from collections.abc import Sequence
import json
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import (
    PostgresConfigurationError,
    PostgresConnection,
    PostgresSettings,
)
from fin_ops_platform.services.postgres_repositories.page_business_audit import (
    PAGE_AUDIT_CONTRACTS,
    audit_page_canonical_data,
)
from fin_ops_platform.services.postgres_repositories.cost_statistics_page_audit import (
    COST_STATISTICS_AUDIT_DOMAIN_KEY,
    audit_cost_statistics_page,
)
from fin_ops_platform.tools.cli_reports import postgres_configuration_missing_report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read-only canonical page-data audit.")
    parser.add_argument(
        "domain_key",
        choices=sorted((*PAGE_AUDIT_CONTRACTS, COST_STATISTICS_AUDIT_DOMAIN_KEY)),
    )
    parser.add_argument("--json", action="store_true", help="Print JSON output. This tool is read-only either way.")
    parser.add_argument("--fail-on-issues", action="store_true", help="Return exit code 1 when blocking issues exist.")
    parser.add_argument("--tenant-id", default="default")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per issue code.")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        active_connection = connection or _connection_from_env()
    except PostgresConfigurationError as exc:
        report = postgres_configuration_missing_report(
            tool="audit_page_canonical_data",
            message=str(exc),
        )
        report["required_env"] = [
            "FIN_OPS_POSTGRES_READ_DATABASE_URL",
            "FIN_OPS_POSTGRES_DATABASE_URL",
            "DATABASE_URL",
        ]
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
        return 2
    if args.domain_key == COST_STATISTICS_AUDIT_DOMAIN_KEY:
        report = audit_cost_statistics_page(
            active_connection,
            tenant_id=str(args.tenant_id or "default"),
            example_limit=max(int(args.limit or 50), 1),
        )
    else:
        report = audit_page_canonical_data(
            active_connection,
            domain_key=str(args.domain_key),
            tenant_id=str(args.tenant_id or "default"),
            example_limit=max(int(args.limit or 50), 1),
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str), file=stdout)
    if args.fail_on_issues and int(report["summary"].get("blocking_issue_sample_count") or 0):
        return 1
    return 0


def _connection_from_env() -> PostgresConnection:
    settings = PostgresSettings.from_read_env() or PostgresSettings.from_env()
    connection = PostgresConnection(settings)
    connection.set_statement_timeout_ms(60_000)
    return connection


if __name__ == "__main__":
    raise SystemExit(main())
