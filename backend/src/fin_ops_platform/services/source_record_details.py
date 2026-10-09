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
from fin_ops_platform.services.bank_transaction_unit import original_bank_summaries, original_bank_transaction
from fin_ops_platform.services.invoice_financial_values import (
    PUBLIC_FIELDS,
    invoice_financial_summary,
    resolve_invoice_financial_values,
)
from fin_ops_platform.services.invoice_kind import INVOICE_KIND_NAMES
from fin_ops_platform.services.oa_expense_details import OA_EXPENSE_FIELDS, public_oa_expense_items
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.output_invoice_tax_rate import combine_invoice_tax_rates


def source_money(value: Any) -> str:
    if value is None:
        return ""
    integer, _, fraction = format(Decimal(str(value)), "f").partition(".")
    return f"{integer}.{fraction.rstrip('0').ljust(2, '0')}"


def invoice_source_line(source: dict[str, Any], *, invoice_id: str, index: int) -> dict[str, Any]:
    """Project an actual source detail row, never invoice header values."""
    return {
        "id": f"{invoice_id}:source-line:{index}",
        "taxClassificationCode": source.get("tax_classification_code"),
        "specificBusinessType": source.get("specific_business_type"),
        "taxableItemName": source.get("taxable_item_name"),
        "sourceLineText": source.get("source_line_text"),
        "specificationModel": source.get("specification_model"),
        "unit": source.get("unit"),
        "quantity": source.get("quantity"),
        "unitPrice": source.get("unit_price"),
        "amount": source.get("amount"),
        "taxRate": source.get("tax_rate"),
        "taxAmount": source.get("tax_amount"),
        "taxAmountText": source.get("tax_amount_text"),
        "totalWithTax": source.get("total_with_tax"),
        "remark": source.get("remark"),
    }


def invoice_source_detail(group: dict[str, Any]) -> dict[str, Any]:
    primary: Invoice = group["primary"]
    lines: list[Invoice] = list(group["line_items"])
    # A group sum is a business result, not a value printed on a source row.
    single = lines[0] if len(lines) == 1 else None
    payload = {
        "id": primary.id,
        "invoiceIdentityKey": group["identity_key"],
        "invoiceType": primary.invoice_type.value,
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
        "taxAmountText": single.tax_amount_text if single else None,
        "totalWithTax": source_money(single.total_with_tax) if single else "",
        "taxRate": primary.tax_rate if single else invoice_financial_summary(lines)["taxRate"],
        "_sourceLineItems": primary.source_line_items if single else [],
        "taxClassificationCode": primary.tax_classification_code,
        "specificBusinessType": primary.specific_business_type,
        "taxableItemName": primary.taxable_item_name,
        "invoiceSource": primary.invoice_source,
        "invoiceKind": primary.invoice_kind,
        "invoiceKindCode": primary.invoice_kind_code,
        "invoiceKindStatus": primary.invoice_kind_status,
        "invoiceKindEvidence": primary.invoice_kind_evidence,
        "invoiceStatus": primary.invoice_status_from_source,
        "isPositiveInvoice": primary.is_positive_invoice,
        "riskLevel": primary.risk_level,
        "issuer": primary.issuer,
        "remark": primary.remark,
        "lineItems": [invoice_source_line(source, invoice_id=line.id, index=index)
                      for line in lines for index, source in enumerate(line.source_line_items, 1)
                      if source.get("source_sheet_role") != "invoice_header"],
    }
    payload["sections"] = source_detail_sections("invoice", payload)
    return payload


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
    payload = {
        "oaId": record.id, "detailAvailable": True,
        "applicantName": record.applicant, "applicationType": record.apply_type,
        "projectName": record.project_name if payment else None,
        "workflowNo": fields.get("OA单号"), "workflowStatus": fields.get("流程状态"),
        "amount": record.amount if payment or record.detail_fields.get("金额来源") == "主表总金额" else None,
        "reason": record.reason if payment else None,
        "counterpartyName": record.counterparty_name,
        "detailFields": fields, "expenseItems": public_oa_expense_items(record.expense_items),
    }
    payload["sections"] = source_detail_sections("oa", payload)
    return payload


