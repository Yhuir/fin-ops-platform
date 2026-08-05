from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Protocol

from fin_ops_platform.services.imports import clean_string


ETC_BATCH_SOURCE = "etc_batch"
ETC_BATCH_TAG = "ETC批量提交"
ETC_BATCH_ID_RE = re.compile(r"etc_batch_id\s*=\s*([^\s,;，；]+)", re.IGNORECASE)


@dataclass(slots=True)
class OAApplicationRecord:
    id: str
    month: str
    section: str
    case_id: str | None
    applicant: str
    project_name: str
    apply_type: str
    amount: str
    counterparty_name: str
    reason: str
    relation_code: str
    relation_label: str
    relation_tone: str
    workflow_status: str | None = None
    expense_type: str | None = None
    expense_content: str | None = None
    detail_fields: dict[str, Any] = field(default_factory=dict)
    attachment_evidences: list[dict[str, str]] = field(default_factory=list)
    attachment_artifacts: list[dict[str, str]] = field(default_factory=list)
    attachment_invoices: list[dict[str, str]] = field(default_factory=list)
    attachment_file_count: int = 0
    expense_items: list[dict[str, Any]] = field(default_factory=list)
    amount_source: str | None = None
    amount_mismatch: dict[str, str] | None = None
    source: str | None = None
    etc_batch_id: str | None = None
    tags: list[str] = field(default_factory=list)
    project_name_display: str | None = None
    project_names: list[str] = field(default_factory=list)


@dataclass(slots=True)
class OAReadStatus:
    code: str
    message: str


class OAAdapter(Protocol):
    def list_application_records(self, month: str) -> list[OAApplicationRecord]: ...

    def get_read_status(self) -> OAReadStatus: ...


class InMemoryOAAdapter:
    def __init__(self, seed_data: dict[str, list[OAApplicationRecord]]) -> None:
        self._seed_data = seed_data

    def list_application_records(self, month: str) -> list[OAApplicationRecord]:
        return list(self._seed_data.get(month, []))

    def list_all_application_records(self) -> list[OAApplicationRecord]:
        records: list[OAApplicationRecord] = []
        for month in sorted(self._seed_data.keys()):
            records.extend(self.list_application_records(month))
        return records

    def list_application_records_by_row_ids(self, row_ids: list[str]) -> list[OAApplicationRecord]:
        normalized_ids = [str(row_id).strip() for row_id in list(row_ids or []) if str(row_id).strip()]
        if not normalized_ids:
            return []
        records_by_id = {
            record.id: record
            for record in self.list_all_application_records()
        }
        return [records_by_id[row_id] for row_id in normalized_ids if row_id in records_by_id]

    def list_available_months(self) -> list[str]:
        return sorted(self._seed_data.keys())

    def get_read_status(self) -> OAReadStatus:
        return OAReadStatus(code="ready", message="OA 已同步")


