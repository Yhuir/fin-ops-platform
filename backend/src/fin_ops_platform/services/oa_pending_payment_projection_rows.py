from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from hashlib import sha1
import json
from typing import Any, Callable

from fin_ops_platform.domain.models import BankTransaction, Invoice
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.invoice_relation_query_context import relation_status, summary_is_linked
from fin_ops_platform.services.oa_adapter import OAApplicationRecord
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRecord, PAY_STATUS_PAID


ZERO = Decimal("0.00")
CENT = Decimal("0.01")
OA_PENDING_PAYMENT_PROJECTION_RULES_VERSION = "oa-pending-payment:canonical-relation-v7"
OA_APPLICATION_TIME_FIELDS = (
    "审批完成时间",
    "申请时间",
    "申请日期",
    "提交时间",
    "创建时间",
    "单据日期",
    "日期",
    "applicationTime",
    "application_time",
    "applyTime",
    "apply_time",
    "createdAt",
    "created_at",
)


def build_oa_pending_payment_rows(
    *,
    records: list[OAApplicationRecord],
    relations: list[dict[str, Any]],
    bank_transactions: list[BankTransaction],
    invoices: list[Invoice],
    payment_statuses_by_flow_id: dict[str, OAPaymentStatusRecord] | None,
    flow_id_resolver: Callable[[OAApplicationRecord], str | None],
    scope_key: str,
    lifecycle_policy: InvoiceLifecyclePolicy | None = None,
) -> list[dict[str, Any]]:
    """Build one OA month shard from already-loaded canonical facts."""

    month_records = [
        record
        for record in records
        if isinstance(record, OAApplicationRecord)
        and str(record.month or "").startswith(scope_key[:7])
    ]
    records_by_id = {record.id: record for record in month_records}
    relations_by_row_id = _relations_by_row_id(relations)
    banks_by_id = {bank.id: bank for bank in bank_transactions if isinstance(bank, BankTransaction)}
    invoices_by_id = {invoice.id: invoice for invoice in invoices if isinstance(invoice, Invoice)}
    policy = lifecycle_policy or InvoiceLifecyclePolicy()
    rows: list[dict[str, Any]] = []
    emitted_relations: set[str] = set()
    grouped_oa_ids: set[str] = set()

    for record in month_records:
        for relation in relations_by_row_id.get(record.id, []):
            relation_identity = _relation_row_identity(relation)
            if not relation_identity or relation_identity in emitted_relations:
                continue
            relation_records = [
                records_by_id[row_id]
                for row_id, row_type in _typed_relation_rows(relation)
                if row_type == "oa" and row_id in records_by_id
            ]
            if not relation_records or record.id not in {item.id for item in relation_records}:
                continue
            rows.append(
                _relation_group_row(
                    relation=relation,
                    records=relation_records,
                    banks_by_id=banks_by_id,
                    invoices_by_id=invoices_by_id,
                    payment_statuses_by_flow_id=payment_statuses_by_flow_id,
                    flow_id_resolver=flow_id_resolver,
                    scope_key=scope_key,
                    lifecycle_policy=policy,
                )
            )
            emitted_relations.add(relation_identity)
            grouped_oa_ids.update(item.id for item in relation_records)

    for record in month_records:
        if record.id in grouped_oa_ids:
            continue
        rows.append(
            _single_oa_row(
                record,
                relations=relations_by_row_id.get(record.id, []),
                banks_by_id=banks_by_id,
                invoices_by_id=invoices_by_id,
                payment_statuses_by_flow_id=payment_statuses_by_flow_id,
                flow_id_resolver=flow_id_resolver,
                lifecycle_policy=policy,
            )
        )
    return rows


def relation_member_ids(relations: list[dict[str, Any]], *, row_types: set[str]) -> list[str]:
    return sorted(
        {
            row_id
            for relation in relations
            if isinstance(relation, dict)
            for row_id, row_type in _typed_relation_rows(relation)
            if row_type in row_types
        }
    )


