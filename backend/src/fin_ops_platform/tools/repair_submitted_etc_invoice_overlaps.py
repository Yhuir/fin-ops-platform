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


SUBMITTED_ETC_OVERLAP_SQL = """
select
    invoices.id::text as invoice_id,
    coalesce(invoices.legacy_mongo_id, invoices.id::text) as invoice_legacy_id,
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
    invoices.workbench_visibility,
    invoices.etc_invoice_id as invoice_etc_invoice_id,
    etc_invoices.id::text as etc_row_id,
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
    etc_invoices.batch_id as etc_batch_id,
    etc_invoices.business_batch_id,
    etc_invoices.status as etc_status,
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
where invoices.invoice_type = 'input'
  and invoices.status <> 'deleted'
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
    parser = argparse.ArgumentParser(
        description="Audit or repair canonical invoices that overlap submitted ETC business batch invoices."
    )
    parser.add_argument("--json", action="store_true", help="Print JSON. This is the default output format.")
    parser.add_argument("--limit", type=int, default=50, help="Maximum examples per candidate category.")
    parser.add_argument("--apply", action="store_true", help="Persist strict auto-fix candidates.")
    parser.add_argument("--reason", default="", help="Required with --apply. Stored in repair source links.")
    parser.add_argument("--operator", default="", help="Required with --apply. Stored in repair source links.")
    return parser


def main(argv: Sequence[str] | None = None, *, stdout: TextIO = sys.stdout) -> int:
    parser = build_parser()
    args = parser.parse_args(list(argv or sys.argv[1:]))
    if args.apply and not str(args.reason or "").strip():
        parser.error("--reason is required with --apply")
    if args.apply and not str(args.operator or "").strip():
        parser.error("--operator is required with --apply")

    connection = PostgresConnection(PostgresSettings.from_env())
    report = audit_submitted_etc_invoice_overlaps(connection=connection, example_limit=max(int(args.limit), 0))
    if args.apply:
        try:
            _ensure_apply_candidate_examples_complete(
                report,
                candidates_key="auto_fix_candidates",
                count_key="auto_fix_candidate_count",
            )
        except ValueError as exc:
            parser.error(str(exc))
        queue_repository = RuntimeQueueRepository(connection)
        report["apply"] = apply_submitted_etc_invoice_overlap_repair(
            connection=connection,
            auto_fix_candidates=list(report["auto_fix_candidates"]),
            reason=str(args.reason).strip(),
            operator=str(args.operator).strip(),
            queue_repository=queue_repository,
        )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True), file=stdout)
    return 0 if report["summary"]["manual_review_candidate_count"] == 0 else 1


def audit_submitted_etc_invoice_overlaps(*, connection: Any, example_limit: int = 50) -> dict[str, Any]:
    rows = list(connection.fetch_all(SUBMITTED_ETC_OVERLAP_SQL))
    auto_fix_candidates: list[dict[str, Any]] = []
    manual_review_candidates: list[dict[str, Any]] = []
    no_action_candidates: list[dict[str, Any]] = []
    for row in rows:
        candidate = _candidate_payload(row)
        strict = not candidate["failed_checks"]
        visible = candidate["workbench_visibility"] == "visible"
        linked = bool(candidate["invoice_etc_invoice_id"])
        if visible and strict and not linked:
            candidate["classification"] = "auto_fix"
            auto_fix_candidates.append(candidate)
        elif visible:
            candidate["classification"] = "manual_review"
            manual_review_candidates.append(candidate)
        else:
            candidate["classification"] = "no_action"
            no_action_candidates.append(candidate)
    affected_months = sorted(
        {
            str(candidate.get("invoice_month") or "")[:7]
            for candidate in auto_fix_candidates
            if str(candidate.get("invoice_month") or "").strip()
        }
    )
    summary = {
        "status": "attention" if manual_review_candidates else "ready",
        "overlap_pair_count": len(rows),
        "auto_fix_candidate_count": len(auto_fix_candidates),
        "manual_review_candidate_count": len(manual_review_candidates),
        "no_action_candidate_count": len(no_action_candidates),
        "affected_workbench_scopes": affected_months + (["all"] if affected_months else []),
        "apply_required_confirmation": bool(auto_fix_candidates),
    }
    return {
        "mode": "dry-run",
        "summary": summary,
        "auto_fix_candidates": auto_fix_candidates[:example_limit],
        "manual_review_candidates": manual_review_candidates[:example_limit],
        "no_action_candidates": no_action_candidates[:example_limit],
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


def apply_submitted_etc_invoice_overlap_repair(
    *,
    connection: Any,
    auto_fix_candidates: list[dict[str, Any]],
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

    affected_months = sorted(
        {
            str(candidate.get("invoice_month") or "")[:7]
            for candidate in auto_fix_candidates
            if str(candidate.get("invoice_month") or "").strip()
        }
    )
    updated_count = 0

    transaction_factory = getattr(connection, "transaction", None)
    if callable(transaction_factory):
        with transaction_factory() as transaction:
            updated_count = _apply_candidates(
                transaction,
                auto_fix_candidates,
                reason=normalized_reason,
                operator=normalized_operator,
            )
    else:
        updated_count = _apply_candidates(
            connection,
            auto_fix_candidates,
            reason=normalized_reason,
            operator=normalized_operator,
        )

    enqueued_scopes: list[str] = []
    if queue_repository is not None and affected_months:
        gateway = ReadModelRefreshGateway(queue_repository=queue_repository)
        enqueued_scopes = gateway.enqueue_many(
            "workbench",
            affected_months + ["all"],
            reason="submitted_etc_invoice_overlap_repair",
            priority="high",
            metadata={"reason": normalized_reason, "operator": normalized_operator},
        )

    return {
        "applied": True,
        "requested_count": len(auto_fix_candidates),
        "updated_count": updated_count,
        "affected_workbench_scopes": affected_months + (["all"] if affected_months else []),
        "enqueued_workbench_scopes": enqueued_scopes,
    }


def _apply_candidates(target: Any, candidates: list[dict[str, Any]], *, reason: str, operator: str) -> int:
    repository = PostgresCoreRepository(target)
    updated_count = 0
    for candidate in candidates:
        updated_count += int(
            repository.repair_submitted_etc_invoice_overlap(
                invoice_id=str(candidate["invoice_id"]),
                etc_invoice_id=str(candidate["etc_invoice_id"]),
                etc_batch_id=(
                    str(candidate.get("etc_batch_id"))
                    if candidate.get("etc_batch_id") is not None
                    else None
                ),
                reason=reason,
                operator=operator,
            )
        )
    return updated_count


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
        left = row.get(invoice_field)
        right = row.get(etc_field)
        if not _values_match(left, right):
            failed_checks.append(field_name)
    return {
        "invoice_id": str(row.get("invoice_id") or ""),
        "invoice_legacy_id": str(row.get("invoice_legacy_id") or ""),
        "invoice_month": str(row.get("invoice_month") or "")[:10],
        "invoice_no": str(row.get("digital_invoice_no") or row.get("invoice_no") or ""),
        "invoice_code": row.get("invoice_code"),
        "invoice_date": str(row.get("invoice_date") or "")[:10],
        "workbench_visibility": str(row.get("workbench_visibility") or "visible"),
        "invoice_etc_invoice_id": str(row.get("invoice_etc_invoice_id") or ""),
        "amount": _decimal_text(row.get("amount")),
        "tax_amount": _decimal_text(row.get("tax_amount")),
        "total_with_tax": _decimal_text(row.get("total_with_tax")),
        "seller_name": row.get("seller_name"),
        "seller_tax_no": row.get("seller_tax_no"),
        "buyer_name": row.get("buyer_name"),
        "buyer_tax_no": row.get("buyer_tax_no"),
        "etc_invoice_id": str(row.get("etc_invoice_id") or ""),
        "etc_row_id": str(row.get("etc_row_id") or ""),
        "etc_invoice_no": str(row.get("etc_invoice_no") or ""),
        "etc_invoice_date": str(row.get("etc_invoice_date") or "")[:10],
        "etc_amount": _decimal_text(row.get("etc_amount")),
        "etc_tax_amount": _decimal_text(row.get("etc_tax_amount")),
        "etc_total_with_tax": _decimal_text(row.get("etc_total_with_tax")),
        "etc_batch_id": row.get("etc_batch_id"),
        "business_batch_id": row.get("business_batch_id"),
        "business_batch_status": row.get("business_batch_status"),
        "failed_checks": failed_checks,
    }


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