# These are source projections, shared by every page. Identity metadata is used
# for grouping/navigation only and is never rendered as a document field.
SOURCE_FIELD_GROUPS = {
    "bank": (
        ("交易信息", (("transactionDate", "交易日期"), ("bookedDate", "入账日期"), ("amount", "金额"), ("balance", "余额"), ("summary", "摘要"))),
        ("账户信息", (("accountName", "账户名称"), ("accountNo", "账号"), ("counterpartyName", "对方户名"), ("counterpartyAccountNo", "对方账号"), ("counterpartyBankName", "对方开户机构"))),
        ("凭证与备注", (("bankSerialNo", "银行流水号"), ("enterpriseSerialNo", "企业流水号"), ("accountDetailNo", "账户明细编号-交易流水号"), ("voucherKind", "凭证种类"), ("voucherNo", "凭证号"), ("remark", "备注"))),
    ),
    "invoice": (
        ("发票信息", (("digitalInvoiceNo", "数电发票号码"), ("invoiceNo", "发票号码"), ("invoiceCode", "发票代码"), ("invoiceDate", "开票日期"), ("invoiceKind", "发票票种"), ("invoiceKindName", "发票类型"), ("invoiceKindStatusLabel", "票种状态"), ("invoiceSource", "发票来源"), ("invoiceStatus", "发票状态"), ("isPositiveInvoice", "是否正数发票"), ("riskLevel", "发票风险等级"), ("issuer", "开票人"))),
        ("购销双方", (("sellerName", "销方名称"), ("sellerTaxNo", "销方识别号"), ("buyerName", "购买方名称"), ("buyerTaxNo", "购买方识别号"))),
        ("金额与税额", (("amount", "不含税金额"), ("taxRate", "税率"), ("taxAmount", "税额"), ("totalWithTax", "价税合计"), ("financialIssue", "核对说明"))),
        ("业务信息", (("taxClassificationCode", "税收分类编码"), ("specificBusinessType", "特定业务类型"), ("taxableItemName", "货物或应税劳务名称"), ("remark", "备注"))),
    ),
    "oa": (("申请信息", (("applicantName", "申请人"), ("applicationType", "OA类型"), ("projectName", "项目名称"), ("amount", "金额"), ("reason", "申请事由"), ("counterpartyName", "收款方"))),),
}
INVOICE_LINE_FIELDS = (("taxableItemName", "货物或应税劳务名称"), ("sourceLineText", "原文"), ("taxClassificationCode", "税收分类编码"), ("specificBusinessType", "特定业务类型"), ("specificationModel", "规格型号"), ("unit", "单位"), ("quantity", "数量"), ("unitPrice", "单价"), ("amount", "金额"), ("taxRate", "税率"), ("taxAmount", "税额"), ("totalWithTax", "价税合计"), ("financialIssue", "核对说明"), ("remark", "备注"))


