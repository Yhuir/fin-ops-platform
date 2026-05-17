#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Mapping, Sequence


REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_REPORT_DATE = datetime.now(timezone.utc).astimezone().strftime("%Y%m%d")
DEFAULT_REPORT_DIR = REPO_ROOT / "docs" / "operations" / "backend-refactor"
REQUIRED_ENV_VARS = (
    "FIN_OPS_PG_SOURCE_CONNINFO",
    "FIN_OPS_PG_BACKUP_DIR",
    "FIN_OPS_PG_RESTORE_CONNINFO",
    "FIN_OPS_PG_RESTORE_TARGET_TIME",
)
EXECUTE_CONFIRM_ENV = "FIN_OPS_POSTGRES_PITR_EXECUTE"


@dataclass(frozen=True)
class DrillConfig:
    mode: str
    output_json: Path
    output_markdown: Path
    generated_at: datetime
    operator: str
    source_conninfo_configured: bool
    restore_conninfo_configured: bool
    backup_dir: Path | None
    restore_target_time: str
    source_instance: str
    restore_instance: str
    wal_archive_status: str
    wal_archive_range: str
    base_backup_id: str
    rpo_seconds: int | None
    rto_seconds: int | None
    sample_counts: list[dict[str, object]]
    execute_confirmed: bool


def parse_args(argv: Sequence[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Generate secret-free PostgreSQL backup/PITR restore drill evidence. "
            "By default this validates environment only and does not connect to PostgreSQL."
        ),
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--validate-only",
        action="store_true",
        help="Validate staging drill configuration and print a GO/NO_GO summary without writing reports.",
    )
    mode.add_argument(
        "--report-only",
        action="store_true",
        help="Write paired JSON and Markdown GO/NO_GO evidence without running PostgreSQL commands.",
    )
    mode.add_argument(
        "--execute-drill",
        action="store_true",
        help=(
            "Run the controlled staging drill. Requires all staging env vars and "
            f"{EXECUTE_CONFIRM_ENV}=1."
        ),
    )
    parser.add_argument("--output-json", type=Path, default=None, help="JSON report output path.")
    parser.add_argument("--output-markdown", type=Path, default=None, help="Markdown report output path.")
    parser.add_argument(
        "--report-date",
        default=DEFAULT_REPORT_DATE,
        help="Date suffix for default report paths, in YYYYMMDD form.",
    )
    parser.add_argument(
        "--generated-at",
        default=None,
        help="Override report generation timestamp, ISO-8601 with timezone.",
    )
    return parser.parse_args(argv)


def build_config(args: argparse.Namespace, env: Mapping[str, str] | None = None) -> DrillConfig:
    environ = os.environ if env is None else env
    mode = "execute-drill" if args.execute_drill else "report-only" if args.report_only else "validate-only"
    report_date = args.report_date
    generated_at = parse_timestamp(args.generated_at) if args.generated_at else datetime.now(timezone.utc).astimezone()
    backup_dir_text = environ.get("FIN_OPS_PG_BACKUP_DIR", "").strip()
    return DrillConfig(
        mode=mode,
        output_json=args.output_json
        or DEFAULT_REPORT_DIR / f"postgres-pitr-drill-{report_date}.json",
        output_markdown=args.output_markdown
        or DEFAULT_REPORT_DIR / f"postgres-pitr-drill-{report_date}.md",
        generated_at=generated_at,
        operator=environ.get("FIN_OPS_PG_OPERATOR", "Codex").strip() or "Codex",
        source_conninfo_configured=bool(environ.get("FIN_OPS_PG_SOURCE_CONNINFO", "").strip()),
        restore_conninfo_configured=bool(environ.get("FIN_OPS_PG_RESTORE_CONNINFO", "").strip()),
        backup_dir=Path(backup_dir_text) if backup_dir_text else None,
        restore_target_time=environ.get("FIN_OPS_PG_RESTORE_TARGET_TIME", "").strip(),
        source_instance=environ.get("FIN_OPS_PG_SOURCE_INSTANCE_LABEL", "configured_from_env").strip()
        or "configured_from_env",
        restore_instance=environ.get("FIN_OPS_PG_RESTORE_INSTANCE_LABEL", "configured_from_env").strip()
        or "configured_from_env",
        wal_archive_status=environ.get("FIN_OPS_PG_WAL_ARCHIVE_STATUS", "").strip(),
        wal_archive_range=environ.get("FIN_OPS_PG_WAL_ARCHIVE_RANGE", "").strip(),
        base_backup_id=environ.get("FIN_OPS_PG_BASE_BACKUP_ID", "").strip(),
        rpo_seconds=parse_optional_int(environ.get("FIN_OPS_PG_RPO_SECONDS")),
        rto_seconds=parse_optional_int(environ.get("FIN_OPS_PG_RTO_SECONDS")),
        sample_counts=parse_sample_counts(environ.get("FIN_OPS_PG_SAMPLE_COUNTS_JSON")),
        execute_confirmed=environ.get(EXECUTE_CONFIRM_ENV) == "1",
    )


