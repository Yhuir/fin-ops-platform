from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Protocol, TextIO

from fin_ops_platform.services.cutover_preflight import (
    DEFAULT_DATABASE_URL_ENV,
    CutoverPreflightConfigurationError,
    build_checker_from_env,
    redact_secret_text,
    redact_secret_values,
)


FORBIDDEN_CLI_FLAGS = {
    "--cutover",
    "--enable-dual-write",
    "--restart-service",
    "--write",
    "--production-write",
}


class Checker(Protocol):
    def run(self) -> dict[str, Any]: ...


class StaticChecker:
    def __init__(self, report: dict[str, Any]) -> None:
        self._report = report

    def run(self) -> dict[str, Any]:
        return self._report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only PostgreSQL cutover preflight checks.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument(
        "--require-backup-confirmation",
        action="store_true",
        help="Block unless FIN_OPS_CUTOVER_BACKUP_CONFIRMED is truthy.",
    )
    parser.add_argument(
        "--no-production-writes",
        action="store_true",
        default=True,
        help="Read-only guard. Defaults to true.",
    )
    parser.add_argument(
        "--database-url-env",
        default=DEFAULT_DATABASE_URL_ENV,
        help="Environment variable containing the PostgreSQL URL.",
    )
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    checker: Checker | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args_list = list(sys.argv[1:] if argv is None else argv)
    forbidden = [arg for arg in args_list if arg.split("=", 1)[0] in FORBIDDEN_CLI_FLAGS]
    if forbidden:
        print(f"ERROR: cutover preflight refuses write or cutover action flags: {', '.join(forbidden)}", file=stderr)
        return 2

    try:
        args = build_parser().parse_args(args_list)
    except SystemExit as exc:
        return int(exc.code or 0)

    try:
        active_checker = checker or build_checker_from_env(
            database_url_env=args.database_url_env,
            require_backup_confirmation=args.require_backup_confirmation,
            no_production_writes=args.no_production_writes,
        )
        report = redact_secret_values(active_checker.run())
    except CutoverPreflightConfigurationError as exc:
        print(f"ERROR: {exc}", file=stderr)
        return 1
    except Exception as exc:  # noqa: BLE001 - CLI boundary must return a secret-safe error.
        print(f"ERROR: {redact_secret_text(str(exc))}", file=stderr)
        return 1

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    else:
        print_human_report(report, stdout=stdout)
    return 0 if report.get("status") == "pass" else 1


def print_human_report(report: dict[str, Any], *, stdout: TextIO) -> None:
    print(f"status: {report.get('status')}", file=stdout)
    postgres = report.get("postgres") if isinstance(report.get("postgres"), dict) else {}
    print(f"postgres: {postgres.get('connectivity')} schema={postgres.get('schema_version')}", file=stdout)
    print(f"schema_migrations: {postgres.get('schema_migrations_table')}", file=stdout)
    guards = report.get("guards") if isinstance(report.get("guards"), dict) else {}
    print(f"no_production_writes: {guards.get('no_production_writes')}", file=stdout)


if __name__ == "__main__":
    raise SystemExit(main())
