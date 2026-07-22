from __future__ import annotations

import argparse
from collections.abc import Sequence
from hashlib import sha256
import json
import re
import sys
from typing import Any, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository


FAILED_STATUS = "failed"
RETRY_REASON = "operator_retry_failed_scope"
SCOPE_MONTH_PATTERN = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Inspect or requeue one failed Workbench matching scope through the durable repository boundary."
    )
    parser.add_argument("--scope-month", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint")
    parser.add_argument("--tenant-id", default="default")
    return parser


def main(
    argv: Sequence[str] | None = None,
    *,
    repository: Any | None = None,
    stdout: TextIO | None = None,
) -> int:
    stdout = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    scope_month = str(args.scope_month or "").strip()
    tenant_id = str(args.tenant_id or "default").strip() or "default"
    if not SCOPE_MONTH_PATTERN.fullmatch(scope_month):
        raise SystemExit("--scope-month must be YYYY-MM")
    if args.dry_run and args.expected_fingerprint:
        raise SystemExit("--dry-run does not accept --expected-fingerprint")
    if args.execute and not args.expected_fingerprint:
        raise SystemExit("--execute requires --expected-fingerprint")

    active_repository = repository or PostgresReadModelRepository(
        PostgresConnection(PostgresSettings.from_env())
    )
    scope = _failed_scope(
        active_repository.list_workbench_matching_dirty_scopes(tenant_id=tenant_id),
        scope_month=scope_month,
    )
    plan = _retry_plan(scope, tenant_id=tenant_id, scope_month=scope_month)
    fingerprint = _fingerprint(plan)
    if args.execute and str(args.expected_fingerprint) != fingerprint:
        raise RuntimeError(
            "Workbench matching scope changed after dry-run; rerun dry-run before execute."
        )

    written = False
    if args.execute:
        written = bool(active_repository.retry_failed_workbench_matching_scope(
            tenant_id=tenant_id,
            scope_month=scope_month,
            reason=RETRY_REASON,
            expected_attempt_count=int(scope.get("attempt_count") or 0),
            expected_request_id=str(scope.get("request_id") or ""),
            expected_last_error=str(scope.get("last_error") or ""),
            expected_source_versions=dict(scope.get("source_versions") or {}),
        ))
        if not written:
            raise RuntimeError(
                "Workbench matching scope changed during execute; no retry was queued."
            )

    report = {
        "action": "workbench_matching_failed_scope_retry",
        "mode": "execute" if args.execute else "dry_run",
        "tenant_id": tenant_id,
        "scope_month": scope_month,
        "status_before": FAILED_STATUS,
        "attempt_count": int(scope.get("attempt_count") or 0),
        "last_error_sha256": _text_sha256(scope.get("last_error")),
        "fingerprint": fingerprint,
        "written": written,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _failed_scope(rows: list[dict[str, Any]], *, scope_month: str) -> dict[str, Any]:
    matches = [row for row in rows if str(row.get("scope_month") or "").strip() == scope_month]
    if len(matches) != 1:
        raise RuntimeError("Workbench matching scope was not found exactly once.")
    scope = matches[0]
    if str(scope.get("status") or "").strip() != FAILED_STATUS:
        raise RuntimeError("Workbench matching scope is not failed; refusing to requeue it.")
    return scope


def _retry_plan(scope: dict[str, Any], *, tenant_id: str, scope_month: str) -> dict[str, Any]:
    return {
        "tenant_id": tenant_id,
        "scope_month": scope_month,
        "status": str(scope.get("status") or ""),
        "attempt_count": int(scope.get("attempt_count") or 0),
        "request_id": str(scope.get("request_id") or ""),
        "last_error_sha256": _text_sha256(scope.get("last_error")),
        "source_versions": dict(scope.get("source_versions") or {}),
    }


def _fingerprint(payload: dict[str, Any]) -> str:
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return sha256(encoded).hexdigest()


def _text_sha256(value: Any) -> str:
    return sha256(str(value or "").encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
