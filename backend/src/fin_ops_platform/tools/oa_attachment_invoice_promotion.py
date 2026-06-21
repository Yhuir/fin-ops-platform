from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import dataclass
import json
import re
import sys
from typing import Any, Sequence, TextIO

from fin_ops_platform.domain.models import Invoice
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.invoice_attachment_recognition_service import (
    CREATE_INVOICE_AND_LINK,
    IGNORE,
    LINK_EXISTING_INVOICE,
    InvoiceAttachmentRecognitionService,
)
from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository


APPLY_CONFIRMATION_FLAG = "--confirm-apply-oa-attachment-invoices"
_OA_SOURCE_RE = re.compile(r"^(oa-[^:]+)")


@dataclass(frozen=True, slots=True)
class OAAttachmentInvoiceCandidate:
    cache_source_attachment_key: str
    invoice_index: int
    attachment_invoice: dict[str, Any]
    oa_form_id: str | None
    oa_row_id: str | None
    source_workbench_row_id: str | None
    context: dict[str, Any]


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Dry-run or apply OA attachment formal invoice promotion into the unified invoice pool."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON report. This is the default output format.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per action/reason.")
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
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0


def audit_oa_attachment_invoice_promotion(
    *,
    connection: Any,
    example_limit: int = 50,
    apply: bool = False,
) -> dict[str, Any]:
    existing_invoices = _fetch_all_invoices(connection)
    initial_invoice_ids = {invoice.id for invoice in existing_invoices}
    initial_identity_keys = {
        str(key).strip()
        for invoice in existing_invoices
        for key in (invoice.source_unique_key, invoice.digital_invoice_no)
        if str(key or "").strip()
    }
    import_service = ImportNormalizationService(existing_invoices=existing_invoices)
    recognition_service = InvoiceAttachmentRecognitionService(invoice_repository=import_service)
    candidates = _load_candidates(connection)

    action_counts: Counter[str] = Counter()
    reason_counts: Counter[str] = Counter()
    examples: dict[str, list[dict[str, Any]]] = {}
    created_invoice_ids: set[str] = set()
    created_identity_keys: set[str] = set()
    linked_invoice_ids: set[str] = set()
    affected_invoices: list[Invoice] = []

    for candidate in candidates:
        decision = recognition_service.decide(candidate.attachment_invoice)
        if decision.action == IGNORE:
            action_counts[decision.action] += 1
            reason_counts[decision.reason] += 1
            _append_example(
                examples,
                f"{decision.action}:{decision.reason}",
                _candidate_example(
                    candidate,
                    action=decision.action,
                    reason=decision.reason,
                    identity_key=decision.identity_key,
                ),
                example_limit=example_limit,
            )
            continue

        if not candidate.oa_row_id or not candidate.source_workbench_row_id:
            action = IGNORE
            reason = "missing_oa_context"
            action_counts[action] += 1
            reason_counts[reason] += 1
            _append_example(
                examples,
                f"{action}:{reason}",
                _candidate_example(candidate, action=action, reason=reason),
                example_limit=example_limit,
            )
            continue

        action_counts[decision.action] += 1
        reason_counts[decision.reason] += 1

        invoice = import_service.upsert_oa_attachment_invoice(
            candidate.attachment_invoice,
            oa_form_id=candidate.oa_form_id,
            oa_row_id=candidate.oa_row_id,
            source_workbench_row_id=candidate.source_workbench_row_id,
            allow_create=decision.action == CREATE_INVOICE_AND_LINK,
        )
        if invoice is None:
            reason = "upsert_returned_none"
            action_counts[IGNORE] += 1
            reason_counts[reason] += 1
            _append_example(
                examples,
                f"{IGNORE}:{reason}",
                _candidate_example(candidate, action=IGNORE, reason=reason, identity_key=decision.identity_key),
                example_limit=example_limit,
            )
            continue

        affected_invoices.append(invoice)
        if invoice.id in initial_invoice_ids:
            linked_invoice_ids.add(invoice.id)
            effective_action = LINK_EXISTING_INVOICE
        else:
            created_invoice_ids.add(invoice.id)
            if invoice.source_unique_key:
                created_identity_keys.add(invoice.source_unique_key)
            effective_action = CREATE_INVOICE_AND_LINK
        _append_example(
            examples,
            f"{effective_action}:{decision.reason}",
            _candidate_example(
                candidate,
                action=effective_action,
                reason=decision.reason,
                identity_key=decision.identity_key,
                invoice=invoice,
            ),
            example_limit=example_limit,
        )

    if apply:
        _persist_affected_invoices(connection, affected_invoices)

    final_invoices = import_service.list_invoices()
    report = {
        "mode": "apply" if apply else "dry_run",
        "summary": {
            "existing_invoice_count": len(existing_invoices),
            "existing_identity_count": len(initial_identity_keys),
            "cache_candidate_count": len(candidates),
            "linked_existing_invoice_count": len(linked_invoice_ids),
            "created_invoice_count": len(created_invoice_ids),
            "created_identity_count": len(created_identity_keys),
            "final_in_memory_invoice_count": len(final_invoices),
            "persisted": bool(apply),
        },
        "action_counts": dict(sorted(action_counts.items())),
        "reason_counts": dict(sorted(reason_counts.items())),
        "examples": examples,
    }
    return report


