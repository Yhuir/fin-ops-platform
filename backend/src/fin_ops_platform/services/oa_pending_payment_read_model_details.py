from __future__ import annotations

from copy import deepcopy
from typing import Any


def oa_pending_payment_oa_detail_from_row(row: dict[str, Any]) -> dict[str, Any]:
    oa = _mapping(row.get("oa"))
    oa_id = _text(oa.get("id"))
    return {
        "id": oa_id,
        "oaId": oa_id,
        "title": "OA详情",
        "subtitle": _text(oa.get("projectName")) or _text(oa.get("workflowNo")) or oa_id,
        "detailAvailable": bool(oa.get("detailAvailable", True)),
        "sections": [
            {
                "title": "OA信息",
                "fields": [
                    {"label": "申请人", "value": oa.get("applicantName")},
                    {"label": "类型", "value": oa.get("applicationType")},
                    {"label": "项目名称", "value": oa.get("projectName")},
                    {"label": "金额", "value": oa.get("amount")},
                    {"label": "月份", "value": oa.get("month")},
                    {"label": "事由", "value": oa.get("reason")},
                    {"label": "往来方", "value": oa.get("counterpartyName")},
                ],
            }
        ],
        "raw": deepcopy(oa),
    }


def oa_pending_payment_bank_detail_from_row(row: dict[str, Any], bank_transaction_id: str) -> dict[str, Any]:
    bank = _bank_summary_for_detail(row, bank_transaction_id)
    bank_id = _text(bank.get("bankTransactionId") or bank.get("primaryBankTransactionId") or bank_transaction_id)
    return {
        "id": bank_id,
        "title": "支出流水详情",
        "subtitle": _text(bank.get("counterpartyName")) or _text(bank.get("summary")) or bank_id,
        "detailAvailable": True,
        "sections": [
            {
                "title": "凭证信息",
                "fields": [
                    {"label": "账户明细编号-交易流水号", "value": bank.get("accountDetailNo")},
                    {"label": "企业流水号", "value": bank.get("enterpriseSerialNo")},
                    {"label": "凭证种类", "value": bank.get("voucherKind")},
                    {"label": "凭证号", "value": bank.get("voucherNo")},
                ],
            },
            {
                "title": "流水信息",
                "fields": [
                    {"label": "支出银行", "value": bank.get("bankName")},
                    {"label": "账户名称", "value": bank.get("accountName")},
                    {"label": "交易时间", "value": bank.get("tradeTime")},
                    {"label": "借方发生额", "value": bank.get("debitAmount")},
                    {"label": "贷方发生额", "value": bank.get("creditAmount")},
                    {"label": "余额", "value": bank.get("balance")},
                    {"label": "币种", "value": bank.get("currency")},
                ],
            },
            {
                "title": "对方信息",
                "fields": [
                    {"label": "对方户名", "value": bank.get("counterpartyName")},
                    {"label": "对方账号", "value": bank.get("counterpartyAccountNo")},
                    {"label": "对方开户机构", "value": bank.get("counterpartyBankName")},
                    {"label": "记账日期", "value": bank.get("bookedDate")},
                    {"label": "摘要", "value": bank.get("summary")},
                    {"label": "备注", "value": bank.get("remark")},
                ],
            },
        ],
        "relations": _relation_summaries_from_row(row),
        "raw": deepcopy(bank),
    }


def oa_pending_payment_invoice_detail_from_row(row: dict[str, Any], invoice_id: str) -> dict[str, Any]:
    invoice = _invoice_summary_for_detail(row, invoice_id)
    resolved_invoice_id = _text(invoice.get("invoiceId") or invoice.get("primaryInvoiceId") or invoice_id)
    return {
        "id": resolved_invoice_id,
        "title": "发票详情",
        "subtitle": _text(invoice.get("digitalInvoiceNo")) or resolved_invoice_id,
        "detailAvailable": True,
        "sections": [
            {
                "title": "发票情况",
                "fields": [
                    {"label": "数电发票号码", "value": invoice.get("digitalInvoiceNo")},
                    {"label": "进项发票方名称", "value": invoice.get("sellerName")},
                    {"label": "开票日期", "value": invoice.get("invoiceDate")},
                    {"label": "价税合计", "value": invoice.get("totalWithTax")},
                ],
            }
        ],
        "raw": deepcopy(invoice),
    }


