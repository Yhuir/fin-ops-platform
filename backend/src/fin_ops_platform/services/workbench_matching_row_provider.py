from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.oa_attachment_invoice_linking import oa_attachment_best_source_link
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAProjectionAdapter,
    PostgresOAProjectionRepository,
)
from fin_ops_platform.services.workbench_query_service import (
    OA_ATTACHMENT_INVOICE_SOURCE_KIND,
    WorkbenchQueryService,
)


class WorkbenchMatchingRowProvider:
    def __init__(
        self,
        *,
        connection: Any,
        oa_query_service: WorkbenchQueryService | None = None,
        bank_account_resolver: BankAccountResolver | None = None,
    ) -> None:
        self._connection = connection
        self._bank_account_mapping_cache: dict[str, str] | None = None
        self._bank_account_resolver = bank_account_resolver or BankAccountResolver(self._bank_account_mapping_dict)
        if oa_query_service is not None:
            self._oa_query_service = oa_query_service
        else:
            repository = PostgresOAProjectionRepository(connection)
            self._oa_query_service = WorkbenchQueryService(
                oa_adapter=PostgresOAProjectionAdapter(repository),
                seed_demo_rows=False,
            )

    def rows_for_scope(self, scope_month: str) -> dict[str, list[dict[str, object]]]:
        month = str(scope_month or "").strip()
        return {
            "oa_rows": self._oa_projection_rows(month),
            "bank_rows": self._bank_rows(month),
            "invoice_rows": self._invoice_rows(month),
        }

    def _bank_account_mapping_dict(self) -> dict[str, str]:
        if self._bank_account_mapping_cache is not None:
            return dict(self._bank_account_mapping_cache)
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            ("app_settings",),
        )
        payload = row_payload(row, "settings_payload")
        settings = payload if isinstance(payload, dict) else {}
        mappings: dict[str, str] = {}
        for item in list(settings.get("bank_account_mappings") or []):
            if not isinstance(item, dict):
                continue
            last4 = str(item.get("last4") or "").strip()
            bank_name = str(item.get("bank_name") or "").strip()
            if len(last4) == 4 and last4.isdigit() and bank_name:
                mappings[last4] = bank_name
        self._bank_account_mapping_cache = mappings
        return dict(mappings)

    def _oa_projection_rows(self, month: str) -> list[dict[str, Any]]:
        self._oa_query_service.get_workbench(month)
        result: list[dict[str, Any]] = []
        for row in self._oa_query_service.list_record_snapshots():
            if str(row.get("_month") or "").strip() != month:
                continue
            row_type = str(row.get("type") or "").strip()
            if row_type != "oa":
                continue
            payload = self._oa_query_service.serialize_row(row)
            payload["status"] = "open"
            payload.setdefault("source_kind", payload.get("type") or row_type)
            result.append(payload)
        return result

    def _bank_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, account_no, account_name,
                   txn_direction, counterparty_name_raw, amount, txn_date, trade_time,
                   summary, remark, project_id, raw_payload
            from app.bank_transactions
            where txn_month = %s::date
              and status <> 'deleted'
            order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
            """,
            (month_start(month),),
        )
        return [payload for row in rows if (payload := self._bank_row_from_sql(row))]

    def _bank_row_from_sql(self, row: dict[str, Any]) -> dict[str, Any] | None:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            return None
        amount = row.get("amount")
        direction = str(row.get("txn_direction") or "")
        debit_amount = amount if _is_outflow(direction, None) else None
        credit_amount = amount if not _is_outflow(direction, None) else None
        account_no = str(row.get("account_no") or "")
        account_name = str(row.get("account_name") or "")
        payment_account_label = self._bank_account_resolver.resolve_label(account_no, account_name)
        detail_fields = row_payload(row, "raw_payload")
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        return {
            "id": row_id,
            "type": "bank",
            "source_kind": "bank",
            "status": "open",
            "case_id": None,
            "trade_time": _date_text(row.get("trade_time") or row.get("txn_date")),
            "account_no": account_no,
            "account_name": account_name,
            "debit_amount": str(debit_amount or "") or None,
            "credit_amount": str(credit_amount or "") or None,
            "counterparty_name": row.get("counterparty_name_raw"),
            "payment_account_label": payment_account_label,
            "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
            "pay_receive_time": _date_text(row.get("trade_time") or row.get("txn_date")),
            "summary": row.get("summary"),
            "remark": row.get("remark"),
            "project_id": row.get("project_id"),
            "available_actions": ["detail", "view_relation", "cancel_link", "handle_exception"],
            "summary_fields": {
                "交易时间": _date_text(row.get("trade_time") or row.get("txn_date")),
                "借方发生额": str(debit_amount or "") or "—",
                "贷方发生额": str(credit_amount or "") or "—",
                "对方户名": row.get("counterparty_name_raw") or "—",
                "支付账户": payment_account_label or "—",
                "和发票关联情况": "待关联发票",
                "支付/收款时间": _date_text(row.get("trade_time") or row.get("txn_date")),
                "备注": row.get("remark") or "—",
            },
            "detail_fields": detail_fields,
        }

    def _invoice_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            f"""
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
                   digital_invoice_no, invoice_date, counterparty_name, seller_name, seller_tax_no,
                   buyer_name, buyer_tax_no, amount, tax_rate, tax_amount, total_with_tax, status,
                   workbench_visibility, tags, source_links, raw_payload
            from app.invoices invoices
            where invoices.invoice_month = %s::date
              and invoices.status <> 'deleted'
              and coalesce(invoices.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
              and coalesce(invoices.raw_payload->'normalized_payload'->>'workbench_visibility', 'visible') <> 'hidden_after_etc_submission'
              and coalesce(invoices.raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
              {_submitted_etc_overlap_exclusion_sql("invoices")}
            order by invoice_date desc nulls last, row_id
            """,
            (month_start(month),),
        )
        return [payload for row in rows if (payload := self._invoice_row_from_sql(row))]

    def _invoice_row_from_sql(self, row: dict[str, Any]) -> dict[str, Any] | None:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            return None
        detail_fields = row_payload(row, "raw_payload")
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        if _invoice_hidden_after_etc_submission(row, detail_fields):
            return None
        source_links = _list_of_dicts(row.get("source_links") if isinstance(row.get("source_links"), list) else detail_fields.get("source_links"))
        oa_attachment_source_link = _first_source_link(source_links, "oa_attachment_invoice")
        source_kind = OA_ATTACHMENT_INVOICE_SOURCE_KIND if oa_attachment_source_link is not None else "invoice"
        tags = _text_list(row.get("tags"))
        if _first_source_link(source_links, "manual_invoice_import") is not None and "人工导入" not in tags:
            tags.append("人工导入")
        if source_kind == OA_ATTACHMENT_INVOICE_SOURCE_KIND and "OA附件" not in tags:
            tags.append("OA附件")
        invoice_code = _first_display_value(row.get("invoice_code"), detail_fields.get("发票代码"))
        invoice_no = _first_display_value(row.get("invoice_no"), detail_fields.get("发票号码"))
        digital_invoice_no = _first_display_value(row.get("digital_invoice_no"), detail_fields.get("数电发票号码"))
        tax_rate = _first_display_value(row.get("tax_rate"), detail_fields.get("税率"), detail_fields.get("tax_rate"))
        tax_amount = _first_display_value(row.get("tax_amount"), detail_fields.get("税额"), detail_fields.get("tax_amount"))
        return {
            "id": row_id,
            "type": "invoice",
            "source_kind": source_kind,
            "status": "open",
            "case_id": None,
            "invoice_type": row.get("invoice_type"),
            "invoice_no": invoice_no,
            "invoice_code": invoice_code,
            "digital_invoice_no": digital_invoice_no,
            "issue_date": _date_text(row.get("invoice_date")),
            "counterparty_name": row.get("counterparty_name") or row.get("seller_name") or row.get("buyer_name"),
            "seller_name": row.get("seller_name"),
            "seller_tax_no": row.get("seller_tax_no"),
            "buyer_name": row.get("buyer_name"),
            "buyer_tax_no": row.get("buyer_tax_no"),
            "amount": str(row.get("amount") or ""),
            "tax_rate": tax_rate,
            "tax_amount": tax_amount,
            "total_with_tax": str(row.get("total_with_tax") or row.get("amount") or ""),
            "invoice_bank_relation": {"code": "pending_collection", "label": "待匹配流水", "tone": "warn"},
            "tags": tags,
            "source_links": source_links,
            "derived_from_oa_id": _metadata_value(oa_attachment_source_link, detail_fields, "derived_from_oa_id"),
            "source_workbench_row_id": _metadata_value(oa_attachment_source_link, detail_fields, "source_workbench_row_id"),
            "source_attachment_key": _metadata_value(oa_attachment_source_link, detail_fields, "source_attachment_key"),
            "source_attachment_name": _metadata_value(oa_attachment_source_link, detail_fields, "source_attachment_name"),
            "source_expense_item_id": _metadata_value(oa_attachment_source_link, detail_fields, "source_expense_item_id"),
            "source_expense_row_index": _metadata_value(oa_attachment_source_link, detail_fields, "source_expense_row_index"),
            "available_actions": ["detail", "confirm_link", "mark_exception", "ignore"],
            "summary_fields": {
                "销方识别号": row.get("seller_tax_no") or "—",
                "销方名称": row.get("seller_name") or "—",
                "购方识别号": row.get("buyer_tax_no") or "—",
                "购买方名称": row.get("buyer_name") or "—",
                "开票日期": _date_text(row.get("invoice_date")),
                "金额": str(row.get("amount") or "—"),
                "税率": tax_rate,
                "税额": tax_amount,
                "价税合计": str(row.get("total_with_tax") or row.get("amount") or "—"),
                "发票类型": row.get("invoice_type") or "—",
                "发票来源": "OA附件解析" if source_kind == OA_ATTACHMENT_INVOICE_SOURCE_KIND else ("人工导入" if "人工导入" in tags else "—"),
            },
            "detail_fields": detail_fields,
        }


def _submitted_etc_overlap_exclusion_sql(invoice_alias: str) -> str:
    return f"""
          and not exists (
              select 1
              from app.etc_batch_invoice_links etc_batch_invoice_links
              where etc_batch_invoice_links.link_status = 'active'
                and etc_batch_invoice_links.invoice_id = {invoice_alias}.id
          )
          and not exists (
              select 1
              from app.etc_invoices etc_invoices
              left join app.etc_business_batches etc_business_batches
                on etc_business_batches.business_batch_id = etc_invoices.business_batch_id
              where (
                      (
                          nullif(coalesce({invoice_alias}.digital_invoice_no, {invoice_alias}.invoice_no), '') is not null
                      and etc_invoices.invoice_no = coalesce({invoice_alias}.digital_invoice_no, {invoice_alias}.invoice_no)
                      )
                   or (
                          nullif({invoice_alias}.invoice_code, '') is not null
                      and nullif({invoice_alias}.invoice_no, '') is not null
                      and etc_invoices.invoice_code = {invoice_alias}.invoice_code
                      and etc_invoices.invoice_no = {invoice_alias}.invoice_no
                      )
              )
                and (
                      etc_business_batches.status in ('oa_submitted', 'manually_marked_submitted', 'closed')
                   or (
                          etc_invoices.status = 'submitted'
                      and coalesce(etc_business_batches.status, '') <> 'deleted'
                      )
                )
          )
    """


def _invoice_hidden_after_etc_submission(row: dict[str, Any], payload: dict[str, Any]) -> bool:
    return (
        str(row.get("workbench_visibility") or payload.get("workbench_visibility") or "").strip()
        == "hidden_after_etc_submission"
        or str(payload.get("etc_submission_status") or "").strip() == "submitted"
    )


def _date_text(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value or "")[:19]


def _first_display_value(*values: object) -> str:
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in {"—", "--"}:
            return normalized
    return "—"


def _text_or_none(value: object) -> str | None:
    if value is None:
        return None
    normalized = str(value).strip()
    if not normalized or normalized in {"—", "--", "None"}:
        return None
    return normalized


def _text_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    seen: set[str] = set()
    for item in value:
        normalized = _text_or_none(item)
        if normalized is None or normalized in seen:
            continue
        seen.add(normalized)
        result.append(normalized)
    return result


def _list_of_dicts(value: object) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [dict(item) for item in value if isinstance(item, dict)]


def _first_source_link(source_links: list[dict[str, Any]], source_type: str) -> dict[str, Any] | None:
    return oa_attachment_best_source_link(source_links, source_type)


def _metadata_value(source_link: dict[str, Any] | None, detail_fields: dict[str, Any], key: str) -> str | None:
    if source_link is not None:
        value = _text_or_none(source_link.get(key))
        if value is not None:
            return value
    return _text_or_none(detail_fields.get(key))


def _decimal_or_none(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _is_outflow(direction: str, signed_amount: object) -> bool:
    normalized_direction = str(direction or "").strip().lower()
    if any(token in normalized_direction for token in ("支出", "付款", "out", "debit")):
        return True
    if any(token in normalized_direction for token in ("收入", "收款", "in", "credit")):
        return False
    parsed = _decimal_or_none(signed_amount)
    return parsed is None or parsed < 0