def _single_oa_row(
    record: OAApplicationRecord,
    *,
    relations: list[dict[str, Any]],
    banks_by_id: dict[str, BankTransaction],
    invoices_by_id: dict[str, Invoice],
    payment_statuses_by_flow_id: dict[str, OAPaymentStatusRecord] | None,
    flow_id_resolver: Callable[[OAApplicationRecord], str | None],
    lifecycle_policy: InvoiceLifecyclePolicy,
) -> dict[str, Any]:
    bank_payload = _bank_relation_payload(record.amount, relations, banks_by_id)
    invoice_payload = _invoice_relation_payload(record.amount, relations, invoices_by_id)
    payment_status = _payment_status_for_amount(record.amount, bank_payload, lifecycle_policy)
    row = {
        "id": _row_id(record.id),
        "oa": _oa_summary(record),
        "paymentStatus": payment_status,
        "oaPaymentWriteback": _oa_payment_writeback_status(
            [record],
            payment_status,
            writeback_eligible=_payment_writeback_eligible(record.amount, bank_payload),
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            flow_id_resolver=flow_id_resolver,
        ),
        "bankTransaction": bank_payload,
        "invoice": invoice_payload,
    }
    row["searchText"] = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return row


def _relation_group_row(
    *,
    relation: dict[str, Any],
    records: list[OAApplicationRecord],
    banks_by_id: dict[str, BankTransaction],
    invoices_by_id: dict[str, Invoice],
    payment_statuses_by_flow_id: dict[str, OAPaymentStatusRecord] | None,
    flow_id_resolver: Callable[[OAApplicationRecord], str | None],
    scope_key: str,
    lifecycle_policy: InvoiceLifecyclePolicy,
) -> dict[str, Any]:
    oa_payload = _oa_group_payload(records, relation)
    oa_amount = _parse_decimal(oa_payload.get("amount")) or ZERO
    bank_payload = _bank_relation_payload(oa_amount, [relation], banks_by_id)
    invoice_payload = _invoice_relation_payload(oa_amount, [relation], invoices_by_id)
    payment_status = _payment_status_for_amount(oa_payload.get("amount"), bank_payload, lifecycle_policy)
    row = {
        "id": _relation_row_id(_relation_row_identity(relation), scope_key=scope_key),
        "oa": oa_payload,
        "paymentStatus": payment_status,
        "oaPaymentWriteback": _oa_payment_writeback_status(
            records,
            payment_status,
            writeback_eligible=_payment_writeback_eligible(oa_payload.get("amount"), bank_payload),
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            flow_id_resolver=flow_id_resolver,
        ),
        "bankTransaction": bank_payload,
        "invoice": invoice_payload,
    }
    row["searchText"] = json.dumps(row, ensure_ascii=False, sort_keys=True)
    return row


def _oa_group_payload(records: list[OAApplicationRecord], relation: dict[str, Any]) -> dict[str, Any]:
    summaries = [_oa_relation_summary(record, relation) for record in records]
    primary = summaries[0] if summaries else {}
    amounts = [_parse_decimal(summary.get("amount")) for summary in summaries]
    complete_amounts = len(amounts) == len(summaries) and all(amount is not None for amount in amounts)
    total = sum((amount or ZERO for amount in amounts), start=ZERO)
    relation_count = len(summaries)
    return {
        "id": primary.get("oaId", ""),
        "primaryOaId": primary.get("oaId", ""),
        "applicantName": primary.get("applicantName", ""),
        "applicationType": primary.get("applicationType", ""),
        "projectName": primary.get("projectName", ""),
        "applicationTime": primary.get("applicationTime", ""),
        "amount": _money(total) if complete_amounts else "",
        "detailAvailable": relation_count > 0,
        "month": primary.get("month", ""),
        "workflowNo": primary.get("workflowNo", ""),
        "reason": primary.get("reason", ""),
        "counterpartyName": primary.get("counterpartyName", ""),
        "workflowStatus": primary.get("workflowStatus", ""),
        "relationCount": relation_count,
        "hasMultiple": relation_count > 1,
        "detailMode": "none" if relation_count == 0 else "list" if relation_count > 1 else "single",
        "summaries": summaries,
    }