def source_detail_sections(kind: str, payload: dict[str, Any]) -> list[dict[str, Any]]:
    if kind == "invoice":
        # Mutate only newly constructed public projections, never canonical/source records.
        for data in [payload, *payload.get("lineItems", [])]:
            values = resolve_invoice_financial_values(
                amount=data.get("amount"), tax_amount=data.get("taxAmount"),
                total_with_tax=data.get("totalWithTax"), tax_rate=data.get("taxRate"),
                tax_amount_text=data.get("taxAmountText"),
                source_line_items=data.pop("_sourceLineItems", []),
            )
            for key, public in PUBLIC_FIELDS.items():
                value = getattr(values, key)
                data[public] = values.rate_label if key == "tax_rate" else source_money(value)
            data["taxAmountText"] = values.tax_amount_text
            if values.issue:
                data["financialIssue"] = values.issue
    if kind not in SOURCE_FIELD_GROUPS:
        raise ValueError(f"Unknown source detail kind: {kind}")
    identifier = str(payload.get("oaId") if kind == "oa" else payload.get("id") or "")
    if kind == "invoice":
        payload["invoiceKindName"] = INVOICE_KIND_NAMES.get(payload.get("invoiceKindCode"))
        payload["invoiceKindStatusLabel"] = {"confirmed": "已确认", "unmapped": "待映射",
            "not_provided": "原件未提供", "unreadable": "未读取", "source_unavailable": "原件不可用",
            "conflict": "来源冲突"}.get(payload.get("invoiceKindStatus"))
        polarity = {"是": "蓝字", "否": "红字", "True": "蓝字", "False": "红字"}.get(str(payload.get("isPositiveInvoice")))
        title_values = (polarity, payload.get("buyerName"), payload.get("totalWithTax"))
    elif kind == "bank":
        title_values = (payload.get("counterpartyName"), payload.get("amount"))
    else:
        title_values = (payload.get("applicantName"), payload.get("amount"))
    title = " · ".join(format(value, "f") if isinstance(value, Decimal) else str(value)
                       for value in title_values if value is not None and value != "")
    metadata = {"document_id": identifier, "document_kind": kind, "document_title": title}
    if kind == "invoice":
        counterparty_key = {"input": "sellerName", "output": "buyerName"}.get(payload.get("invoiceType"))
        metadata["invoice_navigation"] = {
            "polarity": polarity,
            "counterpartyName": payload.get(counterparty_key) if counterparty_key else None,
            "totalWithTax": source_money(payload["totalWithTax"]) if payload.get("totalWithTax") not in (None, "") else None,
            "invoiceDate": str(payload["invoiceDate"]) if payload.get("invoiceDate") else None,
        }
    if kind == "bank":
        metadata["bank_transaction_id"] = identifier
        metadata["bank_navigation"] = {
            "counterpartyName": payload.get("counterpartyName"),
            "amount": source_money(payload["amount"]) if payload.get("amount") not in (None, "") else None,
            "direction": {"inflow": "收入", "outflow": "支出"}.get(payload.get("direction")),
            "transactionDate": str(payload["transactionDate"]) if payload.get("transactionDate") else None,
            "labels": payload.get("bankLabels"),
        }
    if kind == "oa":
        fields = payload.get("detailFields", {})
        metadata["oa_navigation"] = {
            "applicantName": payload.get("applicantName"),
            "amount": source_money(payload["amount"]) if payload.get("amount") not in (None, "") else None,
            "applicationDate": str(fields["申请日期"]) if fields.get("申请日期") else None,
            "workflowNo": str(payload["workflowNo"]) if payload.get("workflowNo") else None,
        }
    sections = []
    def append(title: str, values: Any, fields: Any) -> None:
        projected = []
        for key, label in fields:
            value = values.get(key)
            if kind == "invoice" and key == "taxAmount" and value in (None, ""):
                value = values.get("taxAmountText")
            if value is None or value == "":
                if kind == "invoice" and key in PUBLIC_FIELDS.values():
                    value = "—"
                else:
                    continue
            display = format(value, "f") if isinstance(value, Decimal) else value
            projected.append({"label": label, "value": display})
        if projected:
            sections.append({"title": title, "fields": projected, **metadata})
    for section_title, labels in SOURCE_FIELD_GROUPS[kind]:
        if kind == "bank":
            amount_label = {"inflow": "收入金额", "outflow": "支出金额"}.get(payload.get("direction"), "金额")
            labels = [(key, amount_label if key == "amount" else label) for key, label in labels]
        values = payload
        if kind == "oa":
            values = {**payload, "applicationType": {"payment_request": "支付申请", "expense_claim": "日常报销"}.get(payload.get("applicationType"), payload.get("applicationType"))}
        append(section_title, values, labels)
    if kind == "oa":
        fields = payload.get("detailFields") or {}
        append("单据信息", fields, [(key, key) for key in fields if key in OA_SOURCE_DETAIL_KEYS])
        for index, item in enumerate(payload.get("expenseItems") or [], 1):
            append(f"费用明细 {index}", item, OA_EXPENSE_FIELDS)
    if kind == "invoice":
        for index, item in enumerate(payload.get("lineItems") or [], 1):
            append(f"货物或应税劳务明细 {index}", item, INVOICE_LINE_FIELDS)
    if kind == "bank" and payload.get("bankLabels") is not None:
        sections.append({"title": "业务分类", "fields": [], "bank_labels": payload["bankLabels"], **metadata})
    return sections


def bank_source_detail(transaction: Any, *, labels: list[str] | None = None) -> dict[str, Any]:
    transaction = original_bank_transaction(transaction)
    payload = {
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
        "bankLabels": labels,
    }
    payload["sections"] = source_detail_sections("bank", payload)
    return payload


