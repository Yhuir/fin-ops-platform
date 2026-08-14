from __future__ import annotations

from datetime import UTC, datetime
import json
from pathlib import Path
from typing import Any, TextIO


def postgres_configuration_missing_report(*, tool: str, message: str) -> dict[str, Any]:
    return {
        "status": "configuration_missing",
        "tool": tool,
        "error": "postgres_configuration_missing",
        "message": message,
        "blocking_condition": "database_url_required",
        "required_env": ["FIN_OPS_POSTGRES_DATABASE_URL", "DATABASE_URL"],
        "next_actions": [
            "Provide FIN_OPS_POSTGRES_DATABASE_URL or DATABASE_URL from a secure runtime environment, then rerun the gate.",
            "For production evidence, collect read-only database/runtime facts from an approved SSH session without writing credentials to files, logs, scripts, docs, or prompts.",
            "Do not treat configuration_missing as a pass, skip, or one-second SLO proof.",
        ],
        "allowed_remote_evidence": [
            "systemd worker status and recent logs",
            "PostgreSQL canonical-data, outbox, worker readiness, and pg_stat/EXPLAIN sampling",
            "RabbitMQ queue depth, consumer, unacked, and DLQ read-only checks",
            "Redis, Nginx, App Health, and public/API latency read-only checks",
        ],
        "forbidden_without_approval": [
            "database writes or cleanup",
            "deployments",
            "service restarts",
            "destructive shell commands",
            "production mutating HTTP scenarios",
        ],
        "generated_at": datetime.now(UTC).isoformat(),
    }


def input_file_error_report(*, tool: str, path: str, error: str, message: str) -> dict[str, Any]:
    return {
        "status": "input_error",
        "tool": tool,
        "error": error,
        "path": path,
        "message": message,
        "generated_at": datetime.now(UTC).isoformat(),
    }


def write_json_report(report: dict[str, Any], *, output: Path | None, stdout: TextIO) -> None:
    encoded = json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True, default=str)
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(encoded + "\n", encoding="utf-8")
    print(encoded, file=stdout)
