#!/usr/bin/env python3
"""Preflight checks for P0 platform API Python-vs-Axum shadow validation."""

from __future__ import annotations

import argparse
from dataclasses import dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Any, Mapping
from uuid import UUID


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from api_shadow_validate import validate_shadow_fixture  # noqa: E402


PLATFORM_ENDPOINT_IDS = [
    "background-job-acknowledge-request",
    "workbench-settings-write-contract",
    "workbench-settings-project-sync-request",
    "workbench-settings-project-create-request",
    "workbench-settings-project-delete-request",
    "settings-data-reset-create-job",
    "settings-data-reset-direct-queues-job",
    "projects-hub-list",
    "projects-create-manual-profile",
    "project-detail",
    "project-assign-request",
    "ledgers-list",
    "ledger-detail",
    "ledger-status-update",
    "reminders-list",
    "reminder-run-request",
]
DEFAULT_FIXTURE = ROOT / "docs" / "dev" / "api-fixtures" / "business-api-shadow-validation.json"
DEFAULT_OUTPUT_DIR = ROOT / "docs" / "operations" / "backend-refactor"
POSTGRES_TARGET_MAJOR_MIN = 16
SENSITIVE_ENV_HINTS = ("PASSWORD", "SECRET", "TOKEN", "KEY", "URL")
RUNTIME_VARIABLE_PATTERN = re.compile(r"\$\{([A-Z0-9_]+)\}")
DEFAULT_AXUM_ADMIN_USERNAME = "YNSYLP005"
DEFAULT_AXUM_REQUIRED_PERMISSION = "finops:app:view"
TRUSTED_HEADERS_ADAPTER_VALUES = {"trusted_headers", "trusted-header", "headers"}
LOCAL_FIXABLE = "local_fixable"
ENVIRONMENT_BLOCKER = "environment_blocker"
PYTHON_SHADOW_AUTH_ENV = {
    "FIN_OPS_DEV_ALLOW_LOCAL_SESSION": "0",
    "FIN_OPS_TEST_DEFAULT_AUTH": "0",
}
ACCEPTED_OA_IDENTITY_SOURCES = {
    "staging_oa": {
        "environment": "staging",
        "description": "Non-production OA environment used for runtime shadow identity and password verification.",
    },
    "test_oa": {
        "environment": "staging",
        "description": "Non-production OA test environment used for runtime shadow identity and password verification.",
    },
    "production_oa_test_user": {
        "environment": "production",
        "description": (
            "Production OA test user accepted by updated Prompt04 Prompt 2 criteria; "
            "business writes must still target isolated local/shadow Python and Axum data stores."
        ),
    },
}
RUNTIME_ENVIRONMENT_VARIABLES = [
    {
        "name": "FIN_OPS_SHADOW_PYTHON_BASE_URL",
        "required_for": "legacy Python runtime shadow target and /health probe",
        "sensitive": False,
        "source": "environment",
    },
    {
        "name": "FIN_OPS_SHADOW_AXUM_BASE_URL",
        "required_for": "Axum runtime shadow target and /healthz /readyz probes",
        "sensitive": False,
        "source": "environment",
    },
    {
        "name": "DATABASE_URL",
        "required_for": "PostgreSQL 16/17 migration, seed apply, seed fact probes, and local Axum startup",
        "sensitive": True,
        "source": "environment",
    },
    {
        "name": "FIN_OPS_SHADOW_OA_TOKEN",
        "required_for": "legacy Python Authorization header and platform API auth parity",
        "sensitive": True,
        "source": "fixture",
    },
    {
        "name": "FIN_OPS_SHADOW_OA_PASSWORD",
        "required_for": "settings data reset runtime samples",
        "sensitive": True,
        "source": "fixture",
    },
    {
        "name": "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE",
        "required_for": "audit of OA identity source used by runtime shadow",
        "sensitive": False,
        "source": "environment",
        "allowed_values": sorted(ACCEPTED_OA_IDENTITY_SOURCES),
    },
    {
        "name": "FIN_OPS_OA_IDENTITY_ADAPTER",
        "required_for": "local Axum trusted-header identity resolution",
        "sensitive": False,
        "source": "environment",
        "required_value": "trusted_headers",
        "alternative": "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED=trusted_headers",
    },
    {
        "name": "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED",
        "required_for": "managed Axum shadow service trusted-header attestation",
        "sensitive": False,
        "source": "environment",
        "required_value": "trusted_headers",
        "alternative": "FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers",
    },
    {
        "name": "BACKGROUND_JOB_ID",
        "required_for": "background-job-acknowledge-request",
        "sensitive": False,
        "source": "seed",
    },
    {
        "name": "BANK_TRANSACTION_ID",
        "required_for": "project-assign-request",
        "sensitive": False,
        "source": "seed",
    },
    {
        "name": "LEDGER_ID",
        "required_for": "ledger-detail and ledger-status-update",
        "sensitive": False,
        "source": "seed",
    },
    {
        "name": "PROJECT_ID",
        "required_for": "project-detail and project-assign-request",
        "sensitive": False,
        "source": "seed",
    },
    {
        "name": "PROJECT_DELETE_ID",
        "required_for": "workbench-settings-project-delete-request",
        "sensitive": False,
        "source": "seed",
    },
    {
        "name": "SHADOW_RUN_ID",
        "required_for": "runtime write isolation, idempotency keys, and report correlation",
        "sensitive": False,
        "source": "runtime",
    },
]
LOCAL_RUNTIME_ARTIFACTS = [
    {
        "name": "preflight_script",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_preflight.py",
        "purpose": "repeatable preflight report generation",
    },
    {
        "name": "runtime_script",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_runtime.py",
        "purpose": "health-gated runtime shadow execution",
    },
    {
        "name": "seed_script",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_seed.py",
        "purpose": "deterministic PostgreSQL seed SQL and env exports",
    },
    {
        "name": "legacy_seed_script",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_legacy_seed.py",
        "purpose": "deterministic isolated legacy Python data-dir seed",
    },
    {
        "name": "legacy_reload_script",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_legacy_reload.py",
        "purpose": "token-gated reload of the isolated legacy Python shadow process after reseed",
    },
    {
        "name": "reseed_hook",
        "path": ROOT / "scripts" / "tools" / "platform_shadow_reseed_hook.py",
        "purpose": "runtime before-group cleanup, PostgreSQL seed, legacy seed, and legacy reload orchestration",
    },
    {
        "name": "shadow_validator",
        "path": ROOT / "scripts" / "tools" / "api_shadow_validate.py",
        "purpose": "Python-vs-Axum runtime comparison",
    },
    {
        "name": "python_start_script",
        "path": ROOT / "scripts" / "start-backend.sh",
        "purpose": "legacy Python shadow service startup",
    },
]
PRIMARY_AUTH_HEADERS = {
    "authorization": "Bearer token accepted by the legacy Python service.",
    "x-fin-ops-oa-user-id": "Trusted Axum OA user id header.",
    "x-fin-ops-oa-username": "Trusted Axum OA username header.",
    "x-fin-ops-oa-permissions": "Trusted Axum OA permissions header.",
}
ADMIN_ROUTE_SPECS = (
    ("POST", "/api/workbench/settings", "exact"),
    ("POST", "/api/workbench/settings/projects", "prefix"),
    ("DELETE", "/api/workbench/settings/projects", "prefix"),
    ("POST", "/api/workbench/settings/data-reset", "prefix"),
    ("POST", "/projects", "exact"),
)
SEED_REQUIREMENT_BY_VARIABLE = {
    "BACKGROUND_JOB_ID": {
        "kind": "postgres_fact_id",
        "description": "System-visible worker task that can be acknowledged by the shadow actor.",
        "postgres_fact_source": "job.worker_tasks",
        "legacy_fact_source": "legacy Python background job store / app-health background job projection",
        "probe_sql": (
            "select exists (select 1 from job.worker_tasks "
            "where id = '{value}'::uuid and visibility = 'system')"
        ),
    },
    "PROJECT_ID": {
        "kind": "postgres_fact_id",
        "description": "Active project profile used by project detail, project deletion, and project assignment.",
        "postgres_fact_source": "app.project_profiles",
        "legacy_fact_source": "legacy Python workbench settings projects payload",
        "probe_sql": (
            "select exists (select 1 from app.project_profiles "
            "where id = '{value}'::uuid and project_status = 'active')"
        ),
    },
    "PROJECT_DELETE_ID": {
        "kind": "postgres_fact_id",
        "description": "Dedicated active project profile used only by the project deletion shadow case.",
        "postgres_fact_source": "app.project_profiles",
        "legacy_fact_source": "legacy Python workbench settings projects payload",
        "probe_sql": (
            "select exists (select 1 from app.project_profiles "
            "where id = '{value}'::uuid and project_status = 'active')"
        ),
    },
    "BANK_TRANSACTION_ID": {
        "kind": "postgres_fact_id",
        "description": "Bank transaction target for project assignment object validation.",
        "postgres_fact_source": "app.bank_transactions",
        "legacy_fact_source": "legacy Python bank transaction / workbench row state",
        "probe_sql": "select exists (select 1 from app.bank_transactions where id = '{value}'::uuid)",
    },
    "LEDGER_ID": {
        "kind": "postgres_fact_id",
        "description": "Open ledger target for detail and status update shadow cases.",
        "postgres_fact_source": "app.ledgers",
        "legacy_fact_source": "legacy Python ledger service state",
        "probe_sql": (
            "select exists (select 1 from app.ledgers "
            "where id = '{value}'::uuid and status = 'open')"
        ),
    },
    "FIN_OPS_SHADOW_OA_TOKEN": {
        "kind": "auth_secret",
        "description": "Bearer token or equivalent local shadow token accepted by both Python and Axum.",
        "postgres_fact_source": None,
        "legacy_fact_source": "legacy Python OA/session auth configuration",
    },
    "FIN_OPS_SHADOW_OA_PASSWORD": {
        "kind": "auth_secret",
        "description": "Password sample required by legacy data reset contract; must come from the accepted shadow OA identity source.",
        "postgres_fact_source": None,
        "legacy_fact_source": "legacy Python data reset password validation path",
    },
    "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE": {
        "kind": "auth_identity_source",
        "description": "Source of OA token/password used by runtime shadow.",
        "postgres_fact_source": None,
        "legacy_fact_source": "runtime shadow operator declaration",
    },
    "SHADOW_RUN_ID": {
        "kind": "run_correlation",
        "description": "Unique run suffix used to keep idempotency keys and generated project codes isolated.",
        "postgres_fact_source": None,
        "legacy_fact_source": "shadow validation runtime only",
    },
}


