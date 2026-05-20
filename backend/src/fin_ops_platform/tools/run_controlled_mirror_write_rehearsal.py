from __future__ import annotations

import argparse
from datetime import UTC, datetime
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, TextIO

from fin_ops_platform.services.cutover_preflight import redact_secret_text, redact_secret_values
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_state_store import PostgresStateStore
from fin_ops_platform.services.state_store import ApplicationStateStore, default_data_dir
from fin_ops_platform.tools.run_runtime_state_policy_preflight import (
    READ_ONLY_GUARD_ENV,
    build_runtime_policy_report,
)


EXECUTE_GUARD_ENV = "FIN_OPS_STAGE15_CONTROLLED_MIRROR_WRITE"
BACKUP_CONFIRMED_ENV = "FIN_OPS_STAGE15_BACKUP_CONFIRMED"
RUN_ID_ENV = "FIN_OPS_STAGE15_RUN_ID"
DEFAULT_REPORT_DIR = Path("docs/database-migration/reports")
FORBIDDEN_CLI_FLAGS = {
    "--cutover",
    "--enable-dual-write",
    "--dual-write",
    "--restart-service",
    "--switch-backend",
    "--write-all",
}
TARGET_COUNT_SQL = """
select 'job.background_jobs' as table_name, count(*)::bigint as row_count from job.background_jobs
union all
select 'audit.app_health_alerts' as table_name, count(*)::bigint as row_count from audit.app_health_alerts
union all
select 'app.app_settings.runtime_state' as table_name, count(*)::bigint as row_count
from app.app_settings
where settings_key in ('state:background_jobs', 'state:app_health_alerts')
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run controlled stage15 runtime mirror-write rehearsal.")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="Plan runtime mirror-write without writing PostgreSQL.")
    mode.add_argument("--execute", action="store_true", help="Execute controlled runtime mirror-write.")
    parser.add_argument("--json", action="store_true", help="Print JSON report.")
    parser.add_argument("--output", type=Path, default=None, help="Write report artifact to this path.")
    parser.add_argument("--primary-backend", choices=("local_pickle", "mongo_readonly"), default="local_pickle")
    parser.add_argument("--mirror-backend", choices=("postgres",), default="postgres")
    parser.add_argument("--data-dir", type=Path, default=None)
    parser.add_argument("--run-id", default=None)
    parser.add_argument("--production", action="store_true")
    parser.add_argument("--max-background-jobs", type=int, default=5000)
    parser.add_argument("--max-app-health-alerts", type=int, default=200)
    return parser


def main(
    argv: list[str] | None = None,
    *,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
    primary_store: Any | None = None,
    mirror_store: Any | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args_list = list(sys.argv[1:] if argv is None else argv)
    forbidden = [arg for arg in args_list if arg.split("=", 1)[0] in FORBIDDEN_CLI_FLAGS]
    if forbidden:
        print(f"ERROR: controlled mirror-write rehearsal refuses cutover flags: {', '.join(forbidden)}", file=stderr)
        return 2

    try:
        args = build_parser().parse_args(args_list)
        execute = bool(args.execute)
        _enforce_read_only_guard(args.production or args.primary_backend == "mongo_readonly")
        if execute:
            _enforce_execute_guards()
        data_dir = args.data_dir or default_data_dir()
        primary = primary_store or _build_primary_store(args.primary_backend, data_dir=data_dir)
        mirror = mirror_store or _build_mirror_store(args.mirror_backend, data_dir=data_dir)
        report = build_rehearsal_report(
            primary_store=primary,
            mirror_store=mirror,
            execute=execute,
            run_id=args.run_id or os.environ.get(RUN_ID_ENV),
            primary_backend=args.primary_backend,
            mirror_backend=args.mirror_backend,
            max_background_jobs=args.max_background_jobs,
            max_app_health_alerts=args.max_app_health_alerts,
        )
        report = redact_secret_values(report)
    except Exception as exc:  # noqa: BLE001 - CLI boundary must redact errors.
        print(f"ERROR: {redact_secret_text(str(exc))}", file=stderr)
        return 1

    output = args.output or _default_output(report, execute=bool(args.execute))
    if output is not None:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if str(report.get("gate_recommendation") or "").startswith(("DRY_RUN_PASS", "PASS")) else 1


def build_rehearsal_report(
    *,
    primary_store: Any,
    mirror_store: Any,
    execute: bool,
    run_id: str | None = None,
    primary_backend: str | None = None,
    mirror_backend: str | None = None,
    max_background_jobs: int = 5000,
    max_app_health_alerts: int = 200,
) -> dict[str, Any]:
    run_id = run_id or f"stage15-mirror-write-{_utc_compact()}"
    background_jobs = _mapping_snapshot(primary_store.load_background_jobs())
    app_health_alerts = _alert_snapshot(primary_store.load_app_health_alerts())
    policy_report = build_runtime_policy_report(
        primary_store=primary_store,
        shadow_store=mirror_store,
        run_id=f"{run_id}-policy",
        primary_backend=primary_backend,
        shadow_backend=mirror_backend,
    )
    plan = _build_plan(
        background_jobs=background_jobs,
        app_health_alerts=app_health_alerts,
        max_background_jobs=max_background_jobs,
        max_app_health_alerts=max_app_health_alerts,
    )
    counts_before = _target_counts(mirror_store)
    base_report = {
        "run_id": run_id,
        "generated_at": _utc_now(),
        "redacted": True,
        "mode": "execute" if execute else "dry_run",
        "primary_backend": primary_backend or str(getattr(primary_store, "storage_backend", "unknown")),
        "mirror_backend": mirror_backend or str(getattr(mirror_store, "storage_backend", "unknown")),
        "target_tables": [
            "job.background_jobs",
            "audit.app_health_alerts",
            "app.app_settings[state:background_jobs,state:app_health_alerts]",
        ],
        "policy_summary": policy_report.get("summary", {}),
        "plan": plan,
        "counts_before": counts_before,
    }
    if int(policy_report.get("summary", {}).get("blocked_unknown_count") or 0):
        return {
            **base_report,
            "executed": False,
            "counts_after": counts_before,
            "gate_recommendation": "BLOCKED_RUNTIME_POLICY_UNKNOWN",
        }
    if plan["bound_status"] != "pass":
        return {
            **base_report,
            "executed": False,
            "counts_after": counts_before,
            "gate_recommendation": "BLOCKED_ROW_COUNT_BOUND",
        }
    if not execute:
        return {
            **base_report,
            "executed": False,
            "counts_after": counts_before,
            "gate_recommendation": "DRY_RUN_PASS",
        }

    mirror_store.save_background_jobs(background_jobs)
    mirror_store.save_app_health_alerts(app_health_alerts)
    counts_after = _target_counts(mirror_store)
    return {
        **base_report,
        "executed": True,
        "write_methods_called": ["save_background_jobs", "save_app_health_alerts"],
        "counts_after": counts_after,
        "gate_recommendation": "PASS",
    }


def _build_plan(
    *,
    background_jobs: Mapping[str, Mapping[str, Any]],
    app_health_alerts: Mapping[str, Any],
    max_background_jobs: int,
    max_app_health_alerts: int,
) -> dict[str, Any]:
    alert_records = _alert_records(app_health_alerts)
    checks = {
        "background_jobs": {
            "planned_count": len(background_jobs),
            "max_count": max_background_jobs,
            "status": "pass" if len(background_jobs) <= max_background_jobs else "blocked",
        },
        "app_health_alerts": {
            "planned_count": len(alert_records),
            "max_count": max_app_health_alerts,
            "status": "pass" if len(alert_records) <= max_app_health_alerts else "blocked",
        },
        "app_settings_runtime_rows": {
            "planned_count": 2,
            "max_count": 2,
            "status": "pass",
        },
    }
    return {
        "bounds": checks,
        "bound_status": "pass" if all(item["status"] == "pass" for item in checks.values()) else "blocked",
        "snapshot_hashes": {
            "background_jobs": _fingerprint(background_jobs),
            "app_health_alerts": _fingerprint(app_health_alerts),
        },
    }


def _target_counts(store: Any) -> dict[str, int]:
    connection = getattr(store, "_connection", None)
    if connection is None:
        return {}
    rows = connection.fetch_all(TARGET_COUNT_SQL)
    return {str(row.get("table_name")): int(row.get("row_count") or 0) for row in rows}


def _build_primary_store(backend: str, *, data_dir: Path) -> Any:
    if backend == "local_pickle":
        return ApplicationStateStore(data_dir, read_only=True)
    if backend == "mongo_readonly":
        _enforce_read_only_guard(True)
        store = ApplicationStateStore(data_dir, read_only=True)
        if store.storage_backend != "mongo":
            raise RuntimeError("mongo_readonly backend requires app Mongo state settings in data_dir/env.")
        return store
    raise RuntimeError(f"Unsupported primary backend {backend!r}.")


def _build_mirror_store(backend: str, *, data_dir: Path) -> Any:
    if backend == "postgres":
        return PostgresStateStore(data_dir=data_dir, connection=PostgresConnection(PostgresSettings.from_env()))
    raise RuntimeError(f"Unsupported mirror backend {backend!r}.")


def _mapping_snapshot(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    return {str(key): dict(item) for key, item in value.items() if isinstance(item, dict)}


def _alert_snapshot(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _alert_records(value: Any) -> dict[str, dict[str, Any]]:
    if not isinstance(value, dict):
        return {}
    records = value.get("records") if isinstance(value.get("records"), dict) else value
    return {str(key): dict(item) for key, item in records.items() if isinstance(item, dict)}


def _fingerprint(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, default=str).encode("utf-8")).hexdigest()


def _enforce_read_only_guard(required: bool) -> None:
    if required and os.environ.get(READ_ONLY_GUARD_ENV) != "1":
        raise RuntimeError(f"controlled mirror-write rehearsal requires {READ_ONLY_GUARD_ENV}=1 for primary reads.")


def _enforce_execute_guards() -> None:
    if os.environ.get(EXECUTE_GUARD_ENV) != "1":
        raise RuntimeError(f"--execute requires {EXECUTE_GUARD_ENV}=1.")
    if os.environ.get(BACKUP_CONFIRMED_ENV) != "1":
        raise RuntimeError(f"--execute requires {BACKUP_CONFIRMED_ENV}=1.")


def _default_output(report: Mapping[str, Any], *, execute: bool) -> Path:
    run_id = re.sub(r"[^A-Za-z0-9_.-]+", "-", str(report.get("run_id") or "stage15-mirror-write")).strip("-")
    suffix = "mirror-write-result" if execute else "mirror-write-dry-run"
    return DEFAULT_REPORT_DIR / f"{run_id}.stage15.{suffix}.json"


def _utc_now() -> str:
    return datetime.now(UTC).replace(microsecond=0).isoformat()


def _utc_compact() -> str:
    return datetime.now(UTC).strftime("%Y%m%d%H%M%S")


if __name__ == "__main__":
    raise SystemExit(main())