def _oa_summary(record: OAApplicationRecord) -> dict[str, Any]:
    summary = _oa_relation_summary(record)
    return {
        "id": summary["oaId"],
        "primaryOaId": summary["oaId"],
        "applicantName": summary["applicantName"],
        "applicationType": summary["applicationType"],
        "projectName": summary["projectName"],
        "applicationTime": summary["applicationTime"],
        "amount": summary["amount"],
        "detailAvailable": True,
        "month": summary["month"],
        "workflowNo": summary["workflowNo"],
        "reason": summary["reason"],
        "counterpartyName": summary["counterpartyName"],
        "workflowStatus": summary["workflowStatus"],
        "relationCount": 1,
        "hasMultiple": False,
        "detailMode": "single",
        "summaries": [summary],
    }


def _oa_relation_summary(
    record: OAApplicationRecord,
    relation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "oaId": record.id,
        "applicantName": record.applicant,
        "applicationType": record.apply_type,
        "projectName": record.project_name_display or record.project_name,
        "applicationTime": _oa_application_time(record),
        "amount": _money(record.amount) if _parse_decimal(record.amount) is not None else "",
        "month": record.month,
        "workflowNo": record.case_id or "",
        "reason": record.reason,
        "counterpartyName": record.counterparty_name,
        "workflowStatus": str(getattr(record, "workflow_status", "") or "").strip(),
    }
    if relation is not None:
        summary["relationCaseId"] = relation.get("case_id", "")
        summary["relationStatus"] = relation_status(relation)
        summary["relationSource"] = str(relation.get("relation_source") or "")
    return summary


