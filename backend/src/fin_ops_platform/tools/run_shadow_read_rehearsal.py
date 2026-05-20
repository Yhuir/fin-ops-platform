from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Protocol, TextIO

from fin_ops_platform.services.cutover_preflight import redact_secret_text, redact_secret_values
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.shadow_read_psql_store import PsqlShadowReadStore
from fin_ops_platform.services.shadow_read_rehearsal import (
    ShadowReadRehearsalRunner,
    default_shadow_read_domain_specs,
)
from fin_ops_platform.services.state_store import ApplicationStateStore, default_data_dir


READ_ONLY_GUARD_ENV = "FIN_OPS_SHADOW_REHEARSAL_READ_ONLY"
RUN_ID_ENV = "FIN_OPS_SHADOW_REHEARSAL_RUN_ID"
DOMAINS_ENV = "FIN_OPS_SHADOW_REHEARSAL_DOMAINS"
LIMIT_ENV = "FIN_OPS_SHADOW_REHEARSAL_LIMIT"
OUTPUT_ENV = "FIN_OPS_SHADOW_REHEARSAL_OUTPUT"
DEFAULT_REPORT_DIR = Path("docs/database-migration/reports")
FORBIDDEN_CLI_FLAGS = {
    "--cutover",
    "--enable-dual-write",
    "--dual-write",
    "--write",
    "--restart-service",
    "--switch-backend",
}


class Runner(Protocol):
    def run(self) -> Any: ...


class StaticRunner:
    def __init__(self, report: dict[str, Any]) -> None:
        self._report = report

    def run(self) -> dict[str, Any]:
        return self._report


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run read-only app shadow-read rehearsal.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--markdown", action="store_true", help="Print Markdown report.")
    parser.add_argument("--output", type=Path, default=None, help="Write report artifact to this path.")
    parser.add_argument("--domains", default=None, help="Comma-separated domain whitelist.")
    parser.add_argument("--limit", type=int, default=None, help="Max mismatches per domain.")
    parser.add_argument("--primary-backend", choices=("local_pickle", "postgres", "mongo_readonly"), default="local_pickle")
    parser.add_argument("--shadow-backend", choices=("local_pickle", "postgres", "postgres_psql_json"), default="postgres")
    parser.add_argument("--psql-command", default=os.environ.get("FIN_OPS_SHADOW_REHEARSAL_PSQL_COMMAND", "psql"))
    parser.add_argument("--postgres-database", default=os.environ.get("FIN_OPS_SHADOW_REHEARSAL_POSTGRES_DATABASE", "fin_ops"))
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--require-read-only-guard", action="store_true")
    parser.add_argument("--production", action="store_true")
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    runner: Runner | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args_list = list(sys.argv[1:] if argv is None else argv)
    forbidden = [arg for arg in args_list if arg.split("=", 1)[0] in FORBIDDEN_CLI_FLAGS]
    if forbidden:
        print(f"ERROR: shadow-read rehearsal refuses write or cutover action flags: {', '.join(forbidden)}", file=stderr)
        return 2

    try:
        args = build_parser().parse_args(args_list)
        if runner is None:
            active_runner = build_runner_from_args(args)
        else:
            _enforce_read_only_guard(args)
            active_runner = runner
        report = _report_to_dict(active_runner.run())
        report = redact_secret_values(report)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must redact errors.
        print(f"ERROR: {redact_secret_text(str(exc))}", file=stderr)
        return 1

    output = args.output or _output_from_env_or_default(report, markdown=args.markdown and not args.json)
    if output is not None:
        _write_report(output, report, markdown=args.markdown and not args.json)

    if args.markdown and not args.json:
        print(render_markdown_report(report), file=stdout)
    else:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if str(report.get("gate_recommendation") or "").upper() == "PASS" else 1


def build_runner_from_args(args: argparse.Namespace) -> ShadowReadRehearsalRunner:
    _enforce_read_only_guard(args)
    limit = _limit_from_args(args)
    domains = _domains_from_args(args)
    data_dir = args.data_dir or default_data_dir()
    primary_store = _build_store(args.primary_backend, data_dir=data_dir)
    shadow_store = _build_store(
        args.shadow_backend,
        data_dir=data_dir,
        psql_command=args.psql_command,
        postgres_database=args.postgres_database,
    )
    specs = default_shadow_read_domain_specs(
        domains=domains,
        primary_source=args.primary_backend,
        shadow_source=args.shadow_backend,
        max_mismatches=limit,
    )
    return ShadowReadRehearsalRunner(
        primary_store=primary_store,
        shadow_store=shadow_store,
        domain_specs=specs,
        run_id=args.run_id or os.environ.get(RUN_ID_ENV),
        max_mismatches=limit,
    )


