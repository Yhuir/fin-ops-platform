from __future__ import annotations

from fin_ops_platform.services.oa_attachment_invoice_service import OAAttachmentInvoiceService


ATTACHMENT_EVIDENCE_CACHE_SCHEMA_VERSION = "2026-05-11-evidence-v1"
ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION = ATTACHMENT_EVIDENCE_CACHE_SCHEMA_VERSION


def attachment_invoice_cache_parser_version() -> str:
    return f"{OAAttachmentInvoiceService.PARSER_VERSION}:{ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION}"

