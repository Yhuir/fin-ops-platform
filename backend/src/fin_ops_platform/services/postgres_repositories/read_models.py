from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from datetime import date
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote

from fin_ops_platform.services.read_model_freshness import normalize_source_versions
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_source_snapshot import (
    OA_PENDING_PAYMENT_COVERAGE_ONLY_SCHEMA_VERSION,
    oa_pending_payment_coverage_only_source_versions,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import COMPLETED_WORKFLOW_STATUS_SQL
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
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE
MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
WORKBENCH_PANES = ("oa", "bank", "invoice")
WORKBENCH_FILTER_PLACEHOLDERS = {"", "--", "—"}
NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND = "no_oa_bank_batch_summary"
BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND = "bank_flow_rule_batch_summary"
WORKBENCH_BANK_BATCH_SUMMARY_SOURCE_KINDS = frozenset(
    {NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND, BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND}
)
_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL = """
    regexp_replace(
      coalesce(
        nullif(r.payload->>'source_oa_id', ''),
        nullif(r.payload->>'source_oa_row_id', ''),
        nullif(r.payload->>'derived_from_oa_id', ''),
        nullif(r.payload->>'source_expense_item_id', ''),
        nullif(r.payload->>'source_id', '')
      ),
      ':item:.*$',
      ''
    ) = any(
      coalesce(
        (select array_agg(candidate.oa_row_id) from oa_candidate_ids candidate),
        array[]::text[]
      )
    )
    or exists (
      select 1
      from oa_candidate_ids candidate
      where r.row_id like 'oa-att-inv-' || candidate.oa_row_id || '%%'
    )
    or exists (
      select 1
      from jsonb_array_elements(
        case
          when jsonb_typeof(r.payload->'source_links') = 'array' then r.payload->'source_links'
          else '[]'::jsonb
        end
      ) link
      where regexp_replace(
        coalesce(
          nullif(link->>'source_oa_id', ''),
          nullif(link->>'source_oa_row_id', ''),
          nullif(link->>'derived_from_oa_id', ''),
          nullif(link->>'source_expense_item_id', ''),
          nullif(link->>'source_id', '')
        ),
        ':item:.*$',
        ''
      ) = any(
        coalesce(
          (select array_agg(candidate.oa_row_id) from oa_candidate_ids candidate),
          array[]::text[]
        )
      )
    )
"""


def _execute_many(connection: Any, sql: str, params_seq: list[Any]) -> int:
    if not params_seq:
        return 0
    execute_many_values = getattr(connection, "execute_many_values", None)
    if callable(execute_many_values) and _should_execute_many_values(sql) and _supports_execute_many_values_params(params_seq):
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
        "insert into read_model.workbench_relation_rows" in normalized
        or "insert into read_model.workbench_relation_groups" in normalized
        or "insert into read_model.search_index_rows" in normalized
    )


def _supports_execute_many_values_params(params_seq: list[Any]) -> bool:
    return all(not isinstance(params, Mapping) for params in params_seq)