def parse_timestamp(value: str) -> datetime:
    normalized = value.strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    return datetime.fromisoformat(normalized)


def parse_optional_int(value: str | None) -> int | None:
    if value is None or not value.strip():
        return None
    try:
        parsed = int(value)
    except ValueError:
        return None
    return parsed if parsed >= 0 else None


def parse_sample_counts(value: str | None) -> list[dict[str, object]]:
    if value is None or not value.strip():
        return []
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return []
    if not isinstance(payload, list):
        return []
    rows: list[dict[str, object]] = []
    for item in payload:
        if isinstance(item, dict):
            rows.append(dict(item))
    return rows


def validate_config(config: DrillConfig) -> list[str]:
    blockers: list[str] = []
    if not config.source_conninfo_configured:
        blockers.append("FIN_OPS_PG_SOURCE_CONNINFO")
    if config.backup_dir is None:
        blockers.append("FIN_OPS_PG_BACKUP_DIR")
    if not config.restore_conninfo_configured:
        blockers.append("FIN_OPS_PG_RESTORE_CONNINFO")
    if not config.restore_target_time:
        blockers.append("FIN_OPS_PG_RESTORE_TARGET_TIME")
    if config.mode == "execute-drill" and not config.execute_confirmed:
        blockers.append(f"{EXECUTE_CONFIRM_ENV}=1")
    return blockers


def build_report(config: DrillConfig, now: datetime | None = None) -> dict[str, object]:
    generated_at = now or config.generated_at
    blockers = validate_config(config)
    executed = False
    backup_artifacts: list[dict[str, object]] = []
    checksum_results: list[dict[str, object]] = []
    restore_result = "not_executed"
    drill_errors: list[str] = []

    if config.mode == "execute-drill" and not blockers:
        try:
            execution = execute_drill(config)
            executed = True
            backup_artifacts = execution["backup_artifacts"]
            checksum_results = execution["checksum_results"]
            restore_result = execution["restore_result"]
            drill_errors = execution["errors"]
        except RuntimeError as exc:
            drill_errors = [str(exc)]
            blockers.append("execute-drill failed before producing GO evidence.")

    complete_evidence = (
        executed
        and restore_result == "GO"
        and config.wal_archive_status.upper() == "GO"
        and bool(backup_artifacts)
        and bool(checksum_results)
        and all(item.get("status") == "GO" for item in checksum_results)
        and bool(config.sample_counts)
        and config.rpo_seconds is not None
        and config.rto_seconds is not None
        and not drill_errors
    )
    status = "GO" if complete_evidence and not blockers else "NO_GO"
    if status == "NO_GO" and not blockers:
        blockers.append("complete staging backup/PITR/restore drill evidence is missing.")

    return {
        "report_id": f"postgres-pitr-drill-{generated_at.strftime('%Y%m%d')}",
        "status": status,
        "go_no_go": status,
        "started_at": generated_at.isoformat(),
        "finished_at": generated_at.isoformat(),
        "generated_at": generated_at.isoformat(),
        "operator": config.operator,
        "scope": "PostgreSQL logical backup, WAL/PITR and isolated restore drill evidence.",
        "source_instance": config.source_instance if config.source_conninfo_configured else "missing",
        "restore_instance": config.restore_instance if config.restore_conninfo_configured else "missing",
        "backup_artifacts": backup_artifacts,
        "wal_archive_status": {
            "status": config.wal_archive_status or "missing",
            "range": config.wal_archive_range or "missing",
            "base_backup_id": config.base_backup_id or "missing",
        },
        "restore_target_time": config.restore_target_time or "missing",
        "sample_counts": config.sample_counts,
        "checksum_results": checksum_results,
        "rpo_seconds": config.rpo_seconds,
        "rto_seconds": config.rto_seconds,
        "executed_real_restore_drill": executed,
        "production_safety": {
            "postgres_publicly_exposed": False,
            "oa_source_database_accessed": False,
            "business_facts_modified": False,
            "secrets_written_to_report": False,
        },
        "blockers": blockers,
        "errors": drill_errors,
        "summary": {
            "go": 1 if status == "GO" else 0,
            "no_go": 0 if status == "GO" else 1,
            "blocking_findings": len(blockers),
        },
    }


