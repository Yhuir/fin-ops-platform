from __future__ import annotations

import argparse
from decimal import Decimal
import hashlib
import json
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.etc_service import EtcBusinessBatchInvalidTransitionError
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_SQL
from fin_ops_platform.tools.runtime_application import (
    build_tool_runtime_application,
    etc_reconciliation_task_service,
    etc_service,
    refresh_after_historical_etc_repair_link,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Restore one proven deleted submitted ETC business batch.")
    parser.add_argument("--business-batch-id", required=True)
    parser.add_argument("--expected-invoice-count", required=True, type=int)
    parser.add_argument("--expected-total-amount", required=True)
    parser.add_argument("--expected-oa-row-id", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument("--execute", action="store_true")
    parser.add_argument("--expected-fingerprint", default="")
    parser.add_argument("--operator", default="")
    parser.add_argument("--reason", default="")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or sys.argv[1:]))
    if args.execute and not str(args.expected_fingerprint or "").strip():
        parser.error("--expected-fingerprint is required with --execute")
    if args.execute and not str(args.operator or "").strip():
        parser.error("--operator is required with --execute")
    if args.execute and not str(args.reason or "").strip():
        parser.error("--reason is required with --execute")

    app = build_tool_runtime_application(None)
    service = etc_service(app)
    task_service = etc_reconciliation_task_service(app)
    try:
        inspection = service.preview_deleted_submitted_business_batch_restore(
            str(args.business_batch_id),
            expected_invoice_count=int(args.expected_invoice_count),
            expected_total_amount=Decimal(str(args.expected_total_amount)),
            expected_oa_row_id=None,
        )
    except EtcBusinessBatchInvalidTransitionError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "message": str(exc)}, ensure_ascii=False), file=stdout)
        return 2
    stored_oa_row_id = str(inspection.get("stored_oa_row_id") or "").strip()
    expected_oa_row_id = str(args.expected_oa_row_id).strip()
    try:
        canonical_title = str(task_service.get_task_record(str(inspection.get("task_id") or "")).title or "").strip()
    except (KeyError, TypeError, ValueError):
        canonical_title = ""
    if not canonical_title:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "business_batch_restore_task_title_unproven",
                    "task_id": inspection.get("task_id"),
                },
                ensure_ascii=False,
            ),
            file=stdout,
        )
        return 2
    oa_resolution = _resolve_oa_identity(
        connection=PostgresConnection(PostgresSettings.from_env()),
        stored_oa_row_id=stored_oa_row_id,
        expected_oa_row_id=expected_oa_row_id,
        external_etc_batch_id=str(inspection.get("external_etc_batch_id") or "").strip(),
    )
    if oa_resolution is None:
        print(
            json.dumps(
                {
                    "status": "blocked",
                    "code": "business_batch_restore_oa_identity_unproven",
                    "stored_oa_row_id": stored_oa_row_id,
                    "expected_oa_row_id": expected_oa_row_id,
                    "external_etc_batch_id": inspection.get("external_etc_batch_id"),
                },
                ensure_ascii=False,
            ),
            file=stdout,
        )
        return 2
    try:
        preview = service.preview_deleted_submitted_business_batch_restore(
            str(args.business_batch_id),
            expected_invoice_count=int(args.expected_invoice_count),
            expected_total_amount=Decimal(str(args.expected_total_amount)),
            expected_oa_row_id=stored_oa_row_id or None,
            canonical_oa_row_id=expected_oa_row_id,
            canonical_title=canonical_title,
        )
    except EtcBusinessBatchInvalidTransitionError as exc:
        print(json.dumps({"status": "blocked", "code": exc.code, "message": str(exc)}, ensure_ascii=False), file=stdout)
        return 2

    preview["oa_identity_resolution"] = oa_resolution
    fingerprint = _fingerprint(preview)
    payload: dict[str, object] = {
        "mode": "dry-run",
        "status": "already_restored" if preview.get("already_restored") else "ready",
        "fingerprint": fingerprint,
        "preview": preview,
    }
    if args.execute:
        if str(args.expected_fingerprint).strip() != fingerprint:
            print(
                json.dumps(
                    {
                        "status": "blocked",
                        "code": "fingerprint_mismatch",
                        "expected_fingerprint": str(args.expected_fingerprint).strip(),
                        "actual_fingerprint": fingerprint,
                    },
                    ensure_ascii=False,
                ),
                file=stdout,
            )
            return 2
        restored = service.restore_deleted_submitted_business_batch(
            str(args.business_batch_id),
            expected_version=int(preview["version"]),
            expected_invoice_count=int(args.expected_invoice_count),
            expected_total_amount=Decimal(str(args.expected_total_amount)),
            expected_oa_row_id=stored_oa_row_id or None,
            canonical_oa_row_id=expected_oa_row_id,
            canonical_title=canonical_title,
            reason=f"{str(args.reason).strip()} (operator={str(args.operator).strip()})",
        )
        scope_month = str(preview.get("scope_month") or "").strip()
        if not scope_month:
            raise RuntimeError("Restored ETC business batch scope month is unavailable.")
        refresh_after_historical_etc_repair_link(
            app,
            [scope_month],
            reason="deleted_submitted_etc_business_batch_restored",
        )
        payload = {
            "mode": "execute",
            "status": "normalized" if preview.get("already_restored") else "restored",
            "fingerprint": fingerprint,
            "business_batch_id": restored.business_batch_id,
            "status_after": restored.status,
            "version_after": restored.version,
            "submission_batch_id": restored.submission_batch_id,
            "invoice_count": len(restored.invoice_ids),
            "oa_row_id": restored.oa_row_id,
            "refreshed_scope_months": [scope_month],
        }
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def _fingerprint(preview: dict[str, object]) -> str:
    canonical = json.dumps(preview, ensure_ascii=False, separators=(",", ":"), sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _resolve_oa_alias(
    *,
    connection: Any,
    stored_oa_row_id: str,
    expected_oa_row_id: str,
) -> dict[str, str] | None:
    if not stored_oa_row_id or not expected_oa_row_id:
        return None
    if stored_oa_row_id == expected_oa_row_id:
        return {"mode": "exact", "stored_oa_row_id": stored_oa_row_id, "canonical_oa_row_id": expected_oa_row_id}
    row = connection.fetch_one(
        """
        select alias_row_id, canonical_row_id, status, evidence_hash
        from app.oa_source_aliases
        where alias_row_id = %s and canonical_row_id = %s and status = 'active'
        """,
        (stored_oa_row_id, expected_oa_row_id),
    )
    if not row:
        return None
    return {
        "mode": "active_alias",
        "stored_oa_row_id": stored_oa_row_id,
        "canonical_oa_row_id": expected_oa_row_id,
        "evidence_hash": str(row.get("evidence_hash") or ""),
    }


def _resolve_oa_identity(
    *,
    connection: Any,
    stored_oa_row_id: str,
    expected_oa_row_id: str,
    external_etc_batch_id: str,
) -> dict[str, str] | None:
    if stored_oa_row_id:
        return _resolve_oa_alias(
            connection=connection,
            stored_oa_row_id=stored_oa_row_id,
            expected_oa_row_id=expected_oa_row_id,
        )
    if not expected_oa_row_id or not external_etc_batch_id:
        return None
    rows = connection.fetch_all(
        """
        select row_id
        from app.oa_applications
        where normalized_payload->>'etc_batch_id' = %s
          and status <> 'deleted'
          and """
        + COMPLETED_WORKFLOW_STATUS_SQL
        + """
        order by row_id
        """,
        (external_etc_batch_id,),
    )
    row_ids = [str(row.get("row_id") or "").strip() for row in rows if str(row.get("row_id") or "").strip()]
    if row_ids != [expected_oa_row_id]:
        return None
    return {
        "mode": "external_etc_batch_id",
        "external_etc_batch_id": external_etc_batch_id,
        "canonical_oa_row_id": expected_oa_row_id,
    }


if __name__ == "__main__":
    raise SystemExit(main())