WORKBENCH_ALLOWED_FILTER_COLUMNS = {
    "oa": {"applicant", "projectName", "applicationType", "counterparty", "reconciliationStatus"},
    "bank": {"counterparty", "amount", "direction", "paymentAccount", "invoiceRelationStatus", "loanRepaymentDate"},
    "invoice": {"sellerName", "buyerName", "invoiceType"},
}
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
INPUT_INVOICE_USAGE_OPTION_FIELDS = {
    field: INPUT_INVOICE_USAGE_FILTER_FIELDS[field]
    for field in (
        "seller_name",
        "tax_rate",
        "specific_business_type",
        "taxable_item_name",
        "payment_status",
        "oa_applicant",
        "oa_application_type",
        "oa_project_name",
        "bank_counterparty_name",
        "bank_name",
        "bank_account",
        "bank_direction",
    )
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
OA_PENDING_PAYMENT_OPTION_FIELDS = {
    field: OA_PENDING_PAYMENT_FILTER_FIELDS[field]
    for field in (
        "oa_applicant",
        "oa_application_type",
        "oa_project_name",
        "payment_status",
        "bank_name",
        "bank_account",
        "bank_direction",
        "bank_counterparty_name",
        "seller_name",
    )
}









class PostgresSearchWorkbenchRelationReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

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

    def search_index_scope_summary(self, *, month: str) -> dict[str, Any]:
        scope_month = month_start(month)
        scope_key = text(month) or ""
        if scope_month is None or not scope_key:
            return {"read_model_status": "missing", "row_count": 0, "source_versions": {}}
        row = self._connection.fetch_one(
            """
            select
                count(*)::int as row_count,
                min(source_versions::text) as min_source_versions,
                max(source_versions::text) as max_source_versions,
                (array_agg(source_versions order by generated_at desc nulls last))[1] as source_versions
            from read_model.search_index_rows
            where scope_month = %s::date
            """,
            (scope_month,),
        )
        row_count = int_value((row or {}).get("row_count"), 0) if isinstance(row, dict) else 0
        if row_count <= 0:
            return {"read_model_status": "missing", "row_count": 0, "source_versions": {}}
        source_versions = (row or {}).get("source_versions") if isinstance(row, dict) else {}
        consistent = (
            isinstance(row, dict)
            and text(row.get("min_source_versions")) == text(row.get("max_source_versions"))
        )
        return {
            "read_model_status": self._refresh_status(scope_type="search", scope_key=scope_key),
            "row_count": row_count,
            "source_versions": dict(source_versions) if consistent and isinstance(source_versions, dict) else {},
        }


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
            if params_seq:
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
                    where (
                        read_model.search_index_rows.source_kind,
                        read_model.search_index_rows.scope_month,
                        read_model.search_index_rows.status,
                        read_model.search_index_rows.title,
                        read_model.search_index_rows.subtitle,
                        read_model.search_index_rows.searchable_text,
                        read_model.search_index_rows.project_name,
                        read_model.search_index_rows.counterparty_name,
                        read_model.search_index_rows.amount,
                        read_model.search_index_rows.source_versions,
                        read_model.search_index_rows.generated_at,
                        read_model.search_index_rows.payload,
                        read_model.search_index_rows.raw_payload
                    ) is distinct from (
                        excluded.source_kind,
                        excluded.scope_month,
                        excluded.status,
                        excluded.title,
                        excluded.subtitle,
                        excluded.searchable_text,
                        excluded.project_name,
                        excluded.counterparty_name,
                        excluded.amount,
                        excluded.source_versions,
                        excluded.generated_at,
                        excluded.payload,
                        excluded.raw_payload
                    )
                    """,
                    params_seq,
                )
                if scope_month is not None:
                    connection.execute(
                        "delete from read_model.search_index_rows where scope_month = %s::date and not (row_id = any(%s))",
                        (scope_month, list(params_by_row_id)),
                    )
            elif scope_month is not None:
                connection.execute("delete from read_model.search_index_rows where scope_month = %s::date", (scope_month,))

        run_in_transaction(self._connection, write)


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
            group_params: list[tuple[Any, ...]] = []
            for group in groups_to_save:
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else group
                group_params.append(
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
            _execute_many(
                connection,
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
                group_params,
            )
            row_params: list[tuple[Any, ...]] = []
            for row in rows_to_save:
                payload = _workbench_relation_row_payload(row)
                row_scope_month = month_start(row.get("scope_month") or normalized_scope_key) or scope_month
                row_params.append(
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
            _execute_many(
                connection,
                """
                insert into read_model.workbench_relation_rows(
                    tenant_id, row_id, row_type, scope_key, scope_month, relation_status, group_ids,
                    linked_oa, linked_bank_transactions, linked_input_invoices, linked_output_invoices,
                    source_versions, payload, raw_payload, generated_at
                )
                values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()))
                on conflict (tenant_id, scope_key, row_id) do update set
                    row_type = excluded.row_type,
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
                row_params,
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


    def save_workbench_relation_distribution_rows(
        self,
        *,
        scope_key: str,
        affected_row_ids: list[str],
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
        affected_ids = _dedupe_preserve_order(text(row_id) for row_id in list(affected_row_ids or []))
        rows_to_save = [row for row in list(rows or []) if isinstance(row, dict)]
        groups_to_save = [group for group in list(groups or []) if isinstance(group, dict)]
        row_ids_to_replace = _dedupe_preserve_order(
            [
                *affected_ids,
                *(text(_workbench_relation_row_payload(row).get("row_id")) for row in rows_to_save),
            ]
        )
        group_ids_to_replace = _dedupe_preserve_order(text(group.get("group_id")) for group in groups_to_save)
        if not affected_ids and not row_ids_to_replace and not group_ids_to_replace:
            return

        def write(connection: Any) -> None:
            if row_ids_to_replace or affected_ids or group_ids_to_replace:
                connection.execute(
                    """
                    with replaced_row_ids(row_id) as (
                      select unnest(%s::text[])
                      union
                      select unnest(
                        coalesce(oa_row_ids, array[]::text[])
                        || coalesce(bank_transaction_ids, array[]::text[])
                        || coalesce(input_invoice_ids, array[]::text[])
                        || coalesce(output_invoice_ids, array[]::text[])
                      )
                      from read_model.workbench_relation_groups
                      where tenant_id = %s
                        and scope_key = %s
                        and (
                          group_id = any(%s::text[])
                          or coalesce(oa_row_ids, array[]::text[]) && %s::text[]
                          or coalesce(bank_transaction_ids, array[]::text[]) && %s::text[]
                          or coalesce(input_invoice_ids, array[]::text[]) && %s::text[]
                          or coalesce(output_invoice_ids, array[]::text[]) && %s::text[]
                        )
                    )
                    delete from read_model.workbench_relation_rows target
                    using replaced_row_ids replacement
                    where target.tenant_id = %s
                      and target.scope_key = %s
                      and target.row_id = replacement.row_id
                    """,
                    (
                        row_ids_to_replace,
                        tenant_id,
                        normalized_scope_key,
                        group_ids_to_replace,
                        affected_ids,
                        affected_ids,
                        affected_ids,
                        affected_ids,
                        tenant_id,
                        normalized_scope_key,
                    ),
                )
            if affected_ids or group_ids_to_replace:
                connection.execute(
                    """
                    delete from read_model.workbench_relation_groups
                    where tenant_id = %s
                      and scope_key = %s
                      and (
                        group_id = any(%s::text[])
                        or coalesce(oa_row_ids, array[]::text[]) && %s::text[]
                        or coalesce(bank_transaction_ids, array[]::text[]) && %s::text[]
                        or coalesce(input_invoice_ids, array[]::text[]) && %s::text[]
                        or coalesce(output_invoice_ids, array[]::text[]) && %s::text[]
                      )
                    """,
                    (
                        tenant_id,
                        normalized_scope_key,
                        group_ids_to_replace,
                        affected_ids,
                        affected_ids,
                        affected_ids,
                        affected_ids,
                    ),
                )
            group_params: list[tuple[Any, ...]] = []
            for group in groups_to_save:
                payload = group.get("payload") if isinstance(group.get("payload"), dict) else group
                group_params.append(
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
            _execute_many(
                connection,
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
                group_params,
            )
            row_params: list[tuple[Any, ...]] = []
            for row in rows_to_save:
                payload = _workbench_relation_row_payload(row)
                row_scope_month = month_start(row.get("scope_month") or normalized_scope_key) or scope_month
                row_params.append(
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
            _execute_many(
                connection,
                """
                insert into read_model.workbench_relation_rows(
                    tenant_id, row_id, row_type, scope_key, scope_month, relation_status, group_ids,
                    linked_oa, linked_bank_transactions, linked_input_invoices, linked_output_invoices,
                    source_versions, payload, raw_payload, generated_at
                )
                values (%s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()))
                on conflict (tenant_id, scope_key, row_id) do update set
                    row_type = excluded.row_type,
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
                row_params,
            )
            count_row = connection.fetch_one(
                """
                select
                  (
                    select count(*)::integer
                    from read_model.workbench_relation_rows
                    where tenant_id = %s
                      and scope_key = %s
                  ) as row_count,
                  (
                    select count(*)::integer
                    from read_model.workbench_relation_groups
                    where tenant_id = %s
                      and scope_key = %s
                  ) as group_count
                """,
                (tenant_id, normalized_scope_key, tenant_id, normalized_scope_key),
            )
            self._upsert_workbench_relation_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=scope_month,
                row_count=int_value((count_row or {}).get("row_count"), len(rows_to_save)),
                group_count=int_value((count_row or {}).get("group_count"), len(groups_to_save)),
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
            order by array_position(%s::text[], row_id), scope_key
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
            scope_row = self._workbench_relation_scope_row(scope_key=scope_key, tenant_id=tenant_id)
            if scope_row is None or bool(scope_row.get("excluded_relation_mode_present")):
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
            select scope.scope_key, scope.row_count, scope.group_count,
                   scope.source_versions, scope.cache_status,
                   exists (
                       select 1
                       from read_model.workbench_relation_groups relation_group
                       where relation_group.tenant_id = scope.tenant_id
                         and relation_group.scope_key = scope.scope_key
                         and relation_group.relation_status = 'linked'
                         and relation_group.payload->>'relation_mode' = %s
                   ) as excluded_relation_mode_present
            from read_model.workbench_relation_scopes scope
            where scope.tenant_id = %s
              and scope.scope_key = %s
            """,
            (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, tenant_id, scope_key),
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

    def workbench_relation_scope_summaries(
        self,
        *,
        scope_keys: list[str],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        requested_scope_keys = _dedupe_preserve_order(
            text(scope_key)
            for scope_key in list(scope_keys or [])
        )
        all_requested = "all" in requested_scope_keys
        normalized_scope_keys = (
            self._workbench_relation_available_scope_keys(tenant_id=tenant_id)
            if all_requested
            else [scope_key for scope_key in requested_scope_keys if MONTH_SCOPE_RE.match(scope_key)]
        )
        if not normalized_scope_keys:
            return {
                "read_model_status": "fresh" if all_requested else "missing",
                "read_model_scope_keys": [],
                "read_model_scope_source_versions": {},
                "source_versions": {},
                "stale_reasons": [] if all_requested else ["month_scope_required"],
            }
        proof_rows = self._workbench_relation_scope_proof(
            scope_keys=normalized_scope_keys,
            tenant_id=tenant_id,
        )
        proof_by_scope = {
            text(row.get("scope_key")): row
            for row in proof_rows
            if isinstance(row, dict) and text(row.get("scope_key"))
        }
        statuses: list[str] = []
        stale_reasons: list[str] = []
        source_versions_by_scope: dict[str, dict[str, Any]] = {}
        for scope_key in normalized_scope_keys:
            proof = proof_by_scope.get(scope_key, {})
            dirty_status = text(proof.get("dirty_status"))
            scope_exists = bool(proof.get("scope_exists"))
            source_versions = proof.get("source_versions")
            if isinstance(source_versions, dict):
                source_versions_by_scope[scope_key] = dict(source_versions)
            if dirty_status in {"pending", "processing"}:
                statuses.append("refreshing")
                stale_reasons.append(f"{scope_key}:dirty_{dirty_status}")
            elif dirty_status == "failed":
                statuses.append("stale")
                stale_reasons.append(f"{scope_key}:dirty_failed")
            elif not scope_exists or not isinstance(source_versions, dict):
                statuses.append("missing")
                stale_reasons.append(f"{scope_key}:read_model_missing")
            elif bool(proof.get("excluded_relation_mode_present")):
                statuses.append("stale")
                stale_reasons.append(f"{scope_key}:excluded_relation_mode_present")
            else:
                statuses.append("fresh")
        status = "fresh"
        for candidate in ("refreshing", "stale", "missing"):
            if candidate in statuses:
                status = candidate
                break
        return {
            "read_model_status": status,
            "read_model_scope_keys": normalized_scope_keys,
            "read_model_scope_source_versions": source_versions_by_scope,
            "source_versions": (
                source_versions_by_scope.get(normalized_scope_keys[0], {})
                if len(normalized_scope_keys) == 1
                else {}
            ),
            "stale_reasons": stale_reasons,
        }

    def _workbench_relation_available_scope_keys(self, *, tenant_id: str) -> list[str]:
        rows = self._connection.fetch_all(
            """
            /* workbench_relation_available_scope_keys */
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from (
                select txn_month as scope_month
                from app.bank_transactions
                where txn_month is not null and status <> 'deleted'
                union
                select invoice_month as scope_month
                from app.invoices
                where invoice_month is not null and status <> 'deleted'
                union
                select date_trunc('month', application_date)::date as scope_month
                from app.oa_applications
                where application_date is not null
                  and """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
                union
                select month_scope as scope_month
                from app.workbench_pair_relations
                where month_scope is not null
                  and status = 'active'
                  and relation_mode <> %s
                union
                select scope_month
                from read_model.workbench_relation_scopes
                where tenant_id = %s and scope_month is not null
            ) scopes
            where scope_month is not null
            order by scope_key
            """,
            (TURNOVER_MANUAL_CLOSURE_RELATION_MODE, tenant_id),
        )
        return _dedupe_preserve_order(
            text(row.get("scope_key"))
            for row in rows
            if isinstance(row, dict) and MONTH_SCOPE_RE.match(text(row.get("scope_key")))
        )

    def list_active_workbench_relation_source_rows(
        self,
        *,
        row_ids: list[str],
        include_member_summaries: bool = False,
        exclude_relation_modes: list[str] | None = None,
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        _ = tenant_id
        normalized_row_ids = text_list(row_ids)
        if not normalized_row_ids:
            return []
        normalized_excluded_modes = text_list(exclude_relation_modes)
        excluded_mode_clause = ""
        params: list[Any] = [normalized_row_ids]
        if normalized_excluded_modes:
            excluded_mode_clause = "and not (relation_mode = any(%s::text[]))"
            params.append(normalized_excluded_modes)
        rows = self._connection.fetch_all(
            f"""
            select case_id, status, relation_mode, row_ids, row_types, amount_check, raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and row_ids && %s::text[]
              {excluded_mode_clause}
            order by updated_at desc, case_id
            """,
            tuple(params),
        )
        result = [dict(row) for row in rows if isinstance(row, dict)]
        if not include_member_summaries:
            return result
        summaries = self._workbench_relation_member_source_summaries(result)
        for row in result:
            row["source_summaries"] = {
                row_id: summaries[row_id]
                for row_id in text_list(row.get("row_ids"))
                if row_id in summaries
            }
        return result

    def workbench_relation_source_bundle_from_source(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        """Read relation rows and their source version from one canonical snapshot."""
        _ = tenant_id
        normalized_scope_key = text(scope_key) or ""
        normalized_row_ids = text_list(row_ids)
        if not normalized_row_ids:
            return {"rows": [], "source_versions": {}}
        month = month_start(normalized_scope_key)
        if month:
            summary_predicate = "(month_scope = %s::date or row_ids && %s::text[])"
            summary_params: list[Any] = [month, normalized_row_ids]
        else:
            summary_predicate = "row_ids && %s::text[]"
            summary_params = [normalized_row_ids]
        row = self._connection.fetch_one(
            f"""
            with selected_relations as materialized (
                select case_id, status, relation_mode, row_ids, row_types, amount_check, raw_payload, updated_at
                from app.workbench_pair_relations
                where status = 'active'
                  and row_ids && %s::text[]
            ),
            source_summary as (
                select
                    count(*)::integer as relation_count,
                    coalesce(max(updated_at)::text, '') as relation_updated_at
                from app.workbench_pair_relations
                where status = 'active'
                  and {summary_predicate}
            )
            select
                coalesce(
                    (
                        select jsonb_agg(
                            (to_jsonb(selected_relations) - 'updated_at')
                            order by updated_at desc, case_id
                        )
                        from selected_relations
                    ),
                    '[]'::jsonb
                ) as rows,
                source_summary.relation_count,
                source_summary.relation_updated_at
            from source_summary
            """,
            tuple([normalized_row_ids, *summary_params]),
        )
        payload = row if isinstance(row, dict) else {}
        rows = payload.get("rows") if isinstance(payload.get("rows"), list) else []
        return {
            "rows": [dict(item) for item in rows if isinstance(item, dict)],
            "source_versions": {
                "source": "workbench_pair_relations",
                "scope_key": normalized_scope_key,
                "relation_count": int_value(payload.get("relation_count"), 0),
                "relation_updated_at": text(payload.get("relation_updated_at")) or "",
            },
        }

    def _workbench_relation_member_source_summaries(self, rows: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        bank_ids: list[str] = []
        oa_ids: list[str] = []
        invoice_ids: list[str] = []
        for row in rows:
            row_ids = text_list(row.get("row_ids"))
            row_types = text_list(row.get("row_types"))
            for index, row_id in enumerate(row_ids):
                row_type = text(row_types[index] if index < len(row_types) else "")
                if row_type in {"bank", "bank_transaction"}:
                    bank_ids.append(row_id)
                elif row_type == "oa":
                    oa_ids.append(row_id)
                elif row_type in {"invoice", "input_invoice", "output_invoice"}:
                    invoice_ids.append(row_id)
        summaries: dict[str, dict[str, Any]] = {}
        normalized_bank_ids = text_list(bank_ids)
        if normalized_bank_ids:
            for row in self._connection.fetch_all(
                """
                select coalesce(legacy_mongo_id, id::text) as row_id, counterparty_name_raw, trade_time, txn_date,
                       amount, txn_direction, summary, remark, bank_serial_no, account_name, account_no
                from app.bank_transactions
                where status <> 'deleted'
                  and coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                """,
                (normalized_bank_ids,),
            ):
                row_id = text(row.get("row_id"))
                if not row_id:
                    continue
                summaries[row_id] = {
                    "id": row_id,
                    "amount": decimal_text(row.get("amount")),
                    "counterparty_name": text(row.get("counterparty_name_raw")),
                    "trade_time": text(row.get("trade_time") or row.get("txn_date")),
                    "txn_direction": text(row.get("txn_direction")),
                    "summary": text(row.get("summary")),
                    "remark": text(row.get("remark")),
                    "statement_serial_no": text(row.get("bank_serial_no")),
                    "account_name": text(row.get("account_name")),
                    "account_last4": text(row.get("account_no"))[-4:] if text(row.get("account_no")) else "",
                }
        normalized_oa_ids = text_list(oa_ids)
        if normalized_oa_ids:
            for row in self._connection.fetch_all(
                """
                select row_id, form_id, form_type, status, applicant, project_name, amount
                from app.oa_applications
                where row_id = any(%s::text[])
                """,
                (normalized_oa_ids,),
            ):
                row_id = text(row.get("row_id"))
                if not row_id:
                    continue
                summaries[row_id] = {
                    "id": row_id,
                    "applicant": text(row.get("applicant")),
                    "application_type": text(row.get("form_type")),
                    "project_name": text(row.get("project_name")),
                    "status": text(row.get("status")),
                    "form_no": text(row.get("form_id")),
                    "amount": decimal_text(row.get("amount")),
                    "detail_available": True,
                }
        normalized_invoice_ids = text_list(invoice_ids)
        if normalized_invoice_ids:
            for row in self._connection.fetch_all(
                """
                select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_code, invoice_no,
                       digital_invoice_no, invoice_date, seller_name, seller_tax_no, buyer_name, buyer_tax_no,
                       amount, total_with_tax
                from app.invoices
                where status <> 'deleted'
                  and coalesce(legacy_mongo_id, id::text) = any(%s::text[])
                """,
                (normalized_invoice_ids,),
            ):
                row_id = text(row.get("row_id"))
                if not row_id:
                    continue
                invoice_type = "output" if text(row.get("invoice_type")) == "output" else "input"
                summaries[row_id] = {
                    "id": row_id,
                    "invoice_no": text(row.get("invoice_no")),
                    "digital_invoice_no": text(row.get("digital_invoice_no")),
                    "invoice_code": text(row.get("invoice_code")),
                    "issue_date": text(row.get("invoice_date")),
                    "total_with_tax": decimal_text(row.get("total_with_tax") or row.get("amount")),
                    "amount": decimal_text(row.get("amount")),
                    "seller_name": text(row.get("seller_name")),
                    "seller_tax_no": text(row.get("seller_tax_no")),
                    "buyer_name": text(row.get("buyer_name")),
                    "buyer_tax_no": text(row.get("buyer_tax_no")),
                    "invoice_type": invoice_type,
                    "source_kind": "formal_invoice",
                }
        return summaries

    def workbench_relation_source_summary_from_source(
        self,
        *,
        scope_key: str,
        row_ids: list[str] | None = None,
        include_row_ids: bool = False,
        relation_modes: list[str] | None = None,
        exclude_relation_modes: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        _ = tenant_id
        normalized_scope_key = text(scope_key) or ""
        normalized_row_ids = text_list(row_ids)
        normalized_relation_modes = text_list(relation_modes)
        normalized_excluded_modes = text_list(exclude_relation_modes)
        where = ["status = 'active'"]
        params: list[Any] = []
        if relation_modes is not None:
            if not normalized_relation_modes:
                raise ValueError("relation_modes must contain at least one mode when supplied.")
            where.append("relation_mode = any(%s)")
            params.append(normalized_relation_modes)
        if normalized_excluded_modes:
            where.append("not (relation_mode = any(%s::text[]))")
            params.append(normalized_excluded_modes)
        month = month_start(normalized_scope_key)
        if month and include_row_ids and normalized_row_ids:
            where.append("(month_scope = %s::date or row_ids && %s::text[])")
            params.extend([month, normalized_row_ids])
        elif month:
            where.append("month_scope = %s::date")
            params.append(month)
        elif normalized_row_ids:
            where.append("row_ids && %s::text[]")
            params.append(normalized_row_ids)
        elif relation_modes is None:
            return {
                "source": "workbench_pair_relations",
                "scope_key": normalized_scope_key,
                "relation_count": 0,
                "relation_updated_at": "",
            }
        row = self._connection.fetch_one(
            f"""
            select
                count(*)::integer as relation_count,
                coalesce(max(updated_at)::text, '') as relation_updated_at
            from app.workbench_pair_relations
            where {' and '.join(where)}
            """,
            tuple(params),
        )
        payload = row if isinstance(row, dict) else {}
        return {
            "source": "workbench_pair_relations",
            "scope_key": normalized_scope_key,
            "relation_count": int_value(payload.get("relation_count"), 0),
            "relation_updated_at": text(payload.get("relation_updated_at")) or "",
        }

    def workbench_relation_scope_summary(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        scope_row = self._workbench_relation_scope_row(
            scope_key=text(scope_key) or "all",
            tenant_id=tenant_id,
        )
        if not isinstance(scope_row, dict) or bool(scope_row.get("excluded_relation_mode_present")):
            return None
        return dict(scope_row)

    def workbench_relation_row_id_aliases(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
    ) -> dict[str, str]:
        _ = tenant_id
        normalized_row_ids = text_list(row_ids)
        aliases = {row_id: row_id for row_id in normalized_row_ids}
        if not normalized_row_ids:
            return aliases
        rows = self._connection.fetch_all(
            """
            select id::text as storage_id,
                   legacy_mongo_id,
                   coalesce(legacy_mongo_id, id::text) as canonical_id
            from app.bank_transactions
            where id::text = any(%s::text[])
               or legacy_mongo_id = any(%s::text[])
            union all
            select id::text as storage_id,
                   legacy_mongo_id,
                   coalesce(legacy_mongo_id, id::text) as canonical_id
            from app.invoices
            where id::text = any(%s::text[])
               or legacy_mongo_id = any(%s::text[])
            """,
            (
                normalized_row_ids,
                normalized_row_ids,
                normalized_row_ids,
                normalized_row_ids,
            ),
        )
        for row in rows:
            canonical_id = text(row.get("canonical_id"))
            if not canonical_id:
                continue
            for alias in (
                text(row.get("storage_id")),
                text(row.get("legacy_mongo_id")),
                canonical_id,
            ):
                if alias:
                    aliases[alias] = canonical_id
        return aliases


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
        source_versions: dict[str, Any] = {}
        scope_source_versions: dict[str, dict[str, Any]] = {}
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
            elif bool(scope_row.get("excluded_relation_mode_present")):
                status = "stale"
                stale_reasons.append(f"excluded_relation_mode_present:{scope_key}")
            if not source_versions and isinstance(scope_row.get("source_versions"), dict):
                source_versions = dict(scope_row.get("source_versions"))
            if isinstance(scope_row.get("source_versions"), dict):
                scope_source_versions[scope_key] = dict(scope_row.get("source_versions"))
        if not source_versions:
            source_versions = (
                dict(fallback_source_versions or {})
                or _source_versions_from_relation_records(rows)
                or _source_versions_from_relation_records(groups)
            )
        return {
            "read_model_status": status,
            "rows": [_workbench_relation_row_payload(row) for row in rows],
            "groups": [_workbench_relation_group_payload(group) for group in groups],
            "source_versions": source_versions,
            "read_model_scope_source_versions": scope_source_versions,
            "read_model_scope_keys": normalized_scope_keys,
            "stale_reasons": stale_reasons,
        }

    def _workbench_relation_scope_proof(
        self,
        *,
        scope_keys: list[str],
        tenant_id: str,
    ) -> list[dict[str, Any]]:
        normalized_scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys or []))
        if not normalized_scope_keys:
            return []
        return self._connection.fetch_all(
            """
            select requested.scope_key,
                   (scope.scope_key is not null) as scope_exists,
                   scope.source_versions,
                   dirty.status as dirty_status,
                   exists (
                       select 1
                       from read_model.workbench_relation_groups relation_group
                       where relation_group.tenant_id = %s
                         and relation_group.scope_key = requested.scope_key
                         and relation_group.relation_status = 'linked'
                         and relation_group.payload->>'relation_mode' = %s
                   ) as excluded_relation_mode_present
            from unnest(%s::text[]) with ordinality as requested(scope_key, position)
            left join read_model.workbench_relation_scopes scope
              on scope.tenant_id = %s
             and scope.scope_key = requested.scope_key
            left join lateral (
                select status
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = 'workbench_relation'
                  and scope_key = requested.scope_key
                  and status in ('pending', 'processing', 'failed')
                order by updated_at desc
                limit 1
            ) dirty on true
            order by requested.position
            """,
            (
                tenant_id,
                TURNOVER_MANUAL_CLOSURE_RELATION_MODE,
                normalized_scope_keys,
                tenant_id,
                tenant_id,
            ),
        )

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


class PostgresSummaryReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

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


    def list_no_oa_bank_batch_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        return self._list_bank_batch_rows(
            filters,
            readiness_scope_type="no_oa_bank_batch",
            table_name="read_model.no_oa_bank_batch_rows",
            relation_mode_filter_enabled=True,
        )

    def _list_bank_batch_rows(
        self,
        filters: dict[str, Any] | None = None,
        *,
        readiness_scope_type: str,
        table_name: str,
        relation_mode_filter_enabled: bool,
    ) -> list[dict[str, Any]] | None:
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
        if value := text(resolved_filters.get("batch_id")):
            where.append("batch_id = %s")
            params.append(value)
        if relation_mode_filter_enabled and (value := text(resolved_filters.get("relation_mode"))):
            where.append("coalesce(nullif(payload->>'relation_mode', ''), 'no_oa_bank_batch') = %s")
            params.append(value)
        rows = self._connection.fetch_all(
            f"""
            select batch_id, source_versions, payload, raw_payload
            from {table_name}
            where {" and ".join(where)}
            order by scope_month desc nulls last, generated_at desc, batch_id
            """,
            tuple(params),
        )
        if not rows:
            return [] if self._bank_batch_readiness_is_fresh(
                readiness_scope_type,
                text(resolved_filters.get("month")),
            ) else None
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

    def no_oa_bank_batch_source_versions_summary(self, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._bank_batch_source_versions_summary(
            filters,
            readiness_scope_type="no_oa_bank_batch",
            table_name="read_model.no_oa_bank_batch_rows",
            relation_mode_filter_enabled=True,
        )

    def _bank_batch_source_versions_summary(
        self,
        filters: dict[str, Any] | None = None,
        *,
        readiness_scope_type: str,
        table_name: str,
        relation_mode_filter_enabled: bool,
    ) -> dict[str, Any] | None:
        resolved_filters = filters if isinstance(filters, dict) else {}
        where: list[str] = ["status <> 'superseded'"]
        params: list[Any] = []
        if value := text(resolved_filters.get("month")):
            where.append("scope_month = %s::date")
            params.append(month_start(value))
        if relation_mode_filter_enabled and (value := text(resolved_filters.get("relation_mode"))):
            where.append("coalesce(nullif(payload->>'relation_mode', ''), 'no_oa_bank_batch') = %s")
            params.append(value)
        row = self._connection.fetch_one(
            f"""
            select
              count(*)::bigint as row_count,
              count(distinct source_versions)::bigint as distinct_source_versions_count,
              (array_agg(source_versions order by scope_month desc nulls last, batch_id))[1] as source_versions
            from {table_name}
            where {" and ".join(where)}
            """,
            tuple(params),
        ) or {}
        normalized_month = text(resolved_filters.get("month"))
        row_count = int_value(row.get("row_count"), 0)
        if row_count <= 0:
            if not self._bank_batch_readiness_is_fresh(readiness_scope_type, normalized_month):
                return None
            return {
                "read_model_status": "fresh",
                "row_count": 0,
                "source_versions": {},
            }
        source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
        consistent = int_value(row.get("distinct_source_versions_count"), 0) == 1 and bool(source_versions)
        readiness_fresh = self._bank_batch_readiness_is_fresh(readiness_scope_type, normalized_month)
        read_model_status = "fresh" if readiness_fresh else "refreshing"
        if readiness_fresh and normalized_month and not consistent:
            read_model_status = "schema_mismatch"
        return {
            "read_model_status": read_model_status,
            "row_count": row_count,
            "source_versions": source_versions if consistent else {},
        }

    def _no_oa_bank_batch_readiness_is_fresh(self, scope_key: str | None = None) -> bool:
        return self._bank_batch_readiness_is_fresh("no_oa_bank_batch", scope_key)

    def _bank_batch_readiness_is_fresh(self, scope_type: str, scope_key: str | None = None) -> bool:
        normalized_scope_type = text(scope_type) or "no_oa_bank_batch"
        normalized_scope_key = text(scope_key)
        candidate_scope_keys = [normalized_scope_key, "all"] if normalized_scope_key else ["all"]
        refresh_statuses: dict[str, str] = {}
        if normalized_scope_key:
            refresh_statuses[normalized_scope_key] = self._refresh_status(
                scope_type=normalized_scope_type,
                scope_key=normalized_scope_key,
            )
            if refresh_statuses[normalized_scope_key] != "fresh":
                return False
        for candidate_scope_key in candidate_scope_keys:
            if not candidate_scope_key:
                continue
            refresh_status = refresh_statuses.get(candidate_scope_key)
            if refresh_status is None:
                refresh_status = self._refresh_status(
                    scope_type=normalized_scope_type,
                    scope_key=candidate_scope_key,
                )
            if refresh_status != "fresh":
                continue
            if self._bank_batch_readiness_scope_is_fresh(normalized_scope_type, candidate_scope_key):
                return True
        return False

    def _no_oa_bank_batch_readiness_scope_is_fresh(self, scope_key: str) -> bool:
        return self._bank_batch_readiness_scope_is_fresh("no_oa_bank_batch", scope_key)

    def _bank_batch_readiness_scope_is_fresh(self, scope_type: str, scope_key: str) -> bool:
        normalized_scope_type = text(scope_type) or "no_oa_bank_batch"
        row = self._connection.fetch_one(
            """
            select status
            from read_model.app_status_readiness
            where tenant_id = 'default'
              and read_model_key = %s
              and scope_type = %s
              and scope_key = %s
            limit 1
            """,
            (normalized_scope_type, normalized_scope_type, scope_key),
        )
        return isinstance(row, dict) and text(row.get("status")) == "fresh"





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



class PostgresReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._summary_read_model_repository = PostgresSummaryReadModelRepository(connection)
        self._search_workbench_relation_repository = PostgresSearchWorkbenchRelationReadModelRepository(connection)

    def list_no_oa_bank_batch_rows(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]] | None:
        return self._summary_read_model_repository.list_no_oa_bank_batch_rows(*args, **kwargs)

    def no_oa_bank_batch_source_versions_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.no_oa_bank_batch_source_versions_summary(*args, **kwargs)

    def search_index(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.search_index(*args, **kwargs)

    def search_index_scope_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.search_index_scope_summary(*args, **kwargs)

    def save_search_index_rows(self, *args: Any, **kwargs: Any) -> None:
        self._search_workbench_relation_repository.save_search_index_rows(*args, **kwargs)

    def save_workbench_relation_distribution(self, *args: Any, **kwargs: Any) -> None:
        self._search_workbench_relation_repository.save_workbench_relation_distribution(*args, **kwargs)

    def save_workbench_relation_distribution_rows(self, *args: Any, **kwargs: Any) -> None:
        self._search_workbench_relation_repository.save_workbench_relation_distribution_rows(*args, **kwargs)

    def mark_workbench_relation_scope_empty(self, *args: Any, **kwargs: Any) -> None:
        self._search_workbench_relation_repository.mark_workbench_relation_scope_empty(*args, **kwargs)

    def get_workbench_relation_rows_by_ids(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.get_workbench_relation_rows_by_ids(*args, **kwargs)

    def list_workbench_relation_rows(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.list_workbench_relation_rows(*args, **kwargs)

    def get_workbench_relation_groups_by_ids(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.get_workbench_relation_groups_by_ids(*args, **kwargs)

    def workbench_relation_source_versions(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.workbench_relation_source_versions(*args, **kwargs)

    def workbench_relation_scope_summaries(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.workbench_relation_scope_summaries(*args, **kwargs)

    def list_active_workbench_relation_source_rows(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]]:
        return self._search_workbench_relation_repository.list_active_workbench_relation_source_rows(*args, **kwargs)

    def workbench_relation_source_bundle_from_source(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.workbench_relation_source_bundle_from_source(*args, **kwargs)

    def workbench_relation_source_summary_from_source(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.workbench_relation_source_summary_from_source(*args, **kwargs)

    def workbench_relation_scope_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.workbench_relation_scope_summary(*args, **kwargs)

    def workbench_relation_row_id_aliases(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return self._search_workbench_relation_repository.workbench_relation_row_id_aliases(*args, **kwargs)







































































    @staticmethod

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

    def mark_workbench_matching_dirty_scopes(
        self,
        *,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        with self._connection.transaction() as transaction:
            return self.mark_workbench_matching_dirty_scopes_in_transaction(
                transaction=transaction,
                tenant_id=tenant_id,
                scope_months=scope_months,
                reason=reason,
                source_versions=source_versions,
                debounce_seconds=debounce_seconds,
            )

    @staticmethod
    def mark_workbench_matching_dirty_scopes_in_transaction(
        *,
        transaction: Any,
        tenant_id: str,
        scope_months: list[str],
        reason: str,
        source_versions: dict[str, object],
        debounce_seconds: int,
    ) -> list[str]:
        normalized_months = sorted({str(month)[:7] for month in scope_months if str(month or "").strip()})
        for scope_month in normalized_months:
            transaction.execute(
                    """
                    insert into job.workbench_matching_dirty_scopes(
                        tenant_id, scope_month, reason, status, available_at, source_versions, raw_payload
                    )
                    values (
                        %s, %s::date, %s, 'dirty', now() + (%s::text || ' seconds')::interval, %s, %s
                    )
                    on conflict (tenant_id, scope_month) do update set
                        reason = excluded.reason,
                        status = case
                            when job.workbench_matching_dirty_scopes.status = 'processing' then 'processing'
                            else 'dirty'
                        end,
                        available_at = case
                            when job.workbench_matching_dirty_scopes.status = 'processing'
                                then job.workbench_matching_dirty_scopes.available_at
                            when coalesce((excluded.raw_payload->>'expedite')::boolean, false)
                                then least(job.workbench_matching_dirty_scopes.available_at, excluded.available_at)
                            else greatest(job.workbench_matching_dirty_scopes.available_at, excluded.available_at)
                        end,
                        source_versions = job.workbench_matching_dirty_scopes.source_versions || excluded.source_versions,
                        raw_payload = coalesce(job.workbench_matching_dirty_scopes.raw_payload, '{}'::jsonb)
                            || excluded.raw_payload
                            || case
                                when job.workbench_matching_dirty_scopes.status = 'processing'
                                    then '{"refresh_requested_while_processing":true}'::jsonb
                                else '{}'::jsonb
                               end,
                        lease_owner = case
                            when job.workbench_matching_dirty_scopes.status = 'processing'
                                then job.workbench_matching_dirty_scopes.lease_owner
                            else null
                        end,
                        lease_expires_at = case
                            when job.workbench_matching_dirty_scopes.status = 'processing'
                                then job.workbench_matching_dirty_scopes.lease_expires_at
                            else null
                        end,
                        updated_at = now()
                    """,
                    (
                        text(tenant_id) or "default",
                        month_start(scope_month),
                        text(reason),
                        max(0, int_value(debounce_seconds, 60)),
                        jsonb(source_versions),
                        jsonb(
                            {
                                "reason": reason,
                                "source_versions": source_versions,
                                "expedite": max(0, int_value(debounce_seconds, 60)) == 0,
                            }
                        ),
                    ),
                )
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
                      and status in ('completed', 'failed')
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
                    raw_payload = coalesce(raw_payload, '{}'::jsonb) - 'refresh_requested_while_processing',
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

    def retry_failed_workbench_matching_scope(
        self,
        *,
        tenant_id: str,
        scope_month: str,
        reason: str,
        expected_attempt_count: int,
        expected_request_id: str,
        expected_last_error: str,
        expected_source_versions: dict[str, object],
    ) -> bool:
        def write(connection: Any) -> bool:
            row = connection.fetch_one(
                """
                update job.workbench_matching_dirty_scopes
                set reason = %s,
                    status = 'dirty',
                    available_at = now(),
                    lease_owner = null,
                    lease_expires_at = null,
                    raw_payload = coalesce(raw_payload, '{}'::jsonb)
                        || jsonb_build_object('reason', cast(%s as text), 'expedite', true),
                    updated_at = now()
                where tenant_id = %s
                  and scope_month = %s::date
                  and status = 'failed'
                  and attempt_count = %s
                  and coalesce(request_id, '') = %s
                  and coalesce(last_error, '') = %s
                  and coalesce(source_versions, '{}'::jsonb) = %s
                returning id
                """,
                (
                    text(reason),
                    text(reason),
                    text(tenant_id) or "default",
                    month_start(scope_month),
                    max(0, int_value(expected_attempt_count, 0)),
                    text(expected_request_id) or "",
                    text(expected_last_error) or "",
                    jsonb(expected_source_versions),
                ),
            )
            return isinstance(row, dict)

        return bool(run_in_transaction(self._connection, write))

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
                set status = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then 'dirty'
                        else 'completed'
                    end,
                    available_at = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then now()
                        else available_at
                    end,
                    completed_at = case
                        when coalesce((raw_payload->>'refresh_requested_while_processing')::boolean, false)
                            then null
                        else now()
                    end,
                    failed_at = null,
                    duration_ms = greatest(0, floor(extract(epoch from (now() - started_at)) * 1000)::integer),
                    source_versions = %s,
                    lease_owner = null,
                    lease_expires_at = null,
                    raw_payload = coalesce(raw_payload, '{}'::jsonb) - 'refresh_requested_while_processing',
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
                    raw_payload = coalesce(raw_payload, '{{}}'::jsonb) - 'refresh_requested_while_processing',
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
            row = dict(value)
            if zone in {"paired", "unpaired"}:
                row["status"] = zone
            rows.append(row)

        def scan_group(group: Any, *, zone: str | None = None) -> None:
            if not isinstance(group, dict):
                return
            for key, value in group.items():
                if str(key).endswith("_rows") and isinstance(value, list):
                    for row in value:
                        add_row(row, zone=zone)
            collapsed_rows = group.get("collapsed_rows")
            if isinstance(collapsed_rows, dict):
                for values in collapsed_rows.values():
                    if not isinstance(values, list):
                        continue
                    for row in values:
                        add_row(row, zone=zone)
            add_row(group.get("summary_row"), zone=zone)

        for direct_key in ("rows", "ignored_rows"):
            value = payload.get(direct_key)
            if isinstance(value, list):
                for row in value:
                    add_row(row)
        for section_name in ("paired", "unpaired", "ignored"):
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
        for zone in ("paired", "unpaired"):
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
                        "group_type": text(normalized_group.get("group_type")) or ("relation" if zone == "paired" else "unpaired"),
                        "source_kinds": source_kinds,
                        "row_count": _workbench_group_fact_row_counts(normalized_group)["rows"],
                        "searchable_text": _searchable_group_text(normalized_group),
                        **sort_keys,
                        "payload": normalized_group,
                    }
                )
        return groups












def _workbench_row_id(row: dict[str, Any]) -> str | None:
    return text(row.get("id") or row.get("row_id"))


def _is_workbench_summary_display_row(row: dict[str, Any], pane: str) -> bool:
    return pane == "bank" and (
        text(row.get("row_role")) == "summary"
        or text(row.get("source_kind")) in WORKBENCH_BANK_BATCH_SUMMARY_SOURCE_KINDS
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


def _normalize_workbench_group_detail_level(detail_level: str | None) -> str:
    normalized = (text(detail_level) or "full").lower()
    if normalized == "summary":
        return "summary"
    return "full"


WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT = 3


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
) -> dict[str, Any]:
    panes_to_filter = [
        pane
        for pane in WORKBENCH_PANES
        if column_filters.get(pane) or time_filters.get(pane)
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
            if not any(value == current_value for value in selected_values):
                return False

    pane_time_filter = time_filters.get(pane)
    if pane_time_filter:
        start_date, end_date = _workbench_time_filter_date_range(pane_time_filter)
        row_date = _workbench_date_from_text(_workbench_row_sort_value(row, pane))
        if start_date and end_date and (not row_date or row_date < start_date or row_date >= end_date):
            return False

    return True


def _compact_workbench_group_for_summary_page(group: dict[str, Any]) -> dict[str, Any]:
    compact = without_keys(
        dict(group),
        {
            "raw_payload",
            "payload",
            "searchable_text",
            "source_versions",
            "group_metadata",
            "oa_sort_min",
            "oa_sort_max",
            "bank_sort_min",
            "bank_sort_max",
            "invoice_sort_min",
            "invoice_sort_max",
        },
    )
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
    compact_source = _normalize_workbench_invoice_display_fields(_sanitize_workbench_row_for_read_model(row))
    compact = without_keys(
        compact_source,
        {
            "detail_fields",
            "raw_payload",
            "payload",
            "original_payload",
            "source_payload",
            "source_links",
            "source_versions",
            "artifacts",
            "evidences",
            "ocr_text",
            "full_text",
            "searchable_text",
            "object_identity",
            "object_identity_key",
            "object_identity_kind",
            "object_identity_source",
            "object_identity_confidence",
            "candidate_ids",
            "reconciliation_decision",
            "group_metadata",
        },
    )
    return compact


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
                "applicationTime": table_values.get("applicationTime") or row.get("application_time"),
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


def _sanitize_workbench_row_for_read_model(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("workbench_reconciliation_decision", None)
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
    summary_row = group.get("summary_row")
    if isinstance(summary_row, dict):
        pane = text(summary_row.get("type"))
        summary_row_id = text(summary_row.get("id") or summary_row.get("row_id"))
        already_present = any(
            existing_pane == pane
            and text(existing_row.get("id") or existing_row.get("row_id")) == summary_row_id
            for existing_pane, _role, _index, existing_row in rows
        )
        if pane in WORKBENCH_PANES and summary_row_id is not None and not already_present:
            row_index = sum(1 for existing_pane, _role, _index, _row in rows if existing_pane == pane)
            rows.append((pane, "summary", row_index, summary_row))
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




def _retry_backoff_case_sql(retry_backoff_seconds: list[int]) -> str:
    backoffs = [max(0, int_value(value, 0)) for value in retry_backoff_seconds]
    if not backoffs:
        backoffs = [0]
    clauses = " ".join(
        f"when attempt_count + 1 = {index} then {delay_seconds}"
        for index, delay_seconds in enumerate(backoffs, start=1)
    )
    return f"case {clauses} else {backoffs[-1]} end"


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






UNCATEGORIZED_CATEGORY_FILTER_CODE = "uncategorized"






















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