def _fetch_all_invoices(connection: Any) -> list[Invoice]:
    repository = PostgresCoreRepository(connection)
    page = 1
    page_size = 500
    invoices: list[Invoice] = []
    while True:
        page_rows, total = repository.list_invoices_page(page=page, page_size=page_size)
        invoices.extend(page_rows)
        if len(invoices) >= int(total or 0) or len(page_rows) < page_size:
            break
        page += 1
    return invoices


def _load_candidates(connection: Any) -> list[OAAttachmentInvoiceCandidate]:
    rows = connection.fetch_all(
        """
        select cache.source_attachment_key as cache_source_attachment_key,
               cache.invoices,
               context.oa_application_id,
               context.oa_source_id,
               context.oa_row_id,
               context.source_expense_item_id,
               context.source_expense_row_index,
               context.source_attachment_key,
               context.source_attachment_name
        from app.oa_attachment_invoice_cache cache
        left join lateral (
            select attachment.oa_application_id::text as oa_application_id,
                   coalesce(app.oa_source_id, attachment.oa_source_id) as oa_source_id,
                   attachment.row_id as oa_row_id,
                   source.source_expense_item_id,
                   source.source_expense_row_index,
                   source.source_attachment_key,
                   source.source_attachment_name
            from app.oa_attachment_invoice_cache_sources source
            left join app.oa_attachments attachment
              on attachment.source_attachment_key = source.source_attachment_key
            left join app.oa_applications app
              on app.id = attachment.oa_application_id
            where source.cache_source_attachment_key = cache.source_attachment_key
              and source.source_kind <> 'cache_key'
            order by
              case when attachment.oa_application_id is not null then 0 else 1 end,
              source.source_kind,
              source.source_attachment_key
            limit 1
        ) context on true
        order by cache.parsed_at, cache.source_attachment_key
        """
    )
    candidates: list[OAAttachmentInvoiceCandidate] = []
    for row in rows:
        invoices = row.get("invoices")
        if not isinstance(invoices, list):
            continue
        cache_key = _clean_text(row.get("cache_source_attachment_key"))
        context = {key: row.get(key) for key in row.keys() if key not in {"invoices"}}
        oa_row_id = _resolve_oa_row_id(row)
        oa_form_id = _clean_text(row.get("oa_application_id")) or oa_row_id
        for index, invoice_payload in enumerate(invoices):
            if not isinstance(invoice_payload, dict):
                continue
            attachment_invoice = dict(invoice_payload)
            attachment_invoice.setdefault("source_attachment_key", cache_key)
            for key in (
                "source_expense_item_id",
                "source_expense_row_index",
                "source_attachment_name",
            ):
                value = _clean_text(row.get(key))
                if value and not _clean_text(attachment_invoice.get(key)):
                    attachment_invoice[key] = value
            source_workbench_row_id = None
            if oa_row_id:
                source_workbench_row_id = ImportNormalizationService().oa_attachment_invoice_row_id(
                    oa_row_id,
                    index,
                    attachment_invoice,
                )
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


def _resolve_oa_row_id(row: dict[str, Any]) -> str | None:
    for key in ("oa_row_id", "oa_source_id"):
        value = _clean_text(row.get(key))
        if value:
            return value
    source_expense_item_id = _clean_text(row.get("source_expense_item_id"))
    if not source_expense_item_id:
        return None
    match = _OA_SOURCE_RE.match(source_expense_item_id)
    return match.group(1) if match else None


def _persist_affected_invoices(connection: Any, invoices: list[Invoice]) -> None:
    repository = PostgresCoreRepository(connection)
    seen_ids: set[str] = set()
    unique_invoices: list[Invoice] = []
    for invoice in invoices:
        if invoice.id in seen_ids:
            continue
        seen_ids.add(invoice.id)
        unique_invoices.append(invoice)
    repository.save_invoices(unique_invoices)


def _candidate_example(
    candidate: OAAttachmentInvoiceCandidate,
    *,
    action: str,
    reason: str,
    identity_key: str | None = None,
    invoice: Invoice | None = None,
) -> dict[str, Any]:
    payload = candidate.attachment_invoice
    return {
        "action": action,
        "reason": reason,
        "identity_key": identity_key,
        "invoice_id": invoice.id if invoice is not None else None,
        "cache_source_attachment_key": candidate.cache_source_attachment_key,
        "invoice_index": candidate.invoice_index,
        "oa_form_id": candidate.oa_form_id,
        "oa_row_id": candidate.oa_row_id,
        "source_workbench_row_id": candidate.source_workbench_row_id,
        "invoice_no": payload.get("invoice_no"),
        "digital_invoice_no": payload.get("digital_invoice_no"),
        "invoice_code": payload.get("invoice_code"),
        "issue_date": payload.get("issue_date") or payload.get("invoice_date"),
        "amount": payload.get("total_with_tax") or payload.get("amount") or payload.get("net_amount"),
        "seller_name": payload.get("seller_name"),
        "buyer_name": payload.get("buyer_name"),
        "evidence_type": payload.get("evidence_type"),
        "document_kind": payload.get("document_kind"),
        "source_attachment_name": payload.get("source_attachment_name"),
    }


def _append_example(
    examples: dict[str, list[dict[str, Any]]],
    key: str,
    example: dict[str, Any],
    *,
    example_limit: int,
) -> None:
    bucket = examples.setdefault(key, [])
    if len(bucket) < example_limit:
        bucket.append(example)


def _clean_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


if __name__ == "__main__":
    raise SystemExit(main())
