"""Shared read-only attachment statistics; files and invoice identities are distinct."""
from __future__ import annotations

from typing import Any

from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy

FAILED_ATTACHMENT_STATUSES = frozenset({"download_failed", "parse_failed"})
PENDING_ATTACHMENT_STATUSES = frozenset({"not_parsed", "stale"})
UNSUPPORTED_ATTACHMENT_STATUSES = frozenset({"unsupported", "unsupported_file"})


def attachment_summary(*, file_count: int, artifacts: list[dict], invoices: list[dict]) -> dict[str, Any]:
    policy = FinancialObjectIdentityPolicy()
    seen: set[tuple[str, str]] = set()
    recognized = 0
    invoice_sources = set()
    for invoice in invoices:
        invoice_sources.add(invoice.get("source_attachment_key"))
        keys = policy.oa_attachment_invoice_dedupe_keys(invoice)
        if not any(key in seen for key in keys):
            recognized += 1
            seen.update(keys)
    files = {artifact["source_attachment_key"]: artifact for artifact in artifacts}
    pending = max(0, file_count - len(files))
    failed = unsupported = non_invoice = 0
    for key, artifact in files.items():
        status = artifact.get("parse_status", "not_parsed")
        if status in PENDING_ATTACHMENT_STATUSES:
            pending += 1
        elif status in FAILED_ATTACHMENT_STATUSES:
            failed += 1
        elif status in UNSUPPORTED_ATTACHMENT_STATUSES:
            unsupported += 1
        elif key not in invoice_sources and artifact.get("has_invoice_evidence") != "true":
            non_invoice += 1
    status = "ready"
    if failed:
        status = "failed" if failed == file_count else "partial"
    elif pending:
        status = "unparsed" if pending == file_count else "partial"
    return {
        "attachment_file_count": file_count,
        "importable_invoice_count": recognized,
        "unrecognized_attachment_count": non_invoice,
        "attachment_status": status,
        "pending_attachment_count": pending,
        "failed_attachment_count": failed,
        "unsupported_attachment_count": unsupported,
    }


def record_attachment_summary(record: Any) -> dict[str, Any]:
    return attachment_summary(file_count=record.attachment_file_count,
        artifacts=record.attachment_artifacts, invoices=record.attachment_invoices)