def render_markdown_report(report: dict[str, Any]) -> str:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    lines = [
        f"# Shadow-read rehearsal {report.get('run_id', '')}",
        "",
        f"- Gate: `{report.get('gate_recommendation', 'UNKNOWN')}`",
        f"- Primary backend: `{report.get('primary_backend', 'unknown')}`",
        f"- Shadow backend: `{report.get('shadow_backend', 'unknown')}`",
        f"- Total domains: `{summary.get('total_domains', 0)}`",
        f"- Compared domains: `{summary.get('compared_domains', 0)}`",
        f"- Matched domains: `{summary.get('matched_domains', 0)}`",
        f"- Mismatched domains: `{summary.get('mismatched_domains', 0)}`",
        f"- Primary errors: `{summary.get('primary_errors', 0)}`",
        f"- Shadow errors: `{summary.get('shadow_errors', 0)}`",
        "",
        "## Domains",
        "",
        "| Domain | Status | Mismatches | P0 | P1 | P2 |",
        "| --- | --- | ---: | ---: | ---: | ---: |",
    ]
    for result in report.get("domain_results", []):
        if not isinstance(result, dict):
            continue
        counts = result.get("severity_counts") if isinstance(result.get("severity_counts"), dict) else {}
        lines.append(
            "| {domain} | {status} | {mismatch_count} | {p0} | {p1} | {p2} |".format(
                domain=result.get("domain", ""),
                status=result.get("status", ""),
                mismatch_count=result.get("mismatch_count", 0),
                p0=counts.get("P0", 0),
                p1=counts.get("P1", 0),
                p2=counts.get("P2", 0),
            )
        )
    return "\n".join(lines)


def _build_store(
    backend: str,
    *,
    data_dir: Path,
    psql_command: str = "psql",
    postgres_database: str = "fin_ops",
) -> Any:
    if backend == "local_pickle":
        return ApplicationStateStore(data_dir, read_only=True)
    if backend == "postgres":
        return PostgresStateStore(data_dir=data_dir, connection=PostgresConnection(PostgresSettings.from_env()))
    if backend == "postgres_psql_json":
        return PsqlShadowReadStore(database=postgres_database, psql_command=psql_command)
    if backend == "mongo_readonly":
        if os.environ.get(READ_ONLY_GUARD_ENV) != "1":
            raise RuntimeError(f"{backend} requires {READ_ONLY_GUARD_ENV}=1.")
        store = ApplicationStateStore(data_dir, read_only=True)
        if store.storage_backend != "mongo":
            raise RuntimeError("mongo_readonly backend requires app Mongo state settings in data_dir/env.")
        return store
    raise RuntimeError(f"Unsupported shadow rehearsal backend {backend!r}.")


def _enforce_read_only_guard(args: argparse.Namespace) -> None:
    if args.production or args.require_read_only_guard:
        if os.environ.get(READ_ONLY_GUARD_ENV) != "1":
            raise RuntimeError(f"Production shadow-read rehearsal requires {READ_ONLY_GUARD_ENV}=1.")


def _limit_from_args(args: argparse.Namespace) -> int:
    raw_value = args.limit if args.limit is not None else os.environ.get(LIMIT_ENV) or 20
    try:
        value = int(raw_value)
    except (TypeError, ValueError) as exc:
        raise RuntimeError(f"{LIMIT_ENV} must be a positive integer.") from exc
    if value <= 0:
        raise RuntimeError("shadow rehearsal limit must be positive.")
    return value


def _domains_from_args(args: argparse.Namespace) -> list[str] | None:
    raw_value = args.domains if args.domains is not None else os.environ.get(DOMAINS_ENV)
    if not raw_value:
        return None
    domains = [item.strip() for item in str(raw_value).split(",") if item.strip()]
    if not domains:
        raise RuntimeError("shadow rehearsal domains cannot be empty.")
    return domains


def _output_from_env_or_default(report: dict[str, Any], *, markdown: bool) -> Path | None:
    output_env = os.environ.get(OUTPUT_ENV)
    if output_env:
        return Path(output_env)
    run_id = str(report.get("run_id") or "stage11")
    safe_run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", run_id).strip("-") or "stage11"
    suffix = "md" if markdown else "json"
    return DEFAULT_REPORT_DIR / f"{safe_run_id}.stage11.shadow-read.{suffix}"


def _write_report(path: Path, report: dict[str, Any], *, markdown: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if markdown:
        path.write_text(render_markdown_report(report) + "\n", encoding="utf-8")
    else:
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _report_to_dict(report: Any) -> dict[str, Any]:
    if hasattr(report, "to_dict"):
        report = report.to_dict()
    if not isinstance(report, dict):
        raise RuntimeError("shadow-read rehearsal runner returned a non-dict report.")
    return report


if __name__ == "__main__":
    raise SystemExit(main())
