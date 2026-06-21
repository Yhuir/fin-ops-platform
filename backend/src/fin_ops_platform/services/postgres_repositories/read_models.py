from __future__ import annotations

from copy import deepcopy
from datetime import date
from datetime import datetime
from decimal import Decimal, InvalidOperation
import json
import logging
import re
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_COUNT_KEYS
from fin_ops_platform.services.pending_invoice_status import pending_invoice_filter_status_codes
from fin_ops_platform.services.postgres_repositories.common import (
    decimal_text,
    int_value,
    iter_mapping,
    jsonb,
    month_start,
    row_payload,
    run_in_transaction,
    serialize_value,
    text,
    text_list,
    without_keys,
)
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.workbench_candidate_match_service import CANDIDATE_MATCH_SCHEMA_VERSION

MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
BANK_DETAIL_READ_MODEL_SCHEMA_VERSION = 8
BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION = 1
BANK_DETAIL_PURPOSE_TEXT_LABELS = ("用途", "交易用途")
BANK_DETAIL_SUMMARY_TEXT_LABELS = ("摘要",)
BANK_DETAIL_NOTE_TEXT_LABELS = ("备注", "附言", "客户附言")
WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION = "workbench_sql_projection.aggregate.v2"
WORKBENCH_PANES = ("oa", "bank", "invoice")
WORKBENCH_FILTER_PLACEHOLDERS = {"", "--", "—"}
NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND = "no_oa_bank_batch_summary"
WORKBENCH_GENERATION_RETENTION_KEEP_RECENT = 3
WORKBENCH_GENERATION_RETENTION_KEEP_DAYS = 1
WORKBENCH_GENERATION_RETENTION_LIMIT = 100
LOGGER = logging.getLogger(__name__)


def _parse_postgres_timestamp(value: str | None) -> datetime | None:
    normalized = str(value or "").strip()
    if not normalized:
        return None
    if normalized.endswith("Z"):
        normalized = normalized[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None


def _execute_many(connection: Any, sql: str, params_seq: list[tuple[Any, ...]]) -> int:
    if not params_seq:
        return 0
    execute_many_values = getattr(connection, "execute_many_values", None)
    if callable(execute_many_values) and _should_execute_many_values(sql):
        return int(execute_many_values(sql, params_seq) or 0)
    execute_many = getattr(connection, "execute_many", None)
    if callable(execute_many):
        return int(execute_many(sql, params_seq) or 0)
    affected = 0
    for params in params_seq:
        affected += int(connection.execute(sql, params) or 0)
    return affected


def _should_execute_many_values(sql: str) -> bool:
    normalized = " ".join(str(sql or "").lower().split())
    return (
        "insert into read_model.workbench_group_rows" in normalized
        or "insert into read_model.search_index_rows" in normalized
    )


WORKBENCH_ALLOWED_FILTER_COLUMNS = {
    "oa": {"applicant", "projectName", "applicationType", "counterparty", "reconciliationStatus"},
    "bank": {"counterparty", "amount", "direction", "paymentAccount", "invoiceRelationStatus", "loanRepaymentDate"},
    "invoice": {"sellerName", "buyerName", "invoiceType"},
}
_TAX_OFFSET_ITEM_TYPES = {
    "output_items": "output",
    "input_plan_items": "input_plan",
    "certified_items": "certified",
    "certified_matched_rows": "certified_matched",
    "certified_outside_plan_rows": "certified_outside",
}
_TAX_OFFSET_PAYLOAD_KEYS = {item_type: payload_key for payload_key, item_type in _TAX_OFFSET_ITEM_TYPES.items()}
PENDING_INVOICE_FILTER_FIELDS = {
    "trade_date": {"between"},
    "bank_name": {"in", "contains"},
    "account_name": {"in", "contains"},
    "bank_account": {"in", "contains"},
    "counterparty_name": {"contains", "in"},
    "transaction_tag": {"contains", "in"},
    "direction": {"in"},
    "amount": {"between", "eq"},
    "summary_remark": {"contains"},
    "status_code": {"in"},
    "rule_group": {"in"},
    "seller_name": {"contains", "in"},
    "invoice_total": {"between", "eq"},
    "oa_applicant": {"contains", "in"},
    "oa_application_type": {"contains", "in"},
    "project_name": {"contains", "in"},
}
PENDING_INVOICE_SORT_EXPRESSIONS = {
    "trade_date": "trade_date",
    "amount": "amount",
    "counterparty_name": "counterparty_name",
    "status_code": "status_code",
    "seller_name": "seller_name",
    "invoice_total": "invoice_total",
    "oa_applicant": "oa_applicant",
    "project_name": "project_name",
}
INPUT_INVOICE_USAGE_FILTER_FIELDS = {
    "invoice_no": ("invoice_no", "text", {"contains", "equals"}),
    "invoice_date": ("invoice_date", "date", {"between", "equals"}),
    "seller_name": ("seller_name", "text", {"contains", "in"}),
    "seller_tax_no": ("seller_tax_no", "text", {"contains", "equals"}),
    "total_with_tax": ("total_with_tax", "money", {"between", "equals"}),
    "amount": ("amount", "money", {"between", "equals"}),
    "tax_rate": ("tax_rate", "text", {"in"}),
    "tax_amount": ("tax_amount", "money", {"between", "equals"}),
    "specific_business_type": ("specific_business_type", "text", {"in"}),
    "taxable_item_name": ("taxable_item_name", "text", {"contains", "in"}),
    "payment_status": ("payment_status", "text", {"in"}),
    "oa_applicant": ("oa_applicant", "text", {"contains", "in"}),
    "oa_application_type": ("oa_application_type", "text", {"equals", "in"}),
    "oa_workflow_status": ("oa_workflow_status", "text", {"equals", "in"}),
    "oa_project_name": ("oa_project_name", "text", {"contains", "in"}),
    "bank_counterparty_name": ("bank_counterparty_name", "text", {"contains", "in"}),
    "bank_trade_time": ("bank_trade_time", "date", {"between", "equals"}),
    "bank_amount": ("bank_amount", "money", {"between", "equals"}),
    "bank_name": ("bank_name", "text", {"in"}),
    "bank_account": ("bank_account", "text", {"in"}),
    "bank_direction": ("bank_direction", "text", {"in"}),
    "bank_summary": ("bank_summary", "text", {"contains"}),
}
INPUT_INVOICE_USAGE_SORT_EXPRESSIONS = {
    field: expression
    for field, (expression, _mode, _operators) in INPUT_INVOICE_USAGE_FILTER_FIELDS.items()
    if field != "specific_business_type"
}
OUTPUT_INVOICE_COLLECTION_FILTER_FIELDS = {
    "invoice_no": ("invoice_no", "text", {"contains", "equals"}),
    "invoice_date": ("invoice_date", "date", {"between", "equals"}),
    "buyer_name": ("buyer_name", "text", {"contains", "in"}),
    "buyer_tax_no": ("buyer_tax_no", "text", {"contains", "equals"}),
    "seller_name": ("seller_name", "text", {"contains", "in"}),
    "total_with_tax": ("total_with_tax", "money", {"between", "equals"}),
    "tax_amount": ("tax_amount", "money", {"between", "equals"}),
    "tax_rate": ("tax_rate", "text", {"in"}),
    "specific_business_type": ("specific_business_type", "text", {"in"}),
    "taxable_item_name": ("taxable_item_name", "text", {"contains", "in"}),
    "collection_status": ("collection_status", "text", {"in"}),
    "pending_amount": ("pending_amount", "money", {"between", "equals"}),
    "bank_counterparty_name": ("bank_counterparty_name", "text", {"contains", "in"}),
    "bank_trade_time": ("bank_trade_time", "date", {"between", "equals"}),
    "bank_amount": ("bank_amount", "money", {"between", "equals"}),
    "bank_name": ("bank_name", "text", {"in"}),
    "bank_summary": ("bank_summary", "text", {"contains"}),
    "receipt_status": ("receipt_status", "text", {"in"}),
}
OUTPUT_INVOICE_COLLECTION_SORT_EXPRESSIONS = {
    field: expression
    for field, (expression, _mode, _operators) in OUTPUT_INVOICE_COLLECTION_FILTER_FIELDS.items()
    if field != "specific_business_type"
}
OA_PENDING_PAYMENT_FILTER_FIELDS = {
    "oa_applicant": ("oa_applicant", "text", {"contains", "in"}),
    "oa_application_type": ("oa_application_type", "text", {"equals", "in"}),
    "oa_project_name": ("oa_project_name", "text", {"contains", "in"}),
    "oa_amount": ("oa_amount", "money", {"between", "equals"}),
    "payment_status": ("payment_status", "text", {"in"}),
    "bank_trade_time": ("bank_trade_time", "date", {"between", "equals"}),
    "bank_name": ("bank_name", "text", {"contains", "in"}),
    "bank_account": ("bank_account", "text", {"in"}),
    "bank_direction": ("bank_direction", "text", {"in"}),
    "bank_counterparty_name": ("bank_counterparty_name", "text", {"contains", "in"}),
    "bank_summary": ("bank_summary", "text", {"contains"}),
    "invoice_no": ("invoice_no", "text", {"contains", "equals"}),
    "seller_name": ("seller_name", "text", {"contains", "in"}),
    "invoice_date": ("invoice_date", "date", {"between", "equals"}),
    "invoice_total_with_tax": ("invoice_total_with_tax", "money", {"between", "equals"}),
}
OA_PENDING_PAYMENT_SORT_EXPRESSIONS = {
    field: expression
    for field, (expression, _mode, _operators) in OA_PENDING_PAYMENT_FILTER_FIELDS.items()
}


class PostgresReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def search_index(
        self,
        *,
        q: str,
        scope: str,
        month: str,
        project_name: str | None,
        status: str | None,
        limit: int,
    ) -> dict[str, Any] | None:
        query = str(q or "").strip()
        resolved_scope = str(scope or "all").strip() or "all"
        resolved_month = str(month or "all").strip() or "all"
        resolved_limit = max(1, min(int_value(limit, 20), 100))
        if not query:
            return _empty_search_payload(query, resolved_scope, resolved_month, project_name, status, resolved_limit)
        where = ["searchable_text ilike %s"]
        params: list[Any] = [f"%{query}%"]
        if resolved_scope != "all":
            where.append("source_kind = %s")
            params.append(resolved_scope)
        if resolved_month != "all":
            where.append("scope_month = %s::date")
            params.append(month_start(resolved_month))
        if status:
            where.append("status = %s")
            params.append(status)
        if project_name:
            where.append("project_name ilike %s")
            params.append(f"%{project_name}%")
        params.append(resolved_limit * 3)
        rows = self._connection.fetch_all(
            f"""
            select source_kind, source_versions, payload, raw_payload
            from read_model.search_index_rows
            where {" and ".join(where)}
            order by generated_at desc, row_id
            limit %s
            """,
            tuple(params),
        )
        if not rows:
            return None
        grouped = {"oa": [], "bank": [], "invoice": []}
        source_versions: dict[str, Any] = {}
        for row in rows:
            if not source_versions and isinstance(row.get("source_versions"), dict):
                source_versions = dict(row.get("source_versions"))
            source_kind = text(row.get("source_kind")) or ""
            if source_kind not in grouped or len(grouped[source_kind]) >= resolved_limit:
                continue
            payload = _read_model_payload(row)
            if isinstance(payload, dict):
                grouped[source_kind].append(payload)
        result = {
            "query": query,
            "filters": {
                "scope": resolved_scope,
                "month": resolved_month,
                "project_name": project_name or None,
                "status": status or None,
                "limit": resolved_limit,
            },
            "summary": {
                "total": len(grouped["oa"]) + len(grouped["bank"]) + len(grouped["invoice"]),
                "oa": len(grouped["oa"]),
                "bank": len(grouped["bank"]),
                "invoice": len(grouped["invoice"]),
            },
            "oa_results": grouped["oa"],
            "bank_results": grouped["bank"],
            "invoice_results": grouped["invoice"],
            "refresh_status": self._refresh_status(scope_type="search", scope_key=resolved_month),
            "source_versions": source_versions,
        }
        return result

    def save_search_index_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        scope_month = month_start(scope_key)
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if scope_month is not None:
                connection.execute("delete from read_model.search_index_rows where scope_month = %s::date", (scope_month,))
            params_by_row_id: dict[str, tuple[Any, ...]] = {}
            for row in list(rows or []):
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["source_versions"] = normalized_source_versions
                payload = serialize_value(row_payload.get("payload") if isinstance(row_payload.get("payload"), dict) else row_payload)
                row_id = text(row_payload.get("row_id") or payload.get("row_id"))
                if not row_id:
                    continue
                params_by_row_id[row_id] = (
                    row_id,
                    text(row_payload.get("source_kind") or payload.get("record_type")),
                    scope_month or month_start(payload.get("month")),
                    text(row_payload.get("status") or payload.get("zone_hint")),
                    text(row_payload.get("title") or payload.get("title")),
                    text(row_payload.get("subtitle") or payload.get("secondary_meta")),
                    text(row_payload.get("searchable_text")),
                    text(row_payload.get("project_name")),
                    text(row_payload.get("counterparty_name")),
                    decimal_text(row_payload.get("amount")),
                    jsonb(normalized_source_versions),
                    text(row_payload.get("generated_at")),
                    jsonb(payload),
                    jsonb({"normalized_payload": payload}),
                )
            params_seq = list(params_by_row_id.values())
            _execute_many(
                connection,
                """
                insert into read_model.search_index_rows(
                    row_id, source_kind, scope_month, status, title, subtitle, searchable_text,
                    project_name, counterparty_name, amount, source_versions, generated_at, payload, raw_payload
                )
                values (%s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s)
                on conflict (row_id) do update set
                    source_kind = excluded.source_kind,
                    scope_month = excluded.scope_month,
                    status = excluded.status,
                    title = excluded.title,
                    subtitle = excluded.subtitle,
                    searchable_text = excluded.searchable_text,
                    project_name = excluded.project_name,
                    counterparty_name = excluded.counterparty_name,
                    amount = excluded.amount,
                    source_versions = excluded.source_versions,
                    generated_at = excluded.generated_at,
                    payload = excluded.payload,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                params_seq,
            )

        run_in_transaction(self._connection, write)

    def bank_detail_scope_keys_for_range(self, *, date_from: str | None = None, date_to: str | None = None) -> list[str]:
        return self._bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to)

    def _bank_detail_scope_keys_for_range(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        connection: Any | None = None,
    ) -> list[str]:
        scope_keys = _bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to)
        if scope_keys == ["all"]:
            return self._bank_detail_available_month_scope_keys(connection=connection) or ["all"]
        return scope_keys

    def _bank_detail_available_month_scope_keys(self, *, tenant_id: str = "default", connection: Any | None = None) -> list[str]:
        executor = connection or self._connection
        rows = executor.fetch_all(
            """
            select scope_key
            from read_model.bank_detail_scopes
            where tenant_id = %s
              and scope_type = 'bank_detail'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key
            """,
            (tenant_id,),
        )
        return _dedupe_preserve_order(
            scope_key
            for row in rows
            if isinstance(row, dict)
            for scope_key in [text(row.get("scope_key"))]
            if scope_key and MONTH_SCOPE_RE.match(scope_key)
        )

    def bank_detail_scope_summary(
        self,
        *,
        scope_keys: list[str],
        tenant_id: str = "default",
        connection: Any | None = None,
    ) -> dict[str, Any]:
        normalized_scope_keys = _dedupe_preserve_order(
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if str(scope_key).strip()
        )
        if not normalized_scope_keys:
            return {
                "read_model_status": "missing",
                "read_model_scope_keys": [],
                "read_model_generated_at": None,
                "read_model_scope_signatures": {},
            }
        executor = connection or self._connection
        rows = executor.fetch_all(
            """
            select scope_key, scope_type, schema_version, status, row_count, source_version,
                   source_versions, generated_at, last_error
            from read_model.bank_detail_scopes
            where tenant_id = %s
              and scope_type = 'bank_detail'
              and scope_key = any(%s)
            """,
            (tenant_id, normalized_scope_keys),
        )
        dirty_rows = executor.fetch_all(
            """
            select scope_key, status, updated_at::text as updated_at, last_error, source_version
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = 'bank_detail'
              and scope_key = any(%s)
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            """,
            (tenant_id, normalized_scope_keys),
        )
        by_scope = {text(row.get("scope_key")): row for row in rows if text(row.get("scope_key"))}
        dirty_by_scope: dict[str, dict[str, Any]] = {}
        for row in dirty_rows:
            scope_key = text(row.get("scope_key"))
            if scope_key and scope_key not in dirty_by_scope:
                dirty_by_scope[scope_key] = row
        dirty_statuses = {text(row.get("status")) for row in dirty_by_scope.values()}
        if dirty_statuses.intersection({"pending", "processing"}):
            status = "refreshing"
        elif "failed" in dirty_statuses:
            status = "stale"
        elif any(scope_key not in by_scope for scope_key in normalized_scope_keys):
            status = "missing"
        elif any(int_value(by_scope[scope_key].get("schema_version"), 0) != BANK_DETAIL_READ_MODEL_SCHEMA_VERSION for scope_key in normalized_scope_keys):
            status = "schema_mismatch"
        elif any(text(by_scope[scope_key].get("status")) != "fresh" for scope_key in normalized_scope_keys):
            status = "stale"
        else:
            status = "fresh"
        generated_values = [
            text(by_scope[scope_key].get("generated_at"))
            for scope_key in normalized_scope_keys
            if scope_key in by_scope and text(by_scope[scope_key].get("generated_at"))
        ]
        signatures = {
            scope_key: {
                "schema_version": int_value(by_scope[scope_key].get("schema_version"), 0),
                "status": text(by_scope[scope_key].get("status")) or "",
                "row_count": int_value(by_scope[scope_key].get("row_count"), 0),
                "source_version": int_value(by_scope[scope_key].get("source_version"), 0),
                "source_versions": by_scope[scope_key].get("source_versions") if isinstance(by_scope[scope_key].get("source_versions"), dict) else {},
                "generated_at": text(by_scope[scope_key].get("generated_at")),
                "last_error": text(by_scope[scope_key].get("last_error")),
                "dirty_status": text(dirty_by_scope.get(scope_key, {}).get("status")),
                "dirty_source_version": int_value(dirty_by_scope.get(scope_key, {}).get("source_version"), 0),
                "dirty_last_error": text(dirty_by_scope.get(scope_key, {}).get("last_error")),
            }
            for scope_key in normalized_scope_keys
            if scope_key in by_scope
        }
        return {
            "read_model_status": status,
            "read_model_scope_keys": normalized_scope_keys,
            "read_model_generated_at": max(generated_values) if generated_values else None,
            "read_model_scope_signatures": signatures,
            "dirty_scopes": [
                {
                    "scope_key": scope_key,
                    "status": text(row.get("status")),
                    "updated_at": text(row.get("updated_at")),
                    "last_error": text(row.get("last_error")),
                    "source_version": int_value(row.get("source_version"), 0),
                }
                for scope_key, row in dirty_by_scope.items()
            ],
        }

    def bank_account_balance_scope_summary(
        self,
        *,
        tenant_id: str = "default",
        connection: Any | None = None,
    ) -> dict[str, Any]:
        executor = connection or self._connection
        rows = executor.fetch_all(
            """
            select scope_key, scope_type, schema_version, status, row_count, source_version,
                   source_versions, generated_at, last_error
            from read_model.bank_detail_scopes
            where tenant_id = %s
              and scope_type = 'bank_account_balance'
              and scope_key = 'all'
            """,
            (tenant_id,),
        )
        dirty_rows = executor.fetch_all(
            """
            select scope_key, status, updated_at::text as updated_at, last_error, source_version
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = 'bank_account_balance'
              and scope_key = 'all'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            """,
            (tenant_id,),
        )
        row = rows[0] if rows else None
        dirty_row = dirty_rows[0] if dirty_rows else None
        dirty_status = text((dirty_row or {}).get("status"))
        if dirty_status in {"pending", "processing"}:
            status = "refreshing"
        elif dirty_status == "failed":
            status = "stale"
        elif row is None:
            status = "missing"
        elif int_value(row.get("schema_version"), 0) != BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION:
            status = "schema_mismatch"
        elif text(row.get("status")) != "fresh":
            status = "stale"
        else:
            status = "fresh"
        return {
            "read_model_status": status,
            "read_model_scope_keys": ["all"],
            "read_model_generated_at": text((row or {}).get("generated_at")),
            "read_model_scope_signatures": {
                "all": {
                    "schema_version": int_value((row or {}).get("schema_version"), 0),
                    "status": text((row or {}).get("status")) or "",
                    "row_count": int_value((row or {}).get("row_count"), 0),
                    "source_version": int_value((row or {}).get("source_version"), 0),
                    "source_versions": row.get("source_versions") if isinstance((row or {}).get("source_versions"), dict) else {},
                    "generated_at": text((row or {}).get("generated_at")),
                    "last_error": text((row or {}).get("last_error")),
                    "dirty_status": dirty_status,
                    "dirty_source_version": int_value((dirty_row or {}).get("source_version"), 0),
                    "dirty_last_error": text((dirty_row or {}).get("last_error")),
                }
            } if row is not None else {},
            "dirty_scopes": [
                {
                    "scope_key": text(dirty_row.get("scope_key")) or "all",
                    "status": dirty_status,
                    "updated_at": text(dirty_row.get("updated_at")),
                    "last_error": text(dirty_row.get("last_error")),
                    "source_version": int_value(dirty_row.get("source_version"), 0),
                }
            ] if dirty_row is not None else [],
        }

    def list_bank_detail_transactions(
        self,
        *,
        account_key: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        category_code: str | None = None,
        category_primary_label: str | None = None,
        category_sub_label: str | None = None,
        category_third_label: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 100,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        page_number = max(1, int_value(page, 1))
        page_limit = min(max(1, int_value(page_size, 100)), 100)
        with self._connection.transaction() as connection:
            scope_keys = self._bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to, connection=connection)
            scope_summary = self.bank_detail_scope_summary(scope_keys=scope_keys, tenant_id=tenant_id, connection=connection)
            if scope_summary["read_model_status"] == "missing":
                return None
            read_model_status = text(scope_summary.get("read_model_status")) or "fresh"
            require_current_schema = read_model_status == "fresh"
            where_sql, params = _bank_detail_filter_sql(
                tenant_id=tenant_id,
                scope_keys=scope_keys,
                account_key=account_key,
                date_from=date_from,
                date_to=date_to,
                keyword=keyword,
                category_code=category_code,
                category_primary_label=category_primary_label,
                category_sub_label=category_sub_label,
                category_third_label=category_third_label,
                require_current_schema=require_current_schema,
            )
            total_row = connection.fetch_one(
                f"select count(*)::bigint as total from read_model.bank_detail_rows where {where_sql}",
                tuple(params),
            )
            total = int_value((total_row or {}).get("total"), 0)
            category_counts = _bank_detail_empty_category_counts()
            count_rows = connection.fetch_all(
                f"""
                select coalesce(effective_category_code, 'uncategorized') as category_code,
                       count(*)::bigint as count
                from read_model.bank_detail_rows
                where {where_sql}
                group by coalesce(effective_category_code, 'uncategorized')
                """,
                tuple(params),
            )
            for row in count_rows:
                category_counts[text(row.get("category_code")) or "uncategorized"] = int_value(row.get("count"), 0)
            rows = connection.fetch_all(
                f"""
                select payload, raw_payload, summary, purpose
                from read_model.bank_detail_rows
                where {where_sql}
                order by trade_time_sort desc, transaction_id desc
                limit %s offset %s
                """,
                tuple([*params, page_limit, (page_number - 1) * page_limit]),
            )
        return {
            "account_key": account_key,
            "date_from": date_from,
            "date_to": date_to,
            "rows": [_bank_detail_row_payload(row) for row in rows],
            "category_counts": category_counts,
            "pagination": {"page": page_number, "page_size": page_limit, "total": total},
            **scope_summary,
        }

    def list_bank_detail_accounts(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        with self._connection.transaction() as connection:
            scope_keys = self._bank_detail_scope_keys_for_range(date_from=date_from, date_to=date_to, connection=connection)
            scope_summary = self.bank_detail_scope_summary(scope_keys=scope_keys, tenant_id=tenant_id, connection=connection)
            if scope_summary["read_model_status"] == "missing":
                return None
            read_model_status = text(scope_summary.get("read_model_status")) or "fresh"
            require_current_schema = read_model_status == "fresh"
            where_sql, params = _bank_detail_filter_sql(
                tenant_id=tenant_id,
                scope_keys=scope_keys,
                date_from=date_from,
                date_to=date_to,
                require_current_schema=require_current_schema,
            )
            all_rows_where = ["tenant_id = %s"]
            all_rows_params: list[Any] = [tenant_id]
            if require_current_schema:
                all_rows_where.append("schema_version = %s")
                all_rows_params.append(BANK_DETAIL_READ_MODEL_SCHEMA_VERSION)
            rows = connection.fetch_all(
                f"""
                with all_rows as (
                    select account_key, bank_name, account_last4, balance, trade_time, trade_date, trade_time_sort
                    from read_model.bank_detail_rows
                    where {" and ".join(all_rows_where)}
                ),
                filtered as (
                    select account_key, bank_name, account_last4, balance, trade_time, trade_date, trade_time_sort
                    from read_model.bank_detail_rows
                    where {where_sql}
                ),
                accounts as (
                    select account_key, bank_name, account_last4
                    from all_rows
                    group by account_key, bank_name, account_last4
                ),
                counts as (
                    select account_key, bank_name, account_last4, count(*)::bigint as transaction_count
                    from filtered
                    group by account_key, bank_name, account_last4
                ),
                latest_balances as (
                    select distinct on (account_key)
                        account_key,
                        balance as latest_balance,
                        coalesce(trade_time::text, trade_date::text) as latest_balance_at
                    from all_rows
                    where balance is not null
                    order by account_key, trade_time_sort desc
                )
                select accounts.account_key, accounts.bank_name, accounts.account_last4,
                       coalesce(counts.transaction_count, 0)::bigint as transaction_count,
                       latest_balances.latest_balance,
                       latest_balances.latest_balance_at
                from accounts
                left join counts on counts.account_key = accounts.account_key
                left join latest_balances on latest_balances.account_key = accounts.account_key
                order by accounts.bank_name, accounts.account_last4
                """,
                tuple([*all_rows_params, *params]),
            )
        accounts = []
        for row in rows:
            latest_balance = row.get("latest_balance")
            accounts.append(
                {
                    "account_key": text(row.get("account_key")) or "",
                    "bank_name": text(row.get("bank_name")) or "未知银行",
                    "account_last4": text(row.get("account_last4")) or "unknown",
                    "display_name": f"{text(row.get('bank_name')) or '未知银行'} {text(row.get('account_last4')) or 'unknown'}",
                    "latest_balance": decimal_text(latest_balance) if latest_balance is not None else None,
                    "latest_balance_at": text(row.get("latest_balance_at")),
                    "has_balance": latest_balance is not None,
                    "transaction_count": int_value(row.get("transaction_count"), 0),
                }
            )
        total_balance = sum(
            (Decimal(str(account["latest_balance"])) for account in accounts if account.get("latest_balance") not in (None, "")),
            Decimal("0.00"),
        )
        return {
            "accounts": accounts,
            "total_balance": decimal_text(total_balance) if any(account.get("has_balance") for account in accounts) else None,
            "balance_account_count": sum(1 for account in accounts if account.get("has_balance")),
            "missing_balance_account_count": sum(1 for account in accounts if not account.get("has_balance")),
            **scope_summary,
        }

    def get_bank_detail_tagged_rows_by_transaction_ids(
        self,
        transaction_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_ids = _dedupe_preserve_order(
            text(transaction_id)
            for transaction_id in list(transaction_ids or [])
            if text(transaction_id)
        )
        if not normalized_ids:
            return {
                "rows": [],
                "missing_transaction_ids": [],
                "source_versions": {},
                "read_model_status": "fresh",
                "read_model_scope_keys": [],
                "read_model_scope_signatures": {},
            }
        with self._connection.transaction() as connection:
            rows = connection.fetch_all(
                """
                select payload, raw_payload, summary, purpose, scope_key, source_versions
                from read_model.bank_detail_rows
                where tenant_id = %s
                  and (
                    transaction_id = any(%s)
                    or payload->>'id' = any(%s)
                    or payload->>'transaction_id' = any(%s)
                  )
                """,
                (tenant_id, normalized_ids, normalized_ids, normalized_ids),
            )
            unordered_payload_rows = [_bank_detail_row_payload(row) for row in rows]
            payload_by_id: dict[str, dict[str, Any]] = {}
            for row in unordered_payload_rows:
                for row_identity in (row.get("transaction_id"), row.get("id")):
                    if transaction_id := text(row_identity):
                        payload_by_id.setdefault(transaction_id, row)
            payload_rows = [
                payload_by_id[transaction_id]
                for transaction_id in normalized_ids
                if transaction_id in payload_by_id
            ]
            row_ids = {text(row.get("transaction_id") or row.get("id")) for row in payload_rows}
            missing_ids = [transaction_id for transaction_id in normalized_ids if transaction_id not in row_ids]
            scope_keys = _dedupe_preserve_order(
                text(row.get("scope_key")) or _bank_detail_month_text((row.get("trade_date") or row.get("trade_time")))
                for row in payload_rows
            )
            if not scope_keys:
                return {
                    "rows": [],
                    "missing_transaction_ids": missing_ids,
                    "source_versions": {},
                    "read_model_status": "missing",
                    "read_model_scope_keys": [],
                    "read_model_scope_signatures": {},
                }
            scope_summary = self.bank_detail_scope_summary(
                scope_keys=scope_keys,
                tenant_id=tenant_id,
                connection=connection,
            )
        return {
            "rows": payload_rows,
            "missing_transaction_ids": missing_ids,
            "source_versions": _source_versions_from_scope_summary(scope_summary),
            **scope_summary,
        }

    def list_bank_detail_tagged_rows_by_month(
        self,
        month: str,
        *,
        direction: str | None = None,
        category_codes: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_month = text(month)
        if not normalized_month or not MONTH_SCOPE_RE.match(normalized_month):
            raise ValueError("bank detail tagged row month must be YYYY-MM.")
        with self._connection.transaction() as connection:
            scope_summary = self.bank_detail_scope_summary(
                scope_keys=[normalized_month],
                tenant_id=tenant_id,
                connection=connection,
            )
            if scope_summary["read_model_status"] == "missing":
                return None
            read_model_status = text(scope_summary.get("read_model_status")) or "fresh"
            require_current_schema = read_model_status == "fresh"
            where = ["tenant_id = %s", "scope_month = %s::date"]
            params: list[Any] = [tenant_id, month_start(normalized_month)]
            if require_current_schema:
                where.append("schema_version = %s")
                params.append(BANK_DETAIL_READ_MODEL_SCHEMA_VERSION)
            if normalized_direction := text(direction):
                where.append("direction = %s")
                params.append(normalized_direction)
            normalized_category_codes = _dedupe_preserve_order(
                text(category_code)
                for category_code in list(category_codes or [])
                if text(category_code)
            )
            if normalized_category_codes:
                where.append("effective_category_code = any(%s)")
                params.append(normalized_category_codes)
            rows = connection.fetch_all(
                f"""
                select payload, raw_payload, summary, purpose, scope_key, source_versions
                from read_model.bank_detail_rows
                where {" and ".join(where)}
                order by trade_time_sort desc, transaction_id desc
                """,
                tuple(params),
            )
        return {
            "rows": [_bank_detail_row_payload(row) for row in rows],
            "missing_transaction_ids": [],
            "source_versions": _source_versions_from_scope_summary(scope_summary),
            **scope_summary,
        }

    def list_bank_account_balances(
        self,
        *,
        date_from: str | None = None,
        date_to: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        with self._connection.transaction() as connection:
            scope_summary = self.bank_account_balance_scope_summary(tenant_id=tenant_id, connection=connection)
            balance_read_model_status = text(scope_summary.get("read_model_status")) or "missing"
            if balance_read_model_status == "missing":
                return None
            rows = connection.fetch_all(
                """
                select account_identity, account_key, bank_name, account_last4, account_no, account_name,
                       identity_confidence, latest_balance, latest_balance_at, latest_balance_transaction_id,
                       latest_trade_time_sort, currency, transaction_total_count, schema_version,
                       source_versions, generated_at
                from read_model.bank_account_balances
                where tenant_id = %s
                  and schema_version = %s
                order by bank_name, account_last4, account_identity
                """,
                (tenant_id, BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION),
            )
            count_clauses = ["tenant_id = %s"]
            count_params: list[Any] = [tenant_id]
            if date_text := text(date_from):
                count_clauses.append("trade_date >= %s::date")
                count_params.append(date_text[:10])
            if date_text := text(date_to):
                count_clauses.append("trade_date <= %s::date")
                count_params.append(date_text[:10])
            count_rows = connection.fetch_all(
                f"""
                select account_key, count(*)::bigint as transaction_count
                from read_model.bank_detail_rows
                where {" and ".join(count_clauses)}
                group by account_key
                """,
                tuple(count_params),
            )
        transaction_counts = {
            text(row.get("account_key")) or "": int_value(row.get("transaction_count"), 0)
            for row in count_rows
        }
        accounts = []
        totals_by_currency: dict[str, Decimal] = {}
        for row in rows:
            latest_balance = row.get("latest_balance")
            currency = text(row.get("currency")) or "CNY"
            has_balance = latest_balance is not None
            if has_balance:
                totals_by_currency[currency] = totals_by_currency.get(currency, Decimal("0.00")) + Decimal(str(latest_balance))
            accounts.append(
                {
                    "account_identity": text(row.get("account_identity")) or "",
                    "account_key": text(row.get("account_key")) or text(row.get("account_identity")) or "",
                    "bank_name": text(row.get("bank_name")) or "未知银行",
                    "account_last4": text(row.get("account_last4")) or "unknown",
                    "display_name": f"{text(row.get('bank_name')) or '未知银行'} {text(row.get('account_last4')) or 'unknown'}",
                    "account_no": text(row.get("account_no")),
                    "account_name": text(row.get("account_name")),
                    "identity_confidence": text(row.get("identity_confidence")) or "fallback",
                    "latest_balance": decimal_text(latest_balance) if latest_balance is not None else None,
                    "latest_balance_at": text(row.get("latest_balance_at")),
                    "latest_balance_transaction_id": text(row.get("latest_balance_transaction_id")),
                    "currency": currency,
                    "has_balance": has_balance,
                    "transaction_count": transaction_counts.get(text(row.get("account_key")) or "", 0),
                    "transaction_total_count": int_value(row.get("transaction_total_count"), 0),
                }
            )
        total_balance = totals_by_currency.get("CNY")
        return {
            "accounts": accounts,
            "total_balance": decimal_text(total_balance) if total_balance is not None else None,
            "total_balances_by_currency": {
                currency: decimal_text(total)
                for currency, total in sorted(totals_by_currency.items())
            },
            "balance_account_count": sum(1 for account in accounts if account.get("has_balance")),
            "missing_balance_account_count": sum(1 for account in accounts if not account.get("has_balance")),
            "balance_read_model_status": balance_read_model_status,
            "read_model_status": balance_read_model_status,
            **scope_summary,
        }

    def save_bank_account_balances(self, *, rows: list[dict[str, Any]], tenant_id: str = "default") -> None:
        generated_at = text((rows[0] if rows else {}).get("generated_at")) if rows else None

        def write(connection: Any) -> None:
            connection.execute("delete from read_model.bank_account_balances where tenant_id = %s", (tenant_id,))
            for row in list(rows or []):
                connection.execute(
                    """
                    insert into read_model.bank_account_balances(
                        tenant_id, account_identity, account_key, bank_name, account_last4,
                        account_no, account_name, identity_confidence, latest_balance,
                        latest_balance_at, latest_balance_transaction_id, latest_trade_time_sort,
                        latest_bank_serial_no, source_batch_id, legacy_source_batch_id, currency,
                        transaction_total_count, schema_version, source_versions, generated_at, raw_payload
                    )
                    values (
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s,
                        %s::timestamptz, %s, %s::timestamptz,
                        %s, %s, %s, %s,
                        %s, %s, %s, coalesce(%s::timestamptz, now()), %s
                    )
                    on conflict (tenant_id, account_identity) do update set
                        account_key = excluded.account_key,
                        bank_name = excluded.bank_name,
                        account_last4 = excluded.account_last4,
                        account_no = excluded.account_no,
                        account_name = excluded.account_name,
                        identity_confidence = excluded.identity_confidence,
                        latest_balance = excluded.latest_balance,
                        latest_balance_at = excluded.latest_balance_at,
                        latest_balance_transaction_id = excluded.latest_balance_transaction_id,
                        latest_trade_time_sort = excluded.latest_trade_time_sort,
                        latest_bank_serial_no = excluded.latest_bank_serial_no,
                        source_batch_id = excluded.source_batch_id,
                        legacy_source_batch_id = excluded.legacy_source_batch_id,
                        currency = excluded.currency,
                        transaction_total_count = excluded.transaction_total_count,
                        schema_version = excluded.schema_version,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        tenant_id,
                        text(row.get("account_identity")),
                        text(row.get("account_key") or row.get("account_identity")),
                        text(row.get("bank_name")) or "未知银行",
                        text(row.get("account_last4")) or "unknown",
                        text(row.get("account_no")),
                        text(row.get("account_name")),
                        text(row.get("identity_confidence")) or "fallback",
                        decimal_text(row.get("latest_balance")),
                        text(row.get("latest_balance_at")),
                        text(row.get("latest_balance_transaction_id")),
                        text(row.get("latest_trade_time_sort")),
                        text(row.get("latest_bank_serial_no")),
                        text(row.get("source_batch_id")),
                        text(row.get("legacy_source_batch_id")),
                        text(row.get("currency")) or "CNY",
                        int_value(row.get("transaction_total_count"), 0),
                        BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                        jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                        text(row.get("generated_at")),
                        jsonb(row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}),
                    ),
                )
            self._upsert_bank_detail_scope(
                connection,
                tenant_id=tenant_id,
                scope_type="bank_account_balance",
                scope_key="all",
                scope_month=None,
                row_count=len(list(rows or [])),
                source_versions=(rows[0].get("source_versions") if rows and isinstance(rows[0].get("source_versions"), dict) else {}),
                schema_version=BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION,
                generated_at=generated_at,
            )

        run_in_transaction(self._connection, write)

    def save_bank_detail_rows(self, *, scope_key: str, rows: list[dict[str, Any]], tenant_id: str = "default") -> None:
        normalized_scope_key = text(scope_key)
        if not normalized_scope_key or not MONTH_SCOPE_RE.match(normalized_scope_key):
            raise ValueError("bank detail row scope_key must be YYYY-MM.")
        scope_month = month_start(normalized_scope_key)
        generated_at = text((rows[0] if rows else {}).get("generated_at")) if rows else None

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.bank_detail_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            for row in list(rows or []):
                record = _bank_detail_row_record(row, scope_key=normalized_scope_key, scope_month=scope_month, tenant_id=tenant_id)
                connection.execute(
                    """
                    insert into read_model.bank_detail_rows(
                        tenant_id, transaction_id, scope_key, scope_month, source_batch_id,
                        legacy_source_batch_id, account_key, bank_name, account_last4, account_no,
                        account_name, trade_time, trade_date, trade_time_sort, direction,
                        direction_label, amount, signed_amount, balance, currency,
                        counterparty_name, summary, purpose, manual_category_code,
                        manual_category_label, manual_category_path, manual_category_primary_label,
                        manual_category_sub_label, manual_category_third_label, manual_category_label_path, manual_category_source,
                        manual_category_version, manual_confirmed_category_code, auto_category_code, auto_category_label,
                        auto_category_path, auto_category_primary_label, auto_category_sub_label, auto_category_third_label,
                        auto_category_label_path, auto_category_source, auto_category_rule_code,
                        auto_category_reason, auto_category_confidence, auto_category_rule_version,
                        auto_candidate_category_codes, auto_candidate_categories,
                        effective_category_code, effective_category_label, effective_category_path,
                        effective_category_primary_label, effective_category_sub_label, effective_category_third_label,
                        effective_category_label_path, effective_category_source,
                        effective_turnover_role, effective_turnover_action_type, effective_turnover_family,
                        category_version, category_source,
                        category_resolution_status, category_rule_version,
                        oa_relation_tag, invoice_relation_tag, relation_tags, relation_case_id,
                        search_text, schema_version, source_versions, generated_at, payload, raw_payload
                    )
                    values (
                        %s, %s, %s, %s::date, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s::timestamptz, %s::date, %s::timestamptz, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s
                    )
                    on conflict (tenant_id, transaction_id) do update set
                        scope_key = excluded.scope_key,
                        scope_month = excluded.scope_month,
                        source_batch_id = excluded.source_batch_id,
                        legacy_source_batch_id = excluded.legacy_source_batch_id,
                        account_key = excluded.account_key,
                        bank_name = excluded.bank_name,
                        account_last4 = excluded.account_last4,
                        account_no = excluded.account_no,
                        account_name = excluded.account_name,
                        trade_time = excluded.trade_time,
                        trade_date = excluded.trade_date,
                        trade_time_sort = excluded.trade_time_sort,
                        direction = excluded.direction,
                        direction_label = excluded.direction_label,
                        amount = excluded.amount,
                        signed_amount = excluded.signed_amount,
                        balance = excluded.balance,
                        currency = excluded.currency,
                        counterparty_name = excluded.counterparty_name,
                        summary = excluded.summary,
                        purpose = excluded.purpose,
                        manual_category_code = excluded.manual_category_code,
                        manual_category_label = excluded.manual_category_label,
                        manual_category_path = excluded.manual_category_path,
                        manual_category_primary_label = excluded.manual_category_primary_label,
                        manual_category_sub_label = excluded.manual_category_sub_label,
                        manual_category_third_label = excluded.manual_category_third_label,
                        manual_category_label_path = excluded.manual_category_label_path,
                        manual_category_source = excluded.manual_category_source,
                        manual_category_version = excluded.manual_category_version,
                        manual_confirmed_category_code = excluded.manual_confirmed_category_code,
                        auto_category_code = excluded.auto_category_code,
                        auto_category_label = excluded.auto_category_label,
                        auto_category_path = excluded.auto_category_path,
                        auto_category_primary_label = excluded.auto_category_primary_label,
                        auto_category_sub_label = excluded.auto_category_sub_label,
                        auto_category_third_label = excluded.auto_category_third_label,
                        auto_category_label_path = excluded.auto_category_label_path,
                        auto_category_source = excluded.auto_category_source,
                        auto_category_rule_code = excluded.auto_category_rule_code,
                        auto_category_reason = excluded.auto_category_reason,
                        auto_category_confidence = excluded.auto_category_confidence,
                        auto_category_rule_version = excluded.auto_category_rule_version,
                        auto_candidate_category_codes = excluded.auto_candidate_category_codes,
                        auto_candidate_categories = excluded.auto_candidate_categories,
                        effective_category_code = excluded.effective_category_code,
                        effective_category_label = excluded.effective_category_label,
                        effective_category_path = excluded.effective_category_path,
                        effective_category_primary_label = excluded.effective_category_primary_label,
                        effective_category_sub_label = excluded.effective_category_sub_label,
                        effective_category_third_label = excluded.effective_category_third_label,
                        effective_category_label_path = excluded.effective_category_label_path,
                        effective_category_source = excluded.effective_category_source,
                        effective_turnover_role = excluded.effective_turnover_role,
                        effective_turnover_action_type = excluded.effective_turnover_action_type,
                        effective_turnover_family = excluded.effective_turnover_family,
                        category_version = excluded.category_version,
                        category_source = excluded.category_source,
                        category_resolution_status = excluded.category_resolution_status,
                        category_rule_version = excluded.category_rule_version,
                        oa_relation_tag = excluded.oa_relation_tag,
                        invoice_relation_tag = excluded.invoice_relation_tag,
                        relation_tags = excluded.relation_tags,
                        relation_case_id = excluded.relation_case_id,
                        search_text = excluded.search_text,
                        schema_version = excluded.schema_version,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    record,
                )
            self._upsert_bank_detail_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=scope_month,
                row_count=len(list(rows or [])),
                source_versions=(rows[0].get("source_versions") if rows and isinstance(rows[0].get("source_versions"), dict) else {}),
                generated_at=generated_at,
            )

        run_in_transaction(self._connection, write)

    def mark_bank_detail_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        tenant_id: str = "default",
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        normalized_scope_key = text(scope_key)
        if not normalized_scope_key:
            raise ValueError("bank detail scope_key is required.")

        def write(connection: Any) -> None:
            self._upsert_bank_detail_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=month_start(normalized_scope_key),
                row_count=row_count,
                source_versions=source_versions or {},
            )

        run_in_transaction(self._connection, write)

    @staticmethod
    def _upsert_bank_detail_scope(
        connection: Any,
        *,
        tenant_id: str,
        scope_type: str = "bank_detail",
        scope_key: str,
        scope_month: date | None,
        row_count: int,
        source_versions: dict[str, Any],
        schema_version: int = BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
        generated_at: str | None = None,
    ) -> None:
        connection.execute(
            """
            insert into read_model.bank_detail_scopes(
                tenant_id, scope_type, scope_key, scope_month, schema_version, status,
                row_count, source_version, source_versions, generated_at, raw_payload
            )
            values (
                %s, %s, %s, %s::date, %s, 'fresh',
                %s, %s, %s, coalesce(%s::timestamptz, now()), %s
            )
            on conflict (tenant_id, scope_type, scope_key) do update set
                scope_month = excluded.scope_month,
                schema_version = excluded.schema_version,
                status = 'fresh',
                row_count = excluded.row_count,
                source_version = excluded.source_version,
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                last_error = null,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                tenant_id,
                scope_type,
                scope_key,
                scope_month,
                schema_version,
                max(0, int_value(row_count, 0)),
                _source_version_value(source_versions),
                jsonb(source_versions),
                generated_at,
                jsonb({"source_versions": source_versions}),
            ),
        )

    def list_input_invoice_usage_rows(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any] | None:
        return self._list_invoice_relation_rows(
            table_name="read_model.input_invoice_usage_rows",
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_type="input_invoice_usage",
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            filter_fields=INPUT_INVOICE_USAGE_FILTER_FIELDS,
            sort_expressions=INPUT_INVOICE_USAGE_SORT_EXPRESSIONS,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
            summary_kind="input",
        )

    def save_input_invoice_usage_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._save_invoice_relation_rows(
            table_name="read_model.input_invoice_usage_rows",
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_type="input_invoice_usage",
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
            row_builder=_input_invoice_usage_read_model_record,
        )

    def mark_input_invoice_usage_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._mark_invoice_relation_scope(
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def get_input_invoice_usage_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select scope_key, source_versions, payload, raw_payload
            from read_model.input_invoice_usage_rows
            where row_id = %s
            order by generated_at desc, scope_key desc, row_id
            limit 1
            """,
            (text(row_id),),
        )
        if not isinstance(row, dict):
            return None
        payload = _read_model_payload(row)
        scope_key = text(row.get("scope_key")) or "all"
        source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
        return {
            "row": payload if isinstance(payload, dict) else None,
            "refresh_status": self._invoice_relation_refresh_status(
                scope_type="input_invoice_usage",
                scope_key=scope_key,
            ),
            "source_versions": source_versions,
            "read_model_scope_key": scope_key,
        }

    def list_output_invoice_collection_rows(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any] | None:
        return self._list_invoice_relation_rows(
            table_name="read_model.output_invoice_collection_rows",
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_type="output_invoice_collection",
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            filter_fields=OUTPUT_INVOICE_COLLECTION_FILTER_FIELDS,
            sort_expressions=OUTPUT_INVOICE_COLLECTION_SORT_EXPRESSIONS,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
            summary_kind="output",
        )

    def save_output_invoice_collection_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._save_invoice_relation_rows(
            table_name="read_model.output_invoice_collection_rows",
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_type="output_invoice_collection",
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
            row_builder=_output_invoice_collection_read_model_record,
        )

    def mark_output_invoice_collection_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._mark_invoice_relation_scope(
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def list_oa_pending_payment_rows(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        trade_date_from: str | None = None,
        trade_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
        view_mode: str | None = None,
    ) -> dict[str, Any] | None:
        scope_key = _invoice_relation_scope_key(month)
        page_number = max(int_value(page, 1), 1)
        page_limit = min(max(int_value(page_size, 50), 1), 200)
        base_where: list[str] = []
        base_params: list[Any] = []
        view_mode_clause = _oa_pending_payment_view_mode_clause(view_mode)
        if scope_key != "all":
            base_where.append("scope_key = %s")
            base_params.append(scope_key)
        if trade_date_from:
            base_where.append("bank_trade_time >= %s::date")
            base_params.append(trade_date_from)
        if trade_date_to:
            base_where.append("bank_trade_time < (%s::date + interval '1 day')")
            base_params.append(trade_date_to)
        if keyword:
            base_where.append("searchable_text ilike %s")
            base_params.append(f"%{keyword}%")
        for clause, clause_params in _invoice_relation_filter_clauses(filters, OA_PENDING_PAYMENT_FILTER_FIELDS):
            base_where.append(clause)
            base_params.extend(clause_params)
        where = list(base_where)
        params = list(base_params)
        if view_mode_clause:
            where.append(view_mode_clause)
        where_sql = " and ".join(where) if where else "true"
        base_where_sql = " and ".join(base_where) if base_where else "true"
        summary_row = self._connection.fetch_one(
            f"""
            select
                count(*) as count,
                coalesce(sum(oa_amount), 0) as oa_amount_total,
                coalesce(sum(coalesce(bank_paid_total, bank_amount)), 0) as bank_paid_total
            from read_model.oa_pending_payment_rows
            where {where_sql}
            """,
            tuple(params),
        )
        view_counts_row = self._connection.fetch_one(
            f"""
            select
                coalesce(sum(case when oa_workflow_status is null or oa_workflow_status = '' or oa_workflow_status = 'completed' then 1 else 0 end), 0) as completed_count,
                coalesce(sum(case when oa_workflow_status = 'in_progress' then 1 else 0 end), 0) as in_progress_count
            from read_model.oa_pending_payment_rows
            where {base_where_sql}
            """,
            tuple(base_params),
        )
        view_counts = {
            "completed": int_value(view_counts_row.get("completed_count") if isinstance(view_counts_row, dict) else 0, 0),
            "in_progress": int_value(view_counts_row.get("in_progress_count") if isinstance(view_counts_row, dict) else 0, 0),
        }
        total = int_value(summary_row.get("count") if isinstance(summary_row, dict) else 0, 0)
        refresh_status = self._invoice_relation_refresh_status(scope_type="oa_pending_payment", scope_key=scope_key)
        scope_row = self._invoice_relation_scope_row(scope_table_name="read_model.oa_pending_payment_scopes", scope_key=scope_key)
        source_versions = self._oa_pending_payment_scope_source_versions(scope_key=scope_key, scope_row=scope_row)
        if total == 0:
            if scope_row is None and sum(view_counts.values()) == 0:
                return None
            return {
                "rows": [],
                "pagination": {"page": page_number, "pageSize": page_limit, "total": 0},
                "summary": {"rowCount": 0, "oaAmountTotal": "0.00", "bankPaidTotal": "0.00", "viewCounts": view_counts},
                "refresh_status": refresh_status,
                "source_versions": source_versions,
                "read_model_scope_key": scope_key,
            }
        order_sql = _invoice_relation_order_sql(
            sort_field=sort_field,
            sort_direction=sort_direction,
            sort_expressions=OA_PENDING_PAYMENT_SORT_EXPRESSIONS,
        )
        rows = self._connection.fetch_all(
            f"""
            select payload, raw_payload
            from read_model.oa_pending_payment_rows
            where {where_sql}
            order by {order_sql}
            limit %s offset %s
            """,
            tuple([*params, page_limit, (page_number - 1) * page_limit]),
        )
        payload_rows = [_read_model_payload(row) for row in rows]
        return {
            "rows": [row for row in payload_rows if isinstance(row, dict)],
            "pagination": {"page": page_number, "pageSize": page_limit, "total": total},
            "summary": {
                "rowCount": total,
                "oaAmountTotal": decimal_text(summary_row.get("oa_amount_total") if isinstance(summary_row, dict) else None) or "0.00",
                "bankPaidTotal": decimal_text(summary_row.get("bank_paid_total") if isinstance(summary_row, dict) else None) or "0.00",
                "viewCounts": view_counts,
            },
            "refresh_status": refresh_status,
            "source_versions": source_versions,
            "read_model_scope_key": scope_key,
        }

    def _oa_pending_payment_scope_source_versions(
        self,
        *,
        scope_key: str,
        scope_row: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if scope_key == "all":
            rows = self._connection.fetch_all(
                """
                select distinct scope_key, source_versions
                from read_model.oa_pending_payment_rows
                where scope_key <> 'all'
                order by scope_key desc
                """
            )
            if rows:
                return self._common_source_versions([dict(row) for row in rows if isinstance(row, dict)])
        return (
            scope_row.get("source_versions")
            if isinstance(scope_row, dict) and isinstance(scope_row.get("source_versions"), dict)
            else {}
        )

    def save_oa_pending_payment_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        rows_to_save = list(rows or [])
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if normalized_scope_key == "all":
                connection.execute("delete from read_model.oa_pending_payment_rows")
            else:
                connection.execute("delete from read_model.oa_pending_payment_rows where scope_key = %s", (normalized_scope_key,))
            for row in rows_to_save:
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["sourceVersions"] = normalized_source_versions
                connection.execute(
                    """
                    insert into read_model.oa_pending_payment_rows(
                        row_id, scope_key, scope_month, oa_id, oa_applicant, oa_application_type,
                        oa_workflow_status, oa_project_name, oa_amount, payment_status, payment_status_label,
                        bank_transaction_id, bank_trade_time, bank_amount, bank_paid_total, bank_name, bank_account, bank_direction,
                        bank_counterparty_name, bank_summary, invoice_id, invoice_no,
                        invoice_date, seller_name, invoice_total_with_tax, searchable_text,
                        source_versions, payload, raw_payload
                    )
                    values (
                        %(row_id)s, %(scope_key)s, %(scope_month)s::date, %(oa_id)s, %(oa_applicant)s,
                        %(oa_application_type)s, %(oa_workflow_status)s, %(oa_project_name)s, %(oa_amount)s, %(payment_status)s,
                        %(payment_status_label)s, %(bank_transaction_id)s, %(bank_trade_time)s::timestamptz,
                        %(bank_amount)s, %(bank_paid_total)s, %(bank_name)s, %(bank_account)s, %(bank_direction)s,
                        %(bank_counterparty_name)s, %(bank_summary)s,
                        %(invoice_id)s, %(invoice_no)s, %(invoice_date)s::date, %(seller_name)s,
                        %(invoice_total_with_tax)s, %(searchable_text)s, %(source_versions)s,
                        %(payload)s, %(raw_payload)s
                    )
                    on conflict (row_id, scope_key) do update set
                        scope_month = excluded.scope_month,
                        oa_id = excluded.oa_id,
                        oa_applicant = excluded.oa_applicant,
                        oa_application_type = excluded.oa_application_type,
                        oa_workflow_status = excluded.oa_workflow_status,
                        oa_project_name = excluded.oa_project_name,
                        oa_amount = excluded.oa_amount,
                        payment_status = excluded.payment_status,
                        payment_status_label = excluded.payment_status_label,
                        bank_transaction_id = excluded.bank_transaction_id,
                        bank_trade_time = excluded.bank_trade_time,
                        bank_amount = excluded.bank_amount,
                        bank_paid_total = excluded.bank_paid_total,
                        bank_name = excluded.bank_name,
                        bank_account = excluded.bank_account,
                        bank_direction = excluded.bank_direction,
                        bank_counterparty_name = excluded.bank_counterparty_name,
                        bank_summary = excluded.bank_summary,
                        invoice_id = excluded.invoice_id,
                        invoice_no = excluded.invoice_no,
                        invoice_date = excluded.invoice_date,
                        seller_name = excluded.seller_name,
                        invoice_total_with_tax = excluded.invoice_total_with_tax,
                        searchable_text = excluded.searchable_text,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    _oa_pending_payment_read_model_record(row_payload, normalized_scope_key),
                )
            self._upsert_invoice_relation_scope(
                connection,
                scope_table_name="read_model.oa_pending_payment_scopes",
                scope_key=normalized_scope_key,
                row_count=len(rows_to_save),
                scope_type="oa_pending_payment",
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def mark_oa_pending_payment_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        self._mark_invoice_relation_scope(
            scope_table_name="read_model.oa_pending_payment_scopes",
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
        )

    def get_oa_pending_payment_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        return self._get_oa_pending_payment_row("row_id = %s", (text(row_id),))

    def get_oa_pending_payment_row_by_oa_id(self, oa_id: str) -> dict[str, Any] | None:
        return self._get_oa_pending_payment_row("oa_id = %s", (text(oa_id),))

    def get_oa_pending_payment_row_by_bank_transaction_id(self, bank_transaction_id: str) -> dict[str, Any] | None:
        return self._get_oa_pending_payment_row("bank_transaction_id = %s", (text(bank_transaction_id),))

    def get_oa_pending_payment_row_by_invoice_id(self, invoice_id: str) -> dict[str, Any] | None:
        return self._get_oa_pending_payment_row("invoice_id = %s", (text(invoice_id),))

    def _get_oa_pending_payment_row(self, predicate_sql: str, params: tuple[Any, ...]) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            f"""
            select scope_key, source_versions, payload, raw_payload
            from read_model.oa_pending_payment_rows
            where {predicate_sql}
            order by generated_at desc, scope_key desc, row_id
            limit 1
            """,
            params,
        )
        if isinstance(row, dict):
            payload = _read_model_payload(row)
            scope_key = text(row.get("scope_key")) or "all"
            source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
            return {
                "row": payload if isinstance(payload, dict) else None,
                "refresh_status": self._invoice_relation_refresh_status(scope_type="oa_pending_payment", scope_key=scope_key),
                "source_versions": source_versions,
                "read_model_scope_key": scope_key,
            }
        scope_row = self._invoice_relation_scope_row(scope_table_name="read_model.oa_pending_payment_scopes", scope_key="all")
        if not isinstance(scope_row, dict):
            return None
        return {
            "row": None,
            "refresh_status": self._invoice_relation_refresh_status(scope_type="oa_pending_payment", scope_key="all"),
            "source_versions": scope_row.get("source_versions") if isinstance(scope_row.get("source_versions"), dict) else {},
            "read_model_scope_key": text(scope_row.get("scope_key")) or "all",
        }

    def _list_invoice_relation_rows(
        self,
        *,
        table_name: str,
        scope_table_name: str,
        scope_type: str,
        month: str | None,
        keyword: str | None,
        invoice_date_from: str | None,
        invoice_date_to: str | None,
        filters: str | list[dict[str, Any]] | None,
        filter_fields: dict[str, tuple[str, str, set[str]]],
        sort_expressions: dict[str, str],
        sort_field: str | None,
        sort_direction: str | None,
        page: int | str | None,
        page_size: int | str | None,
        summary_kind: str,
    ) -> dict[str, Any] | None:
        scope_key = _invoice_relation_scope_key(month)
        page_number = max(int_value(page, 1), 1)
        page_limit = min(max(int_value(page_size, 50), 1), 200)
        where: list[str] = []
        params: list[Any] = []
        if scope_key != "all":
            where.append("scope_key = %s")
            params.append(scope_key)
        if invoice_date_from:
            where.append("invoice_date >= %s::date")
            params.append(invoice_date_from)
        if invoice_date_to:
            where.append("invoice_date <= %s::date")
            params.append(invoice_date_to)
        if keyword:
            where.append("searchable_text ilike %s")
            params.append(f"%{keyword}%")
        for clause, clause_params in _invoice_relation_filter_clauses(filters, filter_fields):
            where.append(clause)
            params.extend(clause_params)
        where_sql = " and ".join(where) if where else "true"
        summary_row = self._connection.fetch_one(
            _invoice_relation_summary_sql(table_name=table_name, where_sql=where_sql, summary_kind=summary_kind),
            tuple(params),
        )
        total = int_value(summary_row.get("count") if isinstance(summary_row, dict) else 0, 0)
        refresh_status = self._invoice_relation_refresh_status(scope_type=scope_type, scope_key=scope_key)
        scope_row = self._invoice_relation_scope_row(scope_table_name=scope_table_name, scope_key=scope_key)
        source_versions = (
            scope_row.get("source_versions")
            if isinstance(scope_row, dict) and isinstance(scope_row.get("source_versions"), dict)
            else {}
        )
        if total == 0:
            if scope_row is None:
                return None
            return {
                "rows": [],
                "pagination": {"page": page_number, "pageSize": page_limit, "total": 0},
                "summary": _invoice_relation_summary_payload(summary_row or {}, summary_kind=summary_kind, total=0),
                "refresh_status": refresh_status,
                "source_versions": source_versions,
            }
        order_sql = _invoice_relation_order_sql(
            sort_field=sort_field,
            sort_direction=sort_direction,
            sort_expressions=sort_expressions,
        )
        rows = self._connection.fetch_all(
            f"""
            select payload, raw_payload
            from {table_name}
            where {where_sql}
            order by {order_sql}
            limit %s offset %s
            """,
            tuple([*params, page_limit, (page_number - 1) * page_limit]),
        )
        payload_rows = [_read_model_payload(row) for row in rows]
        return {
            "rows": [row for row in payload_rows if isinstance(row, dict)],
            "pagination": {"page": page_number, "pageSize": page_limit, "total": total},
            "summary": _invoice_relation_summary_payload(summary_row or {}, summary_kind=summary_kind, total=total),
            "refresh_status": refresh_status,
            "source_versions": source_versions,
        }

    def _save_invoice_relation_rows(
        self,
        *,
        table_name: str,
        scope_table_name: str,
        scope_type: str,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None,
        row_builder: Any,
    ) -> None:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        rows_to_save = list(rows or [])
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if normalized_scope_key == "all":
                connection.execute(f"delete from {table_name}")
            else:
                connection.execute(f"delete from {table_name} where scope_key = %s", (normalized_scope_key,))
            for row in rows_to_save:
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["sourceVersions"] = normalized_source_versions
                record = row_builder(row_payload, normalized_scope_key)
                connection.execute(
                    f"""
                    insert into {table_name}(
                        row_id, scope_key, scope_month, invoice_id, invoice_identity_key, invoice_no, invoice_date,
                        seller_name, seller_tax_no, buyer_name, buyer_tax_no, total_with_tax, amount, tax_amount, tax_rate,
                        specific_business_type, taxable_item_name, payment_status, payment_status_label,
                        collection_status, collection_status_label, collected_amount, pending_amount,
                        oa_applicant, oa_application_type, oa_project_name, bank_counterparty_name, bank_trade_time,
                        bank_amount, bank_name, bank_account, bank_direction, bank_summary, receipt_status, receipt_status_label,
                        oa_relation_count, bank_relation_count, red_invoice_relation_count, searchable_text,
                        source_versions, generated_at, cache_status, payload, raw_payload
                    )
                    values (
                        %(row_id)s, %(scope_key)s, %(scope_month)s::date, %(invoice_id)s, %(invoice_identity_key)s,
                        %(invoice_no)s, %(invoice_date)s::date, %(seller_name)s, %(seller_tax_no)s, %(buyer_name)s,
                        %(buyer_tax_no)s, %(total_with_tax)s, %(amount)s, %(tax_amount)s, %(tax_rate)s,
                        %(specific_business_type)s, %(taxable_item_name)s, %(payment_status)s, %(payment_status_label)s,
                        %(collection_status)s, %(collection_status_label)s, %(collected_amount)s, %(pending_amount)s,
                        %(oa_applicant)s, %(oa_application_type)s, %(oa_project_name)s, %(bank_counterparty_name)s,
                        %(bank_trade_time)s::timestamptz, %(bank_amount)s, %(bank_name)s, %(bank_account)s,
                        %(bank_direction)s, %(bank_summary)s,
                        %(receipt_status)s, %(receipt_status_label)s, %(oa_relation_count)s, %(bank_relation_count)s,
                        %(red_invoice_relation_count)s, %(searchable_text)s, %(source_versions)s,
                        coalesce(%(generated_at)s::timestamptz, now()), %(cache_status)s, %(payload)s, %(raw_payload)s
                    )
                    on conflict (row_id, scope_key) do update set
                        scope_month = excluded.scope_month,
                        invoice_id = excluded.invoice_id,
                        invoice_identity_key = excluded.invoice_identity_key,
                        invoice_no = excluded.invoice_no,
                        invoice_date = excluded.invoice_date,
                        seller_name = excluded.seller_name,
                        seller_tax_no = excluded.seller_tax_no,
                        buyer_name = excluded.buyer_name,
                        buyer_tax_no = excluded.buyer_tax_no,
                        total_with_tax = excluded.total_with_tax,
                        amount = excluded.amount,
                        tax_amount = excluded.tax_amount,
                        tax_rate = excluded.tax_rate,
                        specific_business_type = excluded.specific_business_type,
                        taxable_item_name = excluded.taxable_item_name,
                        payment_status = excluded.payment_status,
                        payment_status_label = excluded.payment_status_label,
                        collection_status = excluded.collection_status,
                        collection_status_label = excluded.collection_status_label,
                        collected_amount = excluded.collected_amount,
                        pending_amount = excluded.pending_amount,
                        oa_applicant = excluded.oa_applicant,
                        oa_application_type = excluded.oa_application_type,
                        oa_project_name = excluded.oa_project_name,
                        bank_counterparty_name = excluded.bank_counterparty_name,
                        bank_trade_time = excluded.bank_trade_time,
                        bank_amount = excluded.bank_amount,
                        bank_name = excluded.bank_name,
                        bank_account = excluded.bank_account,
                        bank_direction = excluded.bank_direction,
                        bank_summary = excluded.bank_summary,
                        receipt_status = excluded.receipt_status,
                        receipt_status_label = excluded.receipt_status_label,
                        oa_relation_count = excluded.oa_relation_count,
                        bank_relation_count = excluded.bank_relation_count,
                        red_invoice_relation_count = excluded.red_invoice_relation_count,
                        searchable_text = excluded.searchable_text,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    record,
                )
            self._upsert_invoice_relation_scope(
                connection,
                scope_table_name=scope_table_name,
                scope_key=normalized_scope_key,
                row_count=len(rows_to_save),
                scope_type=scope_type,
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def _mark_invoice_relation_scope(
        self,
        *,
        scope_table_name: str,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, Any] | None,
    ) -> None:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            self._upsert_invoice_relation_scope(
                connection,
                scope_table_name=scope_table_name,
                scope_key=normalized_scope_key,
                row_count=max(int_value(row_count, 0), 0),
                scope_type="",
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    @staticmethod
    def _upsert_invoice_relation_scope(
        connection: Any,
        *,
        scope_table_name: str,
        scope_key: str,
        row_count: int,
        scope_type: str,
        source_versions: dict[str, Any],
    ) -> None:
        connection.execute(
            f"""
            insert into {scope_table_name}(
                scope_key, scope_month, row_count, generated_at, cache_status, source_versions, raw_payload
            )
            values (%s, %s::date, %s, now(), 'fresh', %s, %s)
            on conflict (scope_key) do update set
                scope_month = excluded.scope_month,
                row_count = excluded.row_count,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                scope_key,
                month_start(scope_key) if MONTH_SCOPE_RE.match(scope_key) else None,
                row_count,
                jsonb(source_versions),
                jsonb({"scope_type": scope_type, "scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}),
            ),
        )

    def _invoice_relation_scope_row(self, *, scope_table_name: str, scope_key: str) -> dict[str, Any] | None:
        if scope_key == "all":
            rows = self._connection.fetch_all(
                f"""
                select scope_key, row_count, source_versions, cache_status
                from {scope_table_name}
                where scope_key <> 'all'
                order by generated_at desc, scope_key desc
                """
            )
            if not rows:
                row = self._connection.fetch_one(
                    f"select scope_key, source_versions, cache_status from {scope_table_name} where scope_key = 'all' limit 1"
                )
                return dict(row) if isinstance(row, dict) else None
            rows_for_all_status = self._invoice_relation_all_scope_effective_rows(rows)
            for row in rows_for_all_status:
                if not isinstance(row, dict):
                    continue
                if text(row.get("cache_status")) not in {"", "fresh"}:
                    return {"scope_key": "all", "source_versions": {}}
            return {"scope_key": "all", "source_versions": self._common_source_versions(rows_for_all_status)}
        row = self._connection.fetch_one(
            f"select scope_key, source_versions from {scope_table_name} where scope_key = %s limit 1",
            (scope_key,),
        )
        return dict(row) if isinstance(row, dict) else None

    def _invoice_relation_refresh_status(self, *, scope_type: str, scope_key: str) -> str:
        if scope_key != "all":
            return self._refresh_status(scope_type=scope_type, scope_key=scope_key)
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = %s
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """,
            (scope_type,),
        )
        if dirty_row is None:
            return "fresh"
        return "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"

    @staticmethod
    def _invoice_relation_all_scope_effective_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        non_empty_rows = [row for row in rows if isinstance(row, dict) and int_value(row.get("row_count"), 0) > 0]
        return non_empty_rows or rows

    @staticmethod
    def _common_source_versions(rows: list[dict[str, Any]]) -> dict[str, Any]:
        common_versions: dict[str, Any] | None = None
        for row in rows:
            if not isinstance(row, dict):
                continue
            row_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
            if common_versions is None:
                common_versions = deepcopy(row_versions)
                continue
            for key in list(common_versions):
                if row_versions.get(key) != common_versions[key]:
                    common_versions.pop(key, None)
        return common_versions or {}

    def list_pending_invoice_rows(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        sort_field: str | None = None,
        sort_direction: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any] | None:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter or "all").strip() or "all"
        page_number = max(int_value(page, 1), 1)
        page_limit = min(max(int_value(page_size, 50), 1), 200)
        if normalized_direction == "all" and normalized_filter != "all":
            raise ValueError("all direction only supports filter=all.")
        where: list[str] = []
        params: list[Any] = []
        if normalized_direction != "all":
            where.append("direction = %s")
            params.append(normalized_direction)
        if normalized_filter != "all":
            clause, clause_params = _pending_invoice_visible_filter_clause(
                direction=normalized_direction,
                filter_name=normalized_filter,
            )
            where.append(clause)
            params.extend(clause_params)
        if date_from:
            where.append("trade_date >= %s::date")
            params.append(date_from)
        if date_to:
            where.append("trade_date <= %s::date")
            params.append(date_to)
        if keyword:
            where.append("searchable_text ilike %s")
            params.append(f"%{keyword}%")
        for clause, clause_params in _pending_invoice_filter_clauses(filters):
            where.append(clause)
            params.extend(clause_params)
        where_sql = " and ".join(where) if where else "true"
        order_sql = _pending_invoice_order_sql(sort_field=sort_field, sort_direction=sort_direction)
        scope_key = f"{normalized_direction}:{normalized_filter}"
        with self._connection.transaction() as connection:
            total_row = connection.fetch_one(
                f"select count(*) as count from read_model.pending_invoice_rows where {where_sql}",
                tuple(params),
            )
            total = int_value(total_row.get("count") if isinstance(total_row, dict) else 0, 0)
            if normalized_direction == "all":
                direction_scope_rows = [
                    self._pending_invoice_scope_row("expense:all", connection=connection),
                    self._pending_invoice_scope_row("income:all", connection=connection),
                ]
                direction_refresh_statuses = [
                    self._refresh_status(scope_type="pending_invoice", scope_key="expense:all", connection=connection),
                    self._refresh_status(scope_type="pending_invoice", scope_key="income:all", connection=connection),
                ]
                refresh_status = "refreshing" if "refreshing" in direction_refresh_statuses else ("stale" if "stale" in direction_refresh_statuses else "fresh")
                scope_row = next((row for row in direction_scope_rows if isinstance(row, dict)), None)
            else:
                refresh_status = self._refresh_status(
                    scope_type="pending_invoice",
                    scope_key=scope_key,
                    connection=connection,
                )
                scope_row = self._pending_invoice_scope_row(scope_key, connection=connection)
            source_versions = (
                scope_row.get("source_versions")
                if isinstance(scope_row, dict) and isinstance(scope_row.get("source_versions"), dict)
                else {}
            )
            if total == 0:
                if scope_row is None:
                    return None
                return {
                    "direction": normalized_direction,
                    "filter": normalized_filter,
                    "rows": [],
                    "pagination": {"page": page_number, "page_size": page_limit, "total": 0},
                    "summary": {
                        "total_rows": 0,
                        "missing_invoice_rows": 0,
                        "create_invoice_available_rows": 0,
                        "source_summary": self._pending_invoice_source_summary(
                            direction=normalized_direction,
                            date_from=date_from,
                            date_to=date_to,
                            connection=connection,
                        ),
                    },
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": refresh_status,
                    "source_versions": source_versions,
                }
            rows = connection.fetch_all(
                f"""
                select payload, raw_payload, missing_invoice, can_create_invoice
                from read_model.pending_invoice_rows
                where {where_sql}
                order by {order_sql}
                limit %s offset %s
                """,
                tuple([*params, page_limit, (page_number - 1) * page_limit]),
            )
            payload_rows = [_read_model_payload(row) for row in rows]
            normalized_rows = [row for row in payload_rows if isinstance(row, dict)]
            return {
                "direction": normalized_direction,
                "filter": normalized_filter,
                "rows": normalized_rows,
                "pagination": {"page": page_number, "page_size": page_limit, "total": total},
                "summary": {
                    "total_rows": total,
                    "missing_invoice_rows": sum(1 for row in rows if bool(row.get("missing_invoice"))),
                    "create_invoice_available_rows": sum(1 for row in rows if bool(row.get("can_create_invoice"))),
                    "source_summary": self._pending_invoice_source_summary(
                        direction=normalized_direction,
                        date_from=date_from,
                        date_to=date_to,
                        connection=connection,
                    ),
                },
                "bank_transaction_tags": {},
                "bank_transaction_tags_version": 1,
                "refresh_status": refresh_status,
                "source_versions": source_versions,
            }

    def list_pending_invoice_filter_options(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter or "all").strip() or "all"
        if normalized_direction == "all" and normalized_filter != "all":
            raise ValueError("all direction only supports filter=all.")
        where: list[str] = []
        params: list[Any] = []
        if normalized_direction != "all":
            where.append("direction = %s")
            params.append(normalized_direction)
        if normalized_filter != "all":
            clause, clause_params = _pending_invoice_visible_filter_clause(
                direction=normalized_direction,
                filter_name=normalized_filter,
            )
            where.append(clause)
            params.extend(clause_params)
        if date_from:
            where.append("trade_date >= %s::date")
            params.append(date_from)
        if date_to:
            where.append("trade_date <= %s::date")
            params.append(date_to)
        if keyword:
            where.append("searchable_text ilike %s")
            params.append(f"%{keyword}%")
        for clause, clause_params in _pending_invoice_filter_clauses(filters):
            where.append(clause)
            params.extend(clause_params)
        where_sql = " and ".join(where) if where else "true"
        option_values = ",\n                    ".join(
            f"('{field}', {_pending_invoice_option_expression(field)})"
            for field in PENDING_INVOICE_FILTER_FIELDS
        )
        rows = self._connection.fetch_all(
            f"""
            with filtered_rows as (
                select
                    direction,
                    filter_group,
                    trade_date,
                    counterparty_name,
                    amount,
                    status_code,
                    seller_name,
                    invoice_total,
                    oa_applicant,
                    project_name,
                    payload
                from read_model.pending_invoice_rows
                where {where_sql}
            ),
            option_values(field, value) as (
                select option_value.field, nullif(btrim(option_value.value), '') as value
                from filtered_rows
                cross join lateral (
                    values
                    {option_values}
                ) as option_value(field, value)
            ),
            option_counts as (
                select field, value, count(*)::integer as option_count
                from option_values
                where value is not null
                group by field, value
            ),
            ranked_options as (
                select
                    field,
                    value,
                    option_count,
                    row_number() over (partition by field order by option_count desc, value) as option_rank
                from option_counts
            )
            select field, value, option_count
            from ranked_options
            where option_rank <= 50
            order by field, option_rank
            """,
            tuple(params),
        )
        options: dict[str, list[dict[str, Any]]] = {field: [] for field in PENDING_INVOICE_FILTER_FIELDS}
        for row in rows:
            field = text(row.get("field")) or ""
            value = text(row.get("value")) or ""
            if field not in options or not value:
                continue
            count = int_value(row.get("option_count"), 0)
            options[field].append({"value": value, "label": value, "count": count})
        return {"direction": normalized_direction, "filter": normalized_filter, "options": options}

    def save_pending_invoice_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        normalized_direction, normalized_filter, scope_month = _parse_pending_invoice_scope_key(scope_key)
        rows_to_save = list(rows or [])
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if scope_month:
                connection.execute(
                    """
                    delete from read_model.pending_invoice_rows
                    where direction = %s
                      and scope_month = %s::date
                      and (%s = 'all' or filter_group = %s)
                    """,
                    (normalized_direction, scope_month, normalized_filter, normalized_filter),
                )
            else:
                connection.execute(
                    "delete from read_model.pending_invoice_rows where direction = %s and (%s = 'all' or filter_group = %s)",
                    (normalized_direction, normalized_filter, normalized_filter),
                )
            for row in rows_to_save:
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["source_versions"] = normalized_source_versions
                payload = serialize_value(row_payload.get("payload") if isinstance(row_payload.get("payload"), dict) else row_payload)
                bank_transaction = payload.get("bank_transaction") if isinstance(payload.get("bank_transaction"), dict) else {}
                status = payload.get("invoice_acquisition_status") if isinstance(payload.get("invoice_acquisition_status"), dict) else {}
                input_invoices = payload.get("input_invoices") if isinstance(payload.get("input_invoices"), dict) else {}
                primary_invoice = (
                    input_invoices.get("primary")
                    if isinstance(input_invoices.get("primary"), dict)
                    else {}
                )
                payment_summary = (
                    input_invoices.get("payment_summary")
                    if isinstance(input_invoices.get("payment_summary"), dict)
                    else {}
                )
                oa = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
                primary_oa = oa.get("primary") if isinstance(oa.get("primary"), dict) else {}
                row_scope_month = scope_month or month_start(bank_transaction.get("trade_time"))
                row_filter_group = text(row_payload.get("filter_group") or payload.get("filter_group") or normalized_filter) or "all"
                row_scope_key = _pending_invoice_row_scope_key(
                    direction=normalized_direction,
                    filter_group=row_filter_group,
                    scope_month=row_scope_month,
                )
                connection.execute(
                    """
                    insert into read_model.pending_invoice_rows(
                        row_id, direction, filter_group, scope_month, trade_date, counterparty_name,
                        amount, status_code, seller_name, invoice_total, oa_applicant, project_name,
                        missing_invoice, can_create_invoice, searchable_text, scope_key, generated_at, payload, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s)
                    on conflict (row_id, direction) do update set
                        filter_group = excluded.filter_group,
                        scope_month = excluded.scope_month,
                        trade_date = excluded.trade_date,
                        counterparty_name = excluded.counterparty_name,
                        amount = excluded.amount,
                        status_code = excluded.status_code,
                        seller_name = excluded.seller_name,
                        invoice_total = excluded.invoice_total,
                        oa_applicant = excluded.oa_applicant,
                        project_name = excluded.project_name,
                        missing_invoice = excluded.missing_invoice,
                        can_create_invoice = excluded.can_create_invoice,
                        searchable_text = excluded.searchable_text,
                        scope_key = excluded.scope_key,
                        generated_at = excluded.generated_at,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        text(payload.get("id")),
                        normalized_direction,
                        row_filter_group,
                        row_scope_month,
                        text(bank_transaction.get("trade_time"))[:10] if text(bank_transaction.get("trade_time")) else None,
                        text(bank_transaction.get("counterparty_name")),
                        decimal_text(bank_transaction.get("amount")),
                        text(status.get("code")),
                        text(primary_invoice.get("seller_name")),
                        decimal_text(payment_summary.get("invoice_total") or primary_invoice.get("total_with_tax")),
                        text(primary_oa.get("applicant") or payload.get("oa_applicant")),
                        text(primary_oa.get("project_name")),
                        not bool(payload.get("invoices")),
                        bool(payload.get("can_create_invoice")),
                        text(row_payload.get("searchable_text") or payload),
                        row_scope_key,
                        text(row_payload.get("generated_at")),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            self._upsert_pending_invoice_scope(
                connection,
                scope_key=scope_key,
                direction=normalized_direction,
                filter_group=normalized_filter,
                row_count=len(rows_to_save),
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def mark_pending_invoice_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
    ) -> None:
        normalized_direction, normalized_filter, _scope_month = _parse_pending_invoice_scope_key(scope_key)
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            self._upsert_pending_invoice_scope(
                connection,
                scope_key=str(scope_key or "").strip() or f"{normalized_direction}:{normalized_filter}",
                direction=normalized_direction,
                filter_group=normalized_filter,
                row_count=max(int_value(row_count, 0), 0),
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def save_invoice_lifecycle_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> None:
        normalized_scope_key = text(scope_key) or ""
        if not normalized_scope_key:
            raise ValueError("invoice lifecycle scope_key is required.")
        scope_month = month_start(normalized_scope_key)
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}
        rows_to_save = [row for row in list(rows or []) if isinstance(row, dict)]

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.invoice_lifecycle_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            insert_rows: list[tuple[Any, ...]] = []
            for row in rows_to_save:
                payload = _invoice_lifecycle_row_payload(row)
                row_scope_month = month_start(payload.get("scope_month") or normalized_scope_key) or scope_month
                insert_rows.append(
                    (
                        tenant_id,
                        text(payload.get("subject_id")),
                        text(payload.get("subject_type")),
                        normalized_scope_key,
                        row_scope_month,
                        text(payload.get("invoice_identity_key")),
                        text(payload.get("lifecycle_status")) or "unknown",
                        jsonb(payload.get("acquisition_status") if isinstance(payload.get("acquisition_status"), dict) else {}),
                        jsonb(payload.get("payment_status") if isinstance(payload.get("payment_status"), dict) else {}),
                        jsonb(payload.get("collection_status") if isinstance(payload.get("collection_status"), dict) else {}),
                        jsonb(payload.get("certification_status") if isinstance(payload.get("certification_status"), dict) else {}),
                        jsonb(normalized_source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload, "source_versions": normalized_source_versions}),
                        text(row.get("generated_at")),
                    )
                )
            _execute_many(
                connection,
                """
                    insert into read_model.invoice_lifecycle_rows(
                        tenant_id, subject_id, subject_type, scope_key, scope_month, invoice_identity_key,
                        lifecycle_status, acquisition_status, payment_status, collection_status, certification_status,
                        source_versions, payload, raw_payload, generated_at
                    )
                    values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()))
                    on conflict (tenant_id, subject_type, subject_id) do update set
                        scope_key = excluded.scope_key,
                        scope_month = excluded.scope_month,
                        invoice_identity_key = excluded.invoice_identity_key,
                        lifecycle_status = excluded.lifecycle_status,
                        acquisition_status = excluded.acquisition_status,
                        payment_status = excluded.payment_status,
                        collection_status = excluded.collection_status,
                        certification_status = excluded.certification_status,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        generated_at = excluded.generated_at,
                        updated_at = now()
                """,
                insert_rows,
            )
            self._upsert_invoice_lifecycle_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=scope_month,
                row_count=len(rows_to_save),
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def mark_invoice_lifecycle_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> None:
        normalized_scope_key = text(scope_key) or ""
        if not normalized_scope_key:
            raise ValueError("invoice lifecycle scope_key is required.")
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.invoice_lifecycle_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            self._upsert_invoice_lifecycle_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=month_start(normalized_scope_key),
                row_count=row_count,
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def get_invoice_lifecycle_rows_by_subject_ids(
        self,
        subject_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_ids = _dedupe_preserve_order(text(subject_id) for subject_id in list(subject_ids or []))
        if not normalized_ids:
            return {
                "read_model_status": "fresh",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "stale_reasons": [],
            }
        rows = self._connection.fetch_all(
            """
            select subject_id, subject_type, scope_key, scope_month, invoice_identity_key, lifecycle_status,
                   acquisition_status, payment_status, collection_status, certification_status,
                   source_versions, payload, raw_payload
            from read_model.invoice_lifecycle_rows
            where tenant_id = %s
              and subject_id = any(%s)
            order by array_position(%s::text[], subject_id), subject_type
            """,
            (tenant_id, normalized_ids, normalized_ids),
        )
        if not rows:
            return None
        returned_ids = {text(row.get("subject_id")) for row in rows if text(row.get("subject_id"))}
        if len(returned_ids) < len(normalized_ids):
            return {
                "read_model_status": "missing",
                "rows": [],
                "source_versions": _source_versions_from_relation_records(rows),
                "read_model_scope_keys": _dedupe_preserve_order(text(row.get("scope_key")) for row in rows),
                "stale_reasons": ["missing_invoice_lifecycle_rows"],
            }
        return self._invoice_lifecycle_payload_from_rows(rows=rows, tenant_id=tenant_id)

    def get_invoice_lifecycle_rows_by_identity_keys(
        self,
        invoice_identity_keys: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_keys = _dedupe_preserve_order(text(key) for key in list(invoice_identity_keys or []))
        if not normalized_keys:
            return {
                "read_model_status": "fresh",
                "rows": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "stale_reasons": [],
            }
        rows = self._connection.fetch_all(
            """
            select subject_id, subject_type, scope_key, scope_month, invoice_identity_key, lifecycle_status,
                   acquisition_status, payment_status, collection_status, certification_status,
                   source_versions, payload, raw_payload
            from read_model.invoice_lifecycle_rows
            where tenant_id = %s
              and invoice_identity_key = any(%s)
            order by array_position(%s::text[], invoice_identity_key), subject_type, subject_id
            """,
            (tenant_id, normalized_keys, normalized_keys),
        )
        if not rows:
            return None
        return self._invoice_lifecycle_payload_from_rows(rows=rows, tenant_id=tenant_id)

    def list_invoice_lifecycle_rows(
        self,
        *,
        month: str,
        subject_types: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_month = text(month) or ""
        if not normalized_month:
            return None
        scope_row = self._invoice_lifecycle_scope_row(scope_key=normalized_month, tenant_id=tenant_id)
        if scope_row is None:
            return None
        where = ["tenant_id = %s", "scope_key = %s"]
        params: list[Any] = [tenant_id, normalized_month]
        normalized_subject_types = _dedupe_preserve_order(text(subject_type) for subject_type in list(subject_types or []))
        if normalized_subject_types:
            where.append("subject_type = any(%s)")
            params.append(normalized_subject_types)
        rows = self._connection.fetch_all(
            f"""
            select subject_id, subject_type, scope_key, scope_month, invoice_identity_key, lifecycle_status,
                   acquisition_status, payment_status, collection_status, certification_status,
                   source_versions, payload, raw_payload
            from read_model.invoice_lifecycle_rows
            where {" and ".join(where)}
            order by subject_type, subject_id
            """,
            tuple(params),
        )
        return self._invoice_lifecycle_payload_from_rows(
            rows=rows,
            tenant_id=tenant_id,
            fallback_source_versions=scope_row.get("source_versions") if isinstance(scope_row.get("source_versions"), dict) else {},
            fallback_scope_keys=[normalized_month],
        )

    def _invoice_lifecycle_scope_row(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
        connection: Any | None = None,
    ) -> dict[str, Any] | None:
        executor = connection or self._connection
        return executor.fetch_one(
            """
            select scope_key, row_count, source_versions, cache_status
            from read_model.invoice_lifecycle_scopes
            where tenant_id = %s
              and scope_key = %s
            """,
            (tenant_id, scope_key),
        )

    def _invoice_lifecycle_payload_from_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        tenant_id: str,
        fallback_source_versions: dict[str, Any] | None = None,
        fallback_scope_keys: list[str] | None = None,
    ) -> dict[str, Any]:
        scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in rows) or list(fallback_scope_keys or [])
        status = "fresh"
        stale_reasons: list[str] = []
        source_versions = dict(fallback_source_versions or {})
        for scope_key in scope_keys:
            scope_row = self._invoice_lifecycle_scope_row(scope_key=scope_key, tenant_id=tenant_id)
            if scope_row is None:
                status = "missing"
                stale_reasons.append(f"missing_scope:{scope_key}")
                continue
            scope_status = self._refresh_status(scope_type="invoice_lifecycle", scope_key=scope_key)
            if scope_status != "fresh":
                status = "refreshing" if scope_status == "refreshing" else "stale"
                stale_reasons.append(f"{scope_status}:{scope_key}")
            if not source_versions and isinstance(scope_row.get("source_versions"), dict):
                source_versions = dict(scope_row.get("source_versions"))
        if not source_versions:
            source_versions = _source_versions_from_relation_records(rows)
        return {
            "read_model_status": status,
            "rows": [_invoice_lifecycle_row_payload(row) for row in rows],
            "source_versions": source_versions,
            "read_model_scope_keys": scope_keys,
            "stale_reasons": stale_reasons,
        }

    @staticmethod
    def _upsert_invoice_lifecycle_scope(
        connection: Any,
        *,
        tenant_id: str,
        scope_key: str,
        scope_month: date | str | None,
        row_count: int,
        source_versions: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            insert into read_model.invoice_lifecycle_scopes(
                tenant_id, scope_key, scope_month, row_count, generated_at, cache_status, source_versions, raw_payload
            )
            values (%s, %s, %s::date, %s, now(), 'fresh', %s, %s)
            on conflict (tenant_id, scope_key) do update set
                scope_month = excluded.scope_month,
                row_count = excluded.row_count,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                tenant_id,
                scope_key,
                scope_month,
                max(int_value(row_count, 0), 0),
                jsonb(source_versions),
                jsonb({"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}),
            ),
        )

    def save_workbench_relation_distribution(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> None:
        normalized_scope_key = text(scope_key) or ""
        if not normalized_scope_key:
            raise ValueError("workbench relation distribution scope_key is required.")
        scope_month = month_start(normalized_scope_key)
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}
        rows_to_save = [row for row in list(rows or []) if isinstance(row, dict)]
        groups_to_save = [group for group in list(groups or []) if isinstance(group, dict)]

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.workbench_relation_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            connection.execute(
                "delete from read_model.workbench_relation_groups where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            for group in groups_to_save:
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else group
                connection.execute(
                    """
                    insert into read_model.workbench_relation_groups(
                        tenant_id, group_id, scope_key, scope_month, relation_source, relation_kind, relation_status,
                        oa_row_ids, bank_transaction_ids, input_invoice_ids, output_invoice_ids,
                        source_versions, payload, raw_payload, generated_at
                    )
                    values (%s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()))
                    on conflict (tenant_id, scope_key, group_id) do update set
                        relation_source = excluded.relation_source,
                        relation_kind = excluded.relation_kind,
                        relation_status = excluded.relation_status,
                        oa_row_ids = excluded.oa_row_ids,
                        bank_transaction_ids = excluded.bank_transaction_ids,
                        input_invoice_ids = excluded.input_invoice_ids,
                        output_invoice_ids = excluded.output_invoice_ids,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        generated_at = excluded.generated_at,
                        updated_at = now()
                    """,
                    (
                        tenant_id,
                        text(group.get("group_id")),
                        normalized_scope_key,
                        scope_month,
                        text(group.get("relation_source")) or "manual",
                        text(group.get("relation_kind")) or "linked",
                        text(group.get("relation_status")) or "linked",
                        text_list(group.get("oa_row_ids")),
                        text_list(group.get("bank_transaction_ids")),
                        text_list(group.get("input_invoice_ids")),
                        text_list(group.get("output_invoice_ids")),
                        jsonb(normalized_source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload, "source_versions": normalized_source_versions}),
                        text(group.get("generated_at")),
                    ),
                )
            for row in rows_to_save:
                payload = _workbench_relation_row_payload(row)
                row_scope_month = month_start(row.get("scope_month") or normalized_scope_key) or scope_month
                connection.execute(
                    """
                    insert into read_model.workbench_relation_rows(
                        tenant_id, row_id, row_type, scope_key, scope_month, relation_status, group_ids,
                        linked_oa, linked_bank_transactions, linked_input_invoices, linked_output_invoices,
                        source_versions, payload, raw_payload, generated_at
                    )
                    values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()))
                    on conflict (tenant_id, row_id) do update set
                        row_type = excluded.row_type,
                        scope_key = excluded.scope_key,
                        scope_month = excluded.scope_month,
                        relation_status = excluded.relation_status,
                        group_ids = excluded.group_ids,
                        linked_oa = excluded.linked_oa,
                        linked_bank_transactions = excluded.linked_bank_transactions,
                        linked_input_invoices = excluded.linked_input_invoices,
                        linked_output_invoices = excluded.linked_output_invoices,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        generated_at = excluded.generated_at,
                        updated_at = now()
                    """,
                    (
                        tenant_id,
                        text(payload.get("row_id")),
                        text(payload.get("row_type")),
                        normalized_scope_key,
                        row_scope_month,
                        text(payload.get("relation_status")) or "unlinked",
                        text_list(payload.get("group_ids")),
                        jsonb(payload.get("linked_oa") if isinstance(payload.get("linked_oa"), list) else []),
                        jsonb(
                            payload.get("linked_bank_transactions")
                            if isinstance(payload.get("linked_bank_transactions"), list)
                            else []
                        ),
                        jsonb(
                            payload.get("linked_input_invoices")
                            if isinstance(payload.get("linked_input_invoices"), list)
                            else []
                        ),
                        jsonb(
                            payload.get("linked_output_invoices")
                            if isinstance(payload.get("linked_output_invoices"), list)
                            else []
                        ),
                        jsonb(normalized_source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload, "source_versions": normalized_source_versions}),
                        text(row.get("generated_at")),
                    ),
                )
            self._upsert_workbench_relation_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=scope_month,
                row_count=len(rows_to_save),
                group_count=len(groups_to_save),
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def mark_workbench_relation_scope_empty(
        self,
        *,
        scope_key: str,
        source_versions: dict[str, Any] | None = None,
        tenant_id: str = "default",
    ) -> None:
        normalized_scope_key = text(scope_key) or ""
        if not normalized_scope_key:
            raise ValueError("workbench relation distribution scope_key is required.")
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.workbench_relation_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            connection.execute(
                "delete from read_model.workbench_relation_groups where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            self._upsert_workbench_relation_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=month_start(normalized_scope_key),
                row_count=0,
                group_count=0,
                source_versions=normalized_source_versions,
            )

        run_in_transaction(self._connection, write)

    def get_workbench_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any] | None:
        normalized_ids = _dedupe_preserve_order(text(row_id) for row_id in list(row_ids or []))
        if not normalized_ids:
            return {
                "read_model_status": "fresh",
                "rows": [],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "stale_reasons": [],
            }
        rows = self._connection.fetch_all(
            """
            select row_id, row_type, scope_key, scope_month, relation_status, group_ids,
                   linked_oa, linked_bank_transactions, linked_input_invoices, linked_output_invoices,
                   source_versions, payload, raw_payload
            from read_model.workbench_relation_rows
            where tenant_id = %s
              and row_id = any(%s)
            order by array_position(%s::text[], row_id)
            """,
            (tenant_id, normalized_ids, normalized_ids),
        )
        if not rows:
            scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys_hint or []))
            if scope_keys:
                return self._workbench_relation_payload_from_rows(
                    rows=[],
                    groups=[],
                    scope_keys=scope_keys,
                    tenant_id=tenant_id,
                    fallback_source_versions={},
                )
            return None
        returned_ids = {text(row.get("row_id")) for row in rows if text(row.get("row_id"))}
        if len(returned_ids) < len(normalized_ids):
            scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in rows)
            if self._workbench_relation_scope_keys_are_fresh(scope_keys=scope_keys, tenant_id=tenant_id):
                groups = self._workbench_relation_groups_for_scope_group_ids(
                    scope_keys=scope_keys,
                    group_ids=_dedupe_preserve_order(
                        group_id for row in rows for group_id in text_list(row.get("group_ids"))
                    ),
                    tenant_id=tenant_id,
                )
                return self._workbench_relation_payload_from_rows(
                    rows=rows,
                    groups=groups,
                    scope_keys=scope_keys,
                    tenant_id=tenant_id,
                )
            return {
                "read_model_status": "missing",
                "rows": [],
                "groups": [],
                "source_versions": _source_versions_from_relation_records(rows),
                "read_model_scope_keys": scope_keys,
                "stale_reasons": ["missing_relation_rows"],
            }
        scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in rows)
        groups = self._workbench_relation_groups_for_scope_group_ids(
            scope_keys=scope_keys,
            group_ids=_dedupe_preserve_order(group_id for row in rows for group_id in text_list(row.get("group_ids"))),
            tenant_id=tenant_id,
        )
        return self._workbench_relation_payload_from_rows(
            rows=rows,
            groups=groups,
            scope_keys=scope_keys,
            tenant_id=tenant_id,
        )

    def list_workbench_relation_rows(
        self,
        *,
        month: str,
        row_types: list[str] | None = None,
        relation_status: str | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_month = text(month) or ""
        if not normalized_month:
            return None
        where = ["tenant_id = %s", "scope_key = %s"]
        params: list[Any] = [tenant_id, normalized_month]
        normalized_row_types = _dedupe_preserve_order(text(row_type) for row_type in list(row_types or []))
        if normalized_row_types:
            where.append("row_type = any(%s)")
            params.append(normalized_row_types)
        if text(relation_status):
            where.append("relation_status = %s")
            params.append(text(relation_status))
        scope_row = self._workbench_relation_scope_row(scope_key=normalized_month, tenant_id=tenant_id)
        if scope_row is None:
            return None
        rows = self._connection.fetch_all(
            f"""
            select row_id, row_type, scope_key, scope_month, relation_status, group_ids,
                   linked_oa, linked_bank_transactions, linked_input_invoices, linked_output_invoices,
                   source_versions, payload, raw_payload
            from read_model.workbench_relation_rows
            where {" and ".join(where)}
            order by row_type, row_id
            """,
            tuple(params),
        )
        groups = self._workbench_relation_groups_for_scope_group_ids(
            scope_keys=[normalized_month],
            group_ids=_dedupe_preserve_order(group_id for row in rows for group_id in text_list(row.get("group_ids"))),
            tenant_id=tenant_id,
        )
        return self._workbench_relation_payload_from_rows(
            rows=rows,
            groups=groups,
            scope_keys=[normalized_month],
            tenant_id=tenant_id,
            fallback_source_versions=scope_row.get("source_versions") if isinstance(scope_row.get("source_versions"), dict) else {},
        )

    def get_workbench_relation_groups_by_ids(
        self,
        group_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
    ) -> dict[str, Any] | None:
        normalized_ids = _dedupe_preserve_order(text(group_id) for group_id in list(group_ids or []))
        if not normalized_ids:
            return {
                "read_model_status": "fresh",
                "rows": [],
                "groups": [],
                "source_versions": {},
                "read_model_scope_keys": [],
                "stale_reasons": [],
            }
        groups = self._connection.fetch_all(
            """
            select group_id, scope_key, scope_month, relation_source, relation_kind, relation_status,
                   oa_row_ids, bank_transaction_ids, input_invoice_ids, output_invoice_ids,
                   source_versions, payload, raw_payload
            from read_model.workbench_relation_groups
            where tenant_id = %s
              and group_id = any(%s)
            order by array_position(%s::text[], group_id)
            """,
            (tenant_id, normalized_ids, normalized_ids),
        )
        if not groups:
            scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys_hint or []))
            if scope_keys:
                return self._workbench_relation_payload_from_rows(
                    rows=[],
                    groups=[],
                    scope_keys=scope_keys,
                    tenant_id=tenant_id,
                    fallback_source_versions={},
                )
            return None
        scope_keys = _dedupe_preserve_order(text(group.get("scope_key")) for group in groups)
        return self._workbench_relation_payload_from_rows(
            rows=[],
            groups=groups,
            scope_keys=scope_keys,
            tenant_id=tenant_id,
            fallback_source_versions=_source_versions_from_relation_records(groups),
        )

    def _workbench_relation_scope_keys_are_fresh(self, *, scope_keys: list[str], tenant_id: str) -> bool:
        normalized_scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys or []))
        if not normalized_scope_keys:
            return False
        for scope_key in normalized_scope_keys:
            if self._workbench_relation_scope_row(scope_key=scope_key, tenant_id=tenant_id) is None:
                return False
            if self._refresh_status(scope_type="workbench_relation", scope_key=scope_key) != "fresh":
                return False
        return True

    def _workbench_relation_scope_row(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
        connection: Any | None = None,
    ) -> dict[str, Any] | None:
        executor = connection or self._connection
        return executor.fetch_one(
            """
            select scope_key, row_count, group_count, source_versions, cache_status
            from read_model.workbench_relation_scopes
            where tenant_id = %s
              and scope_key = %s
            """,
            (tenant_id, scope_key),
        )

    def workbench_relation_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        normalized_scope_key = text(scope_key) or "all"
        if normalized_scope_key == "all":
            rows = self._connection.fetch_all(
                """
                select scope_key, source_versions
                from read_model.workbench_relation_scopes
                where tenant_id = %s
                order by scope_key
                """,
                (tenant_id,),
            )
            return self._common_source_versions([dict(row) for row in rows if isinstance(row, dict)])
        scope_row = self._workbench_relation_scope_row(scope_key=normalized_scope_key, tenant_id=tenant_id)
        source_versions = scope_row.get("source_versions") if isinstance(scope_row, dict) else None
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def _workbench_relation_groups_for_scope_group_ids(
        self,
        *,
        scope_keys: list[str],
        group_ids: list[str],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        if not scope_keys or not group_ids:
            return []
        return self._connection.fetch_all(
            """
            select group_id, scope_key, scope_month, relation_source, relation_kind, relation_status,
                   oa_row_ids, bank_transaction_ids, input_invoice_ids, output_invoice_ids,
                   source_versions, payload, raw_payload
            from read_model.workbench_relation_groups
            where tenant_id = %s
              and scope_key = any(%s)
              and group_id = any(%s)
            order by scope_key, group_id
            """,
            (tenant_id, scope_keys, group_ids),
        )

    def _workbench_relation_payload_from_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        scope_keys: list[str],
        tenant_id: str,
        fallback_source_versions: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys or []))
        status = "fresh"
        stale_reasons: list[str] = []
        source_versions = dict(fallback_source_versions or {})
        for scope_key in normalized_scope_keys:
            scope_row = self._workbench_relation_scope_row(scope_key=scope_key, tenant_id=tenant_id)
            if scope_row is None:
                status = "missing"
                stale_reasons.append(f"missing_scope:{scope_key}")
                continue
            scope_status = self._refresh_status(scope_type="workbench_relation", scope_key=scope_key)
            if scope_status != "fresh":
                status = "refreshing" if scope_status == "refreshing" else "stale"
                stale_reasons.append(f"{scope_status}:{scope_key}")
            if not source_versions and isinstance(scope_row.get("source_versions"), dict):
                source_versions = dict(scope_row.get("source_versions"))
        if not source_versions:
            source_versions = _source_versions_from_relation_records(rows) or _source_versions_from_relation_records(groups)
        return {
            "read_model_status": status,
            "rows": [_workbench_relation_row_payload(row) for row in rows],
            "groups": [_workbench_relation_group_payload(group) for group in groups],
            "source_versions": source_versions,
            "read_model_scope_keys": normalized_scope_keys,
            "stale_reasons": stale_reasons,
        }

    @staticmethod
    def _upsert_workbench_relation_scope(
        connection: Any,
        *,
        tenant_id: str,
        scope_key: str,
        scope_month: date | str | None,
        row_count: int,
        group_count: int,
        source_versions: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            insert into read_model.workbench_relation_scopes(
                tenant_id, scope_key, scope_month, row_count, group_count, generated_at, cache_status, source_versions, raw_payload
            )
            values (%s, %s, %s::date, %s, %s, now(), 'fresh', %s, %s)
            on conflict (tenant_id, scope_key) do update set
                scope_month = excluded.scope_month,
                row_count = excluded.row_count,
                group_count = excluded.group_count,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                tenant_id,
                scope_key,
                scope_month,
                max(int_value(row_count, 0), 0),
                max(int_value(group_count, 0), 0),
                jsonb(source_versions),
                jsonb({"scope_key": scope_key, "row_count": row_count, "group_count": group_count, "source_versions": source_versions}),
            ),
        )

    def pending_invoice_source_summary(
        self,
        *,
        direction: str,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> dict[str, int]:
        return self._pending_invoice_source_summary(
            direction=direction,
            date_from=date_from,
            date_to=date_to,
        )

    def _pending_invoice_scope_row(self, scope_key: str, *, connection: Any | None = None) -> dict[str, Any] | None:
        executor = connection or self._connection
        rows = executor.fetch_all(
            """
            select scope_key, source_versions
            from read_model.pending_invoice_scopes
            where scope_key = %s
               or scope_key like %s
            order by scope_key
            """,
            (scope_key, f"{scope_key}:%"),
        )
        return _pending_invoice_scope_source_versions_row(scope_key=scope_key, rows=rows)

    def pending_invoice_bank_detail_source_versions(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter or "all").strip() or "all"
        if normalized_direction == "all" and normalized_filter != "all":
            raise ValueError("all direction only supports filter=all.")
        where: list[str] = []
        params: list[Any] = []
        if normalized_direction != "all":
            where.append("direction = %s")
            params.append(normalized_direction)
        if normalized_filter != "all":
            where.append("filter_group = %s")
            params.append(normalized_filter)
        if date_from:
            where.append("trade_date >= %s::date")
            params.append(date_from)
        if date_to:
            where.append("trade_date <= %s::date")
            params.append(date_to)
        if keyword:
            where.append("searchable_text ilike %s")
            params.append(f"%{keyword}%")
        for clause, clause_params in _pending_invoice_filter_clauses(filters):
            where.append(clause)
            params.extend(clause_params)
        where_sql = " and ".join(where) if where else "true"
        with self._connection.transaction() as connection:
            month_rows = connection.fetch_all(
                f"""
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from read_model.pending_invoice_rows
                where {where_sql}
                  and scope_month is not null
                order by scope_key
                """,
                tuple(params),
            )
            scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in month_rows)
            if not scope_keys:
                return {}
            scope_summary = self.bank_detail_scope_summary(
                scope_keys=scope_keys,
                tenant_id=tenant_id,
                connection=connection,
            )
        return _source_versions_from_scope_summary(scope_summary)

    def pending_invoice_workbench_relation_source_versions(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter or "all").strip() or "all"
        if normalized_direction == "all" and normalized_filter != "all":
            raise ValueError("all direction only supports filter=all.")
        where: list[str] = []
        params: list[Any] = []
        if normalized_direction != "all":
            where.append("direction = %s")
            params.append(normalized_direction)
        if normalized_filter != "all":
            where.append("filter_group = %s")
            params.append(normalized_filter)
        if date_from:
            where.append("trade_date >= %s::date")
            params.append(date_from)
        if date_to:
            where.append("trade_date <= %s::date")
            params.append(date_to)
        if keyword:
            where.append("searchable_text ilike %s")
            params.append(f"%{keyword}%")
        for clause, clause_params in _pending_invoice_filter_clauses(filters):
            where.append(clause)
            params.extend(clause_params)
        where_sql = " and ".join(where) if where else "true"
        with self._connection.transaction() as connection:
            month_rows = connection.fetch_all(
                f"""
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from read_model.pending_invoice_rows
                where {where_sql}
                  and scope_month is not null
                order by scope_key
                """,
                tuple(params),
            )
            scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in month_rows)
            if not scope_keys:
                return {}
            rows = connection.fetch_all(
                """
                select scope_key, source_versions
                from read_model.workbench_relation_scopes
                where tenant_id = %s
                  and scope_key = any(%s)
                order by scope_key
                """,
                (tenant_id, scope_keys),
            )
        return _scope_source_versions_by_month(rows)

    def _pending_invoice_source_summary(
        self,
        *,
        direction: str,
        date_from: str | None,
        date_to: str | None,
        connection: Any | None = None,
    ) -> dict[str, int]:
        where: list[str] = []
        params: list[Any] = []
        if date_from:
            where.append("trade_date >= %s::date")
            params.append(date_from)
        if date_to:
            where.append("trade_date <= %s::date")
            params.append(date_to)
        where_sql = f"where {' and '.join(where)}" if where else ""
        executor = connection or self._connection
        rows = executor.fetch_all(
            f"""
            select direction, count(*) as count
            from read_model.pending_invoice_rows
            {where_sql}
            group by direction
            """,
            tuple(params),
        )
        counts = {
            "expense": 0,
            "income": 0,
        }
        for row in rows:
            row_direction = text(row.get("direction")) or ""
            if row_direction in counts:
                counts[row_direction] = int_value(row.get("count"), 0)
        total = counts["expense"] + counts["income"]
        current = total if direction == "all" else counts.get(direction, 0)
        return {
            "bank_transaction_rows": total,
            "expense_rows": counts["expense"],
            "income_rows": counts["income"],
            "current_direction_rows": current,
            "excluded_direction_rows": max(total - current, 0),
        }

    @staticmethod
    def _upsert_pending_invoice_scope(
        connection: Any,
        *,
        scope_key: str,
        direction: str,
        filter_group: str,
        row_count: int,
        source_versions: dict[str, Any],
    ) -> None:
        connection.execute(
            """
            insert into read_model.pending_invoice_scopes(
                scope_key, direction, filter_group, row_count, generated_at, cache_status, source_versions, raw_payload
            )
            values (%s, %s, %s, %s, now(), 'fresh', %s, %s)
            on conflict (scope_key) do update set
                direction = excluded.direction,
                filter_group = excluded.filter_group,
                row_count = excluded.row_count,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                source_versions = excluded.source_versions,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                scope_key,
                direction,
                filter_group,
                row_count,
                jsonb(source_versions),
                jsonb({"scope_key": scope_key, "row_count": row_count, "source_versions": source_versions}),
            ),
        )

    def _refresh_status(self, *, scope_type: str, scope_key: str, connection: Any | None = None) -> str:
        executor = connection or self._connection
        dirty_row = executor.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = %s
              and scope_key = %s
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """,
            (scope_type, scope_key),
        )
        if dirty_row is None:
            return "fresh"
        return "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"

    @staticmethod
    def _new_workbench_generation_id(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        return f"workbench:{normalized_scope_key}:{uuid4().hex}"

    @staticmethod
    def _active_workbench_generation_id(executor: Any, *, scope_key: str) -> str | None:
        row = executor.fetch_one(
            """
            select generation_id
            from read_model.workbench_generations
            where tenant_id = 'default'
              and scope_key = %s
              and status = 'active'
            order by activated_at desc nulls last, completed_at desc nulls last, updated_at desc
            limit 1
            """,
            (scope_key,),
        )
        return text(row.get("generation_id")) if isinstance(row, dict) else None

    @staticmethod
    def _active_workbench_generation_source_versions(executor: Any, *, scope_key: str) -> dict[str, Any]:
        row = executor.fetch_one(
            """
            select source_versions
            from read_model.workbench_generations
            where tenant_id = 'default'
              and scope_key = %s
              and status = 'active'
            order by activated_at desc nulls last, completed_at desc nulls last, updated_at desc
            limit 1
            """,
            (scope_key,),
        )
        source_versions = row.get("source_versions") if isinstance(row, dict) else {}
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    @staticmethod
    def _workbench_generation_source_versions(
        executor: Any,
        *,
        scope_key: str,
        generation_id: str | None,
    ) -> dict[str, Any]:
        normalized_generation_id = text(generation_id)
        if not normalized_generation_id:
            return {}
        row = executor.fetch_one(
            """
            select source_versions
            from read_model.workbench_generations
            where tenant_id = 'default'
              and scope_key = %s
              and generation_id = %s
            limit 1
            """,
            (scope_key, normalized_generation_id),
        )
        source_versions = row.get("source_versions") if isinstance(row, dict) else {}
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    @staticmethod
    def _workbench_generation_metadata(executor: Any, *, scope_key: str) -> dict[str, Any]:
        rows = executor.fetch_all(
            """
            select
                generation_id,
                status,
                started_at::text as started_at,
                completed_at::text as completed_at,
                activated_at::text as activated_at,
                superseded_at::text as superseded_at,
                updated_at::text as updated_at,
                last_error,
                source_versions,
                row_count,
                group_count,
                build_metadata
            from read_model.workbench_generations
            where tenant_id = 'default'
              and scope_key = %s
              and status in ('active', 'building', 'failed')
            order by
                case status when 'active' then 0 when 'building' then 1 else 2 end,
                updated_at desc
            limit 10
            """,
            (scope_key,),
        )
        generations = [
            {
                "generation_id": text(row.get("generation_id")),
                "status": text(row.get("status")),
                "started_at": text(row.get("started_at")),
                "completed_at": text(row.get("completed_at")),
                "activated_at": text(row.get("activated_at")),
                "superseded_at": text(row.get("superseded_at")),
                "updated_at": text(row.get("updated_at")),
                "last_error": text(row.get("last_error")),
                "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
                "row_count": int_value(row.get("row_count"), 0),
                "group_count": int_value(row.get("group_count"), 0),
                "build_metadata": row.get("build_metadata") if isinstance(row.get("build_metadata"), dict) else {},
            }
            for row in rows
        ]
        active = next((generation for generation in generations if generation.get("status") == "active"), None)
        building = next((generation for generation in generations if generation.get("status") == "building"), None)
        failed = next((generation for generation in generations if generation.get("status") == "failed"), None)
        failed_is_relevant = PostgresReadModelRepository._workbench_failed_generation_is_relevant(
            active=active,
            failed=failed,
        )
        return {
            "generations": generations,
            "active_generation_id": active.get("generation_id") if active else None,
            "building_generation_id": building.get("generation_id") if building else None,
            "failed_generation_id": failed.get("generation_id") if failed else None,
            "failed_generation_is_relevant": failed_is_relevant,
            "generation_last_error": failed.get("last_error") if failed and failed_is_relevant else None,
            "read_model_version": active.get("generation_id") if active else None,
            "generated_at": active.get("activated_at") if active else None,
        }

    @staticmethod
    def _workbench_failed_generation_is_relevant(
        *,
        active: dict[str, Any] | None,
        failed: dict[str, Any] | None,
    ) -> bool:
        if failed is None:
            return False
        if active is None:
            return True
        active_source_version = int_value((active.get("source_versions") or {}).get("source_version"), 0)
        failed_source_version = int_value((failed.get("source_versions") or {}).get("source_version"), 0)
        if failed_source_version > active_source_version:
            return True
        active_timestamp = _parse_postgres_timestamp(
            text(active.get("activated_at")) or text(active.get("completed_at")) or text(active.get("updated_at"))
        )
        failed_timestamp = _parse_postgres_timestamp(
            text(failed.get("completed_at")) or text(failed.get("updated_at")) or text(failed.get("started_at"))
        )
        if active_timestamp is None or failed_timestamp is None:
            return False
        return failed_timestamp > active_timestamp

    @staticmethod
    def _workbench_generation_consistency_failures(
        executor: Any,
        *,
        scope_key: str | None = None,
        include_all: bool = True,
    ) -> list[dict[str, Any]]:
        clauses = ["gen.tenant_id = 'default'", "gen.status = 'active'"]
        params: list[Any] = []
        if scope_key:
            clauses.append("gen.scope_key = %s")
            params.append(scope_key)
        if not include_all:
            clauses.append("gen.scope_key <> 'all'")
        where_sql = " and ".join(clauses)
        rows = executor.fetch_all(
            f"""
            with target_generations as (
                select
                    gen.scope_key,
                    gen.generation_id,
                    gen.row_count,
                    gen.group_count,
                    gen.summary_count,
                    gen.build_metadata
                from read_model.workbench_generations gen
                where {where_sql}
            ),
            row_counts as (
                select r.generation_id, r.scope_key, count(distinct r.row_id)::bigint as actual_row_count
                from read_model.workbench_rows r
                join target_generations
                  on target_generations.generation_id = r.generation_id
                 and target_generations.scope_key = r.scope_key
                group by r.generation_id, r.scope_key
            ),
            group_counts as (
                select g.generation_id, g.scope_key, count(*)::bigint as actual_group_count
                from read_model.workbench_groups g
                join target_generations
                  on target_generations.generation_id = g.generation_id
                 and target_generations.scope_key = g.scope_key
                group by g.generation_id, g.scope_key
            ),
            group_row_counts as (
                select
                    gr.generation_id,
                    gr.scope_key,
                    count(distinct gr.row_id) filter (where coalesce(gr.row_role, '') <> 'summary')::bigint
                        as actual_group_row_count
                from read_model.workbench_group_rows gr
                join target_generations
                  on target_generations.generation_id = gr.generation_id
                 and target_generations.scope_key = gr.scope_key
                group by gr.generation_id, gr.scope_key
            ),
            summary_counts as (
                select s.generation_id, s.scope_key, count(*)::bigint as actual_summary_count
                from read_model.workbench_summary s
                join target_generations
                  on target_generations.generation_id = s.generation_id
                 and target_generations.scope_key = s.scope_key
                group by s.generation_id, s.scope_key
            ),
            duplicate_identity_counts as (
                select
                    duplicate_rows.generation_id,
                    duplicate_rows.scope_key,
                    count(*) filter (where duplicate_rows.object_kind = 'invoice')::bigint
                        as duplicate_invoice_identity_count,
                    count(*) filter (where duplicate_rows.object_kind = 'bank')::bigint
                        as duplicate_bank_identity_count,
                    jsonb_agg(
                        jsonb_build_object(
                            'object_kind', duplicate_rows.object_kind,
                            'object_identity_key', duplicate_rows.object_identity_key,
                            'object_identity_kind', duplicate_rows.object_identity_kind,
                            'zones', duplicate_rows.zones,
                            'row_ids', duplicate_rows.row_ids
                        )
                        order by duplicate_rows.object_kind, duplicate_rows.object_identity_key
                    ) as duplicate_identity_samples
                from (
                    select
                        gr.generation_id,
                        gr.scope_key,
                        case
                            when gr.pane = 'invoice'
                             and gr.object_identity_kind in ('digital_invoice_no', 'invoice_code_no')
                                then 'invoice'
                            when gr.pane = 'bank'
                             and gr.object_identity_kind = 'business_fields'
                                then 'bank'
                            else null
                        end as object_kind,
                        gr.object_identity_key,
                        gr.object_identity_kind,
                        array_agg(distinct gr.zone order by gr.zone) as zones,
                        array_agg(distinct gr.row_id order by gr.row_id) as row_ids
                    from read_model.workbench_group_rows gr
                    join target_generations
                      on target_generations.generation_id = gr.generation_id
                     and target_generations.scope_key = gr.scope_key
                    where gr.row_role <> 'summary'
                      and gr.object_identity_key is not null
                      and gr.zone in ('paired', 'open')
                    group by gr.generation_id, gr.scope_key, gr.pane, gr.object_identity_key, gr.object_identity_kind
                    having bool_or(gr.zone = 'paired') and bool_or(gr.zone = 'open')
                ) duplicate_rows
                where duplicate_rows.object_kind is not null
                group by duplicate_rows.generation_id, duplicate_rows.scope_key
            ),
            duplicate_row_membership_counts as (
                select
                    duplicate_rows.generation_id,
                    duplicate_rows.scope_key,
                    count(*)::bigint as duplicate_row_membership_count,
                    jsonb_agg(
                        jsonb_build_object(
                            'pane', duplicate_rows.pane,
                            'row_id', duplicate_rows.row_id,
                            'zones', duplicate_rows.zones,
                            'groups', duplicate_rows.groups
                        )
                        order by duplicate_rows.pane, duplicate_rows.row_id
                    ) as duplicate_row_membership_samples
                from (
                    select
                        gr.generation_id,
                        gr.scope_key,
                        gr.pane,
                        gr.row_id,
                        array_agg(distinct gr.zone order by gr.zone) as zones,
                        array_agg(distinct gr.zone || ':' || gr.group_id order by gr.zone || ':' || gr.group_id) as groups
                    from read_model.workbench_group_rows gr
                    join target_generations
                      on target_generations.generation_id = gr.generation_id
                     and target_generations.scope_key = gr.scope_key
                    where gr.row_role <> 'summary'
                      and gr.zone in ('paired', 'open')
                    group by gr.generation_id, gr.scope_key, gr.pane, gr.row_id
                    having count(distinct gr.zone || ':' || gr.group_id) > 1
                ) duplicate_rows
                group by duplicate_rows.generation_id, duplicate_rows.scope_key
            ),
            active_relation_open_membership_counts as (
                select
                    active_rows.generation_id,
                    active_rows.scope_key,
                    count(*)::bigint as active_relation_open_membership_count,
                    jsonb_agg(
                        jsonb_build_object(
                            'case_id', active_rows.case_id,
                            'pane', active_rows.pane,
                            'row_id', active_rows.row_id,
                            'group_id', active_rows.group_id
                        )
                        order by active_rows.case_id, active_rows.pane, active_rows.row_id
                    ) as active_relation_open_membership_samples
                from (
                    select distinct
                        gr.generation_id,
                        gr.scope_key,
                        rel.case_id,
                        gr.pane,
                        gr.row_id,
                        gr.group_id
                    from read_model.workbench_group_rows gr
                    join target_generations
                      on target_generations.generation_id = gr.generation_id
                     and target_generations.scope_key = gr.scope_key
                    join app.workbench_pair_relations rel
                      on rel.status = 'active'
                     and gr.row_id = any(rel.row_ids)
                    where coalesce(gr.row_role, '') <> 'summary'
                      and gr.zone = 'open'
                      and gr.row_id is not null
                      and (gr.group_id is null or gr.group_id <> ('case:' || rel.case_id))
                ) active_rows
                group by active_rows.generation_id, active_rows.scope_key
            )
            select
                gen.scope_key,
                gen.generation_id,
                gen.row_count,
                gen.group_count,
                gen.summary_count,
                gen.build_metadata,
                coalesce(row_counts.actual_row_count, 0)::bigint as actual_row_count,
                coalesce(group_counts.actual_group_count, 0)::bigint as actual_group_count,
                coalesce(group_row_counts.actual_group_row_count, 0)::bigint as actual_group_row_count,
                coalesce(summary_counts.actual_summary_count, 0)::bigint as actual_summary_count,
                coalesce(duplicate_identity_counts.duplicate_invoice_identity_count, 0)::bigint
                    as duplicate_invoice_identity_count,
                coalesce(duplicate_identity_counts.duplicate_bank_identity_count, 0)::bigint
                    as duplicate_bank_identity_count,
                coalesce(duplicate_identity_counts.duplicate_identity_samples, '[]'::jsonb)
                    as duplicate_identity_samples,
                coalesce(duplicate_row_membership_counts.duplicate_row_membership_count, 0)::bigint
                    as duplicate_row_membership_count,
                coalesce(duplicate_row_membership_counts.duplicate_row_membership_samples, '[]'::jsonb)
                    as duplicate_row_membership_samples,
                coalesce(active_relation_open_membership_counts.active_relation_open_membership_count, 0)::bigint
                    as active_relation_open_membership_count,
                coalesce(active_relation_open_membership_counts.active_relation_open_membership_samples, '[]'::jsonb)
                    as active_relation_open_membership_samples
            from target_generations gen
            left join row_counts
              on row_counts.generation_id = gen.generation_id
             and row_counts.scope_key = gen.scope_key
            left join group_counts
              on group_counts.generation_id = gen.generation_id
             and group_counts.scope_key = gen.scope_key
            left join group_row_counts
              on group_row_counts.generation_id = gen.generation_id
             and group_row_counts.scope_key = gen.scope_key
            left join summary_counts
              on summary_counts.generation_id = gen.generation_id
             and summary_counts.scope_key = gen.scope_key
            left join duplicate_identity_counts
              on duplicate_identity_counts.generation_id = gen.generation_id
             and duplicate_identity_counts.scope_key = gen.scope_key
            left join duplicate_row_membership_counts
              on duplicate_row_membership_counts.generation_id = gen.generation_id
             and duplicate_row_membership_counts.scope_key = gen.scope_key
            left join active_relation_open_membership_counts
              on active_relation_open_membership_counts.generation_id = gen.generation_id
             and active_relation_open_membership_counts.scope_key = gen.scope_key
            order by gen.scope_key
            """,
            tuple(params),
        )
        failures: list[dict[str, Any]] = []
        for row in rows:
            if "actual_group_count" not in row or "actual_group_row_count" not in row:
                continue
            build_metadata = row.get("build_metadata") if isinstance(row.get("build_metadata"), dict) else {}
            is_tombstone = build_metadata.get("tombstone") is True
            row_count = int_value(row.get("row_count"), 0)
            group_count = int_value(row.get("group_count"), 0)
            summary_count = int_value(row.get("summary_count"), 0)
            actual_group_count = int_value(row.get("actual_group_count"), 0)
            actual_group_row_count = int_value(row.get("actual_group_row_count"), 0)
            actual_summary_count = int_value(row.get("actual_summary_count"), 0)
            duplicate_invoice_identity_count = int_value(row.get("duplicate_invoice_identity_count"), 0)
            duplicate_bank_identity_count = int_value(row.get("duplicate_bank_identity_count"), 0)
            duplicate_row_membership_count = int_value(row.get("duplicate_row_membership_count"), 0)
            active_relation_open_membership_count = int_value(row.get("active_relation_open_membership_count"), 0)
            reasons: list[str] = []
            if group_count != actual_group_count:
                reasons.append(f"group_count metadata={group_count} actual={actual_group_count}")
            if row_count > 0 and actual_group_row_count == 0 and not is_tombstone:
                reasons.append(f"row_count metadata={row_count} actual_group_rows={actual_group_row_count}")
            if summary_count > 0 and actual_summary_count == 0 and not is_tombstone:
                reasons.append(f"summary_count metadata={summary_count} actual={actual_summary_count}")
            if duplicate_invoice_identity_count:
                reasons.append(f"duplicate_invoice_identity_cross_zone count={duplicate_invoice_identity_count}")
            if duplicate_bank_identity_count:
                reasons.append(f"duplicate_bank_identity_cross_zone count={duplicate_bank_identity_count}")
            if duplicate_row_membership_count:
                reasons.append(f"duplicate_row_membership count={duplicate_row_membership_count}")
            if active_relation_open_membership_count:
                reasons.append(f"active_relation_open_membership count={active_relation_open_membership_count}")
            if reasons:
                failures.append(
                    {
                        "scope_key": text(row.get("scope_key")),
                        "generation_id": text(row.get("generation_id")),
                        "row_count": row_count,
                        "group_count": group_count,
                        "summary_count": summary_count,
                        "actual_row_count": int_value(row.get("actual_row_count"), 0),
                        "actual_group_count": actual_group_count,
                        "actual_group_row_count": actual_group_row_count,
                        "actual_summary_count": actual_summary_count,
                        "duplicate_invoice_identity_count": duplicate_invoice_identity_count,
                        "duplicate_bank_identity_count": duplicate_bank_identity_count,
                        "duplicate_identity_samples": row.get("duplicate_identity_samples")
                        if isinstance(row.get("duplicate_identity_samples"), list)
                        else [],
                        "duplicate_row_membership_count": duplicate_row_membership_count,
                        "duplicate_row_membership_samples": row.get("duplicate_row_membership_samples")
                        if isinstance(row.get("duplicate_row_membership_samples"), list)
                        else [],
                        "active_relation_open_membership_count": active_relation_open_membership_count,
                        "active_relation_open_membership_samples": row.get("active_relation_open_membership_samples")
                        if isinstance(row.get("active_relation_open_membership_samples"), list)
                        else [],
                        "reasons": reasons,
                    }
                )
        return failures

    @staticmethod
    def _workbench_generation_consistency_error(failures: list[dict[str, Any]]) -> str:
        parts = []
        for failure in failures[:5]:
            scope_key = text(failure.get("scope_key")) or "unknown"
            generation_id = text(failure.get("generation_id")) or "unknown"
            reasons = failure.get("reasons") if isinstance(failure.get("reasons"), list) else []
            parts.append(f"{scope_key}/{generation_id}: {', '.join(str(reason) for reason in reasons)}")
        suffix = f"; +{len(failures) - 5} more" if len(failures) > 5 else ""
        return "generation_metadata_actual_mismatch: " + "; ".join(parts) + suffix

    @staticmethod
    def _lock_workbench_generation_scope(connection: Any, *, scope_key: str) -> None:
        connection.execute(
            "select pg_advisory_xact_lock(hashtext(%s))",
            (f"workbench_generation:{str(scope_key or 'all').strip() or 'all'}",),
        )

    @staticmethod
    def _start_workbench_generation(
        connection: Any,
        *,
        scope_key: str,
        generation_id: str,
        source_versions: dict[str, Any],
        generated_at: str | None,
        row_count: int,
        group_count: int,
        build_metadata: dict[str, Any] | None = None,
    ) -> None:
        connection.execute(
            """
            insert into read_model.workbench_generations(
                generation_id, tenant_id, scope_key, status, source_versions, started_at,
                row_count, group_count, build_metadata, consistency_status
            )
            values (%s, 'default', %s, 'building', %s, coalesce(%s::timestamptz, now()), %s, %s, %s, 'validating')
            on conflict (generation_id) do update set
                status = 'building',
                source_versions = excluded.source_versions,
                started_at = excluded.started_at,
                row_count = excluded.row_count,
                group_count = excluded.group_count,
                build_metadata = excluded.build_metadata,
                consistency_status = 'validating',
                last_error = null,
                error_reason = null,
                updated_at = now()
            """,
            (
                generation_id,
                scope_key,
                jsonb(source_versions),
                generated_at,
                max(row_count, 0),
                max(group_count, 0),
                jsonb(build_metadata or {}),
            ),
        )

    @staticmethod
    def _activate_workbench_generation(
        connection: Any,
        *,
        scope_key: str,
        generation_id: str,
        row_count: int,
        group_count: int,
        summary_count: int = 1,
    ) -> None:
        connection.execute(
            """
            update read_model.workbench_generations
            set status = 'superseded',
                superseded_at = now(),
                updated_at = now()
            where tenant_id = 'default'
              and scope_key = %s
              and status = 'active'
              and generation_id <> %s
            """,
            (scope_key, generation_id),
        )
        activated_count = connection.execute(
            """
            update read_model.workbench_generations
            set status = 'active',
                completed_at = now(),
                activated_at = now(),
                row_count = %s,
                group_count = %s,
                summary_count = %s,
                consistency_status = 'consistent',
                validated_at = now(),
                last_error = null,
                error_reason = null,
                updated_at = now()
            where tenant_id = 'default'
              and scope_key = %s
              and generation_id = %s
              and status = 'building'
            """,
            (max(row_count, 0), max(group_count, 0), max(summary_count, 0), scope_key, generation_id),
        )
        if int_value(activated_count, 0) != 1:
            raise RuntimeError(f"Workbench generation {generation_id} was not activated.")

    @staticmethod
    def _fail_workbench_generation(
        connection: Any,
        *,
        scope_key: str,
        generation_id: str,
        source_versions: dict[str, Any],
        error: str,
    ) -> None:
        connection.execute(
            """
            insert into read_model.workbench_generations(
                generation_id, tenant_id, scope_key, status, source_versions, started_at,
                completed_at, last_error, error_reason, build_metadata, consistency_status
            )
            values (%s, 'default', %s, 'failed', %s, now(), now(), %s, %s, %s, 'inconsistent')
            on conflict (generation_id) do update set
                status = 'failed',
                completed_at = now(),
                last_error = excluded.last_error,
                error_reason = excluded.error_reason,
                build_metadata = read_model.workbench_generations.build_metadata || excluded.build_metadata,
                consistency_status = 'inconsistent',
                validated_at = now(),
                updated_at = now()
            """,
            (
                generation_id,
                scope_key,
                jsonb(source_versions),
                text(error) or "unknown workbench generation failure",
                text(error) or "unknown workbench generation failure",
                jsonb({"failed_by": "save_workbench_read_models"}),
            ),
        )

    def get_workbench_view(
        self,
        *,
        scope_key: str,
        page: int | str | None = None,
        page_size: int | str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        if normalized_scope_key == "all":
            return self._load_all_workbench_view(
                page=page,
                page_size=page_size,
                status=status,
                source_kind=source_kind,
                search=search,
            )
        row = self._connection.fetch_one(
            """
            select scope_key, payload, raw_payload, cache_status, generated_at, source_versions, row_count
            from read_model.workbench_snapshots
            where scope_key = %s
            limit 1
            """,
            (normalized_scope_key,),
        )
        if row is None:
            return None
        payload = _read_model_payload(row)
        if not isinstance(payload, dict):
            payload = {}
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = %s
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """,
            (normalized_scope_key,),
        )
        refresh_status = "fresh"
        if dirty_row is not None:
            refresh_status = "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"
        payload_source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        row_source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
        result = {
            "scope_key": normalized_scope_key,
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else payload,
            "cache_status": text(row.get("cache_status") or payload.get("cache_status")) or "fresh",
            "generated_at": text(row.get("generated_at") or payload.get("generated_at")),
            "source_versions": payload_source_versions or row_source_versions,
            "row_count": int_value(row.get("row_count"), 0),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
        }
        if page is not None or page_size is not None or status or source_kind or search:
            result["rows_page"] = self._load_workbench_rows_page(
                scope_key=normalized_scope_key,
                page=page,
                page_size=page_size,
                status=status,
                source_kind=source_kind,
                search=search,
            )
        return result

    def get_workbench_summary(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        active_source_versions = self._workbench_generation_source_versions(
            self._connection,
            scope_key=normalized_scope_key,
            generation_id=active_generation_id,
        )
        if active_generation_id:
            materialized_row = self._connection.fetch_one(
                """
                select scope_key, generation_id, generated_at::text as generated_at, source_versions, payload, raw_payload
                from read_model.workbench_summary
                where scope_key = %s
                  and generation_id = %s
                """,
                (normalized_scope_key, active_generation_id),
            )
        else:
            materialized_row = self._connection.fetch_one(
                """
                select scope_key, generation_id, generated_at::text as generated_at, source_versions, payload, raw_payload
                from read_model.workbench_summary
                where scope_key = %s
                order by generated_at desc
                limit 1
                """,
                (normalized_scope_key,),
            )
        if isinstance(materialized_row, dict):
            payload = _read_model_payload(materialized_row)
            if isinstance(payload, dict):
                result = dict(payload)
                if isinstance(result.get("summary"), dict):
                    result["summary"] = _normalize_workbench_summary_counts(result["summary"])
                else:
                    structured_summary = self._workbench_summary_counts_from_group_rows(
                        scope_key=normalized_scope_key,
                        generation_id=active_generation_id,
                    )
                    if isinstance(structured_summary, dict):
                        result["summary"] = structured_summary["summary"]
                        result["generated_at"] = (
                            structured_summary.get("generated_at")
                            or text(materialized_row.get("generated_at"))
                        )
                result.setdefault("month", normalized_scope_key)
                result.setdefault("scope_key", normalized_scope_key)
                result.setdefault("generated_at", text(materialized_row.get("generated_at")))
                result["source_versions"] = (
                    materialized_row.get("source_versions")
                    if isinstance(materialized_row.get("source_versions"), dict)
                    else {}
                )
                result["active_generation_id"] = active_generation_id or text(materialized_row.get("generation_id"))
                result["read_model_version"] = result["active_generation_id"]
                result["read_model_status"] = self._workbench_summary_read_model_status(
                    scope_key=normalized_scope_key
                )
                result.pop("diagnostics", None)
                return result

        structured_summary = self._workbench_summary_counts_from_group_rows(
            scope_key=normalized_scope_key,
            generation_id=active_generation_id,
        )
        if not isinstance(structured_summary, dict):
            return None
        summary = structured_summary["summary"]
        generated_at = structured_summary.get("generated_at")
        refresh_status = self.get_workbench_refresh_status(scope_key=normalized_scope_key)
        return {
            "month": normalized_scope_key,
            "scope_key": normalized_scope_key,
            "summary": summary,
            "invoice_inventory": self._workbench_invoice_inventory(
                scope_key=normalized_scope_key,
                generation_id=active_generation_id,
            ),
            "read_model_status": refresh_status["read_model_status"],
            "generated_at": generated_at,
            "source_versions": active_source_versions,
            "active_generation_id": active_generation_id,
            "read_model_version": active_generation_id,
        }

    def _workbench_summary_counts_from_group_rows(
        self,
        *,
        scope_key: str,
        generation_id: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        group_where, group_params = self._workbench_scope_filter(normalized_scope_key)
        generation_clause = ""
        generation_params: list[Any] = []
        if generation_id:
            generation_clause = " and g.generation_id = %s"
            generation_params.append(generation_id)
        group_rows = self._connection.fetch_all(
            f"""
            select
                g.zone,
                count(distinct g.group_id)::bigint as count,
                count(distinct r.row_id) filter (
                    where r.pane = 'oa'
                      and coalesce(r.row_role, '') <> 'summary'
                )::bigint as oa_count,
                count(distinct r.row_id) filter (
                    where r.pane = 'bank'
                      and coalesce(r.row_role, '') <> 'summary'
                      and coalesce(r.source_kind, '') <> 'no_oa_bank_batch_summary'
                )::bigint as bank_count,
                count(distinct r.row_id) filter (
                    where r.pane = 'invoice'
                      and coalesce(r.row_role, '') <> 'summary'
                )::bigint as invoice_count
            from read_model.workbench_groups
            g
            left join read_model.workbench_group_rows r
              on r.scope_key = g.scope_key
             and r.generation_id = g.generation_id
             and r.zone = g.zone
             and r.group_id = g.group_id
            where g.{group_where}{generation_clause}
            group by g.zone
            """,
            tuple([*group_params, *generation_params]),
        )
        generated_row = self._connection.fetch_one(
            f"""
            select max(generated_at)::text as generated_at
            from read_model.workbench_groups
            where {group_where}{generation_clause.replace('g.', '')}
            """,
            tuple([*group_params, *generation_params]),
        )
        summary = {
            "oa_count": 0,
            "bank_count": 0,
            "invoice_count": 0,
            "paired_count": 0,
            "open_count": 0,
            "exception_count": 0,
            "zone_counts": _empty_workbench_zone_counts(),
        }
        for row in group_rows:
            zone = text(row.get("zone")) or ""
            count = int_value(row.get("count"), 0)
            if zone == "paired":
                summary["paired_count"] += count
            elif zone == "open":
                summary["open_count"] += count
            if zone in {"paired", "open"}:
                zone_counts = summary["zone_counts"][zone]
                zone_counts["groups"] += count
                zone_counts["oa"] += int_value(row.get("oa_count"), 0)
                zone_counts["bank"] += int_value(row.get("bank_count"), 0)
                zone_counts["invoice"] += int_value(row.get("invoice_count"), 0)
                zone_counts["rows"] = zone_counts["oa"] + zone_counts["bank"] + zone_counts["invoice"]
        for zone in ("paired", "open"):
            zone_counts = summary["zone_counts"][zone]
            summary["oa_count"] += zone_counts["oa"]
            summary["bank_count"] += zone_counts["bank"]
            summary["invoice_count"] += zone_counts["invoice"]
        generated_at = text((generated_row or {}).get("generated_at"))
        if generated_at is None and not any(summary.values()):
            return None
        return {
            "summary": summary,
            "generated_at": generated_at,
        }

    def _workbench_bank_count_diagnostics(
        self,
        *,
        scope_key: str,
        summary: dict[str, Any],
        generation_id: str | None = None,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        bank_where = ["status <> 'deleted'"]
        bank_params: list[Any] = []
        if normalized_scope_key != "all":
            bank_where.append("txn_month = %s::date")
            bank_params.append(month_start(normalized_scope_key))
        bank_row = self._connection.fetch_one(
            f"""
            select count(*)::bigint as bank_detail_count
            from app.bank_transactions
            where {" and ".join(bank_where)}
            """,
            tuple(bank_params),
        ) or {}
        ignored_where, ignored_params = self._workbench_scope_filter(normalized_scope_key)
        generation_clause = ""
        generation_params: list[Any] = []
        if generation_id:
            generation_clause = " and generation_id = %s"
            generation_params.append(generation_id)
        ignored_row = self._connection.fetch_one(
            f"""
            select count(distinct row_id)::bigint as ignored_bank_count
            from read_model.workbench_rows
            where {ignored_where}
              {generation_clause}
              and status = 'ignored'
              and (
                  coalesce(nullif(payload->>'type', ''), nullif(payload->>'record_type', ''), source_kind)
                      in ('bank', 'bank_transaction')
                  or source_kind in ('bank', 'bank_transaction')
              )
            """,
            tuple([*ignored_params, *generation_params]),
        ) or {}
        ignored_bank_count = int_value(ignored_row.get("ignored_bank_count"), 0)
        expected_bank_detail_count = int_value(summary.get("bank_count"), 0) + ignored_bank_count
        raw_bank_detail_count = bank_row.get("bank_detail_count")
        bank_detail_count = int_value(raw_bank_detail_count, expected_bank_detail_count)
        if raw_bank_detail_count is None:
            status = "unavailable"
        elif bank_detail_count == expected_bank_detail_count:
            status = "matched"
        else:
            status = "mismatch"
        return {
            "bank_detail_count": bank_detail_count,
            "ignored_bank_count": ignored_bank_count,
            "bank_detail_reconciliation_status": status,
        }

    def _workbench_invoice_inventory(self, *, scope_key: str, generation_id: str | None = None) -> dict[str, int]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        invoice_where = ["status <> 'deleted'"]
        invoice_params: list[Any] = []
        if normalized_scope_key != "all":
            invoice_where.append("invoice_month = %s::date")
            invoice_params.append(month_start(normalized_scope_key))
        invoice_row = self._connection.fetch_one(
            f"""
            with invoice_flags as (
                select
                    status,
                    workbench_visibility,
                    tags,
                    etc_invoice_id,
                    exists (
                        select 1
                        from jsonb_array_elements(
                            case when jsonb_typeof(source_links) = 'array' then source_links else '[]'::jsonb end
                        ) as source_link
                        where coalesce(source_link->>'source_type', source_link->>'type', source_link->>'source') = 'manual_invoice_import'
                    ) as is_manual_import,
                    exists (
                        select 1
                        from jsonb_array_elements(
                            case when jsonb_typeof(source_links) = 'array' then source_links else '[]'::jsonb end
                        ) as source_link
                        where coalesce(source_link->>'source_type', source_link->>'type', source_link->>'source')
                            in ('etc_import', 'etc_invoice_import', 'etc_submission')
                    ) as has_etc_source
                from app.invoices
                where {" and ".join(invoice_where)}
            )
            select
                count(*)::bigint as system_total,
                count(*) filter (where is_manual_import)::bigint as manual_import_total,
                count(*) filter (where workbench_visibility <> 'hidden_after_etc_submission')::bigint as workbench_visible_total,
                count(*) filter (where is_manual_import and workbench_visibility = 'hidden_after_etc_submission')::bigint
                    as hidden_submitted_etc_total,
                count(*) filter (
                    where not is_manual_import
                    and (
                        nullif(etc_invoice_id, '') is not null
                        or has_etc_source
                        or tags && array['ETC', 'etc', 'etc_invoice']::text[]
                    )
                )::bigint as extra_etc_total
            from invoice_flags
            """,
            tuple(invoice_params),
        ) or {}
        batch_where = ["status <> 'withdrawn'"]
        batch_params: list[Any] = []
        if normalized_scope_key != "all":
            batch_where.append("scope_month = %s::date")
            batch_params.append(month_start(normalized_scope_key))
        batch_row = self._connection.fetch_one(
            f"""
            select count(*)::bigint as etc_summary_batch_count
            from app.etc_business_batches
            where {" and ".join(batch_where)}
            """,
            tuple(batch_params),
        ) or {}
        row_where, row_params = self._workbench_scope_filter(normalized_scope_key)
        generation_clause = ""
        generation_params: list[Any] = []
        if generation_id:
            generation_clause = " and generation_id = %s"
            generation_params.append(generation_id)
        attachment_row = self._connection.fetch_one(
            f"""
            select count(distinct row_id)::bigint as oa_attachment_total
            from read_model.workbench_rows
            where {row_where}{generation_clause} and source_kind = 'oa_attachment_invoice'
            """,
            tuple([*row_params, *generation_params]),
        ) or {}
        return {
            "system_total": int_value(invoice_row.get("system_total"), 0),
            "manual_import_total": int_value(invoice_row.get("manual_import_total"), 0),
            "workbench_visible_total": int_value(invoice_row.get("workbench_visible_total"), 0),
            "hidden_submitted_etc_total": int_value(invoice_row.get("hidden_submitted_etc_total"), 0),
            "extra_etc_total": int_value(invoice_row.get("extra_etc_total"), 0),
            "etc_summary_batch_count": int_value(batch_row.get("etc_summary_batch_count"), 0),
            "oa_attachment_total": int_value(attachment_row.get("oa_attachment_total"), 0),
        }

    def _workbench_summary_read_model_status(self, *, scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        scope_clause = ""
        params: list[Any] = []
        if normalized_scope_key != "all":
            scope_clause = "and scope_key = %s"
            params.append(normalized_scope_key)
        rows = self._connection.fetch_all(
            f"""
            select status
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and status in ('pending', 'processing', 'failed')
              {scope_clause}
            limit 50
            """,
            tuple(params),
        )
        statuses = {text(row.get("status")) for row in rows}
        if statuses.intersection({"pending", "processing"}):
            return "refreshing"
        if "failed" in statuses:
            return "stale"
        if self._workbench_groups_schema_status(scope_key=normalized_scope_key) != "fresh":
            return "stale"
        return "fresh"

    def _workbench_groups_schema_status(self, *, scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        expected_builder = _expected_workbench_groups_builder(normalized_scope_key)
        if not expected_builder:
            return "fresh"
        where_sql, params = self._workbench_scope_filter(normalized_scope_key)
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        active_source_versions = (
            self._workbench_generation_source_versions(
                self._connection,
                scope_key=normalized_scope_key,
                generation_id=active_generation_id,
            )
            if active_generation_id
            else {}
        )
        generation_clause = ""
        generation_params: list[Any] = []
        if active_generation_id:
            generation_clause = " and generation_id = %s"
            generation_params.append(active_generation_id)
        row = self._connection.fetch_one(
            f"""
            select
                count(*)::bigint as group_count,
                count(*) filter (
                    where coalesce(source_versions->>'builder', '') = %s
                )::bigint as current_group_count
            from read_model.workbench_groups
            where {where_sql}{generation_clause}
            """,
            (expected_builder, *params, *generation_params),
        )
        if not isinstance(row, dict):
            return "fresh"
        group_count = int_value(row.get("group_count"), 0)
        current_group_count = int_value(row.get("current_group_count"), 0)
        if group_count > 0 and current_group_count < group_count:
            return "stale"
        return "fresh"

    @staticmethod
    def _workbench_summary_from_payload(
        *,
        scope_key: str,
        grouped_payload: dict[str, Any],
        source_versions: dict[str, Any],
        generated_at: str | None,
    ) -> dict[str, Any]:
        paired_groups = []
        open_groups = []
        paired_section = grouped_payload.get("paired")
        open_section = grouped_payload.get("open")
        if isinstance(paired_section, dict) and isinstance(paired_section.get("groups"), list):
            paired_groups = [group for group in paired_section.get("groups", []) if isinstance(group, dict)]
        if isinstance(open_section, dict) and isinstance(open_section.get("groups"), list):
            open_groups = [group for group in open_section.get("groups", []) if isinstance(group, dict)]
        summary = _summarize_workbench_payload_groups(
            {"paired": {"groups": paired_groups}, "open": {"groups": open_groups}}
        )
        invoice_inventory = grouped_payload.get("invoice_inventory")
        if not isinstance(invoice_inventory, dict):
            invoice_inventory = {}
        return {
            "month": scope_key,
            "scope_key": scope_key,
            "summary": summary,
            "invoice_inventory": invoice_inventory,
            "read_model_status": "fresh",
            "generated_at": generated_at,
            "source_versions": source_versions,
        }

    @staticmethod
    def _upsert_workbench_generation_stats(
        connection: Any,
        *,
        generation_id: str,
        scope_key: str,
        summary_payload: dict[str, Any],
    ) -> None:
        summary = summary_payload.get("summary") if isinstance(summary_payload.get("summary"), dict) else {}
        normalized_summary = _normalize_workbench_summary_counts(summary)
        zone_counts = normalized_summary.get("zone_counts")
        if not isinstance(zone_counts, dict):
            zone_counts = _empty_workbench_zone_counts()
        for zone in ("paired", "open"):
            counts = zone_counts.get(zone) if isinstance(zone_counts.get(zone), dict) else {}
            oa_count = int_value(counts.get("oa"), 0)
            bank_count = int_value(counts.get("bank"), 0)
            invoice_count = int_value(counts.get("invoice"), 0)
            row_count_total = int_value(counts.get("rows"), oa_count + bank_count + invoice_count)
            connection.execute(
                """
                insert into read_model.workbench_generation_stats(
                    generation_id, scope_key, zone, status_bucket, total_groups,
                    oa_count, bank_count, invoice_count, row_count_total, payload, raw_payload
                )
                values (%s, %s, %s, 'all', %s, %s, %s, %s, %s, %s, %s)
                on conflict (generation_id, scope_key, zone, status_bucket) do update set
                    total_groups = excluded.total_groups,
                    oa_count = excluded.oa_count,
                    bank_count = excluded.bank_count,
                    invoice_count = excluded.invoice_count,
                    row_count_total = excluded.row_count_total,
                    payload = excluded.payload,
                    raw_payload = excluded.raw_payload,
                    computed_at = now(),
                    updated_at = now()
                """,
                (
                    generation_id,
                    scope_key,
                    zone,
                    int_value(counts.get("groups"), 0),
                    oa_count,
                    bank_count,
                    invoice_count,
                    row_count_total,
                    jsonb(counts if isinstance(counts, dict) else {}),
                    jsonb({"summary_zone_counts": counts if isinstance(counts, dict) else {}}),
                ),
            )

    def _workbench_generation_stats_for_groups_page(
        self,
        *,
        scope_key: str,
        generation_id: str | None,
        zone: str,
        status: str | None,
        source_kind: str | None,
        search: str | None,
        search_mode: str | None,
        search_by_pane: dict[str, Any],
        column_filters: dict[str, Any],
        time_filters: dict[str, Any],
    ) -> dict[str, Any] | None:
        if not generation_id:
            return None
        if text(status) or text(source_kind) or text(search):
            return None
        if search_mode == "linked_context" or search_by_pane or column_filters or time_filters:
            return None
        row = self._connection.fetch_one(
            """
            select total_groups, oa_count, bank_count, invoice_count, row_count_total
            from read_model.workbench_generation_stats
            where generation_id = %s
              and scope_key = %s
              and zone = %s
              and status_bucket = 'all'
            limit 1
            """,
            (generation_id, scope_key, zone),
        )
        if not isinstance(row, dict):
            return None
        return {
            "total": int_value(row.get("total_groups"), 0),
            "row_counts": {
                "oa": int_value(row.get("oa_count"), 0),
                "bank": int_value(row.get("bank_count"), 0),
                "invoice": int_value(row.get("invoice_count"), 0),
                "rows": int_value(
                    row.get("row_count_total"),
                    int_value(row.get("oa_count"), 0)
                    + int_value(row.get("bank_count"), 0)
                    + int_value(row.get("invoice_count"), 0),
                ),
            },
        }

    def list_workbench_ignored_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        if normalized_scope_key == "all":
            scope_clause = "scope_key <> 'all'"
            params: list[Any] = []
        else:
            scope_clause = "scope_key = %s"
            params = [normalized_scope_key]
        rows = self._connection.fetch_all(
            f"""
            select row_id, payload, raw_payload
            from read_model.workbench_rows
            where {scope_clause}
              and status = 'ignored'
            order by generated_at desc, updated_at desc, row_id
            """,
            tuple(params),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _read_model_payload(row)
            if isinstance(payload, dict):
                result.append(payload)
            else:
                result.append({"id": text(row.get("row_id"))})
        return result

    def get_workbench_groups_page(
        self,
        *,
        scope_key: str,
        zone: str,
        page: int | str | None = None,
        page_size: int | str | None = None,
        status: str | None = None,
        source_kind: str | None = None,
        search: str | None = None,
        search_mode: str | None = None,
        search_by_pane: Any = None,
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: Any = None,
        time_filters: Any = None,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_detail_level = _normalize_workbench_group_detail_level(detail_level)
        normalized_page = max(1, int_value(page, 1))
        normalized_page_size = min(200, max(1, int_value(page_size, 50)))
        offset = (normalized_page - 1) * normalized_page_size
        scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        active_source_versions = self._workbench_generation_source_versions(
            self._connection,
            scope_key=normalized_scope_key,
            generation_id=active_generation_id,
        )
        normalized_column_filters = _normalize_workbench_column_filters(column_filters)
        normalized_time_filters = _normalize_workbench_time_filters(time_filters)
        normalized_search_by_pane = _normalize_workbench_search_by_pane(search_by_pane)
        normalized_search_mode = _normalize_workbench_search_mode(search_mode)
        clauses = [f"g.{scope_where}", "g.zone = %s"]
        params = [*scope_params, normalized_zone]
        if active_generation_id:
            clauses.append("g.generation_id = %s")
            params.append(active_generation_id)
        if normalized := text(status):
            clauses.append("g.status = %s")
            params.append(normalized)
        if normalized := text(source_kind):
            clauses.append("%s = any(g.source_kinds)")
            params.append(normalized)
        excludes_linked_etc_summary_groups = normalized_zone == "open"
        if excludes_linked_etc_summary_groups:
            clauses.append(_workbench_open_linked_etc_summary_group_exclusion_sql())
        normalized_search = text(search)
        if (
            normalized_search
            and normalized_search_mode != "linked_context"
            and not normalized_search_by_pane
            and not normalized_column_filters
            and not normalized_time_filters
        ):
            clauses.append("(g.searchable_text ilike %s or g.group_id ilike %s)")
            pattern = f"%{normalized_search}%"
            params.extend([pattern, pattern])
        if normalized_search and normalized_search_mode == "linked_context":
            clauses.append(_workbench_linked_search_exists_sql())
            params.append(f"%{normalized_search}%")
        row_filter_sql, row_filter_params = _workbench_group_row_filter_exists_sql(
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
            search_by_pane=normalized_search_by_pane,
            fallback_search=None if normalized_search_mode == "linked_context" else normalized_search,
        )
        if row_filter_sql:
            clauses.append(row_filter_sql)
            params.extend(row_filter_params)
        where_sql = " and ".join(clauses)
        order_by_sql = _workbench_groups_order_by(sort)
        oa_row_filter_sql, oa_row_filter_params = _workbench_group_row_count_filter_sql(
            "oa",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
            search_by_pane=normalized_search_by_pane,
            fallback_search=None if normalized_search_mode == "linked_context" else normalized_search,
        )
        bank_row_filter_sql, bank_row_filter_params = _workbench_group_row_count_filter_sql(
            "bank",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
            search_by_pane=normalized_search_by_pane,
            fallback_search=None if normalized_search_mode == "linked_context" else normalized_search,
        )
        invoice_row_filter_sql, invoice_row_filter_params = _workbench_group_row_count_filter_sql(
            "invoice",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
            search_by_pane=normalized_search_by_pane,
            fallback_search=None if normalized_search_mode == "linked_context" else normalized_search,
        )
        materialized_counts = None
        if not excludes_linked_etc_summary_groups:
            materialized_counts = self._workbench_generation_stats_for_groups_page(
                scope_key=normalized_scope_key,
                generation_id=active_generation_id,
                zone=normalized_zone,
                status=status,
                source_kind=source_kind,
                search=normalized_search,
                search_mode=normalized_search_mode,
                search_by_pane=normalized_search_by_pane,
                column_filters=normalized_column_filters,
                time_filters=normalized_time_filters,
            )
        if materialized_counts is None:
            count_row = self._connection.fetch_one(
                f"""
                select count(*) as total_count
                from read_model.workbench_groups g
                where {where_sql}
                """,
                tuple(params),
            )
            row_count_row = self._connection.fetch_one(
                f"""
                select
                    count(distinct r.row_id) filter (
                        where r.pane = 'oa'
                          and coalesce(r.row_role, '') <> 'summary'
                          {oa_row_filter_sql}
                    )::bigint as oa_count,
                    count(distinct r.row_id) filter (
                        where r.pane = 'bank'
                          and coalesce(r.row_role, '') <> 'summary'
                          and coalesce(r.source_kind, '') <> 'no_oa_bank_batch_summary'
                          {bank_row_filter_sql}
                    )::bigint as bank_count,
                    count(distinct r.row_id) filter (
                        where r.pane = 'invoice'
                          and coalesce(r.row_role, '') <> 'summary'
                          {invoice_row_filter_sql}
                    )::bigint as invoice_count
                from read_model.workbench_groups g
                left join read_model.workbench_group_rows r
                  on r.scope_key = g.scope_key
                 and r.generation_id = g.generation_id
                 and r.zone = g.zone
                 and r.group_id = g.group_id
                where {where_sql}
                """,
                tuple(
                    [
                        *oa_row_filter_params,
                        *bank_row_filter_params,
                        *invoice_row_filter_params,
                        *params,
                    ]
                ),
            )
            total = int_value((count_row or {}).get("total_count"), 0)
            row_counts = _workbench_group_page_row_counts(row_count_row)
        else:
            total = int_value(materialized_counts.get("total"), 0)
            row_counts = materialized_counts.get("row_counts")
            if not isinstance(row_counts, dict):
                row_counts = _workbench_group_page_row_counts(None)
        page_params = [*params, normalized_page_size + 1, offset]
        rows = self._connection.fetch_all(
            f"""
            select group_id, zone, payload, raw_payload
            from read_model.workbench_groups g
            where {where_sql}
            order by {order_by_sql}
            limit %s offset %s
            """,
            tuple(page_params),
        )
        visible_rows = rows[:normalized_page_size]
        groups: list[dict[str, Any]] = []
        for row in visible_rows:
            group = _read_model_payload(row)
            if not isinstance(group, dict):
                group = {"group_id": text(row.get("group_id"))}
            group = _sanitize_workbench_group_invoice_rows(group)
            group = _with_workbench_group_counts(group)
            if normalized_detail_level == "summary":
                group = _filter_workbench_group_preview_rows_for_criteria(
                    group,
                    column_filters=normalized_column_filters,
                    time_filters=normalized_time_filters,
                    search_by_pane=normalized_search_by_pane,
                    fallback_search=None if normalized_search_mode == "linked_context" else normalized_search,
                )
                group = _compact_workbench_group_for_summary_page(group)
            groups.append(group)
        read_model_status = self._workbench_read_model_status_for_groups_page(scope_key=normalized_scope_key)
        return {
            "month": normalized_scope_key,
            "scope_key": normalized_scope_key,
            "zone": normalized_zone,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "detail_level": normalized_detail_level,
            "total": total,
            "row_counts": row_counts,
            "has_more": len(rows) > normalized_page_size,
            "groups": groups,
            "read_model_status": read_model_status,
            "source_versions": active_source_versions,
            "active_generation_id": active_generation_id,
            "read_model_version": active_generation_id,
        }

    def get_workbench_group_detail(self, *, scope_key: str, zone: str, group_id: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        if not normalized_zone or not normalized_group_id:
            return None
        scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        generation_clause = ""
        generation_params: list[Any] = []
        if active_generation_id:
            generation_clause = "and generation_id = %s"
            generation_params.append(active_generation_id)
        exclusion_clause = ""
        if normalized_zone == "open":
            exclusion_clause = f"and {_workbench_open_linked_etc_summary_group_exclusion_sql()}"
        row = self._connection.fetch_one(
            f"""
            select g.group_id, g.zone, g.payload, g.raw_payload
            from read_model.workbench_groups g
            where {scope_where}
              {generation_clause}
              and g.zone = %s
              and g.group_id = %s
              {exclusion_clause}
            order by g.scope_month desc nulls last, g.updated_at desc
            limit 1
            """,
            (*scope_params, *generation_params, normalized_zone, normalized_group_id),
        )
        if not isinstance(row, dict):
            return None
        group = _read_model_payload(row)
        if not isinstance(group, dict):
            return {"group_id": text(row.get("group_id"))}
        result = _with_workbench_group_counts(_sanitize_workbench_group_invoice_rows(group))
        result["active_generation_id"] = active_generation_id
        result["read_model_version"] = active_generation_id
        return result

    def get_workbench_row_detail(self, *, scope_key: str, row_id: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_row_id = text(row_id)
        if not normalized_row_id:
            return None
        if normalized_scope_key == "all":
            scope_clause = "true"
            scope_params: tuple[Any, ...] = ()
        else:
            scope_clause = "r.scope_key in (%s, 'all')"
            scope_params = (normalized_scope_key,)
        row = self._connection.fetch_one(
            f"""
            select
              r.row_id,
              r.source_kind,
              r.status,
              r.payload,
              r.raw_payload,
              r.scope_key,
              r.generation_id,
              gen.source_versions
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.row_id = %s
              and {scope_clause}
            order by
              case
                when r.scope_key = %s then 0
                when r.scope_key = 'all' then 1
                else 2
              end,
              r.updated_at desc nulls last
            limit 1
            """,
            (normalized_row_id, *scope_params, normalized_scope_key),
        )
        if not isinstance(row, dict):
            return None
        payload = _read_model_payload(row)
        if not isinstance(payload, dict):
            payload = {"id": normalized_row_id, "type": text(row.get("source_kind")) or "unknown"}
        resolved_scope_key = text(row.get("scope_key")) or normalized_scope_key
        return {
            "row": payload,
            "scope_key": resolved_scope_key,
            "source_versions": row.get("source_versions"),
            "active_generation_id": row.get("generation_id"),
            "read_model_version": row.get("generation_id"),
            "read_model_status": self._workbench_read_model_status_for_groups_page(scope_key=resolved_scope_key),
        }

    def _workbench_read_model_status_for_groups_page(self, *, scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        scope_clause = ""
        params: list[Any] = []
        if normalized_scope_key != "all":
            scope_clause = "and scope_key = %s"
            params.append(normalized_scope_key)
        rows = self._connection.fetch_all(
            f"""
            select status
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and status in ('pending', 'processing', 'failed')
              {scope_clause}
            limit 20
            """,
            tuple(params),
        )
        statuses = {text(row.get("status")) for row in rows if isinstance(row, dict)}
        if statuses.intersection({"pending", "processing"}):
            return "refreshing"
        if "failed" in statuses:
            return "stale"
        return "fresh"

    def get_workbench_groups_freshness_status(self, *, scope_key: str | None = None) -> dict[str, Any]:
        return self._get_workbench_refresh_status(scope_key=scope_key, include_consistency=False)

    def get_workbench_refresh_status(self, *, scope_key: str | None = None) -> dict[str, Any]:
        return self._get_workbench_refresh_status(scope_key=scope_key, include_consistency=True)

    def _get_workbench_refresh_status(
        self,
        *,
        scope_key: str | None = None,
        include_consistency: bool,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        scope_clause = ""
        params: list[Any] = []
        if normalized_scope_key != "all":
            scope_clause = "and scope_key = %s"
            params.append(normalized_scope_key)
        dirty_rows = self._connection.fetch_all(
            f"""
            select scope_key, status, updated_at::text as updated_at, last_error, source_version
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and status in ('pending', 'processing', 'failed')
              {scope_clause}
            order by updated_at desc
            limit 50
            """,
            tuple(params),
        )
        worker_rows = self._connection.fetch_all(
            """
            select
                worker_id,
                worker_kind,
                status,
                last_seen_at::text as last_seen_at,
                extract(epoch from now() - last_seen_at)::float as lag_seconds,
                payload
            from job.runtime_worker_heartbeats
            where worker_kind ilike %s
            order by last_seen_at desc
            limit 10
            """,
            ("%workbench%",),
        )
        backlog_rows = self._connection.fetch_all(
            """
            select status, count(*)::bigint as count
            from job.outbox_events
            where event_type = 'workbench.read_model.refresh'
            group by status
            order by status
            """
        )
        dirty_scopes = [
            {
                "scope_key": text(row.get("scope_key")),
                "status": text(row.get("status")),
                "updated_at": text(row.get("updated_at")),
                "last_error": text(row.get("last_error")),
                "source_version": int_value(row.get("source_version"), 0),
            }
            for row in dirty_rows
        ]
        dirty_statuses = {scope["status"] for scope in dirty_scopes}
        generation_metadata = self._workbench_generation_metadata(self._connection, scope_key=normalized_scope_key)
        consistency_failures = (
            self._workbench_generation_consistency_failures(
                self._connection,
                scope_key=normalized_scope_key,
            )
            if include_consistency
            else []
        )
        groups_schema_status = self._workbench_groups_schema_status(scope_key=normalized_scope_key)
        active_refresh_in_progress = bool(
            dirty_statuses.intersection({"pending", "processing"})
            or generation_metadata.get("building_generation_id")
        )
        read_model_status = "fresh"
        if active_refresh_in_progress:
            read_model_status = "refreshing"
        elif consistency_failures:
            read_model_status = "failed"
        elif "failed" in dirty_statuses:
            read_model_status = "stale"
        elif generation_metadata.get("failed_generation_is_relevant"):
            read_model_status = "stale"
        elif groups_schema_status != "fresh":
            read_model_status = "stale"
        last_error = None
        if read_model_status != "refreshing":
            last_error = (
                next((scope["last_error"] for scope in dirty_scopes if scope.get("last_error")), None)
                or generation_metadata.get("generation_last_error")
                or (
                    self._workbench_generation_consistency_error(consistency_failures)
                    if consistency_failures
                    else None
                )
            )
        worker_lag_values = [
            row.get("lag_seconds")
            for row in worker_rows
            if isinstance(row.get("lag_seconds"), (int, float))
        ]
        stale_reasons = []
        if groups_schema_status != "fresh":
            stale_reasons.append("builder_schema_mismatch")
        if consistency_failures:
            stale_reasons.append("generation_metadata_actual_mismatch")
        return {
            "scope_key": normalized_scope_key,
            "read_model_status": read_model_status,
            "consistency_status": "failed" if consistency_failures else "fresh",
            "consistency_failures": consistency_failures,
            "active_generation_id": generation_metadata.get("active_generation_id"),
            "building_generation_id": generation_metadata.get("building_generation_id"),
            "failed_generation_id": generation_metadata.get("failed_generation_id"),
            "read_model_version": generation_metadata.get("read_model_version"),
            "generated_at": generation_metadata.get("generated_at"),
            "generations": generation_metadata.get("generations", []),
            "dirty_scopes": dirty_scopes,
            "read_model_stale_reasons": stale_reasons,
            "worker_lag_seconds": max(worker_lag_values, default=None),
            "last_error": last_error,
            "workers": [
                {
                    "worker_id": text(row.get("worker_id")),
                    "worker_kind": text(row.get("worker_kind")),
                    "status": text(row.get("status")),
                    "last_seen_at": text(row.get("last_seen_at")),
                    "lag_seconds": row.get("lag_seconds"),
                    "payload": row.get("payload") if isinstance(row.get("payload"), dict) else {},
                }
                for row in worker_rows
            ],
            "outbox_backlog": {text(row.get("status")) or "unknown": int_value(row.get("count"), 0) for row in backlog_rows},
        }

    def workbench_groups_cache_version(self, *, scope_key: str) -> str | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        if active_generation_id:
            return active_generation_id
        where_sql, params = self._workbench_scope_filter(normalized_scope_key)
        row = self._connection.fetch_one(
            f"""
            select
                max((source_versions->>'source_version')::bigint) as source_version,
                max(generated_at)::text as generated_at
            from read_model.workbench_groups
            where {where_sql}
            """,
            tuple(params),
        )
        if not isinstance(row, dict):
            return None
        version = text(row.get("source_version"))
        generated_at = text(row.get("generated_at"))
        if version:
            return f"v{version}"
        if generated_at:
            return f"g{generated_at}"
        return None

    def preview_workbench_generation_retention(
        self,
        *,
        keep_recent_generations_per_scope: int = 3,
        keep_days: int = 14,
        limit: int = 500,
        scope_keys: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        keep_recent = max(1, int_value(keep_recent_generations_per_scope, 3))
        keep_days_value = max(1, int_value(keep_days, 14))
        limit_value = min(5000, max(1, int_value(limit, 500)))
        normalized_scope_keys = self._normalize_workbench_retention_scope_keys(scope_keys)
        scope_filter = ""
        params: list[Any] = []
        if normalized_scope_keys is not None:
            if not normalized_scope_keys:
                return {
                    "dry_run": True,
                    "keep_recent_generations_per_scope": keep_recent,
                    "keep_days": keep_days_value,
                    "limit": limit_value,
                    "scope_keys": [],
                    "candidate_count": 0,
                    "generations": [],
                }
            scope_filter = "and scope_key = any(%s)"
            params.append(normalized_scope_keys)
        params.extend([keep_recent, keep_days_value, limit_value])
        rows = self._connection.fetch_all(
            f"""
            with ranked as (
              select
                generation_id,
                scope_key,
                status,
                activated_at,
                completed_at,
                updated_at,
                row_number() over (
                  partition by tenant_id, scope_key
                  order by coalesce(activated_at, completed_at, updated_at) desc, updated_at desc
                ) as scope_rank
              from read_model.workbench_generations
              where tenant_id = 'default'
                and status <> 'active'
                {scope_filter}
            )
            select generation_id, scope_key, status, activated_at::text as activated_at,
                   completed_at::text as completed_at, updated_at::text as updated_at
            from ranked
            where scope_rank > %s
              and coalesce(activated_at, completed_at, updated_at) < now() - (%s * interval '1 day')
            order by scope_key, coalesce(activated_at, completed_at, updated_at)
            limit %s
            """,
            tuple(params),
        )
        result = {
            "dry_run": True,
            "keep_recent_generations_per_scope": keep_recent,
            "keep_days": keep_days_value,
            "limit": limit_value,
            "candidate_count": len(rows),
            "generations": [dict(row) for row in rows],
        }
        if normalized_scope_keys is not None:
            result["scope_keys"] = normalized_scope_keys
        return result

    def prune_workbench_generations(
        self,
        *,
        keep_recent_generations_per_scope: int = 3,
        keep_days: int = 14,
        limit: int = 500,
        dry_run: bool = True,
        scope_keys: set[str] | list[str] | tuple[str, ...] | None = None,
    ) -> dict[str, Any]:
        preview = self.preview_workbench_generation_retention(
            keep_recent_generations_per_scope=keep_recent_generations_per_scope,
            keep_days=keep_days,
            limit=limit,
            scope_keys=scope_keys,
        )
        generation_ids = [
            text(row.get("generation_id"))
            for row in preview["generations"]
            if isinstance(row, dict) and text(row.get("generation_id"))
        ]
        if dry_run or not generation_ids:
            result = dict(preview)
            result["dry_run"] = dry_run
            result["deleted_count"] = 0
            return result

        def delete(connection: Any) -> None:
            self._delete_workbench_generations(connection, generation_ids=generation_ids)

        run_in_transaction(self._connection, delete)
        result = dict(preview)
        result["dry_run"] = False
        result["deleted_count"] = len(generation_ids)
        return result

    @staticmethod
    def _normalize_workbench_retention_scope_keys(
        scope_keys: set[str] | list[str] | tuple[str, ...] | None,
    ) -> list[str] | None:
        if scope_keys is None:
            return None
        normalized = {
            str(scope_key or "").strip()
            for scope_key in scope_keys
            if str(scope_key or "").strip() == "all" or MONTH_SCOPE_RE.match(str(scope_key or "").strip())
        }
        return sorted(normalized)

    @staticmethod
    def _delete_workbench_generations(connection: Any, *, generation_ids: list[str]) -> None:
        params = (generation_ids,)
        connection.execute("delete from read_model.workbench_generation_stats where generation_id = any(%s)", params)
        connection.execute("delete from read_model.workbench_group_rows where generation_id = any(%s)", params)
        connection.execute("delete from read_model.workbench_groups where generation_id = any(%s)", params)
        connection.execute("delete from read_model.workbench_rows where generation_id = any(%s)", params)
        connection.execute("delete from read_model.workbench_summary where generation_id = any(%s)", params)
        connection.execute("delete from read_model.workbench_snapshots where generation_id = any(%s)", params)
        connection.execute(
            """
            delete from read_model.workbench_generations
            where generation_id = any(%s)
              and tenant_id = 'default'
              and status <> 'active'
            """,
            params,
        )

    @staticmethod
    def _workbench_scope_filter(scope_key: str) -> tuple[str, list[Any]]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        return "scope_key = %s", [normalized_scope_key]

    def _load_all_workbench_view(
        self,
        *,
        page: int | str | None,
        page_size: int | str | None,
        status: str | None,
        source_kind: str | None,
        search: str | None,
    ) -> dict[str, Any] | None:
        if page is not None or page_size is not None or status or source_kind or search:
            return self._load_all_workbench_rows_page_view(
                page=page,
                page_size=page_size,
                status=status,
                source_kind=source_kind,
                search=search,
            )
        rows = self._connection.fetch_all(
            """
            select scope_key, payload, raw_payload, cache_status, generated_at, source_versions, row_count
            from read_model.workbench_snapshots
            where scope_key <> 'all'
            order by scope_key desc
            """
        )
        if not rows:
            return None
        payloads = [_read_model_payload(row) for row in rows]
        grouped_payloads = [
            payload.get("payload") if isinstance(payload, dict) and isinstance(payload.get("payload"), dict) else payload
            for payload in payloads
            if isinstance(payload, dict)
        ]
        combined = {
            "month": "all",
            "summary": {
                "oa_count": 0,
                "bank_count": 0,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 0,
                "exception_count": 0,
            },
            "paired": {"groups": []},
            "open": {"groups": []},
            "read_model_scope_key": "all",
        }
        for payload in grouped_payloads:
            summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
            for key in ("oa_count", "bank_count", "invoice_count", "paired_count", "open_count", "exception_count"):
                combined["summary"][key] += int_value(summary.get(key), 0)
            for section_name in ("paired", "open"):
                section = payload.get(section_name) if isinstance(payload.get(section_name), dict) else {}
                groups = section.get("groups") if isinstance(section, dict) else []
                if isinstance(groups, list):
                    combined[section_name]["groups"].extend(groups)
        _dedupe_workbench_payload_groups(combined)
        combined["summary"] = _summarize_workbench_payload_groups(combined)
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = 'all'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """
        )
        refresh_status = "fresh"
        if dirty_row is not None:
            refresh_status = "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"
        result = {
            "scope_key": "all",
            "payload": combined,
            "cache_status": "fresh",
            "generated_at": max((text(row.get("generated_at")) or "" for row in rows), default=""),
            "source_versions": {},
            "row_count": sum(int_value(row.get("row_count"), 0) for row in rows),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
        }
        if page is not None or page_size is not None or status or source_kind or search:
            result["rows_page"] = self._load_workbench_rows_page(
                scope_key="all",
                page=page,
                page_size=page_size,
                status=status,
                source_kind=source_kind,
                search=search,
            )
        return result

    def _load_all_workbench_rows_page_view(
        self,
        *,
        page: int | str | None,
        page_size: int | str | None,
        status: str | None,
        source_kind: str | None,
        search: str | None,
    ) -> dict[str, Any] | None:
        rows = self._connection.fetch_all(
            """
            select
                scope_key,
                coalesce(payload #> '{payload,summary}', payload->'summary', '{}'::jsonb) as summary,
                cache_status,
                generated_at,
                row_count
            from read_model.workbench_snapshots
            where scope_key <> 'all'
            order by scope_key desc
            """
        )
        if not rows:
            return None
        combined = {
            "month": "all",
            "summary": {
                "oa_count": 0,
                "bank_count": 0,
                "invoice_count": 0,
                "paired_count": 0,
                "open_count": 0,
                "exception_count": 0,
            },
            "paired": {"groups": []},
            "open": {"groups": []},
            "read_model_scope_key": "all",
            "page_mode": "sql_rows",
        }
        for row in rows:
            summary = row.get("summary") if isinstance(row.get("summary"), dict) else {}
            for key in ("oa_count", "bank_count", "invoice_count", "paired_count", "open_count", "exception_count"):
                combined["summary"][key] += int_value(summary.get(key), 0)
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = 'all'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """
        )
        refresh_status = "fresh"
        if dirty_row is not None:
            refresh_status = "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"
        return {
            "scope_key": "all",
            "payload": combined,
            "cache_status": "fresh",
            "generated_at": max((text(row.get("generated_at")) or "" for row in rows), default=""),
            "source_versions": {},
            "row_count": sum(int_value(row.get("row_count"), 0) for row in rows),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
            "rows_page": self._load_workbench_rows_page(
                scope_key="all",
                page=page,
                page_size=page_size,
                status=status,
                source_kind=source_kind,
                search=search,
            ),
        }

    def load_workbench_read_models(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select scope_key as key, payload, raw_payload from read_model.workbench_snapshots order by scope_key")
        if rows:
            return {"read_models": {str(row.get("key")): _read_model_payload(row) for row in rows}}
        return {}

    def save_workbench_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: set[str] | None = None,
        refresh_all_scope_from_month_shards: bool = True,
        raise_on_all_scope_parent_inconsistent: bool = False,
    ) -> None:
        started_generations: list[tuple[str, str, dict[str, Any]]] = []
        published_scope_keys: set[str] = set()

        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            refresh_all_scope = False
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    if scope_key == "all" or (
                        refresh_all_scope_from_month_shards and MONTH_SCOPE_RE.match(str(scope_key or ""))
                    ):
                        refresh_all_scope = True
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                self._lock_workbench_generation_scope(connection, scope_key=scope_key)
                if scope_key == "all" or (
                    refresh_all_scope_from_month_shards and MONTH_SCOPE_RE.match(str(scope_key or ""))
                ):
                    refresh_all_scope = True
                grouped_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
                generated_at = text(payload.get("generated_at"))
                cache_status = text(payload.get("cache_status") or "fresh") or "fresh"
                scope_month = month_start(payload.get("scope_month") or payload.get("month") or grouped_payload.get("month") or scope_key)
                workbench_rows = list(self._iter_workbench_rows(grouped_payload))
                workbench_groups = list(self._iter_workbench_groups(grouped_payload))
                summary_payload = self._workbench_summary_from_payload(
                    scope_key=scope_key,
                    grouped_payload=grouped_payload,
                    source_versions=source_versions,
                    generated_at=generated_at,
                )
                incoming_source_version = _source_version_value(source_versions)
                active_generation_id = self._active_workbench_generation_id(connection, scope_key=scope_key)
                if active_generation_id:
                    existing_row = connection.fetch_one(
                        """
                        select source_versions
                        from read_model.workbench_snapshots
                        where scope_key = %s
                          and generation_id = %s
                        order by generated_at desc
                        limit 1
                        """,
                        (scope_key, active_generation_id),
                    )
                else:
                    existing_row = connection.fetch_one(
                        """
                        select source_versions
                        from read_model.workbench_snapshots
                        where scope_key = %s
                        order by generated_at desc
                        limit 1
                        """,
                        (scope_key,),
                    )
                existing_source_versions = existing_row.get("source_versions") if isinstance(existing_row, dict) else {}
                if (
                    incoming_source_version is not None
                    and _source_version_value(existing_source_versions) is not None
                    and incoming_source_version < _source_version_value(existing_source_versions)
                    and _workbench_source_versions_allow_stale_write_skip(
                        source_versions,
                        existing_source_versions,
                    )
                ):
                    continue
                generation_id = self._new_workbench_generation_id(scope_key)
                row_count = len(workbench_rows) or int_value(payload.get("row_count"), 0)
                group_count = len(workbench_groups)
                started_generations.append((scope_key, generation_id, source_versions))
                self._start_workbench_generation(
                    connection,
                    scope_key=scope_key,
                    generation_id=generation_id,
                    source_versions=source_versions,
                    generated_at=generated_at,
                    row_count=row_count,
                    group_count=group_count,
                    build_metadata={"source": "save_workbench_read_models"},
                )
                connection.execute(
                    """
                    insert into read_model.workbench_snapshots(generation_id, scope_key, scope_month, source_versions, generated_at, cache_status, row_count, payload, raw_payload)
                    values (%s, %s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s)
                    on conflict (generation_id, scope_key) do update set
                        scope_month = excluded.scope_month,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        row_count = excluded.row_count,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        generation_id,
                        scope_key,
                        scope_month,
                        jsonb(source_versions),
                        generated_at,
                        cache_status,
                        row_count,
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                connection.execute(
                    """
                    insert into read_model.workbench_summary(
                        generation_id, scope_key, scope_month, source_versions, generated_at, cache_status,
                        summary, invoice_inventory, payload, raw_payload
                    )
                    values (%s, %s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (generation_id, scope_key) do update set
                        scope_month = excluded.scope_month,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        summary = excluded.summary,
                        invoice_inventory = excluded.invoice_inventory,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        generation_id,
                        scope_key,
                        scope_month,
                        jsonb(source_versions),
                        generated_at,
                        cache_status,
                        jsonb(summary_payload.get("summary") if isinstance(summary_payload.get("summary"), dict) else {}),
                        jsonb(summary_payload.get("invoice_inventory") if isinstance(summary_payload.get("invoice_inventory"), dict) else {}),
                        jsonb(summary_payload),
                        jsonb({"normalized_payload": summary_payload}),
                    ),
                )
                self._upsert_workbench_generation_stats(
                    connection,
                    generation_id=generation_id,
                    scope_key=scope_key,
                    summary_payload=summary_payload,
                )
                workbench_row_params: list[tuple[Any, ...]] = []
                for row in workbench_rows:
                    row_id = text(row.get("id") or row.get("row_id"))
                    if row_id is None:
                        continue
                    workbench_row_params.append(
                        (
                            generation_id,
                            row_id,
                            month_start(row.get("scope_month") or row.get("month") or scope_month),
                            scope_key,
                            text(row.get("source_kind") or row.get("type") or "workbench_row") or "workbench_row",
                            text(row.get("status") or payload.get("status") or "open") or "open",
                            text(row.get("project_id")),
                            text(row.get("project_name") or row.get("project")),
                            text(row.get("counterparty_name") or row.get("counterparty") or row.get("supplier_name")),
                            decimal_text(
                                row.get("amount_value")
                                or row.get("amount")
                                or row.get("amount_with_tax")
                                or row.get("invoice_amount")
                            ),
                            text(row.get("object_identity_key")),
                            text(row.get("object_identity_kind")),
                            text(row.get("object_identity_source")),
                            text(row.get("object_identity_confidence")),
                            jsonb(source_versions),
                            generated_at,
                            cache_status,
                            jsonb(row),
                            jsonb({"normalized_payload": row}),
                        ),
                    )
                _execute_many(
                    connection,
                    """
                    insert into read_model.workbench_rows(
                        generation_id, row_id, scope_month, scope_key, source_kind, status, project_id, project_name,
                        counterparty_name, amount, object_identity_key, object_identity_kind,
                        object_identity_source, object_identity_confidence,
                        source_versions, generated_at, cache_status, payload, raw_payload
                    )
                    values (
                        %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (generation_id, scope_key, row_id) do update set
                        scope_month = excluded.scope_month,
                        scope_key = excluded.scope_key,
                        source_kind = excluded.source_kind,
                        status = excluded.status,
                        project_id = excluded.project_id,
                        project_name = excluded.project_name,
                        counterparty_name = excluded.counterparty_name,
                        amount = excluded.amount,
                        object_identity_key = excluded.object_identity_key,
                        object_identity_kind = excluded.object_identity_kind,
                        object_identity_source = excluded.object_identity_source,
                        object_identity_confidence = excluded.object_identity_confidence,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    workbench_row_params,
                )
                workbench_group_params: list[tuple[Any, ...]] = []
                workbench_group_row_params: list[tuple[Any, ...]] = []
                for group in workbench_groups:
                    group_id = text(group.get("group_id"))
                    if group_id is None:
                        continue
                    group_scope_month = month_start(group.get("scope_month") or group.get("month") or scope_month)
                    workbench_group_params.append(
                        (
                            generation_id,
                            group_id,
                            scope_key,
                            group_scope_month,
                            text(group.get("zone")) or "open",
                            text(group.get("status")) or text(group.get("zone")) or "open",
                            text(group.get("group_type")) or "candidate",
                            text_list(group.get("source_kinds")),
                            int_value(group.get("row_count"), 0),
                            text(group.get("searchable_text")) or "",
                            text(group.get("oa_sort_min")),
                            text(group.get("oa_sort_max")),
                            text(group.get("bank_sort_min")),
                            text(group.get("bank_sort_max")),
                            text(group.get("invoice_sort_min")),
                            text(group.get("invoice_sort_max")),
                            jsonb(source_versions),
                            generated_at,
                            cache_status,
                            jsonb(group.get("payload") if isinstance(group.get("payload"), dict) else group),
                            jsonb({"normalized_payload": group}),
                        ),
                    )
                    for group_row in _workbench_group_row_records(_workbench_group_payload_for_rows(group)):
                        workbench_group_row_params.append(
                            (
                                generation_id,
                                scope_key,
                                group_scope_month,
                                text(group_row.get("zone")) or text(group.get("zone")) or "open",
                                group_id,
                                text(group_row.get("pane")) or "",
                                text(group_row.get("row_id")) or "",
                                text(group_row.get("row_role")) or "normal",
                                int_value(group_row.get("row_index"), 0),
                                text(group_row.get("source_kind")) or "workbench_row",
                                text(group_row.get("status")) or text(group.get("status")) or "open",
                                text(group_row.get("time_value")),
                                text(group_row.get("time_date")),
                                jsonb(group_row.get("column_values") if isinstance(group_row.get("column_values"), dict) else {}),
                                text(group_row.get("searchable_text")) or "",
                                text(group_row.get("object_identity_key")),
                                text(group_row.get("object_identity_kind")),
                                text(group_row.get("object_identity_source")),
                                text(group_row.get("object_identity_confidence")),
                                jsonb(source_versions),
                                generated_at,
                                cache_status,
                                jsonb(group_row.get("payload") if isinstance(group_row.get("payload"), dict) else group_row),
                                jsonb({"normalized_payload": group_row}),
                            ),
                        )
                _execute_many(
                    connection,
                    """
                    insert into read_model.workbench_groups(
                        generation_id, group_id, scope_key, scope_month, zone, status, group_type, source_kinds,
                        row_count, searchable_text, oa_sort_min, oa_sort_max, bank_sort_min, bank_sort_max,
                        invoice_sort_min, invoice_sort_max, source_versions, generated_at, cache_status,
                        payload, raw_payload
                    )
                    values (
                        %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (generation_id, scope_key, zone, group_id) do update set
                        scope_month = excluded.scope_month,
                        status = excluded.status,
                        group_type = excluded.group_type,
                        source_kinds = excluded.source_kinds,
                        row_count = excluded.row_count,
                        searchable_text = excluded.searchable_text,
                        oa_sort_min = excluded.oa_sort_min,
                        oa_sort_max = excluded.oa_sort_max,
                        bank_sort_min = excluded.bank_sort_min,
                        bank_sort_max = excluded.bank_sort_max,
                        invoice_sort_min = excluded.invoice_sort_min,
                        invoice_sort_max = excluded.invoice_sort_max,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    workbench_group_params,
                )
                _execute_many(
                    connection,
                    """
                    insert into read_model.workbench_group_rows(
                        generation_id, scope_key, scope_month, zone, group_id, pane, row_id, row_role, row_index,
                        source_kind, status, time_value, time_date, column_values, searchable_text,
                        object_identity_key, object_identity_kind, object_identity_source, object_identity_confidence,
                        source_versions, generated_at, cache_status, payload, raw_payload
                    )
                    values (
                        %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s,
                        %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (generation_id, scope_key, zone, group_id, pane, row_role, row_id) do update set
                        scope_month = excluded.scope_month,
                        row_index = excluded.row_index,
                        source_kind = excluded.source_kind,
                        status = excluded.status,
                        time_value = excluded.time_value,
                        time_date = excluded.time_date,
                        column_values = excluded.column_values,
                        searchable_text = excluded.searchable_text,
                        object_identity_key = excluded.object_identity_key,
                        object_identity_kind = excluded.object_identity_kind,
                        object_identity_source = excluded.object_identity_source,
                        object_identity_confidence = excluded.object_identity_confidence,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    workbench_group_row_params,
                )
                self._activate_workbench_generation(
                    connection,
                    scope_key=scope_key,
                    generation_id=generation_id,
                    row_count=row_count,
                    group_count=group_count,
                    summary_count=1,
                )
                published_scope_keys.add(scope_key)
            if refresh_all_scope:
                if self._refresh_workbench_all_scope_from_month_shards(
                    connection,
                    raise_on_parent_inconsistent=raise_on_all_scope_parent_inconsistent,
                ):
                    published_scope_keys.add("all")

        try:
            run_in_transaction(self._connection, write)
        except Exception as exc:
            for scope_key, generation_id, source_versions in started_generations:
                def mark_failed(
                    connection: Any,
                    *,
                    scope_key: str = scope_key,
                    generation_id: str = generation_id,
                    source_versions: dict[str, Any] = source_versions,
                ) -> None:
                    self._fail_workbench_generation(
                        connection,
                        scope_key=scope_key,
                        generation_id=generation_id,
                        source_versions=source_versions,
                        error=str(exc),
                    )

                try:
                    run_in_transaction(self._connection, mark_failed)
                except Exception:
                    pass
            raise
        self._prune_workbench_generations_after_publish(published_scope_keys)

    def _prune_workbench_generations_after_publish(self, scope_keys: set[str]) -> None:
        normalized_scope_keys = self._normalize_workbench_retention_scope_keys(scope_keys)
        if not normalized_scope_keys:
            return
        try:
            result = self.prune_workbench_generations(
                keep_recent_generations_per_scope=WORKBENCH_GENERATION_RETENTION_KEEP_RECENT,
                keep_days=WORKBENCH_GENERATION_RETENTION_KEEP_DAYS,
                limit=WORKBENCH_GENERATION_RETENTION_LIMIT,
                dry_run=False,
                scope_keys=normalized_scope_keys,
            )
        except Exception:
            LOGGER.warning(
                "workbench generation retention failed after publish for scopes=%s",
                ",".join(normalized_scope_keys),
                exc_info=True,
            )
            return
        deleted_count = int_value(result.get("deleted_count"), 0)
        if deleted_count:
            LOGGER.info(
                "pruned %s old workbench read model generations for scopes=%s",
                deleted_count,
                ",".join(normalized_scope_keys),
            )

    def _refresh_workbench_all_scope_from_month_shards(
        self,
        connection: Any,
        *,
        raise_on_parent_inconsistent: bool = False,
    ) -> bool:
        self._lock_workbench_generation_scope(connection, scope_key="all")
        consistency_failures = self._workbench_generation_consistency_failures(connection, include_all=False)
        if consistency_failures:
            if raise_on_parent_inconsistent:
                parent_scope_keys = ",".join(
                    sorted(
                        {
                            str(failure.get("scope_key") or "").strip()
                            for failure in consistency_failures
                            if str(failure.get("scope_key") or "").strip()
                        }
                    )
                )
                raise RuntimeError(
                    "workbench_read_model_not_fresh: parent_generation_inconsistent "
                    f"parent_scope_keys={parent_scope_keys}; "
                    + self._workbench_generation_consistency_error(consistency_failures)
                )
            return False
        group_rows = connection.fetch_all(
            """
            select g.scope_key, g.scope_month, g.zone, g.group_id, g.payload, g.source_versions, g.generated_at::text as generated_at
            from read_model.workbench_groups g
            join read_model.workbench_generations gen
              on gen.generation_id = g.generation_id
             and gen.scope_key = g.scope_key
             and gen.tenant_id = 'default'
             and gen.status = 'active'
            where g.scope_key <> 'all'
            order by g.scope_month desc nulls last, g.zone, g.group_id, g.updated_at desc
            """
        )
        groups = []
        max_generated_at = ""
        max_source_version: int | None = None
        parser_versions: set[str] = set()
        bank_auto_tag_rules_versions: set[str] = set()
        oa_projection_sync_versions: set[str] = set()
        workbench_matching_rules_versions: set[str] = set()
        has_group_without_parser_version = False
        has_group_without_bank_auto_tag_rules_version = False
        has_group_without_oa_projection_sync_version = False
        has_group_without_workbench_matching_rules_version = False
        for row in group_rows:
            group = _read_model_payload(row)
            if not isinstance(group, dict):
                continue
            row_source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
            parser_version = text(row_source_versions.get("oa_attachment_invoice_parser_version"))
            if parser_version:
                parser_versions.add(parser_version)
            else:
                has_group_without_parser_version = True
            bank_auto_tag_rules_version = text(row_source_versions.get("bank_auto_tag_rules_version"))
            if bank_auto_tag_rules_version:
                bank_auto_tag_rules_versions.add(bank_auto_tag_rules_version)
            else:
                has_group_without_bank_auto_tag_rules_version = True
            oa_projection_sync_version = text(row_source_versions.get("oa_projection_sync_version"))
            if oa_projection_sync_version:
                oa_projection_sync_versions.add(oa_projection_sync_version)
            else:
                has_group_without_oa_projection_sync_version = True
            workbench_matching_rules_version = text(row_source_versions.get("workbench_matching_rules_version"))
            if workbench_matching_rules_version:
                workbench_matching_rules_versions.add(workbench_matching_rules_version)
            else:
                has_group_without_workbench_matching_rules_version = True
            normalized_group = deepcopy(group)
            normalized_group["_source_scope_key"] = text(row.get("scope_key"))
            normalized_group["_source_scope_month"] = text(row.get("scope_month"))
            normalized_group.setdefault("group_id", text(row.get("group_id")))
            normalized_group["zone"] = text(row.get("zone")) or normalized_group.get("zone") or "open"
            normalized_group["scope_key"] = "all"
            normalized_group["month"] = "all"
            normalized_group["scope_month"] = None
            groups.append(normalized_group)
            generated_at = text(row.get("generated_at")) or ""
            if generated_at > max_generated_at:
                max_generated_at = generated_at
            source_version = _source_version_value(row.get("source_versions"))
            if source_version is not None:
                max_source_version = max(source_version, max_source_version or source_version)
        if not groups:
            return False

        (
            canonical_paired_row_keys,
            canonical_paired_identity_keys,
            canonical_relation_claims_by_row_key,
        ) = _workbench_active_relation_claim_keys_for_groups(
            connection,
            groups,
        )
        aggregate_payload = _aggregate_workbench_all_scope_payload(
            groups,
            paired_row_keys=canonical_paired_row_keys,
            paired_identity_keys=canonical_paired_identity_keys,
            canonical_relation_claims_by_row_key=canonical_relation_claims_by_row_key,
        )
        aggregate_source_versions = {
            "builder": WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION,
            "source_version": max_source_version or 0,
        }
        if len(parser_versions) == 1 and not has_group_without_parser_version:
            aggregate_source_versions["oa_attachment_invoice_parser_version"] = next(iter(parser_versions))
        if len(bank_auto_tag_rules_versions) == 1 and not has_group_without_bank_auto_tag_rules_version:
            aggregate_source_versions["bank_auto_tag_rules_version"] = next(iter(bank_auto_tag_rules_versions))
        if len(oa_projection_sync_versions) == 1 and not has_group_without_oa_projection_sync_version:
            aggregate_source_versions["oa_projection_sync_version"] = next(iter(oa_projection_sync_versions))
        if len(workbench_matching_rules_versions) == 1 and not has_group_without_workbench_matching_rules_version:
            aggregate_source_versions["workbench_matching_rules_version"] = next(iter(workbench_matching_rules_versions))
        generated_at = max_generated_at or None
        workbench_rows = list(self._iter_workbench_rows(aggregate_payload))
        workbench_groups = list(self._iter_workbench_groups(aggregate_payload))
        generation_id = self._new_workbench_generation_id("all")
        self._start_workbench_generation(
            connection,
            scope_key="all",
            generation_id=generation_id,
            source_versions=aggregate_source_versions,
            generated_at=generated_at,
            row_count=len(workbench_rows),
            group_count=len(workbench_groups),
            build_metadata={"source": "_refresh_workbench_all_scope_from_month_shards"},
        )
        connection.execute(
            """
            insert into read_model.workbench_snapshots(
                generation_id, scope_key, scope_month, source_versions, generated_at, cache_status, row_count, payload, raw_payload
            )
            values (%s, 'all', null, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s, %s)
            on conflict (generation_id, scope_key) do update set
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                row_count = excluded.row_count,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                generation_id,
                jsonb(aggregate_source_versions),
                generated_at,
                len(workbench_rows),
                jsonb(
                    {
                        "scope_key": "all",
                        "scope_month": "all",
                        "generated_at": generated_at,
                        "cache_status": "fresh",
                        "payload": aggregate_payload,
                        "source_versions": aggregate_source_versions,
                    }
                ),
                jsonb({"normalized_payload": aggregate_payload}),
            ),
        )
        workbench_row_params: list[tuple[Any, ...]] = []
        for row in workbench_rows:
            row_id = text(row.get("id") or row.get("row_id"))
            if row_id is None:
                continue
            workbench_row_params.append(
                (
                    generation_id,
                    row_id,
                    month_start(row.get("scope_month") or row.get("month")),
                    text(row.get("source_kind") or row.get("type") or "workbench_row") or "workbench_row",
                    text(row.get("status") or "open") or "open",
                    text(row.get("project_id")),
                    text(row.get("project_name") or row.get("project")),
                    text(row.get("counterparty_name") or row.get("counterparty") or row.get("supplier_name")),
                    decimal_text(row.get("amount") or row.get("amount_with_tax") or row.get("invoice_amount")),
                    text(row.get("object_identity_key")),
                    text(row.get("object_identity_kind")),
                    text(row.get("object_identity_source")),
                    text(row.get("object_identity_confidence")),
                    jsonb(aggregate_source_versions),
                    generated_at,
                    jsonb(row),
                    jsonb({"normalized_payload": row}),
                ),
            )
        _execute_many(
            connection,
            """
            insert into read_model.workbench_rows(
                generation_id, row_id, scope_month, scope_key, source_kind, status, project_id, project_name,
                counterparty_name, amount, object_identity_key, object_identity_kind,
                object_identity_source, object_identity_confidence,
                source_versions, generated_at, cache_status, payload, raw_payload
            )
            values (
                %s, %s, %s::date, 'all', %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s
            )
            on conflict (generation_id, scope_key, row_id) do update set
                scope_month = excluded.scope_month,
                source_kind = excluded.source_kind,
                status = excluded.status,
                project_id = excluded.project_id,
                project_name = excluded.project_name,
                counterparty_name = excluded.counterparty_name,
                amount = excluded.amount,
                object_identity_key = excluded.object_identity_key,
                object_identity_kind = excluded.object_identity_kind,
                object_identity_source = excluded.object_identity_source,
                object_identity_confidence = excluded.object_identity_confidence,
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            workbench_row_params,
        )
        workbench_group_params: list[tuple[Any, ...]] = []
        workbench_group_row_params: list[tuple[Any, ...]] = []
        for group in workbench_groups:
            group_id = text(group.get("group_id"))
            if group_id is None:
                continue
            sort_keys = _workbench_group_sort_keys(group)
            workbench_group_params.append(
                (
                    generation_id,
                    group_id,
                    text(group.get("zone")) or "open",
                    text(group.get("status")) or text(group.get("zone")) or "open",
                    text(group.get("group_type")) or "candidate",
                    text_list(group.get("source_kinds")),
                    int_value(group.get("row_count"), 0),
                    text(group.get("searchable_text")) or _searchable_group_text(group),
                    text(group.get("oa_sort_min") or sort_keys.get("oa_sort_min")),
                    text(group.get("oa_sort_max") or sort_keys.get("oa_sort_max")),
                    text(group.get("bank_sort_min") or sort_keys.get("bank_sort_min")),
                    text(group.get("bank_sort_max") or sort_keys.get("bank_sort_max")),
                    text(group.get("invoice_sort_min") or sort_keys.get("invoice_sort_min")),
                    text(group.get("invoice_sort_max") or sort_keys.get("invoice_sort_max")),
                    jsonb(aggregate_source_versions),
                    generated_at,
                    jsonb(group.get("payload") if isinstance(group.get("payload"), dict) else group),
                    jsonb({"normalized_payload": group}),
                ),
            )
            for group_row in _workbench_group_row_records(_workbench_group_payload_for_rows(group)):
                workbench_group_row_params.append(
                    (
                        generation_id,
                        text(group_row.get("zone")) or text(group.get("zone")) or "open",
                        group_id,
                        text(group_row.get("pane")) or "",
                        text(group_row.get("row_id")) or "",
                        text(group_row.get("row_role")) or "normal",
                        int_value(group_row.get("row_index"), 0),
                        text(group_row.get("source_kind")) or "workbench_row",
                        text(group_row.get("status")) or text(group.get("status")) or "open",
                        text(group_row.get("time_value")),
                        text(group_row.get("time_date")),
                        jsonb(group_row.get("column_values") if isinstance(group_row.get("column_values"), dict) else {}),
                        text(group_row.get("searchable_text")) or "",
                        text(group_row.get("object_identity_key")),
                        text(group_row.get("object_identity_kind")),
                        text(group_row.get("object_identity_source")),
                        text(group_row.get("object_identity_confidence")),
                        jsonb(aggregate_source_versions),
                        generated_at,
                        jsonb(group_row.get("payload") if isinstance(group_row.get("payload"), dict) else group_row),
                        jsonb({"normalized_payload": group_row}),
                    ),
                )
        _execute_many(
            connection,
            """
            insert into read_model.workbench_groups(
                generation_id, group_id, scope_key, scope_month, zone, status, group_type, source_kinds,
                row_count, searchable_text, oa_sort_min, oa_sort_max, bank_sort_min, bank_sort_max,
                invoice_sort_min, invoice_sort_max, source_versions, generated_at, cache_status,
                payload, raw_payload
            )
            values (
                %s, %s, 'all', null, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s
            )
            on conflict (generation_id, scope_key, zone, group_id) do update set
                scope_month = excluded.scope_month,
                status = excluded.status,
                group_type = excluded.group_type,
                source_kinds = excluded.source_kinds,
                row_count = excluded.row_count,
                searchable_text = excluded.searchable_text,
                oa_sort_min = excluded.oa_sort_min,
                oa_sort_max = excluded.oa_sort_max,
                bank_sort_min = excluded.bank_sort_min,
                bank_sort_max = excluded.bank_sort_max,
                invoice_sort_min = excluded.invoice_sort_min,
                invoice_sort_max = excluded.invoice_sort_max,
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            workbench_group_params,
        )
        _execute_many(
            connection,
            """
            insert into read_model.workbench_group_rows(
                generation_id, scope_key, scope_month, zone, group_id, pane, row_id, row_role, row_index,
                source_kind, status, time_value, time_date, column_values, searchable_text,
                object_identity_key, object_identity_kind, object_identity_source, object_identity_confidence,
                source_versions, generated_at, cache_status, payload, raw_payload
            )
            values (
                %s, 'all', null, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::date, %s, %s,
                %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s
            )
            on conflict (generation_id, scope_key, zone, group_id, pane, row_role, row_id) do update set
                scope_month = excluded.scope_month,
                row_index = excluded.row_index,
                source_kind = excluded.source_kind,
                status = excluded.status,
                time_value = excluded.time_value,
                time_date = excluded.time_date,
                column_values = excluded.column_values,
                searchable_text = excluded.searchable_text,
                object_identity_key = excluded.object_identity_key,
                object_identity_kind = excluded.object_identity_kind,
                object_identity_source = excluded.object_identity_source,
                object_identity_confidence = excluded.object_identity_confidence,
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            workbench_group_row_params,
        )
        final_summary_payload = self._workbench_summary_from_payload(
            scope_key="all",
            grouped_payload=aggregate_payload,
            source_versions=aggregate_source_versions,
            generated_at=generated_at,
        )
        final_summary_payload["invoice_inventory"] = self._workbench_invoice_inventory(
            scope_key="all",
            generation_id=generation_id,
        )
        connection.execute(
            """
            insert into read_model.workbench_summary(
                generation_id, scope_key, scope_month, source_versions, generated_at, cache_status,
                summary, invoice_inventory, payload, raw_payload
            )
            values (%s, 'all', null, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s, %s, %s)
            on conflict (generation_id, scope_key) do update set
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                summary = excluded.summary,
                invoice_inventory = excluded.invoice_inventory,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            (
                generation_id,
                jsonb(aggregate_source_versions),
                generated_at,
                jsonb(final_summary_payload.get("summary") if isinstance(final_summary_payload.get("summary"), dict) else {}),
                jsonb(
                    final_summary_payload.get("invoice_inventory")
                    if isinstance(final_summary_payload.get("invoice_inventory"), dict)
                    else {}
                ),
                jsonb(final_summary_payload),
                jsonb({"normalized_payload": final_summary_payload}),
            ),
        )
        self._upsert_workbench_generation_stats(
            connection,
            generation_id=generation_id,
            scope_key="all",
            summary_payload=final_summary_payload,
        )
        self._activate_workbench_generation(
            connection,
            scope_key="all",
            generation_id=generation_id,
            row_count=len(workbench_rows),
            group_count=len(workbench_groups),
            summary_count=1,
        )
        return True

    def _load_workbench_rows_page(
        self,
        *,
        scope_key: str,
        page: int | str | None,
        page_size: int | str | None,
        status: str | None,
        source_kind: str | None,
        search: str | None,
    ) -> dict[str, Any]:
        normalized_page = max(1, int_value(page, 1))
        normalized_page_size = min(200, max(1, int_value(page_size, 100)))
        offset = (normalized_page - 1) * normalized_page_size
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=scope_key)
        if scope_key == "all" and active_generation_id:
            clauses = ["scope_key = %s"]
            params = ["all"]
        elif scope_key == "all":
            clauses = ["scope_key <> 'all'"]
            params: list[Any] = []
        else:
            clauses = ["scope_key = %s"]
            params = [scope_key]
        if active_generation_id:
            clauses.append("generation_id = %s")
            params.append(active_generation_id)
        if normalized := text(status):
            clauses.append("status = %s")
            params.append(normalized)
        if normalized := text(source_kind):
            clauses.append("source_kind = %s")
            params.append(normalized)
        if normalized := text(search):
            clauses.append("(project_name ilike %s or counterparty_name ilike %s or row_id ilike %s)")
            pattern = f"%{normalized}%"
            params.extend([pattern, pattern, pattern])
        where_sql = " and ".join(clauses)
        count_row = self._connection.fetch_one(
            f"""
            select count(*) as total_count
            from read_model.workbench_rows
            where {where_sql}
            """,
            tuple(params),
        )
        params.extend([normalized_page_size + 1, offset])
        rows = self._connection.fetch_all(
            f"""
            select row_id, source_kind, status, payload, raw_payload
            from read_model.workbench_rows
            where {where_sql}
            order by updated_at desc, row_id
            limit %s offset %s
            """,
            tuple(params),
        )
        visible_rows = rows[:normalized_page_size]
        payload_rows = [
            _read_model_payload(row) if isinstance(_read_model_payload(row), dict) else {"id": text(row.get("row_id"))}
            for row in visible_rows
        ]
        return {
            "page": normalized_page,
            "page_size": normalized_page_size,
            "total": int_value((count_row or {}).get("total_count"), 0),
            "has_more": len(rows) > normalized_page_size,
            "rows": payload_rows,
        }

    def load_batch_accounting_workbench_payload(self, *, bank_year: str, oa_year: str) -> dict[str, Any] | None:
        resolved_bank_year = text(bank_year)
        resolved_oa_year = text(oa_year)
        if not resolved_bank_year or not resolved_oa_year:
            return None
        bank_start = f"{resolved_bank_year}-01-01"
        oa_start = f"{resolved_oa_year}-01-01"
        bank_rows = self._connection.fetch_all(
            """
            select r.row_id, r.source_kind, r.status, r.payload, r.raw_payload
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.scope_key <> 'all'
              and r.source_kind = 'bank'
              and (
                    r.counterparty_name = %s
                    or r.payload->>'counterparty_name' = %s
                    or r.payload->>'counterparty_name_raw' = %s
                  )
              and (
                    r.scope_month >= %s::date
                    and r.scope_month < (%s::date + interval '1 year')
                  )
            order by coalesce(r.payload->>'trade_time', r.payload->>'pay_receive_time', r.payload->>'txn_date', '') desc, r.row_id
            """,
            ("批量账务集中处理", "批量账务集中处理", "批量账务集中处理", bank_start, bank_start),
        )
        oa_rows = self._connection.fetch_all(
            """
            select r.row_id, r.source_kind, r.status, r.payload, r.raw_payload
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.scope_key <> 'all'
              and r.source_kind = 'oa'
              and (
                    r.scope_month >= %s::date
                    and r.scope_month < (%s::date + interval '1 year')
                  )
            order by coalesce(r.payload->>'apply_time', r.payload->>'application_time', r.payload->>'application_date', r.payload->>'created_at', '') desc, r.row_id
            """,
            (oa_start, oa_start),
        )
        invoice_rows = self._connection.fetch_all(
            """
            select r.row_id, r.source_kind, r.status, r.payload, r.raw_payload
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.scope_key <> 'all'
              and r.source_kind = 'oa_attachment_invoice'
              and (
                    r.scope_month >= %s::date
                    and r.scope_month < (%s::date + interval '1 year')
                  )
            order by r.row_id
            """,
            (oa_start, oa_start),
        )
        return {
            "month": "all",
            "summary": {},
            "paired": {"groups": []},
            "open": {
                "groups": [
                    {
                        "group_id": f"batch-accounting:{resolved_bank_year}:{resolved_oa_year}",
                        "group_type": "batch_accounting_sql_read_model",
                        "bank_rows": self._payload_rows(bank_rows),
                        "oa_rows": self._payload_rows(oa_rows),
                        "invoice_rows": self._payload_rows(invoice_rows),
                    }
                ]
            },
        }

    @staticmethod
    def _payload_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload_rows: list[dict[str, Any]] = []
        for row in rows:
            payload = _read_model_payload(row)
            if isinstance(payload, dict):
                payload_rows.append(payload)
                continue
            row_id = text(row.get("row_id"))
            if row_id:
                payload_rows.append({"id": row_id, "type": text(row.get("source_kind")) or "unknown"})
        return payload_rows

    def load_workbench_candidate_matches(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            "select candidate_key as key, payload, raw_payload from read_model.workbench_candidate_matches order by candidate_key"
        )
        values = {
            str(row.get("key")): payload
            for row in rows
            if (payload := _read_model_payload(row, drop_rebuildable_rows=True)) is not None
        }
        scope_rows = self._connection.fetch_all(
            """
            select
                to_char(scope_month, 'YYYY-MM') as scope_month,
                source_versions,
                completed_at::text as generated_at,
                request_id,
                reason
            from job.workbench_matching_dirty_scopes
            where tenant_id = 'default'
              and status = 'completed'
            order by scope_month
            """
        )
        scope_runs: dict[str, dict[str, Any]] = {}
        for row in scope_rows:
            scope_month = str(row.get("scope_month") or "").strip()
            if not MONTH_SCOPE_RE.match(scope_month):
                continue
            scope_runs[scope_month] = {
                "schema_version": CANDIDATE_MATCH_SCHEMA_VERSION,
                "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
                "candidate_count": 0,
                "generated_at": str(row.get("generated_at") or ""),
                "request_id": str(row.get("request_id") or ""),
                "reason": str(row.get("reason") or ""),
            }
        result: dict[str, Any] = {}
        if values:
            result["candidates"] = values
        if scope_runs:
            result["schema_version"] = CANDIDATE_MATCH_SCHEMA_VERSION
            result["scope_runs"] = scope_runs
        return result

    def upsert_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        decisions: list[dict[str, Any]],
    ) -> None:
        def write(connection: Any) -> None:
            dirty_scope_keys: set[str] = set()
            for decision in decisions:
                payload = serialize_value(decision)
                scope_month = month_start(payload.get("scope_month"))
                if scope_month is not None:
                    dirty_scope_keys.add(str(scope_month)[:7])
                connection.execute(
                    """
                    insert into read_model.workbench_reconciliation_decisions(
                        tenant_id, scope_month, decision_id, decision_key, display_state, decision_status,
                        match_domain, match_shape, rule_code, rule_version, row_ids, row_types,
                        oa_row_ids, bank_row_ids, invoice_row_ids, amount, direction, cardinality,
                        payment_amount_closed, invoice_amount_closed, warnings, evidence, blockers,
                        conflict_set, explanation, source_versions, generated_at, raw_payload
                    )
                    values (
                        %s, %s::date, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s,
                        %s, %s, %s::timestamptz, %s
                    )
                    on conflict (tenant_id, decision_key) do update set
                        scope_month = excluded.scope_month,
                        decision_id = excluded.decision_id,
                        display_state = excluded.display_state,
                        decision_status = excluded.decision_status,
                        match_domain = excluded.match_domain,
                        match_shape = excluded.match_shape,
                        rule_code = excluded.rule_code,
                        rule_version = excluded.rule_version,
                        row_ids = excluded.row_ids,
                        row_types = excluded.row_types,
                        oa_row_ids = excluded.oa_row_ids,
                        bank_row_ids = excluded.bank_row_ids,
                        invoice_row_ids = excluded.invoice_row_ids,
                        amount = excluded.amount,
                        direction = excluded.direction,
                        cardinality = excluded.cardinality,
                        payment_amount_closed = excluded.payment_amount_closed,
                        invoice_amount_closed = excluded.invoice_amount_closed,
                        warnings = excluded.warnings,
                        evidence = excluded.evidence,
                        blockers = excluded.blockers,
                        conflict_set = excluded.conflict_set,
                        explanation = excluded.explanation,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        raw_payload = excluded.raw_payload,
                        consumed_by_relation_id = null,
                        suppressed_by_exception_case_id = null,
                        updated_at = now()
                    """,
                    (
                        text(tenant_id) or "default",
                        month_start(payload.get("scope_month")),
                        text(payload.get("decision_id")),
                        text(payload.get("decision_key")),
                        text(payload.get("display_state")),
                        text(payload.get("decision_status")),
                        text(payload.get("match_domain")),
                        text(payload.get("match_shape")),
                        text(payload.get("rule_code")),
                        text(payload.get("rule_version")),
                        text_list(payload.get("row_ids")),
                        _workbench_reconciliation_row_types(payload),
                        text_list(payload.get("oa_row_ids")),
                        text_list(payload.get("bank_row_ids")),
                        text_list(payload.get("invoice_row_ids")),
                        decimal_text(payload.get("amount")),
                        text(payload.get("direction")),
                        text(payload.get("cardinality")),
                        bool(payload.get("payment_amount_closed")),
                        bool(payload.get("invoice_amount_closed")),
                        jsonb(payload.get("warnings") if isinstance(payload.get("warnings"), list) else []),
                        jsonb(payload.get("evidence") if isinstance(payload.get("evidence"), dict) else {}),
                        jsonb(payload.get("blockers") if isinstance(payload.get("blockers"), list) else []),
                        jsonb(payload.get("conflict_set") if isinstance(payload.get("conflict_set"), list) else []),
                        text(payload.get("explanation")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            for scope_key in sorted(dirty_scope_keys):
                _enqueue_workbench_relation_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_changed",
                )
                _enqueue_workbench_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_changed",
                )

        run_in_transaction(self._connection, write)

    def list_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        statuses: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        where = ["tenant_id = %s", "scope_month = %s::date"]
        params: list[Any] = [text(tenant_id) or "default", month_start(scope_month)]
        if statuses:
            where.append("decision_status = any(%s)")
            params.append(sorted(str(status) for status in statuses))
        rows = self._connection.fetch_all(
            f"""
            select
                decision_key, scope_month, display_state, decision_status, match_domain, match_shape,
                rule_code, rule_version, row_ids, oa_row_ids, bank_row_ids, invoice_row_ids,
                amount, direction, payment_amount_closed, invoice_amount_closed, warnings, evidence,
                blockers, source_versions, consumed_by_relation_id, suppressed_by_exception_case_id,
                decision_id, explanation, raw_payload
            from read_model.workbench_reconciliation_decisions
            where {" and ".join(where)}
            order by decision_key
            """,
            tuple(params),
        )
        return [_workbench_reconciliation_decision_payload(row) for row in rows]

    def list_active_workbench_reconciliation_decisions_for_cleanup(
        self,
        *,
        tenant_id: str,
        scope_months: list[str] | None = None,
        decision_keys: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        where = [
            "dec.tenant_id = %s",
            "dec.decision_status in ('proposed', 'paired', 'open')",
        ]
        params: list[Any] = [text(tenant_id) or "default"]
        normalized_scope_months = sorted(
            {month for month in (month_start(value) for value in list(scope_months or [])) if month}
        )
        normalized_decision_keys = sorted({value for value in (text(value) for value in list(decision_keys or [])) if value})
        if normalized_scope_months:
            where.append("dec.scope_month = any(%s::date[])")
            params.append(normalized_scope_months)
        if normalized_decision_keys:
            where.append("dec.decision_key = any(%s)")
            params.append(normalized_decision_keys)
        rows = self._connection.fetch_all(
            f"""
            select
                dec.decision_key,
                dec.scope_month,
                dec.display_state,
                dec.decision_status,
                dec.match_domain,
                dec.match_shape,
                dec.rule_code,
                dec.rule_version,
                dec.row_ids,
                dec.oa_row_ids,
                dec.bank_row_ids,
                dec.invoice_row_ids,
                dec.amount,
                dec.direction,
                dec.payment_amount_closed,
                dec.invoice_amount_closed,
                dec.warnings,
                dec.evidence,
                dec.blockers,
                dec.source_versions,
                dec.consumed_by_relation_id,
                dec.suppressed_by_exception_case_id,
                dec.decision_id,
                dec.explanation,
                dec.raw_payload,
                dec.updated_at,
                coalesce(active_relation_overlaps.items, '[]'::jsonb) as active_relation_overlaps,
                coalesce(submitted_no_oa_batch_overlaps.items, '[]'::jsonb) as submitted_no_oa_batch_overlaps
            from read_model.workbench_reconciliation_decisions dec
            left join lateral (
                select jsonb_agg(
                    jsonb_build_object(
                        'case_id', rel.case_id,
                        'relation_mode', rel.relation_mode,
                        'month_scope', coalesce(to_char(rel.month_scope, 'YYYY-MM'), 'all'),
                        'row_ids', rel.row_ids,
                        'row_types', rel.row_types,
                        'overlap_row_ids', overlap_rows.overlap_row_ids
                    )
                    order by rel.case_id
                ) as items
                from app.workbench_pair_relations rel
                cross join lateral (
                    select array_agg(decision_row_id order by decision_row_id) as overlap_row_ids
                    from unnest(dec.row_ids) decision_row_id
                    where decision_row_id = any(rel.row_ids)
                ) overlap_rows
                where rel.status = 'active'
                  and rel.row_ids && dec.row_ids
                  and cardinality(overlap_rows.overlap_row_ids) > 0
                  and (
                    rel.month_scope is null
                    or rel.month_scope between (dec.scope_month - interval '2 months')::date
                                           and (dec.scope_month + interval '2 months')::date
                  )
            ) active_relation_overlaps on true
            left join lateral (
                select jsonb_agg(
                    jsonb_build_object(
                        'batch_id', batch.batch_id,
                        'batch_type', batch.raw_payload->'normalized_payload'->>'batch_type',
                        'batch_label', batch.raw_payload->'normalized_payload'->>'batch_label',
                        'status', batch.status,
                        'scope_month', coalesce(to_char(batch.scope_month, 'YYYY-MM'), 'all'),
                        'bank_transaction_ids', batch.bank_transaction_ids,
                        'overlap_row_ids', overlap_rows.overlap_row_ids
                    )
                    order by batch.batch_id
                ) as items
                from app.no_oa_bank_batches batch
                cross join lateral (
                    select array_agg(decision_bank_row_id order by decision_bank_row_id) as overlap_row_ids
                    from unnest(dec.bank_row_ids) decision_bank_row_id
                    where decision_bank_row_id = any(batch.bank_transaction_ids)
                ) overlap_rows
                where batch.status = 'submitted'
                  and batch.bank_transaction_ids && dec.bank_row_ids
                  and cardinality(overlap_rows.overlap_row_ids) > 0
                  and (
                    batch.scope_month is null
                    or batch.scope_month between (dec.scope_month - interval '2 months')::date
                                             and (dec.scope_month + interval '2 months')::date
                  )
            ) submitted_no_oa_batch_overlaps on true
            where {" and ".join(where)}
            order by dec.scope_month, dec.decision_key
            """,
            tuple(params),
        )
        payloads: list[dict[str, Any]] = []
        for row in rows:
            payload = _workbench_reconciliation_decision_payload(row)
            payload["active_relation_overlaps"] = (
                row.get("active_relation_overlaps") if isinstance(row.get("active_relation_overlaps"), list) else []
            )
            payload["submitted_no_oa_batch_overlaps"] = (
                row.get("submitted_no_oa_batch_overlaps")
                if isinstance(row.get("submitted_no_oa_batch_overlaps"), list)
                else []
            )
            payload["updated_at"] = text(row.get("updated_at"))
            payloads.append(payload)
        return payloads

    def expire_workbench_reconciliation_decisions_by_keys(
        self,
        *,
        tenant_id: str,
        decision_keys: list[str],
        reason: str,
        actor: str = "repair_workbench_reconciliation_decisions",
    ) -> dict[str, Any]:
        normalized_decision_keys = sorted({value for value in (text(value) for value in list(decision_keys or [])) if value})
        if not normalized_decision_keys:
            return {"expired_count": 0, "scope_keys": []}

        def write(connection: Any) -> dict[str, Any]:
            rows = connection.fetch_all(
                """
                with expired as (
                    update read_model.workbench_reconciliation_decisions
                    set decision_status = 'expired',
                        raw_payload = raw_payload || jsonb_build_object(
                            'expired_reason', %s::text,
                            'expired_by', %s::text
                        ),
                        updated_at = now()
                    where tenant_id = %s::text
                      and decision_key = any(%s::text[])
                      and decision_status in ('proposed', 'paired', 'open')
                    returning to_char(scope_month, 'YYYY-MM') as scope_key
                )
                select scope_key, count(*)::bigint as expired_count
                from expired
                group by scope_key
                order by scope_key
                """,
                (
                    text(reason) or "invalid_workbench_reconciliation_decision",
                    text(actor) or "repair_workbench_reconciliation_decisions",
                    text(tenant_id) or "default",
                    normalized_decision_keys,
                ),
            )
            scope_keys = [str(row.get("scope_key") or "").strip() for row in rows if str(row.get("scope_key") or "").strip()]
            expired_count = sum(int_value(row.get("expired_count"), 0) for row in rows)
            for scope_key in scope_keys:
                _enqueue_workbench_relation_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_expired",
                )
                _enqueue_workbench_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_expired",
                )
            return {"expired_count": expired_count, "scope_keys": scope_keys}

        result: dict[str, Any] = {"expired_count": 0, "scope_keys": []}

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def consume_workbench_reconciliation_decisions_by_row_ids(
        self,
        *,
        tenant_id: str,
        row_ids: list[str],
        relation_id: str,
    ) -> int:
        return int(
            self._connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'consumed',
                    consumed_by_relation_id = %s,
                    updated_at = now()
                where tenant_id = %s
                  and decision_status in ('proposed', 'paired', 'open')
                  and row_ids && %s
                """,
                (relation_id, text(tenant_id) or "default", text_list(row_ids)),
            )
            or 0
        )

    def suppress_workbench_reconciliation_decisions_by_row_ids(
        self,
        *,
        tenant_id: str,
        row_ids: list[str],
        exception_case_id: str,
    ) -> int:
        return int(
            self._connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'suppressed',
                    suppressed_by_exception_case_id = %s,
                    updated_at = now()
                where tenant_id = %s
                  and decision_status in ('proposed', 'paired', 'open')
                  and row_ids && %s
                """,
                (exception_case_id, text(tenant_id) or "default", text_list(row_ids)),
            )
            or 0
        )

    def expire_stale_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        source_versions: dict[str, object],
    ) -> int:
        normalized_scope_months = sorted({month_start(month) for month in scope_months if month_start(month)})

        def write(connection: Any) -> int:
            affected = int(
                connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'expired',
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = any(%s::date[])
                  and decision_status in ('proposed', 'paired', 'open')
                  and not (source_versions @> %s)
                """,
                (
                    text(tenant_id) or "default",
                    normalized_scope_months,
                    jsonb(source_versions),
                ),
            )
            or 0
            )
            if affected:
                for scope_month in normalized_scope_months:
                    scope_key = str(scope_month)[:7]
                    _enqueue_workbench_relation_refresh_in_transaction(
                        connection,
                        tenant_id=text(tenant_id) or "default",
                        scope_key=scope_key,
                        reason="workbench_reconciliation_decision_expired",
                    )
                    _enqueue_workbench_refresh_in_transaction(
                        connection,
                        tenant_id=text(tenant_id) or "default",
                        scope_key=scope_key,
                        reason="workbench_reconciliation_decision_expired",
                    )
            return affected

        result = 0

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def expire_missing_workbench_reconciliation_decisions(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        active_decision_keys: list[str],
    ) -> int:
        normalized_scope_month = month_start(scope_month)

        def write(connection: Any) -> int:
            affected = int(
                connection.execute(
                """
                update read_model.workbench_reconciliation_decisions
                set decision_status = 'expired',
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and decision_status in ('proposed', 'paired', 'open')
                  and not (decision_key = any(%s))
                """,
                (
                    text(tenant_id) or "default",
                    normalized_scope_month,
                    text_list(active_decision_keys),
                ),
            )
            or 0
            )
            if affected and normalized_scope_month is not None:
                scope_key = str(normalized_scope_month)[:7]
                _enqueue_workbench_relation_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_expired",
                )
                _enqueue_workbench_refresh_in_transaction(
                    connection,
                    tenant_id=text(tenant_id) or "default",
                    scope_key=scope_key,
                    reason="workbench_reconciliation_decision_expired",
                )
            return affected

        result = 0

        def capture(connection: Any) -> None:
            nonlocal result
            result = write(connection)

        run_in_transaction(self._connection, capture)
        return result

    def mark_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        normalized_months = sorted({str(month)[:7] for month in scope_months if str(month or "").strip()})

        def write(connection: Any) -> None:
            for scope_month in normalized_months:
                connection.execute(
                    """
                    insert into job.workbench_matching_dirty_scopes(
                        tenant_id, scope_month, reason, status, available_at, source_versions, raw_payload
                    )
                    values (
                        %s, %s::date, %s, 'dirty', now() + (%s::text || ' seconds')::interval, %s, %s
                    )
                    on conflict (tenant_id, scope_month) do update set
                        reason = excluded.reason,
                        status = 'dirty',
                        available_at = greatest(job.workbench_matching_dirty_scopes.available_at, excluded.available_at),
                        source_versions = job.workbench_matching_dirty_scopes.source_versions || excluded.source_versions,
                        lease_owner = null,
                        lease_expires_at = null,
                        updated_at = now()
                    """,
                    (
                        text(tenant_id) or "default",
                        month_start(scope_month),
                        text(reason),
                        max(0, int_value(debounce_seconds, 60)),
                        jsonb(source_versions),
                        jsonb({"reason": reason, "source_versions": source_versions}),
                    ),
                )

        run_in_transaction(self._connection, write)
        return normalized_months

    def mark_stale_workbench_matching_completed_scopes(
        self,
        *,
        tenant_id: str,
        source_versions: dict[str, object],
        reason: str,
        debounce_seconds: int,
        limit: int | None = None,
    ) -> list[str]:
        normalized_tenant = text(tenant_id) or "default"
        normalized_source_versions = dict(source_versions or {})
        if not normalized_source_versions:
            return []
        resolved_limit = max(1, int_value(limit, 100)) if limit is not None else 100
        resolved_debounce_seconds = max(0, int_value(debounce_seconds, 0))

        def write(connection: Any) -> list[dict[str, Any]]:
            return connection.fetch_all(
                """
                with stale as (
                    select id
                    from job.workbench_matching_dirty_scopes
                    where tenant_id = %s
                      and status = 'completed'
                      and not (coalesce(source_versions, '{}'::jsonb) @> %s)
                    order by completed_at nulls first, scope_month
                    limit %s
                    for update skip locked
                )
                update job.workbench_matching_dirty_scopes dirty
                set reason = %s,
                    status = 'dirty',
                    available_at = now() + (%s::text || ' seconds')::interval,
                    source_versions = coalesce(dirty.source_versions, '{}'::jsonb) || %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                from stale
                where dirty.id = stale.id
                returning to_char(dirty.scope_month, 'YYYY-MM') as scope_month
                """,
                (
                    normalized_tenant,
                    jsonb(normalized_source_versions),
                    resolved_limit,
                    text(reason),
                    resolved_debounce_seconds,
                    jsonb(normalized_source_versions),
                ),
            )

        rows = run_in_transaction(self._connection, write)
        return [str(row.get("scope_month")) for row in rows if row.get("scope_month")]

    def claim_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        worker_id: str,
        limit: int,
        lease_seconds: int,
        request_id: str | None = None,
    ) -> list[str]:
        resolved_request_id = text(request_id) or text(worker_id) or "worker"
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id) or "worker"

        def write(connection: Any) -> list[dict[str, Any]]:
            rows = connection.fetch_all(
                """
                with due as (
                    select id
                    from job.workbench_matching_dirty_scopes
                    where tenant_id = %s
                      and (
                        status in ('dirty', 'retry') and available_at <= now()
                        or status = 'processing' and lease_expires_at <= now()
                      )
                    order by available_at, scope_month
                    limit %s
                    for update skip locked
                )
                update job.workbench_matching_dirty_scopes dirty
                set status = 'processing',
                    lease_owner = %s,
                    lease_expires_at = now() + (%s::text || ' seconds')::interval,
                    request_id = %s || ':' || to_char(dirty.scope_month, 'YYYY-MM'),
                    started_at = now(),
                    completed_at = null,
                    failed_at = null,
                    duration_ms = null,
                    error_summary = null,
                    updated_at = now()
                from due
                where dirty.id = due.id
                returning to_char(dirty.scope_month, 'YYYY-MM') as scope_month,
                          dirty.request_id,
                          dirty.source_versions
                """,
                (
                    normalized_tenant,
                    max(1, int_value(limit, 1)),
                    normalized_worker,
                    max(1, int_value(lease_seconds, 600)),
                    resolved_request_id,
                ),
            )
            for row in rows:
                connection.execute(
                    """
                    insert into app.matching_runs(
                        tenant_id, run_id, request_id, scope_month, triggered_by,
                        executed_at, started_at, status, source_versions, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s, now(), now(), 'running', %s, %s)
                    on conflict (tenant_id, request_id) where request_id is not null do update set
                        started_at = excluded.started_at,
                        status = 'running',
                        source_versions = excluded.source_versions,
                        updated_at = now()
                    """,
                    (
                        normalized_tenant,
                        text(row.get("request_id")),
                        text(row.get("request_id")),
                        month_start(row.get("scope_month")),
                        normalized_worker,
                        jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                        jsonb({"scope_month": row.get("scope_month"), "worker_id": normalized_worker}),
                    ),
                )
            return rows

        rows = run_in_transaction(self._connection, write)
        return [str(row.get("scope_month")) for row in rows if row.get("scope_month")]

    def complete_workbench_matching_dirty_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        source_versions: dict[str, object],
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id)
        normalized_request = text(request_id)
        if not normalized_worker:
            raise ValueError("worker_id is required to complete a workbench matching dirty scope.")
        if not normalized_request:
            raise ValueError("request_id is required to complete a workbench matching dirty scope.")

        def write(connection: Any) -> None:
            row = connection.fetch_one(
                """
                update job.workbench_matching_dirty_scopes
                set status = 'completed',
                    completed_at = now(),
                    failed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    source_versions = %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'processing'
                  and lease_owner = %s
                  and request_id = %s
                returning request_id, duration_ms
                """,
                (
                    jsonb(source_versions),
                    normalized_tenant,
                    month_start(scope_month),
                    normalized_worker,
                    normalized_request,
                ),
            )
            if not isinstance(row, dict):
                raise RuntimeError("Workbench matching dirty scope is not actively leased.")
            connection.execute(
                """
                update app.matching_runs
                set status = 'completed',
                    completed_at = now(),
                    failed_at = null,
                    duration_ms = %s,
                    source_versions = %s,
                    updated_at = now()
                where tenant_id = %s and request_id = %s
                """,
                (
                    int_value(row.get("duration_ms"), 0),
                    jsonb(source_versions),
                    normalized_tenant,
                    text(row.get("request_id")),
                ),
            )

        run_in_transaction(self._connection, write)

    def fail_workbench_matching_dirty_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        error: str,
        retry_delay_seconds: int | None,
        retry_max_attempts: int,
        retry_backoff_seconds: list[int],
        worker_id: str | None = None,
        request_id: str | None = None,
    ) -> None:
        delay_seconds = int_value(retry_delay_seconds, 0)
        backoff_sql = _retry_backoff_case_sql(retry_backoff_seconds)
        normalized_tenant = text(tenant_id) or "default"
        normalized_worker = text(worker_id)
        normalized_request = text(request_id)
        if not normalized_worker:
            raise ValueError("worker_id is required to fail a workbench matching dirty scope.")
        if not normalized_request:
            raise ValueError("request_id is required to fail a workbench matching dirty scope.")

        def write(connection: Any) -> None:
            row = connection.fetch_one(
                f"""
                update job.workbench_matching_dirty_scopes
                set attempt_count = attempt_count + 1,
                    status = case when attempt_count + 1 >= %s then 'failed' else 'retry' end,
                    last_error = %s,
                    failed_at = now(),
                    completed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    error_summary = %s,
                    available_at = now() + (
                        (case when %s > 0 then %s else {backoff_sql} end)::text || ' seconds'
                    )::interval,
                    lease_owner = null,
                    lease_expires_at = null,
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'processing'
                  and lease_owner = %s
                  and request_id = %s
                returning request_id, duration_ms, source_versions
                """,
                (
                    max(1, int_value(retry_max_attempts, 5)),
                    text(error),
                    text(error),
                    max(0, delay_seconds),
                    max(0, delay_seconds),
                    normalized_tenant,
                    month_start(scope_month),
                    normalized_worker,
                    normalized_request,
                ),
            )
            if not isinstance(row, dict):
                raise RuntimeError("Workbench matching dirty scope is not actively leased.")
            connection.execute(
                """
                update app.matching_runs
                set status = 'failed',
                    failed_at = now(),
                    duration_ms = %s,
                    source_versions = %s,
                    error_summary = %s,
                    updated_at = now()
                where tenant_id = %s and request_id = %s
                """,
                (
                    int_value(row.get("duration_ms"), 0),
                    jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                    text(error),
                    normalized_tenant,
                    text(row.get("request_id")),
                ),
            )

        run_in_transaction(self._connection, write)

    def list_workbench_matching_dirty_scopes(self, *, tenant_id: str) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select tenant_id, to_char(scope_month, 'YYYY-MM') as scope_month, reason, status,
                   attempt_count, last_error, available_at, lease_owner, lease_expires_at,
                   request_id, started_at, completed_at, failed_at, duration_ms, source_versions, error_summary
            from job.workbench_matching_dirty_scopes
            where tenant_id = %s
            order by scope_month
            """,
            (text(tenant_id) or "default",),
        )

    def list_workbench_matching_runs(self, *, tenant_id: str) -> list[dict[str, Any]]:
        return self._connection.fetch_all(
            """
            select to_char(scope_month, 'YYYY-MM') as scope_month, request_id, started_at, completed_at,
                   failed_at, duration_ms, status, source_versions, error_summary
            from app.matching_runs
            where tenant_id = %s and request_id is not null
            order by started_at, request_id
            """,
            (text(tenant_id) or "default",),
        )

    def save_workbench_candidate_matches(self, snapshot: dict[str, Any], *, changed_scope_months: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            candidates = snapshot.get("candidates") if isinstance(snapshot, dict) else None
            normalized_months = {str(month)[:7] for month in changed_scope_months or set() if str(month or "").strip()}
            scope_runs = snapshot.get("scope_runs") if isinstance(snapshot, dict) else None
            incoming_versions_by_month = {
                str(month)[:7]: _source_version_value(
                    run.get("source_versions") if isinstance(run, dict) else {}
                )
                for month, run in iter_mapping(scope_runs)
                if str(month or "").strip()
            }
            stale_months: set[str] = set()
            for scope_month in sorted(normalized_months):
                incoming_source_version = incoming_versions_by_month.get(scope_month)
                existing_row = connection.fetch_one(
                    """
                    select max((source_versions->>'source_version')::bigint) as source_version
                    from read_model.workbench_candidate_matches
                    where to_char(scope_month, 'YYYY-MM') = %s
                      and source_versions ? 'source_version'
                    """,
                    (scope_month,),
                )
                existing_source_version = _source_version_value(
                    {"source_version": existing_row.get("source_version")} if isinstance(existing_row, dict) else {}
                )
                if (
                    incoming_source_version is not None
                    and existing_source_version is not None
                    and incoming_source_version < existing_source_version
                ):
                    stale_months.add(scope_month)
                    continue
                connection.execute(
                    "delete from read_model.workbench_candidate_matches where to_char(scope_month, 'YYYY-MM') = %s",
                    (scope_month,),
                )
            for candidate_key, payload in iter_mapping(candidates):
                scope_month = month_start(payload.get("scope_month") or payload.get("month"))
                normalized_scope_month = str(scope_month or "")[:7]
                if normalized_months and normalized_scope_month not in normalized_months:
                    continue
                if normalized_scope_month in stale_months:
                    continue
                connection.execute(
                    """
                    insert into read_model.workbench_candidate_matches(
                        candidate_key, scope_month, status, row_ids, confidence, source_versions,
                        generated_at, cache_status, payload, raw_payload
                    )
                    values (%s, %s::date, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s)
                    on conflict (candidate_key) do update set
                        scope_month = excluded.scope_month,
                        status = excluded.status,
                        row_ids = excluded.row_ids,
                        confidence = excluded.confidence,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        candidate_key,
                        scope_month,
                        text(payload.get("status") or "active"),
                        text_list(payload.get("row_ids")),
                        decimal_text(payload.get("confidence")),
                        jsonb(payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}),
                        text(payload.get("generated_at")),
                        text(payload.get("cache_status") or "fresh"),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def load_cost_statistics_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.cost_statistics_read_models order by scope_key",
            "read_models",
        )

    def get_cost_statistics_view(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key:
            return None
        row = self._connection.fetch_one(
            """
            select scope_key, project_scope, scope_month, generated_at, entry_count, source_versions, payload, raw_payload
            from read_model.cost_statistics_read_models
            where scope_key = %s
            limit 1
            """,
            (normalized_scope_key,),
        )
        if row is None:
            return None
        stored_payload = _read_model_payload(row)
        if not isinstance(stored_payload, dict):
            stored_payload = {}
        row_items = self._connection.fetch_all(
            """
            select
                scope_key, project_scope, scope_month::text as scope_month, row_key, transaction_id,
                group_id, trade_time_text, trade_date::text as trade_date, counterparty_name,
                payment_account_label, direction, remark, project_id, project_name, expense_type,
                expense_content, amount::text as amount, oa_applicant, source_versions,
                generated_at::text as generated_at, cache_status, payload, raw_payload
            from read_model.cost_statistics_rows
            where scope_key = %s
            order by trade_date desc nulls last, trade_time_text desc, transaction_id, row_key
            """,
            (normalized_scope_key,),
        )
        if row_items:
            payload = _cost_statistics_payload_from_rows(
                scope_key=normalized_scope_key,
                parent_payload=stored_payload,
                parent_row=row,
                rows=row_items,
            )
        else:
            payload = stored_payload.get("payload") if isinstance(stored_payload.get("payload"), dict) else stored_payload
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'cost_statistics'
              and scope_key = %s
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """,
            (normalized_scope_key,),
        )
        refresh_status = "fresh"
        if dirty_row is not None:
            refresh_status = "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"
        return {
            "scope_key": normalized_scope_key,
            "project_scope": text(row.get("project_scope") or payload.get("project_scope")),
            "payload": payload,
            "schema_version": text(row.get("schema_version") or stored_payload.get("schema_version") or payload.get("schema_version")),
            "generated_at": text(row.get("generated_at") or stored_payload.get("generated_at") or payload.get("generated_at")),
            "source_versions": (
                row.get("source_versions")
                if isinstance(row.get("source_versions"), dict)
                else stored_payload.get("source_versions")
                if isinstance(stored_payload.get("source_versions"), dict)
                else {}
            ),
            "entry_count": int_value(
                row.get("entry_count")
                or payload.get("entry_count")
                or ((payload.get("summary") if isinstance(payload.get("summary"), dict) else {}).get("row_count")),
                0,
            ),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
        }

    def save_cost_statistics_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            self._save_generic_read_model_snapshots(
                connection,
                snapshot,
                table="read_model.cost_statistics_read_models",
                changed_scope_keys=changed_scope_keys,
                default_project_scope="all",
            )
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                if _is_cost_statistics_parent_scope(scope_key, payload=model_payload):
                    connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
                    continue
                self._replace_cost_statistics_rows(connection, scope_key=scope_key, payload=payload)

        run_in_transaction(self._connection, write)

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.tax_offset_read_models order by scope_key",
            "read_models",
        )

    def list_no_oa_bank_batch_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        resolved_filters = filters if isinstance(filters, dict) else {}
        where: list[str] = ["status <> 'superseded'"]
        params: list[Any] = []
        if value := text(resolved_filters.get("month")):
            where.append("scope_month = %s::date")
            params.append(month_start(value))
        if value := text(resolved_filters.get("type")):
            where.append("batch_type = %s")
            params.append(value)
        if value := text(resolved_filters.get("status")):
            where.append("status = %s")
            params.append(value)
        if value := text(resolved_filters.get("bucket")):
            where.append("status_bucket = %s")
            params.append(value)
        if value := text(resolved_filters.get("account_key")):
            where.append("account_key = %s")
            params.append(value)
        rows = self._connection.fetch_all(
            f"""
            select batch_id, source_versions, payload, raw_payload
            from read_model.no_oa_bank_batch_rows
            where {" and ".join(where)}
            order by scope_month desc nulls last, generated_at desc, batch_id
            """,
            tuple(params),
        )
        if not rows:
            return [] if self._no_oa_bank_batch_readiness_is_fresh(text(resolved_filters.get("month"))) else None
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _read_model_payload(row)
            if isinstance(payload, dict):
                if isinstance(row.get("source_versions"), dict):
                    payload = {**payload, "source_versions": row.get("source_versions")}
                result.append(payload)
            elif batch_id := text(row.get("batch_id")):
                payload = {"batch_id": batch_id}
                if isinstance(row.get("source_versions"), dict):
                    payload["source_versions"] = row.get("source_versions")
                result.append(payload)
        return result

    def _no_oa_bank_batch_readiness_is_fresh(self, scope_key: str | None = None) -> bool:
        normalized_scope_key = text(scope_key)
        candidate_scope_keys = [normalized_scope_key, "all"] if normalized_scope_key else ["all"]
        if normalized_scope_key and self._refresh_status(scope_type="no_oa_bank_batch", scope_key=normalized_scope_key) != "fresh":
            return False
        for candidate_scope_key in candidate_scope_keys:
            if not candidate_scope_key:
                continue
            if self._refresh_status(scope_type="no_oa_bank_batch", scope_key=candidate_scope_key) != "fresh":
                continue
            if self._no_oa_bank_batch_readiness_scope_is_fresh(candidate_scope_key):
                return True
        return False

    def _no_oa_bank_batch_readiness_scope_is_fresh(self, scope_key: str) -> bool:
        row = self._connection.fetch_one(
            """
            select status
            from read_model.app_status_readiness
            where tenant_id = 'default'
              and read_model_key = 'no_oa_bank_batch'
              and scope_type = 'no_oa_bank_batch'
              and scope_key = %s
            limit 1
            """,
            (scope_key,),
        )
        return isinstance(row, dict) and text(row.get("status")) == "fresh"

    def list_turnover_ledger_view(
        self,
        *,
        family: str = "all",
        direction: str = "all",
        status: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
        scope_key: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_family = (text(family) or "all").lower()
        normalized_direction = (text(direction) or "all").lower()
        normalized_status = text(status)
        normalized_scope_key = text(scope_key) or "all"
        normalized_page = max(int_value(page, 1), 1)
        normalized_page_size = min(max(int_value(page_size, 50), 1), 200)
        clauses: list[str] = ["status <> 'withdrawn'"]
        params: list[Any] = []
        if normalized_scope_key != "all":
            clauses.append("scope_month = %s::date")
            params.append(month_start(normalized_scope_key))
        if normalized_family != "all":
            clauses.append("family = %s")
            params.append(normalized_family)
        if normalized_status:
            clauses.append("status = %s")
            params.append(normalized_status)
        where_sql = " and ".join(clauses)
        all_rows = self._connection.fetch_all(
            f"""
            select relation_id, family, status, amount::text as amount, source_versions, payload, raw_payload
            from read_model.turnover_ledger_rows
            where {where_sql}
            order by scope_month desc nulls last, generated_at desc, relation_id
            """,
            tuple(params),
        )
        if not all_rows:
            return None
        source_versions = _shared_source_versions(all_rows)
        ledger_rows = [_turnover_ledger_row_payload(row) for row in all_rows]
        if normalized_direction == "borrow_in":
            ledger_rows = [
                row for row in ledger_rows
                if row.get("business_type") == "borrow_in"
                or _decimal_or_zero(row.get("pending_repayment_amount")) > Decimal("0")
                or _decimal_or_zero(row.get("repaid_amount")) > Decimal("0")
            ]
        elif normalized_direction == "borrow_out":
            ledger_rows = [
                row for row in ledger_rows
                if row.get("business_type") in {"borrow_out", "business_receivable"}
                or _decimal_or_zero(row.get("pending_collection_amount")) > Decimal("0")
                or _decimal_or_zero(row.get("collected_amount")) > Decimal("0")
            ]
        visible_rows = ledger_rows[(normalized_page - 1) * normalized_page_size : normalized_page * normalized_page_size]
        return {
            "summary": _turnover_ledger_summary(ledger_rows),
            "family_summaries": [
                _turnover_ledger_family_summary(family_key, [row for row in ledger_rows if row.get("family") == family_key])
                for family_key in ("personal", "company", "bank", "business")
            ],
            "rows": visible_rows,
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": len(ledger_rows),
            },
            "filters": {
                "family": normalized_family,
                "direction": normalized_direction,
                "status": normalized_status,
            },
            "read_model_status": "fresh",
            "source_versions": source_versions,
        }

    def save_turnover_ledger_rows(self, payload: dict[str, Any], *, scope_key: str | None = None) -> None:
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return
        normalized_scope_key = text(scope_key) or text(payload.get("scope_key")) or "all"

        def write(connection: Any) -> None:
            if normalized_scope_key == "all":
                connection.execute("delete from read_model.turnover_ledger_rows", ())
            else:
                connection.execute(
                    "delete from read_model.turnover_ledger_rows where scope_month = %s::date",
                    (month_start(normalized_scope_key),),
                )
            for index, item in enumerate(rows):
                if not isinstance(item, dict):
                    continue
                row = serialize_value(item)
                relation_id = text(row.get("relation_id")) or f"turnover-row-{index}"
                bank_row_ids = text_list(row.get("bank_row_ids"))
                connection.execute(
                    """
                    insert into read_model.turnover_ledger_rows(
                        relation_id, scope_month, family, status, relation_type, source,
                        counterparty_name, amount, bank_row_ids, source_versions,
                        generated_at, cache_status, payload, raw_payload
                    )
                    values (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, now(), 'fresh', %s, %s)
                    on conflict (relation_id) do update set
                        scope_month = excluded.scope_month,
                        family = excluded.family,
                        status = excluded.status,
                        relation_type = excluded.relation_type,
                        source = excluded.source,
                        counterparty_name = excluded.counterparty_name,
                        amount = excluded.amount,
                        bank_row_ids = excluded.bank_row_ids,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        relation_id,
                        month_start(row.get("first_transaction_at") or row.get("borrow_date") or row.get("scope_month")),
                        text(row.get("family")),
                        text(row.get("status") or "suggested"),
                        text(row.get("relation_type") or row.get("business_type")),
                        text(row.get("source")),
                        text(row.get("counterparty_name")),
                        decimal_text(row.get("balance_amount") or row.get("principal_amount") or row.get("amount")),
                        bank_row_ids,
                        jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                        jsonb(row),
                        jsonb({"normalized_payload": row}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def clear_turnover_ledger_rows(self) -> None:
        self._connection.execute("delete from read_model.turnover_ledger_rows", ())

    def get_tax_offset_view(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key:
            return None
        row = self._connection.fetch_one(
            """
            select scope_key, scope_month, generated_at, entry_count, source_versions, schema_version, cache_status, payload, raw_payload
            from read_model.tax_offset_read_models
            where scope_key = %s
            limit 1
            """,
            (normalized_scope_key,),
        )
        if row is None:
            return None
        stored_payload = _read_model_payload(row)
        if not isinstance(stored_payload, dict):
            stored_payload = {}
        payload = stored_payload.get("payload") if isinstance(stored_payload.get("payload"), dict) else stored_payload
        item_rows = self._connection.fetch_all(
            """
            select item_type, item_index, item_id, payload, raw_payload
            from read_model.tax_offset_items
            where scope_key = %s
            order by item_type, item_index, item_id
            """,
            (normalized_scope_key,),
        )
        if item_rows:
            payload = _tax_offset_payload_from_items(parent_payload=payload, rows=item_rows)
        dirty_row = self._connection.fetch_one(
            """
            select status, updated_at, last_error
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'tax_offset'
              and scope_key = %s
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """,
            (normalized_scope_key,),
        )
        refresh_status = "fresh"
        if dirty_row is not None:
            refresh_status = "refreshing" if text(dirty_row.get("status")) in {"pending", "processing"} else "stale"
        return {
            "scope_key": normalized_scope_key,
            "payload": payload,
            "schema_version": text(row.get("schema_version") or stored_payload.get("schema_version") or payload.get("schema_version")),
            "generated_at": text(row.get("generated_at") or stored_payload.get("generated_at") or payload.get("generated_at")),
            "source_versions": (
                row.get("source_versions")
                if isinstance(row.get("source_versions"), dict)
                else stored_payload.get("source_versions")
                if isinstance(stored_payload.get("source_versions"), dict)
                else {}
            ),
            "entry_count": int_value(row.get("entry_count") or stored_payload.get("entry_count") or _tax_offset_item_count(payload), 0),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
        }

    def save_tax_offset_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    connection.execute("delete from read_model.tax_offset_read_models where scope_key = %s", (scope_key,))
                    connection.execute("delete from read_model.tax_offset_items where scope_key = %s", (scope_key,))
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                source_counts = payload.get("source_counts") if isinstance(payload.get("source_counts"), dict) else {}
                source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
                row_count = self._read_model_row_count(payload)
                scope_month = month_start(payload.get("scope_month") or payload.get("month") or scope_key)
                connection.execute(
                    """
                    insert into read_model.tax_offset_read_models(
                        scope_key, scope_month, generated_at, entry_count,
                        source_counts, source_versions, schema_version, cache_status, payload, raw_payload
                    )
                    values (%s, %s::date, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        scope_month = excluded.scope_month,
                        generated_at = excluded.generated_at,
                        entry_count = excluded.entry_count,
                        source_counts = excluded.source_counts,
                        source_versions = excluded.source_versions,
                        schema_version = excluded.schema_version,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        scope_month,
                        text(payload.get("generated_at")),
                        row_count,
                        jsonb(source_counts),
                        jsonb(source_versions),
                        text(payload.get("schema_version")),
                        text(payload.get("cache_status") or "fresh"),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                if isinstance(model_payload, dict) and any(key in model_payload for key in _TAX_OFFSET_ITEM_TYPES):
                    self._replace_tax_offset_items(connection, scope_key=scope_key, payload=payload)

        run_in_transaction(self._connection, write)

    def _replace_cost_statistics_rows(self, connection: Any, *, scope_key: str, payload: dict[str, Any]) -> None:
        connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
        model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        time_rows = model_payload.get("time_rows") if isinstance(model_payload, dict) else None
        if not isinstance(time_rows, list):
            return
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        project_scope, scope_month_text = _parse_cost_statistics_scope_parts(scope_key, payload=model_payload)
        if scope_month_text == "all":
            raise ValueError("cost_statistics_rows only supports concrete month scopes.")
        scope_month = month_start(model_payload.get("scope_month") or model_payload.get("month") or scope_month_text)
        if scope_month is None:
            raise ValueError("cost_statistics_rows requires a concrete scope_month.")
        generated_at = text(payload.get("generated_at") or model_payload.get("generated_at"))
        cache_status = text(payload.get("cache_status") or model_payload.get("cache_status") or "fresh") or "fresh"
        row_params: list[tuple[Any, ...]] = []
        for index, item in enumerate(time_rows):
            if not isinstance(item, dict):
                continue
            row = serialize_value(item)
            transaction_id = text(row.get("transaction_id")) or f"row-{index}"
            row_key = text(row.get("row_key") or f"{transaction_id}:{index}") or f"row-{index}"
            row_params.append(
                (
                    scope_key,
                    project_scope,
                    scope_month,
                    row_key,
                    transaction_id,
                    text(row.get("group_id")),
                    text(row.get("trade_time")),
                    _date_text(row.get("trade_date") or row.get("trade_time")),
                    text(row.get("counterparty_name")),
                    text(row.get("payment_account_label")),
                    text(row.get("direction")),
                    text(row.get("remark")),
                    text(row.get("project_id")),
                    text(row.get("project_name")) or "未归集项目",
                    text(row.get("expense_type")) or "未分类",
                    text(row.get("expense_content")),
                    decimal_text(row.get("amount")) or "0",
                    text(row.get("oa_applicant")),
                    jsonb(source_versions),
                    generated_at,
                    cache_status,
                    jsonb(row),
                    jsonb({"normalized_payload": row}),
                ),
            )
        _execute_many(
            connection,
            """
            insert into read_model.cost_statistics_rows(
                scope_key, project_scope, scope_month, row_key, transaction_id, group_id,
                trade_time_text, trade_date, counterparty_name, payment_account_label, direction,
                remark, project_id, project_name, expense_type, expense_content, amount,
                oa_applicant, source_versions, generated_at, cache_status, payload, raw_payload
            )
            values (
                %s, %s, %s::date, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s
            )
            on conflict (scope_key, row_key) do update set
                project_scope = excluded.project_scope,
                scope_month = excluded.scope_month,
                transaction_id = excluded.transaction_id,
                group_id = excluded.group_id,
                trade_time_text = excluded.trade_time_text,
                trade_date = excluded.trade_date,
                counterparty_name = excluded.counterparty_name,
                payment_account_label = excluded.payment_account_label,
                direction = excluded.direction,
                remark = excluded.remark,
                project_id = excluded.project_id,
                project_name = excluded.project_name,
                expense_type = excluded.expense_type,
                expense_content = excluded.expense_content,
                amount = excluded.amount,
                oa_applicant = excluded.oa_applicant,
                source_versions = excluded.source_versions,
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                payload = excluded.payload,
                raw_payload = excluded.raw_payload,
                updated_at = now()
            """,
            row_params,
        )

    def _replace_tax_offset_items(self, connection: Any, *, scope_key: str, payload: dict[str, Any]) -> None:
        connection.execute("delete from read_model.tax_offset_items where scope_key = %s", (scope_key,))
        model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        if not isinstance(model_payload, dict):
            return
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        scope_month = month_start(model_payload.get("scope_month") or model_payload.get("month") or scope_key)
        generated_at = text(payload.get("generated_at") or model_payload.get("generated_at"))
        cache_status = text(payload.get("cache_status") or model_payload.get("cache_status") or "fresh") or "fresh"
        for payload_key, item_type in _TAX_OFFSET_ITEM_TYPES.items():
            items = model_payload.get(payload_key)
            if not isinstance(items, list):
                continue
            for index, item in enumerate(items):
                if not isinstance(item, dict):
                    continue
                row = serialize_value(item)
                item_id = text(row.get("id") or row.get("unique_key") or row.get("invoice_id")) or f"{item_type}:{index}"
                connection.execute(
                    """
                    insert into read_model.tax_offset_items(
                        scope_key, scope_month, item_type, item_id, item_index, issue_date,
                        invoice_no, invoice_code, digital_invoice_no, seller_name, seller_tax_no,
                        buyer_name, buyer_tax_no, invoice_type, tax_rate, tax_amount, total_with_tax,
                        source_kind, source_versions, generated_at, cache_status, payload, raw_payload
                    )
                    values (
                        %s, %s::date, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                    )
                    on conflict (scope_key, item_type, item_id) do update set
                        scope_month = excluded.scope_month,
                        item_index = excluded.item_index,
                        issue_date = excluded.issue_date,
                        invoice_no = excluded.invoice_no,
                        invoice_code = excluded.invoice_code,
                        digital_invoice_no = excluded.digital_invoice_no,
                        seller_name = excluded.seller_name,
                        seller_tax_no = excluded.seller_tax_no,
                        buyer_name = excluded.buyer_name,
                        buyer_tax_no = excluded.buyer_tax_no,
                        invoice_type = excluded.invoice_type,
                        tax_rate = excluded.tax_rate,
                        tax_amount = excluded.tax_amount,
                        total_with_tax = excluded.total_with_tax,
                        source_kind = excluded.source_kind,
                        source_versions = excluded.source_versions,
                        generated_at = excluded.generated_at,
                        cache_status = excluded.cache_status,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        scope_month,
                        item_type,
                        item_id,
                        index,
                        _date_text(row.get("issue_date") or row.get("invoice_date")),
                        text(row.get("invoice_no")),
                        text(row.get("invoice_code")),
                        text(row.get("digital_invoice_no")),
                        text(row.get("seller_name")),
                        text(row.get("seller_tax_no")),
                        text(row.get("buyer_name")),
                        text(row.get("buyer_tax_no")),
                        text(row.get("invoice_type")),
                        text(row.get("tax_rate")),
                        decimal_text(row.get("tax_amount")),
                        decimal_text(row.get("total_with_tax") or row.get("amount")),
                        text(row.get("source_kind")),
                        jsonb(source_versions),
                        generated_at,
                        cache_status,
                        jsonb(row),
                        jsonb({"normalized_payload": row}),
                    ),
                )

    def _load_table_map(self, sql: str, payload_key: str) -> dict[str, Any]:
        rows = self._connection.fetch_all(sql)
        values = {str(row.get("key")): _read_model_payload(row) for row in rows}
        return {payload_key: values} if values else {}

    def _save_generic_read_model_snapshots(
        self,
        connection: Any,
        snapshot: dict[str, Any],
        *,
        table: str,
        changed_scope_keys: set[str] | None,
        default_project_scope: str | None,
    ) -> None:
        read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
        if changed_scope_keys is not None:
            present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
            for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                connection.execute(f"delete from {table} where scope_key = %s", (scope_key,))
        for scope_key, payload in iter_mapping(read_models):
            if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                continue
            source_counts = payload.get("source_counts") if isinstance(payload.get("source_counts"), dict) else {}
            source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
            row_count = self._read_model_row_count(payload)
            scope_month = month_start(payload.get("scope_month") or payload.get("month") or scope_key)
            if default_project_scope is not None:
                connection.execute(
                    f"""
                    insert into {table}(
                        scope_key, project_scope, scope_month, generated_at, entry_count,
                        source_counts, source_versions, payload, raw_payload
                    )
                    values (%s, %s, %s::date, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        project_scope = excluded.project_scope,
                        scope_month = excluded.scope_month,
                        generated_at = excluded.generated_at,
                        entry_count = excluded.entry_count,
                        source_counts = excluded.source_counts,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        text(payload.get("project_scope") or default_project_scope) or default_project_scope,
                        scope_month,
                        text(payload.get("generated_at")),
                        row_count,
                        jsonb(source_counts),
                        jsonb(source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
            else:
                connection.execute(
                    f"""
                    insert into {table}(
                        scope_key, scope_month, generated_at, entry_count,
                        source_counts, source_versions, payload, raw_payload
                    )
                    values (%s, %s::date, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
                        scope_month = excluded.scope_month,
                        generated_at = excluded.generated_at,
                        entry_count = excluded.entry_count,
                        source_counts = excluded.source_counts,
                        source_versions = excluded.source_versions,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        scope_key,
                        scope_month,
                        text(payload.get("generated_at")),
                        row_count,
                        jsonb(source_counts),
                        jsonb(source_versions),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

    @staticmethod
    def _read_model_row_count(payload: dict[str, Any]) -> int:
        for key in ("entries", "rows", "items", "records"):
            value = payload.get(key)
            if isinstance(value, list):
                return len(value)
        tax_offset_count = 0
        for key in ("output_items", "input_plan_items", "certified_items"):
            value = payload.get(key)
            if isinstance(value, list):
                tax_offset_count += len(value)
        if tax_offset_count:
            return tax_offset_count
        return int_value(payload.get("entry_count") or payload.get("row_count"), 0)

    @staticmethod
    def _iter_workbench_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        seen: set[str] = set()

        def add_row(value: Any, *, zone: str | None = None) -> None:
            if not isinstance(value, dict):
                return
            row_id = text(value.get("id") or value.get("row_id"))
            if row_id is None or row_id in seen:
                return
            seen.add(row_id)
            row = serialize_value(value)
            if zone in {"paired", "open"}:
                row["status"] = zone
            rows.append(row)

        def scan_group(group: Any, *, zone: str | None = None) -> None:
            if not isinstance(group, dict):
                return
            for key, value in group.items():
                if not str(key).endswith("_rows") or not isinstance(value, list):
                    continue
                for row in value:
                    add_row(row, zone=zone)

        for direct_key in ("rows", "ignored_rows"):
            value = payload.get(direct_key)
            if isinstance(value, list):
                for row in value:
                    add_row(row)
        for section_name in ("paired", "open", "ignored"):
            section = payload.get(section_name)
            if not isinstance(section, dict):
                continue
            groups = section.get("groups")
            if isinstance(groups, list):
                for group in groups:
                    scan_group(group, zone=section_name)
            else:
                scan_group(section, zone=section_name)
        return rows

    @staticmethod
    def _iter_workbench_groups(payload: dict[str, Any]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        seen_row_sets: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for zone in ("paired", "open"):
            section = payload.get(zone)
            if not isinstance(section, dict):
                continue
            section_groups = section.get("groups")
            if not isinstance(section_groups, list):
                continue
            for index, group in enumerate(section_groups):
                if not isinstance(group, dict):
                    continue
                normalized_group = _with_workbench_group_counts(group)
                group_id = text(normalized_group.get("group_id") or normalized_group.get("id")) or f"{zone}:{index}"
                key = (zone, group_id)
                if key in seen:
                    continue
                seen.add(key)
                group_rows = list(_iter_group_rows(normalized_group))
                row_identity = _workbench_group_row_identity(normalized_group)
                if row_identity:
                    row_key = (zone, row_identity)
                    if row_key in seen_row_sets:
                        continue
                    seen_row_sets.add(row_key)
                source_kinds = sorted(
                    {
                        source_kind
                        for row in group_rows
                        if (source_kind := text(row.get("source_kind") or row.get("type"))) is not None
                    }
                )
                sort_keys = _workbench_group_sort_keys(normalized_group)
                groups.append(
                    {
                        "group_id": group_id,
                        "scope_month": normalized_group.get("scope_month") or normalized_group.get("month") or payload.get("month"),
                        "month": normalized_group.get("month") or payload.get("month"),
                        "zone": zone,
                        "status": zone,
                        "group_type": text(normalized_group.get("group_type")) or "candidate",
                        "source_kinds": source_kinds,
                        "row_count": _workbench_group_fact_row_counts(normalized_group)["rows"],
                        "searchable_text": _searchable_group_text(normalized_group),
                        **sort_keys,
                        "payload": serialize_value(normalized_group),
                    }
                )
        return groups


def _parse_pending_invoice_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = [part.strip() for part in str(scope_key or "").split(":")]
    direction = parts[0] if parts and parts[0] else "expense"
    filter_group = parts[1] if len(parts) > 1 and parts[1] else "all"
    month = parts[2] if len(parts) > 2 and parts[2] else ""
    return direction, filter_group, month_start(month)


def _pending_invoice_row_scope_key(*, direction: str, filter_group: str, scope_month: str | None) -> str:
    if scope_month:
        return f"{direction}:{filter_group}:{scope_month[:7]}"
    return f"{direction}:{filter_group}"


def _invoice_relation_scope_key(value: str | None) -> str:
    raw = str(value or "").strip()
    if not raw or raw == "all":
        return "all"
    if MONTH_SCOPE_RE.match(raw[:7]):
        return raw[:7]
    return "all"


def _invoice_relation_filter_clauses(
    filters: str | list[dict[str, Any]] | None,
    field_specs: dict[str, tuple[str, str, set[str]]],
) -> list[tuple[str, list[Any]]]:
    if filters in (None, ""):
        return []
    if isinstance(filters, str):
        parsed = json.loads(unquote(filters))
    else:
        parsed = filters
    if not isinstance(parsed, list):
        raise ValueError("invoice relation filters must be a list")
    clauses: list[tuple[str, list[Any]]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("invoice relation filter must be an object")
        field = text(item.get("field")) or ""
        operator = text(item.get("operator")) or ""
        if field not in field_specs or operator not in field_specs[field][2]:
            raise ValueError(f"unsupported invoice relation filter: {field}/{operator}")
        expression, mode, _operators = field_specs[field]
        if operator == "contains":
            clauses.append((f"{expression} ilike %s", [f"%{text(item.get('value')) or ''}%"]))
        elif operator == "equals":
            if mode == "money":
                clauses.append((f"{expression} = %s", [decimal_text(item.get("value"))]))
            elif mode == "date":
                clauses.append((f"{expression} = %s::date", [text(item.get("value"))]))
            else:
                clauses.append((f"{expression} = %s", [text(item.get("value")) or ""]))
        elif operator == "in":
            values = [str(value).strip() for value in list(item.get("values") or []) if str(value).strip()]
            if values:
                clauses.append((f"{expression} = any(%s)", [values]))
        elif operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            if mode == "money":
                minimum = decimal_text(bounds.get("min"))
                maximum = decimal_text(bounds.get("max"))
                if minimum is not None:
                    clauses.append((f"{expression} >= %s", [minimum]))
                if maximum is not None:
                    clauses.append((f"{expression} <= %s", [maximum]))
            else:
                start = text(bounds.get("min") or bounds.get("from"))
                end = text(bounds.get("max") or bounds.get("to"))
                if start:
                    clauses.append((f"{expression} >= %s::date", [start]))
                if end:
                    clauses.append((f"{expression} <= %s::date", [end]))
    return clauses


def _oa_pending_payment_view_mode_clause(view_mode: str | None) -> str:
    normalized = text(view_mode) or "completed"
    if normalized == "in_progress":
        return "oa_workflow_status = 'in_progress'"
    if normalized != "completed":
        raise ValueError("view_mode must be completed or in_progress")
    return "(oa_workflow_status is null or oa_workflow_status = '' or oa_workflow_status = 'completed')"


def _invoice_relation_order_sql(
    *,
    sort_field: str | None,
    sort_direction: str | None,
    sort_expressions: dict[str, str],
) -> str:
    field = text(sort_field) or "invoice_date"
    if field not in sort_expressions:
        raise ValueError(f"unsupported invoice relation sort field: {field}")
    direction = (text(sort_direction) or "desc").lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("invoice relation sort direction must be asc or desc")
    return f"{sort_expressions[field]} {direction} nulls last, row_id"


def _invoice_relation_summary_sql(*, table_name: str, where_sql: str, summary_kind: str) -> str:
    if summary_kind == "input":
        return f"""
        select
            count(*) as count,
            coalesce(sum(total_with_tax), 0) as total_with_tax,
            coalesce(sum(case when oa_relation_count > 0 then 1 else 0 end), 0) as matched_oa_count,
            coalesce(sum(case when bank_relation_count > 0 then 1 else 0 end), 0) as matched_bank_transaction_count,
            coalesce(sum(case when payment_status = 'pending' then 1 else 0 end), 0) as pending_count
        from {table_name}
        where {where_sql}
        """
    return f"""
    select
        count(*) as count,
        coalesce(sum(total_with_tax), 0) as total_with_tax,
        coalesce(sum(collected_amount), 0) as collected_amount,
        coalesce(sum(pending_amount), 0) as pending_amount,
        coalesce(sum(case when collection_status = 'pending_collection' then 1 else 0 end), 0) as pending_collection_count,
        coalesce(sum(case when collection_status = 'partial_collected' then 1 else 0 end), 0) as partial_collection_count,
        coalesce(sum(case when receipt_status = 'pending' then 1 else 0 end), 0) as receipt_pending_count
    from {table_name}
    where {where_sql}
    """


def _invoice_relation_summary_payload(row: dict[str, Any], *, summary_kind: str, total: int) -> dict[str, Any]:
    if summary_kind == "input":
        return {
            "invoiceCount": total,
            "totalWithTax": decimal_text(row.get("total_with_tax")) or "0.00",
            "matchedOaCount": int_value(row.get("matched_oa_count"), 0),
            "matchedBankTransactionCount": int_value(row.get("matched_bank_transaction_count"), 0),
            "pendingCount": int_value(row.get("pending_count"), 0),
        }
    return {
        "invoiceCount": total,
        "totalWithTax": decimal_text(row.get("total_with_tax")) or "0.00",
        "collectedAmount": decimal_text(row.get("collected_amount")) or "0.00",
        "pendingAmount": decimal_text(row.get("pending_amount")) or "0.00",
        "pendingCollectionCount": int_value(row.get("pending_collection_count"), 0),
        "partialCollectionCount": int_value(row.get("partial_collection_count"), 0),
        "receiptPendingCount": int_value(row.get("receipt_pending_count"), 0),
    }


def _input_invoice_usage_read_model_record(row: dict[str, Any], scope_key: str) -> dict[str, Any]:
    payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    payment = payload.get("paymentStatus") if isinstance(payload.get("paymentStatus"), dict) else {}
    oa = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
    bank = payload.get("bankTransactions") if isinstance(payload.get("bankTransactions"), dict) else {}
    record = _base_invoice_relation_record(payload, scope_key)
    record.update(
        {
            "seller_name": text(invoice.get("sellerName")),
            "seller_tax_no": text(invoice.get("sellerTaxNo")),
            "amount": decimal_text(invoice.get("amount")),
            "payment_status": text(payment.get("code")),
            "payment_status_label": text(payment.get("label")),
            "oa_applicant": text(oa.get("applicantName")),
            "oa_application_type": text(oa.get("applicationType")),
            "oa_project_name": text(oa.get("projectName")),
            "bank_counterparty_name": text(bank.get("counterpartyName")),
            "bank_trade_time": text(bank.get("tradeTime")),
            "bank_amount": decimal_text(bank.get("amount")),
            "bank_name": text(bank.get("bankName")),
            "bank_account": text(bank.get("bankAccount")) or _bank_account_label(bank),
            "bank_direction": text(bank.get("direction")),
            "bank_summary": text(bank.get("summary")),
            "oa_relation_count": int_value(oa.get("relationCount"), 0),
            "bank_relation_count": int_value(bank.get("relationCount"), 0),
        }
    )
    return record


def _bank_account_label(bank: dict[str, Any]) -> str | None:
    bank_name = text(bank.get("bankName"))
    account_last4 = text(bank.get("accountLast4"))
    value = " ".join(part for part in [bank_name, account_last4] if part)
    return value or None


def _bank_direction_from_payload(bank: dict[str, Any]) -> str | None:
    direction_label = text(bank.get("directionLabel"))
    if direction_label == "支出":
        return "outflow"
    if direction_label == "收入":
        return "inflow"
    return None


def _output_invoice_collection_read_model_record(row: dict[str, Any], scope_key: str) -> dict[str, Any]:
    payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    collection = payload.get("collectionStatus") if isinstance(payload.get("collectionStatus"), dict) else {}
    bank = payload.get("bankTransactions") if isinstance(payload.get("bankTransactions"), dict) else {}
    receipt = payload.get("receipt") if isinstance(payload.get("receipt"), dict) else {}
    red_invoice = payload.get("redInvoiceRelation") if isinstance(payload.get("redInvoiceRelation"), dict) else {}
    record = _base_invoice_relation_record(payload, scope_key)
    record.update(
        {
            "buyer_name": text(invoice.get("buyerName")),
            "buyer_tax_no": text(invoice.get("buyerTaxNo")),
            "seller_name": text(invoice.get("sellerName")),
            "seller_tax_no": text(invoice.get("sellerTaxNo")),
            "amount": decimal_text(invoice.get("amount") or invoice.get("amountWithoutTax")),
            "collection_status": text(collection.get("code")),
            "collection_status_label": text(collection.get("label")),
            "collected_amount": decimal_text(collection.get("collectedAmount")),
            "pending_amount": decimal_text(collection.get("pendingAmount")),
            "bank_counterparty_name": text(bank.get("counterpartyName")),
            "bank_trade_time": text(bank.get("tradeTime")),
            "bank_amount": decimal_text(bank.get("amount")),
            "bank_name": text(bank.get("bankName")),
            "bank_summary": text(bank.get("summary")),
            "receipt_status": text(receipt.get("status")),
            "receipt_status_label": text(receipt.get("label")),
            "bank_relation_count": int_value(bank.get("relationCount"), 0),
            "red_invoice_relation_count": int_value(red_invoice.get("relationCount"), 0),
        }
    )
    return record


def _oa_pending_payment_read_model_record(row: dict[str, Any], scope_key: str) -> dict[str, Any]:
    payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
    oa = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
    payment = payload.get("paymentStatus") if isinstance(payload.get("paymentStatus"), dict) else {}
    bank = payload.get("bankTransaction") if isinstance(payload.get("bankTransaction"), dict) else {}
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    trade_time = text(bank.get("tradeTime"))
    invoice_date = text(invoice.get("invoiceDate"))
    scope_month = month_start(scope_key) or month_start(trade_time[:10]) or month_start(str(oa.get("month") or "")) or month_start("1970-01")
    return {
        "row_id": text(payload.get("id")),
        "scope_key": scope_key,
        "scope_month": scope_month,
        "oa_id": text(oa.get("id")),
        "oa_applicant": text(oa.get("applicantName")),
        "oa_application_type": text(oa.get("applicationType")),
        "oa_workflow_status": text(oa.get("workflowStatus")),
        "oa_project_name": text(oa.get("projectName")),
        "oa_amount": decimal_text(oa.get("amount")),
        "payment_status": text(payment.get("code")),
        "payment_status_label": text(payment.get("label")),
        "bank_transaction_id": text(bank.get("primaryBankTransactionId")),
        "bank_trade_time": trade_time or None,
        "bank_amount": decimal_text(bank.get("amount") or bank.get("debitAmount")),
        "bank_paid_total": decimal_text(bank.get("paidTotal") or bank.get("amount") or bank.get("debitAmount")),
        "bank_name": text(bank.get("bankName")),
        "bank_account": text(bank.get("bankAccount")) or _bank_account_label(bank),
        "bank_direction": text(bank.get("direction")) or _bank_direction_from_payload(bank),
        "bank_counterparty_name": text(bank.get("counterpartyName")),
        "bank_summary": text(bank.get("summary")),
        "invoice_id": text(invoice.get("primaryInvoiceId")),
        "invoice_no": text(invoice.get("digitalInvoiceNo")),
        "invoice_date": invoice_date[:10] if invoice_date else None,
        "seller_name": text(invoice.get("sellerName")),
        "invoice_total_with_tax": decimal_text(invoice.get("totalWithTax")),
        "searchable_text": text(payload.get("searchText")) or json.dumps(payload, ensure_ascii=False, sort_keys=True)[:12000],
        "source_versions": jsonb(payload.get("sourceVersions") if isinstance(payload.get("sourceVersions"), dict) else {}),
        "payload": jsonb(payload),
        "raw_payload": jsonb({"source": "oa_pending_payment", "source_versions": payload.get("sourceVersions")}),
    }


def _invoice_lifecycle_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = row.get("payload") if isinstance(row.get("payload"), dict) else None
    if payload is not None and text(payload.get("subject_id")) and text(payload.get("subject_type")):
        return dict(payload)
    acquisition_status = row.get("acquisition_status") if isinstance(row.get("acquisition_status"), dict) else {}
    payment_status = row.get("payment_status") if isinstance(row.get("payment_status"), dict) else {}
    collection_status = row.get("collection_status") if isinstance(row.get("collection_status"), dict) else {}
    certification_status = row.get("certification_status") if isinstance(row.get("certification_status"), dict) else {}
    return {
        "subject_id": text(row.get("subject_id")),
        "subject_type": text(row.get("subject_type")),
        "scope_key": text(row.get("scope_key")),
        "scope_month": text(row.get("scope_month")),
        "invoice_identity_key": text(row.get("invoice_identity_key")),
        "lifecycle_status": text(row.get("lifecycle_status")) or _first_lifecycle_code(
            acquisition_status,
            payment_status,
            collection_status,
            certification_status,
        ),
        "acquisition_status": acquisition_status,
        "payment_status": payment_status,
        "collection_status": collection_status,
        "certification_status": certification_status,
    }


def _first_lifecycle_code(*statuses: dict[str, Any]) -> str:
    for status in statuses:
        code = text(status.get("code")) if isinstance(status, dict) else ""
        if code:
            return code
    return "unknown"


def _base_invoice_relation_record(payload: dict[str, Any], scope_key: str) -> dict[str, Any]:
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    invoice_date = text(invoice.get("invoiceDate") or invoice.get("issueDate"))
    scope_month = month_start(scope_key) or month_start(invoice_date) or month_start("1970-01")
    return {
        "row_id": text(payload.get("id")),
        "scope_key": scope_key,
        "scope_month": scope_month,
        "invoice_id": text(payload.get("invoiceId") or invoice.get("id")),
        "invoice_identity_key": text(payload.get("invoiceIdentityKey")),
        "invoice_no": text(invoice.get("displayNo") or invoice.get("invoiceNo")),
        "invoice_date": invoice_date[:10] if invoice_date else None,
        "buyer_name": None,
        "buyer_tax_no": None,
        "seller_name": None,
        "seller_tax_no": None,
        "total_with_tax": decimal_text(invoice.get("totalWithTax")),
        "amount": None,
        "tax_amount": decimal_text(invoice.get("taxAmount")),
        "tax_rate": text(invoice.get("taxRate")),
        "specific_business_type": text(invoice.get("specificBusinessType")),
        "taxable_item_name": text(invoice.get("taxableItemName")),
        "payment_status": None,
        "payment_status_label": None,
        "collection_status": None,
        "collection_status_label": None,
        "collected_amount": None,
        "pending_amount": None,
        "oa_applicant": None,
        "oa_application_type": None,
        "oa_project_name": None,
        "bank_counterparty_name": None,
        "bank_trade_time": None,
        "bank_amount": None,
        "bank_name": None,
        "bank_account": None,
        "bank_direction": None,
        "bank_summary": None,
        "receipt_status": None,
        "receipt_status_label": None,
        "oa_relation_count": 0,
        "bank_relation_count": 0,
        "red_invoice_relation_count": 0,
        "searchable_text": json.dumps(payload, ensure_ascii=False, sort_keys=True)[:12000],
        "source_versions": jsonb(payload.get("sourceVersions") if isinstance(payload.get("sourceVersions"), dict) else {}),
        "generated_at": text(payload.get("generatedAt")),
        "cache_status": "fresh",
        "payload": jsonb(payload),
        "raw_payload": jsonb({"normalized_payload": payload}),
    }


def _pending_invoice_filter_clauses(filters: str | list[dict[str, Any]] | None) -> list[tuple[str, list[Any]]]:
    if filters in (None, ""):
        return []
    if isinstance(filters, str):
        parsed = json.loads(filters)
    else:
        parsed = filters
    if not isinstance(parsed, list):
        raise ValueError("pending invoice filters must be a list")
    clauses: list[tuple[str, list[Any]]] = []
    for item in parsed:
        if not isinstance(item, dict):
            raise ValueError("pending invoice filter must be an object")
        field = text(item.get("field")) or ""
        operator = text(item.get("operator")) or ""
        if field not in PENDING_INVOICE_FILTER_FIELDS or operator not in PENDING_INVOICE_FILTER_FIELDS[field]:
            raise ValueError(f"unsupported pending invoice filter: {field}/{operator}")
        expression = _pending_invoice_filter_expression(field)
        if operator == "contains":
            clauses.append((f"{expression} ilike %s", [f"%{text(item.get('value')) or ''}%"]))
        elif operator == "in":
            values = [str(value).strip() for value in list(item.get("values") or []) if str(value).strip()]
            if values:
                clauses.append((f"{expression} = any(%s)", [values]))
        elif operator == "between":
            bounds = item.get("value") if isinstance(item.get("value"), dict) else {}
            if field in {"amount", "invoice_total"}:
                minimum = decimal_text(bounds.get("min"))
                maximum = decimal_text(bounds.get("max"))
                if minimum is not None:
                    clauses.append((f"{expression} >= %s", [minimum]))
                if maximum is not None:
                    clauses.append((f"{expression} <= %s", [maximum]))
            else:
                start = text(bounds.get("from"))
                end = text(bounds.get("to"))
                if start:
                    clauses.append((f"{expression} >= %s::date", [start]))
                if end:
                    clauses.append((f"{expression} <= %s::date", [end]))
        elif operator == "eq":
            clauses.append((f"{expression} = %s", [decimal_text(item.get("value"))]))
    return clauses


def _pending_invoice_filter_expression(field: str) -> str:
    if field == "bank_name":
        return "coalesce(payload->'bank_transaction'->>'bank_name', '')"
    if field == "account_name":
        return "coalesce(payload->'bank_transaction'->>'account_name', '')"
    if field == "bank_account":
        return (
            "(trim(concat_ws(' ', "
            "nullif(coalesce(payload->'bank_transaction'->>'bank_short_name', payload->'bank_transaction'->>'bank_name', ''), ''), "
            "nullif(coalesce(payload->'bank_transaction'->>'account_last4', ''), '')"
            ")))"
        )
    if field == "transaction_tag":
        return (
            "(coalesce(payload->'bank_transaction'->>'effective_tag_label_path', '') || ' ' || "
            "coalesce(payload->'bank_transaction'->>'effective_tag_primary_label', '') || ' / ' || "
            "coalesce(payload->'bank_transaction'->>'effective_tag_sub_label', '') || ' ' || "
            "coalesce(payload->'bank_transaction'->>'effective_tag_label', ''))"
        )
    if field == "direction":
        return "direction"
    if field == "summary_remark":
        return "(coalesce(payload->'bank_transaction'->>'summary', '') || ' ' || coalesce(payload->'bank_transaction'->>'remark', ''))"
    if field == "rule_group":
        return "filter_group"
    if field == "oa_application_type":
        return "coalesce(payload->'oa'->'primary'->>'application_type', '')"
    return PENDING_INVOICE_SORT_EXPRESSIONS.get(field, field)


def _pending_invoice_option_expression(field: str) -> str:
    if field == "trade_date":
        return "coalesce(to_char(trade_date, 'YYYY-MM-DD'), left(coalesce(payload->'bank_transaction'->>'trade_time', ''), 10), '')"
    if field == "bank_name":
        return "coalesce(payload->'bank_transaction'->>'bank_name', '')"
    if field == "account_name":
        return "coalesce(payload->'bank_transaction'->>'account_name', '')"
    if field == "bank_account":
        return (
            "trim(concat_ws(' ', "
            "nullif(coalesce(payload->'bank_transaction'->>'bank_short_name', payload->'bank_transaction'->>'bank_name', ''), ''), "
            "nullif(coalesce(payload->'bank_transaction'->>'account_last4', ''), '')"
            "))"
        )
    if field == "counterparty_name":
        return "coalesce(counterparty_name, payload->'bank_transaction'->>'counterparty_name', '')"
    if field == "transaction_tag":
        return (
            "coalesce("
            "nullif((select string_agg(label, ' / ') from jsonb_array_elements_text("
            "case when jsonb_typeof(payload->'bank_transaction'->'effective_tag_label_path') = 'array' "
            "then payload->'bank_transaction'->'effective_tag_label_path' else '[]'::jsonb end"
            ") as labels(label)), ''), "
            "nullif(trim(concat_ws(' / ', "
            "nullif(coalesce(payload->'bank_transaction'->>'effective_tag_primary_label', ''), ''), "
            "nullif(coalesce(payload->'bank_transaction'->>'effective_tag_sub_label', ''), '')"
            ")), ''), "
            "nullif(coalesce(payload->'bank_transaction'->>'effective_tag_label', ''), ''), "
            "coalesce(payload->'bank_transaction'->>'effective_tag_code', '')"
            ")"
        )
    if field == "direction":
        return "direction"
    if field == "amount":
        return (
            "coalesce("
            "nullif(payload->'bank_transaction'->>'amount', ''), "
            "case when amount is null then '' else trim(to_char(amount, 'FM999999999999990.00')) end"
            ")"
        )
    if field == "summary_remark":
        return "(coalesce(payload->'bank_transaction'->>'summary', '') || ' ' || coalesce(payload->'bank_transaction'->>'remark', ''))"
    if field == "status_code":
        return "coalesce(status_code, payload->'invoice_acquisition_status'->>'code', '')"
    if field == "rule_group":
        return "coalesce(payload->'invoice_acquisition_status'->'matched_rule'->>'group', '')"
    if field == "seller_name":
        return "coalesce(seller_name, payload->'input_invoices'->'primary'->>'seller_name', '')"
    if field == "invoice_total":
        return (
            "coalesce("
            "nullif(payload->'input_invoices'->'payment_summary'->>'invoice_total', ''), "
            "case when invoice_total is null then '' else trim(to_char(invoice_total, 'FM999999999999990.00')) end"
            ")"
        )
    if field == "oa_applicant":
        return "coalesce(oa_applicant, payload->'oa'->'primary'->>'applicant', payload->>'oa_applicant', '')"
    if field == "oa_application_type":
        return "coalesce(payload->'oa'->'primary'->>'application_type', '')"
    if field == "project_name":
        return "coalesce(project_name, payload->'oa'->'primary'->>'project_name', '')"
    raise ValueError(f"unsupported pending invoice filter option field: {field}")


def _pending_invoice_visible_filter_clause(*, direction: str, filter_name: str) -> tuple[str, list[Any]]:
    normalized_filter = text(filter_name) or "all"
    normalized_direction = text(direction) or "expense"
    status_codes = pending_invoice_filter_status_codes(direction=normalized_direction, filter_name=normalized_filter)
    if not status_codes:
        return ("true", [])
    return ("status_code = any(%s)", [list(status_codes)])


def _pending_invoice_order_sql(*, sort_field: str | None, sort_direction: str | None) -> str:
    field = text(sort_field) or ""
    if not field:
        return "trade_date desc nulls last, row_id"
    if field not in PENDING_INVOICE_SORT_EXPRESSIONS:
        raise ValueError(f"unsupported pending invoice sort field: {field}")
    direction = (text(sort_direction) or "asc").lower()
    if direction not in {"asc", "desc"}:
        raise ValueError("pending invoice sort direction must be asc or desc")
    expression = PENDING_INVOICE_SORT_EXPRESSIONS[field]
    return f"{expression} {direction} nulls last, row_id"


def _parse_cost_statistics_scope_parts(scope_key: str, *, payload: dict[str, Any]) -> tuple[str, str]:
    raw = str(scope_key or "").strip()
    if ":" in raw:
        project_scope, month = raw.split(":", 1)
    else:
        project_scope = str(payload.get("project_scope") or "all")
        month = raw
    project_scope = (text(project_scope) or "all").lower()
    if project_scope not in {"active", "all"}:
        project_scope = "all"
    normalized_month = text(payload.get("month") or month) or "all"
    return project_scope, normalized_month


def _is_cost_statistics_parent_scope(scope_key: str, *, payload: dict[str, Any]) -> bool:
    _project_scope, month = _parse_cost_statistics_scope_parts(scope_key, payload=payload)
    return month == "all"


def _cost_statistics_payload_from_rows(
    *,
    scope_key: str,
    parent_payload: dict[str, Any],
    parent_row: dict[str, Any],
    rows: list[dict[str, Any]],
) -> dict[str, Any]:
    parent_model_payload = parent_payload.get("payload") if isinstance(parent_payload.get("payload"), dict) else parent_payload
    project_scope, scope_month_text = _parse_cost_statistics_scope_parts(scope_key, payload=parent_model_payload)
    if rows:
        scope_month_text = text(rows[0].get("scope_month")) or scope_month_text
    month = scope_month_text[:7] if scope_month_text and scope_month_text != "all" else text(parent_model_payload.get("month")) or scope_month_text
    time_rows: list[dict[str, Any]] = []
    project_groups: dict[str, dict[str, Any]] = {}
    expense_groups: dict[str, dict[str, Any]] = {}
    total_amount = Decimal("0")
    for index, db_row in enumerate(rows):
        payload = _read_model_payload(db_row)
        row_payload_value = deepcopy(payload) if isinstance(payload, dict) else {}
        amount = _decimal_or_zero(db_row.get("amount") or row_payload_value.get("amount"))
        total_amount += amount
        project_name = text(db_row.get("project_name") or row_payload_value.get("project_name")) or "未归集项目"
        expense_type = text(db_row.get("expense_type") or row_payload_value.get("expense_type")) or "未分类"
        transaction_id = text(db_row.get("transaction_id") or row_payload_value.get("transaction_id")) or f"row-{index}"
        normalized_row = {
            **row_payload_value,
            "transaction_id": transaction_id,
            "group_id": text(db_row.get("group_id") or row_payload_value.get("group_id")),
            "trade_time": text(db_row.get("trade_time_text") or row_payload_value.get("trade_time") or db_row.get("trade_date")),
            "direction": text(db_row.get("direction") or row_payload_value.get("direction")),
            "project_name": project_name,
            "project_id": text(db_row.get("project_id") or row_payload_value.get("project_id")),
            "expense_type": expense_type,
            "expense_content": text(db_row.get("expense_content") or row_payload_value.get("expense_content")),
            "amount": _format_decimal(amount),
            "counterparty_name": text(db_row.get("counterparty_name") or row_payload_value.get("counterparty_name")),
            "payment_account_label": text(db_row.get("payment_account_label") or row_payload_value.get("payment_account_label")),
            "remark": text(db_row.get("remark") or row_payload_value.get("remark")),
            "oa_applicant": text(db_row.get("oa_applicant") or row_payload_value.get("oa_applicant")),
        }
        time_rows.append(normalized_row)
        project_bucket = project_groups.setdefault(
            project_name,
            {"project_name": project_name, "total_amount": Decimal("0"), "transaction_count": 0, "expense_types": set()},
        )
        project_bucket["total_amount"] += amount
        project_bucket["transaction_count"] += 1
        project_bucket["expense_types"].add(expense_type)
        expense_bucket = expense_groups.setdefault(
            expense_type,
            {"expense_type": expense_type, "total_amount": Decimal("0"), "transaction_count": 0, "projects": set()},
        )
        expense_bucket["total_amount"] += amount
        expense_bucket["transaction_count"] += 1
        expense_bucket["projects"].add(project_name)
    return {
        "month": month,
        "project_scope": project_scope,
        "summary": {
            "row_count": len(time_rows),
            "transaction_count": len(time_rows),
            "total_amount": _format_decimal(total_amount),
        },
        "time_rows": time_rows,
        "project_rows": [
            {
                "project_name": bucket["project_name"],
                "total_amount": _format_decimal(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "expense_type_count": len(bucket["expense_types"]),
            }
            for bucket in sorted(project_groups.values(), key=lambda item: (-item["total_amount"], item["project_name"]))
        ],
        "expense_type_rows": [
            {
                "expense_type": bucket["expense_type"],
                "total_amount": _format_decimal(bucket["total_amount"]),
                "transaction_count": bucket["transaction_count"],
                "project_count": len(bucket["projects"]),
            }
            for bucket in sorted(expense_groups.values(), key=lambda item: (-item["total_amount"], item["expense_type"]))
        ],
        "generated_at": text(parent_row.get("generated_at") or parent_payload.get("generated_at")),
    }


def _tax_offset_payload_from_items(*, parent_payload: dict[str, Any], rows: list[dict[str, Any]]) -> dict[str, Any]:
    payload = deepcopy(parent_payload)
    for key in _TAX_OFFSET_ITEM_TYPES:
        payload[key] = []
    for row in rows:
        item_type = text(row.get("item_type"))
        payload_key = _TAX_OFFSET_PAYLOAD_KEYS.get(item_type or "")
        if payload_key is None:
            continue
        item_payload = _read_model_payload(row)
        if isinstance(item_payload, dict):
            payload[payload_key].append(item_payload)
    return payload


def _tax_offset_item_count(payload: dict[str, Any]) -> int:
    total = 0
    for key in _TAX_OFFSET_ITEM_TYPES:
        value = payload.get(key)
        if isinstance(value, list):
            total += len(value)
    return total


def _turnover_ledger_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    if isinstance(payload, dict):
        return payload
    return {
        "relation_id": text(row.get("relation_id")),
        "family": text(row.get("family")),
        "status": text(row.get("status")),
        "balance_amount": decimal_text(row.get("amount")) or "0.00",
    }


def _shared_source_versions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    versions: dict[str, Any] = {}
    for row in rows:
        row_versions = row.get("source_versions")
        if not isinstance(row_versions, dict):
            return {}
        if not versions:
            versions = dict(row_versions)
            continue
        if row_versions != versions:
            return {}
    return versions


def _turnover_ledger_summary(rows: list[dict[str, Any]]) -> dict[str, Any]:
    pending_repayment = Decimal("0")
    repaid = Decimal("0")
    pending_collection = Decimal("0")
    collected = Decimal("0")
    closed = Decimal("0")
    suggested_count = 0
    conflict_count = 0
    for row in rows:
        if any(
            row.get(key) is not None
            for key in (
                "pending_repayment_amount",
                "repaid_amount",
                "pending_collection_amount",
                "collected_amount",
                "closed_amount",
            )
        ):
            pending_repayment += _decimal_or_zero(row.get("pending_repayment_amount"))
            repaid += _decimal_or_zero(row.get("repaid_amount"))
            pending_collection += _decimal_or_zero(row.get("pending_collection_amount"))
            collected += _decimal_or_zero(row.get("collected_amount"))
            closed += _decimal_or_zero(row.get("closed_amount"))
            if row.get("status") == "suggested":
                suggested_count += 1
            if row.get("status") == "conflict":
                conflict_count += 1
            continue
        principal = _decimal_or_zero(row.get("principal_amount"))
        settled = _decimal_or_zero(row.get("settled_amount"))
        balance = _decimal_or_zero(row.get("balance_amount"))
        business_type = text(row.get("business_type")) or ""
        if business_type == "borrow_in":
            pending_repayment += max(balance, Decimal("0"))
            repaid += settled
        elif business_type in {"borrow_out", "business_receivable"}:
            pending_collection += max(balance, Decimal("0"))
            collected += settled
        if balance == Decimal("0") and row.get("status") in {"deterministic", "confirmed"}:
            closed += principal
        if row.get("status") == "suggested":
            suggested_count += 1
        if row.get("status") == "conflict":
            conflict_count += 1
    return {
        "pending_repayment_amount": _format_decimal(pending_repayment),
        "repaid_amount": _format_decimal(repaid),
        "pending_collection_amount": _format_decimal(pending_collection),
        "collected_amount": _format_decimal(collected),
        "closed_amount": _format_decimal(closed),
        "suggested_count": suggested_count,
        "conflict_count": conflict_count,
        "row_count": len(rows),
    }


def _turnover_ledger_family_summary(family: str, rows: list[dict[str, Any]]) -> dict[str, Any]:
    summary = _turnover_ledger_summary(rows)
    pending_amount = _decimal_or_zero(summary.get("pending_repayment_amount")) + _decimal_or_zero(
        summary.get("pending_collection_amount")
    )
    labels = {"personal": "个人往来", "company": "公司往来", "bank": "银行往来", "business": "业务往来"}
    return {
        "family": family,
        "label": labels.get(family, family),
        "pending_repayment_amount": summary["pending_repayment_amount"],
        "repaid_amount": summary["repaid_amount"],
        "pending_collection_amount": summary["pending_collection_amount"],
        "collected_amount": summary["collected_amount"],
        "pending_amount": _format_decimal(pending_amount),
        "closed_amount": summary["closed_amount"],
        "row_count": summary["row_count"],
    }


def _date_text(value: Any) -> str | None:
    normalized = text(value)
    if not normalized:
        return None
    if len(normalized) >= 10 and normalized[4] == "-" and normalized[7] == "-":
        return normalized[:10]
    return month_start(normalized)


def _decimal_or_zero(value: Any) -> Decimal:
    if value in (None, "", "—", "--"):
        return Decimal("0")
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return Decimal("0")


def _format_decimal(value: Decimal) -> str:
    normalized = value.quantize(Decimal("0.01"))
    return format(normalized, "f")


def _dedupe_workbench_payload_groups(payload: dict[str, Any]) -> None:
    for zone in ("paired", "open"):
        section = payload.get(zone)
        if not isinstance(section, dict):
            continue
        groups = section.get("groups")
        if not isinstance(groups, list):
            continue
        deduped: list[dict[str, Any]] = []
        seen_keys: set[tuple[str, str]] = set()
        seen_row_sets: set[tuple[str, tuple[tuple[str, str], ...]]] = set()
        for index, group in enumerate(groups):
            if not isinstance(group, dict):
                continue
            group_id = text(group.get("group_id") or group.get("id")) or f"{zone}:{index}"
            group_key = (zone, group_id)
            if group_key in seen_keys:
                continue
            row_identity = _workbench_group_row_identity(group)
            if row_identity:
                row_key = (zone, row_identity)
                if row_key in seen_row_sets:
                    continue
                seen_row_sets.add(row_key)
            seen_keys.add(group_key)
            deduped.append(group)
        section["groups"] = deduped


def _workbench_active_relation_claim_keys_for_groups(
    executor: Any,
    groups: list[dict[str, Any]],
) -> tuple[set[tuple[str, str]], set[tuple[str, str, str]], dict[tuple[str, str], set[str]]]:
    row_panes_by_id: dict[str, set[str]] = {}
    for group in list(groups or []):
        if not isinstance(group, dict):
            continue
        for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
            if row_role == "summary":
                continue
            row_id = _workbench_row_id(row)
            if row_id is None:
                continue
            row_panes_by_id.setdefault(row_id, set()).add(pane)
    if not row_panes_by_id:
        return set(), set(), {}
    rows = executor.fetch_all(
        """
        select case_id, row_ids
        from app.workbench_pair_relations
        where status = 'active'
          and row_ids && %s::text[]
        order by case_id
        """,
        (sorted(row_panes_by_id),),
    )

    paired_row_keys: set[tuple[str, str]] = set()
    canonical_relation_claims_by_row_key: dict[tuple[str, str], set[str]] = {}
    for relation in list(rows or []):
        case_id = text(relation.get("case_id"))
        for row_id in text_list(relation.get("row_ids")):
            for pane in row_panes_by_id.get(row_id, set()):
                row_key = (pane, row_id)
                paired_row_keys.add(row_key)
                if case_id:
                    canonical_relation_claims_by_row_key.setdefault(row_key, set()).add(case_id)
    return paired_row_keys, set(), canonical_relation_claims_by_row_key


def _aggregate_workbench_all_scope_payload(
    groups: list[dict[str, Any]],
    *,
    paired_row_keys: set[tuple[str, str]] | None = None,
    paired_identity_keys: set[tuple[str, str, str]] | None = None,
    canonical_relation_claims_by_row_key: dict[tuple[str, str], set[str]] | None = None,
) -> dict[str, Any]:
    aggregate = {
        "month": "all",
        "scope_key": "all",
        "read_model_scope_key": "all",
        "paired": {"groups": []},
        "open": {"groups": []},
        "workbench_read_model_schema_version": WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION,
    }
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        zone = text(group.get("zone") or group.get("status")) or "open"
        if zone not in {"paired", "open"}:
            zone = "open"
        source_group_id = text(group.get("group_id") or group.get("id"))
        if source_group_id is None:
            continue
        group_id = _all_scope_group_id(group, source_group_id)
        key = (zone, group_id)
        if key not in grouped:
            grouped[key] = _normalize_all_scope_group(group, zone=zone, group_id=group_id)
            continue
        _merge_all_scope_group(grouped[key], group)

    finalized_by_zone: dict[str, list[dict[str, Any]]] = {"paired": [], "open": []}
    for (zone, _group_id), group in grouped.items():
        _finalize_all_scope_group(group, zone=zone)
        finalized_by_zone[zone].append(group)
    _co_locate_all_scope_oa_attachment_invoices_with_parent_groups(finalized_by_zone)
    _suppress_all_scope_open_rows_claimed_by_paired(
        finalized_by_zone["paired"],
        finalized_by_zone["open"],
        extra_paired_row_keys=paired_row_keys,
        extra_paired_identity_keys=paired_identity_keys,
        canonical_relation_claims_by_row_key=canonical_relation_claims_by_row_key,
    )
    _suppress_all_scope_open_rows_claimed_by_other_open_groups(finalized_by_zone["open"])
    for zone in ("paired", "open"):
        aggregate[zone]["groups"] = [
            group
            for group in finalized_by_zone[zone]
            if _workbench_group_fact_row_counts(group)["rows"] > 0
        ]
        aggregate[zone]["groups"].sort(key=lambda item: text(item.get("group_id")) or "")
    aggregate["summary"] = _summarize_workbench_payload_groups(aggregate)
    return aggregate


def _co_locate_all_scope_oa_attachment_invoices_with_parent_groups(
    finalized_by_zone: dict[str, list[dict[str, Any]]],
) -> None:
    all_groups = [group for zone in ("paired", "open") for group in finalized_by_zone.get(zone, [])]
    parent_groups_by_oa_id: dict[str, dict[str, Any]] = {}
    for group in all_groups:
        for row in _as_workbench_row_list(group.get("oa_rows")):
            row_id = _workbench_row_id(row)
            if row_id:
                parent_groups_by_oa_id.setdefault(row_id, group)
    if not parent_groups_by_oa_id:
        return

    changed_groups: set[int] = set()
    for group in all_groups:
        invoice_rows = _as_workbench_row_list(group.get("invoice_rows"))
        if not invoice_rows:
            continue
        retained_rows: list[dict[str, Any]] = []
        for row in invoice_rows:
            parent_oa_id = _all_scope_oa_attachment_parent_oa_id(row)
            target_group = parent_groups_by_oa_id.get(parent_oa_id or "")
            if target_group is None or target_group is group:
                retained_rows.append(row)
                continue
            target_group["invoice_rows"] = _merge_workbench_rows(target_group.get("invoice_rows"), [row])
            _mark_all_scope_oa_attachment_source_group(target_group)
            changed_groups.add(id(target_group))
            changed_groups.add(id(group))
        if len(retained_rows) != len(invoice_rows):
            group["invoice_rows"] = retained_rows

    if not changed_groups:
        return
    for zone, groups in finalized_by_zone.items():
        for group in groups:
            if id(group) in changed_groups:
                _finalize_all_scope_group(group, zone=zone)


def _all_scope_oa_attachment_parent_oa_id(row: dict[str, Any]) -> str | None:
    if text(row.get("source_kind")) != "oa_attachment_invoice":
        return None
    candidates = [
        row.get("derived_from_oa_id"),
        row.get("source_oa_row_id"),
        row.get("source_expense_item_id"),
        row.get("source_id"),
    ]
    source_links = row.get("source_links")
    if isinstance(source_links, list):
        for source_link in source_links:
            if not isinstance(source_link, dict):
                continue
            if text(source_link.get("source_type")) != "oa_attachment_invoice":
                continue
            candidates.extend(
                [
                    source_link.get("derived_from_oa_id"),
                    source_link.get("source_oa_row_id"),
                    source_link.get("source_expense_item_id"),
                    source_link.get("source_id"),
                ]
            )
    for candidate in candidates:
        parent_oa_id = _normalize_all_scope_oa_attachment_parent_oa_id(candidate)
        if parent_oa_id:
            return parent_oa_id
    return None


def _normalize_all_scope_oa_attachment_parent_oa_id(value: Any) -> str | None:
    normalized = text(value)
    if normalized is None:
        return None
    return re.sub(r":item:.*$", "", normalized)


def _mark_all_scope_oa_attachment_source_group(group: dict[str, Any]) -> None:
    if text(group.get("zone") or group.get("status")) == "paired":
        return
    if text(group.get("group_type")) in {"manual_confirmed", "auto_closed", "open_exception", "processed_exception", "ignored", "legacy_exception"}:
        return
    group["group_type"] = "source_linked"
    group["match_confidence"] = "high"
    group["reason"] = "oa_attachment_source_relation"


def _suppress_all_scope_open_rows_claimed_by_paired(
    paired_groups: list[dict[str, Any]],
    open_groups: list[dict[str, Any]],
    *,
    extra_paired_row_keys: set[tuple[str, str]] | None = None,
    extra_paired_identity_keys: set[tuple[str, str, str]] | None = None,
    canonical_relation_claims_by_row_key: dict[tuple[str, str], set[str]] | None = None,
) -> None:
    paired_row_keys: set[tuple[str, str]] = set(extra_paired_row_keys or set())
    paired_identity_keys: set[tuple[str, str, str]] = set(extra_paired_identity_keys or set())
    relation_claims_by_row_key = {
        key: set(value)
        for key, value in (canonical_relation_claims_by_row_key or {}).items()
    }
    for group in paired_groups:
        for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
            if row_role == "summary":
                continue
            row_id = _workbench_row_id(row)
            if row_id is not None:
                paired_row_keys.add((pane, row_id))
            identity = _workbench_strong_object_identity(row, pane)
            if identity is not None:
                paired_identity_keys.add(identity)

    if not paired_row_keys and not paired_identity_keys:
        return

    for group in open_groups:
        before_row_count = _workbench_group_fact_row_counts(group)["rows"]
        _remove_workbench_rows_from_group(
            group,
            paired_row_keys=paired_row_keys,
            paired_identity_keys=paired_identity_keys,
            canonical_relation_claims_by_row_key=relation_claims_by_row_key,
        )
        _drop_partial_all_scope_automatic_decision_group(group, before_row_count=before_row_count)
        _finalize_all_scope_group(group, zone="open")


def _suppress_all_scope_open_rows_claimed_by_other_open_groups(open_groups: list[dict[str, Any]]) -> None:
    owner_by_claim_key: dict[tuple[str, ...], tuple[tuple[Any, ...], dict[str, Any]]] = {}
    for group in open_groups:
        rank = _all_scope_open_group_claim_rank(group)
        for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
            if row_role == "summary":
                continue
            for claim_key in _workbench_open_visible_owner_claim_keys(row, pane):
                owner = owner_by_claim_key.get(claim_key)
                if owner is None or rank < owner[0]:
                    owner_by_claim_key[claim_key] = (rank, group)

    if not owner_by_claim_key:
        return

    for group in open_groups:
        before_row_count = _workbench_group_fact_row_counts(group)["rows"]
        _remove_workbench_rows_from_group_claimed_by_other_open_group(
            group,
            owner_by_claim_key=owner_by_claim_key,
        )
        _drop_partial_all_scope_automatic_decision_group(group, before_row_count=before_row_count)
        _finalize_all_scope_group(group, zone="open")


def _drop_partial_all_scope_automatic_decision_group(group: dict[str, Any], *, before_row_count: int) -> None:
    after_row_count = _workbench_group_fact_row_counts(group)["rows"]
    if 0 < after_row_count < before_row_count and _is_all_scope_automatic_decision_group(group):
        _clear_workbench_group_rows(group)


def _is_all_scope_automatic_decision_group(group: dict[str, Any]) -> bool:
    group_id = text(group.get("group_id") or group.get("id")) or ""
    if group_id.startswith("case:decision:"):
        return True
    for row in _iter_group_rows(group):
        if text(row.get("relation_mode")) == "automatic_decision":
            return True
        case_id = text(row.get("case_id"))
        if case_id and case_id.startswith("decision:"):
            return True
    return False


def _clear_workbench_group_rows(group: dict[str, Any]) -> None:
    for row_key in ("oa_rows", "bank_rows", "invoice_rows"):
        group[row_key] = []
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for pane in list(collapsed_rows):
            collapsed_rows[pane] = []


def _all_scope_open_group_claim_rank(group: dict[str, Any]) -> tuple[Any, ...]:
    group_type = text(group.get("group_type")) or ""
    reason = text(group.get("reason")) or ""
    fact_counts = _workbench_group_fact_row_counts(group)
    pane_count = sum(1 for pane in WORKBENCH_PANES if fact_counts.get(pane, 0) > 0)
    row_count = fact_counts.get("rows", 0)
    has_reconciliation_decision = any(
        isinstance(row.get("workbench_reconciliation_decision"), dict) for row in _iter_group_rows(group)
    )
    if group_type == "source_linked":
        group_type_priority = 0
    elif group_type in {"auto_closed", "manual_confirmed", "open_exception", "ignored", "legacy_exception"}:
        group_type_priority = 1
    elif group_type == "open" and (reason == "reconciliation_decision_open" or has_reconciliation_decision):
        group_type_priority = 2
    elif group_type == "candidate":
        group_type_priority = 3
    elif group_type == "open":
        group_type_priority = 4
    else:
        group_type_priority = 5
    confidence_priority = {"high": 0, "medium": 1, "low": 2}.get(text(group.get("match_confidence")) or "", 3)
    stable_group_id = text(group.get("group_id") or group.get("id")) or ""
    return (group_type_priority, -pane_count, -row_count, confidence_priority, stable_group_id)


def _remove_workbench_rows_from_group_claimed_by_other_open_group(
    group: dict[str, Any],
    *,
    owner_by_claim_key: dict[tuple[str, ...], tuple[tuple[Any, ...], dict[str, Any]]],
) -> None:
    for pane, row_key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        rows = group.get(row_key)
        if isinstance(rows, list):
            group[row_key] = [
                row
                for row in rows
                if isinstance(row, dict)
                and _workbench_row_owned_by_group(
                    row,
                    pane,
                    group=group,
                    owner_by_claim_key=owner_by_claim_key,
                )
            ]
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for pane, rows in list(collapsed_rows.items()):
            if not isinstance(rows, list):
                continue
            collapsed_rows[pane] = [
                row
                for row in rows
                if isinstance(row, dict)
                and _workbench_row_owned_by_group(
                    row,
                    str(pane),
                    group=group,
                    owner_by_claim_key=owner_by_claim_key,
                )
            ]


def _workbench_row_owned_by_group(
    row: dict[str, Any],
    pane: str,
    *,
    group: dict[str, Any],
    owner_by_claim_key: dict[tuple[str, ...], tuple[tuple[Any, ...], dict[str, Any]]],
) -> bool:
    for claim_key in _workbench_open_visible_owner_claim_keys(row, pane):
        owner = owner_by_claim_key.get(claim_key)
        if owner is not None and owner[1] is not group:
            return False
    return True


def _remove_workbench_rows_from_group(
    group: dict[str, Any],
    *,
    paired_row_keys: set[tuple[str, str]],
    paired_identity_keys: set[tuple[str, str, str]],
    canonical_relation_claims_by_row_key: dict[tuple[str, str], set[str]] | None = None,
) -> None:
    group_relation_case_id = _workbench_canonical_relation_case_id_for_group(group)
    for pane, row_key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        rows = group.get(row_key)
        if isinstance(rows, list):
            group[row_key] = [
                row
                for row in rows
                if isinstance(row, dict)
                and not _workbench_row_claimed_by_paired(
                    row,
                    pane,
                    paired_row_keys=paired_row_keys,
                    paired_identity_keys=paired_identity_keys,
                    canonical_relation_claims_by_row_key=canonical_relation_claims_by_row_key,
                    group_relation_case_id=group_relation_case_id,
                )
            ]
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for pane, rows in list(collapsed_rows.items()):
            if not isinstance(rows, list):
                continue
            collapsed_rows[pane] = [
                row
                for row in rows
                if isinstance(row, dict)
                and not _workbench_row_claimed_by_paired(
                    row,
                    str(pane),
                    paired_row_keys=paired_row_keys,
                    paired_identity_keys=paired_identity_keys,
                    canonical_relation_claims_by_row_key=canonical_relation_claims_by_row_key,
                    group_relation_case_id=group_relation_case_id,
                )
            ]


def _workbench_row_claimed_by_paired(
    row: dict[str, Any],
    pane: str,
    *,
    paired_row_keys: set[tuple[str, str]],
    paired_identity_keys: set[tuple[str, str, str]],
    canonical_relation_claims_by_row_key: dict[tuple[str, str], set[str]] | None = None,
    group_relation_case_id: str | None = None,
) -> bool:
    row_id = _workbench_row_id(row)
    if row_id is not None and (pane, row_id) in paired_row_keys:
        claim_case_ids = (canonical_relation_claims_by_row_key or {}).get((pane, row_id), set())
        if group_relation_case_id and group_relation_case_id in claim_case_ids:
            return False
        return True
    identity = _workbench_strong_object_identity(row, pane)
    return identity is not None and identity in paired_identity_keys


def _workbench_canonical_relation_case_id_for_group(group: dict[str, Any]) -> str | None:
    group_id = text(group.get("group_id") or group.get("id")) or ""
    if group_id.startswith("case:"):
        return group_id.removeprefix("case:")
    return None


def _workbench_open_visible_owner_claim_keys(row: dict[str, Any], pane: str) -> list[tuple[str, ...]]:
    keys: list[tuple[str, ...]] = []
    row_id = _workbench_row_id(row)
    if row_id is not None:
        keys.append(("row", pane, row_id))
    identity = _workbench_strong_object_identity(row, pane)
    if pane == "invoice" and identity is not None:
        keys.append(("identity", *identity))
    return keys


def _workbench_strong_object_identity(row: dict[str, Any], pane: str) -> tuple[str, str, str] | None:
    identity_key = text(row.get("object_identity_key"))
    identity_kind = text(row.get("object_identity_kind"))
    if identity_key is None or identity_kind is None:
        return None
    if pane == "invoice" and identity_kind in {"digital_invoice_no", "invoice_code_no"}:
        return (pane, identity_kind, identity_key)
    if pane == "bank" and identity_kind == "business_fields":
        return (pane, identity_kind, identity_key)
    return None


def _normalize_all_scope_group(group: dict[str, Any], *, zone: str, group_id: str) -> dict[str, Any]:
    normalized = deepcopy(group)
    normalized["group_id"] = group_id
    normalized["id"] = group_id
    normalized["zone"] = zone
    normalized["status"] = zone
    normalized["scope_key"] = "all"
    normalized["month"] = "all"
    normalized["scope_month"] = None
    normalized.pop("_source_scope_key", None)
    normalized.pop("_source_scope_month", None)
    normalized.pop("collapsed_row_counts", None)
    normalized.pop("display_row_counts", None)
    for key in ("oa_rows", "bank_rows", "invoice_rows"):
        normalized[key] = _dedupe_workbench_rows(normalized.get(key))
    collapsed_rows = normalized.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        normalized["collapsed_rows"] = {
            str(row_type): _dedupe_workbench_rows(rows)
            for row_type, rows in collapsed_rows.items()
            if isinstance(rows, list)
        }
    return _with_workbench_group_counts(normalized)


def _all_scope_group_id(group: dict[str, Any], group_id: str) -> str:
    if _is_all_scope_mergeable_group_id(group_id):
        return group_id
    source_scope_key = text(group.get("_source_scope_key") or group.get("source_scope_key"))
    if source_scope_key and source_scope_key != "all":
        return f"scope:{source_scope_key}:{group_id}"
    source_scope_month = text(group.get("_source_scope_month") or group.get("source_scope_month"))
    if source_scope_month:
        return f"scope-month:{source_scope_month}:{group_id}"
    return group_id


def _is_all_scope_mergeable_group_id(group_id: str) -> bool:
    return group_id.startswith(("case:", "turnover:", "batch-accounting:", "source:oa_attachment:"))


def _expected_workbench_groups_builder(scope_key: str) -> str | None:
    return WORKBENCH_ALL_SCOPE_AGGREGATE_SCHEMA_VERSION if scope_key == "all" else None


def _merge_all_scope_group(target: dict[str, Any], incoming: dict[str, Any]) -> None:
    for key in ("oa_rows", "bank_rows", "invoice_rows"):
        target[key] = _merge_workbench_rows(target.get(key), incoming.get(key))
    incoming_collapsed = incoming.get("collapsed_rows")
    if isinstance(incoming_collapsed, dict):
        target_collapsed = target.get("collapsed_rows")
        if not isinstance(target_collapsed, dict):
            target_collapsed = {}
            target["collapsed_rows"] = target_collapsed
        for row_type, rows in incoming_collapsed.items():
            existing_rows = target_collapsed.get(str(row_type))
            target_collapsed[str(row_type)] = _merge_workbench_rows(existing_rows, rows)
    target["source_kinds"] = sorted(
        {
            source_kind
            for row in _iter_group_rows(target)
            if (source_kind := text(row.get("source_kind") or row.get("type"))) is not None
        }
    )
    target["searchable_text"] = _searchable_group_text(target)


def _finalize_all_scope_group(group: dict[str, Any], *, zone: str) -> None:
    group.pop("collapsed_row_counts", None)
    group.pop("display_row_counts", None)
    group["zone"] = zone
    group["status"] = zone
    group["scope_key"] = "all"
    group["month"] = "all"
    group["scope_month"] = None
    group.update(_with_workbench_group_counts(group))
    group["source_kinds"] = sorted(
        {
            source_kind
            for row in _iter_group_rows(group)
            if (source_kind := text(row.get("source_kind") or row.get("type"))) is not None
        }
    )
    group["searchable_text"] = _searchable_group_text(group)
    group.update(_workbench_group_sort_keys(group))


def _merge_workbench_rows(left: Any, right: Any) -> list[dict[str, Any]]:
    return _dedupe_workbench_rows([*_as_workbench_row_list(left), *_as_workbench_row_list(right)])


def _dedupe_workbench_rows(rows: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for row in _as_workbench_row_list(rows):
        row_id = text(row.get("id") or row.get("row_id"))
        if row_id is None:
            continue
        row_type = text(row.get("type") or row.get("record_type") or row.get("source_kind")) or ""
        key = (row_type, row_id)
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _as_workbench_row_list(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []
    return [deepcopy(row) for row in rows if isinstance(row, dict)]


def _workbench_row_id(row: dict[str, Any]) -> str | None:
    return text(row.get("id") or row.get("row_id"))


def _is_workbench_summary_display_row(row: dict[str, Any], pane: str) -> bool:
    return pane == "bank" and (
        text(row.get("row_role")) == "summary"
        or text(row.get("source_kind")) == NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND
    )


def _empty_workbench_row_counts() -> dict[str, int]:
    return {"oa": 0, "bank": 0, "invoice": 0, "rows": 0}


def _workbench_group_fact_row_counts(group: dict[str, Any]) -> dict[str, int]:
    counts = _empty_workbench_row_counts()
    seen: set[tuple[str, str]] = set()
    for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        if pane not in WORKBENCH_PANES or row_role == "summary":
            continue
        row_id = _workbench_row_id(row)
        if row_id is None:
            continue
        row_key = (pane, row_id)
        if row_key in seen:
            continue
        seen.add(row_key)
        counts[pane] += 1
        counts["rows"] += 1
    return counts


def _workbench_panes_with_summary_display_rows(group: dict[str, Any]) -> set[str]:
    panes: set[str] = set()
    for pane, row_role, _row_index, _row in _iter_typed_group_rows_with_metadata(group):
        if row_role == "summary":
            panes.add(pane)
    return panes


def _workbench_group_display_row_counts(group: dict[str, Any]) -> dict[str, int]:
    counts = _empty_workbench_row_counts()
    for pane, row_key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        rows = group.get(row_key)
        if isinstance(rows, list):
            counts[pane] = sum(1 for row in rows if isinstance(row, dict))
            counts["rows"] += counts[pane]
    return counts


def _normalize_workbench_row_counts(value: Any, fallback: dict[str, int]) -> dict[str, int]:
    source = value if isinstance(value, dict) else {}
    counts = {
        "oa": int_value(source.get("oa"), fallback.get("oa", 0)),
        "bank": int_value(source.get("bank"), fallback.get("bank", 0)),
        "invoice": int_value(source.get("invoice"), fallback.get("invoice", 0)),
        "rows": 0,
    }
    counts["rows"] = int_value(source.get("rows"), counts["oa"] + counts["bank"] + counts["invoice"])
    return counts


def _with_workbench_group_counts(group: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(group)
    normalized["row_counts"] = _workbench_group_fact_row_counts(normalized)
    normalized["display_row_counts"] = _workbench_group_display_row_counts(normalized)
    normalized["row_count"] = normalized["row_counts"]["rows"]
    return normalized


def _empty_workbench_zone_counts() -> dict[str, dict[str, int]]:
    return {
        "paired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
        "open": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
    }


def _normalize_workbench_summary_counts(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    zone_counts = normalized.get("zone_counts")
    if not isinstance(zone_counts, dict):
        zone_counts = _empty_workbench_zone_counts()
        zone_counts["paired"]["groups"] = int_value(normalized.get("paired_count"), 0)
        zone_counts["open"]["groups"] = int_value(normalized.get("open_count"), 0)
    else:
        merged = _empty_workbench_zone_counts()
        for zone in ("paired", "open"):
            zone_payload = zone_counts.get(zone)
            if not isinstance(zone_payload, dict):
                continue
            merged[zone]["groups"] = int_value(zone_payload.get("groups"), 0)
            merged[zone]["oa"] = int_value(zone_payload.get("oa"), 0)
            merged[zone]["bank"] = int_value(zone_payload.get("bank"), 0)
            merged[zone]["invoice"] = int_value(zone_payload.get("invoice"), 0)
            merged[zone]["rows"] = int_value(
                zone_payload.get("rows"),
                merged[zone]["oa"] + merged[zone]["bank"] + merged[zone]["invoice"],
            )
        zone_counts = merged
    normalized["zone_counts"] = zone_counts
    return normalized


def _workbench_group_page_row_counts(row: dict[str, Any] | None) -> dict[str, int]:
    oa_count = int_value((row or {}).get("oa_count"), 0)
    bank_count = int_value((row or {}).get("bank_count"), 0)
    invoice_count = int_value((row or {}).get("invoice_count"), 0)
    return {"oa": oa_count, "bank": bank_count, "invoice": invoice_count, "rows": oa_count + bank_count + invoice_count}


def _normalize_workbench_column_filters(value: Any) -> dict[str, dict[str, list[str]]]:
    payload = _json_object_payload(value)
    result: dict[str, dict[str, list[str]]] = {}
    total_values = 0
    for pane in WORKBENCH_PANES:
        pane_payload = payload.get(pane)
        if not isinstance(pane_payload, dict):
            continue
        pane_filters: dict[str, list[str]] = {}
        for column_key, raw_values in pane_payload.items():
            normalized_column = text(column_key)
            if normalized_column is None or normalized_column not in WORKBENCH_ALLOWED_FILTER_COLUMNS[pane]:
                continue
            values = raw_values if isinstance(raw_values, list) else [raw_values]
            cleaned = sorted(
                {
                    value
                    for item in values
                    if (value := text(item)) is not None
                    if value not in WORKBENCH_FILTER_PLACEHOLDERS
                }
            )
            if not cleaned:
                continue
            pane_filters[normalized_column] = cleaned[:20]
            total_values += len(pane_filters[normalized_column])
            if total_values >= 80:
                break
        if pane_filters:
            result[pane] = pane_filters
        if total_values >= 80:
            break
    return result


def _normalize_workbench_time_filters(value: Any) -> dict[str, dict[str, str]]:
    payload = _json_object_payload(value)
    result: dict[str, dict[str, str]] = {}
    for pane in WORKBENCH_PANES:
        pane_payload = payload.get(pane)
        if not isinstance(pane_payload, dict):
            continue
        mode = text(pane_payload.get("mode"))
        if mode == "year":
            year = text(pane_payload.get("year"))
            if year and re.match(r"^\d{4}$", year):
                result[pane] = {"mode": "year", "year": year}
        elif mode == "month":
            month = text(pane_payload.get("month"))
            if month and re.match(r"^\d{4}-\d{2}$", month):
                result[pane] = {"mode": "month", "month": month}
    return result


def _normalize_workbench_search_by_pane(value: Any) -> dict[str, str]:
    payload = _json_object_payload(value)
    result: dict[str, str] = {}
    for pane in WORKBENCH_PANES:
        normalized = text(payload.get(pane))
        if normalized:
            result[pane] = normalized[:200]
    return result


def _normalize_workbench_search_mode(value: Any) -> str:
    normalized = text(value)
    return "linked_context" if normalized == "linked_context" else "pane"


def _workbench_linked_search_exists_sql() -> str:
    return (
        "exists (select 1 from read_model.workbench_group_rows r_linked_search "
        "where r_linked_search.scope_key = g.scope_key "
        "and r_linked_search.generation_id = g.generation_id "
        "and r_linked_search.zone = g.zone "
        "and r_linked_search.group_id = g.group_id "
        "and r_linked_search.searchable_text ilike %s)"
    )


def _json_object_payload(value: Any) -> dict[str, Any]:
    if isinstance(value, dict):
        return value
    if isinstance(value, str) and value.strip():
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError:
            return {}
        return parsed if isinstance(parsed, dict) else {}
    return {}


def _workbench_group_row_filter_exists_sql(
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    search_by_pane: dict[str, str],
    fallback_search: str | None,
) -> tuple[str, list[Any]]:
    pane_exists: list[str] = []
    params: list[Any] = []
    for pane in WORKBENCH_PANES:
        row_match_clauses, row_match_params = _workbench_group_row_match_sql(
            pane,
            column_filters=column_filters,
            time_filters=time_filters,
            search_by_pane=search_by_pane,
            fallback_search=fallback_search,
            include_pane=True,
        )
        if not row_match_clauses:
            continue
        row_clauses = [
            "r.scope_key = g.scope_key",
            "r.generation_id = g.generation_id",
            "r.zone = g.zone",
            "r.group_id = g.group_id",
            *row_match_clauses,
        ]
        pane_exists.append(
            "exists (select 1 from read_model.workbench_group_rows r where " + " and ".join(row_clauses) + ")"
        )
        params.extend(row_match_params)
    if not pane_exists:
        return "", []
    return "(" + " and ".join(pane_exists) + ")", params


def _workbench_group_row_count_filter_sql(
    pane: str,
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    search_by_pane: dict[str, str],
    fallback_search: str | None,
) -> tuple[str, list[Any]]:
    row_clauses, params = _workbench_group_row_match_sql(
        pane,
        column_filters=column_filters,
        time_filters=time_filters,
        search_by_pane=search_by_pane,
        fallback_search=fallback_search,
        include_pane=False,
    )
    if not row_clauses:
        return "", []
    return "and " + " and ".join(row_clauses), params


def _workbench_group_row_match_sql(
    pane: str,
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    search_by_pane: dict[str, str],
    fallback_search: str | None,
    include_pane: bool,
) -> tuple[list[str], list[Any]]:
    pane_column_filters = column_filters.get(pane, {})
    pane_time_filter = time_filters.get(pane)
    pane_search = search_by_pane.get(pane)
    if not pane_search and fallback_search and (pane_column_filters or pane_time_filter):
        pane_search = fallback_search
    if not pane_column_filters and not pane_time_filter and not pane_search:
        return [], []

    row_clauses: list[str] = []
    row_params: list[Any] = []
    if include_pane:
        row_clauses.append("r.pane = %s")
        row_params.append(pane)
    for column_key in sorted(pane_column_filters):
        values = pane_column_filters[column_key]
        value_match_clauses: list[str] = []
        if pane == "bank" and column_key == "amount":
            for value in values:
                value_clauses = []
                value_clauses.append("r.column_values @> %s::jsonb")
                row_params.append(json.dumps({"direction": value}, ensure_ascii=False))
                value_clauses.append("r.column_values @> %s::jsonb")
                row_params.append(json.dumps({"paymentAccount": value}, ensure_ascii=False))
                value_match_clauses.append("(" + " or ".join(value_clauses) + ")")
        else:
            for value in values:
                value_match_clauses.append("r.column_values @> %s::jsonb")
                row_params.append(json.dumps({column_key: value}, ensure_ascii=False))
        if value_match_clauses:
            row_clauses.append("(" + " and ".join(value_match_clauses) + ")")
    if pane_time_filter:
        start_date, end_date = _workbench_time_filter_date_range(pane_time_filter)
        if start_date and end_date:
            row_clauses.append("r.time_date >= %s::date and r.time_date < %s::date")
            row_params.extend([start_date, end_date])
    if pane_search:
        row_clauses.append("r.searchable_text ilike %s")
        row_params.append(f"%{pane_search}%")
    return row_clauses, row_params


def _workbench_time_filter_date_range(time_filter: dict[str, str]) -> tuple[str | None, str | None]:
    if time_filter.get("mode") == "year":
        year = time_filter.get("year") or ""
        if not re.match(r"^\d{4}$", year):
            return None, None
        return f"{year}-01-01", f"{int(year) + 1:04d}-01-01"
    if time_filter.get("mode") == "month":
        month = time_filter.get("month") or ""
        if not re.match(r"^\d{4}-\d{2}$", month):
            return None, None
        year_number = int(month[:4])
        month_number = int(month[5:7])
        if month_number == 12:
            return f"{year_number:04d}-12-01", f"{year_number + 1:04d}-01-01"
        return f"{year_number:04d}-{month_number:02d}-01", f"{year_number:04d}-{month_number + 1:02d}-01"
    return None, None


def _summarize_workbench_payload_groups(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "oa_count": 0,
        "bank_count": 0,
        "invoice_count": 0,
        "paired_count": 0,
        "open_count": 0,
        "exception_count": 0,
        "zone_counts": _empty_workbench_zone_counts(),
    }
    seen_rows: set[tuple[str, str]] = set()
    seen_rows_by_zone: dict[str, set[tuple[str, str]]] = {"paired": set(), "open": set()}
    for zone in ("paired", "open"):
        section = payload.get(zone)
        groups = section.get("groups") if isinstance(section, dict) else []
        if not isinstance(groups, list):
            continue
        group_count = sum(1 for group in groups if isinstance(group, dict))
        summary[f"{zone}_count"] = group_count
        summary["zone_counts"][zone]["groups"] = group_count
        for group in groups:
            if not isinstance(group, dict):
                continue
            if zone == "open" and _workbench_group_has_danger(group):
                summary["exception_count"] += 1
            for pane, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
                if row_role == "summary":
                    continue
                row_type = text(row.get("type") or row.get("record_type")) or pane
                row_id = _workbench_row_id(row)
                if row_type is None or row_id is None:
                    continue
                row_key = (row_type, row_id)
                if row_key not in seen_rows_by_zone[zone]:
                    seen_rows_by_zone[zone].add(row_key)
                    if row_type in {"oa", "bank", "invoice"}:
                        summary["zone_counts"][zone][row_type] += 1
                        summary["zone_counts"][zone]["rows"] += 1
                if row_key in seen_rows:
                    continue
                seen_rows.add(row_key)
                if row_type == "oa":
                    summary["oa_count"] += 1
                elif row_type == "bank":
                    summary["bank_count"] += 1
                elif row_type == "invoice":
                    summary["invoice_count"] += 1
    return summary


def _workbench_group_has_danger(group: dict[str, Any]) -> bool:
    if text(group.get("match_confidence")) == "danger":
        return True
    for row in _iter_group_rows(group):
        relation_codes = [
            row.get("oa_bank_relation"),
            row.get("invoice_relation"),
            row.get("invoice_bank_relation"),
        ]
        for relation in relation_codes:
            if isinstance(relation, dict) and text(relation.get("tone")) == "danger":
                return True
    return False


def _workbench_groups_order_by(sort: str | None) -> str:
    normalized = (text(sort) or "").lower()
    allowed = {
        "oa:asc": "oa_sort_min asc nulls last",
        "oa:desc": "oa_sort_max desc nulls last",
        "bank:asc": "bank_sort_min asc nulls last",
        "bank:desc": "bank_sort_max desc nulls last",
        "invoice:asc": "invoice_sort_min asc nulls last",
        "invoice:desc": "invoice_sort_max desc nulls last",
    }
    prefix = allowed.get(normalized)
    if prefix is None:
        return "scope_month desc nulls last, updated_at desc, group_id"
    return f"{prefix}, scope_month desc nulls last, updated_at desc, group_id"


def _workbench_open_linked_etc_summary_group_exclusion_sql() -> str:
    return """
    not exists (
        select 1
        from read_model.workbench_group_rows gr
        join app.workbench_pair_relations rel
          on rel.status = 'active'
         and nullif(rel.amount_check->>'external_etc_batch_id', '') is not null
         and gr.row_id = concat('etc-summary-', rel.amount_check->>'external_etc_batch_id')
        where gr.scope_key = g.scope_key
          and gr.generation_id = g.generation_id
          and gr.zone = g.zone
          and gr.group_id = g.group_id
          and gr.pane = 'invoice'
          and coalesce(gr.row_role, '') <> 'summary'
          and gr.source_kind = 'etc_invoice_summary'
    )
    """


def _normalize_workbench_group_detail_level(detail_level: str | None) -> str:
    normalized = (text(detail_level) or "full").lower()
    if normalized == "summary":
        return "summary"
    return "full"


WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT = 3
OA_ATTACHMENT_NON_INVOICE_EVIDENCE_SOURCE_KINDS = {
    "oa_attachment_payment_receipt",
    "oa_attachment_unknown",
}


def _is_non_invoice_oa_attachment_evidence_summary_row(row: dict[str, Any]) -> bool:
    return (text(row.get("source_kind") or row.get("sourceKind")) or "") in OA_ATTACHMENT_NON_INVOICE_EVIDENCE_SOURCE_KINDS


def _sanitize_workbench_group_invoice_rows(group: dict[str, Any]) -> dict[str, Any]:
    rows = group.get("invoice_rows")
    if not isinstance(rows, list):
        return group
    sanitized_rows = [
        row
        for row in rows
        if not (isinstance(row, dict) and _is_non_invoice_oa_attachment_evidence_summary_row(row))
    ]
    if len(sanitized_rows) == len(rows):
        return group
    sanitized = dict(group)
    sanitized["invoice_rows"] = sanitized_rows
    return sanitized


def _is_oa_attachment_invoice_summary_row(row: dict[str, Any]) -> bool:
    return (text(row.get("source_kind") or row.get("sourceKind")) or "") == "oa_attachment_invoice"


def _workbench_group_summary_preview_rows(row_key: str, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if row_key == "oa_rows":
        return list(rows)

    preview_rows = list(rows[:WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT])
    if row_key != "invoice_rows":
        return preview_rows

    preview_ids = {
        row_id
        for row in preview_rows
        if isinstance(row, dict)
        if (row_id := text(row.get("id") or row.get("row_id") or row.get("rowId")))
    }
    for row in rows[WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT:]:
        if not isinstance(row, dict) or not _is_oa_attachment_invoice_summary_row(row):
            continue
        row_id = text(row.get("id") or row.get("row_id") or row.get("rowId"))
        if row_id and row_id in preview_ids:
            continue
        preview_rows.append(row)
        if row_id:
            preview_ids.add(row_id)
    return preview_rows


def _filter_workbench_group_preview_rows_for_criteria(
    group: dict[str, Any],
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    search_by_pane: dict[str, str],
    fallback_search: str | None,
) -> dict[str, Any]:
    panes_to_filter = [
        pane
        for pane in WORKBENCH_PANES
        if column_filters.get(pane) or time_filters.get(pane) or search_by_pane.get(pane)
    ]
    if not panes_to_filter:
        return group

    filtered = dict(group)
    existing_row_counts = group.get("row_counts")
    row_counts = dict(existing_row_counts) if isinstance(existing_row_counts, dict) else {}
    for pane in WORKBENCH_PANES:
        row_key = f"{pane}_rows"
        rows = group.get(row_key)
        if isinstance(rows, list):
            row_counts.setdefault(pane, len(rows))

    collapsed_rows = group.get("collapsed_rows")
    collapsed_row_counts = dict(group.get("collapsed_row_counts")) if isinstance(group.get("collapsed_row_counts"), dict) else {}
    if isinstance(collapsed_rows, dict):
        for pane in WORKBENCH_PANES:
            rows = collapsed_rows.get(pane)
            if isinstance(rows, list):
                collapsed_row_counts.setdefault(pane, len(rows))

    for pane in panes_to_filter:
        row_key = f"{pane}_rows"
        rows = group.get(row_key)
        if isinstance(rows, list):
            filtered[row_key] = [
                row
                for row in rows
                if isinstance(row, dict)
                and _workbench_payload_row_matches_preview_criteria(
                    row,
                    pane,
                    column_filters=column_filters,
                    time_filters=time_filters,
                    search_by_pane=search_by_pane,
                    fallback_search=fallback_search,
                )
            ]
        if isinstance(collapsed_rows, dict):
            collapsed_pane_rows = collapsed_rows.get(pane)
            if isinstance(collapsed_pane_rows, list):
                next_collapsed_rows = dict(filtered.get("collapsed_rows")) if isinstance(filtered.get("collapsed_rows"), dict) else dict(collapsed_rows)
                next_collapsed_rows[pane] = [
                    row
                    for row in collapsed_pane_rows
                    if isinstance(row, dict)
                    and _workbench_payload_row_matches_preview_criteria(
                        row,
                        pane,
                        column_filters=column_filters,
                        time_filters=time_filters,
                        search_by_pane=search_by_pane,
                        fallback_search=fallback_search,
                    )
                ]
                filtered["collapsed_rows"] = next_collapsed_rows

    if row_counts:
        filtered["row_counts"] = row_counts
    if collapsed_row_counts:
        filtered["collapsed_row_counts"] = collapsed_row_counts
    return filtered


def _workbench_payload_row_matches_preview_criteria(
    row: dict[str, Any],
    pane: str,
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    search_by_pane: dict[str, str],
    fallback_search: str | None,
) -> bool:
    pane_column_filters = column_filters.get(pane, {})
    column_values = _workbench_row_column_values(row, pane)
    for column_key in sorted(pane_column_filters):
        selected_values = pane_column_filters[column_key]
        if not selected_values:
            continue
        if pane == "bank" and column_key == "amount":
            row_values = [
                column_values.get("direction"),
                column_values.get("paymentAccount"),
            ]
            if not all(value in row_values for value in selected_values):
                return False
        else:
            current_value = column_values.get(column_key)
            if not all(value == current_value for value in selected_values):
                return False

    pane_time_filter = time_filters.get(pane)
    if pane_time_filter:
        start_date, end_date = _workbench_time_filter_date_range(pane_time_filter)
        row_date = _workbench_date_from_text(_workbench_row_sort_value(row, pane))
        if start_date and end_date and (not row_date or row_date < start_date or row_date >= end_date):
            return False

    pane_search = search_by_pane.get(pane)
    if not pane_search and fallback_search and (pane_column_filters or pane_time_filter):
        pane_search = fallback_search
    if pane_search and pane_search.lower() not in _searchable_row_text(row, pane).lower():
        return False

    return True


def _compact_workbench_group_for_summary_page(group: dict[str, Any]) -> dict[str, Any]:
    compact = without_keys(dict(group), {"raw_payload", "payload"})
    normalized_counts = _with_workbench_group_counts(group)
    compact["row_counts"] = _normalize_workbench_row_counts(group.get("row_counts"), normalized_counts["row_counts"])
    compact["display_row_counts"] = _normalize_workbench_row_counts(
        group.get("display_row_counts"),
        normalized_counts["display_row_counts"],
    )
    for row_key in ("oa_rows", "bank_rows", "invoice_rows"):
        rows = group.get(row_key)
        compact[row_key] = [
            _compact_workbench_row_for_summary_page(row)
            for row in _workbench_group_summary_preview_rows(row_key, rows)
            if isinstance(row, dict)
        ] if isinstance(rows, list) else []
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        existing_collapsed_row_counts = (
            group.get("collapsed_row_counts")
            if isinstance(group.get("collapsed_row_counts"), dict)
            else {}
        )
        compact["collapsed_row_counts"] = {
            str(row_type): int_value(existing_collapsed_row_counts.get(str(row_type)), len(rows))
            for row_type, rows in collapsed_rows.items()
            if isinstance(rows, list)
        }
        compact["collapsed_rows"] = {
            str(row_type): [
                _compact_workbench_row_for_summary_page(row)
                for row in rows[:WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT]
                if isinstance(row, dict)
            ]
            for row_type, rows in collapsed_rows.items()
            if isinstance(rows, list)
        }
    return compact


def _compact_workbench_row_for_summary_page(row: dict[str, Any]) -> dict[str, Any]:
    compact_source = _normalize_workbench_invoice_display_fields(row)
    return without_keys(
        compact_source,
        {
            "detail_fields",
            "raw_payload",
            "payload",
            "original_payload",
            "source_payload",
            "artifacts",
            "evidences",
            "ocr_text",
            "full_text",
        },
    )


def _normalize_workbench_invoice_display_fields(row: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(row)
    if text(normalized.get("type")) != "invoice":
        return normalized
    detail_fields = normalized.get("detail_fields")
    detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
    summary_fields = normalized.get("summary_fields")
    summary_fields = summary_fields if isinstance(summary_fields, dict) else {}

    _set_workbench_display_value(
        normalized,
        "invoice_code",
        detail_fields.get("发票代码"),
        summary_fields.get("发票代码"),
    )
    _set_workbench_display_value(
        normalized,
        "invoice_no",
        normalized.get("digital_invoice_no"),
        detail_fields.get("发票号码"),
        detail_fields.get("数电发票号码"),
        summary_fields.get("发票号码"),
        summary_fields.get("数电发票号码"),
    )
    _set_workbench_display_value(
        normalized,
        "digital_invoice_no",
        detail_fields.get("数电发票号码"),
        summary_fields.get("数电发票号码"),
    )
    _set_workbench_display_value(
        normalized,
        "tax_rate",
        summary_fields.get("税率"),
        detail_fields.get("税率"),
        detail_fields.get("tax_rate"),
    )
    _set_workbench_display_value(
        normalized,
        "tax_amount",
        summary_fields.get("税额"),
        detail_fields.get("税额"),
        detail_fields.get("tax_amount"),
    )
    return normalized


def _set_workbench_display_value(row: dict[str, Any], key: str, *fallback_values: Any) -> None:
    current = text(row.get(key))
    if current and current not in WORKBENCH_FILTER_PLACEHOLDERS:
        return
    row[key] = _first_workbench_display_value(*fallback_values)


def _first_workbench_display_value(*values: Any) -> str:
    for value in values:
        normalized = text(value)
        if normalized and normalized not in WORKBENCH_FILTER_PLACEHOLDERS:
            return normalized
    return "—"


def _workbench_group_sort_keys(group: dict[str, Any]) -> dict[str, str | None]:
    result: dict[str, str | None] = {}
    for pane_id in ("oa", "bank", "invoice"):
        values = sorted(
            value
            for row_type, row in _iter_typed_group_rows(group)
            if row_type == pane_id
            if (value := _workbench_row_sort_value(row, pane_id)) is not None
        )
        result[f"{pane_id}_sort_min"] = values[0] if values else None
        result[f"{pane_id}_sort_max"] = values[-1] if values else None
    return result


def _workbench_row_sort_value(row: dict[str, Any], pane_id: str) -> str | None:
    table_values = row.get("table_values")
    if not isinstance(table_values, dict):
        table_values = row.get("tableValues")
    if not isinstance(table_values, dict):
        table_values = {}
    if pane_id == "oa":
        return text(
            table_values.get("applicationTime")
            or table_values.get("application_time")
            or row.get("application_time")
            or row.get("applicationTime")
            or row.get("date")
        )
    if pane_id == "bank":
        return text(
            table_values.get("transactionTime")
            or table_values.get("transaction_time")
            or row.get("transaction_time")
            or row.get("transactionTime")
            or row.get("trade_time")
            or row.get("tradeTime")
        )
    if pane_id == "invoice":
        return text(
            table_values.get("issueDate")
            or table_values.get("issue_date")
            or row.get("issue_date")
            or row.get("issueDate")
            or row.get("invoice_date")
            or row.get("invoiceDate")
        )
    return None


def _workbench_row_column_values(row: dict[str, Any], pane_id: str) -> dict[str, str]:
    table_values = row.get("table_values")
    if not isinstance(table_values, dict):
        table_values = row.get("tableValues")
    table_values = table_values if isinstance(table_values, dict) else {}
    if pane_id == "oa":
        return _clean_workbench_column_values(
            {
                "applicant": table_values.get("applicant") or row.get("applicant"),
                "projectName": table_values.get("projectName") or row.get("project_name_display") or row.get("project_name"),
                "applicationType": table_values.get("applicationType") or row.get("apply_type"),
                "counterparty": table_values.get("counterparty") or row.get("counterparty_name"),
                "reconciliationStatus": table_values.get("reconciliationStatus") or _workbench_relation_label(row),
                "amount": table_values.get("amount") or row.get("amount"),
                "reason": table_values.get("reason") or row.get("reason"),
            }
        )
    if pane_id == "bank":
        direction = text(table_values.get("direction")) or _workbench_bank_direction(row)
        payment_account = text(table_values.get("paymentAccount")) or text(row.get("payment_account_label"))
        return _clean_workbench_column_values(
            {
                "transactionTime": table_values.get("transactionTime") or row.get("trade_time"),
                "direction": direction,
                "amount": table_values.get("amount") or _workbench_bank_amount(row),
                "debitAmount": table_values.get("debitAmount") or row.get("debit_amount"),
                "creditAmount": table_values.get("creditAmount") or row.get("credit_amount"),
                "counterparty": table_values.get("counterparty") or row.get("counterparty_name"),
                "paymentAccount": payment_account,
                "invoiceRelationStatus": table_values.get("invoiceRelationStatus") or _workbench_relation_label(row),
                "paymentOrReceiptTime": table_values.get("paymentOrReceiptTime") or row.get("pay_receive_time"),
                "note": table_values.get("note") or row.get("remark"),
                "loanRepaymentDate": table_values.get("loanRepaymentDate") or row.get("repayment_date"),
            }
        )
    if pane_id == "invoice":
        return _clean_workbench_column_values(
            {
                "sellerTaxId": table_values.get("sellerTaxId") or row.get("seller_tax_no"),
                "sellerName": table_values.get("sellerName") or row.get("seller_name"),
                "buyerTaxId": table_values.get("buyerTaxId") or row.get("buyer_tax_no"),
                "buyerName": table_values.get("buyerName") or row.get("buyer_name"),
                "invoiceCode": table_values.get("invoiceCode") or row.get("invoice_code"),
                "invoiceNo": table_values.get("invoiceNo") or row.get("invoice_no") or row.get("digital_invoice_no"),
                "digitalInvoiceNo": table_values.get("digitalInvoiceNo") or row.get("digital_invoice_no"),
                "issueDate": table_values.get("issueDate") or row.get("issue_date"),
                "amount": table_values.get("amount") or row.get("amount"),
                "taxRate": table_values.get("taxRate") or row.get("tax_rate"),
                "taxAmount": table_values.get("taxAmount") or row.get("tax_amount"),
                "grossAmount": table_values.get("grossAmount") or row.get("total_with_tax"),
                "invoiceType": table_values.get("invoiceType") or row.get("invoice_type"),
            }
        )
    return {}


def _clean_workbench_column_values(values: dict[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in values.items():
        normalized = text(value)
        if normalized is None or normalized in WORKBENCH_FILTER_PLACEHOLDERS:
            continue
        result[key] = normalized
    return result


def _workbench_bank_direction(row: dict[str, Any]) -> str | None:
    direction = text(row.get("direction"))
    if direction in {"支出", "收入"}:
        return direction
    if text(row.get("debit_amount")) not in {None, "", "--", "—"}:
        return "支出"
    if text(row.get("credit_amount")) not in {None, "", "--", "—"}:
        return "收入"
    return None


def _workbench_bank_amount(row: dict[str, Any]) -> str | None:
    return text(row.get("debit_amount")) or text(row.get("credit_amount")) or text(row.get("amount"))


def _workbench_relation_label(row: dict[str, Any]) -> str | None:
    for key in ("oa_bank_relation", "invoice_relation", "relation"):
        relation = row.get(key)
        if isinstance(relation, dict):
            label = text(relation.get("label"))
            if label:
                return label
    return text(row.get("status"))


def _workbench_date_from_text(value: str | None) -> str | None:
    normalized = text(value)
    if normalized is None:
        return None
    match = re.search(r"(\d{4})-(\d{2})-(\d{2})", normalized)
    if not match:
        return None
    return f"{match.group(1)}-{match.group(2)}-{match.group(3)}"


def _searchable_row_text(row: dict[str, Any], pane_id: str) -> str:
    values = [text(row.get("id") or row.get("row_id")), text(row.get("label")), text(row.get("status"))]
    values.extend(text(value) for value in _workbench_row_column_values(row, pane_id).values())
    values.append(text(row.get("amount_value")))
    tags = row.get("tags")
    if isinstance(tags, list):
        values.extend(text(tag) for tag in tags)
    return " ".join(value for value in values if value)


def _workbench_group_row_identity(group: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    identities = []
    for fallback_row_type, row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        if row_role == "summary":
            continue
        row_id = _workbench_row_id(row)
        if row_id is None:
            continue
        row_type = text(row.get("type") or row.get("record_type")) or fallback_row_type
        identities.append((row_type, row_id))
    return tuple(sorted(set(identities)))


def _workbench_group_row_records(group: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    group_id = text(group.get("group_id") or group.get("id"))
    zone = text(group.get("zone") or group.get("status")) or "open"
    if group_id is None:
        return records
    for pane, row_role, row_index, row in _iter_typed_group_rows_with_metadata(group):
        row_id = text(row.get("id") or row.get("row_id"))
        if row_id is None:
            continue
        column_values = _workbench_row_column_values(row, pane)
        time_value = _workbench_row_sort_value(row, pane)
        records.append(
            {
                "group_id": group_id,
                "zone": zone,
                "pane": pane,
                "row_id": row_id,
                "row_role": row_role,
                "row_index": row_index,
                "source_kind": text(row.get("source_kind") or row.get("type") or pane) or pane,
                "status": text(row.get("status") or zone) or zone,
                "time_value": time_value,
                "time_date": _workbench_date_from_text(time_value),
                "column_values": column_values,
                "searchable_text": _searchable_row_text(row, pane),
                "object_identity_key": text(row.get("object_identity_key")),
                "object_identity_kind": text(row.get("object_identity_kind")),
                "object_identity_source": text(row.get("object_identity_source")),
                "object_identity_confidence": text(row.get("object_identity_confidence")),
                "payload": serialize_value(row),
            }
        )
    return records


def _workbench_group_payload_for_rows(group: dict[str, Any]) -> dict[str, Any]:
    payload = deepcopy(group.get("payload") if isinstance(group.get("payload"), dict) else group)
    payload.setdefault("group_id", text(group.get("group_id") or group.get("id")))
    payload.setdefault("zone", text(group.get("zone") or group.get("status")) or "open")
    payload.setdefault("status", text(group.get("status") or group.get("zone")) or "open")
    payload.setdefault("scope_month", group.get("scope_month"))
    payload.setdefault("month", group.get("month"))
    return payload


def _iter_typed_group_rows_with_metadata(group: dict[str, Any]) -> list[tuple[str, str, int, dict[str, Any]]]:
    rows: list[tuple[str, str, int, dict[str, Any]]] = []
    for row_type, key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        value = group.get(key)
        if isinstance(value, list):
            rows.extend(
                (
                    row_type,
                    "summary" if _is_workbench_summary_display_row(row, row_type) else "normal",
                    index,
                    row,
                )
                for index, row in enumerate(value)
                if isinstance(row, dict)
            )
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for row_type, value in collapsed_rows.items():
            if isinstance(value, list):
                rows.extend((str(row_type), "collapsed", index, row) for index, row in enumerate(value) if isinstance(row, dict))
    return rows


def _iter_typed_group_rows(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for row_type, _row_role, _row_index, row in _iter_typed_group_rows_with_metadata(group):
        rows.append((row_type, row))
    return rows


def _iter_group_rows(group: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for key, value in group.items():
        if str(key).endswith("_rows") and isinstance(value, list):
            rows.extend(row for row in value if isinstance(row, dict))
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for value in collapsed_rows.values():
            if isinstance(value, list):
                rows.extend(row for row in value if isinstance(row, dict))
    return rows


def _searchable_group_text(group: dict[str, Any]) -> str:
    values: list[str] = []

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for nested_value in value.values():
                collect(nested_value)
        elif isinstance(value, list):
            for nested_value in value:
                collect(nested_value)
        elif value not in (None, ""):
            values.append(str(value))

    collect(group)
    return " ".join(values)[:12000]


def _read_model_payload(row: dict[str, Any], *, drop_rebuildable_rows: bool = False) -> Any:
    payload = row_payload(row, "payload", "extra_payload", "raw_payload")
    if drop_rebuildable_rows and isinstance(payload, dict) and payload.get("rebuildable") is True:
        return None
    return without_keys(payload, {"rebuildable"})


def _workbench_reconciliation_row_types(payload: dict[str, Any]) -> list[str]:
    row_types: list[str] = []
    for row_type, key in (("oa", "oa_row_ids"), ("bank", "bank_row_ids"), ("invoice", "invoice_row_ids")):
        row_types.extend(row_type for _row_id in text_list(payload.get(key)))
    return row_types


def _workbench_reconciliation_decision_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    if isinstance(payload, dict) and payload:
        result = dict(payload)
    else:
        result = {}
    for key in (
        "decision_id",
        "decision_key",
        "display_state",
        "decision_status",
        "match_domain",
        "match_shape",
        "rule_code",
        "rule_version",
        "direction",
        "explanation",
    ):
        result[key] = text(row.get(key))
    result["scope_month"] = str(row.get("scope_month") or "")[:7]
    result["row_ids"] = text_list(row.get("row_ids"))
    result["oa_row_ids"] = text_list(row.get("oa_row_ids"))
    result["bank_row_ids"] = text_list(row.get("bank_row_ids"))
    result["invoice_row_ids"] = text_list(row.get("invoice_row_ids"))
    result["amount"] = decimal_text(row.get("amount"))
    result["payment_amount_closed"] = bool(row.get("payment_amount_closed"))
    result["invoice_amount_closed"] = bool(row.get("invoice_amount_closed"))
    result["warnings"] = row.get("warnings") if isinstance(row.get("warnings"), list) else []
    result["evidence"] = row.get("evidence") if isinstance(row.get("evidence"), dict) else {}
    result["blockers"] = row.get("blockers") if isinstance(row.get("blockers"), list) else []
    result["source_versions"] = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
    result["consumed_by_relation_id"] = text(row.get("consumed_by_relation_id"))
    result["suppressed_by_exception_case_id"] = text(row.get("suppressed_by_exception_case_id"))
    return result


def _enqueue_workbench_relation_refresh_in_transaction(
    connection: Any,
    *,
    tenant_id: str,
    scope_key: str,
    reason: str,
) -> None:
    payload = {
        "scope_type": "workbench_relation",
        "scope_key": scope_key,
        "reason": reason,
    }
    dirty_row = connection.fetch_one(
        """
        insert into job.read_model_dirty_scopes(
            tenant_id, scope_type, scope_key, reason, payload, raw_payload,
            source_version, status, next_run_at, priority
        )
        values (
            %s, 'workbench_relation', %s, %s, %s, %s,
            coalesce((
                select max(existing.source_version) + 1
                from job.read_model_dirty_scopes existing
                where existing.tenant_id = %s
                  and existing.scope_type = 'workbench_relation'
                  and existing.scope_key = %s
            ), 0),
            'pending',
            now(),
            'normal'
        )
        on conflict (tenant_id, scope_type, scope_key)
        where status in ('pending', 'processing')
        do update set
            reason = excluded.reason,
            payload = job.read_model_dirty_scopes.payload || excluded.payload,
            raw_payload = excluded.raw_payload,
            source_version = job.read_model_dirty_scopes.source_version + 1,
            status = 'pending',
            next_run_at = now(),
            priority = excluded.priority,
            updated_at = now()
        returning source_version
        """,
        (
            text(tenant_id) or "default",
            text(scope_key) or "all",
            text(reason) or "workbench_relation_changed",
            jsonb(payload),
            jsonb(payload),
            text(tenant_id) or "default",
            text(scope_key) or "all",
        ),
    )
    source_version = int_value((dirty_row or {}).get("source_version"), 0)
    event_payload = {**payload, "source_version": source_version}
    connection.execute(
        """
        insert into job.outbox_events(tenant_id, event_type, aggregate_type, aggregate_id, payload, raw_payload, available_at)
        values (%s, 'workbench_relation.read_model.refresh', 'read_model_scope', %s, %s, %s, now())
        """,
        (
            text(tenant_id) or "default",
            f"workbench_relation:{text(scope_key) or 'all'}",
            jsonb(event_payload),
            jsonb(event_payload),
        ),
    )


def _enqueue_workbench_refresh_in_transaction(
    connection: Any,
    *,
    tenant_id: str,
    scope_key: str,
    reason: str,
) -> None:
    RuntimeQueueRepository(connection).enqueue_read_model_refresh_in_transaction(
        transaction=connection,
        tenant_id=text(tenant_id) or "default",
        scope_type="workbench",
        scope_key=text(scope_key) or "all",
        reason=text(reason) or "workbench_changed",
        metadata={"source": "workbench_reconciliation_decision_cleanup"},
    )


def _retry_backoff_case_sql(retry_backoff_seconds: list[int]) -> str:
    backoffs = [max(0, int_value(value, 0)) for value in retry_backoff_seconds]
    if not backoffs:
        backoffs = [0]
    clauses = " ".join(
        f"when attempt_count + 1 = {index} then {delay_seconds}"
        for index, delay_seconds in enumerate(backoffs, start=1)
    )
    return f"case {clauses} else {backoffs[-1]} end"


def _source_version_value(source_versions: Any) -> int | None:
    if not isinstance(source_versions, dict):
        return None
    value = source_versions.get("source_version")
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _workbench_source_versions_allow_stale_write_skip(incoming: Any, existing: Any) -> bool:
    if not isinstance(incoming, dict) or not isinstance(existing, dict):
        return True
    for key, value in incoming.items():
        if key == "source_version":
            continue
        if existing.get(key) != value:
            return False
    return True


def _source_versions_from_scope_summary(scope_summary: dict[str, Any]) -> dict[str, Any]:
    signatures = (
        scope_summary.get("read_model_scope_signatures")
        if isinstance(scope_summary.get("read_model_scope_signatures"), dict)
        else {}
    )
    scope_keys = text_list(scope_summary.get("read_model_scope_keys"))
    if len(scope_keys) == 1:
        signature = signatures.get(scope_keys[0]) if isinstance(signatures.get(scope_keys[0]), dict) else {}
        source_versions = signature.get("source_versions") if isinstance(signature.get("source_versions"), dict) else {}
        return dict(source_versions)
    result: dict[str, Any] = {}
    for scope_key in scope_keys:
        signature = signatures.get(scope_key) if isinstance(signatures.get(scope_key), dict) else {}
        if isinstance(signature.get("source_versions"), dict):
            result[scope_key] = dict(signature.get("source_versions"))
    return result


def _pending_invoice_scope_source_versions_row(scope_key: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return None
    if len(normalized_rows) == 1:
        row = normalized_rows[0]
        return {
            "scope_key": text(row.get("scope_key")) or scope_key,
            "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
        }
    first_versions = (
        normalized_rows[0].get("source_versions")
        if isinstance(normalized_rows[0].get("source_versions"), dict)
        else {}
    )
    aggregate = dict(first_versions)
    bank_detail_by_month: dict[str, Any] = {}
    workbench_relation_by_month: dict[str, Any] = {}
    for row in normalized_rows:
        row_scope_key = text(row.get("scope_key")) or ""
        source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
        bank_detail_versions = (
            source_versions.get("bank_detail_source_versions")
            if isinstance(source_versions.get("bank_detail_source_versions"), dict)
            else {}
        )
        workbench_relation_versions = (
            source_versions.get("workbench_relation_source_versions")
            if isinstance(source_versions.get("workbench_relation_source_versions"), dict)
            else {}
        )
        _direction, _filter_group, scope_month = _parse_pending_invoice_scope_key(row_scope_key)
        month_key = scope_month[:7] if scope_month else row_scope_key
        if month_key:
            if bank_detail_versions:
                bank_detail_by_month[month_key] = dict(bank_detail_versions)
            if workbench_relation_versions:
                workbench_relation_by_month[month_key] = dict(workbench_relation_versions)
    if bank_detail_by_month:
        aggregate["bank_detail_source_versions"] = bank_detail_by_month
    if workbench_relation_by_month:
        aggregate["workbench_relation_source_versions"] = workbench_relation_by_month
    return {"scope_key": scope_key, "source_versions": aggregate}


def _scope_source_versions_by_month(rows: list[dict[str, Any]]) -> dict[str, Any]:
    normalized_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return {}
    if len(normalized_rows) == 1:
        source_versions = normalized_rows[0].get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}
    result: dict[str, Any] = {}
    for row in normalized_rows:
        scope_key = text(row.get("scope_key"))
        source_versions = row.get("source_versions")
        if scope_key and isinstance(source_versions, dict):
            result[scope_key] = dict(source_versions)
    return result


def _workbench_relation_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    base = dict(payload) if isinstance(payload, dict) else {}
    row_id = text(base.get("row_id") or row.get("row_id")) or ""
    row_type = text(base.get("row_type") or row.get("row_type")) or ""
    relation_status = text(base.get("relation_status") or row.get("relation_status")) or "unlinked"
    return {
        "row_id": row_id,
        "row_type": row_type,
        "scope_key": text(base.get("scope_key") or row.get("scope_key")),
        "scope_month": text(base.get("scope_month") or row.get("scope_month")),
        "relation_status": relation_status,
        "group_ids": text_list(base.get("group_ids") if "group_ids" in base else row.get("group_ids")),
        "linked_oa": _list_payload(base.get("linked_oa") if "linked_oa" in base else row.get("linked_oa")),
        "linked_bank_transactions": _list_payload(
            base.get("linked_bank_transactions")
            if "linked_bank_transactions" in base
            else row.get("linked_bank_transactions")
        ),
        "linked_input_invoices": _list_payload(
            base.get("linked_input_invoices") if "linked_input_invoices" in base else row.get("linked_input_invoices")
        ),
        "linked_output_invoices": _list_payload(
            base.get("linked_output_invoices")
            if "linked_output_invoices" in base
            else row.get("linked_output_invoices")
        ),
        "payload": base.get("payload") if isinstance(base.get("payload"), dict) else {},
    }


def _workbench_relation_group_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    base = dict(payload) if isinstance(payload, dict) else {}
    relation_payload = base.get("payload") if isinstance(base.get("payload"), dict) else base
    return {
        "group_id": text(base.get("group_id") or row.get("group_id")) or "",
        "scope_key": text(base.get("scope_key") or row.get("scope_key")),
        "scope_month": text(base.get("scope_month") or row.get("scope_month")),
        "relation_source": text(base.get("relation_source") or row.get("relation_source")) or "manual",
        "relation_kind": text(base.get("relation_kind") or row.get("relation_kind")) or "linked",
        "relation_status": text(base.get("relation_status") or row.get("relation_status")) or "linked",
        "oa_row_ids": text_list(base.get("oa_row_ids") if "oa_row_ids" in base else row.get("oa_row_ids")),
        "bank_transaction_ids": text_list(
            base.get("bank_transaction_ids") if "bank_transaction_ids" in base else row.get("bank_transaction_ids")
        ),
        "input_invoice_ids": text_list(
            base.get("input_invoice_ids") if "input_invoice_ids" in base else row.get("input_invoice_ids")
        ),
        "output_invoice_ids": text_list(
            base.get("output_invoice_ids") if "output_invoice_ids" in base else row.get("output_invoice_ids")
        ),
        "payload": relation_payload,
    }


def _source_versions_from_relation_records(rows: list[dict[str, Any]]) -> dict[str, Any]:
    for row in list(rows or []):
        if isinstance(row, dict) and isinstance(row.get("source_versions"), dict):
            return dict(row.get("source_versions"))
        payload = _read_model_payload(row) if isinstance(row, dict) else {}
        if isinstance(payload, dict) and isinstance(payload.get("source_versions"), dict):
            return dict(payload.get("source_versions"))
    return {}


def _list_payload(value: Any) -> list[dict[str, Any]]:
    return [dict(item) for item in list(value or []) if isinstance(item, dict)]


def _dedupe_preserve_order(values: Any) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text_value = text(value)
        if text_value is None or text_value in seen:
            continue
        seen.add(text_value)
        result.append(text_value)
    return result


def _bank_detail_scope_keys_for_range(*, date_from: str | None, date_to: str | None) -> list[str]:
    start_month = _bank_detail_month_text(date_from)
    end_month = _bank_detail_month_text(date_to)
    if start_month is None and end_month is None:
        return ["all"]
    if start_month is None:
        start_month = end_month
    if end_month is None:
        end_month = start_month
    if start_month is None or end_month is None:
        return ["all"]
    start_year, start_month_number = int(start_month[:4]), int(start_month[5:7])
    end_year, end_month_number = int(end_month[:4]), int(end_month[5:7])
    start_index = start_year * 12 + start_month_number
    end_index = end_year * 12 + end_month_number
    if start_index > end_index:
        start_index, end_index = end_index, start_index
    scope_keys = []
    for index in range(start_index, end_index + 1):
        year = (index - 1) // 12
        month = (index - 1) % 12 + 1
        scope_keys.append(f"{year:04d}-{month:02d}")
    return scope_keys or ["all"]


def _bank_detail_month_text(value: Any) -> str | None:
    normalized = text(value)
    if normalized is None:
        return None
    candidate = normalized[:7]
    return candidate if MONTH_SCOPE_RE.match(candidate) else None


UNCATEGORIZED_CATEGORY_FILTER_CODE = "uncategorized"


def _bank_detail_filter_sql(
    *,
    tenant_id: str,
    scope_keys: list[str],
    account_key: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    keyword: str | None = None,
    category_code: str | None = None,
    category_primary_label: str | None = None,
    category_sub_label: str | None = None,
    category_third_label: str | None = None,
    require_current_schema: bool = True,
) -> tuple[str, list[Any]]:
    where = ["tenant_id = %s", "scope_key = any(%s)"]
    params: list[Any] = [tenant_id, list(scope_keys or ["all"])]
    if require_current_schema:
        where.append("schema_version = %s")
        params.append(BANK_DETAIL_READ_MODEL_SCHEMA_VERSION)
    if normalized_account_key := text(account_key):
        where.append("account_key = %s")
        params.append(normalized_account_key)
    if normalized_date_from := text(date_from):
        where.append("trade_date >= %s::date")
        params.append(normalized_date_from[:10])
    if normalized_date_to := text(date_to):
        where.append("trade_date <= %s::date")
        params.append(normalized_date_to[:10])
    if normalized_keyword := text(keyword):
        where.append("search_text ilike %s")
        params.append(f"%{normalized_keyword}%")
    if normalized_category_code := text(category_code):
        if normalized_category_code == UNCATEGORIZED_CATEGORY_FILTER_CODE:
            where.append("effective_category_code is null")
        else:
            where.append("effective_category_code = %s")
            params.append(normalized_category_code)
    if not require_current_schema and text(category_code):
        return " and ".join(where), params
    if normalized_category_primary_label := text(category_primary_label):
        where.append("effective_category_primary_label = %s")
        params.append(normalized_category_primary_label)
    if normalized_category_sub_label := text(category_sub_label):
        where.append("effective_category_sub_label = %s")
        params.append(normalized_category_sub_label)
    if normalized_category_third_label := text(category_third_label):
        where.append("effective_category_third_label = %s")
        params.append(normalized_category_third_label)
    return " and ".join(where), params


def _bank_detail_empty_category_counts() -> dict[str, int]:
    return {key: 0 for key in BANK_TRANSACTION_CATEGORY_COUNT_KEYS}


def _bank_detail_refreshing_payload(
    *,
    scope_summary: dict[str, Any],
    account_key: str | None,
    date_from: str | None,
    date_to: str | None,
    page: int,
    page_size: int,
) -> dict[str, Any]:
    return {
        "account_key": account_key,
        "date_from": date_from,
        "date_to": date_to,
        "rows": [],
        "category_counts": _bank_detail_empty_category_counts(),
        "pagination": {"page": page, "page_size": page_size, "total": 0},
        **scope_summary,
    }


def _bank_detail_row_payload(row: dict[str, Any]) -> dict[str, Any]:
    payload = _read_model_payload(row)
    if not isinstance(payload, dict):
        return {}
    result = dict(payload)
    text_fields = _bank_detail_text_display_fields(result, row)
    result["purpose_text"] = text_fields["purpose_text"]
    result["summary_text"] = text_fields["summary_text"]
    result["note_text"] = text_fields["note_text"]
    result["summary"] = text_fields["summary_text"]
    result["purpose"] = text_fields["purpose_text"] or text_fields["note_text"]
    return result


def _bank_detail_text_display_fields(payload: dict[str, Any], row: dict[str, Any]) -> dict[str, str]:
    raw_payload = row_payload(row, "raw_payload")
    normalized_payload = raw_payload.get("normalized_payload") if isinstance(raw_payload, dict) and isinstance(raw_payload.get("normalized_payload"), dict) else raw_payload
    if not isinstance(normalized_payload, dict):
        normalized_payload = {}
    bank_text_fields = payload.get("bank_text_fields") or normalized_payload.get("bank_text_fields")
    fields_by_label = _bank_detail_text_fields_by_label(bank_text_fields)
    summary_text = _first_bank_detail_text_field(fields_by_label, BANK_DETAIL_SUMMARY_TEXT_LABELS)
    purpose_text = _first_bank_detail_text_field(fields_by_label, BANK_DETAIL_PURPOSE_TEXT_LABELS)
    note_text = _first_bank_detail_text_field(fields_by_label, BANK_DETAIL_NOTE_TEXT_LABELS)
    if not fields_by_label:
        return _legacy_bank_detail_text_display_fields(payload, row, normalized_payload)
    return {
        "purpose_text": purpose_text.strip(),
        "summary_text": summary_text.strip(),
        "note_text": note_text.strip(),
    }


def _legacy_bank_detail_text_display_fields(payload: dict[str, Any], row: dict[str, Any], normalized_payload: dict[str, Any]) -> dict[str, str]:
    bank_name = text(payload.get("bank_name") or normalized_payload.get("imported_bank_name") or normalized_payload.get("bank_name")) or ""
    summary_text = text(payload.get("summary_text") or payload.get("summary") or row.get("summary") or normalized_payload.get("summary")) or ""
    purpose_text = text(payload.get("purpose_text") or payload.get("purpose") or row.get("purpose") or normalized_payload.get("purpose")) or ""
    note_text = text(payload.get("note_text") or payload.get("note") or payload.get("remark") or normalized_payload.get("note") or normalized_payload.get("remark")) or ""
    if "民生" in bank_name:
        return {"purpose_text": "", "summary_text": "", "note_text": note_text or purpose_text or summary_text}
    if "交通" in bank_name or "光大" in bank_name:
        return {"purpose_text": "", "summary_text": summary_text or purpose_text or note_text, "note_text": ""}
    if "建设" in bank_name:
        return {"purpose_text": "", "summary_text": summary_text, "note_text": note_text or purpose_text}
    if "平安" in bank_name:
        return {"purpose_text": purpose_text or note_text, "summary_text": summary_text, "note_text": ""}
    if "工商" in bank_name:
        return {"purpose_text": purpose_text if purpose_text != note_text else "", "summary_text": summary_text, "note_text": note_text}
    return {"purpose_text": purpose_text, "summary_text": summary_text, "note_text": note_text}


def _bank_detail_text_fields_by_label(value: Any) -> dict[str, str]:
    fields: dict[str, str] = {}
    if isinstance(value, dict):
        iterable = [{"label": label, "value": field_value} for label, field_value in value.items()]
    else:
        iterable = list(value or []) if isinstance(value, list) else []
    for item in iterable:
        if not isinstance(item, dict):
            continue
        label = text(item.get("label"))
        field_value = text(item.get("value"))
        if label and field_value and label not in fields:
            fields[label] = field_value
    return fields


def _first_bank_detail_text_field(fields_by_label: dict[str, str], labels: tuple[str, ...]) -> str:
    for label in labels:
        value = fields_by_label.get(label)
        if value:
            return value
    return ""


def _bank_detail_row_record(row: dict[str, Any], *, scope_key: str, scope_month: date | None, tenant_id: str) -> tuple[Any, ...]:
    payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
    raw_payload = serialize_value(row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {"normalized_payload": payload})
    transaction_id = text(row.get("transaction_id") or row.get("id") or payload.get("id"))
    if transaction_id is None:
        raise ValueError("bank detail read model row requires transaction_id.")
    direction = text(row.get("direction") or payload.get("direction")) or "expense"
    if direction not in {"income", "expense"}:
        direction = "income" if direction in {"收入", "收", "credit"} else "expense"
    relation_tags = text_list(row.get("relation_tags") or payload.get("relation_tags"))
    source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
    generated_at = text(row.get("generated_at") or payload.get("generated_at"))
    trade_time = text(row.get("trade_time") or payload.get("trade_time"))
    trade_date = text(row.get("trade_date") or payload.get("trade_date") or trade_time)
    trade_date = trade_date[:10] if trade_date else None
    trade_time_sort = text(row.get("trade_time_sort") or row.get("trade_time") or payload.get("trade_time") or payload.get("trade_date") or trade_date)
    amount = decimal_text(row.get("amount") or payload.get("amount")) or "0"
    return (
        tenant_id,
        transaction_id,
        scope_key,
        scope_month,
        text(row.get("source_batch_id") or payload.get("source_batch_id")),
        text(row.get("legacy_source_batch_id") or payload.get("legacy_source_batch_id")),
        text(row.get("account_key") or payload.get("account_key")) or "unknown:unknown",
        text(row.get("bank_name") or payload.get("bank_name")) or "未知银行",
        text(row.get("account_last4") or payload.get("account_last4")) or "unknown",
        text(row.get("account_no") or payload.get("account_no")),
        text(row.get("account_name") or payload.get("account_name")),
        trade_time,
        trade_date,
        trade_time_sort,
        direction,
        text(row.get("direction_label") or payload.get("direction_label")) or ("收" if direction == "income" else "支"),
        amount,
        decimal_text(row.get("signed_amount") or payload.get("signed_amount")),
        decimal_text(row.get("balance") or payload.get("balance")),
        text(row.get("currency") or payload.get("currency")) or "CNY",
        text(row.get("counterparty_name") or payload.get("counterparty_name")),
        text(row.get("summary") or payload.get("summary")),
        text(row.get("purpose") or payload.get("purpose")),
        text(row.get("manual_category_code") or payload.get("manual_category_code")),
        text(row.get("manual_category_label") or payload.get("manual_category_label")),
        text_list(row.get("manual_category_path") or payload.get("manual_category_path")),
        text(row.get("manual_category_primary_label") or payload.get("manual_category_primary_label")),
        text(row.get("manual_category_sub_label") or payload.get("manual_category_sub_label")),
        text(row.get("manual_category_third_label") or payload.get("manual_category_third_label")),
        text_list(row.get("manual_category_label_path") or payload.get("manual_category_label_path")),
        text(row.get("manual_category_source") or payload.get("manual_category_source")),
        int_value(row.get("manual_category_version") or payload.get("manual_category_version"), None),
        text(row.get("manual_confirmed_category_code") or payload.get("manual_confirmed_category_code")),
        text(row.get("auto_category_code") or payload.get("auto_category_code")),
        text(row.get("auto_category_label") or payload.get("auto_category_label")),
        text_list(row.get("auto_category_path") or payload.get("auto_category_path")),
        text(row.get("auto_category_primary_label") or payload.get("auto_category_primary_label")),
        text(row.get("auto_category_sub_label") or payload.get("auto_category_sub_label")),
        text(row.get("auto_category_third_label") or payload.get("auto_category_third_label")),
        text_list(row.get("auto_category_label_path") or payload.get("auto_category_label_path")),
        text(row.get("auto_category_source") or payload.get("auto_category_source")),
        text(row.get("auto_category_rule_code") or payload.get("auto_category_rule_code")),
        text(row.get("auto_category_reason") or payload.get("auto_category_reason")),
        text(row.get("auto_category_confidence") or payload.get("auto_category_confidence")),
        text(row.get("auto_category_rule_version") or payload.get("auto_category_rule_version")),
        text_list(row.get("auto_candidate_category_codes") or payload.get("auto_candidate_category_codes")),
        jsonb(row.get("auto_candidate_categories") or payload.get("auto_candidate_categories") or []),
        text(row.get("effective_category_code") or payload.get("effective_category_code")),
        text(row.get("effective_category_label") or payload.get("effective_category_label")),
        text_list(row.get("effective_category_path") or payload.get("effective_category_path")),
        text(row.get("effective_category_primary_label") or payload.get("effective_category_primary_label")),
        text(row.get("effective_category_sub_label") or payload.get("effective_category_sub_label")),
        text(row.get("effective_category_third_label") or payload.get("effective_category_third_label")),
        text_list(row.get("effective_category_label_path") or payload.get("effective_category_label_path")),
        text(row.get("effective_category_source") or payload.get("effective_category_source")),
        text(row.get("effective_turnover_role") or payload.get("effective_turnover_role") or row.get("turnover_role") or payload.get("turnover_role")),
        text(row.get("effective_turnover_action_type") or payload.get("effective_turnover_action_type") or row.get("turnover_action_type") or payload.get("turnover_action_type")),
        text(row.get("effective_turnover_family") or payload.get("effective_turnover_family") or row.get("turnover_family") or payload.get("turnover_family")),
        int_value(row.get("category_version") or payload.get("category_version"), None),
        text(row.get("category_source") or payload.get("category_source")),
        text(row.get("category_resolution_status") or payload.get("category_resolution_status")) or "unmatched",
        text(row.get("category_rule_version") or payload.get("category_rule_version")),
        text(row.get("oa_relation_tag") or payload.get("oa_relation_tag")),
        text(row.get("invoice_relation_tag") or payload.get("invoice_relation_tag")),
        relation_tags,
        text(row.get("relation_case_id") or payload.get("relation_case_id")),
        text(row.get("search_text") or payload.get("search_text")) or _bank_detail_search_text(payload),
        BANK_DETAIL_READ_MODEL_SCHEMA_VERSION,
        jsonb(source_versions),
        generated_at,
        jsonb(payload),
        jsonb(raw_payload),
    )


def _bank_detail_search_text(row: dict[str, Any]) -> str:
    values = [
        row.get("id"),
        row.get("trade_time"),
        row.get("counterparty_name"),
        row.get("direction_label"),
        row.get("amount"),
        row.get("balance"),
        row.get("summary"),
        row.get("purpose"),
        row.get("bank_name"),
        row.get("account_last4"),
        row.get("manual_category_label"),
        row.get("manual_category_primary_label"),
        row.get("manual_category_sub_label"),
        row.get("manual_category_third_label"),
        row.get("auto_category_label"),
        row.get("auto_category_primary_label"),
        row.get("auto_category_sub_label"),
        row.get("auto_category_third_label"),
        row.get("effective_category_label"),
        row.get("effective_category_primary_label"),
        row.get("effective_category_sub_label"),
        row.get("effective_category_third_label"),
        row.get("turnover_action_type"),
        row.get("turnover_family"),
        row.get("oa_relation_tag"),
        row.get("invoice_relation_tag"),
        row.get("relation_case_id"),
    ]
    relation_tags = row.get("relation_tags")
    if isinstance(relation_tags, list):
        values.extend(relation_tags)
    for path_key in ("manual_category_label_path", "auto_category_label_path", "effective_category_label_path"):
        path_values = row.get(path_key)
        if isinstance(path_values, list):
            values.extend(path_values)
    return " ".join(str(value) for value in values if value not in (None, ""))


def _empty_search_payload(
    query: str,
    scope: str,
    month: str,
    project_name: str | None,
    status: str | None,
    limit: int,
) -> dict[str, Any]:
    return {
        "query": query,
        "filters": {
            "scope": scope,
            "month": month,
            "project_name": project_name or None,
            "status": status or None,
            "limit": limit,
        },
        "summary": {"total": 0, "oa": 0, "bank": 0, "invoice": 0},
        "oa_results": [],
        "bank_results": [],
        "invoice_results": [],
        "refresh_status": "fresh",
    }
