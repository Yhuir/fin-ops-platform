from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any, Mapping, Sequence, TextIO
from urllib.parse import ParseResult, urlparse, urlunparse


PASS = "pass"
FAIL = "fail"

REQUIRED_ENV = (
    "FIN_OPS_TEST_DATABASE_URL",
    "RABBITMQ_TEST_URL",
)


@dataclass(frozen=True)
class CheckResult:
    name: str
    status: str
    detail: str
    metadata: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        return {key: value for key, value in payload.items() if value is not None}


@dataclass(frozen=True)
class CommandResult:
    returncode: int
    stdout: str = ""
    stderr: str = ""


class CommandRunner:
    def run(self, command: list[str], *, env: Mapping[str, str], timeout: int) -> CommandResult:
        completed = subprocess.run(
            command,
            env=dict(env),
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        return CommandResult(
            returncode=int(completed.returncode),
            stdout=completed.stdout,
            stderr=completed.stderr,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run RabbitMQ staging preflight for fin-ops runtime queue cutover.")
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    parser.add_argument("--output", type=Path, help="Write JSON report to a file.")
    parser.add_argument(
        "--apply-topology",
        action="store_true",
        help="Run rabbitmq_topology --apply after the read-only check. Use only against staging/prod after approval.",
    )
    parser.add_argument(
        "--skip-real-tests",
        action="store_true",
        help="Skip real PostgreSQL/RabbitMQ pytest integration tests. Intended only for CLI smoke in local development.",
    )
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    stdout: TextIO = sys.stdout,
    runner: CommandRunner | None = None,
    environ: Mapping[str, str] | None = None,
) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    env = dict(os.environ if environ is None else environ)
    checks = run_checks(
        env=env,
        runner=runner or CommandRunner(),
        apply_topology=args.apply_topology,
        skip_real_tests=args.skip_real_tests,
    )
    status = PASS if all(check.status == PASS for check in checks) else FAIL
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "status": status,
        "apply_topology": bool(args.apply_topology),
        "skip_real_tests": bool(args.skip_real_tests),
        "checks": [check.to_dict() for check in checks],
    }
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True)
    if args.output is not None:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded if args.json else _format_text(report), file=stdout)
    return 0 if status == PASS else 1


def run_checks(
    *,
    env: Mapping[str, str],
    runner: CommandRunner,
    apply_topology: bool,
    skip_real_tests: bool,
) -> list[CheckResult]:
    checks: list[CheckResult] = [_check_required_env(env)]
    if checks[-1].status != PASS:
        return checks

    runtime_env = _runtime_env(env)
    if not skip_real_tests:
        checks.append(
            _run_command_check(
                runner,
                "postgres.integration",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_runtime_infrastructure_postgres_integration.py",
                    "-q",
                ],
                env=runtime_env,
                timeout=240,
            )
        )
        checks.append(
            _run_command_check(
                runner,
                "rabbitmq.integration",
                [
                    sys.executable,
                    "-m",
                    "pytest",
                    "tests/test_rabbitmq_integration.py",
                    "-q",
                ],
                env=runtime_env,
                timeout=120,
            )
        )
    checks.append(
        _run_command_check(
            runner,
            "rabbitmq.topology_check",
            [sys.executable, "-m", "fin_ops_platform.app.rabbitmq_topology", "--check"],
            env=runtime_env,
            timeout=30,
        )
    )
    if apply_topology:
        checks.append(
            _run_command_check(
                runner,
                "rabbitmq.topology_apply",
                [sys.executable, "-m", "fin_ops_platform.app.rabbitmq_topology", "--apply"],
                env=runtime_env,
                timeout=60,
            )
        )
    dispatcher_command = [
        sys.executable,
        "-m",
        "fin_ops_platform.app.rabbitmq_dispatcher",
        "--check",
        "--shadow-publish",
    ]
    for event_type in (
        "workbench.read_model.refresh",
        "search.read_model.refresh",
        "pending_invoice.read_model.refresh",
        "cost_statistics.read_model.refresh",
        "tax_offset.read_model.refresh",
        "oa.sync",
        "file_object.gridfs_migration",
        "import.process.requested",
    ):
        dispatcher_command.extend(["--event-type", event_type])
    checks.append(
        _run_command_check(
            runner,
            "rabbitmq.dispatcher_shadow_check",
            dispatcher_command,
            env={**runtime_env, "FIN_OPS_QUEUE_BACKEND": "postgres", "RABBITMQ_SHADOW_PUBLISH": "true"},
            timeout=30,
        )
    )
    worker_checks = {
        "rabbitmq.consumer_worker_check.workbench": [
            "--enable-workbench-read-model-refresh",
            "--event-type",
            "workbench.read_model.refresh",
            "--worker-kind",
            "workbench-read-model",
        ],
        "rabbitmq.consumer_worker_check.search_pending": [
            "--enable-search-read-model-refresh",
            "--enable-pending-invoice-read-model-refresh",
            "--event-type",
            "search.read_model.refresh",
            "--event-type",
            "pending_invoice.read_model.refresh",
            "--worker-kind",
            "search-pending-read-model",
        ],
        "rabbitmq.consumer_worker_check.cost_tax": [
            "--enable-cost-statistics-read-model-refresh",
            "--enable-tax-offset-read-model-refresh",
            "--event-type",
            "cost_statistics.read_model.refresh",
            "--event-type",
            "tax_offset.read_model.refresh",
            "--worker-kind",
            "cost-tax-read-model",
        ],
        "rabbitmq.consumer_worker_check.oa_sync": [
            "--enable-oa-sync",
            "--event-type",
            "oa.sync",
            "--worker-kind",
            "oa-sync",
        ],
        "rabbitmq.consumer_worker_check.file_migration": [
            "--enable-file-object-migration",
            "--event-type",
            "file_object.gridfs_migration",
            "--worker-kind",
            "file-object-migration",
        ],
        "rabbitmq.consumer_worker_check.import_job": [
            "--enable-import-job-processing",
            "--event-type",
            "import.process.requested",
            "--worker-kind",
            "import-job",
        ],
    }
    for name, worker_args in worker_checks.items():
        checks.append(
            _run_command_check(
                runner,
                name,
                [sys.executable, "-m", "fin_ops_platform.app.worker", *worker_args, "--check"],
                env={**runtime_env, "FIN_OPS_QUEUE_BACKEND": "rabbitmq"},
                timeout=30,
            )
        )
    return checks


