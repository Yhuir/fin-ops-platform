from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from dataclasses import asdict, dataclass
from typing import Any, TextIO

from fin_ops_platform.services.app_status_read_model_registry import APP_STATUS_READ_MODEL_REGISTRY
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.runtime_monitoring import RuntimeMonitoringRepository


@dataclass(frozen=True)
class ReadinessBackfillResult:
    read_model_key: str
    scope_type: str
    scope_key: str
    status: str
    row_count: int | None
    schema_version: str
    source_versions: dict[str, Any]
    generated_at: str
    last_error: str
    applied: bool = False


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Backfill app status read model readiness from durable read model facts.")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="Inspect readiness facts without writing read_model.app_status_readiness.")
    mode.add_argument("--apply", action="store_true", help="Write computed readiness facts to read_model.app_status_readiness.")
    parser.add_argument("--read-model-key", action="append", default=[], help="Limit to one or more app status read_model_key values.")
    parser.add_argument("--tenant-id", default="default")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    connection: Any | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    stderr = stderr or sys.stderr
    args = build_parser().parse_args(argv)
    active_connection = connection or PostgresConnection(PostgresSettings.from_env())
    keys = tuple(args.read_model_key or sorted(APP_STATUS_READ_MODEL_REGISTRY))
    unknown = [key for key in keys if key not in APP_STATUS_READ_MODEL_REGISTRY]
    if unknown:
        print(f"unknown read model key(s): {', '.join(unknown)}", file=stderr)
        return 2

    repository = RuntimeMonitoringRepository(active_connection)
    results = [compute_readiness(repository, key, tenant_id=args.tenant_id) for key in keys]
    if args.apply:
        applied_results: list[ReadinessBackfillResult] = []
        for result in results:
            repository.record_read_model_readiness(
                tenant_id=args.tenant_id,
                read_model_key=result.read_model_key,
                scope_type=result.scope_type,
                scope_key=result.scope_key,
                status=result.status,
                schema_version=result.schema_version,
                source_versions=result.source_versions,
                row_count=result.row_count,
                generated_at=result.generated_at or None,
                last_error=result.last_error or None,
                raw_payload={"backfill": True},
            )
            applied_results.append(ReadinessBackfillResult(**{**asdict(result), "applied": True}))
        results = applied_results

    print(
        json.dumps(
            {
                "mode": "apply" if args.apply else "dry-run",
                "tenant_id": args.tenant_id,
                "results": [asdict(result) for result in results],
            },
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
        ),
        file=stdout,
    )
    return 0


def compute_readiness(repository: Any, read_model_key: str, *, tenant_id: str = "default") -> ReadinessBackfillResult:
    definition = APP_STATUS_READ_MODEL_REGISTRY[read_model_key]
    try:
        row = repository.app_status_readiness_backfill_fact(read_model_key, tenant_id=tenant_id)
    except Exception as exc:
        return ReadinessBackfillResult(
            read_model_key=read_model_key,
            scope_type=definition.scope_type,
            scope_key="all",
            status="unavailable",
            row_count=None,
            schema_version="",
            source_versions={},
            generated_at="",
            last_error=str(exc) or exc.__class__.__name__,
        )
    if row is None:
        return ReadinessBackfillResult(
            read_model_key=read_model_key,
            scope_type=definition.scope_type,
            scope_key="all",
            status="missing",
            row_count=None,
            schema_version="",
            source_versions={},
            generated_at="",
            last_error=f"{read_model_key} has no fresh projection fact",
        )
    status = str(row.get("status") or row.get("cache_status") or "fresh").strip().lower() or "fresh"
    if status == "ready":
        status = "fresh"
    if status == "pending" or status == "processing":
        status = "refreshing"
    if status not in {
        "fresh",
        "missing",
        "refreshing",
        "stale",
        "failed",
        "schema_mismatch",
        "source_mismatch",
        "unavailable",
    }:
        status = "missing"
    return ReadinessBackfillResult(
        read_model_key=read_model_key,
        scope_type=definition.scope_type,
        scope_key=str(row.get("scope_key") or "all").strip() or "all",
        status=status,
        row_count=_optional_int(row.get("row_count") if row.get("row_count") is not None else row.get("entry_count")),
        schema_version=str(row.get("schema_version") or ""),
        source_versions=row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
        generated_at=str(row.get("generated_at") or ""),
        last_error=str(row.get("last_error") or ""),
    )


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
