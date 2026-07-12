from __future__ import annotations

from datetime import UTC, datetime, timedelta
import hashlib
from typing import Any

from fin_ops_platform.services.external_control_evidence import (
    EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
    external_evidence_controls,
    normalize_external_evidence_item,
)


ARTIFACT_BYTES = b"independent external source artifact\n"


def manifest_payload(
    domain: str,
    items: list[dict[str, Any]],
    *,
    observed_at: datetime | None = None,
    valid_until: datetime | None = None,
    artifact_bytes: bytes = ARTIFACT_BYTES,
) -> dict[str, Any]:
    observed = observed_at or datetime(2026, 7, 11, 0, 0, tzinfo=UTC)
    expires = valid_until or (observed + timedelta(days=1))
    normalized_items = tuple(normalize_external_evidence_item(domain=domain, payload=item) for item in items)
    return {
        "contract_version": EXTERNAL_CONTROL_EVIDENCE_CONTRACT_VERSION,
        "tenant_id": "default",
        "domain": domain,
        "coverage_mode": "complete_snapshot",
        "scope_key": "all",
        "source_system": f"trusted-{domain}-source",
        "source_snapshot_id": f"{domain}-snapshot-20260711",
        "observed_at": observed.isoformat(),
        "valid_until": expires.isoformat(),
        "artifact": {
            "sha256": hashlib.sha256(artifact_bytes).hexdigest(),
            "size_bytes": len(artifact_bytes),
        },
        "collector": {"name": f"{domain}-manifest-collector", "version": "1.0.0"},
        "controls": external_evidence_controls(tuple(sorted(normalized_items, key=lambda item: (item.item_kind, item.item_key)))),
        "items": items,
    }


def bank_item(*, serial: str = "SERIAL-001", amount: str = "100.00") -> dict[str, Any]:
    return {
        "kind": "bank_transaction",
        "fields": {
            "account_no": "622200001234",
            "txn_direction": "outflow",
            "trade_time": "2026-07-10T01:02:03+00:00",
            "bank_serial_no": serial,
            "amount": amount,
            "counterparty_name": "外部银行对账供应商",
            "balance": "900.00",
            "currency": "CNY",
            "summary": "采购付款",
            "remark": "独立清单",
            "status": "active",
        },
    }


def oa_application_item() -> dict[str, Any]:
    return {
        "kind": "oa_application",
        "fields": {
            "form_id": "2",
            "oa_source_id": "oa-source-001",
            "workflow_no": "OA-001",
            "status": "completed",
            "applicant": "申请人",
            "application_date": "2026-07-10",
            "amount": "100.00",
            "project_id": "project-001",
            "project_name": "外部证据项目",
            "source_updated_at": "2026-07-10T02:00:00+00:00",
        },
    }


def oa_detail_item() -> dict[str, Any]:
    return {
        "kind": "oa_item",
        "fields": {
            "form_id": "2",
            "oa_source_id": "oa-source-001",
            "row_id": "oa-row-001",
            "item_type": "expense",
            "item_no": "1",
            "amount": "100.00",
            "tax_amount": "0",
            "project_id": "project-001",
            "project_name": "外部证据项目",
        },
    }


def oa_attachment_item() -> dict[str, Any]:
    return {
        "kind": "oa_attachment",
        "fields": {
            "form_id": "2",
            "oa_source_id": "oa-source-001",
            "source_attachment_key": "attachment-key-001",
            "filename": "invoice.pdf",
            "size_bytes": 1024,
            "source_modified_at": "2026-07-10T02:10:00+00:00",
            "file_sha256": "c" * 64,
        },
    }


def invoice_item() -> dict[str, Any]:
    return {
        "kind": "invoice",
        "fields": {
            "invoice_type": "input",
            "invoice_no": "INV-001",
            "invoice_code": "CODE-001",
            "digital_invoice_no": "DIGITAL-001",
            "invoice_date": "2026-07-10",
            "seller_name": "销售方",
            "seller_tax_no": "SELLER-TAX",
            "buyer_name": "购买方",
            "buyer_tax_no": "BUYER-TAX",
            "amount": "100.00",
            "tax_amount": "6.00",
            "total_with_tax": "106.00",
            "currency": "CNY",
            "status": "active",
        },
    }


def etc_invoice_item() -> dict[str, Any]:
    return {
        "kind": "etc_invoice",
        "fields": {
            "etc_invoice_id": "etc-source-001",
            "invoice_no": "ETC-INV-001",
            "invoice_code": "ETC-CODE-001",
            "invoice_date": "2026-07-10",
            "seller_name": "ETC 销售方",
            "buyer_name": "ETC 购买方",
            "amount": "50.00",
            "tax_amount": "1.50",
            "total_with_tax": "51.50",
            "status": "unsubmitted",
            "file_sha256": "a" * 64,
        },
    }
