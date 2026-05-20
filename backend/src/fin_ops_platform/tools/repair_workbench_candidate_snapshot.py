from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.common import jsonb, serialize_value
from fin_ops_platform.services.state_store import ApplicationStateStore, default_data_dir


SETTINGS_KEY = "state:workbench_candidate_matches"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Repair PostgreSQL workbench candidate runtime snapshot.")
    parser.add_argument("--mode", choices=("dry-run", "execute"), required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    snapshot = _load_validated_snapshot()
    snapshot_sha = _stable_sha(snapshot)
    connection = PostgresConnection(PostgresSettings.from_env())
    existing = _load_existing_summary(connection)
    read_model_count = _read_model_count(connection)
    summary: dict[str, Any] = {
        "run_id": args.run_id,
        "mode": args.mode,
        "validated": True,
        "write_executed": False,
        "authorized_write_scope": "app.app_settings settings_key='state:workbench_candidate_matches' only",
        "snapshot": _snapshot_summary(snapshot, snapshot_sha),
        "postgres_before": existing or {"exists": False},
        "read_model_workbench_candidate_matches_count": read_model_count,
        "app_mongo_written": False,
        "oa_mongo_form_data_touched": False,
        "service_modified_or_restarted": False,
        "read_model_cleanup_executed": False,
    }
    if args.mode == "execute":
        summary.update(_execute_repair(connection, snapshot, snapshot_sha))
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    print(json.dumps(_stdout_summary(summary), ensure_ascii=False, sort_keys=True))
    return 0


def _load_validated_snapshot() -> dict[str, Any]:
    store = ApplicationStateStore(default_data_dir(), read_only=True)
    snapshot = store.load_workbench_candidate_matches()
    if not isinstance(snapshot, dict):
        raise RuntimeError("workbench_candidate_matches snapshot is not a dict")
    normalized = serialize_value(snapshot)
    if not isinstance(normalized, dict):
        raise RuntimeError("normalized workbench_candidate_matches snapshot is not a dict")
    candidates = normalized.get("candidates")
    scope_runs = normalized.get("scope_runs")
    schema_version = normalized.get("schema_version")
    if not isinstance(candidates, dict) or not candidates:
        raise RuntimeError("snapshot candidates are missing or empty")
    if not isinstance(scope_runs, dict) or not scope_runs:
        raise RuntimeError("snapshot scope_runs are missing or empty")
    if not schema_version:
        raise RuntimeError("snapshot schema_version is missing")
    return normalized


def _stable_sha(payload: Any) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, default=str).encode()
    return hashlib.sha256(encoded).hexdigest()


def _snapshot_summary(snapshot: dict[str, Any], snapshot_sha: str) -> dict[str, Any]:
    return {
        "candidate_count": len(snapshot.get("candidates") or {}),
        "scope_run_count": len(snapshot.get("scope_runs") or {}),
        "schema_version": snapshot.get("schema_version"),
        "sha256": snapshot_sha,
    }


def _load_existing_summary(connection: PostgresConnection) -> dict[str, Any] | None:
    row = connection.fetch_one(
        """
        select
          version,
          (
            select count(*)
            from jsonb_object_keys(coalesce(settings_payload->'candidates', '{}'::jsonb))
          ) as candidate_count,
          (
            select count(*)
            from jsonb_object_keys(coalesce(settings_payload->'scope_runs', '{}'::jsonb))
          ) as scope_run_count,
          settings_payload->>'schema_version' as schema_version
        from app.app_settings
        where settings_key = %s
        """,
        (SETTINGS_KEY,),
    )
    return dict(row) if row else None


def _read_model_count(connection: PostgresConnection) -> int:
    row = connection.fetch_one("select count(*) as row_count from read_model.workbench_candidate_matches")
    return int(row.get("row_count") or 0) if row else 0


def _execute_repair(connection: PostgresConnection, snapshot: dict[str, Any], snapshot_sha: str) -> dict[str, Any]:
    affected = connection.execute(
        """
        insert into app.app_settings(settings_key, version, settings_payload, raw_payload, updated_at)
        values (%s, 1, %s, %s, now())
        on conflict (settings_key) do update set
          version = app.app_settings.version + 1,
          settings_payload = excluded.settings_payload,
          raw_payload = excluded.raw_payload,
          updated_at = now()
        """,
        (SETTINGS_KEY, jsonb(snapshot), jsonb({"normalized_payload": snapshot})),
    )
    if affected != 1:
        raise RuntimeError(f"expected one affected row, got {affected}")
    row = connection.fetch_one(
        """
        select
          version,
          settings_payload,
          (
            select count(*)
            from jsonb_object_keys(coalesce(settings_payload->'candidates', '{}'::jsonb))
          ) as candidate_count,
          (
            select count(*)
            from jsonb_object_keys(coalesce(settings_payload->'scope_runs', '{}'::jsonb))
          ) as scope_run_count,
          settings_payload->>'schema_version' as schema_version
        from app.app_settings
        where settings_key = %s
        """,
        (SETTINGS_KEY,),
    )
    if not row:
        raise RuntimeError("post-repair settings row is missing")
    payload = row.pop("settings_payload")
    after_sha = _stable_sha(payload)
    expected = _snapshot_summary(snapshot, snapshot_sha)
    actual = {
        "candidate_count": int(row.get("candidate_count") or 0),
        "scope_run_count": int(row.get("scope_run_count") or 0),
        "schema_version": row.get("schema_version"),
        "sha256": after_sha,
    }
    if actual != expected:
        raise RuntimeError(f"post-repair verification mismatch: expected {expected}, got {actual}")
    return {
        "write_executed": True,
        "affected_rows": affected,
        "postgres_after": {"version": row.get("version"), **actual},
    }


def _stdout_summary(summary: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": summary.get("mode"),
        "validated": summary.get("validated"),
        "write_executed": summary.get("write_executed"),
        "snapshot": summary.get("snapshot"),
        "postgres_after": summary.get("postgres_after"),
    }


if __name__ == "__main__":
    raise SystemExit(main())
