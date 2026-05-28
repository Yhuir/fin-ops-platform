from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import csv
import json
from typing import Any

from fin_ops_platform.services.imports import clean_string


AUDIT_START_DATE = date(2026, 1, 1)
FORMAL_INVOICE_EVIDENCE_TYPES = {"tax_invoice", "machine_invoice", "non_tax_receipt"}
PAYMENT_RECEIPT_EVIDENCE_TYPE = "payment_receipt"
PARSER_FAILURE_STATUSES = {"download_failed", "parse_failed"}


def audit_oa_attachment_records(
    records: list[Any],
    *,
    start_date: date = AUDIT_START_DATE,
) -> dict[str, Any]:
    rows = [audit_oa_attachment_record(record, start_date=start_date) for record in list(records or [])]
    in_scope_rows = [row for row in rows if row["in_scope"]]
    summary = {
        "scope_start_date": start_date.isoformat(),
        "records_total": len(rows),
        "records_in_scope": len(in_scope_rows),
        "records_out_of_scope_before_2026": sum(1 for row in rows if row["status"] == "out_of_scope_before_2026"),
        "records_ok": sum(1 for row in in_scope_rows if row["status"] == "ok"),
        "records_with_formal_invoices": sum(1 for row in in_scope_rows if row["formal_invoice_count"] > 0),
        "records_with_payment_receipts_only": sum(
            1 for row in in_scope_rows if row["status"] == "evidence_only_no_formal_invoice"
        ),
        "records_source_attachment_missing": sum(
            1 for row in in_scope_rows if row["status"] == "source_attachment_missing"
        ),
        "records_parser_failed": sum(1 for row in in_scope_rows if row["status"] == "parser_failed"),
    }
    return {"summary": summary, "rows": rows, "issues": [row for row in in_scope_rows if row["status"] != "ok"]}


def audit_oa_attachment_record(record: Any, *, start_date: date = AUDIT_START_DATE) -> dict[str, Any]:
    application_date = _record_application_date(record)
    in_scope = application_date is None or application_date >= start_date
    evidences = _record_evidences(record)
    artifacts = _record_artifacts(record)
    formal_invoices = [
        evidence
        for evidence in evidences
        if clean_string(evidence.get("evidence_type") or "") in FORMAL_INVOICE_EVIDENCE_TYPES
    ]
    payment_receipts = [
        evidence
        for evidence in evidences
        if clean_string(evidence.get("evidence_type") or "") == PAYMENT_RECEIPT_EVIDENCE_TYPE
    ]
    attachment_file_count = _record_attachment_file_count(record)
    expected_evidence_count = _expected_evidence_count(record)
    source_missing_attachment_count = expected_evidence_count if expected_evidence_count > 0 and attachment_file_count == 0 else 0
    parser_failed_artifacts = [
        artifact
        for artifact in artifacts
        if clean_string(artifact.get("parse_status") or "") in PARSER_FAILURE_STATUSES
    ]
    status = _audit_status(
        in_scope=in_scope,
        source_missing_attachment_count=source_missing_attachment_count,
        parser_failed_artifacts=parser_failed_artifacts,
        formal_invoice_count=len(formal_invoices),
        payment_receipt_count=len(payment_receipts),
    )
    return {
        "status": status,
        "in_scope": in_scope,
        "oa_id": clean_string(getattr(record, "id", "")),
        "month": clean_string(getattr(record, "month", "")),
        "application_date": application_date.isoformat() if application_date is not None else "",
        "applicant": clean_string(getattr(record, "applicant", "")),
        "amount": clean_string(getattr(record, "amount", "")),
        "project_name": clean_string(getattr(record, "project_name", "")),
        "reason": clean_string(getattr(record, "reason", "")),
        "original_attachment_file_count": attachment_file_count,
        "expected_evidence_count": expected_evidence_count,
        "formal_invoice_count": len(formal_invoices),
        "payment_receipt_count": len(payment_receipts),
        "non_invoice_evidence_count": max(0, len(evidences) - len(formal_invoices) - len(payment_receipts)),
        "source_missing_attachment_count": source_missing_attachment_count,
        "parser_failed_count": len(parser_failed_artifacts),
        "issue_items": _issue_items(record, parser_failed_artifacts=parser_failed_artifacts),
    }


