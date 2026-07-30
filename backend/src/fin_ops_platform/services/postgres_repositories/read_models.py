from __future__ import annotations

import hashlib
import json
import re
from collections.abc import Mapping
from contextlib import contextmanager
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Any
from urllib.parse import unquote
from uuid import uuid4

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
from fin_ops_platform.services.workbench_read_model_version import (
    WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
    WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION,
    WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS,
    WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS,
    WorkbenchReadModelVersionConflictError,
    WorkbenchRelationPreviewSelectionError,
)
from fin_ops_platform.services.workbench_relation_modes import TURNOVER_MANUAL_CLOSURE_RELATION_MODE
MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
WORKBENCH_PANES = ("oa", "bank", "invoice")
WORKBENCH_FILTER_PLACEHOLDERS = {"", "--", "—"}
WORKBENCH_COMPACT_BANK_NAMES = {
    "中国工商银行": "工行",
    "工商银行": "工行",
    "中国建设银行": "建行",
    "建设银行": "建行",
    "中国农业银行": "农行",
    "农业银行": "农行",
    "中国银行": "中行",
    "招商银行": "招行",
    "交通银行": "交行",
    "中国光大银行": "光大",
    "光大银行": "光大",
    "中国民生银行": "民生",
    "民生银行": "民生",
    "平安银行": "平安",
}
WORKBENCH_INVOICE_SOURCE_LABELS = {
    "etc_invoice_summary": "ETC批次",
    "etc_invoice": "ETC",
    "oa_attachment_invoice": "OA附件",
    "oa_attachment_payment_receipt": "付款凭证",
    "oa_attachment_unknown": "未识别附件",
}
WORKBENCH_ROW_PAYLOAD_PRUNED_KEYS = {"object_identity"}
WORKBENCH_GROUP_MEMBER_PAYLOAD_KEYS = {
    "rows",
    "oa_rows",
    "bank_rows",
    "invoice_rows",
    "collapsed_rows",
}
OA_ATTACHMENT_NON_INVOICE_EVIDENCE_SOURCE_KINDS = {
    "oa_attachment_payment_receipt",
    "oa_attachment_unknown",
}
BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND = "bank_flow_rule_batch_summary"
WORKBENCH_BANK_BATCH_SUMMARY_SOURCE_KINDS = frozenset(
    {BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND}
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


def _write_workbench_generation_rows(
    connection: Any,
    *,
    copy_sql: str,
    insert_sql: str,
    params_seq: list[tuple[Any, ...]],
    generated_at_index: int,
) -> int:
    copy_rows = getattr(connection, "copy_rows", None)
    if callable(copy_rows) and all(
        len(params) > generated_at_index and params[generated_at_index] not in (None, "")
        for params in params_seq
    ):
        return int(copy_rows(copy_sql, params_seq) or 0)
    return _execute_many(connection, insert_sql, params_seq)



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
        self._workbench_generation_consistency_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
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
    def _workbench_active_month_generation_version(executor: Any) -> dict[str, Any]:
        rows = executor.fetch_all(
            """
            select
                scope_key,
                generation_id,
                source_versions,
                coalesce(activated_at, completed_at, updated_at)::text as generated_at
            from read_model.workbench_generations
            where tenant_id = 'default'
              and status = 'active'
              and scope_key <> 'all'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key, generation_id
            """,
        )
        return PostgresReadModelRepository._workbench_active_month_generation_version_from_rows(rows)

    @staticmethod
    def _workbench_active_month_generation_version_from_rows(rows: list[dict[str, Any]]) -> dict[str, Any]:
        generation_set = [
            {
                "scope_key": text(row.get("scope_key")),
                "generation_id": text(row.get("generation_id")),
                "source_versions": (
                    row.get("source_versions")
                    if isinstance(row.get("source_versions"), dict)
                    else row.get("generation_source_versions")
                    if isinstance(row.get("generation_source_versions"), dict)
                    else {}
                ),
            }
            for row in rows
            if isinstance(row, dict) and text(row.get("scope_key")) and text(row.get("generation_id"))
        ]
        if not generation_set:
            return {}
        generation_set.sort(key=lambda item: (str(item["scope_key"]), str(item["generation_id"])))
        digest = hashlib.sha256(
            json.dumps(generation_set, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()
        generated_at = max((text(row.get("generated_at")) or "" for row in rows if isinstance(row, dict)), default="")
        return {
            "scope_count": len(generation_set),
            "generation_set": generation_set,
            "generated_at": generated_at,
            "version": f"workbench:all:active-generation-set:{digest}",
        }

    def _workbench_all_composed_generation_metadata(self) -> dict[str, Any]:
        active_month_version = self._workbench_active_month_generation_version(self._connection)
        active_generation_id = text(active_month_version.get("version"))
        if not active_generation_id:
            return {}
        source_versions = self._workbench_all_active_source_versions()
        generated_at = text(active_month_version.get("generated_at"))
        return {
            "active_generation_id": active_generation_id,
            "building_generation_id": None,
            "failed_generation_id": None,
            "read_model_version": active_generation_id,
            "generated_at": generated_at,
            "generation_last_error": None,
            "failed_generation_is_relevant": False,
            "generations": [
                {
                    "generation_id": active_generation_id,
                    "status": "active",
                    "source_versions": source_versions,
                    "activated_at": generated_at,
                    "completed_at": generated_at,
                    "updated_at": generated_at,
                }
            ],
        }

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
                      and gr.zone in ('paired', 'unpaired')
                    group by gr.generation_id, gr.scope_key, gr.pane, gr.object_identity_key, gr.object_identity_kind
                    having bool_or(gr.zone = 'paired') and bool_or(gr.zone = 'unpaired')
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
                      and gr.zone in ('paired', 'unpaired')
                    group by gr.generation_id, gr.scope_key, gr.pane, gr.row_id
                    having count(distinct gr.zone || ':' || gr.group_id) > 1
                ) duplicate_rows
                group by duplicate_rows.generation_id, duplicate_rows.scope_key
            ),
            active_relation_unpaired_membership_counts as (
                select
                    active_rows.generation_id,
                    active_rows.scope_key,
                    count(*)::bigint as active_relation_unpaired_membership_count,
                    jsonb_agg(
                        jsonb_build_object(
                            'case_id', active_rows.case_id,
                            'pane', active_rows.pane,
                            'row_id', active_rows.row_id,
                            'group_id', active_rows.group_id
                        )
                        order by active_rows.case_id, active_rows.pane, active_rows.row_id
                    ) as active_relation_unpaired_membership_samples
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
                    join read_model.workbench_groups grp
                      on grp.generation_id = gr.generation_id
                     and grp.scope_key = gr.scope_key
                     and grp.zone = gr.zone
                     and grp.group_id = gr.group_id
                    join app.workbench_pair_relations rel
                      on rel.status = 'active'
                     and gr.row_id = any(rel.row_ids)
                    where coalesce(gr.row_role, '') <> 'summary'
                      and gr.zone = 'unpaired'
                      and gr.row_id is not null
                      and coalesce(grp.payload #>> '{{completion,is_complete}}', 'true') <> 'false'
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
                coalesce(active_relation_unpaired_membership_counts.active_relation_unpaired_membership_count, 0)::bigint
                    as active_relation_unpaired_membership_count,
                coalesce(active_relation_unpaired_membership_counts.active_relation_unpaired_membership_samples, '[]'::jsonb)
                    as active_relation_unpaired_membership_samples
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
            left join active_relation_unpaired_membership_counts
              on active_relation_unpaired_membership_counts.generation_id = gen.generation_id
             and active_relation_unpaired_membership_counts.scope_key = gen.scope_key
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
            active_relation_unpaired_membership_count = int_value(row.get("active_relation_unpaired_membership_count"), 0)
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
            if active_relation_unpaired_membership_count:
                reasons.append(f"active_relation_unpaired_membership count={active_relation_unpaired_membership_count}")
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
                        "active_relation_unpaired_membership_count": active_relation_unpaired_membership_count,
                        "active_relation_unpaired_membership_samples": row.get("active_relation_unpaired_membership_samples")
                        if isinstance(row.get("active_relation_unpaired_membership_samples"), list)
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
    def _workbench_all_scope_parent_stale_failures(
        executor: Any,
        *,
        scope_key: str,
    ) -> list[dict[str, Any]]:
        return []

    @staticmethod
    def _lock_workbench_generation_set(connection: Any) -> None:
        connection.execute(
            "select pg_advisory_xact_lock(hashtext(%s))",
            ("workbench_generation_set",),
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

    def _load_workbench_groups_payload(
        self,
        *,
        scope_key: str,
        generation_id: str | None,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        result = dict(payload)
        result.setdefault("paired", {"groups": []})
        result.setdefault("unpaired", {"groups": []})
        if not generation_id:
            return result
        rows = self._connection.fetch_all(
            """
            select scope_key, generation_id, zone, group_id, payload, raw_payload
            from read_model.workbench_groups
            where scope_key = %s
              and generation_id = %s
            order by
              case when zone = 'paired' then 0 else 1 end,
              coalesce(oa_sort_max, bank_sort_max, invoice_sort_max) desc nulls last,
              group_id
            """,
            (scope_key, generation_id),
        )
        materialized_rows = self._materialize_workbench_group_payloads(rows)
        grouped: dict[str, list[dict[str, Any]]] = {"paired": [], "unpaired": []}
        for row, group_payload in zip(rows, materialized_rows, strict=False):
            zone = text(row.get("zone")) or "unpaired"
            if zone not in grouped:
                continue
            if isinstance(group_payload, dict):
                grouped[zone].append(group_payload)
        result["paired"] = {"groups": grouped["paired"]}
        result["unpaired"] = {"groups": grouped["unpaired"]}
        return result

    def _materialize_workbench_group_payloads(self, rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        groups: list[dict[str, Any]] = []
        materialized_keys: list[tuple[str, str, str, str]] = []
        all_scope_keys: list[tuple[str, str]] = []
        for row in rows:
            group = _read_model_payload(row)
            if not isinstance(group, dict):
                group = {}
            display_group_id = text(row.get("group_id"))
            if display_group_id:
                group["group_id"] = display_group_id
                group["id"] = display_group_id
            group.setdefault("zone", text(row.get("zone")) or "unpaired")
            scope_key = text(row.get("scope_key"))
            generation_id = text(row.get("generation_id"))
            zone = text(row.get("zone")) or text(group.get("zone")) or "unpaired"
            group_id = text(row.get("source_group_id")) or display_group_id or text(group.get("group_id"))
            if (
                _workbench_group_payload_requires_row_materialization(group)
                and scope_key
                and generation_id
                and group_id
            ):
                if text(row.get("source_group_id")):
                    all_scope_keys.append((zone, group_id))
                else:
                    materialized_keys.append((scope_key, generation_id, zone, group_id))
            groups.append(group)
        if not materialized_keys and not all_scope_keys:
            return groups

        member_rows: list[dict[str, Any]] = []
        if materialized_keys:
            member_rows.extend(self._connection.fetch_all(
                """
            with target_groups as (
                select *
                from unnest(%s::text[], %s::text[], %s::text[], %s::text[])
                  as target(scope_key, generation_id, zone, group_id)
            )
            select
                gr.scope_key,
                gr.generation_id,
                gr.zone,
                gr.group_id,
                gr.pane,
                gr.row_id,
                gr.row_role,
                gr.row_index,
                gr.source_kind,
                gr.status,
                gr.time_value,
                gr.time_date::text as time_date,
                gr.column_values,
                gr.searchable_text,
                gr.object_identity_key,
                gr.object_identity_kind,
                gr.object_identity_source,
                gr.object_identity_confidence,
                wr.payload as row_payload,
                wr.raw_payload as row_raw_payload,
                gr.payload as member_payload,
                gr.raw_payload as member_raw_payload
            from target_groups target
            join read_model.workbench_group_rows gr
              on gr.scope_key = target.scope_key
             and gr.generation_id = target.generation_id
             and gr.zone = target.zone
             and gr.group_id = target.group_id
            left join read_model.workbench_rows wr
              on wr.scope_key = gr.scope_key
             and wr.generation_id = gr.generation_id
             and wr.row_id = gr.row_id
            order by
                gr.scope_key,
                gr.generation_id,
                gr.zone,
                gr.group_id,
                case gr.pane when 'oa' then 0 when 'bank' then 1 when 'invoice' then 2 else 3 end,
                gr.row_role,
                gr.row_index,
                gr.row_id
            """,
                (
                    [key[0] for key in materialized_keys],
                    [key[1] for key in materialized_keys],
                    [key[2] for key in materialized_keys],
                    [key[3] for key in materialized_keys],
                ),
            ))
        if all_scope_keys:
            member_rows.extend(self._connection.fetch_all(
                """
                with target_groups as (
                    select *
                    from unnest(%s::text[], %s::text[]) as target(zone, logical_group_id)
                ), physical_groups as (
                    select
                        g.*,
                        case
                            when left(g.group_id, 5) = 'case:' or left(g.group_id, 9) = 'unpaired:'
                                then g.group_id
                            else 'scope:' || g.scope_key || ':' || g.group_id
                        end as logical_group_id
                    from read_model.workbench_groups g
                    join read_model.workbench_generations gen
                      on gen.tenant_id = 'default'
                     and gen.scope_key = g.scope_key
                     and gen.generation_id = g.generation_id
                     and gen.status = 'active'
                    where g.scope_key <> 'all'
                ), ranked_members as (
                    select
                        target.logical_group_id,
                        gr.*,
                        wr.payload as row_payload,
                        wr.raw_payload as row_raw_payload,
                        row_number() over (
                            partition by
                                target.zone,
                                target.logical_group_id,
                                gr.pane,
                                case
                                    when coalesce(gr.row_role, '') = 'summary' then 'summary:' || gr.row_id
                                    else coalesce(nullif(gr.object_identity_key, ''), gr.row_id)
                                end
                            order by gr.scope_month desc nulls last, gr.updated_at desc, gr.row_id
                        ) as member_rank
                    from target_groups target
                    join physical_groups pg
                      on pg.zone = target.zone
                     and pg.logical_group_id = target.logical_group_id
                    join read_model.workbench_group_rows gr
                      on gr.scope_key = pg.scope_key
                     and gr.generation_id = pg.generation_id
                     and gr.zone = pg.zone
                     and gr.group_id = pg.group_id
                    left join read_model.workbench_rows wr
                      on wr.scope_key = gr.scope_key
                     and wr.generation_id = gr.generation_id
                     and wr.row_id = gr.row_id
                )
                select
                    'all' as scope_key,
                    'all-active-shards' as generation_id,
                    zone,
                    logical_group_id as group_id,
                    pane,
                    row_id,
                    row_role,
                    row_index,
                    source_kind,
                    status,
                    time_value,
                    time_date::text as time_date,
                    column_values,
                    searchable_text,
                    object_identity_key,
                    object_identity_kind,
                    object_identity_source,
                    object_identity_confidence,
                    row_payload,
                    row_raw_payload,
                    payload as member_payload,
                    raw_payload as member_raw_payload
                from ranked_members
                where member_rank = 1
                order by
                    zone,
                    logical_group_id,
                    case pane when 'oa' then 0 when 'bank' then 1 when 'invoice' then 2 else 3 end,
                    row_role,
                    row_index,
                    row_id
                """,
                (
                    [key[0] for key in all_scope_keys],
                    [key[1] for key in all_scope_keys],
                ),
            ))
        rows_by_group: dict[tuple[str, str, str, str], list[dict[str, Any]]] = {}
        for row in member_rows:
            key = (
                text(row.get("scope_key")) or "",
                text(row.get("generation_id")) or "",
                text(row.get("zone")) or "unpaired",
                text(row.get("group_id")) or "",
            )
            rows_by_group.setdefault(key, []).append(row)

        materialized: list[dict[str, Any]] = []
        for row, group in zip(rows, groups, strict=False):
            if text(row.get("source_group_id")):
                key = (
                    "all",
                    "all-active-shards",
                    text(row.get("zone")) or text(group.get("zone")) or "unpaired",
                    text(row.get("source_group_id")) or text(row.get("group_id")) or "",
                )
            else:
                key = (
                    text(row.get("scope_key")) or "",
                    text(row.get("generation_id")) or "",
                    text(row.get("zone")) or text(group.get("zone")) or "unpaired",
                    text(row.get("group_id")) or text(group.get("group_id")) or "",
                )
            materialized.append(_materialize_workbench_group_payload(group, rows_by_group.get(key, [])))
        return materialized

    def _workbench_active_month_summary_rows(self) -> list[dict[str, Any]]:
        return list(self._connection.fetch_all(
            """
            select
                gen.scope_key,
                gen.generation_id,
                gen.source_versions as generation_source_versions,
                coalesce(s.generated_at, gen.activated_at, gen.completed_at, gen.updated_at)::text as generated_at,
                s.payload,
                s.raw_payload
            from read_model.workbench_generations gen
            left join read_model.workbench_summary s
              on s.scope_key = gen.scope_key
             and s.generation_id = gen.generation_id
            where gen.tenant_id = 'default'
              and gen.status = 'active'
              and gen.scope_key <> 'all'
              and gen.scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by gen.scope_key desc
            """,
        ))

    def _get_workbench_all_summary_from_active_month_shards(self) -> dict[str, Any] | None:
        rows = self._workbench_active_month_summary_rows()
        if not rows:
            return None
        summary = self._get_workbench_all_canonical_summary_counts()
        read_model_status = self._workbench_summary_read_model_status(scope_key="all")
        active_month_version = self._workbench_active_month_generation_version_from_rows(rows)
        return self._compose_workbench_all_summary_payload(
            rows=rows,
            summary=summary,
            read_model_status=read_model_status,
            active_month_version=active_month_version,
        )

    @staticmethod
    def _compose_workbench_all_summary_payload(
        *,
        rows: list[dict[str, Any]],
        summary: dict[str, Any],
        read_model_status: str,
        active_month_version: dict[str, Any],
    ) -> dict[str, Any]:
        invoice_inventory: dict[str, int] = {}
        generated_at = ""
        complete_summary_count = 0
        source_version_rows: list[dict[str, Any]] = []
        for row in rows:
            source_versions = row.get("generation_source_versions")
            if isinstance(source_versions, dict):
                source_version_rows.append({"source_versions": source_versions})
            payload = _read_model_payload(row)
            if not isinstance(payload, dict) or not isinstance(payload.get("summary"), dict):
                continue
            complete_summary_count += 1
            inventory = payload.get("invoice_inventory")
            if isinstance(inventory, dict):
                for key, value in inventory.items():
                    invoice_inventory[str(key)] = invoice_inventory.get(str(key), 0) + int_value(value, 0)
            row_generated_at = text(row.get("generated_at")) or ""
            if row_generated_at > generated_at:
                generated_at = row_generated_at
        if complete_summary_count < len(rows):
            read_model_status = "stale"
        statistics = summary.get("statistics") if isinstance(summary.get("statistics"), dict) else None
        return {
            "month": "all",
            "scope_key": "all",
            "summary": _normalize_workbench_summary_counts(summary),
            "statistics": dict(statistics) if read_model_status == "fresh" and statistics is not None else None,
            "invoice_inventory": invoice_inventory,
            "read_model_status": read_model_status,
            "generated_at": generated_at,
            "source_versions": _workbench_composed_all_source_versions(source_version_rows),
            "active_generation_id": active_month_version.get("version"),
            "read_model_version": active_month_version.get("version"),
        }

    def _get_workbench_default_all_initial_group_pages(
        self,
        *,
        summary: dict[str, Any],
        read_model_status: str,
        read_model_version: str,
        source_versions: dict[str, Any],
    ) -> dict[str, dict[str, Any]]:
        canonical_groups_sql = _workbench_active_month_groups_sql(include_aggregated_metadata=False)
        rows = self._connection.fetch_all(
            f"""
            select
                ranked.group_id,
                ranked.source_group_id,
                ranked.zone,
                ranked.payload,
                ranked.raw_payload,
                ranked.scope_key,
                ranked.generation_id,
                ranked.zone_rank
            from (
                select
                    g.*,
                    row_number() over (
                        partition by g.zone
                        order by g.scope_month desc nulls last, g.updated_at desc, g.group_id
                    ) as zone_rank
                from {canonical_groups_sql}
                where g.zone in ('paired', 'unpaired')
            ) ranked
            where ranked.zone_rank <= 51
            order by
                case when ranked.zone = 'paired' then 0 else 1 end,
                ranked.zone_rank
            """,
        )
        rows_by_zone: dict[str, list[dict[str, Any]]] = {"paired": [], "unpaired": []}
        for row in rows:
            zone = text(row.get("zone"))
            if zone in rows_by_zone:
                rows_by_zone[zone].append(row)
        visible_rows = [
            row
            for zone in ("paired", "unpaired")
            for row in rows_by_zone[zone][:50]
        ]
        materialized_rows = self._materialize_workbench_group_payloads(visible_rows)
        groups_by_zone: dict[str, list[dict[str, Any]]] = {"paired": [], "unpaired": []}
        for row, materialized_group in zip(visible_rows, materialized_rows, strict=False):
            zone = text(row.get("zone"))
            if zone not in groups_by_zone:
                continue
            group = materialized_group if isinstance(materialized_group, dict) else {
                "group_id": text(row.get("group_id"))
            }
            group = _with_workbench_group_counts(_sanitize_workbench_group_invoice_rows(group))
            groups_by_zone[zone].append(_compact_workbench_group_for_summary_page(group))

        summary_zone_counts = summary.get("zone_counts") if isinstance(summary.get("zone_counts"), dict) else {}
        pages: dict[str, dict[str, Any]] = {}
        for zone in ("paired", "unpaired"):
            counts = summary_zone_counts.get(zone) if isinstance(summary_zone_counts.get(zone), dict) else {}
            pages[zone] = {
                "month": "all",
                "scope_key": "all",
                "zone": zone,
                "page": 1,
                "page_size": 50,
                "detail_level": "summary",
                "total": int_value(counts.get("groups"), 0),
                "row_counts": _normalize_workbench_row_counts(counts, _empty_workbench_row_counts()),
                "has_more": len(rows_by_zone[zone]) > 50,
                "groups": groups_by_zone[zone],
                "read_model_status": read_model_status,
                "source_versions": source_versions,
                "active_generation_id": read_model_version,
                "read_model_version": read_model_version,
            }
        return pages

    def _get_workbench_all_canonical_summary_counts(self) -> dict[str, Any]:
        canonical_groups_sql = _workbench_active_month_groups_sql(include_aggregated_metadata=False)
        physical_group_id_sql = _workbench_all_logical_group_id_sql("physical_group.group_id", "physical_group.scope_key")
        row = self._connection.fetch_one(
            f"""
            with canonical_groups as (
                select group_id, zone, payload
                from {canonical_groups_sql}
            ), physical_groups as (
                select
                    physical_group.scope_key,
                    physical_group.generation_id,
                    physical_group.zone,
                    physical_group.group_id,
                    {physical_group_id_sql} as logical_group_id
                from read_model.workbench_groups physical_group
                join read_model.workbench_generations physical_generation
                  on physical_generation.tenant_id = 'default'
                 and physical_generation.scope_key = physical_group.scope_key
                 and physical_generation.generation_id = physical_group.generation_id
                 and physical_generation.status = 'active'
                where physical_group.scope_key <> 'all'
            ), canonical_members as (
                select distinct
                    canonical_groups.zone,
                    canonical_groups.group_id,
                    member.pane,
                    coalesce(nullif(member.object_identity_key, ''), member.row_id) as object_identity_key,
                    member.column_values
                from canonical_groups
                join physical_groups
                  on physical_groups.logical_group_id = canonical_groups.group_id
                 and physical_groups.zone = canonical_groups.zone
                join read_model.workbench_group_rows member
                  on member.scope_key = physical_groups.scope_key
                 and member.generation_id = physical_groups.generation_id
                 and member.zone = physical_groups.zone
                 and member.group_id = physical_groups.group_id
                where coalesce(member.row_role, '') <> 'summary'
            )
            select
                count(distinct canonical_groups.group_id) filter (
                    where canonical_groups.zone = 'paired'
                )::bigint as paired_count,
                count(distinct canonical_groups.group_id) filter (
                    where canonical_groups.zone = 'unpaired'
                )::bigint as unpaired_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'oa'
                )::bigint as oa_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'bank'
                )::bigint as bank_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'invoice'
                )::bigint as invoice_count,
                count(distinct canonical_groups.group_id) filter (
                    where canonical_groups.zone = 'unpaired'
                      and (
                        coalesce(canonical_groups.payload->>'match_confidence', '') = 'danger'
                        or jsonb_path_exists(
                            coalesce(canonical_groups.payload, '{{}}'::jsonb),
                            '$.** ? (@.tone == "danger")'
                        )
                      )
                )::bigint as exception_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'paired' and canonical_members.pane = 'oa'
                )::bigint as paired_oa_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'paired' and canonical_members.pane = 'bank'
                )::bigint as paired_bank_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'paired' and canonical_members.pane = 'invoice'
                )::bigint as paired_invoice_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'unpaired' and canonical_members.pane = 'oa'
                )::bigint as unpaired_oa_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'unpaired' and canonical_members.pane = 'bank'
                )::bigint as unpaired_bank_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.zone = 'unpaired' and canonical_members.pane = 'invoice'
                )::bigint as unpaired_invoice_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'bank'
                      and lower(coalesce(canonical_members.column_values->>'direction', '')) in ('支出', 'expense', 'outflow')
                )::bigint as expense_transaction_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'bank'
                      and lower(coalesce(canonical_members.column_values->>'direction', '')) in ('收入', 'income', 'inflow')
                )::bigint as income_transaction_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'invoice'
                      and (
                          lower(coalesce(canonical_members.column_values->>'invoiceType', '')) like '%%input%%'
                          or lower(coalesce(canonical_members.column_values->>'invoiceType', '')) like '%%purchase%%'
                          or coalesce(canonical_members.column_values->>'invoiceType', '') like '%%进%%'
                      )
                )::bigint as input_invoice_count,
                count(distinct (canonical_members.pane, canonical_members.object_identity_key)) filter (
                    where canonical_members.pane = 'invoice'
                      and (
                          lower(coalesce(canonical_members.column_values->>'invoiceType', '')) like '%%output%%'
                          or lower(coalesce(canonical_members.column_values->>'invoiceType', '')) like '%%sale%%'
                          or coalesce(canonical_members.column_values->>'invoiceType', '') like '%%销%%'
                      )
                )::bigint as output_invoice_count,
                count(distinct canonical_groups.group_id) filter (
                    where coalesce(canonical_groups.payload #>> '{{completion,is_complete}}', 'true') = 'false'
                )::bigint as incomplete_group_count,
                count(distinct canonical_groups.group_id) filter (
                    where exists (
                        select 1
                        from jsonb_array_elements_text(
                            case
                                when jsonb_typeof(canonical_groups.payload #> '{{completion,missing_row_types}}') = 'array'
                                then canonical_groups.payload #> '{{completion,missing_row_types}}'
                                else '[]'::jsonb
                            end
                        ) missing(value)
                        where lower(missing.value) = 'oa'
                    )
                )::bigint as missing_oa_group_count,
                count(distinct canonical_groups.group_id) filter (
                    where exists (
                        select 1
                        from jsonb_array_elements_text(
                            case
                                when jsonb_typeof(canonical_groups.payload #> '{{completion,missing_row_types}}') = 'array'
                                then canonical_groups.payload #> '{{completion,missing_row_types}}'
                                else '[]'::jsonb
                            end
                        ) missing(value)
                        where lower(missing.value) in ('bank', 'bank_transaction')
                    )
                )::bigint as missing_bank_group_count,
                count(distinct canonical_groups.group_id) filter (
                    where exists (
                        select 1
                        from jsonb_array_elements_text(
                            case
                                when jsonb_typeof(canonical_groups.payload #> '{{completion,missing_row_types}}') = 'array'
                                then canonical_groups.payload #> '{{completion,missing_row_types}}'
                                else '[]'::jsonb
                            end
                        ) missing(value)
                        where lower(missing.value) = 'invoice'
                    )
                )::bigint as missing_invoice_group_count
            from canonical_groups
            left join canonical_members
              on canonical_members.zone = canonical_groups.zone
             and canonical_members.group_id = canonical_groups.group_id
            """,
        )
        if not isinstance(row, dict):
            raise RuntimeError("Workbench all-scope canonical summary query returned no result.")

        zone_counts = _empty_workbench_zone_counts()
        for zone in ("paired", "unpaired"):
            target = zone_counts[zone]
            target["groups"] = int_value(row.get(f"{zone}_count"), 0)
            for pane in WORKBENCH_PANES:
                target[pane] = int_value(row.get(f"{zone}_{pane}_count"), 0)
            target["rows"] = target["oa"] + target["bank"] + target["invoice"]
        oa_count = int_value(row.get("oa_count"), 0)
        bank_count = int_value(row.get("bank_count"), 0)
        invoice_count = int_value(row.get("invoice_count"), 0)
        paired_count = int_value(row.get("paired_count"), 0)
        unpaired_object_count = sum(
            int_value(row.get(f"unpaired_{pane}_count"), 0) for pane in WORKBENCH_PANES
        )
        return {
            "oa_count": oa_count,
            "bank_count": bank_count,
            "invoice_count": invoice_count,
            "paired_count": paired_count,
            "unpaired_count": int_value(row.get("unpaired_count"), 0),
            "exception_count": int_value(row.get("exception_count"), 0),
            "zone_counts": zone_counts,
            "statistics": {
                "oa_count": oa_count,
                "bank_transaction_count": bank_count,
                "input_invoice_count": int_value(row.get("input_invoice_count"), 0),
                "output_invoice_count": int_value(row.get("output_invoice_count"), 0),
                "paired_group_count": paired_count,
                "unpaired_object_count": unpaired_object_count,
                "expense_transaction_count": int_value(row.get("expense_transaction_count"), 0),
                "income_transaction_count": int_value(row.get("income_transaction_count"), 0),
                "paired_oa_count": int_value(row.get("paired_oa_count"), 0),
                "paired_bank_transaction_count": int_value(row.get("paired_bank_count"), 0),
                "paired_invoice_count": int_value(row.get("paired_invoice_count"), 0),
                "incomplete_group_count": int_value(row.get("incomplete_group_count"), 0),
                "missing_oa_group_count": int_value(row.get("missing_oa_group_count"), 0),
                "missing_bank_group_count": int_value(row.get("missing_bank_group_count"), 0),
                "missing_invoice_group_count": int_value(row.get("missing_invoice_group_count"), 0),
            },
        }

    def _workbench_all_active_source_versions(self) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select source_versions
            from read_model.workbench_generations
            where tenant_id = 'default'
              and status = 'active'
              and scope_key <> 'all'
              and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            order by scope_key desc
            """,
        )
        return _workbench_composed_all_source_versions(
            [row for row in rows if isinstance(row, dict)]
        )

    def get_workbench_initial_page(
        self,
        *,
        scope_key: str,
        paired_query: dict[str, Any] | None = None,
        unpaired_query: dict[str, Any] | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            raise RuntimeError("Workbench initial page requires PostgreSQL transaction support.")

        def page_query(value: dict[str, Any] | None) -> dict[str, Any]:
            source = value if isinstance(value, dict) else {}
            return {
                key: source.get(key)
                for key in (
                    "status",
                    "source_kind",
                    "search",
                    "sort",
                    "column_filters",
                    "time_filters",
                )
                if key in source
            }

        with transaction_factory() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            transaction.execute("set local statement_timeout = '2s'")
            snapshot_repository = PostgresReadModelRepository(transaction)
            paired_page_query = page_query(paired_query)
            unpaired_page_query = page_query(unpaired_query)
            if normalized_scope_key == "all" and not paired_page_query and not unpaired_page_query:
                summary_rows = snapshot_repository._workbench_active_month_summary_rows()
                if not summary_rows:
                    return None
                active_month_version = snapshot_repository._workbench_active_month_generation_version_from_rows(
                    summary_rows
                )
                read_model_version = text(active_month_version.get("version"))
                if not read_model_version:
                    return None
                summary = snapshot_repository._get_workbench_all_canonical_summary_counts()
                read_model_status = snapshot_repository._workbench_summary_read_model_status(scope_key="all")
                summary_payload = snapshot_repository._compose_workbench_all_summary_payload(
                    rows=summary_rows,
                    summary=summary,
                    read_model_status=read_model_status,
                    active_month_version=active_month_version,
                )
                initial_pages = snapshot_repository._get_workbench_default_all_initial_group_pages(
                    summary=dict(summary_payload.get("summary") or {}),
                    read_model_status=text(summary_payload.get("read_model_status")) or "fresh",
                    read_model_version=read_model_version,
                    source_versions=dict(summary_payload.get("source_versions") or {}),
                )
                paired_page = initial_pages["paired"]
                unpaired_page = initial_pages["unpaired"]
            else:
                summary_payload = snapshot_repository.get_workbench_summary(scope_key=normalized_scope_key)
                if not isinstance(summary_payload, dict):
                    return None
                paired_page = snapshot_repository.get_workbench_groups_page(
                    scope_key=normalized_scope_key,
                    zone="paired",
                    page=1,
                    page_size=50,
                    detail_level="summary",
                    **paired_page_query,
                )
                unpaired_page = snapshot_repository.get_workbench_groups_page(
                    scope_key=normalized_scope_key,
                    zone="unpaired",
                    page=1,
                    page_size=50,
                    detail_level="summary",
                    **unpaired_page_query,
                )
            if not all(isinstance(payload, dict) for payload in (summary_payload, paired_page, unpaired_page)):
                return None

            versions = [
                text(payload.get("read_model_version") or payload.get("active_generation_id"))
                for payload in (summary_payload, paired_page, unpaired_page)
            ]
            if any(version is None for version in versions) or len(set(versions)) != 1:
                raise RuntimeError("Workbench initial page components resolved different read model versions.")
            read_model_version = versions[0]
            status_values = {
                text(payload.get("read_model_status")) or "fresh"
                for payload in (summary_payload, paired_page, unpaired_page)
            }
            read_model_status = next(
                (status for status in ("failed", "refreshing", "stale", "fresh") if status in status_values),
                "fresh",
            )
            statistics = summary_payload.get("statistics")
            if read_model_status != "fresh" or not isinstance(statistics, dict):
                statistics = None
            return {
                "month": normalized_scope_key,
                "scope_key": normalized_scope_key,
                "summary": dict(summary_payload.get("summary") or {}),
                "statistics": dict(statistics) if isinstance(statistics, dict) else None,
                "invoice_inventory": dict(summary_payload.get("invoice_inventory") or {}),
                "paired": paired_page,
                "unpaired": unpaired_page,
                "read_model_status": read_model_status,
                "generated_at": summary_payload.get("generated_at"),
                "source_versions": dict(summary_payload.get("source_versions") or {}),
                "active_generation_id": read_model_version,
                "read_model_version": read_model_version,
            }

    def get_workbench_summary(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        if normalized_scope_key == "all":
            active_month_summary = self._get_workbench_all_summary_from_active_month_shards()
            if active_month_summary is not None:
                return active_month_summary
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
                    return None
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
                if normalized_scope_key == "all":
                    statistics = result.get("summary", {}).get("statistics")
                elif result["read_model_status"] == "fresh":
                    all_summary = self._get_workbench_all_canonical_summary_counts()
                    statistics = all_summary.get("statistics")
                else:
                    statistics = None
                result["statistics"] = (
                    dict(statistics)
                    if result["read_model_status"] == "fresh" and isinstance(statistics, dict)
                    else None
                )
                result.pop("diagnostics", None)
                return result

        return None

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
        if self._workbench_all_scope_parent_stale_failures(
            self._connection,
            scope_key=normalized_scope_key,
        ):
            return "stale"
        return "fresh"

    def _workbench_groups_schema_status(self, *, scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        if normalized_scope_key == "all":
            return "fresh"
        expected_builder = _expected_workbench_groups_builder(normalized_scope_key)
        if not expected_builder:
            return "fresh"
        where_sql, params = self._workbench_scope_filter(normalized_scope_key)
        active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
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
        unpaired_groups = []
        paired_section = grouped_payload.get("paired")
        unpaired_section = grouped_payload.get("unpaired")
        if isinstance(paired_section, dict) and isinstance(paired_section.get("groups"), list):
            paired_groups = [group for group in paired_section.get("groups", []) if isinstance(group, dict)]
        if isinstance(unpaired_section, dict) and isinstance(unpaired_section.get("groups"), list):
            unpaired_groups = [group for group in unpaired_section.get("groups", []) if isinstance(group, dict)]
        summary = _summarize_workbench_payload_groups(
            {"paired": {"groups": paired_groups}, "unpaired": {"groups": unpaired_groups}}
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
        page_statistics = (
            dict(normalized_summary.get("statistics"))
            if isinstance(normalized_summary.get("statistics"), dict)
            else None
        )
        for zone in ("paired", "unpaired"):
            counts = zone_counts.get(zone) if isinstance(zone_counts.get(zone), dict) else {}
            stored_counts = {
                **dict(counts),
                "page_statistics": page_statistics,
            }
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
                    jsonb(stored_counts),
                    jsonb({"summary_zone_counts": counts, "page_statistics": page_statistics}),
                ),
            )

    def _workbench_generation_stats_for_groups_page(
        self,
        *,
        scope_key: str,
        generation_id: str | None,
        zone: str,
    ) -> dict[str, Any] | None:
        if not generation_id:
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
            scope_clause = "rows.scope_key <> 'all'"
            params: list[Any] = []
        else:
            scope_clause = "rows.scope_key = %s"
            params = [normalized_scope_key]
        rows = self._connection.fetch_all(
            f"""
            select rows.row_id, rows.payload, rows.raw_payload
            from read_model.workbench_rows rows
            join read_model.workbench_generations generation
              on generation.tenant_id = 'default'
             and generation.scope_key = rows.scope_key
             and generation.generation_id = rows.generation_id
             and generation.status = 'active'
            where {scope_clause}
              and rows.status = 'ignored'
            order by rows.generated_at desc, rows.updated_at desc, rows.row_id
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
        sort: str | None = None,
        detail_level: str | None = None,
        column_filters: Any = None,
        time_filters: Any = None,
        expected_read_model_version: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_detail_level = _normalize_workbench_group_detail_level(detail_level)
        normalized_page = max(1, int_value(page, 1))
        normalized_page_size = min(200, max(1, int_value(page_size, 50)))
        offset = (normalized_page - 1) * normalized_page_size
        composed_all_scope = normalized_scope_key == "all"
        if composed_all_scope:
            scope_params: list[Any] = []
            active_month_version = self._workbench_active_month_generation_version(self._connection)
            active_generation_id = text(active_month_version.get("version"))
            active_source_versions = self._workbench_all_active_source_versions()
        else:
            groups_from_sql = "read_model.workbench_groups g"
            scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
            active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
            active_source_versions = self._workbench_generation_source_versions(
                self._connection,
                scope_key=normalized_scope_key,
                generation_id=active_generation_id,
            )
        expected_version = text(expected_read_model_version)
        if expected_version and expected_version != active_generation_id:
            raise WorkbenchReadModelVersionConflictError(expected=expected_version, current=active_generation_id)
        group_scope_clause = "true" if composed_all_scope else f"g.{scope_where}"
        group_row_join_id_sql = "coalesce(g.source_group_id, g.group_id)" if composed_all_scope else "g.group_id"
        group_select_sql = (
            "group_id, source_group_id, zone, payload, raw_payload, scope_key, generation_id"
            if composed_all_scope
            else "group_id, zone, payload, raw_payload, scope_key, generation_id"
        )
        normalized_column_filters = _normalize_workbench_column_filters(column_filters)
        normalized_time_filters = _normalize_workbench_time_filters(time_filters)
        normalized_search = (text(search) or "")[:200]
        if composed_all_scope:
            requires_aggregated_metadata = bool(text(sort))
            groups_from_sql = _workbench_active_month_groups_sql(
                include_aggregated_metadata=requires_aggregated_metadata
            )
        clauses = ["g.zone = %s"] if composed_all_scope else [f"g.{scope_where}", "g.zone = %s"]
        params = [*scope_params, normalized_zone]
        active_member_filter_joins: list[str] = []
        active_member_filter_params: list[Any] = []
        if active_generation_id and not composed_all_scope:
            clauses.append("g.generation_id = %s")
            params.append(active_generation_id)
        if normalized := text(status):
            clauses.append("g.status = %s")
            params.append(normalized)
        if normalized := text(source_kind):
            if composed_all_scope:
                active_member_filter_joins.append(
                    _workbench_all_active_member_filter_join_sql(
                        "r_source.source_kind = %s",
                        row_alias="r_source",
                        match_alias="source_match",
                    )
                )
                active_member_filter_params.append(normalized)
            else:
                clauses.append("%s = any(g.source_kinds)")
                params.append(normalized)
        if normalized_search:
            pattern = _workbench_literal_ilike_pattern(normalized_search)
            if composed_all_scope:
                active_member_filter_joins.append(
                    _workbench_all_active_member_filter_join_sql(
                        "r_zone_search.searchable_text ilike %s escape E'\\\\'",
                        row_alias="r_zone_search",
                        match_alias="zone_search_match",
                    )
                )
                active_member_filter_params.append(pattern)
            else:
                clauses.append(_workbench_zone_search_exists_sql(group_id_sql=group_row_join_id_sql))
                params.append(pattern)
        if composed_all_scope:
            row_filter_joins, row_filter_params = _workbench_all_group_row_filter_joins_sql(
                column_filters=normalized_column_filters,
                time_filters=normalized_time_filters,
            )
            active_member_filter_joins.extend(row_filter_joins)
            active_member_filter_params.extend(row_filter_params)
        else:
            row_filter_sql, row_filter_params = _workbench_group_row_filter_exists_sql(
                column_filters=normalized_column_filters,
                time_filters=normalized_time_filters,
                group_id_sql=group_row_join_id_sql,
            )
            if row_filter_sql:
                clauses.append(row_filter_sql)
                params.extend(row_filter_params)
        where_sql = " and ".join(clauses)
        active_member_filter_join_sql = "\n".join(active_member_filter_joins)
        order_by_sql = _workbench_groups_order_by(sort)
        oa_row_filter_sql, oa_row_filter_params = _workbench_group_row_count_filter_sql(
            "oa",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
        )
        bank_row_filter_sql, bank_row_filter_params = _workbench_group_row_count_filter_sql(
            "bank",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
        )
        invoice_row_filter_sql, invoice_row_filter_params = _workbench_group_row_count_filter_sql(
            "invoice",
            column_filters=normalized_column_filters,
            time_filters=normalized_time_filters,
        )
        generation_stats_eligible = (
            bool(active_generation_id)
            and not composed_all_scope
            and not any(
                (
                    text(status),
                    text(source_kind),
                    normalized_search,
                    normalized_column_filters,
                    normalized_time_filters,
                )
            )
        )
        materialized_counts = (
            self._workbench_generation_stats_for_groups_page(
                scope_key=normalized_scope_key,
                generation_id=active_generation_id,
                zone=normalized_zone,
            )
            if generation_stats_eligible
            else None
        )
        matching_group_ids: list[str] | None = None
        if materialized_counts is None:
            if composed_all_scope:
                groups_for_counts_sql = _workbench_active_month_group_keys_sql(
                    include_aggregated_searchable_text=False
                )
                distinct_row_sql = "(r.pane, coalesce(nullif(r.object_identity_key, ''), r.row_id))"
                count_row = self._connection.fetch_one(
                    f"""
                    with {_workbench_active_month_members_cte_sql()},
                    canonical_workbench_groups as materialized (
                        select * from {groups_for_counts_sql}
                    ), filtered_workbench_groups as materialized (
                        select g.group_id, g.zone
                        from canonical_workbench_groups g
                        {active_member_filter_join_sql}
                        where {where_sql}
                    ), filtered_workbench_members as materialized (
                        select r.*
                        from active_workbench_members r
                        join filtered_workbench_groups g
                          on g.zone = r.zone
                         and g.group_id = r.all_scope_group_id
                    )
                    select
                        (
                            select count(distinct g.group_id)
                            from filtered_workbench_groups g
                        )::bigint as total_count,
                        (
                            select coalesce(array_agg(distinct g.group_id), array[]::text[])
                            from filtered_workbench_groups g
                        ) as matching_group_ids,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'oa'
                              and coalesce(r.row_role, '') <> 'summary'
                              {oa_row_filter_sql}
                        )::bigint as oa_count,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'bank'
                              and coalesce(r.row_role, '') <> 'summary'
                              and coalesce(r.source_kind, '') not in (
                                  'bank_flow_rule_batch_summary'
                              )
                              {bank_row_filter_sql}
                        )::bigint as bank_count,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'invoice'
                              and coalesce(r.row_role, '') <> 'summary'
                              {invoice_row_filter_sql}
                        )::bigint as invoice_count
                    from filtered_workbench_members r
                    """,
                    tuple(
                        [
                            *active_member_filter_params,
                            *params,
                            *oa_row_filter_params,
                            *bank_row_filter_params,
                            *invoice_row_filter_params,
                        ]
                    ),
                )
            else:
                groups_for_counts_sql = groups_from_sql
                member_join_sql = f"""
                left join read_model.workbench_group_rows r
                  on r.scope_key = g.scope_key
                 and r.generation_id = g.generation_id
                 and r.zone = g.zone
                 and r.group_id = {group_row_join_id_sql}
                """
                distinct_row_sql = "r.row_id"
                count_row = self._connection.fetch_one(
                    f"""
                    select
                        count(distinct g.group_id)::bigint as total_count,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'oa'
                              and coalesce(r.row_role, '') <> 'summary'
                              {oa_row_filter_sql}
                        )::bigint as oa_count,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'bank'
                              and coalesce(r.row_role, '') <> 'summary'
                              and coalesce(r.source_kind, '') not in (
                                  'bank_flow_rule_batch_summary'
                              )
                              {bank_row_filter_sql}
                        )::bigint as bank_count,
                        count(distinct {distinct_row_sql}) filter (
                            where r.pane = 'invoice'
                              and coalesce(r.row_role, '') <> 'summary'
                              {invoice_row_filter_sql}
                        )::bigint as invoice_count
                    from {groups_for_counts_sql}
                    {member_join_sql}
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
            row_counts = _workbench_group_page_row_counts(count_row)
            if composed_all_scope:
                matching_group_ids = text_list((count_row or {}).get("matching_group_ids"))
        else:
            total = int_value(materialized_counts.get("total"), 0)
            row_counts = materialized_counts.get("row_counts")
            if not isinstance(row_counts, dict):
                row_counts = _workbench_group_page_row_counts(None)
        if composed_all_scope and matching_group_ids is not None:
            page_where_sql = "g.zone = %s and g.group_id = any(%s)"
            page_params = [normalized_zone, matching_group_ids, normalized_page_size + 1, offset]
        else:
            page_where_sql = where_sql
            page_params = [*params, normalized_page_size + 1, offset]
        rows = (
            self._connection.fetch_all(
                f"""
                select {group_select_sql}
                from {groups_from_sql}
                where {page_where_sql}
                order by {order_by_sql}
                limit %s offset %s
                """,
                tuple(page_params),
            )
            if matching_group_ids is None or matching_group_ids
            else []
        )
        visible_rows = rows[:normalized_page_size]
        materialized_rows = self._materialize_workbench_group_payloads(visible_rows)
        groups: list[dict[str, Any]] = []
        for row, materialized_group in zip(visible_rows, materialized_rows, strict=False):
            group = materialized_group
            if not isinstance(group, dict):
                group = {"group_id": text(row.get("group_id"))}
            group = _sanitize_workbench_group_invoice_rows(group)
            group = _with_workbench_group_counts(group)
            if normalized_detail_level == "summary":
                group = _filter_workbench_group_preview_rows_for_criteria(
                    group,
                    column_filters=normalized_column_filters,
                    time_filters=normalized_time_filters,
                )
                group = _compact_workbench_group_for_summary_page(group)
            groups.append(group)
        if composed_all_scope:
            current_generation_id = text(
                self._workbench_active_month_generation_version(self._connection).get("version")
            )
            if current_generation_id != active_generation_id:
                return None
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

    def get_workbench_group_detail(
        self,
        *,
        scope_key: str,
        zone: str,
        group_id: str,
        expected_read_model_version: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        if not normalized_zone or not normalized_group_id:
            return None
        composed_all_scope = normalized_scope_key == "all"
        if composed_all_scope:
            groups_from_sql = _workbench_active_month_groups_sql(include_aggregated_metadata=False)
            scope_where, scope_params = "true", []
            active_generation_id = text(self._workbench_active_month_generation_version(self._connection).get("version"))
        else:
            groups_from_sql = "read_model.workbench_groups g"
            scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
            active_generation_id = self._active_workbench_generation_id(self._connection, scope_key=normalized_scope_key)
        expected_version = text(expected_read_model_version)
        if expected_version and expected_version != active_generation_id:
            raise WorkbenchReadModelVersionConflictError(expected=expected_version, current=active_generation_id)
        source_group_select_sql = "g.source_group_id," if composed_all_scope else ""
        generation_clause = ""
        generation_params: list[Any] = []
        if active_generation_id and not composed_all_scope:
            generation_clause = "and g.generation_id = %s"
            generation_params.append(active_generation_id)
        group_scope_clause = "true" if composed_all_scope else f"g.{scope_where}"
        group_id_clause = "(g.group_id = %s or g.source_group_id = %s)" if composed_all_scope else "g.group_id = %s"
        row = self._connection.fetch_one(
            f"""
            select
              g.group_id,
              g.zone,
              g.scope_key,
              g.generation_id,
              {source_group_select_sql}
              g.payload,
              g.raw_payload,
              gen.source_versions
              from {groups_from_sql}
              left join read_model.workbench_generations gen
                on gen.tenant_id = 'default'
             and gen.scope_key = g.scope_key
             and gen.generation_id = g.generation_id
            where {group_scope_clause}
              {generation_clause}
              and g.zone = %s
              and {group_id_clause}
            order by g.scope_month desc nulls last, g.updated_at desc
            limit 1
            """,
            (
                *scope_params,
                *generation_params,
                normalized_zone,
                normalized_group_id,
                *([normalized_group_id] if composed_all_scope else []),
            ),
        )
        if not isinstance(row, dict):
            return None
        resolved_scope_key = text(row.get("scope_key")) or normalized_scope_key
        materialized_groups = self._materialize_workbench_group_payloads([row])
        group = materialized_groups[0] if materialized_groups else _read_model_payload(row)
        if not isinstance(group, dict):
            group = {"group_id": text(row.get("group_id"))}
        result = _with_workbench_group_counts(_sanitize_workbench_group_invoice_rows(group))
        result["scope_key"] = "all" if composed_all_scope else resolved_scope_key
        if composed_all_scope and resolved_scope_key and resolved_scope_key != "all":
            result["source_scope_key"] = resolved_scope_key
        source_versions = self._workbench_all_active_source_versions() if composed_all_scope else row.get("source_versions")
        result["source_versions"] = dict(source_versions) if isinstance(source_versions, dict) else {}
        result["active_generation_id"] = active_generation_id
        result["read_model_version"] = active_generation_id
        result["read_model_status"] = self._workbench_read_model_status_for_groups_page(scope_key=result["scope_key"])
        return result

    def get_workbench_row_detail(
        self,
        *,
        scope_key: str,
        row_id: str,
        expected_read_model_version: str | None = None,
    ) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_row_id = text(row_id)
        if not normalized_row_id:
            return None
        if normalized_scope_key == "all":
            active_generation_id = text(self._workbench_active_month_generation_version(self._connection).get("version"))
        else:
            active_generation_id = self._active_workbench_generation_id(
                self._connection,
                scope_key=normalized_scope_key,
            )
        expected_version = text(expected_read_model_version)
        if expected_version and expected_version != active_generation_id:
            raise WorkbenchReadModelVersionConflictError(expected=expected_version, current=active_generation_id)
        if normalized_scope_key == "all":
            row_scope_clause = "true"
            group_row_scope_clause = "true"
            scope_params: tuple[Any, ...] = ()
        else:
            row_scope_clause = "r.scope_key in (%s, 'all')"
            group_row_scope_clause = "gr.scope_key in (%s, 'all')"
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
              and {row_scope_clause}
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
            row = self._connection.fetch_one(
                f"""
                select
                  gr.row_id,
                  gr.pane,
                  gr.source_kind,
                  gr.status,
                  gr.payload as member_payload,
                  gr.raw_payload as member_raw_payload,
                  gr.scope_key,
                  gr.generation_id,
                  gen.source_versions
                from read_model.workbench_group_rows gr
                join read_model.workbench_generations gen
                  on gen.generation_id = gr.generation_id
                 and gen.scope_key = gr.scope_key
                 and gen.status = 'active'
                where gr.row_id = %s
                  and {group_row_scope_clause}
                order by
                  case
                    when gr.scope_key = %s then 0
                    when gr.scope_key = 'all' then 1
                    else 2
                  end,
                  gr.updated_at desc nulls last
                limit 1
                """,
                (normalized_row_id, *scope_params, normalized_scope_key),
            )
            if isinstance(row, dict):
                payload = row_payload(row, "member_payload", "member_raw_payload")
                if not isinstance(payload, dict) or not payload:
                    return None
                payload = dict(payload)
                payload.setdefault("id", normalized_row_id)
                payload.setdefault("row_id", normalized_row_id)
                payload.setdefault("type", text(row.get("source_kind")) or text(row.get("pane")) or "unknown")
                source_kind = text(row.get("source_kind"))
                if source_kind:
                    payload.setdefault("source_kind", source_kind)
                status = text(row.get("status"))
                if status:
                    payload.setdefault("status", status)
                resolved_scope_key = text(row.get("scope_key")) or normalized_scope_key
                return {
                    "row": payload,
                    "scope_key": resolved_scope_key,
                    "source_versions": row.get("source_versions"),
                    "active_generation_id": active_generation_id,
                    "read_model_version": active_generation_id,
                    "read_model_status": self._workbench_read_model_status_for_groups_page(scope_key=resolved_scope_key),
                }
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
            "active_generation_id": active_generation_id,
            "read_model_version": active_generation_id,
            "read_model_status": self._workbench_read_model_status_for_groups_page(scope_key=resolved_scope_key),
        }

    def get_workbench_relation_preview_selection(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        expected_read_model_version: str,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_row_ids = _dedupe_preserve_order(text(row_id) for row_id in list(row_ids or []))
        if not normalized_row_ids:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_selection_required",
                message="请至少选择一条工作台记录。",
            )
        if len(normalized_row_ids) > WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_selection_too_large",
                message=f"单次预览最多选择 {WORKBENCH_RELATION_PREVIEW_MAX_SELECTED_ROWS} 条记录。",
            )
        expected_version = text(expected_read_model_version)
        if not expected_version:
            raise WorkbenchRelationPreviewSelectionError(
                code="expected_read_model_version_required",
                message="工作台版本缺失，请刷新后重试。",
            )

        freshness = self.get_workbench_groups_freshness_status(scope_key=normalized_scope_key)
        read_model_status = text(freshness.get("read_model_status")) or "unavailable"
        if read_model_status != "fresh":
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_read_model_not_fresh",
                message="工作台数据正在更新，请刷新后重试。",
            )
        start_proof = self._workbench_relation_preview_generation_proof(normalized_scope_key)
        start_version = text(start_proof.get("version"))
        if expected_version != start_version:
            raise WorkbenchReadModelVersionConflictError(expected=expected_version, current=start_version)
        freshness_version = text(
            freshness.get("read_model_version") or freshness.get("active_generation_id")
        )
        if freshness_version != start_version:
            raise WorkbenchReadModelVersionConflictError(
                expected=expected_version,
                current=start_version,
            )
        generation_set = [
            dict(item)
            for item in list(start_proof.get("generation_set") or [])
            if isinstance(item, dict)
            and text(item.get("scope_key"))
            and text(item.get("generation_id"))
        ]
        if not generation_set:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_generation_unavailable",
                message="工作台当前版本不可用，请刷新后重试。",
            )
        active_pairs = {
            (text(item.get("scope_key")), text(item.get("generation_id")))
            for item in generation_set
        }
        scope_keys = [str(item["scope_key"]) for item in generation_set]
        generation_ids = [str(item["generation_id"]) for item in generation_set]
        selected_records = self._connection.fetch_all(
            """
            /* relation-preview-selected-rows */
            with active_generations as (
                select *
                from unnest(%s::text[], %s::text[])
                  as active(scope_key, generation_id)
            )
            select
                r.row_id,
                r.source_kind,
                r.status,
                r.payload,
                r.raw_payload,
                r.scope_key,
                r.generation_id
            from active_generations active
            join read_model.workbench_rows r
              on r.scope_key = active.scope_key
             and r.generation_id = active.generation_id
            where r.row_id = any(%s::text[])
            order by array_position(%s::text[], r.row_id), r.scope_key, r.row_id
            """,
            (scope_keys, generation_ids, normalized_row_ids, normalized_row_ids),
        )
        selected_rows = self._workbench_relation_preview_rows(
            selected_records,
            expected_pairs=active_pairs,
        )
        selected_by_id = self._workbench_relation_preview_rows_by_id(selected_rows)
        missing_row_ids = [row_id for row_id in normalized_row_ids if row_id not in selected_by_id]
        if missing_row_ids:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_rows_missing",
                message="所选工作台记录已变化，请刷新后重试。",
            )

        oa_source_ids = self._workbench_relation_preview_oa_source_ids(
            [selected_by_id[row_id] for row_id in normalized_row_ids]
        )
        context_records: list[dict[str, Any]] = []
        if oa_source_ids:
            context_records = self._connection.fetch_all(
                f"""
                /* relation-preview-oa-attachment-context */
                with active_generations as (
                    select *
                    from unnest(%s::text[], %s::text[])
                      as active(scope_key, generation_id)
                ),
                oa_candidate_ids as materialized (
                    select unnest(%s::text[]) as oa_row_id
                )
                select
                    r.row_id,
                    r.source_kind,
                    r.status,
                    r.payload,
                    r.raw_payload,
                    r.scope_key,
                    r.generation_id
                from active_generations active
                join read_model.workbench_rows r
                  on r.scope_key = active.scope_key
                 and r.generation_id = active.generation_id
                where r.source_kind = 'oa_attachment_invoice'
                  and (
                    {_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL}
                    or regexp_replace(
                        coalesce(nullif(r.payload->>'oa_row_id', ''), ''),
                        ':item:.*$',
                        ''
                    ) = any(
                        coalesce(
                            (select array_agg(candidate.oa_row_id) from oa_candidate_ids candidate),
                            array[]::text[]
                        )
                    )
                  )
                order by r.scope_key, r.row_id
                """,
                (scope_keys, generation_ids, oa_source_ids),
            )
        context_rows = self._workbench_relation_preview_rows(
            context_records,
            expected_pairs=active_pairs,
        )
        context_by_id = self._workbench_relation_preview_rows_by_id(context_rows)
        for selected_row_id in normalized_row_ids:
            context_by_id.pop(selected_row_id, None)
        if len(context_by_id) > WORKBENCH_RELATION_PREVIEW_MAX_CONTEXT_ROWS:
            raise WorkbenchRelationPreviewSelectionError(
                code="relation_preview_context_too_large",
                message="所选记录关联的上下文过多，请缩小选择范围后重试。",
            )

        end_freshness = self.get_workbench_groups_freshness_status(scope_key=normalized_scope_key)
        end_version = text(
            end_freshness.get("read_model_version")
            or end_freshness.get("active_generation_id")
        )
        if (
            text(end_freshness.get("read_model_status")) != "fresh"
            or end_version != start_version
        ):
            raise WorkbenchReadModelVersionConflictError(expected=expected_version, current=end_version)

        ordered_selected_rows = [selected_by_id[row_id] for row_id in normalized_row_ids]
        ordered_context_rows = [context_by_id[row_id] for row_id in sorted(context_by_id)]
        rows = [*ordered_selected_rows, *ordered_context_rows]
        memberships, context_groups = self._workbench_relation_preview_context(rows)
        return {
            "scope_key": normalized_scope_key,
            "selected_row_ids": normalized_row_ids,
            "selected_rows": ordered_selected_rows,
            "context_rows": ordered_context_rows,
            "rows": rows,
            "memberships": memberships,
            "context_groups": context_groups,
            "source_versions": dict(freshness.get("source_versions") or {}),
            "generation_set": generation_set,
            "active_generation_id": start_version,
            "read_model_version": start_version,
            "read_model_status": "fresh",
        }

    def _workbench_relation_preview_generation_proof(self, scope_key: str) -> dict[str, Any]:
        if scope_key == "all":
            proof = self._workbench_active_month_generation_version(self._connection)
            return {
                "version": text(proof.get("version")),
                "generation_set": list(proof.get("generation_set") or []),
            }
        generation_id = self._active_workbench_generation_id(
            self._connection,
            scope_key=scope_key,
        )
        return {
            "version": generation_id,
            "generation_set": (
                [{"scope_key": scope_key, "generation_id": generation_id}]
                if generation_id
                else []
            ),
        }

    @staticmethod
    def _workbench_relation_preview_rows(
        records: list[dict[str, Any]],
        *,
        expected_pairs: set[tuple[str | None, str | None]],
    ) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for record in records:
            scope_key = text(record.get("scope_key"))
            generation_id = text(record.get("generation_id"))
            if (scope_key, generation_id) not in expected_pairs:
                raise WorkbenchRelationPreviewSelectionError(
                    code="relation_preview_cross_generation",
                    message="工作台版本已变化，请刷新后重试。",
                )
            row_id = text(record.get("row_id"))
            payload = _read_model_payload(record)
            if not row_id or not isinstance(payload, dict):
                continue
            row = dict(payload)
            row.setdefault("id", row_id)
            row.setdefault("row_id", row_id)
            source_kind = text(record.get("source_kind"))
            if source_kind:
                row.setdefault("source_kind", source_kind)
            row.setdefault("type", source_kind or "unknown")
            status = text(record.get("status"))
            if status:
                row.setdefault("status", status)
            rows.append(row)
        return rows

    @staticmethod
    def _workbench_relation_preview_rows_by_id(
        rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        rows_by_id: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = text(row.get("id") or row.get("row_id"))
            if not row_id:
                continue
            if row_id in rows_by_id:
                if rows_by_id[row_id] == row:
                    continue
                raise WorkbenchRelationPreviewSelectionError(
                    code="relation_preview_rows_ambiguous",
                    message="所选工作台记录跨版本内容不一致，请刷新后重试。",
                )
            rows_by_id[row_id] = row
        return rows_by_id

    @staticmethod
    def _workbench_relation_preview_oa_source_ids(
        rows: list[dict[str, Any]],
    ) -> list[str]:
        source_ids: list[str] = []
        for row in rows:
            row_id = text(row.get("id") or row.get("row_id"))
            row_type = text(row.get("type") or row.get("source_kind"))
            if row_id and row_type == "oa":
                source_ids.append(row_id)
            for key in ("source_oa_id", "source_oa_row_id", "oa_row_id", "derived_from_oa_id"):
                value = text(row.get(key))
                if value:
                    source_ids.append(value.split(":item:", 1)[0])
        return _dedupe_preserve_order(source_ids)

    @staticmethod
    def _workbench_relation_preview_context(
        rows: list[dict[str, Any]],
    ) -> tuple[list[dict[str, str]], list[dict[str, Any]]]:
        memberships: list[dict[str, str]] = []
        grouped_row_ids: dict[str, list[str]] = {}
        for row in rows:
            row_id = text(row.get("id") or row.get("row_id"))
            if not row_id:
                continue
            case_id = text(row.get("case_id") or row.get("active_relation_case_id"))
            source_oa_id = text(
                row.get("source_oa_id")
                or row.get("source_oa_row_id")
                or row.get("oa_row_id")
                or row.get("derived_from_oa_id")
            )
            if case_id:
                group_id = f"case:{case_id}"
            elif source_oa_id:
                group_id = f"oa-context:{source_oa_id.split(':item:', 1)[0]}"
            else:
                group_id = f"selected:{row_id}"
            memberships.append({"row_id": row_id, "group_id": group_id})
            grouped_row_ids.setdefault(group_id, []).append(row_id)
        context_groups = [
            {
                "group_id": group_id,
                "group_type": "selection",
                "zone": "unpaired",
                "status": "unpaired",
                "row_ids": row_ids,
            }
            for group_id, row_ids in grouped_row_ids.items()
        ]
        return memberships, context_groups

    def find_workbench_row_scope_key(self, *, row_id: str) -> str | None:
        normalized_row_id = text(row_id)
        if not normalized_row_id:
            return None
        row = self._connection.fetch_one(
            """
            select r.scope_key
            from read_model.workbench_rows r
            join read_model.workbench_generations gen
              on gen.generation_id = r.generation_id
             and gen.scope_key = r.scope_key
             and gen.status = 'active'
            where r.row_id = %s
              and r.scope_key <> 'all'
            order by r.updated_at desc nulls last
            limit 1
            """,
            (normalized_row_id,),
        )
        if not isinstance(row, dict):
            return None
        return text(row.get("scope_key")) or None

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
        normalized_scope_key = str(scope_key or "all").strip() or "all"
        scope_clause = "" if normalized_scope_key == "all" else "and dirty.scope_key = %s"
        params = () if normalized_scope_key == "all" else (normalized_scope_key,)
        dirty_rows = self._connection.fetch_all(
            f"""
            select dirty.scope_key, dirty.status,
                   dirty.updated_at::text as updated_at,
                   dirty.last_error, dirty.source_version,
                   exists (
                       select 1
                       from job.outbox_events event
                       where event.tenant_id = dirty.tenant_id
                         and event.event_type = 'workbench.read_model.refresh'
                         and event.scope_type = dirty.scope_type
                         and event.scope_key = dirty.scope_key
                         and event.status in ('pending', 'processing')
                   ) as active_event
            from job.read_model_dirty_scopes dirty
            where dirty.tenant_id = 'default'
              and dirty.scope_type = 'workbench'
              and dirty.status in ('pending', 'processing', 'failed')
              {scope_clause}
            order by dirty.updated_at desc
            limit 50
            """,
            params,
        )
        if normalized_scope_key == "all":
            active_version = self._workbench_active_month_generation_version(self._connection)
            generation_set = [
                item
                for item in list(active_version.get("generation_set") or [])
                if isinstance(item, dict)
            ]
            active_generation_id = text(active_version.get("version"))
            generated_at = text(active_version.get("generated_at"))
            active_source_versions = _workbench_composed_all_source_versions(
                [{"source_versions": item.get("source_versions")} for item in generation_set]
            )
            source_version_by_scope = {
                text(item.get("scope_key")): _source_version_value(item.get("source_versions")) or 0
                for item in generation_set
                if text(item.get("scope_key"))
            }
        else:
            active_row = self._connection.fetch_one(
                """
                select
                    generation_id,
                    source_versions,
                    coalesce(activated_at, completed_at, updated_at)::text as generated_at
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and scope_key = %s
                  and status = 'active'
                order by activated_at desc nulls last, completed_at desc nulls last, updated_at desc
                limit 1
                """,
                (normalized_scope_key,),
            )
            active_generation_id = text((active_row or {}).get("generation_id"))
            generated_at = text((active_row or {}).get("generated_at"))
            raw_source_versions = (active_row or {}).get("source_versions")
            active_source_versions = dict(raw_source_versions) if isinstance(raw_source_versions, dict) else {}
            source_version_by_scope = {
                normalized_scope_key: _source_version_value(active_source_versions) or 0,
            }

        dirty_scopes = [
            {
                "scope_key": text(row.get("scope_key")),
                "status": text(row.get("status")),
                "updated_at": text(row.get("updated_at")),
                "last_error": text(row.get("last_error")),
                "source_version": int_value(row.get("source_version"), 0),
                "active_event": bool(row.get("active_event")),
            }
            for row in dirty_rows
            if isinstance(row, dict)
        ]
        active_source_version = max(source_version_by_scope.values(), default=0)
        pending_scopes = [
            scope
            for scope in dirty_scopes
            if scope.get("status") in {"pending", "processing"}
            and (
                int_value(scope.get("source_version"), 0) <= 0
                or int_value(scope.get("source_version"), 0)
                > source_version_by_scope.get(text(scope.get("scope_key")), active_source_version)
            )
        ]
        failed_scopes = [scope for scope in dirty_scopes if scope.get("status") == "failed"]
        orphan_scope_keys = [
            text(scope.get("scope_key"))
            for scope in pending_scopes
            if not bool(scope.get("active_event")) and text(scope.get("scope_key"))
        ]
        active_refresh_in_progress = bool(pending_scopes) and not orphan_scope_keys
        read_model_status = "fresh"
        stale_reasons: list[str] = []
        if not active_generation_id:
            read_model_status = "unavailable"
            stale_reasons.append("active_generation_missing")
        elif orphan_scope_keys:
            read_model_status = "stale"
            stale_reasons.append("orphan_dirty_scope")
        elif active_refresh_in_progress:
            read_model_status = "refreshing"
        elif failed_scopes:
            read_model_status = "stale"
            stale_reasons.append("refresh_failed")
        else:
            schema_status = self._workbench_groups_schema_status(scope_key=normalized_scope_key)
            if schema_status != "fresh":
                read_model_status = "stale"
                stale_reasons.append("builder_schema_mismatch")
        return {
            "scope_key": normalized_scope_key,
            "read_model_status": read_model_status,
            "active_generation_id": active_generation_id,
            "read_model_version": active_generation_id,
            "generated_at": generated_at,
            "source_versions": active_source_versions,
            "dirty_scopes": dirty_scopes,
            "active_refresh_in_progress": active_refresh_in_progress,
            "refresh_scope_keys": orphan_scope_keys,
            "read_model_stale_reasons": stale_reasons,
            "last_error": next((scope.get("last_error") for scope in failed_scopes if scope.get("last_error")), None),
        }

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
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
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
        generation_metadata = (
            self._workbench_all_composed_generation_metadata()
            if normalized_scope_key == "all"
            else self._workbench_generation_metadata(self._connection, scope_key=normalized_scope_key)
        )
        all_scope_parent_failures = self._workbench_all_scope_parent_stale_failures(
            self._connection,
            scope_key=normalized_scope_key,
        )
        groups_schema_status = self._workbench_groups_schema_status(scope_key=normalized_scope_key)
        active_refresh_in_progress = bool(
            dirty_statuses.intersection({"pending", "processing"})
            or generation_metadata.get("building_generation_id")
        )
        if active_refresh_in_progress and self._workbench_active_generation_covers_dirty_scopes(
            generation_metadata=generation_metadata,
            dirty_scopes=dirty_scopes,
        ):
            active_refresh_in_progress = False
        consistency_failures = []
        consistency_status = "fresh"
        if include_consistency:
            if active_refresh_in_progress:
                active_generation_id = text(generation_metadata.get("active_generation_id"))
                cached_failures = self._workbench_generation_consistency_cache.get(
                    (normalized_scope_key, active_generation_id)
                )
                if cached_failures is not None:
                    consistency_failures = deepcopy(cached_failures)
                consistency_status = "failed" if consistency_failures else "refreshing"
            else:
                consistency_failures = self._cached_workbench_generation_consistency_failures(
                    scope_key=normalized_scope_key,
                    generation_metadata=generation_metadata,
                )
                consistency_status = "failed" if consistency_failures else "fresh"
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
        elif all_scope_parent_failures:
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
        if all_scope_parent_failures:
            stale_reasons.append("all_scope_parent_generation_out_of_sync")
        return {
            "scope_key": normalized_scope_key,
            "read_model_status": read_model_status,
            "consistency_status": consistency_status,
            "consistency_failures": consistency_failures,
            "all_scope_parent_failures": all_scope_parent_failures,
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

    def _cached_workbench_generation_consistency_failures(
        self,
        *,
        scope_key: str,
        generation_metadata: dict[str, Any],
    ) -> list[dict[str, Any]]:
        active_generation_id = text(generation_metadata.get("active_generation_id"))
        if not active_generation_id:
            return self._workbench_generation_consistency_failures(
                self._connection,
                scope_key=None if scope_key == "all" else scope_key,
                include_all=scope_key != "all",
            )
        cache_key = (scope_key, active_generation_id)
        cached = self._workbench_generation_consistency_cache.get(cache_key)
        if cached is not None:
            return deepcopy(cached)
        failures = self._workbench_generation_consistency_failures(
            self._connection,
            scope_key=None if scope_key == "all" else scope_key,
            include_all=scope_key != "all",
        )
        for existing_key in tuple(self._workbench_generation_consistency_cache):
            if existing_key[0] == scope_key:
                self._workbench_generation_consistency_cache.pop(existing_key, None)
        self._workbench_generation_consistency_cache[cache_key] = deepcopy(failures)
        return failures

    @staticmethod
    def _workbench_active_generation_covers_dirty_scopes(
        *,
        generation_metadata: dict[str, Any],
        dirty_scopes: list[dict[str, Any]],
    ) -> bool:
        if generation_metadata.get("building_generation_id"):
            return False
        generations = generation_metadata.get("generations")
        active_generation_id = text(generation_metadata.get("active_generation_id"))
        if not isinstance(generations, list) or not active_generation_id:
            return False
        active_generation = next(
            (
                generation
                for generation in generations
                if isinstance(generation, dict)
                and text(generation.get("generation_id")) == active_generation_id
                and text(generation.get("status")) == "active"
            ),
            None,
        )
        if not isinstance(active_generation, dict):
            return False
        source_versions = active_generation.get("source_versions")
        if not isinstance(source_versions, dict):
            return False
        active_source_version = int_value(source_versions.get("source_version"), 0)
        if active_source_version <= 0:
            return False
        active_dirty_scopes = [
            scope
            for scope in dirty_scopes
            if text(scope.get("status")) in {"pending", "processing"}
        ]
        if not active_dirty_scopes:
            return False
        for scope in active_dirty_scopes:
            dirty_source_version = int_value(scope.get("source_version"), 0)
            if dirty_source_version <= 0 or dirty_source_version > active_source_version:
                return False
        return True

    def workbench_groups_cache_version(self, *, scope_key: str) -> str | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        if normalized_scope_key == "all":
            version = text(self._workbench_active_month_generation_version(self._connection).get("version"))
            return f"{WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION}:{version}" if version else None
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
        keep_days_value = max(0, int_value(keep_days, 14))
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
    ) -> set[str]:
        started_generations: list[tuple[str, str, dict[str, Any]]] = []
        prepared_generations: list[tuple[str, str, int, int]] = []
        published_scope_keys: set[str] = set()

        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            read_model_items = list(iter_mapping(read_models))
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in read_model_items}
                if set(changed_scope_keys) - present_scope_keys:
                    raise ValueError("changed_scope_keys must reference payloads written in this call.")
            writable_items = [
                (scope_key, payload)
                for scope_key, payload in read_model_items
                if changed_scope_keys is None or scope_key in changed_scope_keys
            ]
            for scope_key, payload in writable_items:
                if scope_key == "all":
                    raise ValueError("all-scope is composed from active month shards and must not be materialized.")
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
                source_versions_jsonb = jsonb(source_versions)
                empty_jsonb = jsonb({})
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
                        source_versions_jsonb,
                        generated_at,
                        cache_status,
                        row_count,
                        jsonb(
                            _workbench_snapshot_payload_for_write(
                                scope_key=scope_key,
                                scope_month=scope_month,
                                grouped_payload=grouped_payload,
                                source_versions=source_versions,
                                generated_at=generated_at,
                                cache_status=cache_status,
                            )
                        ),
                        empty_jsonb,
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
                        source_versions_jsonb,
                        generated_at,
                        cache_status,
                        jsonb(summary_payload.get("summary") if isinstance(summary_payload.get("summary"), dict) else {}),
                        jsonb(summary_payload.get("invoice_inventory") if isinstance(summary_payload.get("invoice_inventory"), dict) else {}),
                        jsonb(summary_payload),
                        empty_jsonb,
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
                            text(row.get("status") or payload.get("status") or "unpaired") or "unpaired",
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
                            source_versions_jsonb,
                            generated_at,
                            cache_status,
                            jsonb(_workbench_row_payload_for_write(row)),
                            empty_jsonb,
                        ),
                    )
                _write_workbench_generation_rows(
                    connection,
                    copy_sql="""
                    copy read_model.workbench_rows(
                        generation_id, row_id, scope_month, scope_key, source_kind, status, project_id, project_name,
                        counterparty_name, amount, object_identity_key, object_identity_kind,
                        object_identity_source, object_identity_confidence,
                        source_versions, generated_at, cache_status, payload, raw_payload
                    ) from stdin
                    """,
                    insert_sql="""
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
                    """,
                    params_seq=workbench_row_params,
                    generated_at_index=15,
                )
                workbench_group_params: list[tuple[Any, ...]] = []
                workbench_group_row_params: list[tuple[Any, ...]] = []
                for group in workbench_groups:
                    group_id = text(group.get("group_id"))
                    if group_id is None:
                        continue
                    group_scope_month = month_start(group.get("scope_month") or group.get("month") or scope_month)
                    group_payload = group.get("payload") if isinstance(group.get("payload"), dict) else group
                    group_payload_for_write = _workbench_group_payload_for_write(group, payload=group_payload)
                    workbench_group_params.append(
                        (
                            generation_id,
                            group_id,
                            scope_key,
                            group_scope_month,
                            text(group.get("zone")) or "unpaired",
                            text(group.get("status")) or text(group.get("zone")) or "unpaired",
                            text(group.get("group_type"))
                            or ("relation" if text(group.get("zone")) == "paired" else "unpaired"),
                            text_list(group.get("source_kinds")),
                            int_value(group.get("row_count"), 0),
                            text(group.get("searchable_text")) or "",
                            text(group.get("oa_sort_min")),
                            text(group.get("oa_sort_max")),
                            text(group.get("bank_sort_min")),
                            text(group.get("bank_sort_max")),
                            text(group.get("invoice_sort_min")),
                            text(group.get("invoice_sort_max")),
                            source_versions_jsonb,
                            generated_at,
                            cache_status,
                            jsonb(group_payload_for_write),
                            empty_jsonb,
                        ),
                    )
                    for group_row in _workbench_group_row_records(
                        _workbench_group_payload_for_rows(group, payload=group_payload)
                    ):
                        workbench_group_row_params.append(
                            (
                                generation_id,
                                scope_key,
                                group_scope_month,
                                text(group_row.get("zone")) or text(group.get("zone")) or "unpaired",
                                group_id,
                                text(group_row.get("pane")) or "",
                                text(group_row.get("row_id")) or "",
                                text(group_row.get("row_role")) or "normal",
                                int_value(group_row.get("row_index"), 0),
                                text(group_row.get("source_kind")) or "workbench_row",
                                text(group_row.get("status")) or text(group.get("status")) or "unpaired",
                                text(group_row.get("time_value")),
                                text(group_row.get("time_date")),
                                jsonb(group_row.get("column_values") if isinstance(group_row.get("column_values"), dict) else {}),
                                text(group_row.get("searchable_text")) or "",
                                text(group_row.get("object_identity_key")),
                                text(group_row.get("object_identity_kind")),
                                text(group_row.get("object_identity_source")),
                                text(group_row.get("object_identity_confidence")),
                                empty_jsonb,
                                generated_at,
                                cache_status,
                                empty_jsonb,
                                empty_jsonb,
                            ),
                        )
                _write_workbench_generation_rows(
                    connection,
                    copy_sql="""
                    copy read_model.workbench_groups(
                        generation_id, group_id, scope_key, scope_month, zone, status, group_type, source_kinds,
                        row_count, searchable_text, oa_sort_min, oa_sort_max, bank_sort_min, bank_sort_max,
                        invoice_sort_min, invoice_sort_max, source_versions, generated_at, cache_status,
                        payload, raw_payload
                    ) from stdin
                    """,
                    insert_sql="""
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
                    """,
                    params_seq=workbench_group_params,
                    generated_at_index=17,
                )
                _write_workbench_generation_rows(
                    connection,
                    copy_sql="""
                    copy read_model.workbench_group_rows(
                        generation_id, scope_key, scope_month, zone, group_id, pane, row_id, row_role, row_index,
                        source_kind, status, time_value, time_date, column_values, searchable_text,
                        object_identity_key, object_identity_kind, object_identity_source, object_identity_confidence,
                        source_versions, generated_at, cache_status, payload, raw_payload
                    ) from stdin
                    """,
                    insert_sql="""
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
                    """,
                    params_seq=workbench_group_row_params,
                    generated_at_index=20,
                )
                prepared_generations.append((scope_key, generation_id, row_count, group_count))
            if prepared_generations:
                # ponytail: COPY stays parallel; only the short activation/stats section shares one lock.
                self._lock_workbench_generation_set(connection)
                for scope_key, generation_id, row_count, group_count in prepared_generations:
                    self._activate_workbench_generation(
                        connection,
                        scope_key=scope_key,
                        generation_id=generation_id,
                        row_count=row_count,
                        group_count=group_count,
                        summary_count=1,
                    )
                    published_scope_keys.add(scope_key)
        try:
            run_in_transaction(self._connection, write)
        except Exception as exc:
            error_message = str(exc)
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
                        error=error_message,
                    )

                try:
                    run_in_transaction(self._connection, mark_failed)
                except Exception:
                    pass
            raise
        return set(published_scope_keys)

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


def _empty_workbench_zone_counts() -> dict[str, dict[str, int]]:
    return {
        "paired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
        "unpaired": {"groups": 0, "oa": 0, "bank": 0, "invoice": 0, "rows": 0},
    }


def _normalize_workbench_summary_counts(summary: dict[str, Any]) -> dict[str, Any]:
    normalized = dict(summary)
    zone_counts = normalized.get("zone_counts")
    if not isinstance(zone_counts, dict):
        zone_counts = _empty_workbench_zone_counts()
        zone_counts["paired"]["groups"] = int_value(normalized.get("paired_count"), 0)
        zone_counts["unpaired"]["groups"] = int_value(normalized.get("unpaired_count"), 0)
    else:
        merged = _empty_workbench_zone_counts()
        for zone in ("paired", "unpaired"):
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
    return {
        "oa": oa_count,
        "bank": bank_count,
        "invoice": invoice_count,
        "rows": oa_count + bank_count + invoice_count,
    }


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
            "collapsed_rows",
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
            for row in rows
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

def _workbench_literal_ilike_pattern(value: str) -> str:
    escaped = value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _workbench_zone_search_exists_sql(*, group_id_sql: str = "g.group_id") -> str:
    return (
        "exists (select 1 from read_model.workbench_group_rows r_zone_search "
        "where r_zone_search.scope_key = g.scope_key "
        "and r_zone_search.generation_id = g.generation_id "
        "and r_zone_search.zone = g.zone "
        f"and r_zone_search.group_id = {group_id_sql} "
        "and r_zone_search.searchable_text ilike %s escape E'\\\\')"
    )


def _workbench_all_logical_group_id_sql(group_id_sql: str, scope_key_sql: str) -> str:
    return (
        f"case when left({group_id_sql}, 5) = 'case:' or left({group_id_sql}, 9) = 'unpaired:' "
        f"then {group_id_sql} else 'scope:' || {scope_key_sql} || ':' || {group_id_sql} end"
    )


def _workbench_active_month_groups_sql(*, include_aggregated_metadata: bool = True) -> str:
    logical_group_id_sql = _workbench_all_logical_group_id_sql("g.group_id", "g.scope_key")
    if include_aggregated_metadata:
        ranked_groups_sql = """
            , canonical_candidates as (
                select active_groups.*
                from active_groups
                join canonical_owners
                  on canonical_owners.all_scope_group_id = active_groups.all_scope_group_id
                 and canonical_owners.zone = active_groups.zone
            ), ranked_groups as (
                select
                    canonical_candidates.*,
                    row_number() over (
                        partition by canonical_candidates.all_scope_group_id
                        order by
                            canonical_candidates.scope_month desc nulls last,
                            canonical_candidates.updated_at desc,
                            canonical_candidates.group_id
                    ) as logical_rank,
                    min(canonical_candidates.oa_sort_min) over logical_window as logical_oa_sort_min,
                    max(canonical_candidates.oa_sort_max) over logical_window as logical_oa_sort_max,
                    min(canonical_candidates.bank_sort_min) over logical_window as logical_bank_sort_min,
                    max(canonical_candidates.bank_sort_max) over logical_window as logical_bank_sort_max,
                    min(canonical_candidates.invoice_sort_min) over logical_window as logical_invoice_sort_min,
                    max(canonical_candidates.invoice_sort_max) over logical_window as logical_invoice_sort_max,
                    string_agg(canonical_candidates.searchable_text, ' ') over logical_window
                        as logical_searchable_text
                from canonical_candidates
                window logical_window as (partition by canonical_candidates.all_scope_group_id)
            )
        """
        searchable_text_sql = "ranked_groups.logical_searchable_text"
        oa_sort_min_sql = "ranked_groups.logical_oa_sort_min"
        oa_sort_max_sql = "ranked_groups.logical_oa_sort_max"
        bank_sort_min_sql = "ranked_groups.logical_bank_sort_min"
        bank_sort_max_sql = "ranked_groups.logical_bank_sort_max"
        invoice_sort_min_sql = "ranked_groups.logical_invoice_sort_min"
        invoice_sort_max_sql = "ranked_groups.logical_invoice_sort_max"
    else:
        ranked_groups_sql = """
            , ranked_groups as (
                select canonical_owners.*, 1::bigint as logical_rank
                from canonical_owners
            )
        """
        searchable_text_sql = "ranked_groups.searchable_text"
        oa_sort_min_sql = "ranked_groups.oa_sort_min"
        oa_sort_max_sql = "ranked_groups.oa_sort_max"
        bank_sort_min_sql = "ranked_groups.bank_sort_min"
        bank_sort_max_sql = "ranked_groups.bank_sort_max"
        invoice_sort_min_sql = "ranked_groups.invoice_sort_min"
        invoice_sort_max_sql = "ranked_groups.invoice_sort_max"
    return f"""
        (
            with active_groups as (
                select
                    g.*,
                    {logical_group_id_sql} as all_scope_group_id
                from read_model.workbench_groups g
                join read_model.workbench_generations gen
                  on gen.tenant_id = 'default'
                 and gen.scope_key = g.scope_key
                 and gen.generation_id = g.generation_id
                 and gen.status = 'active'
                where g.scope_key <> 'all'
            ), canonical_owners as (
                select distinct on (active_groups.all_scope_group_id) active_groups.*
                from active_groups
                order by
                    active_groups.all_scope_group_id,
                    case when active_groups.zone = 'paired' then 0 else 1 end,
                    active_groups.scope_month desc nulls last,
                    active_groups.updated_at desc,
                    active_groups.group_id
            )
            {ranked_groups_sql}
            select
                ranked_groups.generation_id,
                ranked_groups.all_scope_group_id as group_id,
                ranked_groups.all_scope_group_id as source_group_id,
                ranked_groups.scope_key,
                ranked_groups.scope_month,
                ranked_groups.zone,
                ranked_groups.status,
                ranked_groups.group_type,
                ranked_groups.source_kinds,
                ranked_groups.row_count,
                {searchable_text_sql} as searchable_text,
                {oa_sort_min_sql} as oa_sort_min,
                {oa_sort_max_sql} as oa_sort_max,
                {bank_sort_min_sql} as bank_sort_min,
                {bank_sort_max_sql} as bank_sort_max,
                {invoice_sort_min_sql} as invoice_sort_min,
                {invoice_sort_max_sql} as invoice_sort_max,
                ranked_groups.source_versions,
                ranked_groups.generated_at,
                ranked_groups.cache_status,
                ranked_groups.payload,
                ranked_groups.raw_payload,
                ranked_groups.updated_at
            from ranked_groups
            where ranked_groups.logical_rank = 1
        ) g
    """


def _workbench_active_month_group_keys_sql(*, include_aggregated_searchable_text: bool) -> str:
    logical_group_id_sql = _workbench_all_logical_group_id_sql("g.group_id", "g.scope_key")
    if include_aggregated_searchable_text:
        canonical_projection_sql = """
            , canonical_candidates as (
                select active_groups.*
                from active_groups
                join canonical_owners
                  on canonical_owners.all_scope_group_id = active_groups.all_scope_group_id
                 and canonical_owners.zone = active_groups.zone
            ), ranked_groups as (
                select
                    canonical_candidates.*,
                    row_number() over (
                        partition by canonical_candidates.all_scope_group_id
                        order by
                            canonical_candidates.scope_month desc nulls last,
                            canonical_candidates.updated_at desc,
                            canonical_candidates.group_id
                    ) as logical_rank,
                    string_agg(canonical_candidates.searchable_text, ' ') over (
                        partition by canonical_candidates.all_scope_group_id
                    ) as logical_searchable_text
                from canonical_candidates
            )
            select
                ranked_groups.all_scope_group_id as group_id,
                ranked_groups.zone,
                ranked_groups.status,
                ranked_groups.logical_searchable_text as searchable_text
            from ranked_groups
            where ranked_groups.logical_rank = 1
        """
    else:
        canonical_projection_sql = """
            select
                canonical_owners.all_scope_group_id as group_id,
                canonical_owners.zone,
                canonical_owners.status,
                canonical_owners.searchable_text
            from canonical_owners
        """
    return f"""
        (
            with active_groups as (
                select
                    g.scope_key,
                    g.scope_month,
                    g.zone,
                    g.group_id,
                    g.status,
                    g.searchable_text,
                    g.updated_at,
                    {logical_group_id_sql} as all_scope_group_id
                from read_model.workbench_groups g
                join read_model.workbench_generations gen
                  on gen.tenant_id = 'default'
                 and gen.scope_key = g.scope_key
                 and gen.generation_id = g.generation_id
                 and gen.status = 'active'
                where g.scope_key <> 'all'
            ), canonical_owners as (
                select distinct on (active_groups.all_scope_group_id) active_groups.*
                from active_groups
                order by
                    active_groups.all_scope_group_id,
                    case when active_groups.zone = 'paired' then 0 else 1 end,
                    active_groups.scope_month desc nulls last,
                    active_groups.updated_at desc,
                    active_groups.group_id
            )
            {canonical_projection_sql}
        ) g
    """


def _workbench_active_month_members_cte_sql() -> str:
    logical_group_id_sql = _workbench_all_logical_group_id_sql("r.group_id", "r.scope_key")
    return f"""
        active_workbench_members as not materialized (
            select
                r.scope_key,
                r.generation_id,
                r.zone,
                r.group_id,
                {logical_group_id_sql} as all_scope_group_id,
                r.pane,
                r.row_id,
                r.row_role,
                r.source_kind,
                r.time_date,
                r.column_values,
                r.searchable_text,
                r.object_identity_key
            from read_model.workbench_group_rows r
            join read_model.workbench_generations gen
              on gen.tenant_id = 'default'
             and gen.scope_key = r.scope_key
             and gen.generation_id = r.generation_id
             and gen.status = 'active'
            where r.scope_key <> 'all'
        )
    """


def _workbench_all_active_member_filter_join_sql(
    predicate_sql: str,
    *,
    row_alias: str,
    match_alias: str,
) -> str:
    return (
        "join ("
        f"select distinct {row_alias}.zone, {row_alias}.all_scope_group_id "
        f"from active_workbench_members {row_alias} where {predicate_sql}"
        f") {match_alias} on {match_alias}.zone = g.zone "
        f"and {match_alias}.all_scope_group_id = g.group_id"
    )


def _workbench_group_row_filter_exists_sql(
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
    group_id_sql: str = "g.group_id",
) -> tuple[str, list[Any]]:
    pane_exists: list[str] = []
    params: list[Any] = []
    for pane in WORKBENCH_PANES:
        row_match_clauses, row_match_params = _workbench_group_row_match_sql(
            pane,
            column_filters=column_filters,
            time_filters=time_filters,
            include_pane=True,
        )
        if not row_match_clauses:
            continue
        row_clauses = [
            "r.scope_key = g.scope_key",
            "r.generation_id = g.generation_id",
            "r.zone = g.zone",
            f"r.group_id = {group_id_sql}",
            *row_match_clauses,
        ]
        pane_exists.append(
            "exists (select 1 from read_model.workbench_group_rows r where " + " and ".join(row_clauses) + ")"
        )
        params.extend(row_match_params)
    if not pane_exists:
        return "", []
    return "(" + " and ".join(pane_exists) + ")", params


def _workbench_all_group_row_filter_joins_sql(
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
) -> tuple[list[str], list[Any]]:
    joins: list[str] = []
    params: list[Any] = []
    for pane in WORKBENCH_PANES:
        row_match_clauses, row_match_params = _workbench_group_row_match_sql(
            pane,
            column_filters=column_filters,
            time_filters=time_filters,
            include_pane=True,
        )
        if not row_match_clauses:
            continue
        joins.append(
            _workbench_all_active_member_filter_join_sql(
                " and ".join(row_match_clauses),
                row_alias="r",
                match_alias=f"{pane}_filter_match",
            )
        )
        params.extend(row_match_params)
    return joins, params


def _workbench_group_row_count_filter_sql(
    pane: str,
    *,
    column_filters: dict[str, dict[str, list[str]]],
    time_filters: dict[str, dict[str, str]],
) -> tuple[str, list[Any]]:
    row_clauses, params = _workbench_group_row_match_sql(
        pane,
        column_filters=column_filters,
        time_filters=time_filters,
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
    include_pane: bool,
) -> tuple[list[str], list[Any]]:
    pane_column_filters = column_filters.get(pane, {})
    pane_time_filter = time_filters.get(pane)
    if not pane_column_filters and not pane_time_filter:
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
            operator = " and " if pane == "bank" and column_key == "amount" else " or "
            row_clauses.append("(" + operator.join(value_match_clauses) + ")")
    if pane_time_filter:
        start_date, end_date = _workbench_time_filter_date_range(pane_time_filter)
        if start_date and end_date:
            row_clauses.append("r.time_date >= %s::date and r.time_date < %s::date")
            row_params.extend([start_date, end_date])
    return row_clauses, row_params


def _summarize_workbench_payload_groups(payload: dict[str, Any]) -> dict[str, Any]:
    summary = {
        "oa_count": 0,
        "bank_count": 0,
        "invoice_count": 0,
        "paired_count": 0,
        "unpaired_count": 0,
        "exception_count": 0,
        "zone_counts": _empty_workbench_zone_counts(),
    }
    seen_rows: set[tuple[str, str]] = set()
    seen_rows_by_zone: dict[str, set[tuple[str, str]]] = {"paired": set(), "unpaired": set()}
    for zone in ("paired", "unpaired"):
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
            if zone == "unpaired" and _workbench_group_has_danger(group):
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


def _workbench_existing_group_sort_keys(group: dict[str, Any]) -> dict[str, str | None]:
    keys = (
        "oa_sort_min",
        "oa_sort_max",
        "bank_sort_min",
        "bank_sort_max",
        "invoice_sort_min",
        "invoice_sort_max",
    )
    result = {key: text(group.get(key)) for key in keys}
    if any(value is not None for value in result.values()):
        return result
    return _workbench_group_sort_keys(group)


def _searchable_row_text(row: dict[str, Any], pane_id: str) -> str:
    values = [
        text(row.get("label")),
        text(row.get("status")),
        text(row.get("category_label") or row.get("categoryLabel")),
        text(row.get("counterparty") or row.get("counterparty_name")),
    ]
    values.extend(text(value) for value in _workbench_row_column_values(row, pane_id).values())
    values.append(text(row.get("amount_value")))
    tags = row.get("tags")
    if isinstance(tags, list):
        values.extend(text(tag) for tag in tags)
    bank_text_fields = row.get("bank_text_fields") or row.get("bankTextFields")
    if isinstance(bank_text_fields, list):
        for field in bank_text_fields:
            if isinstance(field, dict):
                values.extend((text(field.get("label")), text(field.get("value"))))
    values.extend(_workbench_row_display_search_aliases(row, pane_id))
    return " ".join(value for value in values if value)


def _workbench_row_display_search_aliases(row: dict[str, Any], pane_id: str) -> list[str]:
    if pane_id == "bank":
        account_label = text(_workbench_row_column_values(row, pane_id).get("paymentAccount")) or ""
        for bank_name, short_name in WORKBENCH_COMPACT_BANK_NAMES.items():
            if account_label == bank_name:
                return [short_name]
            if account_label.startswith(f"{bank_name} "):
                return [f"{short_name}{account_label[len(bank_name):]}"]
        return []
    if pane_id != "invoice":
        return []
    invoice_type = text(_workbench_row_column_values(row, pane_id).get("invoiceType")) or ""
    normalized_invoice_type = invoice_type.lower()
    flow_label = None
    if any(value in normalized_invoice_type for value in ("销", "output", "sale")):
        flow_label = "销"
    elif any(value in normalized_invoice_type for value in ("进", "input", "purchase")):
        flow_label = "进"
    source_kind = text(row.get("source_kind") or row.get("sourceKind"))
    source_label = (
        WORKBENCH_INVOICE_SOURCE_LABELS.get(source_kind or "", "人工导入")
        if flow_label or source_kind
        else None
    )
    return [value for value in (flow_label, source_label) if value]


def _workbench_group_row_records(group: dict[str, Any]) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    group_id = text(group.get("group_id") or group.get("id"))
    zone = text(group.get("zone") or group.get("status")) or "unpaired"
    if group_id is None:
        return records
    for pane, row_role, row_index, row in _iter_typed_group_rows_with_metadata(group):
        row_id = text(row.get("id") or row.get("row_id"))
        if row_id is None:
            continue
        source_kind = text(row.get("source_kind") or row.get("type") or pane) or pane
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
                "source_kind": source_kind,
                "status": text(row.get("status") or zone) or zone,
                "time_value": time_value,
                "time_date": _workbench_date_from_text(time_value),
                "column_values": column_values,
                "searchable_text": _searchable_row_text(row, pane),
                "object_identity_key": text(row.get("object_identity_key")),
                "object_identity_kind": text(row.get("object_identity_kind")),
                "object_identity_source": text(row.get("object_identity_source")),
                "object_identity_confidence": text(row.get("object_identity_confidence")),
            }
        )
    return records


def _workbench_row_payload_for_write(row: dict[str, Any]) -> dict[str, Any]:
    payload = _sanitize_workbench_row_for_read_model(row)
    for key in WORKBENCH_ROW_PAYLOAD_PRUNED_KEYS:
        payload.pop(key, None)
    return serialize_value(payload)


def _workbench_group_payload_for_rows(group: dict[str, Any], *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source_payload = payload if isinstance(payload, dict) else group.get("payload")
    payload = dict(source_payload if isinstance(source_payload, dict) else group)
    payload.setdefault("group_id", text(group.get("group_id") or group.get("id")))
    payload.setdefault("zone", text(group.get("zone") or group.get("status")) or "unpaired")
    payload.setdefault("status", text(group.get("status") or group.get("zone")) or "unpaired")
    payload.setdefault("scope_month", group.get("scope_month"))
    payload.setdefault("month", group.get("month"))
    return payload


def _workbench_group_payload_for_write(group: dict[str, Any], *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source_payload = payload if isinstance(payload, dict) else group.get("payload")
    normalized = dict(source_payload if isinstance(source_payload, dict) else group)
    for key in list(normalized):
        if str(key).endswith("_rows") or str(key) in WORKBENCH_GROUP_MEMBER_PAYLOAD_KEYS:
            normalized.pop(key, None)
    normalized.setdefault("group_id", text(group.get("group_id") or group.get("id")))
    normalized.setdefault("zone", text(group.get("zone") or group.get("status")) or "unpaired")
    normalized.setdefault("status", text(group.get("status") or group.get("zone")) or "unpaired")
    normalized.setdefault("scope_month", group.get("scope_month"))
    normalized.setdefault("month", group.get("month"))
    normalized["workbench_group_rows_materialized"] = True
    return serialize_value(normalized)


def _workbench_group_payload_requires_row_materialization(payload: dict[str, Any]) -> bool:
    return payload.get("workbench_group_rows_materialized") is True


def _materialize_workbench_group_payload(group: dict[str, Any], member_rows: list[dict[str, Any]]) -> dict[str, Any]:
    if not _workbench_group_payload_requires_row_materialization(group):
        return group
    result = dict(group)
    result.pop("workbench_group_rows_materialized", None)
    for key in WORKBENCH_GROUP_MEMBER_PAYLOAD_KEYS:
        result.pop(key, None)
    collapsed_rows: dict[str, list[dict[str, Any]]] = {}
    visible_row_keys: set[tuple[str, str]] = set()
    for member in member_rows:
        pane = text(member.get("pane")) or "rows"
        row_id = text(member.get("row_id"))
        row = row_payload(member, "row_payload", "row_raw_payload", "member_payload", "member_raw_payload")
        if isinstance(row, dict):
            row_payload_value = dict(row)
        else:
            row_payload_value = {}
        if row_id:
            row_payload_value.setdefault("id", row_id)
            row_payload_value.setdefault("row_id", row_id)
        row_payload_value.setdefault("type", pane)
        source_kind = text(member.get("source_kind"))
        if source_kind:
            row_payload_value.setdefault("source_kind", source_kind)
        status = text(member.get("status"))
        if status:
            row_payload_value.setdefault("status", status)
        for key in (
            "object_identity_key",
            "object_identity_kind",
            "object_identity_source",
            "object_identity_confidence",
        ):
            value = text(member.get(key))
            if value is not None:
                row_payload_value.setdefault(key, value)
        row_role = text(member.get("row_role")) or "normal"
        if row_role == "collapsed":
            collapsed_rows.setdefault(pane, []).append(row_payload_value)
            continue
        visible_row_key = (pane, row_id or "")
        if row_id and visible_row_key in visible_row_keys:
            continue
        if row_id:
            visible_row_keys.add(visible_row_key)
        result.setdefault(f"{pane}_rows", []).append(row_payload_value)
    for pane in ("oa", "bank", "invoice"):
        result.setdefault(f"{pane}_rows", [])
    if collapsed_rows:
        result["collapsed_rows"] = collapsed_rows
    return result


def _workbench_group_row_minimal_payload(
    row_payload: dict[str, Any],
    *,
    pane: str,
    row_id: str | None,
    source_kind: str | None,
) -> dict[str, Any]:
    result: dict[str, Any] = {
        "row_id": text(row_id or row_payload.get("row_id") or row_payload.get("id")),
        "type": text(row_payload.get("type") or row_payload.get("record_type") or pane),
        "source_kind": text(source_kind or row_payload.get("source_kind")),
    }
    for key in (
        "case_id",
        "relation_id",
        "relation_mode",
        "source_oa_id",
        "source_oa_row_id",
        "oa_row_id",
        "derived_from_oa_id",
    ):
        value = text(row_payload.get(key))
        if value is not None:
            result[key] = value
    special_metadata = row_payload.get("special_metadata")
    if isinstance(special_metadata, dict):
        for key in ("source_oa_id", "source_oa_row_id", "oa_row_id"):
            value = text(special_metadata.get(key))
            if value is not None and key not in result:
                result[key] = value
    return {key: value for key, value in serialize_value(result).items() if value not in (None, "")}


def _workbench_group_row_payload_for_write(group_row: dict[str, Any]) -> dict[str, Any]:
    row_payload = group_row.get("payload") if isinstance(group_row.get("payload"), dict) else {}
    return _workbench_group_row_minimal_payload(
        row_payload,
        pane=text(group_row.get("pane")) or "",
        row_id=text(group_row.get("row_id") or row_payload.get("row_id") or row_payload.get("id")),
        source_kind=text(group_row.get("source_kind") or row_payload.get("source_kind")),
    )


def _workbench_snapshot_payload_for_write(
    *,
    scope_key: str,
    scope_month: Any,
    grouped_payload: dict[str, Any],
    source_versions: dict[str, Any],
    generated_at: str | None,
    cache_status: str,
) -> dict[str, Any]:
    summary = grouped_payload.get("summary") if isinstance(grouped_payload.get("summary"), dict) else {}
    payload: dict[str, Any] = {
        "month": grouped_payload.get("month") or scope_key,
        "scope_key": scope_key,
        "scope_month": scope_month,
        "summary": serialize_value(summary),
        "paired": {"groups": []},
        "unpaired": {"groups": []},
        "workbench_groups_materialized": True,
    }
    for key in (
        "oa_status",
        "workbench_read_model_schema_version",
        "oa_attachment_invoice_parser_version",
        "oa_projection_sync_version",
        "page_mode",
    ):
        if key in grouped_payload:
            payload[key] = serialize_value(grouped_payload.get(key))
    return {
        "scope_key": scope_key,
        "scope_month": scope_month,
        "generated_at": generated_at,
        "cache_status": cache_status,
        "payload": payload,
        "source_versions": serialize_value(source_versions),
    }


def _input_invoice_usage_payload_invoice_ids(row: dict[str, Any], payload: dict[str, Any]) -> list[str]:
    invoice = payload.get("invoice") if isinstance(payload.get("invoice"), dict) else {}
    relation_payload = payload.get("invoiceRelations") if isinstance(payload.get("invoiceRelations"), dict) else {}
    summaries = relation_payload.get("summaries") if isinstance(relation_payload.get("summaries"), list) else []
    return _dedupe_preserve_order(
        [
            row.get("invoice_id"),
            payload.get("invoiceId"),
            invoice.get("primaryInvoiceId"),
            invoice.get("id"),
            *[
                summary.get("invoiceId")
                for summary in summaries
                if isinstance(summary, dict)
            ],
        ]
    )


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


def _expected_workbench_groups_builder(scope_key: str) -> str | None:
    normalized = str(scope_key or "").strip()
    if MONTH_SCOPE_RE.fullmatch(normalized):
        return WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION
    if normalized == "all":
        return WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION
    return None


def _workbench_composed_all_source_versions(rows: list[dict[str, Any]]) -> dict[str, Any]:
    source_versions_rows = [
        row.get("source_versions")
        for row in list(rows or [])
        if isinstance(row, dict) and isinstance(row.get("source_versions"), dict)
    ]
    result: dict[str, Any] = {
        "builder": WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
        "source_version": max((_source_version_value(versions) or 0 for versions in source_versions_rows), default=0),
    }
    for key in (
        "oa_attachment_invoice_parser_version",
        "bank_auto_tag_rules_version",
        "bank_account_mappings_fingerprint",
        "oa_projection_sync_version",
        "workbench_formal_relation_rule_version",
    ):
        observed = [text(versions.get(key)) for versions in source_versions_rows]
        values = {value for value in observed if value}
        if observed and len(values) == 1 and all(observed):
            result[key] = next(iter(values))
    for key in (
        "workbench_pair_relations_updated_at",
        "workbench_exception_cases_updated_at",
        "workbench_row_overrides_updated_at",
        "oa_pending_payment_bank_claims_updated_at",
        "bank_transactions_updated_at",
        "invoices_updated_at",
        "oa_projection_updated_at",
        "etc_submission_batches_updated_at",
        "etc_business_batches_updated_at",
        "etc_invoices_updated_at",
        "etc_batch_invoice_links_updated_at",
    ):
        latest = max((text(versions.get(key)) or "" for versions in source_versions_rows), default="")
        if latest:
            result[key] = latest
    return result


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