def oa_pending_payment_relation_details_from_row(row: dict[str, Any], *, kind: str) -> dict[str, Any]:
    normalized_kind = _text(kind)
    if normalized_kind not in {"bank", "invoice"}:
        raise ValueError("kind must be bank or invoice.")
    relation_payload = _mapping(row.get("bankTransaction")) if normalized_kind == "bank" else _mapping(row.get("invoice"))
    summaries = [summary for summary in list(relation_payload.get("summaries") or []) if isinstance(summary, dict)]
    oa = _mapping(row.get("oa"))
    return {
        "rowId": row.get("id"),
        "oaId": oa.get("id"),
        "kind": normalized_kind,
        "title": "支出流水关联明细" if normalized_kind == "bank" else "发票关联明细",
        "subtitle": _text(oa.get("applicantName")) or _text(oa.get("projectName")) or _text(oa.get("id")),
        "detailAvailable": relation_payload.get("detailMode") != "none",
        "relationCount": relation_payload.get("relationCount", 0),
        "hasMultiple": relation_payload.get("hasMultiple", False),
        "summaries": deepcopy(summaries),
        "sections": _relation_detail_sections(normalized_kind, summaries),
        "relations": _relation_summaries_from_row(row),
    }


def _bank_summary_for_detail(row: dict[str, Any], bank_transaction_id: str) -> dict[str, Any]:
    bank = _mapping(row.get("bankTransaction"))
    wanted = _text(bank_transaction_id)
    for summary in list(bank.get("summaries") or []):
        if isinstance(summary, dict) and _text(summary.get("bankTransactionId")) == wanted:
            return deepcopy(summary)
    return {
        "bankTransactionId": bank.get("primaryBankTransactionId"),
        **deepcopy(bank),
    }


def _invoice_summary_for_detail(row: dict[str, Any], invoice_id: str) -> dict[str, Any]:
    invoice = _mapping(row.get("invoice"))
    wanted = _text(invoice_id)
    for summary in list(invoice.get("summaries") or []):
        if isinstance(summary, dict) and _text(summary.get("invoiceId")) == wanted:
            return deepcopy(summary)
    return {
        "invoiceId": invoice.get("primaryInvoiceId"),
        **deepcopy(invoice),
    }


def _relation_detail_sections(kind: str, summaries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not summaries:
        return [{"title": "关联明细", "fields": [{"label": "状态", "value": "暂无关联记录"}]}]
    if kind == "bank":
        return [
            {
                "title": f"支出流水 {index}",
                "fields": [
                    {"label": "支出银行", "value": summary.get("bankName")},
                    {"label": "交易时间", "value": summary.get("tradeTime")},
                    {"label": "金额", "value": summary.get("amount")},
                    {"label": "对方户名", "value": summary.get("counterpartyName")},
                    {"label": "账户明细编号-交易流水号", "value": summary.get("accountDetailNo")},
                    {"label": "摘要", "value": summary.get("summary")},
                    {"label": "备注", "value": summary.get("remark")},
                ],
            }
            for index, summary in enumerate(summaries, start=1)
        ]
    return [
        {
            "title": f"发票 {index}",
            "fields": [
                {"label": "数电发票号码", "value": summary.get("digitalInvoiceNo")},
                {"label": "进项发票方名称", "value": summary.get("sellerName")},
                {"label": "开票日期", "value": summary.get("invoiceDate")},
                {"label": "价税合计", "value": summary.get("totalWithTax")},
            ],
        }
        for index, summary in enumerate(summaries, start=1)
    ]


def _relation_summaries_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    relations: dict[str, dict[str, Any]] = {}
    for section_key in ("bankTransaction", "invoice"):
        section = _mapping(row.get(section_key))
        for summary in list(section.get("summaries") or []):
            if not isinstance(summary, dict):
                continue
            case_id = _text(summary.get("relationCaseId"))
            if case_id:
                relations[case_id] = {"caseId": case_id}
    return list(relations.values())


def _mapping(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _text(value: Any) -> str:
    return str(value or "").strip()