def write_oa_attachment_audit_report(report: dict[str, Any], output_dir: Path, *, stem: str) -> dict[str, str]:
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / f"{stem}.json"
    csv_path = output_dir / f"{stem}.csv"
    json_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    rows = list(report.get("issues") or report.get("rows") or [])
    fieldnames = [
        "status",
        "oa_id",
        "month",
        "application_date",
        "applicant",
        "amount",
        "original_attachment_file_count",
        "expected_evidence_count",
        "formal_invoice_count",
        "payment_receipt_count",
        "non_invoice_evidence_count",
        "source_missing_attachment_count",
        "parser_failed_count",
        "reason",
        "issue_items",
    ]
    with csv_path.open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            csv_row = {field: row.get(field, "") for field in fieldnames}
            csv_row["issue_items"] = json.dumps(csv_row.get("issue_items") or [], ensure_ascii=False)
            writer.writerow(csv_row)
    return {"json": str(json_path), "csv": str(csv_path)}


def _audit_status(
    *,
    in_scope: bool,
    source_missing_attachment_count: int,
    parser_failed_artifacts: list[dict[str, Any]],
    formal_invoice_count: int,
    payment_receipt_count: int,
) -> str:
    if not in_scope:
        return "out_of_scope_before_2026"
    if source_missing_attachment_count > 0:
        return "source_attachment_missing"
    if parser_failed_artifacts:
        return "parser_failed"
    if formal_invoice_count <= 0 and payment_receipt_count > 0:
        return "evidence_only_no_formal_invoice"
    return "ok"


def _record_application_date(record: Any) -> date | None:
    detail_fields = getattr(record, "detail_fields", {})
    if isinstance(detail_fields, dict):
        for key in ("申请日期", "application_date", "ApplicationDate"):
            parsed = _parse_date(detail_fields.get(key))
            if parsed is not None:
                return parsed
    parsed_month = _parse_date(f"{clean_string(getattr(record, 'month', ''))}-01")
    return parsed_month


def _parse_date(value: Any) -> date | None:
    text = clean_string(value)
    if len(text) < 10:
        return None
    try:
        return datetime.strptime(text[:10], "%Y-%m-%d").date()
    except ValueError:
        return None


def _record_evidences(record: Any) -> list[dict[str, Any]]:
    return [dict(evidence) for evidence in list(getattr(record, "attachment_evidences", []) or []) if isinstance(evidence, dict)]


def _record_artifacts(record: Any) -> list[dict[str, Any]]:
    return [dict(artifact) for artifact in list(getattr(record, "attachment_artifacts", []) or []) if isinstance(artifact, dict)]


def _record_attachment_file_count(record: Any) -> int:
    try:
        return int(getattr(record, "attachment_file_count", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _expected_evidence_count(record: Any) -> int:
    detail_fields = getattr(record, "detail_fields", {})
    if isinstance(detail_fields, dict):
        for key in ("附件凭证期望数", "detailNumberOfBills", "票据数量", "单据数量"):
            count = _parse_int(detail_fields.get(key))
            if count > 0:
                return count
    total = 0
    for item in list(getattr(record, "expense_items", []) or []):
        if not isinstance(item, dict):
            continue
        total += _parse_int(item.get("detailNumberOfBills") or item.get("expected_evidence_count"))
    return total


def _parse_int(value: Any) -> int:
    text = clean_string(value)
    if not text:
        return 0
    try:
        return int(float(text))
    except ValueError:
        return 0


def _issue_items(record: Any, *, parser_failed_artifacts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for artifact in parser_failed_artifacts:
        items.append(
            {
                "attachment_name": clean_string(
                    artifact.get("attachment_name") or artifact.get("source_attachment_name") or ""
                ),
                "parse_status": clean_string(artifact.get("parse_status") or ""),
                "parse_error": clean_string(artifact.get("parse_error") or ""),
                "source_expense_row_index": clean_string(artifact.get("source_expense_row_index") or ""),
            }
        )
    if items:
        return items
    for item in list(getattr(record, "expense_items", []) or []):
        if not isinstance(item, dict):
            continue
        if _parse_int(item.get("detailNumberOfBills") or item.get("expected_evidence_count")) <= 0:
            continue
        items.append(
            {
                "row_index": clean_string(item.get("row_index") or ""),
                "expense_content": clean_string(item.get("expense_content") or ""),
                "expected_evidence_count": _parse_int(
                    item.get("detailNumberOfBills") or item.get("expected_evidence_count")
                ),
                "attachment_file_count": _parse_int(item.get("attachment_file_count")),
            }
        )
    return items
