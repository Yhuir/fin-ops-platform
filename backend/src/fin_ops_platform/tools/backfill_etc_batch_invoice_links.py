from __future__ import annotations

import argparse
import json
import sys
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Sequence, TextIO

from fin_ops_platform.services.postgres_connection import PostgresConnection, PostgresSettings
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.read_model_refresh_gateway import ReadModelRefreshGateway
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository


ETC_BATCH_INVOICE_LINK_BACKFILL_SQL = """
select
    links.id::text as link_id,
    invoices.id::text as invoice_id,
    invoices.invoice_month::text as invoice_month,
    invoices.invoice_no,
    invoices.invoice_code,
    invoices.digital_invoice_no,
    invoices.invoice_date::text as invoice_date,
    invoices.seller_name,
    invoices.seller_tax_no,
    invoices.buyer_name,
    invoices.buyer_tax_no,
    invoices.amount,
    invoices.tax_amount,
    invoices.total_with_tax,
    etc_invoices.etc_invoice_id,
    etc_invoices.invoice_no as etc_invoice_no,
    etc_invoices.invoice_code as etc_invoice_code,
    etc_invoices.invoice_date::text as etc_invoice_date,
    etc_invoices.seller_name as etc_seller_name,
    nullif(etc_invoices.raw_payload->'normalized_payload'->>'seller_tax_no', '') as etc_seller_tax_no,
    etc_invoices.buyer_name as etc_buyer_name,
    nullif(etc_invoices.raw_payload->'normalized_payload'->>'buyer_tax_no', '') as etc_buyer_tax_no,
    etc_invoices.amount as etc_amount,
    etc_invoices.tax_amount as etc_tax_amount,
    etc_invoices.total_with_tax as etc_total_with_tax,
    etc_invoices.business_batch_id,
    etc_business_batches.status as business_batch_status
from app.invoices invoices
join app.etc_invoices etc_invoices
  on (
        (
            nullif(coalesce(invoices.digital_invoice_no, invoices.invoice_no), '') is not null
        and etc_invoices.invoice_no = coalesce(invoices.digital_invoice_no, invoices.invoice_no)
        )
     or (
            nullif(invoices.invoice_code, '') is not null
        and nullif(invoices.invoice_no, '') is not null
        and etc_invoices.invoice_code = invoices.invoice_code
        and etc_invoices.invoice_no = invoices.invoice_no
        )
  )
left join app.etc_business_batches etc_business_batches
  on etc_business_batches.business_batch_id = etc_invoices.business_batch_id
left join app.etc_batch_invoice_links links
  on links.invoice_id = invoices.id
 and links.business_batch_id = etc_invoices.business_batch_id
 and links.link_status = 'active'
where invoices.invoice_type = 'input'
  and invoices.status <> 'deleted'
  and nullif(etc_invoices.business_batch_id, '') is not null
  and (
        etc_business_batches.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
     or (
            etc_invoices.status = 'submitted'
        and coalesce(etc_business_batches.status, '') <> 'deleted'
        )
  )
order by invoices.invoice_month nulls last, invoices.invoice_date nulls last, invoices.invoice_no, etc_invoices.etc_invoice_id
"""


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Dry-run or apply ETC batch invoice link backfill.")
    parser.add_argument("--json", action="store_true", help="Print JSON. This is the default output format.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per candidate category; 0 prints counts only.")
    parser.add_argument("--apply", action="store_true", help="Persist strict auto-backfill candidates.")
    parser.add_argument("--reason", default="", help="Required with --apply. Stored in backfill raw payload.")
    parser.add_argument("--operator", default="", help="Required with --apply. Stored in backfill raw payload.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or sys.argv[1:]))
    if args.apply and not str(args.reason or "").strip():
        parser.error("--reason is required with --apply")
    if args.apply and not str(args.operator or "").strip():
        parser.error("--operator is required with --apply")

    connection = PostgresConnection(PostgresSettings.from_env())
    if not _etc_batch_invoice_links_table_exists(connection):
        report = {
            "mode": "dry-run",
            "summary": {
                "status": "blocked_missing_migration",
                "message": "app.etc_batch_invoice_links is missing; apply migration 0074 before backfill.",
                "candidate_count": 0,
                "auto_backfill_count": 0,
                "manual_review_count": 0,
                "already_linked_count": 0,
                "affected_workbench_scopes": [],
                "rollback_plan_available": False,
                "apply_required_confirmation": False,
            },
            "auto_backfill_candidates": [],
            "manual_review_candidates": [],
            "already_linked": [],
            "rollback_plan": _rollback_plan([]),
        }
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
        return 2
    report = audit_etc_batch_invoice_link_backfill(connection=connection, example_limit=max(int(args.limit), 0))
    if args.apply:
        try:
            _ensure_apply_candidate_examples_complete(
                report,
                candidates_key="auto_backfill_candidates",
                count_key="auto_backfill_count",
            )
        except ValueError as exc:
            parser.error(str(exc))
        queue_repository = RuntimeQueueRepository(connection)
        report["apply"] = apply_etc_batch_invoice_link_backfill(
            connection=connection,
            auto_backfill_candidates=list(report["auto_backfill_candidates"]),
            reason=str(args.reason).strip(),
            operator=str(args.operator).strip(),
            queue_repository=queue_repository,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report["summary"]["manual_review_count"] == 0 else 1


def audit_etc_batch_invoice_link_backfill(*, connection: Any, example_limit: int = 50) -> dict[str, Any]:
    rows = list(connection.fetch_all(ETC_BATCH_INVOICE_LINK_BACKFILL_SQL))
    auto_backfill_candidates: list[dict[str, Any]] = []
    manual_review_candidates: list[dict[str, Any]] = []
    already_linked: list[dict[str, Any]] = []
    for row in rows:
        candidate = _candidate_payload(row)
        if candidate["link_id"]:
            candidate["classification"] = "already_linked"
            already_linked.append(candidate)
        elif candidate["failed_checks"]:
            candidate["classification"] = "manual_review"
            manual_review_candidates.append(candidate)
        else:
            candidate["classification"] = "auto_backfill"
            auto_backfill_candidates.append(candidate)

    affected_months = _affected_months(auto_backfill_candidates)
    summary = {
        "status": "attention" if manual_review_candidates else "ready",
        "candidate_count": len(rows),
        "auto_backfill_count": len(auto_backfill_candidates),
        "manual_review_count": len(manual_review_candidates),
        "already_linked_count": len(already_linked),
        "affected_workbench_scopes": affected_months + (["all"] if affected_months else []),
        "rollback_plan_available": bool(auto_backfill_candidates),
        "apply_required_confirmation": bool(auto_backfill_candidates),
    }
    return {
        "mode": "dry-run",
        "summary": summary,
        "auto_backfill_candidates": auto_backfill_candidates[:example_limit],
        "manual_review_candidates": manual_review_candidates[:example_limit],
        "already_linked": already_linked[:example_limit],
        "rollback_plan": _rollback_plan(auto_backfill_candidates),
    }


def _etc_batch_invoice_links_table_exists(connection: Any) -> bool:
    row = connection.fetch_one(
        "select to_regclass('app.etc_batch_invoice_links')::text as table_name",
    )
    return bool(row and str(row.get("table_name") or "").strip())


def apply_etc_batch_invoice_link_backfill(
    *,
    connection: Any,
    auto_backfill_candidates: list[dict[str, Any]],
    reason: str,
    operator: str,
    queue_repository: Any | None = None,
) -> dict[str, Any]:
    normalized_reason = str(reason or "").strip()
    normalized_operator = str(operator or "").strip()
    if not normalized_reason:
        raise ValueError("reason is required for apply")
    if not normalized_operator:
        raise ValueError("operator is required for apply")

    repository = PostgresCoreRepository(connection)
    linked: list[dict[str, Any]] = []
    for candidate in auto_backfill_candidates:
        link = repository.upsert_etc_batch_invoice_link(
            invoice_id=str(candidate.get("invoice_id") or ""),
            business_batch_id=str(candidate.get("business_batch_id") or ""),
            etc_invoice_id=str(candidate.get("etc_invoice_id") or ""),
            invoice_no=str(candidate.get("invoice_no") or ""),
            invoice_code=candidate.get("invoice_code"),
            digital_invoice_no=str(candidate.get("digital_invoice_no") or candidate.get("invoice_no") or ""),
            invoice_date=str(candidate.get("invoice_date") or ""),
            link_source="historical_backfill",
            confidence="strict",
            raw_payload={"reason": normalized_reason, "operator": normalized_operator, "candidate": candidate},
        )
        if link:
            linked.append(link)

    affected_months = _affected_months(auto_backfill_candidates)
    enqueued_scopes: list[str] = []
    if queue_repository is not None and affected_months:
        gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        enqueued_scopes = gateway.enqueue_many(
            "workbench",
            affected_months + ["all"],
            reason="etc_batch_invoice_link_backfill",
            priority="high",
            metadata={"reason": normalized_reason, "operator": normalized_operator},
        )
    return {
        "applied": True,
        "requested_count": len(auto_backfill_candidates),
        "linked_count": len(linked),
        "affected_workbench_scopes": affected_months + (["all"] if affected_months else []),
        "enqueued_workbench_scopes": enqueued_scopes,
        "rollback_plan": _rollback_plan(auto_backfill_candidates, link_ids=[str(item.get("id") or "") for item in linked]),
    }


def _ensure_apply_candidate_examples_complete(
    report: dict[str, Any],
    *,
    candidates_key: str,
    count_key: str,
) -> None:
    summary = report.get("summary") if isinstance(report.get("summary"), dict) else {}
    expected_count = int(summary.get(count_key) or 0)
    actual_count = len(report.get(candidates_key) or [])
    if actual_count < expected_count:
        raise ValueError(
            f"--apply requires --limit >= {expected_count} so the exact {candidates_key} row set is included"
        )


def _candidate_payload(row: dict[str, Any]) -> dict[str, Any]:
    failed_checks = []
    for field_name, invoice_field, etc_field in (
        ("invoice_date", "invoice_date", "etc_invoice_date"),
        ("amount", "amount", "etc_amount"),
        ("tax_amount", "tax_amount", "etc_tax_amount"),
        ("total_with_tax", "total_with_tax", "etc_total_with_tax"),
        ("seller_name", "seller_name", "etc_seller_name"),
        ("seller_tax_no", "seller_tax_no", "etc_seller_tax_no"),
        ("buyer_name", "buyer_name", "etc_buyer_name"),
        ("buyer_tax_no", "buyer_tax_no", "etc_buyer_tax_no"),
    ):
        if not _values_match(row.get(invoice_field), row.get(etc_field)):
            failed_checks.append(field_name)
    return {
        "link_id": str(row.get("link_id") or ""),
        "invoice_id": str(row.get("invoice_id") or ""),
        "invoice_month": str(row.get("invoice_month") or "")[:10],
        "invoice_no": str(row.get("digital_invoice_no") or row.get("invoice_no") or ""),
        "invoice_code": row.get("invoice_code"),
        "digital_invoice_no": str(row.get("digital_invoice_no") or row.get("invoice_no") or ""),
        "invoice_date": str(row.get("invoice_date") or "")[:10],
        "amount": _decimal_text(row.get("amount")),
        "tax_amount": _decimal_text(row.get("tax_amount")),
        "total_with_tax": _decimal_text(row.get("total_with_tax")),
        "etc_invoice_id": str(row.get("etc_invoice_id") or ""),
        "etc_invoice_no": str(row.get("etc_invoice_no") or ""),
        "etc_invoice_date": str(row.get("etc_invoice_date") or "")[:10],
        "business_batch_id": str(row.get("business_batch_id") or ""),
        "business_batch_status": str(row.get("business_batch_status") or ""),
        "failed_checks": failed_checks,
    }


def _rollback_plan(candidates: list[dict[str, Any]], *, link_ids: list[str] | None = None) -> dict[str, Any]:
    return {
        "sql_template": (
            "update app.etc_batch_invoice_links set link_status='removed', "
            "raw_payload = raw_payload || jsonb_build_object('rollback_reason', :reason), updated_at = now() "
            "where link_source='historical_backfill' and link_status='active' and id::text = any(:link_ids);"
        ),
        "candidate_keys": [
            {
                "invoice_id": candidate.get("invoice_id"),
                "business_batch_id": candidate.get("business_batch_id"),
                "etc_invoice_id": candidate.get("etc_invoice_id"),
            }
            for candidate in candidates
        ],
        "link_ids": [link_id for link_id in list(link_ids or []) if link_id],
    }


def _affected_months(candidates: list[dict[str, Any]]) -> list[str]:
    return sorted(
        {
            str(candidate.get("invoice_month") or "")[:7]
            for candidate in candidates
            if str(candidate.get("invoice_month") or "").strip()
        }
    )


def _values_match(left: Any, right: Any) -> bool:
    if _is_blank(left) or _is_blank(right):
        return True
    left_decimal = _decimal_or_none(left)
    right_decimal = _decimal_or_none(right)
    if left_decimal is not None and right_decimal is not None:
        return left_decimal == right_decimal
    return str(left).strip() == str(right).strip()


def _is_blank(value: Any) -> bool:
    return str(value or "").strip() in {"", "--", "-", "—", "无"}


def _decimal_text(value: Any) -> str | None:
    parsed = _decimal_or_none(value)
    return f"{parsed:.2f}" if parsed is not None else None


def _decimal_or_none(value: Any) -> Decimal | None:
    if _is_blank(value):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except (InvalidOperation, ValueError):
        return None


if __name__ == "__main__":
    raise SystemExit(main())