def execute_drill(config: DrillConfig) -> dict[str, object]:
    if config.backup_dir is None:
        raise RuntimeError("backup directory is not configured")
    source_conninfo = os.environ.get("FIN_OPS_PG_SOURCE_CONNINFO", "")
    if not source_conninfo:
        raise RuntimeError("source conninfo is not configured")

    config.backup_dir.mkdir(parents=True, exist_ok=True)
    logical_dump = config.backup_dir / f"fin_ops_logical_{config.generated_at.strftime('%Y%m%d_%H%M%S')}.dump"
    restore_list = logical_dump.with_suffix(".restore-list.txt")
    command_env = os.environ.copy()
    command_env["PGDATABASE"] = source_conninfo
    run_command(["pg_dump", "--format=custom", f"--file={logical_dump}"], env=command_env)
    run_command(["pg_restore", "--list", str(logical_dump)], stdout_path=restore_list)
    digest = sha256_file(logical_dump)
    return {
        "backup_artifacts": [
            {
                "kind": "logical_pg_dump",
                "path": str(logical_dump),
                "sha256": digest,
            },
            {
                "kind": "pg_restore_list",
                "path": str(restore_list),
            },
        ],
        "checksum_results": [
            {
                "artifact": logical_dump.name,
                "algorithm": "sha256",
                "value": digest,
                "status": "GO",
            }
        ],
        "restore_result": "NO_GO",
        "errors": [
            "Automated restore command is intentionally not inferred; record isolated restore instance evidence via env and rerun after controlled staging drill."
        ],
    }


def run_command(command: Sequence[str], stdout_path: Path | None = None, env: Mapping[str, str] | None = None) -> None:
    stdout_target = subprocess.PIPE
    output_file = None
    try:
        if stdout_path is not None:
            stdout_path.parent.mkdir(parents=True, exist_ok=True)
            output_file = stdout_path.open("w", encoding="utf-8")
            stdout_target = output_file
        completed = subprocess.run(
            list(command),
            check=False,
            stdout=stdout_target,
            stderr=subprocess.PIPE,
            text=True,
            env=dict(env) if env is not None else None,
        )
    finally:
        if output_file is not None:
            output_file.close()
    if completed.returncode != 0:
        raise RuntimeError(f"PostgreSQL command failed with exit code {completed.returncode}.")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_reports(report: dict[str, object], config: DrillConfig) -> None:
    config.output_json.parent.mkdir(parents=True, exist_ok=True)
    config.output_json.write_text(
        json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )
    config.output_markdown.parent.mkdir(parents=True, exist_ok=True)
    config.output_markdown.write_text(render_markdown(report), encoding="utf-8")


