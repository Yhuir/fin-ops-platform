"""Source detail projections only; never used for matching, totals or classification.

Canonical records include operational defaults. Only fields whose ingestion mapping
preserves their source meaning belong in these drawer projections. In particular,
historical bank timestamps may contain a parser-supplied midnight, and OA expense
types/completion timestamps may be inferred. They are not source evidence.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Any

from fin_ops_platform.domain.models import Invoice
from fin_ops_platform.services.bank_transaction_unit import original_bank_summaries
from fin_ops_platform.services.oa_expense_details import public_oa_expense_items


def source_money(value: Any) -> str:
    if value is None:
        return ""
    integer, _, fraction = format(Decimal(str(value)), "f").partition(".")
    return f"{integer}.{fraction.rstrip('0').ljust(2, '0')}"


def invoice_source_line(invoice: Invoice) -> dict[str, Any]:
    return {
        "id": invoice.id,
        "taxClassificationCode": invoice.tax_classification_code,
        "specificBusinessType": invoice.specific_business_type,
        "taxableItemName": invoice.taxable_item_name,
        "specificationModel": invoice.specification_model,
        "unit": invoice.unit,
        "quantity": invoice.quantity,
        "unitPrice": invoice.unit_price,
        "amount": source_money(invoice.amount),
        "taxRate": invoice.tax_rate,
        "taxAmount": source_money(invoice.tax_amount),
        "totalWithTax": source_money(invoice.total_with_tax),
        "remark": invoice.remark,
    }


def invoice_source_detail(group: dict[str, Any]) -> dict[str, Any]:
    primary: Invoice = group["primary"]
    lines: list[Invoice] = list(group["line_items"])
    # A group sum is a business result, not a value printed on a source row.
    single = lines[0] if len(lines) == 1 else None
    return {
        "id": primary.id,
        "invoiceIdentityKey": group["identity_key"],
        "invoiceNo": primary.invoice_no if primary.invoice_no != primary.id else None,
        "invoiceCode": primary.invoice_code,
        "digitalInvoiceNo": primary.digital_invoice_no,
        "invoiceDate": primary.invoice_date,
        "sellerName": primary.seller_name,
        "sellerTaxNo": primary.seller_tax_no,
        "buyerName": primary.buyer_name,
        "buyerTaxNo": primary.buyer_tax_no,
        "amount": source_money(single.amount) if single else "",
        "taxAmount": source_money(single.tax_amount) if single else "",
        "totalWithTax": source_money(single.total_with_tax) if single else "",
        "taxRate": primary.tax_rate,
        "taxClassificationCode": primary.tax_classification_code,
        "specificBusinessType": primary.specific_business_type,
        "taxableItemName": primary.taxable_item_name,
        "invoiceSource": primary.invoice_source,
        "invoiceKind": primary.invoice_kind,
        "invoiceStatus": primary.invoice_status_from_source,
        "isPositiveInvoice": primary.is_positive_invoice,
        "riskLevel": primary.risk_level,
        "issuer": primary.issuer,
        "remark": primary.remark,
        "lineItems": [invoice_source_line(line) for line in lines],
    }


OA_SOURCE_DETAIL_KEYS = frozenset({
    "OA单号", "申请日期", "申请时间", "收款账号", "开户行", "付款方式",
    "票据类型", "流程状态", "url", "open_url",
})


def oa_source_fields(fields: dict[str, Any]) -> dict[str, Any]:
    result = {key: value for key, value in fields.items() if key in OA_SOURCE_DETAIL_KEYS}
    number = result.get("OA单号")
    if number and number == fields.get("Mongo文档ID") and number not in (
        fields.get("流程请求ID"), fields.get("流程实例ID"),
    ):
        result.pop("OA单号")
    return result


def oa_source_detail(record: Any) -> dict[str, Any]:
    payment = record.apply_type in {"payment_request", "付款申请", "支付申请"}
    fields = oa_source_fields(record.detail_fields)
    return {
        "oaId": record.id, "detailAvailable": True,
        "applicantName": record.applicant, "applicationType": record.apply_type,
        "projectName": record.project_name if payment else None,
        "workflowNo": fields.get("OA单号"), "workflowStatus": fields.get("流程状态"),
        "amount": record.amount if payment or record.detail_fields.get("金额来源") == "主表总金额" else None,
        "reason": record.reason if payment else None,
        "counterpartyName": record.counterparty_name,
        "detailFields": fields, "expenseItems": public_oa_expense_items(record.expense_items),
    }


def source_detail_sections(kind: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Existing section DTO for consumers that do not use the camel-case adapters."""
    if kind == "bank":
        labels = {"counterpartyName": "对方户名", "transactionDate": "交易日期",
                  "amount": "金额", "accountNo": "账号", "bookedDate": "入账日期",
                  "accountName": "账户名称", "bankSerialNo": "银行流水号",
                  "enterpriseSerialNo": "企业流水号", "voucherKind": "凭证种类",
                  "voucherNo": "凭证号", "accountDetailNo": "账户明细编号-交易流水号",
                  "counterpartyAccountNo": "对方账号", "counterpartyBankName": "对方开户机构",
                  "balance": "余额", "summary": "摘要", "remark": "备注"}
    elif kind == "invoice":
        labels = {"invoiceNo": "发票号码", "invoiceCode": "发票代码", "digitalInvoiceNo": "数电发票号码",
                  "invoiceDate": "开票日期", "sellerName": "销方名称", "sellerTaxNo": "销方识别号",
                  "buyerName": "购买方名称", "buyerTaxNo": "购买方识别号", "amount": "不含税金额",
                  "taxAmount": "税额", "totalWithTax": "价税合计", "taxRate": "税率",
                  "invoiceKind": "发票票种", "invoiceStatus": "发票状态", "isPositiveInvoice": "是否正数发票",
                  "riskLevel": "发票风险等级", "issuer": "开票人", "remark": "备注",
                  "taxableItemName": "货物或应税劳务名称", "specificBusinessType": "特定业务类型",
                  "invoiceSource": "发票来源"}
    elif kind == "oa":
        labels = {"applicantName": "申请人", "applicationType": "OA类型", "projectName": "项目名称",
                  "amount": "金额", "reason": "申请事由", "counterpartyName": "收款方"}
    else:
        raise ValueError(f"Unknown source detail kind: {kind}")
    fields = [{"label": label, "value": payload[key]} for key, label in labels.items()
              if payload.get(key) is not None and payload.get(key) != ""]
    if kind == "oa":
        fields.extend({"label": key, "value": value} for key, value in payload["detailFields"].items()
                      if value is not None and value != "")
    section = {"title": {"bank": "银行流水", "invoice": "发票", "oa": "OA信息"}[kind], "fields": fields}
    if kind == "bank":
        section["bank_transaction_id"] = payload["id"]
    return [section]