@dataclass(frozen=True)
class CommandResult:
    command: list[str]
    status: str
    returncode: int | None
    stdout: str
    stderr: str

    def to_report(self) -> dict[str, Any]:
        return {
            "command": [redact_sensitive_text(part) for part in self.command],
            "status": self.status,
            "returncode": self.returncode,
            "stdout": self.stdout.strip(),
            "stderr": redact_sensitive_text(self.stderr.strip()),
        }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--output-dir", type=Path, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--report-date", help="YYYYMMDD; defaults to current UTC date")
    parser.add_argument("--python-base-url", default=os.environ.get("FIN_OPS_SHADOW_PYTHON_BASE_URL"))
    parser.add_argument("--axum-base-url", default=os.environ.get("FIN_OPS_SHADOW_AXUM_BASE_URL"))
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    parser.add_argument("--skip-python-check", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_preflight_report(args)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    json_path = args.output_dir / f"p0-platform-shadow-preflight-{report['report_date']}.json"
    md_path = args.output_dir / f"p0-platform-shadow-preflight-{report['report_date']}.md"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    md_path.write_text(render_markdown(report), encoding="utf-8")
    print(json.dumps({"status": report["status"], "json_path": str(json_path), "markdown_path": str(md_path)}, ensure_ascii=False))
    return 0 if report["status"] == "GO" else 2


def build_preflight_report(args: argparse.Namespace) -> dict[str, Any]:
    report_date = args.report_date or datetime.now(UTC).strftime("%Y%m%d")
    fixture_validation = validate_shadow_fixture(
        args.fixture,
        endpoint_ids=set(PLATFORM_ENDPOINT_IDS),
    )
    fixture_static_checks = collect_fixture_static_checks(
        args.fixture,
        endpoint_ids=set(PLATFORM_ENDPOINT_IDS),
    )
    runtime_variables = collect_runtime_variable_requirements(
        args.fixture,
        endpoint_ids=set(PLATFORM_ENDPOINT_IDS),
        environ=os.environ,
    )
    seed_requirements = collect_seed_requirements(
        runtime_variables,
        database_url_env=args.database_url_env,
        environ=os.environ,
    )
    auth_requirements = collect_auth_requirements(
        args.fixture,
        endpoint_ids=set(PLATFORM_ENDPOINT_IDS),
        axum_base_url=args.axum_base_url,
        environ=os.environ,
    )
    local_runtime_diagnostics = collect_local_runtime_diagnostics(args.fixture, output_dir=args.output_dir)
    python_check = None if args.skip_python_check else run_python_readiness_check()
    psql_version = command(["psql", "--version"])
    local_postgres_server = collect_local_postgres_server()
    docker_info = command(["docker", "info", "--format", "{{.ServerVersion}}"])
    sqlx_version = command(["cargo", "sqlx", "--version"], cwd=ROOT / "rust" / "fin-ops-api")

    database_url_present = bool(os.environ.get(args.database_url_env))
    postgres_major = parse_postgres_major(psql_version.stdout)
    findings = findings_for_report(
        fixture_validation=fixture_validation,
        fixture_static_checks=fixture_static_checks,
        python_base_url=args.python_base_url,
        axum_base_url=args.axum_base_url,
        database_url_env=args.database_url_env,
        database_url_present=database_url_present,
        postgres_major=postgres_major,
        psql_version=psql_version,
        local_postgres_server=local_postgres_server,
        docker_info=docker_info,
        sqlx_version=sqlx_version,
        python_check=python_check,
        runtime_variables=runtime_variables,
        seed_requirements=seed_requirements,
        auth_requirements=auth_requirements,
        local_runtime_diagnostics=local_runtime_diagnostics,
    )
    input_plan = runtime_shadow_input_plan(
        runtime_variables=runtime_variables,
        seed_requirements=seed_requirements,
        auth_requirements=auth_requirements,
        args=args,
    )
    status = "GO" if not findings else "NO_GO"
    return {
        "report": f"p0-platform-shadow-preflight-{report_date}",
        "report_date": report_date,
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "status": status,
        "scope": "P0 platform API runtime shadow preflight for Python vs Axum contract equivalence.",
        "fixture": str(args.fixture),
        "platform_endpoint_ids": PLATFORM_ENDPOINT_IDS,
        "inputs": {
            "python_base_url_present": bool(args.python_base_url),
            "axum_base_url_present": bool(args.axum_base_url),
            "database_url_env": args.database_url_env,
            "database_url_present": database_url_present,
            "target_postgres_major_min": POSTGRES_TARGET_MAJOR_MIN,
        },
        "fixture_validation": fixture_validation,
        "fixture_static_checks": fixture_static_checks,
        "runtime_variables": runtime_variables,
        "seed_requirements": seed_requirements,
        "auth_requirements": auth_requirements,
        "local_runtime_diagnostics": local_runtime_diagnostics,
        "runtime_shadow_input_plan": input_plan,
        "out_of_scope_dependencies": out_of_scope_dependencies(),
        "blocker_summary": blocker_summary(findings),
        "environment_checks": {
            "python_readiness_check": python_check.to_report() if python_check else {"status": "SKIPPED"},
            "psql_version": psql_version.to_report(),
            "postgres_major_detected": postgres_major,
            "local_postgres_server": local_postgres_server,
            "docker_info": docker_info.to_report(),
            "cargo_sqlx_version": sqlx_version.to_report(),
        },
        "findings": findings,
        "next_runtime_shadow_command": runtime_shadow_command(args),
    }


def findings_for_report(
    *,
    fixture_validation: dict[str, Any],
    fixture_static_checks: dict[str, Any] | None = None,
    python_base_url: str | None,
    axum_base_url: str | None,
    database_url_env: str,
    database_url_present: bool,
    postgres_major: int | None,
    psql_version: CommandResult,
    local_postgres_server: dict[str, Any] | None = None,
    docker_info: CommandResult,
    sqlx_version: CommandResult,
    python_check: CommandResult | None,
    runtime_variables: dict[str, Any] | None = None,
    seed_requirements: dict[str, Any] | None = None,
    auth_requirements: dict[str, Any] | None = None,
    local_runtime_diagnostics: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    findings: list[dict[str, str]] = []
    if fixture_validation.get("status") != "GO":
        findings.append(
            {
                "code": "PLATFORM_SHADOW_FIXTURE_NO_GO",
                "severity": "blocking",
                "blocker_type": LOCAL_FIXABLE,
                "message": "Scoped platform shadow fixture validation did not pass.",
                "required_action": "Fix business-api-shadow-validation.json before runtime shadow.",
            }
        )
    if fixture_static_checks is not None and fixture_static_checks.get("status") != "GO":
        findings.append(
            {
                "code": "PLATFORM_SHADOW_FIXTURE_STATIC_CONFLICT",
                "severity": "blocking",
                "blocker_type": LOCAL_FIXABLE,
                "message": "Scoped platform shadow fixture has static write-order conflicts.",
                "required_action": "Fix fixture idempotency keys, destructive target reuse, or mutually exclusive write actions before runtime shadow.",
            }
        )
    if not python_base_url:
        findings.append(
            {
                "code": "PYTHON_BASE_URL_MISSING",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": "FIN_OPS_SHADOW_PYTHON_BASE_URL or --python-base-url is required for runtime shadow.",
                "required_action": "Start isolated Python legacy service and provide its base URL.",
            }
        )
    if not axum_base_url:
        findings.append(
            {
                "code": "AXUM_BASE_URL_MISSING",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": "FIN_OPS_SHADOW_AXUM_BASE_URL or --axum-base-url is required for runtime shadow.",
                "required_action": "Start isolated Axum service backed by migrated PostgreSQL facts and provide its base URL.",
            }
        )
    if not database_url_present and not axum_base_url:
        findings.append(
            {
                "code": "AXUM_DATABASE_URL_MISSING",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": f"{database_url_env} is not set; a local Axum shadow service cannot be started from this shell.",
                "required_action": f"Provide a disposable PostgreSQL 16/17 shadow database through {database_url_env}, or provide --axum-base-url for an already running Axum shadow service.",
            }
        )
    if psql_version.status != "GO":
        findings.append(
            {
                "code": "PSQL_CLIENT_UNAVAILABLE",
                "severity": "blocking",
                "blocker_type": LOCAL_FIXABLE,
                "message": "psql is unavailable, so local PostgreSQL version and connectivity cannot be inspected.",
                "required_action": "Install PostgreSQL client tools or use a managed staging database with explicit Axum base URL.",
            }
        )
    elif postgres_major is not None and postgres_major < POSTGRES_TARGET_MAJOR_MIN:
        findings.append(
            {
                "code": "LOCAL_POSTGRES_VERSION_TOO_OLD",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": f"Local psql reports PostgreSQL {postgres_major}; migrations require PostgreSQL {POSTGRES_TARGET_MAJOR_MIN}+ because 0002 uses NULLS NOT DISTINCT.",
                "required_action": "Use PostgreSQL 16/17 for migration dry-run and Axum shadow service.",
            }
        )
    if local_postgres_server is not None:
        server_major = local_postgres_server.get("server_major")
        if (
            not database_url_present
            and not axum_base_url
            and local_postgres_server.get("reachable") is True
            and isinstance(server_major, int)
            and server_major < POSTGRES_TARGET_MAJOR_MIN
        ):
            findings.append(
                {
                    "code": "LOCAL_POSTGRES_SERVER_TOO_OLD",
                    "severity": "blocking",
                    "blocker_type": ENVIRONMENT_BLOCKER,
                    "message": (
                        f"Default local PostgreSQL service on localhost:5432 is {local_postgres_server.get('server_version')}; "
                        f"runtime shadow migrations require PostgreSQL {POSTGRES_TARGET_MAJOR_MIN}+."
                    ),
                    "required_action": (
                        "Start a PostgreSQL 16/17 shadow server and set DATABASE_URL to that disposable database. "
                        "A PostgreSQL 17 client alone is not sufficient when localhost:5432 serves an older cluster."
                    ),
                }
            )
    if docker_info.status != "GO" and not database_url_present and not axum_base_url:
        findings.append(
            {
                "code": "DOCKER_DAEMON_UNAVAILABLE",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": "Docker daemon is unavailable, so a temporary PostgreSQL 16/17 shadow database cannot be started locally.",
                "required_action": "Start Docker Desktop or provide a managed PostgreSQL 16/17 staging DATABASE_URL.",
            }
        )
    if python_check is not None and python_check.status != "GO":
        findings.append(
            {
                "code": "PYTHON_READINESS_CHECK_FAILED",
                "severity": "blocking",
                "blocker_type": LOCAL_FIXABLE,
                "message": "Legacy Python backend readiness check failed.",
                "required_action": "Fix Python backend startup/readiness before running runtime shadow.",
            }
        )
    missing_runtime_variables = []
    if runtime_variables is not None:
        missing_runtime_variables = runtime_variables.get("missing_variables") or []
    if missing_runtime_variables:
        findings.append(
            {
                "code": "PLATFORM_FIXTURE_VARIABLES_MISSING",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": "Platform runtime shadow fixture still contains unresolved variables: "
                + ", ".join(missing_runtime_variables),
                "required_action": (
                    "Seed equivalent facts in both legacy Python/Mongo and Axum PostgreSQL shadow environments. "
                    "For PostgreSQL, run scripts/tools/platform_shadow_seed.py --run-id <unique-run-id> --apply after migrations, "
                    "then source the generated env file and provide FIN_OPS_SHADOW_* secrets before runtime shadow."
                ),
            }
        )
    if seed_requirements is not None and seed_requirements.get("status") == "NO_GO":
        failed = [
            item.get("variable")
            for item in seed_requirements.get("requirements") or []
            if item.get("probe", {}).get("status") == "NO_GO"
        ]
        if failed:
            findings.append(
                {
                    "code": "PLATFORM_SEED_FACTS_MISSING",
                    "severity": "blocking",
                    "blocker_type": ENVIRONMENT_BLOCKER,
                    "message": "PostgreSQL shadow seed probes failed for: " + ", ".join(map(str, failed)),
                    "required_action": (
                        "Load equivalent platform seed facts into both legacy and PostgreSQL shadow stores, "
                        "then rerun preflight before runtime shadow."
                    ),
                }
            )
    if auth_requirements is not None and auth_requirements.get("status") != "GO":
        blockers = [
            item.get("code")
            for item in auth_requirements.get("checks") or []
            if item.get("status") == "NO_GO"
        ]
        findings.append(
            {
                "code": "PLATFORM_AUTH_REQUIREMENTS_NO_GO",
                "severity": "blocking",
                "blocker_type": ENVIRONMENT_BLOCKER,
                "message": "Platform runtime shadow auth prerequisites are not satisfied: "
                + ", ".join(map(str, blockers or ["unknown_auth_blocker"])),
                "required_action": (
                    "Run Axum with FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers, keep the fixture trusted OA headers, "
                    "and provide a Python-accepted FIN_OPS_SHADOW_OA_TOKEN before runtime shadow."
                ),
            }
            )
    if local_runtime_diagnostics is not None and local_runtime_diagnostics.get("status") != "GO":
        failed = [
            str(item.get("name"))
            for item in local_runtime_diagnostics.get("checks") or []
            if item.get("status") != "GO"
        ]
        findings.append(
            {
                "code": "LOCAL_RUNTIME_DIAGNOSTICS_NO_GO",
                "severity": "blocking",
                "blocker_type": LOCAL_FIXABLE,
                "message": "Local repeatability prerequisites are missing or incomplete: " + ", ".join(failed),
                "required_action": (
                    "Restore the missing script, seed output capability, health probe command, or final shadow command "
                    "before relying on runtime shadow reports."
                ),
            }
        )
    return findings


def blocker_summary(findings: list[dict[str, str]]) -> dict[str, Any]:
    grouped = {LOCAL_FIXABLE: [], ENVIRONMENT_BLOCKER: []}
    for finding in findings:
        blocker_type = finding.get("blocker_type") or ENVIRONMENT_BLOCKER
        grouped.setdefault(blocker_type, []).append(finding)
    return {
        "local_fixable_count": len(grouped.get(LOCAL_FIXABLE, [])),
        "environment_blocker_count": len(grouped.get(ENVIRONMENT_BLOCKER, [])),
        "local_fixable": grouped.get(LOCAL_FIXABLE, []),
        "environment_blockers": grouped.get(ENVIRONMENT_BLOCKER, []),
    }


def collect_local_runtime_diagnostics(fixture_path: Path, *, output_dir: Path = DEFAULT_OUTPUT_DIR) -> dict[str, Any]:
    checks: list[dict[str, Any]] = []
    for artifact in LOCAL_RUNTIME_ARTIFACTS:
        path = artifact["path"]
        checks.append(
            {
                "name": artifact["name"],
                "status": "GO" if path.exists() else "NO_GO",
                "path": str(path),
                "purpose": artifact["purpose"],
                "blocker_type": LOCAL_FIXABLE,
            }
        )
    checks.append(
        {
            "name": "seed_output_command",
            "status": "GO",
            "command": (
                "python3 scripts/tools/platform_shadow_seed.py --run-id \"$SHADOW_RUN_ID\" "
                "--write-sql /tmp/p0-platform-shadow-seed.sql --write-env /tmp/p0-platform-shadow-env.sh"
            ),
            "purpose": "generate deterministic seed SQL/env without applying to PostgreSQL",
            "blocker_type": LOCAL_FIXABLE,
        }
    )
    seed_outputs = seed_output_artifacts(output_dir)
    checks.append(
        {
            "name": "seed_output_artifacts",
            "status": "GO" if all(item["present"] for item in seed_outputs) else "NO_GO",
            "purpose": "persist deterministic seed SQL/env/probe/report output for repeatable runtime shadow runs",
            "artifacts": seed_outputs,
            "blocker_type": LOCAL_FIXABLE,
        }
    )
    checks.append(
        {
            "name": "health_probe_commands",
            "status": "GO",
            "commands": health_probe_commands(),
            "purpose": "probe legacy Python and Axum readiness before running shadow cases",
            "blocker_type": LOCAL_FIXABLE,
        }
    )
    checks.append(
        {
            "name": "final_shadow_command",
            "status": "GO" if fixture_path.exists() else "NO_GO",
            "command": " ".join(runtime_shadow_command_for_fixture(fixture_path)),
            "purpose": "run all 16 platform endpoint primary and permission-failure cases",
            "blocker_type": LOCAL_FIXABLE,
        }
    )
    failed = [item for item in checks if item.get("status") != "GO"]
    return {
        "status": "GO" if not failed else "NO_GO",
        "checks": checks,
        "failed_count": len(failed),
    }


def collect_local_postgres_server() -> dict[str, Any]:
    readiness = command(["pg_isready", "-h", "localhost", "-p", "5432"], timeout=5)
    version = command(
        ["psql", "-h", "localhost", "-p", "5432", "-d", "postgres", "-At", "-c", "show server_version;"],
        timeout=5,
    )
    server_version = version.stdout.strip() if version.status == "GO" else ""
    server_major = parse_postgres_major(f"PostgreSQL {server_version}") if server_version else None
    return {
        "status": "GO" if readiness.status == "GO" and version.status == "GO" else "NO_GO",
        "host": "localhost",
        "port": 5432,
        "reachable": readiness.status == "GO",
        "readiness": readiness.to_report(),
        "server_version": server_version or None,
        "server_major": server_major,
        "version_probe": version.to_report(),
        "target_postgres_major_min": POSTGRES_TARGET_MAJOR_MIN,
    }


def seed_output_artifacts(output_dir: Path) -> list[dict[str, Any]]:
    patterns = [
        ("seed_sql", "p0-platform-shadow-seed-*.sql"),
        ("seed_env", "p0-platform-shadow-env-*.sh"),
        ("seed_probe_sql", "p0-platform-shadow-probe-*.sql"),
        ("seed_report", "p0-platform-shadow-seed-*.json"),
    ]
    artifacts = []
    for name, pattern in patterns:
        matches = sorted(output_dir.glob(pattern))
        artifacts.append(
            {
                "name": name,
                "pattern": str(output_dir / pattern),
                "present": bool(matches),
                "paths": [str(path) for path in matches],
            }
        )
    return artifacts


def out_of_scope_dependencies() -> list[dict[str, str]]:
    return [
        {
            "name": "NATS",
            "status": "OUT_OF_SCOPE_FOR_PROMPT_2",
            "reason": (
                "Prompt 2 gates runtime shadow preflight, service health, fixture variables, "
                "and Python-vs-Axum API validation only; NATS/Worker replay remains a separate "
                "production readiness blocker."
            ),
        }
    ]


def runtime_shadow_input_plan(
    *,
    runtime_variables: dict[str, Any],
    seed_requirements: dict[str, Any],
    auth_requirements: dict[str, Any],
    args: argparse.Namespace,
) -> dict[str, Any]:
    migration_command = (
        "for f in rust/fin-ops-api/migrations/000*.sql; do "
        'psql "$DATABASE_URL" -v ON_ERROR_STOP=1 -f "$f"; '
        "done"
    )
    python_start_command = (
        "FIN_OPS_DEV_ALLOW_LOCAL_SESSION=0 FIN_OPS_TEST_DEFAULT_AUTH=0 "
        "FIN_OPS_BACKEND_PORT=8001 FIN_OPS_STORAGE_MODE=auto "
        "scripts/start-backend.sh"
    )
    axum_start_command = (
        "cd rust/fin-ops-api && "
        "FIN_OPS_API_BIND_ADDR=127.0.0.1:8002 "
        "FIN_OPS_OA_IDENTITY_ADAPTER=trusted_headers "
        "cargo run -p fin-ops-api --bin fin-ops-api"
    )
    required_by_name = {
        str(item.get("name")): item
        for item in runtime_variables.get("required_variables") or []
        if isinstance(item, dict)
    }
    env_exports = [
        {
            "name": "FIN_OPS_SHADOW_PYTHON_BASE_URL",
            "required_for": "runtime shadow validator",
            "example": args.python_base_url or "http://127.0.0.1:8001",
            "sensitive": False,
            "status": "GO" if args.python_base_url else "NO_GO",
        },
        {
            "name": "FIN_OPS_SHADOW_AXUM_BASE_URL",
            "required_for": "runtime shadow validator",
            "example": args.axum_base_url or "http://127.0.0.1:8002",
            "sensitive": False,
            "status": "GO" if args.axum_base_url else "NO_GO",
        },
        {
            "name": args.database_url_env,
            "required_for": "local Axum service and PostgreSQL seed probes",
            "example": "postgres://fin_ops_api:[REDACTED]@127.0.0.1:5432/fin_ops_shadow",
            "sensitive": True,
            "status": "GO" if os.environ.get(args.database_url_env) else "NO_GO",
        },
        {
            "name": "FIN_OPS_OA_IDENTITY_ADAPTER",
            "required_for": "local Axum trusted-header identity resolution",
            "example": "trusted_headers",
            "sensitive": False,
            "status": "GO"
            if os.environ.get("FIN_OPS_OA_IDENTITY_ADAPTER", "").strip().lower()
            in TRUSTED_HEADERS_ADAPTER_VALUES
            else "NO_GO",
        },
        {
            "name": "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED",
            "required_for": "managed/remote Axum shadow service auth-mode attestation",
            "example": "trusted_headers",
            "sensitive": False,
            "status": "GO"
            if os.environ.get("FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED", "").strip().lower()
            in TRUSTED_HEADERS_ADAPTER_VALUES
            else "OPTIONAL_LOCAL_AXUM_NO_GO_REMOTE_ONLY",
        },
        {
            "name": "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE",
            "required_for": "runtime shadow identity-source audit",
            "example": "production_oa_test_user",
            "sensitive": False,
            "allowed_values": sorted(ACCEPTED_OA_IDENTITY_SOURCES),
            "status": "GO"
            if os.environ.get("FIN_OPS_SHADOW_OA_IDENTITY_SOURCE", "").strip()
            in ACCEPTED_OA_IDENTITY_SOURCES
            else "NO_GO",
        },
        {
            "name": "FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN",
            "required_for": "local legacy Python shadow reload after per-group reseed",
            "example": "generate with openssl rand -hex 24",
            "sensitive": True,
            "status": "GO" if os.environ.get("FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN") else "NO_GO",
        },
        {
            "name": "FIN_OPS_SHADOW_LEGACY_DATA_DIR",
            "required_for": "isolated legacy Python seed and reload source",
            "example": "/tmp/fin-ops-platform-shadow-legacy-$SHADOW_RUN_ID",
            "sensitive": False,
            "status": "GO" if os.environ.get("FIN_OPS_SHADOW_LEGACY_DATA_DIR") else "NO_GO",
        },
    ]
    for name in sorted(required_by_name):
        item = required_by_name[name]
        env_exports.append(
            {
                "name": name,
                "required_for": ", ".join(item.get("used_by") or []),
                "classification": item.get("classification"),
                "example": example_for_runtime_variable(name),
                "sensitive": item.get("classification") == "auth_secret",
                "status": "GO" if item.get("present") else "NO_GO",
            }
        )
    required_environment = runtime_environment_requirements(
        env_exports=env_exports,
        auth_requirements=auth_requirements,
    )
    fact_probe_commands = []
    for item in seed_requirements.get("requirements") or []:
        probe = item.get("probe") if isinstance(item.get("probe"), dict) else {}
        if item.get("postgres_fact_source") is None:
            continue
        metadata = SEED_REQUIREMENT_BY_VARIABLE.get(str(item.get("variable")) or "", {})
        probe_sql = metadata.get("probe_sql")
        if not probe_sql:
            continue
        fact_probe_commands.append(
            {
                "variable": item.get("variable"),
                "postgres_fact_source": item.get("postgres_fact_source"),
                "status": probe.get("status"),
                "command": (
                    "psql \"$DATABASE_URL\" -X -v ON_ERROR_STOP=1 -At -c "
                    + shell_double_quote(
                        str(probe_sql).format(value="${" + str(item.get("variable")) + "}")
                    )
                ),
            }
        )
    return {
        "status": "GO"
        if runtime_variables.get("status") == "GO"
        and seed_requirements.get("status") == "GO"
        and auth_requirements.get("status") == "GO"
        and args.python_base_url
        and args.axum_base_url
        else "NO_GO",
        "required_environment": required_environment,
        "environment_exports": env_exports,
        "postgres_migration_command": migration_command,
        "seed_command": (
            "python3 scripts/tools/platform_shadow_seed.py --run-id \"$SHADOW_RUN_ID\" "
            "--actor-id \"$FIN_OPS_SHADOW_OA_USERNAME\" --user-id \"$FIN_OPS_SHADOW_OA_USER_ID\" "
            "--display-name \"$FIN_OPS_SHADOW_OA_DISPLAY_NAME\" --apply && "
            "python3 scripts/tools/platform_shadow_legacy_seed.py --run-id \"$SHADOW_RUN_ID\" "
            "--username \"$FIN_OPS_SHADOW_OA_USERNAME\" --user-id \"$FIN_OPS_SHADOW_OA_USER_ID\" "
            "--data-dir \"$FIN_OPS_SHADOW_LEGACY_DATA_DIR\""
        ),
        "python_service_start_command": python_start_command,
        "axum_service_start_command": axum_start_command,
        "health_probe_commands": health_probe_commands(),
        "final_api_shadow_validate_command": " ".join(runtime_shadow_command(args)),
        "service_start_order": [
            {
                "step": 1,
                "name": "legacy_python_shadow",
                "command": python_start_command,
                "readiness": "curl -fsS \"$FIN_OPS_SHADOW_PYTHON_BASE_URL/health\"",
            },
            {
                "step": 2,
                "name": "postgres_migrations",
                "command": migration_command,
                "readiness": "all 0001-0009 migrations applied on PostgreSQL 16/17 shadow database",
            },
            {
                "step": 3,
                "name": "platform_postgres_seed",
                "command": (
                    "python3 scripts/tools/platform_shadow_seed.py --run-id \"$SHADOW_RUN_ID\" "
                    "--actor-id \"$FIN_OPS_SHADOW_OA_USERNAME\" --user-id \"$FIN_OPS_SHADOW_OA_USER_ID\" "
                    "--display-name \"$FIN_OPS_SHADOW_OA_DISPLAY_NAME\" --apply"
                ),
                "readiness": "generated seed SQL applied; source the generated p0-platform-shadow-env-*.sh file for fixture IDs",
            },
            {
                "step": 4,
                "name": "platform_legacy_seed",
                "command": (
                    "python3 scripts/tools/platform_shadow_legacy_seed.py --run-id \"$SHADOW_RUN_ID\" "
                    "--username \"$FIN_OPS_SHADOW_OA_USERNAME\" --user-id \"$FIN_OPS_SHADOW_OA_USER_ID\" "
                    "--data-dir \"$FIN_OPS_SHADOW_LEGACY_DATA_DIR\""
                ),
                "readiness": "legacy Python isolated data-dir seeded before service startup",
            },
            {
                "step": 5,
                "name": "axum_shadow",
                "command": axum_start_command,
                "readiness": "curl -fsS \"$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz\"",
            },
            {
                "step": 6,
                "name": "platform_seed_fact_probes",
                "command": "run every command in fact_probe_commands until each returns t",
                "readiness": "all fact id variables resolve to equivalent seeded PostgreSQL facts",
            },
            {
                "step": 7,
                "name": "legacy_shadow_reload_probe",
                "command": "python3 scripts/tools/platform_shadow_legacy_reload.py",
                "readiness": "reload report status GO",
            },
            {
                "step": 8,
                "name": "runtime_shadow_validation",
                "command": "python3 scripts/tools/platform_shadow_runtime.py --report-date "
                + (getattr(args, "report_date", None) or "$REPORT_DATE"),
                "readiness": "api_shadow_validate report status GO for all platform endpoint primary and permission cases",
            },
        ],
        "fact_probe_commands": fact_probe_commands,
        "auth_summary": auth_requirements,
    }


def runtime_environment_requirements(
    *,
    env_exports: list[dict[str, Any]],
    auth_requirements: dict[str, Any],
) -> list[dict[str, Any]]:
    export_by_name = {str(item.get("name")): item for item in env_exports}
    adapter_local = export_by_name.get("FIN_OPS_OA_IDENTITY_ADAPTER", {})
    adapter_remote = export_by_name.get("FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED", {})
    auth_adapter_ready = auth_requirements.get("status") == "GO" or (
        adapter_local.get("status") == "GO" or adapter_remote.get("status") == "GO"
    )
    requirements = []
    for item in RUNTIME_ENVIRONMENT_VARIABLES:
        name = item["name"]
        export = export_by_name.get(name, {})
        status = export.get("status")
        if name in {"FIN_OPS_OA_IDENTITY_ADAPTER", "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED"}:
            status = "GO" if auth_adapter_ready else "NO_GO_ALTERNATIVE_REQUIRED"
        requirements.append(
            {
                **item,
                "present": bool(status == "GO"),
                "status": status or "NO_GO",
                "example": export.get("example") or example_for_runtime_variable(name),
            }
        )
    return requirements


def health_probe_commands() -> list[dict[str, str]]:
    return [
        {
            "name": "python_health",
            "url": "$FIN_OPS_SHADOW_PYTHON_BASE_URL/health",
            "command": "curl -fsS \"$FIN_OPS_SHADOW_PYTHON_BASE_URL/health\"",
        },
        {
            "name": "axum_healthz",
            "url": "$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz",
            "command": "curl -fsS \"$FIN_OPS_SHADOW_AXUM_BASE_URL/healthz\"",
        },
        {
            "name": "axum_readyz",
            "url": "$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz",
            "command": "curl -fsS \"$FIN_OPS_SHADOW_AXUM_BASE_URL/readyz\"",
        },
    ]


def runtime_shadow_command_for_fixture(fixture_path: Path) -> list[str]:
    args = type(
        "Args",
        (),
        {
            "fixture": fixture_path,
            "python_base_url": None,
            "axum_base_url": None,
        },
    )()
    return runtime_shadow_command(args)


def example_for_runtime_variable(name: str) -> str:
    examples = {
        "BACKGROUND_JOB_ID": "00000000-0000-0000-0000-000000000000",
        "BANK_TRANSACTION_ID": "00000000-0000-0000-0000-000000000000",
        "LEDGER_ID": "00000000-0000-0000-0000-000000000000",
        "PROJECT_DELETE_ID": "00000000-0000-0000-0000-000000000000",
        "PROJECT_ID": "00000000-0000-0000-0000-000000000000",
        "FIN_OPS_SHADOW_OA_PASSWORD": "[REDACTED-STAGING-RESET-PASSWORD]",
        "FIN_OPS_SHADOW_OA_TOKEN": "[REDACTED-STAGING-OA-TOKEN]",
        "FIN_OPS_SHADOW_OA_IDENTITY_SOURCE": "production_oa_test_user",
        "SHADOW_RUN_ID": datetime.now(UTC).strftime("p0-platform-%Y%m%d%H%M%S"),
    }
    return examples.get(name, f"<{name}>")


def shell_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"


def shell_double_quote(value: str) -> str:
    return '"' + value.replace("\\", "\\\\").replace('"', '\\"').replace("`", "\\`") + '"'


def collect_auth_requirements(
    fixture_path: Path,
    *,
    endpoint_ids: set[str],
    axum_base_url: str | None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    defaults = fixture.get("defaults") if isinstance(fixture.get("defaults"), dict) else {}
    default_headers = normalize_headers(defaults.get("headers") if isinstance(defaults.get("headers"), dict) else {})
    endpoints = fixture.get("endpoints") if isinstance(fixture.get("endpoints"), list) else []
    selected = [
        endpoint
        for endpoint in endpoints
        if isinstance(endpoint, dict) and str(endpoint.get("id") or "") in endpoint_ids
    ]
    checks: list[dict[str, Any]] = []

    missing_primary_headers = []
    for header_name, description in PRIMARY_AUTH_HEADERS.items():
        value = default_headers.get(header_name)
        if not isinstance(value, str) or not value.strip():
            missing_primary_headers.append({"header": header_name, "description": description})
    checks.append(
        {
            "code": "PRIMARY_AUTH_HEADERS_PRESENT",
            "status": "GO" if not missing_primary_headers else "NO_GO",
            "missing_headers": missing_primary_headers,
        }
    )

    authorization = str(default_headers.get("authorization") or "")
    checks.append(
        {
            "code": "PRIMARY_AUTH_TOKEN_VARIABLE_PRESENT",
            "status": "GO" if env.get("FIN_OPS_SHADOW_OA_TOKEN") else "NO_GO",
            "header_uses_shadow_token": "${FIN_OPS_SHADOW_OA_TOKEN}" in authorization,
            "required_variable": "FIN_OPS_SHADOW_OA_TOKEN",
        }
    )
    identity_source = str(env.get("FIN_OPS_SHADOW_OA_IDENTITY_SOURCE") or "").strip()
    source_metadata = ACCEPTED_OA_IDENTITY_SOURCES.get(identity_source)
    checks.append(
        {
            "code": "OA_IDENTITY_SOURCE_ACCEPTED",
            "status": "GO" if source_metadata else "NO_GO",
            "source": identity_source or None,
            "accepted_values": sorted(ACCEPTED_OA_IDENTITY_SOURCES),
            "environment": source_metadata.get("environment") if source_metadata else None,
            "description": source_metadata.get("description") if source_metadata else None,
            "risk_note": (
                "Production OA test user is accepted only as identity/password source; "
                "Python and Axum business writes must remain isolated from production data."
                if identity_source == "production_oa_test_user"
                else None
            ),
        }
    )

    permission_header = str(default_headers.get("x-fin-ops-oa-permissions") or "")
    required_permission = env.get("FIN_OPS_OA_REQUIRED_PERMISSION") or DEFAULT_AXUM_REQUIRED_PERMISSION
    permission_values = expand_csv_value(permission_header, env)
    checks.append(
        {
            "code": "AXUM_TRUSTED_PERMISSION_PRESENT",
            "status": "GO" if required_permission in permission_values else "NO_GO",
            "required_permission": required_permission,
            "configured_permissions": permission_values,
        }
    )

    username_header = str(default_headers.get("x-fin-ops-oa-username") or "")
    username_value = expand_runtime_value(username_header, env)
    admin_usernames = normalize_csv(
        ",".join([DEFAULT_AXUM_ADMIN_USERNAME, env.get("FIN_OPS_ADMIN_USERNAMES", "")])
    )
    admin_routes = [endpoint for endpoint in selected if is_admin_fixture_endpoint(endpoint)]
    checks.append(
        {
            "code": "AXUM_ADMIN_USERNAME_PRESENT_FOR_ADMIN_ROUTES",
            "status": "GO" if not admin_routes or username_value in admin_usernames else "NO_GO",
            "admin_route_count": len(admin_routes),
            "trusted_username": redact_sensitive_text(username_value),
            "accepted_admin_usernames": admin_usernames,
        }
    )

    adapter = str(env.get("FIN_OPS_OA_IDENTITY_ADAPTER") or "").strip().lower()
    remote_confirmation = str(env.get("FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED") or "").strip().lower()
    adapter_confirmed = adapter in TRUSTED_HEADERS_ADAPTER_VALUES or (
        bool(axum_base_url) and remote_confirmation in TRUSTED_HEADERS_ADAPTER_VALUES
    )
    checks.append(
        {
            "code": "AXUM_TRUSTED_HEADERS_ADAPTER_CONFIRMED",
            "status": "GO" if adapter_confirmed else "NO_GO",
            "local_env_value": adapter or None,
            "remote_confirmation_env": "FIN_OPS_SHADOW_AXUM_AUTH_MODE_CONFIRMED",
            "remote_confirmation_value": remote_confirmation or None,
            "axum_base_url_present": bool(axum_base_url),
        }
    )

    no_go = [check for check in checks if check.get("status") != "GO"]
    return {
        "status": "GO" if not no_go else "NO_GO",
        "source": "Axum middleware/auth.rs and Python app/auth.py",
        "checks": checks,
    }


def normalize_headers(headers: Mapping[str, Any]) -> dict[str, str]:
    return {str(key).strip().lower(): str(value) for key, value in headers.items()}


def expand_runtime_value(value: str, env: Mapping[str, str]) -> str:
    def replace(match: re.Match[str]) -> str:
        return env.get(match.group(1), match.group(0))

    return RUNTIME_VARIABLE_PATTERN.sub(replace, value).strip()


def expand_csv_value(value: str, env: Mapping[str, str]) -> list[str]:
    return normalize_csv(expand_runtime_value(value, env))


def normalize_csv(value: str) -> list[str]:
    normalized = []
    for item in value.split(","):
        token = item.strip()
        if token and token not in normalized:
            normalized.append(token)
    return normalized


def is_admin_fixture_endpoint(endpoint: dict[str, Any]) -> bool:
    method = str(endpoint.get("method") or "").upper()
    path = str(endpoint.get("path") or "")
    for admin_method, admin_path, match_mode in ADMIN_ROUTE_SPECS:
        if method != admin_method:
            continue
        if match_mode == "exact" and path == admin_path:
            return True
        if match_mode == "prefix" and path.startswith(admin_path):
            return True
    return False


def collect_runtime_variable_requirements(
    fixture_path: Path,
    *,
    endpoint_ids: set[str],
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    endpoints = fixture.get("endpoints") if isinstance(fixture.get("endpoints"), list) else []
    selected_endpoints = [
        endpoint
        for endpoint in endpoints
        if isinstance(endpoint, dict) and str(endpoint.get("id") or "") in endpoint_ids
    ]
    selected_endpoint_ids = [str(endpoint.get("id")) for endpoint in selected_endpoints]
    variables: dict[str, set[str]] = {}
    defaults = fixture.get("defaults") if isinstance(fixture.get("defaults"), dict) else {}

    def record(value: Any, used_by: str) -> None:
        if isinstance(value, str):
            for variable in RUNTIME_VARIABLE_PATTERN.findall(value):
                variables.setdefault(variable, set()).add(used_by)
            return
        if isinstance(value, list):
            for item in value:
                record(item, used_by)
            return
        if isinstance(value, dict):
            for item in value.values():
                record(item, used_by)

    for endpoint_id in selected_endpoint_ids:
        record(defaults, endpoint_id)
    for endpoint in selected_endpoints:
        record(endpoint, str(endpoint.get("id")))

    env = environ if environ is not None else os.environ
    required = []
    for name in sorted(variables):
        used_by = sorted(variables[name])
        required.append(
            {
                "name": name,
                "present": bool(env.get(name)),
                "classification": classify_runtime_variable(name),
                "used_by": used_by,
            }
        )
    missing = [item["name"] for item in required if not item["present"]]
    return {
        "status": "GO" if not missing else "NO_GO",
        "required_count": len(required),
        "missing_count": len(missing),
        "missing_variables": missing,
        "required_variables": required,
    }


def collect_fixture_static_checks(fixture_path: Path, *, endpoint_ids: set[str]) -> dict[str, Any]:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    endpoints = fixture.get("endpoints") if isinstance(fixture.get("endpoints"), list) else []
    selected = [
        endpoint
        for endpoint in endpoints
        if isinstance(endpoint, dict) and str(endpoint.get("id") or "") in endpoint_ids
    ]
    conflicts: list[dict[str, Any]] = []
    conflicts.extend(duplicate_idempotency_key_conflicts(selected))
    conflicts.extend(data_reset_action_conflicts(selected))
    conflicts.extend(destructive_target_reuse_conflicts(selected))
    return {
        "status": "GO" if not conflicts else "NO_GO",
        "conflict_count": len(conflicts),
        "conflicts": conflicts,
    }


def duplicate_idempotency_key_conflicts(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_key: dict[str, list[str]] = {}
    for endpoint in endpoints:
        body = endpoint.get("body") if isinstance(endpoint.get("body"), dict) else {}
        key = body.get("idempotency_key")
        if isinstance(key, str) and key:
            by_key.setdefault(key, []).append(str(endpoint.get("id")))
    return [
        {
            "kind": "duplicate_idempotency_key",
            "value": key,
            "endpoint_ids": endpoint_ids,
            "message": "write endpoints must not share the same idempotency_key template",
        }
        for key, endpoint_ids in sorted(by_key.items())
        if len(endpoint_ids) > 1
    ]


def data_reset_action_conflicts(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    by_action: dict[str, list[str]] = {}
    for endpoint in endpoints:
        if not str(endpoint.get("path") or "").startswith("/api/workbench/settings/data-reset"):
            continue
        if endpoint.get("expected_status") != 202:
            continue
        body = endpoint.get("body") if isinstance(endpoint.get("body"), dict) else {}
        action = body.get("action")
        if isinstance(action, str) and action:
            by_action.setdefault(action, []).append(str(endpoint.get("id")))
    return [
        {
            "kind": "data_reset_action_reuse",
            "value": action,
            "endpoint_ids": endpoint_ids,
            "message": "data reset 202 shadow samples must use distinct actions to avoid active-job 409 self-conflicts",
        }
        for action, endpoint_ids in sorted(by_action.items())
        if len(endpoint_ids) > 1
    ]


def destructive_target_reuse_conflicts(endpoints: list[dict[str, Any]]) -> list[dict[str, Any]]:
    destructive_variables: dict[str, list[str]] = {}
    non_destructive_variables: dict[str, list[str]] = {}
    for endpoint in endpoints:
        endpoint_id = str(endpoint.get("id"))
        path = str(endpoint.get("path") or "")
        path_variables = set(RUNTIME_VARIABLE_PATTERN.findall(path))
        if is_destructive_fixture_endpoint(endpoint):
            for variable in path_variables:
                destructive_variables.setdefault(variable, []).append(endpoint_id)
        else:
            for variable in path_variables:
                non_destructive_variables.setdefault(variable, []).append(endpoint_id)
        body = endpoint.get("body") if isinstance(endpoint.get("body"), dict) else {}
        for value in body.values():
            if isinstance(value, str):
                for variable in RUNTIME_VARIABLE_PATTERN.findall(value):
                    non_destructive_variables.setdefault(variable, []).append(endpoint_id)
    conflicts = []
    for variable, destructive_endpoint_ids in sorted(destructive_variables.items()):
        readers = sorted(set(non_destructive_variables.get(variable) or []) - set(destructive_endpoint_ids))
        if readers:
            conflicts.append(
                {
                    "kind": "destructive_target_reuse",
                    "value": variable,
                    "endpoint_ids": sorted(set(destructive_endpoint_ids + readers)),
                    "message": "destructive shadow endpoint target variable must not be reused by later read/write samples",
                }
            )
    return conflicts


def is_destructive_fixture_endpoint(endpoint: dict[str, Any]) -> bool:
    method = str(endpoint.get("method") or "").upper()
    path = str(endpoint.get("path") or "")
    return method == "DELETE" or path.endswith("/delete")


def classify_runtime_variable(name: str) -> str:
    if any(hint in name for hint in ("TOKEN", "PASSWORD", "SECRET", "KEY")):
        return "auth_secret"
    if name == "SHADOW_RUN_ID":
        return "run_correlation"
    if name.endswith("_ID"):
        return "fixture_fact_id"
    return "runtime_parameter"


def collect_seed_requirements(
    runtime_variables: dict[str, Any],
    *,
    database_url_env: str,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    env = environ if environ is not None else os.environ
    database_url = env.get(database_url_env)
    runtime_by_name = {
        str(item.get("name")): item
        for item in runtime_variables.get("required_variables") or []
        if isinstance(item, dict)
    }
    requirements = []
    for variable in sorted(runtime_by_name):
        metadata = SEED_REQUIREMENT_BY_VARIABLE.get(variable, {})
        value_present = bool(env.get(variable))
        probe = seed_probe_for_variable(
            variable=variable,
            value=env.get(variable),
            database_url=database_url,
            metadata=metadata,
        )
        requirements.append(
            {
                "variable": variable,
                "kind": metadata.get("kind", classify_runtime_variable(variable)),
                "description": metadata.get("description", "Runtime variable required by platform shadow fixture."),
                "present": value_present,
                "used_by": runtime_by_name[variable].get("used_by") or [],
                "postgres_fact_source": metadata.get("postgres_fact_source"),
                "legacy_fact_source": metadata.get("legacy_fact_source"),
                "probe": probe,
            }
        )
    not_ready = [
        item
        for item in requirements
        if not item.get("present")
        or item.get("probe", {}).get("status") not in {"GO", "SKIPPED_NOT_POSTGRES_FACT"}
    ]
    failed = [item for item in requirements if item.get("probe", {}).get("status") == "NO_GO"]
    return {
        "status": "NO_GO" if not_ready else "GO",
        "database_url_env": database_url_env,
        "database_url_present": bool(database_url),
        "requirements": requirements,
        "failed_probe_count": len(failed),
        "skipped_probe_count": sum(
            1
            for item in requirements
            if str(item.get("probe", {}).get("status", "")).startswith("SKIPPED")
        ),
    }


def seed_probe_for_variable(
    *,
    variable: str,
    value: str | None,
    database_url: str | None,
    metadata: dict[str, Any],
) -> dict[str, Any]:
    probe_sql = metadata.get("probe_sql")
    if not probe_sql:
        return {"status": "SKIPPED_NOT_POSTGRES_FACT", "reason": "variable is not a PostgreSQL fact id"}
    if not value:
        return {"status": "SKIPPED_MISSING_VARIABLE", "reason": f"{variable} is not set"}
    try:
        canonical_value = str(UUID(value))
    except ValueError:
        return {"status": "NO_GO", "reason": f"{variable} must be a UUID for PostgreSQL seed probing"}
    if not database_url:
        return {"status": "SKIPPED_DATABASE_URL_MISSING", "reason": "DATABASE_URL is not set"}
    sql = str(probe_sql).format(value=canonical_value)
    result = command(
        ["psql", database_url, "-X", "-v", "ON_ERROR_STOP=1", "-At", "-c", sql],
        timeout=15,
    )
    output = result.stdout.strip().lower()
    status = "GO" if result.status == "GO" and output in {"t", "true", "1"} else "NO_GO"
    return {
        "status": status,
        "command": result.to_report(),
        "expected_stdout": "t",
        "stdout": result.stdout.strip(),
        "stderr": result.stderr.strip(),
    }


def runtime_shadow_command(args: argparse.Namespace) -> list[str]:
    command_parts = [
        "python3",
        "scripts/tools/api_shadow_validate.py",
        "--fixture",
        str(args.fixture),
        "--output-dir",
        "docs/operations/backend-refactor",
        "--include-permission-failures",
    ]
    if args.python_base_url:
        command_parts.extend(["--python-base-url", args.python_base_url])
    else:
        command_parts.extend(["--python-base-url", "$FIN_OPS_SHADOW_PYTHON_BASE_URL"])
    if args.axum_base_url:
        command_parts.extend(["--axum-base-url", args.axum_base_url])
    else:
        command_parts.extend(["--axum-base-url", "$FIN_OPS_SHADOW_AXUM_BASE_URL"])
    for endpoint_id in PLATFORM_ENDPOINT_IDS:
        command_parts.extend(["--endpoint-id", endpoint_id])
    return command_parts


def run_python_readiness_check() -> CommandResult:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT / "backend" / "src")
    return command(
        ["python3", "-m", "fin_ops_platform.app.main", "--check"],
        cwd=ROOT,
        env=env,
        timeout=20,
    )


def command(
    args: list[str],
    *,
    cwd: Path | None = None,
    env: dict[str, str] | None = None,
    timeout: int = 10,
) -> CommandResult:
    try:
        completed = subprocess.run(
            args,
            cwd=str(cwd or ROOT),
            env=env,
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
    except FileNotFoundError as error:
        return CommandResult(args, "NO_GO", None, "", str(error))
    except subprocess.TimeoutExpired as error:
        return CommandResult(args, "NO_GO", None, error.stdout or "", error.stderr or "timed out")
    status = "GO" if completed.returncode == 0 else "NO_GO"
    return CommandResult(args, status, completed.returncode, completed.stdout, completed.stderr)


def parse_postgres_major(version_text: str) -> int | None:
    match = re.search(r"PostgreSQL\)?\s+(\d+)", version_text)
    if match is None:
        return None
    return int(match.group(1))


def redact_sensitive_text(text: str) -> str:
    if not text:
        return text
    redacted = text
    for hint in SENSITIVE_ENV_HINTS:
        redacted = re.sub(rf"({hint}[^=\s]*=)[^\s]+", rf"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    redacted = re.sub(r"(postgres(?:ql)?://)[^\s]+", r"\1[REDACTED]", redacted, flags=re.IGNORECASE)
    return redacted


def render_markdown(report: dict[str, Any]) -> str:
    lines = [
        f"# {report['report']}",
        "",
        f"- Status: `{report['status']}`",
        f"- Generated at: `{report['generated_at']}`",
        f"- Fixture: `{report['fixture']}`",
        f"- Platform endpoint count: `{len(report['platform_endpoint_ids'])}`",
        "",
        "## Inputs",
        "",
        "| Item | Value |",
        "| --- | --- |",
    ]
    for key, value in report["inputs"].items():
        lines.append(f"| `{key}` | `{value}` |")
    lines.extend(
        [
            "",
            "## Checks",
            "",
            "| Check | Status | Detail |",
            "| --- | --- | --- |",
            f"| fixture_validation | `{report['fixture_validation']['status']}` | endpoint_count={report['fixture_validation'].get('endpoint_count')} |",
        ]
    )
    for name, payload in report["environment_checks"].items():
        if isinstance(payload, dict):
            detail = payload.get("stdout") or payload.get("stderr") or payload.get("value") or ""
            status = payload.get("status", "observed")
        else:
            detail = payload
            status = "observed" if payload is not None else "missing"
        lines.append(f"| `{name}` | `{status}` | `{markdown_cell(detail)}` |")
    fixture_static_checks = (
        report.get("fixture_static_checks")
        if isinstance(report.get("fixture_static_checks"), dict)
        else None
    )
    if fixture_static_checks is not None:
        lines.extend(
            [
                "",
                "## Fixture Static Checks",
                "",
                f"- Status: `{fixture_static_checks.get('status')}`",
                f"- Conflicts: `{fixture_static_checks.get('conflict_count')}`",
                "",
                "| Kind | Value | Endpoints | Message |",
                "| --- | --- | --- | --- |",
            ]
        )
        conflicts = fixture_static_checks.get("conflicts") or []
        if conflicts:
            for conflict in conflicts:
                lines.append(
                    "| `{kind}` | `{value}` | {endpoints} | {message} |".format(
                        kind=markdown_cell(conflict.get("kind")),
                        value=markdown_cell(conflict.get("value")),
                        endpoints=markdown_cell(", ".join(conflict.get("endpoint_ids") or [])),
                        message=markdown_cell(conflict.get("message")),
                    )
                )
        else:
            lines.append("| `none` | `` |  | No static write-order conflicts detected. |")
    runtime_variables = report.get("runtime_variables") if isinstance(report.get("runtime_variables"), dict) else None
    if runtime_variables is not None:
        lines.extend(
            [
                "",
                "## Runtime Variables",
                "",
                f"- Status: `{runtime_variables.get('status')}`",
                f"- Required variables: `{runtime_variables.get('required_count')}`",
                f"- Missing variables: `{runtime_variables.get('missing_count')}`",
                "",
                "| Variable | Present | Classification | Used by |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in runtime_variables.get("required_variables") or []:
            lines.append(
                "| `{name}` | `{present}` | `{classification}` | {used_by} |".format(
                    name=markdown_cell(item.get("name")),
                    present=item.get("present"),
                    classification=markdown_cell(item.get("classification")),
                    used_by=markdown_cell(", ".join(item.get("used_by") or [])),
                )
            )
    seed_requirements = report.get("seed_requirements") if isinstance(report.get("seed_requirements"), dict) else None
    if seed_requirements is not None:
        lines.extend(
            [
                "",
                "## Seed Requirements",
                "",
                f"- Status: `{seed_requirements.get('status')}`",
                f"- Database URL present: `{seed_requirements.get('database_url_present')}`",
                f"- Failed probes: `{seed_requirements.get('failed_probe_count')}`",
                f"- Skipped probes: `{seed_requirements.get('skipped_probe_count')}`",
                "",
                "| Variable | Kind | Present | PostgreSQL fact | Probe status | Used by |",
                "| --- | --- | --- | --- | --- | --- |",
            ]
        )
        for item in seed_requirements.get("requirements") or []:
            probe = item.get("probe") if isinstance(item.get("probe"), dict) else {}
            lines.append(
                "| `{variable}` | `{kind}` | `{present}` | `{postgres_fact}` | `{probe_status}` | {used_by} |".format(
                    variable=markdown_cell(item.get("variable")),
                    kind=markdown_cell(item.get("kind")),
                    present=item.get("present"),
                    postgres_fact=markdown_cell(item.get("postgres_fact_source")),
                    probe_status=markdown_cell(probe.get("status")),
                    used_by=markdown_cell(", ".join(item.get("used_by") or [])),
                )
            )
    auth_requirements = report.get("auth_requirements") if isinstance(report.get("auth_requirements"), dict) else None
    if auth_requirements is not None:
        lines.extend(
            [
                "",
                "## Auth Requirements",
                "",
                f"- Status: `{auth_requirements.get('status')}`",
                f"- Source: `{auth_requirements.get('source')}`",
                "",
                "| Check | Status | Detail |",
                "| --- | --- | --- |",
            ]
        )
        for item in auth_requirements.get("checks") or []:
            detail = {
                key: value
                for key, value in item.items()
                if key not in {"code", "status"}
            }
            lines.append(
                "| `{code}` | `{status}` | `{detail}` |".format(
                    code=markdown_cell(item.get("code")),
                    status=markdown_cell(item.get("status")),
                    detail=markdown_cell(json.dumps(detail, ensure_ascii=False, sort_keys=True)),
                )
            )
    local_runtime_diagnostics = (
        report.get("local_runtime_diagnostics")
        if isinstance(report.get("local_runtime_diagnostics"), dict)
        else None
    )
    if local_runtime_diagnostics is not None:
        lines.extend(
            [
                "",
                "## Local Runtime Diagnostics",
                "",
                f"- Status: `{local_runtime_diagnostics.get('status')}`",
                f"- Failed checks: `{local_runtime_diagnostics.get('failed_count')}`",
                "",
                "| Check | Status | Purpose | Detail |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in local_runtime_diagnostics.get("checks") or []:
            detail = item.get("path") or item.get("command") or item.get("commands") or ""
            lines.append(
                "| `{name}` | `{status}` | {purpose} | `{detail}` |".format(
                    name=markdown_cell(item.get("name")),
                    status=markdown_cell(item.get("status")),
                    purpose=markdown_cell(item.get("purpose")),
                    detail=markdown_cell(detail),
                )
            )
    out_of_scope = report.get("out_of_scope_dependencies")
    if isinstance(out_of_scope, list):
        lines.extend(
            [
                "",
                "## Out Of Scope Dependencies",
                "",
                "| Dependency | Status | Reason |",
                "| --- | --- | --- |",
            ]
        )
        for item in out_of_scope:
            lines.append(
                "| `{name}` | `{status}` | {reason} |".format(
                    name=markdown_cell(item.get("name")),
                    status=markdown_cell(item.get("status")),
                    reason=markdown_cell(item.get("reason")),
                )
            )
    input_plan = report.get("runtime_shadow_input_plan") if isinstance(report.get("runtime_shadow_input_plan"), dict) else None
    if input_plan is not None:
        lines.extend(
            [
                "",
                "## Runtime Shadow Input Plan",
                "",
                f"- Status: `{input_plan.get('status')}`",
                "",
                "### Required Environment",
                "",
                "| Variable | Status | Sensitive | Required for | Alternative |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in input_plan.get("required_environment") or []:
            lines.append(
                "| `{name}` | `{status}` | `{sensitive}` | {required_for} | {alternative} |".format(
                    name=markdown_cell(item.get("name")),
                    status=markdown_cell(item.get("status")),
                    sensitive=item.get("sensitive"),
                    required_for=markdown_cell(item.get("required_for")),
                    alternative=markdown_cell(item.get("alternative") or ""),
                )
            )
        lines.extend(
            [
                "",
                "### Command Plan",
                "",
                "| Step | Command |",
                "| --- | --- |",
                f"| PostgreSQL migration | `{markdown_cell(input_plan.get('postgres_migration_command'))}` |",
                f"| Seed | `{markdown_cell(input_plan.get('seed_command'))}` |",
                f"| Python service | `{markdown_cell(input_plan.get('python_service_start_command'))}` |",
                f"| Axum service | `{markdown_cell(input_plan.get('axum_service_start_command'))}` |",
                f"| Final shadow validation | `{markdown_cell(input_plan.get('final_api_shadow_validate_command'))}` |",
                "",
                "### Health Probe Commands",
                "",
                "| Probe | URL | Command |",
                "| --- | --- | --- |",
            ]
        )
        for item in input_plan.get("health_probe_commands") or []:
            lines.append(
                "| `{name}` | `{url}` | `{command}` |".format(
                    name=markdown_cell(item.get("name")),
                    url=markdown_cell(item.get("url")),
                    command=markdown_cell(item.get("command")),
                )
            )
        lines.extend(
            [
                "",
                "### Environment Exports",
                "",
                "| Variable | Status | Sensitive | Example | Required for |",
                "| --- | --- | --- | --- | --- |",
            ]
        )
        for item in input_plan.get("environment_exports") or []:
            lines.append(
                "| `{name}` | `{status}` | `{sensitive}` | `{example}` | {required_for} |".format(
                    name=markdown_cell(item.get("name")),
                    status=markdown_cell(item.get("status")),
                    sensitive=item.get("sensitive"),
                    example=markdown_cell(item.get("example")),
                    required_for=markdown_cell(item.get("required_for")),
                )
            )
        lines.extend(
            [
                "",
                "### Service Start Order",
                "",
                "| Step | Name | Command | Readiness |",
                "| --- | --- | --- | --- |",
            ]
        )
        for item in input_plan.get("service_start_order") or []:
            lines.append(
                "| `{step}` | `{name}` | `{command}` | {readiness} |".format(
                    step=item.get("step"),
                    name=markdown_cell(item.get("name")),
                    command=markdown_cell(item.get("command")),
                    readiness=markdown_cell(item.get("readiness")),
                )
            )
        lines.extend(
            [
                "",
                "### Fact Probe Commands",
                "",
                "| Variable | PostgreSQL fact | Current status | Command |",
                "| --- | --- | --- | --- |",
            ]
        )
        commands = input_plan.get("fact_probe_commands") or []
        if commands:
            for item in commands:
                lines.append(
                    "| `{variable}` | `{fact}` | `{status}` | `{command}` |".format(
                        variable=markdown_cell(item.get("variable")),
                        fact=markdown_cell(item.get("postgres_fact_source")),
                        status=markdown_cell(item.get("status")),
                        command=markdown_cell(item.get("command")),
                    )
                )
        else:
            lines.append("| `none` | `` | `` | No PostgreSQL fact probes are required. |")
    lines.extend(["", "## Findings", "", "| Code | Severity | Message | Required action |", "| --- | --- | --- | --- |"])
    if report["findings"]:
        for finding in report["findings"]:
            lines.append(
                "| `{code}` | `{severity}` | {message} | {required_action} |".format(
                    code=finding["code"],
                    severity=finding["severity"],
                    message=markdown_cell(finding["message"]),
                    required_action=markdown_cell(finding["required_action"]),
                )
            )
    else:
        lines.append("| `NONE` | `none` | No blocking findings. | Run runtime shadow command. |")
    blocker = report.get("blocker_summary") if isinstance(report.get("blocker_summary"), dict) else None
    if blocker is not None:
        lines.extend(
            [
                "",
                "## Blocker Classification",
                "",
                f"- Local fixable: `{blocker.get('local_fixable_count')}`",
                f"- Environment blockers: `{blocker.get('environment_blocker_count')}`",
            ]
        )
    lines.extend(
        [
            "",
            "## Runtime Shadow Command",
            "",
            "```bash",
            " ".join(report["next_runtime_shadow_command"]),
            "```",
            "",
        ]
    )
    return "\n".join(lines)


def markdown_cell(value: Any) -> str:
    text = str(value).replace("\n", "\\n").replace("|", "\\|").replace("`", "\\`")
    if len(text) > 220:
        text = text[:217] + "..."
    return text


if __name__ == "__main__":
    raise SystemExit(main())
