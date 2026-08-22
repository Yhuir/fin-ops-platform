from __future__ import annotations

import argparse
import hashlib
import json
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.app_settings_service import OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoiceCandidate,
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)


APPLY_CONFIRMATION_FLAG = "--confirm-apply-oa-attachment-invoices"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply OA attachment formal invoice promotion into the unified invoice pool."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report. This is the default output format.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per action/reason.")
    parser.add_argument("--oa-row-id", action="append", default=[], help="Limit promotion to an exact OA row id.")
    parser.add_argument("--apply", action="store_true", help="Persist eligible OA attachment invoice links/creates.")
    parser.add_argument(
        "--expected-fingerprint",
        help="Required with --apply; must match the immediately preceding dry-run candidate fingerprint.",
    )
    parser.add_argument(
        APPLY_CONFIRMATION_FLAG,
        action="store_true",
        help="Required together with --apply to guard production writes.",
    )
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    args = build_parser().parse_args(list(argv or sys.argv[1:]))
    if bool(args.apply) and not bool(getattr(args, "confirm_apply_oa_attachment_invoices", False)):
        print(f"--apply requires {APPLY_CONFIRMATION_FLAG}", file=stdout)
        return 2
    if bool(args.apply) and not str(args.expected_fingerprint or "").strip():
        print("--apply requires --expected-fingerprint", file=stdout)
        return 2
    connection = PostgresConnection(PostgresSettings.from_env())
    report = audit_oa_attachment_invoice_promotion(
        connection=connection,
        example_limit=max(int(args.limit or 50), 1),
        apply=bool(args.apply),
        oa_row_ids=list(args.oa_row_id or []),
        expected_fingerprint=str(args.expected_fingerprint or "").strip() or None,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def audit_oa_attachment_invoice_promotion(
    *,
    connection: Any,
    example_limit: int = 50,
    apply: bool = False,
    oa_row_ids: list[str] | None = None,
    expected_fingerprint: str | None = None,
) -> dict[str, Any]:
    candidates = _load_candidates(connection, oa_row_ids=oa_row_ids)
    candidate_fingerprint = _candidate_fingerprint(candidates)
    if expected_fingerprint and expected_fingerprint != candidate_fingerprint:
        raise ValueError("OA attachment invoice candidate fingerprint changed; run dry-run again.")
    service = OAAttachmentInvoicePromotionService(
        invoice_repository=PostgresOAAttachmentInvoiceRepository(connection),
    )
    report = service.promote_candidates(
        candidates,
        promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
        apply=apply,
        example_limit=example_limit,
    )
    return {**report, "candidate_fingerprint": candidate_fingerprint}


def _load_candidates(
    connection: Any,
    *,
    oa_row_ids: list[str] | None = None,
) -> list[OAAttachmentInvoiceCandidate]:
    rows = PostgresOAAttachmentInvoiceRepository(connection).list_promotion_source_rows(
        oa_row_ids=oa_row_ids,
    )
    return OAAttachmentInvoicePromotionService.candidates_from_source_rows(rows)


def _candidate_fingerprint(candidates: list[OAAttachmentInvoiceCandidate]) -> str:
    rows = sorted(
        (
            candidate.oa_row_id or "",
            candidate.source_workbench_row_id or "",
            candidate.cache_source_attachment_key,
            str(candidate.invoice_index),
            json.dumps(candidate.attachment_invoice, ensure_ascii=False, sort_keys=True, default=str),
        )
        for candidate in candidates
    )
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())