def bank_source_detail(transaction: Any) -> dict[str, Any]:
    return {
        "id": transaction.id,
        "counterpartyName": (
            transaction.counterparty_name_raw
            if transaction.counterparty_name_raw not in {"unknown", "未知对手方"} else ""
        ),
        "transactionDate": transaction.txn_date,
        "amount": source_money(transaction.amount),
        "direction": str(getattr(transaction.txn_direction, "value", transaction.txn_direction)),
        "accountNo": transaction.account_no,
        "accountName": transaction.account_name,
        "bankSerialNo": transaction.bank_serial_no,
        "enterpriseSerialNo": transaction.enterprise_serial_no,
        "voucherKind": transaction.voucher_kind,
        "voucherNo": transaction.voucher_no,
        "accountDetailNo": transaction.account_detail_no,
        "counterpartyAccountNo": transaction.counterparty_account_no,
        "counterpartyBankName": transaction.counterparty_bank_name,
        "bookedDate": transaction.booked_date,
        "summary": transaction.summary,
        "remark": transaction.remark,
        "balance": source_money(transaction.balance),
        "bankTextFields": list(transaction.bank_text_fields),
    }


BANK_SOURCE_KEYS = frozenset({
    "amount", "account_no", "account_name", "counterparty_name_raw",
    "counterparty_name", "counterparty_account_no", "counterparty_bank_name",
    "txn_date", "booked_date", "balance", "summary", "remark", "bank_serial_no",
    "enterprise_serial_no", "voucher_kind", "voucher_no", "account_detail_no",
})
INVOICE_SOURCE_KEYS = frozenset({
    "invoice_no", "invoice_code", "digital_invoice_no", "invoice_date",
    "seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no", "amount",
    "tax_amount", "tax_rate", "total_with_tax", "invoice_status_from_source",
    "invoice_kind", "is_positive_invoice", "risk_level", "issuer", "remark",
    "tax_classification_code", "specific_business_type", "taxable_item_name",
    "specification_model", "unit", "quantity", "unit_price",
    "invoice_source",
})