BANK_SOURCE_KEYS = frozenset({
    "amount", "account_no", "account_name", "counterparty_name_raw",
    "counterparty_name", "counterparty_account_no", "counterparty_bank_name",
    "txn_date", "booked_date", "balance", "summary", "remark", "bank_serial_no",
    "enterprise_serial_no", "voucher_kind", "voucher_no", "account_detail_no",
})
INVOICE_SOURCE_KEYS = frozenset({
    "invoice_no", "invoice_code", "digital_invoice_no", "invoice_date",
    "seller_name", "seller_tax_no", "buyer_name", "buyer_tax_no", "amount",
    "tax_amount", "tax_amount_text", "tax_rate", "total_with_tax", "invoice_status_from_source",
    "invoice_kind", "is_positive_invoice", "risk_level", "issuer", "remark",
    "tax_classification_code", "specific_business_type", "taxable_item_name",
    "specification_model", "unit", "quantity", "unit_price",
    "invoice_source", "source_line_items",
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
        payload = query_source_detail("oa", {"oa_id": row["id"], "applicant": row.get("applicant"),
            "application_type": row.get("apply_type"), "project_name": row.get("project_name"),
            "amount": row.get("amount"), "reason": row.get("reason"), "counterparty_name": row.get("counterparty_name"),
            "detail_fields": fields, "expense_items": row.get("expense_items") or []})
        return {**row, "detail_fields": details, "source_sections": payload["sections"],
                "expense_items": public_oa_expense_items(row.get("expense_items") or [])}
    keys = BANK_SOURCE_KEYS if kind == "bank" else INVOICE_SOURCE_KEYS
    details = {key: value for key, value in fields.items() if key in keys}
    if kind == "bank":
        counterparty = details.pop("counterparty_name_raw", None)
        if counterparty not in (None, "", "unknown", "未知对手方"):
            details["counterparty_name"] = counterparty
    return {**row, "detail_fields": details}


def source_invoice_groups(invoices: list[Invoice]) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Invoice]] = {}
    policy = FinancialObjectIdentityPolicy()
    for invoice in sorted(invoices, key=lambda invoice: invoice.id):
        key = f"{invoice.invoice_type.value}:{policy.legacy_invoice_identity_key(invoice)}"
        grouped.setdefault(key, {})[invoice.id] = invoice
    return [{"identity_key": key, "primary": next(iter(lines.values())), "line_items": list(lines.values())}
            for key, lines in grouped.items()]


def source_relation_sections(kind: str, summaries: list[Any], *, groups: list[dict[str, Any]],
                             transactions: list[Any], oa_records: list[Any], bank_labels: dict[str, list[str]] | None = None) -> list[dict[str, Any]]:
    """Resolve all members against one authorized snapshot; never use summary fields as detail."""
    typed = [item for item in summaries if isinstance(item, dict)]
    if kind == "bank":
        typed = original_bank_summaries(typed)
    sections: list[dict[str, Any]] = []
    seen: set[str] = set()
    banks = {record.id: original_bank_transaction(record) for record in transactions}
    banks.update({record.id: record for record in list(banks.values())})
    oas = {record.id: record for record in oa_records}
    groups = source_invoice_groups([line for group in groups for line in group["line_items"]])
    invoices = {line.id: group for group in groups for line in group["line_items"]}
    for summary in typed:
        key = {"bank": "bankTransactionId", "invoice": "invoiceId", "oa": "oaId"}[kind]
        identifier = str(summary.get(key) or summary.get("id") or "")
        if kind == "bank":
            record = banks.get(identifier)
            payload = bank_source_detail(record, labels=bank_labels[record.id] if bank_labels is not None else None) if record is not None else None
        elif kind == "oa":
            record = oas.get(identifier)
            payload = oa_source_detail(record) if record is not None else None
        else:
            group = invoices.get(identifier)
            payload = invoice_source_detail(group) if group is not None else None
        if payload is None:
            raise ValueError("关联单据原始详情不可用")
        identity = str(payload.get("oaId") if kind == "oa" else payload["id"])
        if identity not in seen:
            seen.add(identity)
            sections.extend(payload["sections"])
    return sections