def build_attachment_invoice_detail_fields(
    attachment_invoices: list[dict[str, Any]] | None,
    *,
    attachment_file_count: int | None = None,
    attachment_evidences: list[dict[str, Any]] | None = None,
    attachment_artifacts: list[dict[str, Any]] | None = None,
) -> dict[str, str]:
    invoices = [invoice for invoice in (attachment_invoices or []) if isinstance(invoice, dict)]
    evidences = [evidence for evidence in (attachment_evidences or []) if isinstance(evidence, dict)]
    artifacts = [artifact for artifact in (attachment_artifacts or []) if isinstance(artifact, dict)]
    parsed_count = len(invoices)
    total_count = max(parsed_count, len(artifacts), int(attachment_file_count or 0))
    if parsed_count == 0 and total_count == 0:
        return {}

    summary_items: list[str] = []
    for invoice in invoices:
        invoice_no = clean_string(
            invoice.get("invoice_no")
            or invoice.get("digital_invoice_no")
            or invoice.get("invoice_code")
            or ""
        )
        attachment_name = clean_string(invoice.get("attachment_name") or "")
        if invoice_no and attachment_name:
            summary_items.append(f"{invoice_no}（{attachment_name}）")
        elif invoice_no:
            summary_items.append(invoice_no)
        elif attachment_name:
            summary_items.append(attachment_name)

    detail_fields = {
        "附件发票数量": str(parsed_count),
        "附件发票识别情况": f"已解析 {parsed_count} / {total_count or parsed_count}",
    }
    if summary_items:
        detail_fields["附件发票摘要"] = "；".join(summary_items)
    if evidences:
        payment_receipts = [
            evidence
            for evidence in evidences
            if clean_string(evidence.get("evidence_type") or "") == "payment_receipt"
        ]
        evidence_total_count = max(len(artifacts), int(attachment_file_count or 0)) or len(evidences)
        invoice_total = _sum_attachment_amounts(invoices, prefer_total_with_tax=True)
        payment_total = _sum_attachment_amounts(payment_receipts, prefer_total_with_tax=False)
        detail_fields.update(
            {
                "附件凭证数量": str(len(evidences)),
                "付款凭证数量": str(len(payment_receipts)),
                "附件凭证识别情况": f"已解析 {len(evidences)} / {evidence_total_count or len(evidences)}",
                "附件发票金额合计": _format_attachment_amount(invoice_total),
                "付款凭证金额合计": _format_attachment_amount(payment_total),
                "附件凭证闭环状态": _attachment_evidence_closure_status(invoice_total, payment_total),
            }
        )
    return detail_fields


def _sum_attachment_amounts(rows: list[dict[str, Any]], *, prefer_total_with_tax: bool) -> float:
    total = 0.0
    for row in rows:
        amount_text = clean_string(
            (row.get("total_with_tax") if prefer_total_with_tax else None)
            or row.get("amount")
            or ""
        )
        if not amount_text:
            continue
        try:
            total += float(amount_text.replace(",", ""))
        except ValueError:
            continue
    return total


def _format_attachment_amount(amount: float) -> str:
    if amount == int(amount):
        return str(int(amount))
    return f"{amount:.2f}".rstrip("0").rstrip(".")


def _attachment_evidence_closure_status(invoice_total: float, payment_total: float) -> str:
    if invoice_total <= 0 and payment_total <= 0:
        return "无可校验附件凭证"
    if invoice_total <= 0:
        return "缺少附件发票"
    if payment_total <= 0:
        return "缺少付款凭证"
    if round(invoice_total, 2) == round(payment_total, 2):
        return "付款凭证金额与附件发票金额一致"
    return "付款凭证金额与附件发票金额不一致"


def detect_etc_batch_metadata(*values: Any) -> dict[str, Any]:
    structured_id = _find_structured_etc_batch_id(values)
    if structured_id:
        return {
            "source": ETC_BATCH_SOURCE,
            "etc_batch_id": structured_id,
            "tags": [ETC_BATCH_TAG],
        }
    text = "\n".join(_iter_text_values(values))
    if ETC_BATCH_TAG not in text:
        return {}
    match = ETC_BATCH_ID_RE.search(text)
    if not match:
        return {}
    etc_batch_id = clean_string(match.group(1))
    if not etc_batch_id:
        return {}
    return {
        "source": ETC_BATCH_SOURCE,
        "etc_batch_id": etc_batch_id,
        "tags": [ETC_BATCH_TAG],
    }


def _find_structured_etc_batch_id(values: Any) -> str:
    found = ""

    def visit(value: Any) -> None:
        nonlocal found
        if found or value in (None, ""):
            return
        if isinstance(value, dict):
            for key, child in value.items():
                if str(key).replace("_", "").lower() == "etcbatchid":
                    found = clean_string(child)
                    if found:
                        return
                visit(child)
            return
        if isinstance(value, (list, tuple, set)):
            for child in value:
                visit(child)

    visit(values)
    return found


def _iter_text_values(values: Any) -> list[str]:
    texts: list[str] = []

    def visit(value: Any) -> None:
        if value in (None, ""):
            return
        if isinstance(value, dict):
            for child in value.values():
                visit(child)
            return
        if isinstance(value, (list, tuple, set)):
            for child in value:
                visit(child)
            return
        text = clean_string(value)
        if text:
            texts.append(text)

    visit(values)
    return texts
