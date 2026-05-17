#!/usr/bin/env python3
"""Reseed platform runtime shadow stores before a mutating isolation group."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
import shlex
import subprocess
import sys
from typing import Any, Sequence


ROOT = Path(__file__).resolve().parents[2]
TOOLS_DIR = Path(__file__).resolve().parent
SENSITIVE_PATTERN = re.compile(
    r"(?i)(bearer\s+)[^\s]+|((?:password|token|secret|key)=)[^\s&]+|"
    r"(postgres(?:ql)?://[^:\s/]+:)[^@\s]+(@)"
)


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=ROOT / "docs" / "operations" / "backend-refactor")
    parser.add_argument("--report-date", default=datetime.now(UTC).strftime("%Y%m%d"))
    parser.add_argument("--database-url-env", default="DATABASE_URL")
    return parser.parse_args(argv)


def main(argv: Sequence[str] | None = None) -> int:
    args = parse_args(argv)
    report: dict[str, Any] = {
        "status": "NO_GO",
        "hook": "platform_shadow_reseed_hook",
        "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "isolation_group": os.environ.get("SHADOW_ISOLATION_GROUP"),
        "endpoint_id": os.environ.get("SHADOW_ENDPOINT_ID"),
        "postgres_cleanup_applied": False,
        "legacy_seed_applied": False,
        "restart_required": False,
        "steps": [],
    }

    missing = required_missing(args.database_url_env)
    if missing:
        report["message"] = "required shadow reseed environment is missing"
        report["missing_environment"] = missing
        print_report(report)
        return 3

    run_id = os.environ["SHADOW_RUN_ID"].strip()
    username = os.environ["FIN_OPS_SHADOW_OA_USERNAME"].strip()
    user_id = os.environ["FIN_OPS_SHADOW_OA_USER_ID"].strip()
    display_name = os.environ["FIN_OPS_SHADOW_OA_DISPLAY_NAME"].strip()
    database_url = os.environ[args.database_url_env]
    legacy_data_dir = Path(os.environ["FIN_OPS_SHADOW_LEGACY_DATA_DIR"])

    postgres = run_step(
        [
            sys.executable,
            str(TOOLS_DIR / "platform_shadow_seed.py"),
            "--run-id",
            run_id,
            "--actor-id",
            username,
            "--user-id",
            user_id,
            "--display-name",
            display_name,
            "--database-url",
            database_url,
            "--output-dir",
            str(args.output_dir),
            "--report-date",
            args.report_date,
            "--apply",
        ],
        name="postgres_cleanup_and_seed",
    )
    report["steps"].append(postgres)
    report["postgres_cleanup_applied"] = postgres["status"] == "GO"
    if postgres["status"] != "GO":
        report["message"] = "PostgreSQL shadow cleanup/seed failed"
        print_report(report)
        return 3

    legacy = run_step(
        [
            sys.executable,
            str(TOOLS_DIR / "platform_shadow_legacy_seed.py"),
            "--run-id",
            run_id,
            "--username",
            username,
            "--user-id",
            user_id,
            "--data-dir",
            str(legacy_data_dir),
            "--output-dir",
            str(args.output_dir),
            "--report-date",
            args.report_date,
        ],
        name="legacy_data_dir_seed",
    )
    report["steps"].append(legacy)
    report["legacy_seed_applied"] = legacy["status"] == "GO"
    if legacy["status"] != "GO":
        report["message"] = "legacy Python isolated data-dir seed failed"
        print_report(report)
        return 3

    reload_hook = os.environ.get("FIN_OPS_SHADOW_LEGACY_RELOAD_HOOK", "").strip()
    if not reload_hook and os.environ.get("FIN_OPS_SHADOW_PYTHON_BASE_URL") and os.environ.get("FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN"):
        reload_hook = shlex.join([sys.executable, str(TOOLS_DIR / "platform_shadow_legacy_reload.py")])
    if not reload_hook:
        report["restart_required"] = True
        report["message"] = (
            "legacy Python process must restart or expose FIN_OPS_SHADOW_LEGACY_RELOAD_HOOK "
            "or FIN_OPS_SHADOW_LEGACY_RELOAD_TOKEN with FIN_OPS_SHADOW_PYTHON_BASE_URL "
            "to load the reseeded isolated data-dir before requests are sent"
        )
        print_report(report)
        return 4

    reload_result = run_step(shlex.split(reload_hook), name="legacy_shadow_reload")
    report["steps"].append(reload_result)
    if reload_result["status"] != "GO":
        report["restart_required"] = True
        report["message"] = "legacy Python shadow reload hook failed"
        print_report(report)
        return 4

    report["status"] = "GO"
    report["message"] = "shadow stores reseeded and legacy reload hook completed"
    print_report(report)
    return 0


def required_missing(database_url_env: str) -> list[str]:
    required = [
        "SHADOW_RUN_ID",
        "FIN_OPS_SHADOW_OA_USERNAME",
        "FIN_OPS_SHADOW_OA_USER_ID",
        "FIN_OPS_SHADOW_OA_DISPLAY_NAME",
        "FIN_OPS_SHADOW_LEGACY_DATA_DIR",
        database_url_env,
    ]
    return [name for name in required if not os.environ.get(name)]


def run_step(command: list[str], *, name: str) -> dict[str, Any]:
    completed = subprocess.run(
        command,
        check=False,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return {
        "name": name,
        "status": "GO" if completed.returncode == 0 else "NO_GO",
        "returncode": completed.returncode,
        "stdout_tail": tail(redact_sensitive_text(completed.stdout)),
        "stderr_tail": tail(redact_sensitive_text(completed.stderr)),
    }


def redact_sensitive_text(value: str) -> str:
    def replace(match: re.Match[str]) -> str:
        if match.group(1):
            return match.group(1) + "[REDACTED]"
        if match.group(2):
            return match.group(2) + "[REDACTED]"
        if match.group(3):
            return match.group(3) + "[REDACTED]" + match.group(4)
        return "[REDACTED]"

    return SENSITIVE_PATTERN.sub(replace, value)


def tail(value: str, *, limit: int = 1600) -> str:
    stripped = value.strip()
    if len(stripped) <= limit:
        return stripped
    return stripped[-limit:]


def print_report(report: dict[str, Any]) -> None:
    print(json.dumps(report, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