def workbench_source_row(row: dict[str, Any]) -> dict[str, Any]:
    """Project only the row-detail response, leaving list/search facts untouched."""
    fields = row.get("detail_fields") or {}
    kind = row["type"]
    if kind == "oa":
        payment = row.get("apply_type") in {"payment_request", "付款申请", "支付申请"}
        details = oa_source_fields(fields)
        details["OA类型"] = row.get("apply_type")
        details["申请人"] = row.get("applicant")
        if fields.get("金额来源") == "主表总金额" or payment:
            details["金额"] = row.get("amount")
        if payment:
            details["申请事由"] = row.get("reason")
            details["项目名称"] = row.get("project_name")
        return {**row, "detail_fields": details,
                "expense_items": public_oa_expense_items(row.get("expense_items") or [])}
    keys = BANK_SOURCE_KEYS if kind == "bank" else INVOICE_SOURCE_KEYS
    details = {key: value for key, value in fields.items() if key in keys}
    if kind == "bank":
        counterparty = details.pop("counterparty_name_raw", None)
        if counterparty not in (None, "", "unknown", "未知对手方"):
            details["counterparty_name"] = counterparty
    return {**row, "detail_fields": details}


def source_relation_sections(kind: str, summaries: list[Any]) -> list[dict[str, Any]]:
    typed_summaries = [summary for summary in summaries if isinstance(summary, dict)]
    if not typed_summaries:
        return []
    if kind == "oa":
        return [
            {
                "title": f"OA {index}",
                "fields": [
                    {"label": "申请人", "value": summary.get("applicantName")},
                    {"label": "类型", "value": summary.get("applicationType")},
                ],
            }
            for index, summary in enumerate(typed_summaries, start=1)
        ]
    if kind == "bank":
        typed_summaries = original_bank_summaries(typed_summaries)
        return [
            {
                "title": f"银行流水 {index}",
                "bank_transaction_id": summary["bankTransactionId"],
                "fields": [
                    {"label": "对方户名", "value": summary.get("counterpartyName")},
                    {"label": "金额", "value": summary.get("amount")},
                    {"label": "收支方向", "value": summary.get("directionLabel") or summary.get("direction")},
                    {"label": "摘要", "value": summary.get("summary")},
                    {"label": "备注", "value": summary.get("remark")},
                ],
            }
            for index, summary in enumerate(typed_summaries, start=1)
        ]
    return [
        {
            "title": f"发票 {index}",
            "fields": [
                {"label": "发票号码", "value": summary.get("invoiceNo")},
                {"label": "数电发票号码", "value": summary.get("digitalInvoiceNo")},
                {"label": "开票日期", "value": summary.get("invoiceDate")},
                {"label": "货物或应税劳务名称", "value": summary.get("taxableItemName")},
            ],
        }
        for index, summary in enumerate(typed_summaries, start=1)
    ]