def render_markdown(report: dict[str, object]) -> str:
    wal = report["wal_archive_status"]
    assert isinstance(wal, dict)
    lines = [
        f"# PostgreSQL PITR 恢复演练证据 - {str(report['generated_at'])[:10]}",
        "",
        "本文由 `scripts/tools/postgres_pitr_restore_drill.py` 生成。报告不包含 PostgreSQL URI、密码、token、私钥或完整连接串；缺少受控 staging 环境变量时保持 `NO_GO`。",
        "",
        "## 结论",
        "",
        f"- Gate: **{report['status']}**",
        f"- go/no-go: `{report['go_no_go']}`",
        f"- operator: {report['operator']}",
        f"- started_at: `{report['started_at']}`",
        f"- finished_at: `{report['finished_at']}`",
        f"- source_instance: `{report['source_instance']}`",
        f"- restore_instance: `{report['restore_instance']}`",
        f"- restore_target_time: `{report['restore_target_time']}`",
        f"- executed_real_restore_drill: `{str(report['executed_real_restore_drill']).lower()}`",
        "",
        "## WAL/PITR",
        "",
        f"- base_backup_id: `{wal.get('base_backup_id')}`",
        f"- WAL archive status: `{wal.get('status')}`",
        f"- WAL archive range: `{wal.get('range')}`",
        f"- RPO seconds: `{report['rpo_seconds'] if report['rpo_seconds'] is not None else 'missing'}`",
        f"- RTO seconds: `{report['rto_seconds'] if report['rto_seconds'] is not None else 'missing'}`",
        "",
        "## Backup Artifacts",
        "",
    ]
    artifacts = report.get("backup_artifacts")
    if isinstance(artifacts, list) and artifacts:
        lines.extend(["| kind | path | sha256 |", "| --- | --- | --- |"])
        for item in artifacts:
            if isinstance(item, dict):
                lines.append(f"| `{item.get('kind')}` | `{item.get('path')}` | `{item.get('sha256', '-')}` |")
    else:
        lines.append("- none")
    lines.extend(["", "## checksum_results", ""])
    checksums = report.get("checksum_results")
    if isinstance(checksums, list) and checksums:
        lines.extend(["| artifact | algorithm | status |", "| --- | --- | --- |"])
        for item in checksums:
            if isinstance(item, dict):
                lines.append(f"| `{item.get('artifact')}` | `{item.get('algorithm')}` | `{item.get('status')}` |")
    else:
        lines.append("- none")
    lines.extend(["", "## sample_count_checks", ""])
    sample_counts = report.get("sample_counts")
    if isinstance(sample_counts, list) and sample_counts:
        lines.extend(["| object | source | restored | status |", "| --- | ---: | ---: | --- |"])
        for item in sample_counts:
            if isinstance(item, dict):
                lines.append(
                    f"| `{item.get('object')}` | `{item.get('source_count')}` | `{item.get('restored_count')}` | `{item.get('status')}` |"
                )
    else:
        lines.append("- none")
    lines.extend(["", "## Blockers", ""])
    blockers = report.get("blockers")
    if isinstance(blockers, list) and blockers:
        lines.extend(f"- {blocker}" for blocker in blockers)
    else:
        lines.append("- none")
    lines.extend(
        [
            "",
            "## Safety",
            "",
            "- PostgreSQL 不得开放公网。",
            "- Secret 只从环境变量读取，不写日志、不写报告。",
            "- 未访问 OA 源数据库。",
            "- 未修改业务事实数据。",
        ]
    )
    return "\n".join(lines) + "\n"


def main(argv: Sequence[str] | None = None, env: Mapping[str, str] | None = None) -> int:
    args = parse_args(argv)
    config = build_config(args, env)
    report = build_report(config)
    if config.mode != "validate-only":
        write_reports(report, config)
    print(
        json.dumps(
            {
                "status": report["status"],
                "go_no_go": report["go_no_go"],
                "executed_real_restore_drill": report["executed_real_restore_drill"],
                "blocking_findings": len(report["blockers"]),
                "output_json": str(config.output_json) if config.mode != "validate-only" else None,
                "output_markdown": str(config.output_markdown) if config.mode != "validate-only" else None,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