# Explicit adapters for the existing canonical SQL query DTOs.
QUERY_SOURCE_KEYS = {
    "bank": {"id": "id", "transaction_date": "transactionDate", "booked_date": "bookedDate", "txn_direction": "direction", "amount": "amount", "balance": "balance", "summary": "summary", "remark": "remark", "account_name": "accountName", "account_no": "accountNo", "counterparty_name": "counterpartyName", "counterparty_account_no": "counterpartyAccountNo", "counterparty_bank_name": "counterpartyBankName", "statement_serial_no": "bankSerialNo", "enterprise_serial_no": "enterpriseSerialNo", "voucher_type": "voucherKind", "voucher_no": "voucherNo", "account_detail_no": "accountDetailNo"},
    "invoice": {"id": "id", "invoice_type": "invoiceType", "invoice_no": "invoiceNo", "digital_invoice_no": "digitalInvoiceNo", "invoice_code": "invoiceCode", "issue_date": "invoiceDate", "seller_name": "sellerName", "seller_tax_no": "sellerTaxNo", "buyer_name": "buyerName", "buyer_tax_no": "buyerTaxNo", "amount_without_tax": "amount", "tax_amount": "taxAmount", "tax_amount_text": "taxAmountText", "tax_rate": "taxRate", "total_with_tax": "totalWithTax", "tax_classification_code": "taxClassificationCode", "specific_business_type": "specificBusinessType", "taxable_item_name": "taxableItemName", "invoice_source": "invoiceSource", "invoice_kind": "invoiceKind", "invoice_kind_code": "invoiceKindCode", "invoice_kind_status": "invoiceKindStatus", "invoice_status_from_source": "invoiceStatus", "is_positive_invoice": "isPositiveInvoice", "risk_level": "riskLevel", "issuer": "issuer", "remark": "remark", "model": "specificationModel", "unit": "unit", "quantity": "quantity", "unit_price": "unitPrice"},
}


def query_source_detail(kind: str, row: dict[str, Any]) -> dict[str, Any]:
    if kind == "invoice" and row.get("line_items"):
        lines = sorted(row["line_items"], key=lambda item: item["id"])
        row = {**lines[0], "line_items": lines}
    if kind == "oa":
        fields = row.get("detail_fields") or {}
        payment = row.get("application_type") in {"payment_request", "付款申请", "支付申请"}
        payload = {"oaId": row.get("oa_id"), "applicantName": row.get("applicant"),
                   "applicationType": row.get("application_type"), "detailFields": oa_source_fields(fields),
                   "projectName": row.get("project_name") if payment else None,
                   "amount": row.get("amount") if payment or fields.get("金额来源") == "主表总金额" else None,
                   "reason": row.get("reason") if payment else None, "counterpartyName": row.get("counterparty_name"),
                   "workflowNo": oa_source_fields(fields).get("OA单号"),
                   "expenseItems": public_oa_expense_items(row.get("expense_items") or [])}
    else:
        payload = {target: row.get(source) for source, target in QUERY_SOURCE_KEYS[kind].items()}
        if kind == "bank":
            payload["bankLabels"] = row.get("bank_labels")
        if kind == "bank" and payload.get("amount") in (None, ""):
            if row.get("credit_amount") not in (None, "") and row.get("debit_amount") in (None, ""):
                payload.update(amount=row["credit_amount"], direction="inflow")
            elif row.get("debit_amount") not in (None, "") and row.get("credit_amount") in (None, ""):
                payload.update(amount=row["debit_amount"], direction="outflow")
        if kind == "invoice":
            payload["_sourceLineItems"] = row.get("source_line_items") or []
            lines = row.get("line_items") or [row]
            payload["lineItems"] = [
                invoice_source_line(source, invoice_id=line["id"], index=index)
                for line in lines for index, source in enumerate(line.get("source_line_items") or [], 1)
                if source.get("source_sheet_role") != "invoice_header"
            ]
            if len(lines) > 1:
                payload["taxRate"] = combine_invoice_tax_rates(resolve_invoice_financial_values(
                    amount=line.get("amount_without_tax"), tax_amount=line.get("tax_amount"),
                    total_with_tax=line.get("total_with_tax"), tax_rate=line.get("tax_rate"),
                    tax_amount_text=line.get("tax_amount_text"), source_line_items=line.get("source_line_items") or [],
                ).tax_rate for line in lines)
                payload["_sourceLineItems"] = []
                payload["taxAmountText"] = None
                for key in ("amount", "taxAmount", "totalWithTax"):
                    payload[key] = None
    for data in [payload, *payload.get("lineItems", [])]:
        for key in ("amount", "balance", "taxAmount", "totalWithTax"):
            if data.get(key) not in (None, ""):
                data[key] = source_money(data[key])
    payload["sections"] = source_detail_sections(kind, payload)
    return payload


def query_invoice_sections(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[Any, ...], list[dict[str, Any]]] = {}
    for row in rows:
        key = ("digital", row["digital_invoice_no"]) if row.get("digital_invoice_no") else (
            ("paper", row["invoice_code"], row["invoice_no"]) if row.get("invoice_code") and row.get("invoice_no") else ("id", row["id"]))
        grouped.setdefault((row.get("invoice_type"), *key), []).append(row)
    return [section for lines in grouped.values()
            for section in query_source_detail("invoice", {**lines[0], "line_items": lines})["sections"]]
