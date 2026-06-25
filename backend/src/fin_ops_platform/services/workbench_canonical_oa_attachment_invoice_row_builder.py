from __future__ import annotations

from typing import Callable


class WorkbenchCanonicalOaAttachmentInvoiceRowBuilder:
    """Builds canonical Workbench invoice rows for OA attachment invoices."""

    def __init__(
        self,
        *,
        money_text: Callable[[object], str],
        first_month_from_oa_row: Callable[[dict[str, object]], str | None],
        output_invoice_type_value: object,
    ) -> None:
        self._money_text = money_text
        self._first_month_from_oa_row = first_month_from_oa_row
        self._output_invoice_type_value = output_invoice_type_value

    def build(
        self,
        invoice: object,
        *,
        source_link: dict[str, str],
        oa_row: dict[str, object],
    ) -> dict[str, object]:
        source_links = [
            {str(key): str(value) for key, value in link.items() if value is not None}
            for link in list(getattr(invoice, "source_links", []) or [])
            if isinstance(link, dict)
        ]
        tags = [
            str(tag).strip()
            for tag in list(getattr(invoice, "tags", []) or [])
            if str(tag).strip()
        ]
        if any(str(link.get("source_type") or "").strip() == "manual_invoice_import" for link in source_links):
            self._append_unique_text(tags, "人工导入")
        self._append_unique_text(tags, "OA附件")

        invoice_type_label = (
            "销项发票"
            if getattr(getattr(invoice, "invoice_type", None), "value", getattr(invoice, "invoice_type", None))
            == self._output_invoice_type_value
            else "进项发票"
        )
        invoice_no = str(getattr(invoice, "invoice_no", "") or "").strip() or "—"
        digital_invoice_no = str(getattr(invoice, "digital_invoice_no", "") or "").strip() or "—"
        invoice_code = str(getattr(invoice, "invoice_code", "") or "").strip() or "—"
        issue_date = str(getattr(invoice, "invoice_date", "") or "").strip() or "—"
        seller_name = str(getattr(invoice, "seller_name", "") or "").strip()
        buyer_name = str(getattr(invoice, "buyer_name", "") or "").strip()
        counterparty_name = str(getattr(getattr(invoice, "counterparty", None), "name", "") or "").strip()
        amount_text = self._money_text(getattr(invoice, "amount", None))
        tax_amount_text = self._money_text(getattr(invoice, "tax_amount", None))
        total_with_tax_text = self._money_text(
            getattr(invoice, "total_with_tax", None) if getattr(invoice, "total_with_tax", None) is not None else getattr(invoice, "amount", None)
        )
        source_oa_no = self._oa_display_number_for_attachment_invoice(oa_row)
        detail_fields = {
            "序号": str(getattr(invoice, "id", "") or ""),
            "发票代码": invoice_code,
            "发票号码": invoice_no,
            "数电发票号码": digital_invoice_no,
            "销方识别号": str(getattr(invoice, "seller_tax_no", "") or "—"),
            "销方名称": seller_name or "—",
            "购方识别号": str(getattr(invoice, "buyer_tax_no", "") or "—"),
            "购买方名称": buyer_name or "—",
            "开票日期": issue_date,
            "金额": amount_text,
            "税率": str(getattr(invoice, "tax_rate", "") or "—"),
            "税额": tax_amount_text,
            "价税合计": total_with_tax_text,
            "发票类型": invoice_type_label,
            "税收分类编码": str(getattr(invoice, "tax_classification_code", "") or "—"),
            "特定业务类型": str(getattr(invoice, "specific_business_type", "") or "—"),
            "货物或应税劳务名称": str(getattr(invoice, "taxable_item_name", "") or "—"),
            "规格型号": str(getattr(invoice, "specification_model", "") or "—"),
            "单位": str(getattr(invoice, "unit", "") or "—"),
            "数量": self._money_text(getattr(invoice, "quantity", None)),
            "单价": self._money_text(getattr(invoice, "unit_price", None)),
            "发票来源": str(getattr(invoice, "invoice_source", "") or "OA附件解析"),
            "发票票种": str(getattr(invoice, "invoice_kind", "") or "—"),
            "发票状态": str(getattr(invoice, "invoice_status_from_source", "") or "—"),
            "是否正数发票": str(getattr(invoice, "is_positive_invoice", "") or "—"),
            "发票风险等级": str(getattr(invoice, "risk_level", "") or "—"),
            "开票人": str(getattr(invoice, "issuer", "") or "—"),
            "备注": str(getattr(invoice, "remark", "") or "—"),
            "标签": "、".join(tags) or "—",
            "来源OA单号": source_oa_no,
            "来源付款项ID": str(source_link.get("source_expense_item_id") or "—"),
            "来源附件Key": str(source_link.get("source_attachment_key") or "—"),
            "附件文件名": str(source_link.get("source_attachment_name") or "—"),
        }
        derived_from_oa_id = str(source_link.get("derived_from_oa_id") or getattr(invoice, "oa_form_id", "") or "").strip()
        return {
            "id": str(getattr(invoice, "id", "") or ""),
            "type": "invoice",
            "source_kind": "oa_attachment_invoice",
            "status": "open",
            "case_id": None,
            "seller_tax_no": str(getattr(invoice, "seller_tax_no", "") or ""),
            "seller_name": seller_name or counterparty_name,
            "buyer_tax_no": str(getattr(invoice, "buyer_tax_no", "") or ""),
            "buyer_name": buyer_name,
            "invoice_code": invoice_code,
            "invoice_no": invoice_no,
            "digital_invoice_no": digital_invoice_no,
            "issue_date": issue_date,
            "counterparty_name": counterparty_name or seller_name or buyer_name,
            "amount": amount_text,
            "tax_rate": str(getattr(invoice, "tax_rate", "") or "—"),
            "tax_amount": tax_amount_text,
            "total_with_tax": total_with_tax_text,
            "invoice_type": invoice_type_label,
            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
            "tags": tags,
            "source_links": source_links,
            "derived_from_oa_id": derived_from_oa_id,
            "source_workbench_row_id": str(source_link.get("source_workbench_row_id") or ""),
            "source_attachment_key": str(source_link.get("source_attachment_key") or ""),
            "source_attachment_name": str(source_link.get("source_attachment_name") or ""),
            "source_expense_item_id": str(source_link.get("source_expense_item_id") or ""),
            "source_expense_row_index": str(source_link.get("source_expense_row_index") or ""),
            "source_region_key": str(source_link.get("source_region_key") or ""),
            "evidence_type": str(source_link.get("evidence_type") or ""),
            "document_kind": str(source_link.get("document_kind") or ""),
            "source_oa_month": self._first_month_from_oa_row(oa_row) or "",
            "available_actions": ["detail", "confirm_link", "mark_exception", "ignore"],
            "summary_fields": {
                "销方识别号": str(getattr(invoice, "seller_tax_no", "") or "—"),
                "销方名称": seller_name or "—",
                "购方识别号": str(getattr(invoice, "buyer_tax_no", "") or "—"),
                "购买方名称": buyer_name or "—",
                "开票日期": issue_date,
                "金额": amount_text,
                "税率": str(getattr(invoice, "tax_rate", "") or "—"),
                "税额": tax_amount_text,
                "价税合计": total_with_tax_text,
                "发票类型": invoice_type_label,
                "发票来源": "OA附件解析",
            },
            "detail_fields": detail_fields,
        }

    @staticmethod
    def _append_unique_text(values: list[str], value: str) -> None:
        if value and value not in values:
            values.append(value)

    @staticmethod
    def _oa_display_number_for_attachment_invoice(oa_row: dict[str, object]) -> str:
        for fields_key in ("detail_fields", "summary_fields"):
            fields = oa_row.get(fields_key)
            if isinstance(fields, dict):
                for key in ("OA单号", "单据编号", "申请单号"):
                    value = str(fields.get(key) or "").strip()
                    if value:
                        return value
        return str(oa_row.get("id") or "—")