def _bank_relation_payload(
    oa_amount_value: Any,
    relations: list[dict[str, Any]],
    banks_by_id: dict[str, BankTransaction],
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    non_outflow_edges: list[dict[str, str]] = []
    seen_non_outflow_edges: set[tuple[str, str]] = set()
    missing_bank_relation_count = 0
    oa_amount = _parse_decimal(oa_amount_value) or ZERO
    for relation in relations:
        linked = relation_status(relation) == "linked"
        for row_id, row_type in _typed_relation_rows(relation):
            if row_type not in {"bank", "bank_transaction"}:
                continue
            bank = banks_by_id.get(row_id)
            if bank is None:
                if linked:
                    missing_bank_relation_count += 1
                continue
            if _bank_direction(bank) != "outflow":
                edge_key = (str(relation.get("case_id") or ""), bank.id)
                if linked and edge_key not in seen_non_outflow_edges:
                    seen_non_outflow_edges.add(edge_key)
                    non_outflow_edges.append(
                        {
                            "bankTransactionId": bank.id,
                            "relationCaseId": edge_key[0],
                            "relationStatus": relation_status(relation),
                            "relationSource": str(relation.get("relation_source") or ""),
                        }
                    )
                continue
            if bank.id not in seen:
                seen.add(bank.id)
                summaries.append(_bank_summary(bank, oa_amount, relation))
    summaries.sort(key=lambda item: item["_sort"])
    public = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
    primary = public[0] if public else {}
    linked_summaries = [summary for summary in public if summary_is_linked(summary)]
    paid_total = sum((_decimal(summary.get("amount")) for summary in linked_summaries), start=ZERO)
    return {
        "primaryBankTransactionId": primary.get("bankTransactionId"),
        "accountDetailNo": primary.get("accountDetailNo", ""),
        "enterpriseSerialNo": primary.get("enterpriseSerialNo", ""),
        "voucherKind": primary.get("voucherKind", ""),
        "voucherNo": primary.get("voucherNo", ""),
        "bankName": primary.get("bankName", ""),
        "accountNo": primary.get("accountNo", ""),
        "accountLast4": primary.get("accountLast4", ""),
        "bankAccount": primary.get("bankAccount", ""),
        "accountName": primary.get("accountName", ""),
        "tradeTime": primary.get("tradeTime", ""),
        "debitAmount": primary.get("debitAmount", ""),
        "creditAmount": primary.get("creditAmount", ""),
        "balance": primary.get("balance", ""),
        "currency": primary.get("currency", ""),
        "counterpartyName": primary.get("counterpartyName", ""),
        "counterpartyAccountNo": primary.get("counterpartyAccountNo", ""),
        "counterpartyBankName": primary.get("counterpartyBankName", ""),
        "bookedDate": primary.get("bookedDate", ""),
        "summary": primary.get("summary", ""),
        "remark": primary.get("remark", ""),
        "amount": primary.get("amount", ""),
        "paidTotal": _money(paid_total),
        "direction": primary.get("direction", ""),
        "directionLabel": primary.get("directionLabel", ""),
        "relationCount": len(public),
        "hasMultiple": len(public) > 1,
        "detailMode": "none" if not public else "list" if len(public) > 1 else "single",
        "summaries": public,
        "linkedRelationCount": len(linked_summaries),
        "missingBankRelationCount": missing_bank_relation_count,
        "nonOutflowBankRelationCount": len(non_outflow_edges),
        "nonOutflowRelationEdges": non_outflow_edges,
    }


def _bank_summary(bank: BankTransaction, oa_amount: Decimal, relation: dict[str, Any]) -> dict[str, Any]:
    bank_amount = abs(_decimal(bank.amount))
    return {
        "bankTransactionId": bank.id,
        "accountDetailNo": bank.account_detail_no or "",
        "enterpriseSerialNo": bank.enterprise_serial_no or "",
        "voucherKind": bank.voucher_kind or "",
        "voucherNo": bank.voucher_no or "",
        "bankName": bank.imported_bank_name or "",
        "accountNo": bank.account_no or "",
        "accountLast4": bank.imported_bank_last4 or str(bank.account_no or "")[-4:],
        "bankAccount": " ".join(
            part for part in [str(bank.imported_bank_name or "").strip(), str(bank.imported_bank_last4 or str(bank.account_no or "")[-4:]).strip()] if part
        ),
        "accountName": bank.account_name or "",
        "tradeTime": bank.trade_time or bank.txn_date or "",
        "debitAmount": _money(bank.amount) if _bank_direction(bank) == "outflow" else "0.00",
        "creditAmount": _money(bank.amount) if _bank_direction(bank) == "inflow" else "0.00",
        "balance": _money(bank.balance) if bank.balance is not None else "",
        "currency": bank.currency or "",
        "counterpartyName": bank.counterparty_name_raw or "",
        "counterpartyAccountNo": bank.counterparty_account_no or "",
        "counterpartyBankName": bank.counterparty_bank_name or "",
        "bookedDate": bank.booked_date or "",
        "summary": bank.summary or "",
        "remark": bank.remark or "",
        "amount": _money(bank_amount),
        "direction": _bank_direction(bank),
        "directionLabel": "支出" if _bank_direction(bank) == "outflow" else "收入",
        "relationCaseId": relation.get("case_id", ""),
        "relationStatus": relation_status(relation),
        "relationSource": str(relation.get("relation_source") or ""),
        "_sort": (abs(bank_amount - oa_amount), -_sortable_time(bank.trade_time or bank.txn_date), bank.id),
    }


def _invoice_relation_payload(
    oa_amount_value: Any,
    relations: list[dict[str, Any]],
    invoices_by_id: dict[str, Invoice],
) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    seen: set[str] = set()
    oa_amount = _parse_decimal(oa_amount_value) or ZERO
    for relation in relations:
        for row_id, row_type in _typed_relation_rows(relation):
            invoice = invoices_by_id.get(row_id)
            if row_type == "invoice" and invoice is not None and invoice.id not in seen:
                seen.add(invoice.id)
                total = _invoice_total(invoice)
                summaries.append(
                    {
                        "invoiceId": invoice.id,
                        "digitalInvoiceNo": invoice.digital_invoice_no or invoice.invoice_no or "",
                        "sellerName": invoice.seller_name or invoice.counterparty.name,
                        "invoiceDate": invoice.invoice_date or "",
                        "totalWithTax": _money(total),
                        "relationCaseId": relation.get("case_id", ""),
                        "relationStatus": relation_status(relation),
                        "relationSource": str(relation.get("relation_source") or ""),
                        "_sort": (abs(total - oa_amount), invoice.invoice_date or "", invoice.id),
                    }
                )
    summaries.sort(key=lambda item: item["_sort"])
    public = [{key: value for key, value in item.items() if key != "_sort"} for item in summaries]
    primary = public[0] if public else {}
    invoice_total = sum((_decimal(summary.get("totalWithTax")) for summary in public), start=ZERO)
    return {
        "primaryInvoiceId": primary.get("invoiceId"),
        "digitalInvoiceNo": primary.get("digitalInvoiceNo", ""),
        "sellerName": primary.get("sellerName", ""),
        "invoiceDate": primary.get("invoiceDate", ""),
        "totalWithTax": _money(invoice_total) if public else "",
        "relationCount": len(public),
        "hasMultiple": len(public) > 1,
        "detailMode": "none" if not public else "list" if len(public) > 1 else "single",
        "summaries": public,
    }


def _payment_status_for_amount(
    oa_amount_value: Any,
    bank_payload: dict[str, Any],
    lifecycle_policy: InvoiceLifecyclePolicy,
) -> dict[str, str]:
    return lifecycle_policy.evaluate_oa_payment(
        oa_amount=_parse_decimal(oa_amount_value),
        paid_total=_decimal(bank_payload.get("paidTotal")),
        has_bank=(
            int(bank_payload.get("linkedRelationCount") or 0) > 0
            or int(bank_payload.get("missingBankRelationCount") or 0) > 0
            or int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0
        ),
        has_missing_bank_relation=int(bank_payload.get("missingBankRelationCount") or 0) > 0,
        has_non_outflow_bank_relation=int(bank_payload.get("nonOutflowBankRelationCount") or 0) > 0,
    )


def _payment_writeback_eligible(oa_amount_value: Any, bank_payload: dict[str, Any]) -> bool:
    oa_amount = _parse_decimal(oa_amount_value)
    return bool(
        oa_amount is not None
        and int(bank_payload.get("linkedRelationCount") or 0) > 0
        and int(bank_payload.get("missingBankRelationCount") or 0) == 0
        and int(bank_payload.get("nonOutflowBankRelationCount") or 0) == 0
        and abs(_decimal(bank_payload.get("paidTotal")) - oa_amount) <= CENT
    )


def _oa_payment_writeback_status(
    records: list[OAApplicationRecord],
    payment_status: dict[str, str],
    *,
    writeback_eligible: bool,
    payment_statuses_by_flow_id: dict[str, OAPaymentStatusRecord] | None,
    flow_id_resolver: Callable[[OAApplicationRecord], str | None],
) -> dict[str, Any]:
    if payment_status.get("code") != "paid" or not writeback_eligible:
        return _writeback("not_written", sync_status="not_required")
    if payment_statuses_by_flow_id is None:
        return _writeback("not_written", sync_status="unavailable")
    flow_ids: list[str] = []
    for record in records:
        flow_id = flow_id_resolver(record)
        if not flow_id:
            return _writeback("not_written", flow_ids=flow_ids, sync_status="flow_id_missing")
        flow_ids.append(flow_id)
        status = payment_statuses_by_flow_id.get(flow_id)
        if status is None or status.pay_status != PAY_STATUS_PAID:
            return _writeback("not_written", flow_ids=flow_ids, sync_status="ready")
    return _writeback("written", flow_ids=flow_ids, sync_status="ready")


def _writeback(code: str, *, flow_ids: list[str] | None = None, sync_status: str) -> dict[str, Any]:
    written = code == "written"
    return {
        "code": "written" if written else "not_written",
        "label": "已写回" if written else "未写回",
        "flowIds": list(flow_ids or []),
        "syncStatus": sync_status,
    }


def _relations_by_row_id(relations: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {}
    for relation in relations:
        if not isinstance(relation, dict) or relation_status(relation) != "linked":
            continue
        for row_id, _row_type in _typed_relation_rows(relation):
            result.setdefault(row_id, []).append(relation)
    return result


def _typed_relation_rows(relation: dict[str, Any]) -> list[tuple[str, str]]:
    row_ids = [str(value) for value in list(relation.get("row_ids") or [])]
    row_types = [str(value) for value in list(relation.get("row_types") or [])]
    return [
        (row_id, row_types[index] if index < len(row_types) else _infer_row_type(row_id))
        for index, row_id in enumerate(row_ids)
    ]


def _infer_row_type(row_id: str) -> str:
    if row_id.startswith("bank"):
        return "bank"
    if row_id.startswith("oa"):
        return "oa"
    return "invoice"


def _relation_row_identity(relation: dict[str, Any]) -> str:
    case_id = str(relation.get("case_id") or relation.get("relation_id") or "").strip()
    return case_id or "|".join(f"{row_type}:{row_id}" for row_id, row_type in _typed_relation_rows(relation))


def _row_id(oa_id: str) -> str:
    return "oa_pending_payment_row_" + sha1(str(oa_id).encode("utf-8")).hexdigest()[:16]


def _relation_row_id(identity: str, *, scope_key: str) -> str:
    return "oa_pending_payment_relation_" + sha1(f"{identity}:{scope_key[:7]}".encode("utf-8")).hexdigest()[:16]


def _parse_decimal(value: Any) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _decimal(value: Any) -> Decimal:
    return _parse_decimal(value) or ZERO


def _money(value: Any) -> str:
    return f"{_decimal(value).quantize(CENT)}"


def _invoice_total(invoice: Invoice) -> Decimal:
    return _decimal(invoice.total_with_tax) if invoice.total_with_tax is not None else _decimal(invoice.amount) + _decimal(invoice.tax_amount)


def _bank_direction(transaction: BankTransaction) -> str:
    value = getattr(transaction.txn_direction, "value", str(transaction.txn_direction))
    return "outflow" if "outflow" in value else "inflow"


def _oa_application_time(record: OAApplicationRecord) -> str:
    detail_fields = record.detail_fields if isinstance(record.detail_fields, dict) else {}
    for field in OA_APPLICATION_TIME_FIELDS:
        text = _oa_time_text(detail_fields.get(field))
        if text:
            return text
    return ""


def _oa_time_text(value: Any) -> str:
    text = str(value or "").strip()
    if not text or text in {"-", "--", "—", "None", "null"}:
        return ""
    normalized = text.replace("T", " ").strip()
    if normalized.endswith("Z"):
        normalized = normalized[:-1].strip()
    return normalized[:19] if _looks_like_datetime(normalized) else normalized


def _looks_like_datetime(value: str) -> bool:
    return len(value) >= 19 and value[4] == "-" and value[7] == "-" and value[10] == " " and value[13] == ":" and value[16] == ":"


def _sortable_time(value: str | None) -> float:
    try:
        return datetime.fromisoformat(str(value or "").strip().replace(" ", "T")).timestamp()
    except ValueError:
        return 0