def _check_required_env(env: Mapping[str, str]) -> CheckResult:
    missing = [name for name in REQUIRED_ENV if not str(env.get(name) or "").strip()]
    optional_runtime = {
        "RABBITMQ_URL": bool(str(env.get("RABBITMQ_URL") or "").strip()),
        "FIN_OPS_POSTGRES_DATABASE_URL": bool(str(env.get("FIN_OPS_POSTGRES_DATABASE_URL") or "").strip()),
    }
    if missing:
        return CheckResult(
            name="env.required",
            status=FAIL,
            detail="RabbitMQ staging preflight requires real staging PostgreSQL and RabbitMQ test URLs.",
            metadata={"missing": missing, "optional_runtime": optional_runtime},
        )
    return CheckResult(
        name="env.required",
        status=PASS,
        detail="Required staging preflight environment is present.",
        metadata={
            "FIN_OPS_TEST_DATABASE_URL": _redact_url(str(env["FIN_OPS_TEST_DATABASE_URL"])),
            "RABBITMQ_TEST_URL": _redact_url(str(env["RABBITMQ_TEST_URL"])),
            "runtime_fallbacks": {
                "FIN_OPS_POSTGRES_DATABASE_URL": _redact_url(
                    str(env.get("FIN_OPS_POSTGRES_DATABASE_URL") or env["FIN_OPS_TEST_DATABASE_URL"])
                ),
                "RABBITMQ_URL": _redact_url(str(env.get("RABBITMQ_URL") or env["RABBITMQ_TEST_URL"])),
            },
        },
    )


def _runtime_env(env: Mapping[str, str]) -> dict[str, str]:
    runtime_env = dict(env)
    runtime_env.setdefault("PYTHONPATH", "backend/src")
    runtime_env["FIN_OPS_TEST_DATABASE_URL"] = str(env["FIN_OPS_TEST_DATABASE_URL"])
    runtime_env["FIN_OPS_POSTGRES_DATABASE_URL"] = str(env.get("FIN_OPS_POSTGRES_DATABASE_URL") or env["FIN_OPS_TEST_DATABASE_URL"])
    runtime_env["RABBITMQ_TEST_URL"] = str(env["RABBITMQ_TEST_URL"])
    runtime_env["RABBITMQ_URL"] = str(env.get("RABBITMQ_URL") or env["RABBITMQ_TEST_URL"])
    runtime_env.setdefault("RABBITMQ_VHOST", "/finops")
    runtime_env.setdefault("RABBITMQ_EXCHANGE", "finops.events")
    runtime_env.setdefault("RABBITMQ_WORKBENCH_QUEUE", "finops.workbench.read_model.refresh")
    runtime_env.setdefault("RABBITMQ_WORKBENCH_ROUTING_KEY", "workbench.read_model.refresh")
    runtime_env.setdefault("RABBITMQ_DEAD_LETTER_EXCHANGE", "finops.events.dlx")
    runtime_env.setdefault("RABBITMQ_WORKBENCH_DEAD_LETTER_QUEUE", "finops.workbench.read_model.refresh.dlq")
    runtime_env.setdefault("RABBITMQ_PREFETCH", "10")
    runtime_env.setdefault("RABBITMQ_PUBLISH_CONFIRM", "true")
    return runtime_env


def _run_command_check(
    runner: CommandRunner,
    name: str,
    command: list[str],
    *,
    env: Mapping[str, str],
    timeout: int,
) -> CheckResult:
    try:
        result = runner.run(command, env=env, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        return CheckResult(name=name, status=FAIL, detail=f"Command timed out after {timeout}s.", metadata={"command": command, "error": str(exc)})
    except Exception as exc:
        return CheckResult(name=name, status=FAIL, detail=str(exc), metadata={"command": command})
    if result.returncode != 0:
        return CheckResult(
            name=name,
            status=FAIL,
            detail=f"Command failed with exit code {result.returncode}.",
            metadata={
                "command": command,
                "stdout_tail": result.stdout[-4000:],
                "stderr_tail": result.stderr[-4000:],
            },
        )
    return CheckResult(
        name=name,
        status=PASS,
        detail="Command passed.",
        metadata={"command": command, "stdout_tail": result.stdout[-2000:]},
    )


def _format_text(report: dict[str, Any]) -> str:
    lines = [f"RabbitMQ staging preflight: {report['status']}"]
    for check in report["checks"]:
        lines.append(f"- {check['status']} {check['name']}: {check['detail']}")
    return "\n".join(lines)


def _redact_url(value: str) -> str:
    parsed = urlparse(value)
    if not parsed.scheme or not parsed.netloc:
        return "<invalid-url>"
    username = parsed.username or ""
    host = parsed.hostname or ""
    port = f":{parsed.port}" if parsed.port is not None else ""
    credentials = f"{username}:***@" if username else ""
    redacted = ParseResult(
        scheme=parsed.scheme,
        netloc=f"{credentials}{host}{port}",
        path=parsed.path,
        params="",
        query="",
        fragment="",
    )
    return urlunparse(redacted)


if __name__ == "__main__":
    raise SystemExit(main())
