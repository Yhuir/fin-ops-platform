from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.app_settings_service import OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING
from fin_ops_platform.services.imports import ImportNormalizationService
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
    connection = PostgresConnection(PostgresSettings.from_env())
    report = audit_oa_attachment_invoice_promotion(
        connection=connection,
        example_limit=max(int(args.limit or 50), 1),
        apply=bool(args.apply),
        oa_row_ids=list(args.oa_row_id or []),
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def audit_oa_attachment_invoice_promotion(
    *,
    connection: Any,
    example_limit: int = 50,
    apply: bool = False,
    oa_row_ids: list[str] | None = None,
) -> dict[str, Any]:
    service = OAAttachmentInvoicePromotionService(
        invoice_repository=PostgresOAAttachmentInvoiceRepository(connection),
    )
    return service.promote_candidates(
        _load_candidates(connection, oa_row_ids=oa_row_ids),
        promotion_mode=OA_ATTACHMENT_INVOICE_PROMOTION_CREATE_MISSING,
        apply=apply,
        example_limit=example_limit,
    )


def _load_candidates(
    connection: Any,
    *,
    oa_row_ids: list[str] | None = None,
) -> list[OAAttachmentInvoiceCandidate]:
    rows = PostgresOAAttachmentInvoiceRepository(connection).list_promotion_source_rows(
        oa_row_ids=oa_row_ids,
    )
    candidates: list[OAAttachmentInvoiceCandidate] = []
    seen_candidates: set[tuple[str, str, str, str]] = set()
    row_id_service = ImportNormalizationService()
    for row in rows:
        invoices = row.get("invoices")
        if not isinstance(invoices, list):
            continue
        cache_key = _clean_text(row.get("cache_source_attachment_key"))
        context = {key: row.get(key) for key in row.keys() if key != "invoices"}
        oa_row_id = _clean_text(row.get("oa_row_id"))
        oa_form_id = _clean_text(row.get("oa_application_id")) or oa_row_id
        context_attachment_key = _clean_text(row.get("source_attachment_key"))
        for index, invoice_payload in enumerate(invoices):
            if not isinstance(invoice_payload, dict):
                continue
            attachment_invoice = dict(invoice_payload)
            if context_attachment_key:
                attachment_invoice["source_attachment_key"] = context_attachment_key
            else:
                attachment_invoice.setdefault("source_attachment_key", cache_key)
            for key in (
                "source_expense_item_id",
                "source_expense_row_index",
                "source_attachment_name",
            ):
                value = _clean_text(row.get(key))
                if value:
                    attachment_invoice[key] = value
            source_workbench_row_id = (
                row_id_service.oa_attachment_invoice_row_id(oa_row_id, index, attachment_invoice)
                if oa_row_id
                else None
            )
            candidate_key = (
                oa_row_id or "",
                source_workbench_row_id or "",
                _clean_text(attachment_invoice.get("source_attachment_key")) or "",
                _clean_text(attachment_invoice.get("source_expense_item_id")) or "",
            )
            if candidate_key in seen_candidates:
                continue
            seen_candidates.add(candidate_key)
            candidates.append(
                OAAttachmentInvoiceCandidate(
                    cache_source_attachment_key=cache_key or "",
                    invoice_index=index,
                    attachment_invoice=attachment_invoice,
                    oa_form_id=oa_form_id,
                    oa_row_id=oa_row_id,
                    source_workbench_row_id=source_workbench_row_id,
                    context=context,
                )
            )
    return candidates


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
