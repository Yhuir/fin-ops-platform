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

from fin_ops_platform.services.bank_transaction_category_service import BANK_TRANSACTION_CATEGORY_COUNT_KEYS
from fin_ops_platform.services.cost_statistics_source_versions import COST_STATISTICS_READ_MODEL_SCHEMA_VERSION
from fin_ops_platform.services.pending_invoice_status import pending_invoice_filter_status_codes
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
from fin_ops_platform.services.runtime_queue import RuntimeQueueRepository
from fin_ops_platform.services.workbench_read_model_version import (
    WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
    WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION,
    WorkbenchReadModelVersionConflictError,
)
MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")
BANK_DETAIL_READ_MODEL_SCHEMA_VERSION = 11
BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE = hashlib.sha256(b"[]").hexdigest()
BANK_ACCOUNT_BALANCE_READ_MODEL_SCHEMA_VERSION = 1
BANK_DETAIL_PURPOSE_TEXT_LABELS = ("用途", "交易用途")
BANK_DETAIL_SUMMARY_TEXT_LABELS = ("摘要",)
BANK_DETAIL_NOTE_TEXT_LABELS = ("备注", "附言", "客户附言")
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
NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND = "no_oa_bank_batch_summary"
BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND = "bank_flow_rule_batch_summary"
WORKBENCH_BANK_BATCH_SUMMARY_SOURCE_KINDS = frozenset(
    {NO_OA_BANK_BATCH_SUMMARY_SOURCE_KIND, BANK_FLOW_RULE_BATCH_SUMMARY_SOURCE_KIND}
)
WORKBENCH_ROW_PAYLOAD_PRUNED_KEYS = {"object_identity"}


class TurnoverLedgerGenerationConflictError(RuntimeError):
    pass
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
    """Return the canonical all-scope group fields required by filters and counts only."""
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
        active_workbench_members as materialized (
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


def _should_execute_many_values(sql: str) -> bool:
    normalized = " ".join(str(sql or "").lower().split())
    return (
        "insert into read_model.workbench_rows" in normalized
        or "insert into read_model.workbench_groups" in normalized
        or "insert into read_model.workbench_group_rows" in normalized
        or "insert into read_model.workbench_relation_rows" in normalized
        or "insert into read_model.workbench_relation_groups" in normalized
        or "insert into read_model.search_index_rows" in normalized
        or "insert into read_model.turnover_ledger_rows" in normalized
        or "insert into read_model.bank_account_balances" in normalized
        or "insert into read_model.oa_pending_payment_rows" in normalized
    )


def _supports_execute_many_values_params(params_seq: list[Any]) -> bool:
    return all(not isinstance(params, Mapping) for params in params_seq)


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


class PostgresInvoiceUsageCollectionReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection

    @contextmanager
    def oa_pending_payment_read_snapshot(self):
        transaction_factory = getattr(self._connection, "transaction", None)
        if not callable(transaction_factory):
            yield self
            return
        with transaction_factory() as transaction:
            transaction.execute("set transaction isolation level repeatable read read only")
            yield PostgresInvoiceUsageCollectionReadModelRepository(transaction)

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
        include_statistics: bool = True,
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
            dedupe_all_scope_by_row_id=True,
            include_statistics=include_statistics,
        )

    def input_invoice_usage_scope_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._invoice_relation_scope_source_versions(
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_type="input_invoice_usage",
            scope_key=scope_key,
            tenant_id=tenant_id,
        )

    def list_input_invoice_usage_filter_options(
        self,
        *,
        month: str | None = None,
        keyword: str | None = None,
        invoice_date_from: str | None = None,
        invoice_date_to: str | None = None,
        filters: str | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        return self._list_invoice_relation_filter_options(
            table_name="read_model.input_invoice_usage_rows",
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_type="input_invoice_usage",
            month=month,
            keyword=keyword,
            invoice_date_from=invoice_date_from,
            invoice_date_to=invoice_date_to,
            filters=filters,
            filter_fields=INPUT_INVOICE_USAGE_FILTER_FIELDS,
            option_fields=INPUT_INVOICE_USAGE_OPTION_FIELDS,
        )

    def save_input_invoice_usage_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        statistics_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._save_invoice_relation_rows(
            table_name="read_model.input_invoice_usage_rows",
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_type="input_invoice_usage",
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
            row_builder=_input_invoice_usage_read_model_record,
            statistics_metadata=statistics_metadata,
        )

    def mark_input_invoice_usage_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
        statistics_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._mark_invoice_relation_scope(
            scope_table_name="read_model.input_invoice_usage_scopes",
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
            statistics_metadata=statistics_metadata,
        )

    def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._prune_invoice_relation_scope_shards(
            table_name="read_model.input_invoice_usage_rows",
            scope_table_name="read_model.input_invoice_usage_scopes",
            current_scope_keys=current_scope_keys,
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

    def list_input_invoice_usage_rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, Any] | None:
        normalized_ids = _dedupe_preserve_order(invoice_ids)
        if not normalized_ids:
            return {
                "rows": [],
                "missing_invoice_ids": [],
                "refresh_status": "fresh",
                "source_versions_by_scope": {},
                "read_model_scope_keys": [],
            }
        rows = self._connection.fetch_all(
            """
            select invoice_id, scope_key, source_versions, payload, raw_payload
            from read_model.input_invoice_usage_rows
            where invoice_id = any(%s)
               or exists (
                    select 1
                    from jsonb_array_elements(
                        case
                            when jsonb_typeof(payload->'invoiceRelations'->'summaries') = 'array'
                            then payload->'invoiceRelations'->'summaries'
                            else '[]'::jsonb
                        end
                    ) as member
                    where member->>'invoiceId' = any(%s)
               )
            order by generated_at desc, scope_key desc, row_id
            """,
            (normalized_ids, normalized_ids),
        )
        rows_by_invoice_id: dict[str, dict[str, Any]] = {}
        source_versions_by_scope: dict[str, dict[str, Any]] = {}
        requested_ids = set(normalized_ids)
        for row in rows:
            if not isinstance(row, dict):
                continue
            payload = _read_model_payload(row)
            if not isinstance(payload, dict):
                continue
            for invoice_id in _input_invoice_usage_payload_invoice_ids(row, payload):
                if invoice_id in requested_ids and invoice_id not in rows_by_invoice_id:
                    rows_by_invoice_id[invoice_id] = payload
            scope_key = text(row.get("scope_key")) or "all"
            source_versions_by_scope.setdefault(
                scope_key,
                row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
            )
        if not source_versions_by_scope:
            scope_row = self._invoice_relation_scope_row(
                scope_table_name="read_model.input_invoice_usage_scopes",
                scope_key="all",
            )
            if scope_row is None:
                return None
            source_versions_by_scope["all"] = (
                scope_row.get("source_versions")
                if isinstance(scope_row.get("source_versions"), dict)
                else {}
            )
        missing_invoice_ids = [invoice_id for invoice_id in normalized_ids if invoice_id not in rows_by_invoice_id]
        if missing_invoice_ids and "all" not in source_versions_by_scope:
            scope_row = self._invoice_relation_scope_row(
                scope_table_name="read_model.input_invoice_usage_scopes",
                scope_key="all",
            )
            if scope_row is None:
                return None
            source_versions_by_scope["all"] = (
                scope_row.get("source_versions")
                if isinstance(scope_row.get("source_versions"), dict)
                else {}
            )
        scope_keys = sorted(source_versions_by_scope) or ["all"]
        refresh_status = "fresh"
        for scope_key in scope_keys:
            scope_status = self._invoice_relation_refresh_status(
                scope_type="input_invoice_usage",
                scope_key=scope_key,
            )
            if scope_status != "fresh":
                refresh_status = scope_status
                break
        ordered_rows = []
        seen_row_ids: set[str] = set()
        for invoice_id in normalized_ids:
            row = rows_by_invoice_id.get(invoice_id)
            if row is None:
                continue
            row_id = text(row.get("id")) or invoice_id
            if row_id in seen_row_ids:
                continue
            seen_row_ids.add(row_id)
            ordered_rows.append(row)
        return {
            "rows": ordered_rows,
            "missing_invoice_ids": missing_invoice_ids,
            "refresh_status": refresh_status,
            "source_versions_by_scope": source_versions_by_scope,
            "read_model_scope_keys": scope_keys,
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
        include_statistics: bool = True,
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
            include_statistics=include_statistics,
        )

    def output_invoice_collection_scope_source_versions(
        self,
        *,
        scope_key: str,
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        return self._invoice_relation_scope_source_versions(
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_type="output_invoice_collection",
            scope_key=scope_key,
            tenant_id=tenant_id,
        )

    def get_output_invoice_collection_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        row = self._connection.fetch_one(
            """
            select scope_key, source_versions, payload, raw_payload
            from read_model.output_invoice_collection_rows
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
                scope_type="output_invoice_collection",
                scope_key=scope_key,
            ),
            "source_versions": source_versions,
            "read_model_scope_key": scope_key,
        }

    def save_output_invoice_collection_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        statistics_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._save_invoice_relation_rows(
            table_name="read_model.output_invoice_collection_rows",
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_type="output_invoice_collection",
            scope_key=scope_key,
            rows=rows,
            source_versions=source_versions,
            row_builder=_output_invoice_collection_read_model_record,
            statistics_metadata=statistics_metadata,
        )

    def mark_output_invoice_collection_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
        statistics_metadata: dict[str, Any] | None = None,
    ) -> None:
        self._mark_invoice_relation_scope(
            scope_table_name="read_model.output_invoice_collection_scopes",
            scope_key=scope_key,
            row_count=row_count,
            source_versions=source_versions,
            statistics_metadata=statistics_metadata,
        )

    def prune_output_invoice_collection_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._prune_invoice_relation_scope_shards(
            table_name="read_model.output_invoice_collection_rows",
            scope_table_name="read_model.output_invoice_collection_scopes",
            current_scope_keys=current_scope_keys,
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
        rows_source_sql = "read_model.oa_pending_payment_rows"
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
        option_values_sql = ",\n                        ".join(
            f"('{field}', nullif(btrim(({expression})::text), ''), "
            f"nullif(btrim(({_invoice_relation_option_label_expression(field, expression)})::text), ''))"
            for field, (expression, _mode, _operators) in OA_PENDING_PAYMENT_OPTION_FIELDS.items()
        )
        order_sql = _invoice_relation_order_sql(
            sort_field=sort_field,
            sort_direction=sort_direction,
            sort_expressions=OA_PENDING_PAYMENT_SORT_EXPRESSIONS,
        )
        summary_row = self._connection.fetch_one(
            f"""
            with base_rows as materialized (
                select
                    oa_amount,
                    bank_paid_total,
                    bank_amount,
                    oa_id,
                    oa_ids,
                    oa_workflow_status,
                    payment_status,
                    payment_status_label,
                    oa_applicant,
                    oa_application_type,
                    oa_project_name,
                    bank_name,
                    bank_account,
                    bank_direction,
                    bank_counterparty_name,
                    seller_name
                from {rows_source_sql}
                where {base_where_sql}
            ),
            filtered_rows as materialized (
                select *
                from base_rows
                where {view_mode_clause or 'true'}
            ),
            summary as (
                select
                    count(*) as count,
                    coalesce(sum(oa_amount), 0) as oa_amount_total,
                    coalesce(sum(coalesce(bank_paid_total, bank_amount)), 0) as bank_paid_total
                from filtered_rows
            ),
            view_counts as (
                select
                    count(distinct oa_id_value) filter (
                        where oa_workflow_status is null
                           or oa_workflow_status = ''
                           or oa_workflow_status = 'completed'
                    ) as completed_count,
                    count(distinct oa_id_value) filter (
                        where oa_workflow_status = 'in_progress'
                    ) as in_progress_count
                from base_rows
                cross join lateral unnest(
                    case
                        when cardinality(oa_ids) > 0 then oa_ids
                        when oa_id is not null and oa_id <> '' then array[oa_id]
                        else array[]::text[]
                    end
                ) as expanded_oa(oa_id_value)
            ),
            status_counts as (
                select coalesce(jsonb_object_agg(payment_status, status_count), '{{}}'::jsonb) as payload
                from (
                    select payment_status, count(*)::integer as status_count
                    from filtered_rows
                    where payment_status is not null and payment_status <> ''
                    group by payment_status
                ) grouped_statuses
            ),
            option_values(field, value, label) as (
                select option_value.field, option_value.value, option_value.label
                from filtered_rows
                cross join lateral (
                    values
                        {option_values_sql}
                ) as option_value(field, value, label)
            ),
            options_by_field as (
                select field, jsonb_agg(
                    jsonb_build_object(
                        'value', value,
                        'label', coalesce(label, value),
                        'count', option_count
                    )
                    order by value
                ) as options
                from (
                    select field, value, max(label) as label, count(*)::integer as option_count
                    from option_values
                    where value is not null
                    group by field, value
                ) option_counts
                group by field
            ),
            filter_options as (
                select coalesce(jsonb_object_agg(field, options), '{{}}'::jsonb) as payload
                from options_by_field
            ),
            statistics_scopes as (
                select raw_payload->'statistics' as statistics
                from read_model.oa_pending_payment_scopes
                where scope_key <> 'all'
                union all
                select raw_payload->'statistics' as statistics
                from read_model.oa_pending_payment_scopes
                where scope_key = 'all'
                  and not exists (
                      select 1 from read_model.oa_pending_payment_scopes where scope_key <> 'all'
                  )
            ),
            page_statistics as (
                select coalesce(jsonb_agg(statistics), '[]'::jsonb) as payload
                from statistics_scopes
            ),
            paged_rows as materialized (
                select
                    payload - 'searchText' - 'sourceVersions' - 'source_versions' as payload,
                    row_number() over (order by {order_sql}) as row_order
                from {rows_source_sql}
                where {where_sql}
                order by {order_sql}
                limit %s offset %s
            ),
            page_rows as (
                select coalesce(
                    jsonb_agg(jsonb_build_object('payload', payload) order by row_order),
                    '[]'::jsonb
                ) as payload
                from paged_rows
            )
            select
                summary.count,
                summary.oa_amount_total,
                summary.bank_paid_total,
                view_counts.completed_count,
                view_counts.in_progress_count,
                status_counts.payload as status_counts,
                filter_options.payload as filter_options,
                page_statistics.payload as page_statistics,
                page_rows.payload as rows
            from summary
            cross join view_counts
            cross join status_counts
            cross join filter_options
            cross join page_statistics
            cross join page_rows
            """,
            tuple([*base_params, *params, page_limit, (page_number - 1) * page_limit]),
        )
        view_counts = {
            "completed": int_value(summary_row.get("completed_count") if isinstance(summary_row, dict) else 0, 0),
            "in_progress": int_value(summary_row.get("in_progress_count") if isinstance(summary_row, dict) else 0, 0),
        }
        total = int_value(summary_row.get("count") if isinstance(summary_row, dict) else 0, 0)
        rows = list(summary_row.get("rows") or []) if isinstance(summary_row, dict) else []
        payload_rows = [_read_model_payload(row) for row in rows]
        filter_options = summary_row.get("filter_options") if isinstance(summary_row, dict) else {}
        normalized_filter_options = {
            field: [dict(option) for option in list(options or []) if isinstance(option, dict)]
            for field, options in dict(filter_options or {}).items()
            if field in OA_PENDING_PAYMENT_OPTION_FIELDS
        }
        for option in normalized_filter_options.get("bank_direction", []):
            value = text(option.get("value")) or ""
            option["label"] = "支出" if value == "outflow" else "收入" if value == "inflow" else value
        statistics = self._oa_pending_payment_statistics(
            summary_row.get("page_statistics") if isinstance(summary_row, dict) else None
        )
        return {
            "rows": [row for row in payload_rows if isinstance(row, dict)],
            "pagination": {"page": page_number, "pageSize": page_limit, "total": total},
            "summary": {
                "rowCount": total,
                "oaAmountTotal": decimal_text(summary_row.get("oa_amount_total") if isinstance(summary_row, dict) else None) or "0.00",
                "bankPaidTotal": decimal_text(summary_row.get("bank_paid_total") if isinstance(summary_row, dict) else None) or "0.00",
                "statusCounts": dict(summary_row.get("status_counts") or {}) if isinstance(summary_row, dict) else {},
                "viewCounts": view_counts,
            },
            "statistics": statistics,
            "filterOptions": normalized_filter_options,
            "read_model_scope_key": scope_key,
        }

    @staticmethod
    def _oa_pending_payment_statistics(values: Any) -> dict[str, int] | None:
        rows = list(values) if isinstance(values, list) else []
        keys = (
            "oa_count",
            "bank_transaction_count",
            "input_invoice_count",
            "paid_oa_count",
            "completed_oa_count",
            "in_progress_oa_count",
            "expense_transaction_count",
            "income_transaction_count",
            "unpaid_oa_count",
            "linked_bank_oa_count",
            "linked_input_invoice_oa_count",
        )
        result = {key: 0 for key in keys}
        if not rows:
            return None
        for statistics in rows:
            if not isinstance(statistics, dict) or any(
                isinstance(statistics.get(key), bool) or not isinstance(statistics.get(key), int)
                for key in keys
            ):
                return None
            for key in keys:
                result[key] += statistics[key]
        return result

    def list_oa_pending_payment_lifecycle_source_rows(
        self,
        *,
        month: str,
        page: int | str | None = 1,
        page_size: int | str | None = 200,
        sort_field: str | None = "bank_trade_time",
        sort_direction: str | None = "desc",
        view_mode: str | None = "completed",
    ) -> dict[str, Any] | None:
        with self.oa_pending_payment_read_snapshot() as snapshot:
            return snapshot._list_oa_pending_payment_lifecycle_source_rows_in_snapshot(
                month=month,
                page=page,
                page_size=page_size,
                sort_field=sort_field,
                sort_direction=sort_direction,
                view_mode=view_mode,
            )

    def _list_oa_pending_payment_lifecycle_source_rows_in_snapshot(
        self,
        *,
        month: str,
        page: int | str | None,
        page_size: int | str | None,
        sort_field: str | None,
        sort_direction: str | None,
        view_mode: str | None,
    ) -> dict[str, Any] | None:
        scope_key = _invoice_relation_scope_key(month)
        if scope_key == "all":
            raise ValueError("OA pending payment lifecycle source month must be YYYY-MM.")
        scope_row = self._invoice_relation_scope_row(
            scope_table_name="read_model.oa_pending_payment_scopes",
            scope_key=scope_key,
        )
        if scope_row is None:
            return None
        refresh_status = self._invoice_relation_refresh_status(
            scope_type="oa_pending_payment",
            scope_key=scope_key,
        )
        source_versions = (
            dict(scope_row.get("source_versions"))
            if isinstance(scope_row.get("source_versions"), dict)
            else {}
        )
        if refresh_status != "fresh":
            return {
                "rows": [],
                "pagination": {"page": max(int_value(page, 1), 1), "pageSize": min(max(int_value(page_size, 200), 1), 200), "total": 0},
                "refresh_status": refresh_status,
                "source_versions": source_versions,
                "read_model_scope_key": scope_key,
            }
        payload = self.list_oa_pending_payment_rows(
            month=scope_key,
            sort_field=sort_field,
            sort_direction=sort_direction,
            page=page,
            page_size=page_size,
            view_mode=view_mode,
        )
        if not isinstance(payload, dict):
            return None
        return {
            **payload,
            "refresh_status": "fresh",
            "source_versions": source_versions,
            "read_model_scope_key": scope_key,
        }

    def oa_pending_payment_query_state(
        self,
        *,
        scope_key: str,
        tenant_id: str,
        base_source_versions: dict[str, object],
    ) -> dict[str, Any]:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        normalized_tenant_id = text(tenant_id) or "default"
        source_prefix = f"oa_pending_payment_source:{normalized_tenant_id}:"
        pending_relation_prefix = f"oa_pending_payment_relation:{normalized_tenant_id}:"
        rows = self._connection.fetch_all(
            """
            /* check: oa_pending_payment_query_state */
            with requested as (
                select %s::text as scope_key, %s::text as tenant_id
            ), target_scopes as (
                select scope_key
                from requested
                where scope_key <> 'all'
                union
                select substring(watermark.sync_key from length(%s) + 1)
                from app.oa_sync_watermarks watermark, requested
                where requested.scope_key = 'all'
                  and watermark.sync_key like %s
                union
                select scope.scope_key
                from read_model.oa_pending_payment_scopes scope, requested
                where requested.scope_key = 'all'
                union
                select dirty.scope_key
                from job.read_model_dirty_scopes dirty, requested
                where requested.scope_key = 'all'
                  and dirty.tenant_id = requested.tenant_id
                  and dirty.scope_type = 'oa_pending_payment'
                  and dirty.status in ('pending', 'processing', 'failed')
                union
                select outbox.scope_key
                from job.outbox_events outbox, requested
                where requested.scope_key = 'all'
                  and outbox.tenant_id = requested.tenant_id
                  and outbox.event_type = 'oa_pending_payment.read_model.refresh'
                  and outbox.scope_key is not null
                  and outbox.status in ('pending', 'processing', 'failed', 'dead_lettered')
            )
            select
                target.scope_key,
                scope.row_count,
                scope.generated_at,
                scope.cache_status,
                scope.source_versions as actual_source_versions,
                source_watermark.status as source_status,
                source_watermark.version as source_snapshot_version,
                source_watermark.payload as source_payload,
                pending_relation_watermark.version as pending_relation_version,
                latest_dirty.status as dirty_status,
                latest_dirty.source_version as dirty_source_version,
                exists (
                    select 1
                    from job.outbox_events outbox
                    where outbox.tenant_id = %s
                      and outbox.event_type = 'oa_pending_payment.read_model.refresh'
                      and outbox.scope_key = target.scope_key
                      and outbox.status in ('pending', 'processing', 'failed', 'dead_lettered')
                ) as outbox_blocking
            from target_scopes target
            cross join requested
            left join read_model.oa_pending_payment_scopes scope
              on scope.scope_key = target.scope_key
            left join app.oa_sync_watermarks source_watermark
              on source_watermark.sync_key = %s || target.scope_key
            left join app.oa_sync_watermarks pending_relation_watermark
              on pending_relation_watermark.sync_key = %s || target.scope_key
            left join lateral (
                select dirty.status, dirty.source_version
                from job.read_model_dirty_scopes dirty
                where dirty.tenant_id = %s
                  and dirty.scope_type = 'oa_pending_payment'
                  and dirty.scope_key = target.scope_key
                order by dirty.source_version desc, dirty.updated_at desc, dirty.id desc
                limit 1
            ) latest_dirty on true
            order by target.scope_key
            """,
            (
                normalized_scope_key,
                normalized_tenant_id,
                source_prefix,
                f"{source_prefix}%",
                normalized_tenant_id,
                source_prefix,
                pending_relation_prefix,
                normalized_tenant_id,
            ),
        )
        state_rows = [dict(row) for row in rows if isinstance(row, dict)]
        month_rows = [row for row in state_rows if MONTH_SCOPE_RE.match(text(row.get("scope_key")) or "")]
        control_rows = [row for row in state_rows if text(row.get("scope_key")) == "all"]
        blocking_scope_keys: set[str] = set()
        stale_reasons: list[str] = []
        actual_versions_by_scope: dict[str, dict[str, Any]] = {}
        expected_versions_by_scope: dict[str, dict[str, Any]] = {}
        token_rows: list[dict[str, Any]] = []

        for row in month_rows:
            row_scope_key = text(row.get("scope_key")) or ""
            source_payload = row.get("source_payload") if isinstance(row.get("source_payload"), dict) else {}
            actual_versions = (
                dict(row.get("actual_source_versions"))
                if isinstance(row.get("actual_source_versions"), dict)
                else {}
            )
            coverage_only = (
                int_value(
                    actual_versions.get("oa_pending_payment_coverage_only_schema_version"),
                    0,
                )
                == OA_PENDING_PAYMENT_COVERAGE_ONLY_SCHEMA_VERSION
                and row.get("source_snapshot_version") is None
            )
            if coverage_only:
                expected_versions: dict[str, Any] = {
                    **dict(base_source_versions),
                    **oa_pending_payment_coverage_only_source_versions(row_scope_key),
                    "oa_pending_payment_relation_version": int_value(row.get("pending_relation_version"), 0),
                    "oa_pending_payment_event_source_version": int_value(row.get("dirty_source_version"), -1),
                }
            else:
                expected_versions = {
                    **dict(base_source_versions),
                    "oa_pending_payment_source_snapshot_version": int_value(row.get("source_snapshot_version"), 0),
                    "completed_oa_signature": text(source_payload.get("completed_oa_signature")) or "",
                    "in_progress_admission_signature": text(source_payload.get("admission_signature")) or "",
                    "payment_status_signature": text(source_payload.get("payment_status_signature")) or "",
                    "oa_pending_payment_source_signature": text(source_payload.get("source_signature")) or "",
                    "oa_pending_payment_relation_version": int_value(row.get("pending_relation_version"), 0),
                    "oa_pending_payment_event_source_version": int_value(row.get("dirty_source_version"), -1),
                }
            bank_coverage_signature = text(
                actual_versions.get("oa_pending_payment_bank_coverage_signature")
            ) or ""
            input_invoice_coverage_signature = text(
                actual_versions.get("oa_pending_payment_input_invoice_coverage_signature")
            ) or ""
            # Coverage digests are projection-owned inventory evidence persisted at
            # refresh time. The request hot path validates their presence and relies
            # on the durable dirty/outbox event version to invalidate them; only the
            # independent Page Audit recomputes canonical membership for comparison.
            expected_versions["oa_pending_payment_bank_coverage_signature"] = bank_coverage_signature
            expected_versions[
                "oa_pending_payment_input_invoice_coverage_signature"
            ] = input_invoice_coverage_signature
            actual_versions_by_scope[row_scope_key] = actual_versions
            expected_versions_by_scope[row_scope_key] = expected_versions
            reasons: list[str] = []
            if not isinstance(row.get("actual_source_versions"), dict):
                reasons.append("scope_missing")
            if text(row.get("cache_status")) not in {"fresh"}:
                reasons.append("scope_not_fresh")
            if not coverage_only and (
                text(row.get("source_status")) not in {"success", "succeeded"}
                or not text(source_payload.get("source_signature"))
            ):
                reasons.append("source_snapshot_missing")
            if not coverage_only and int_value(row.get("pending_relation_version"), 0) < 1:
                reasons.append("pending_relation_version_missing")
            if not bank_coverage_signature or "|digest:" not in bank_coverage_signature:
                reasons.append("bank_coverage_missing")
            if not input_invoice_coverage_signature or "|digest:" not in input_invoice_coverage_signature:
                reasons.append("input_invoice_coverage_missing")
            if text(row.get("dirty_status")) in {"pending", "processing", "failed"}:
                reasons.append(f"dirty_{text(row.get('dirty_status'))}")
            if bool(row.get("outbox_blocking")):
                reasons.append("outbox_blocking")
            if normalize_source_versions(actual_versions) != normalize_source_versions(expected_versions):
                reasons.append("source_versions_mismatch")
            if reasons:
                blocking_scope_keys.add(row_scope_key)
                stale_reasons.extend(f"{row_scope_key}:{reason}" for reason in reasons)
            token_rows.append(
                {
                    "scope_key": row_scope_key,
                    "row_count": int_value(row.get("row_count"), 0),
                    "generated_at": serialize_value(row.get("generated_at")),
                    "expected_source_versions": expected_versions,
                    "actual_source_versions": actual_versions,
                    "dirty_status": text(row.get("dirty_status")),
                    "dirty_source_version": int_value(row.get("dirty_source_version"), -1),
                    "outbox_blocking": bool(row.get("outbox_blocking")),
                }
            )

        control_blocking = any(
            text(row.get("dirty_status")) in {"pending", "processing", "failed"} or bool(row.get("outbox_blocking"))
            for row in control_rows
        )
        if control_blocking:
            blocking_scope_keys.update(row["scope_key"] for row in month_rows if text(row.get("scope_key")))
            if not month_rows:
                blocking_scope_keys.add("all")
            stale_reasons.append("all:control_scope_blocking")
        if normalized_scope_key == "all" and not month_rows:
            empty_source_ready = any(
                text(row.get("source_status")) in {"success", "succeeded"}
                and isinstance(row.get("source_payload"), dict)
                and bool(text(row["source_payload"].get("source_signature")))
                for row in control_rows
            )
            if not empty_source_ready:
                blocking_scope_keys.add("all")
                stale_reasons.append("all:canonical_scope_inventory_missing")
        if normalized_scope_key != "all" and not month_rows:
            blocking_scope_keys.add(normalized_scope_key)
            stale_reasons.append(f"{normalized_scope_key}:scope_inventory_missing")

        version_material = {
            "tenant_id": normalized_tenant_id,
            "scope_key": normalized_scope_key,
            "scopes": token_rows,
            "control": [
                {
                    "dirty_status": text(row.get("dirty_status")),
                    "dirty_source_version": int_value(row.get("dirty_source_version"), -1),
                    "outbox_blocking": bool(row.get("outbox_blocking")),
                    "source_snapshot_version": int_value(row.get("source_snapshot_version"), 0),
                    "source_payload": row.get("source_payload") if isinstance(row.get("source_payload"), dict) else {},
                }
                for row in control_rows
            ],
        }
        version_token = hashlib.sha256(
            json.dumps(serialize_value(version_material), ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
        ).hexdigest()
        common_actual_versions = self._common_source_versions(
            [{"source_versions": versions} for versions in actual_versions_by_scope.values()]
        )
        return {
            "status": "refreshing" if blocking_scope_keys else "fresh",
            "scope_key": normalized_scope_key,
            "blocking_scope_keys": sorted(blocking_scope_keys),
            "stale_reasons": sorted(set(stale_reasons)),
            "version_token": version_token,
            "source_versions": common_actual_versions,
            "source_versions_by_scope": actual_versions_by_scope,
            "expected_source_versions_by_scope": expected_versions_by_scope,
        }

    def save_oa_pending_payment_rows(
        self,
        *,
        scope_key: str,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        statistics: dict[str, int] | None = None,
        transaction: Any | None = None,
    ) -> None:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        rows_to_save = list(rows or [])
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if normalized_scope_key == "all":
                connection.execute("delete from read_model.oa_pending_payment_rows")
            else:
                connection.execute("delete from read_model.oa_pending_payment_rows where scope_key = %s", (normalized_scope_key,))
            insert_rows: list[tuple[Any, ...]] = []
            for row in rows_to_save:
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["sourceVersions"] = normalized_source_versions
                record = _oa_pending_payment_read_model_record(row_payload, normalized_scope_key)
                insert_rows.append(
                    (
                        record["row_id"],
                        record["scope_key"],
                        record["scope_month"],
                        record["oa_id"],
                        record["oa_ids"],
                        record["oa_applicant"],
                        record["oa_application_type"],
                        record["oa_workflow_status"],
                        record["oa_project_name"],
                        record["oa_amount"],
                        record["payment_status"],
                        record["payment_status_label"],
                        record["bank_transaction_id"],
                        record["bank_trade_time"],
                        record["bank_amount"],
                        record["bank_paid_total"],
                        record["bank_name"],
                        record["bank_account"],
                        record["bank_direction"],
                        record["bank_counterparty_name"],
                        record["bank_summary"],
                        record["invoice_id"],
                        record["invoice_no"],
                        record["invoice_date"],
                        record["seller_name"],
                        record["invoice_total_with_tax"],
                        record["searchable_text"],
                        record["source_versions"],
                        record["payload"],
                        record["raw_payload"],
                    )
                )
            _execute_many(
                connection,
                """
                    insert into read_model.oa_pending_payment_rows(
                        row_id, scope_key, scope_month, oa_id, oa_ids, oa_applicant, oa_application_type,
                        oa_workflow_status, oa_project_name, oa_amount, payment_status, payment_status_label,
                        bank_transaction_id, bank_trade_time, bank_amount, bank_paid_total, bank_name, bank_account, bank_direction,
                        bank_counterparty_name, bank_summary, invoice_id, invoice_no,
                        invoice_date, seller_name, invoice_total_with_tax, searchable_text,
                        source_versions, payload, raw_payload
                    )
                    values (
                        %s, %s, %s::date, %s, %s, %s,
                        %s, %s, %s, %s, %s,
                        %s, %s, %s::timestamptz,
                        %s, %s, %s, %s, %s,
                        %s, %s,
                        %s, %s, %s::date, %s,
                        %s, %s, %s,
                        %s, %s
                    )
                    on conflict (row_id, scope_key) do update set
                        scope_month = excluded.scope_month,
                        oa_id = excluded.oa_id,
                        oa_ids = excluded.oa_ids,
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
                insert_rows,
            )
            self._upsert_invoice_relation_scope(
                connection,
                scope_table_name="read_model.oa_pending_payment_scopes",
                scope_key=normalized_scope_key,
                row_count=len(rows_to_save),
                scope_type="oa_pending_payment",
                source_versions=normalized_source_versions,
                scope_payload={"statistics": dict(statistics)} if isinstance(statistics, dict) else None,
            )

        if transaction is not None:
            write(transaction)
            return
        run_in_transaction(self._connection, write)

    def publish_oa_pending_payment_rows(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        rows: list[dict[str, Any]],
        source_versions: dict[str, Any] | None = None,
        statistics: dict[str, int] | None = None,
    ) -> bool:
        normalized_tenant_id = text(tenant_id)
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        if not normalized_tenant_id:
            raise ValueError("tenant_id is required for OA pending payment publish.")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            raise ValueError("source_version must be a non-negative integer for OA pending payment publish.")

        def publish(connection: Any) -> bool:
            current = connection.fetch_one(
                """
                select source_version
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = 'oa_pending_payment'
                  and scope_key = %s
                order by source_version desc, updated_at desc, id desc
                limit 1
                for update
                """,
                (normalized_tenant_id, normalized_scope_key),
            )
            if current is None or int_value(current.get("source_version"), -1) != source_version:
                return False
            self.save_oa_pending_payment_rows(
                scope_key=normalized_scope_key,
                rows=rows,
                source_versions=source_versions,
                statistics=statistics,
                transaction=connection,
            )
            return True

        return run_in_transaction(self._connection, publish)

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

    def prune_oa_pending_payment_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._prune_invoice_relation_scope_shards(
            table_name="read_model.oa_pending_payment_rows",
            scope_table_name="read_model.oa_pending_payment_scopes",
            current_scope_keys=current_scope_keys,
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
        dedupe_all_scope_by_row_id: bool = False,
        include_statistics: bool = True,
    ) -> dict[str, Any] | None:
        scope_key = _invoice_relation_scope_key(month)
        rows_table_sql = (
            f"""
            (
                select *
                from (
                    select
                        *,
                        row_number() over (
                            partition by row_id
                            order by generated_at desc, scope_key desc, row_id
                        ) as row_id_rank
                    from {table_name}
                ) deduped_invoice_relation_rows
                where row_id_rank = 1
            ) invoice_relation_rows
            """
            if dedupe_all_scope_by_row_id and scope_key == "all"
            else table_name
        )
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
            _invoice_relation_summary_sql(table_name=rows_table_sql, where_sql=where_sql, summary_kind=summary_kind),
            tuple(params),
        )
        total = int_value(summary_row.get("count") if isinstance(summary_row, dict) else 0, 0)
        refresh_status = self._invoice_relation_refresh_status(scope_type=scope_type, scope_key=scope_key)
        scope_row = self._invoice_relation_scope_row(scope_table_name=scope_table_name, scope_key=scope_key)
        statistics_status = (
            self._invoice_relation_refresh_status(
                scope_type=scope_type,
                scope_key="all",
            )
            if include_statistics
            else "not_requested"
        )
        statistics_scope_row = None
        if include_statistics:
            statistics_scope_row = (
                scope_row
                if scope_key == "all"
                else self._invoice_relation_scope_row(scope_table_name=scope_table_name, scope_key="all")
            )
        statistics = (
            _invoice_relation_statistics_from_scope_metadata(
                statistics_scope_row.get("statistics_metadata_rows"),
                summary_kind=summary_kind,
            )
            if statistics_status == "fresh" and isinstance(statistics_scope_row, dict)
            else None
        )
        if include_statistics and statistics is None:
            statistics_status = "stale" if statistics_status == "fresh" else statistics_status
        statistics_source_versions = (
            statistics_scope_row.get("statistics_source_versions")
            if isinstance(statistics_scope_row, dict)
            and isinstance(statistics_scope_row.get("statistics_source_versions"), dict)
            else {}
        )
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
                "statistics": statistics,
                "statistics_status": statistics_status,
                "statistics_source_versions": statistics_source_versions,
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
            from {rows_table_sql}
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
            "statistics": statistics,
            "statistics_status": statistics_status,
            "statistics_source_versions": statistics_source_versions,
            "refresh_status": refresh_status,
            "source_versions": source_versions,
        }

    def _invoice_relation_scope_source_versions(
        self,
        *,
        scope_table_name: str,
        scope_type: str,
        scope_key: str,
        tenant_id: str,
    ) -> dict[str, Any]:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        rows = self._connection.fetch_all(
            f"""
            with projection_scopes as (
                select scope_key, row_count, source_versions, cache_status
                from {scope_table_name}
                where (
                    %s = 'all'
                    and scope_key <> 'all'
                ) or scope_key = %s
            ),
            active_dirty as (
                select distinct on (scope_key)
                    scope_key,
                    status as dirty_status
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = %s
                  and status in ('pending', 'processing', 'failed')
                  and (
                      (%s = 'all' and scope_key <> 'all')
                      or scope_key = %s
                  )
                order by scope_key, source_version desc, updated_at desc, id desc
            ),
            requested_scopes as (
                select scope_key from projection_scopes
                union
                select scope_key from active_dirty
                union
                select %s where %s <> 'all'
            )
            select requested.scope_key,
                   projection.row_count,
                   projection.source_versions,
                   projection.cache_status,
                   dirty.dirty_status,
                   exists (
                       select 1
                       from job.outbox_events event
                       where event.tenant_id = %s
                         and event.event_type = %s
                         and event.scope_type = %s
                         and event.scope_key = requested.scope_key
                         and event.status in ('pending', 'processing')
                   ) as has_active_event
            from requested_scopes requested
            left join projection_scopes projection using (scope_key)
            left join active_dirty dirty using (scope_key)
            order by requested.scope_key
            """,
            (
                normalized_scope_key,
                normalized_scope_key,
                tenant_id,
                scope_type,
                normalized_scope_key,
                normalized_scope_key,
                normalized_scope_key,
                normalized_scope_key,
                tenant_id,
                f"{scope_type}.read_model.refresh",
                scope_type,
            ),
        )
        source_versions_by_scope: dict[str, dict[str, Any]] = {}
        statuses_by_scope: dict[str, str] = {}
        blocking_scope_keys: list[str] = []
        active_event_scope_keys: list[str] = []
        effective_rows = rows
        if normalized_scope_key == "all" and any(
            int_value(row.get("row_count"), 0) > 0
            for row in rows
            if row.get("row_count") is not None
        ):
            effective_rows = [
                row
                for row in rows
                if row.get("row_count") is None
                or int_value(row.get("row_count"), 0) > 0
                or text(row.get("dirty_status")) in {"pending", "processing", "failed"}
            ]
        for row in effective_rows:
            current_scope_key = text(row.get("scope_key"))
            if not current_scope_key or not MONTH_SCOPE_RE.match(current_scope_key):
                continue
            source_versions = (
                row.get("source_versions")
                if isinstance(row.get("source_versions"), dict)
                else {}
            )
            source_versions_by_scope[current_scope_key] = dict(source_versions)
            dirty_status = text(row.get("dirty_status"))
            cache_status = text(row.get("cache_status"))
            if dirty_status in {"pending", "processing"}:
                status = "refreshing"
            elif dirty_status == "failed":
                status = "stale"
            elif not source_versions:
                status = "missing"
            elif cache_status not in {"", "fresh"}:
                status = "stale"
            else:
                status = "fresh"
            statuses_by_scope[current_scope_key] = status
            if status != "fresh":
                blocking_scope_keys.append(current_scope_key)
                if bool(row.get("has_active_event")):
                    active_event_scope_keys.append(current_scope_key)
        return {
            "scope_keys": list(source_versions_by_scope),
            "source_versions_by_scope": source_versions_by_scope,
            "statuses_by_scope": statuses_by_scope,
            "blocking_scope_keys": blocking_scope_keys,
            "active_event_scope_keys": active_event_scope_keys,
        }

    def _list_invoice_relation_filter_options(
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
        option_fields: dict[str, tuple[str, str, set[str]]],
    ) -> dict[str, Any] | None:
        scope_key = _invoice_relation_scope_key(month)
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
        refresh_status = self._invoice_relation_refresh_status(scope_type=scope_type, scope_key=scope_key)
        scope_row = self._invoice_relation_scope_row(scope_table_name=scope_table_name, scope_key=scope_key)
        if scope_row is None:
            return None
        source_versions = scope_row.get("source_versions") if isinstance(scope_row.get("source_versions"), dict) else {}
        option_values = ",\n                    ".join(
            f"('{field}', nullif(btrim(({expression})::text), ''), nullif(btrim(({_invoice_relation_option_label_expression(field, expression)})::text), ''))"
            for field, (expression, _mode, _operators) in option_fields.items()
        )
        rows = self._connection.fetch_all(
            f"""
            with filtered_rows as (
                select *
                from {table_name}
                where {where_sql}
            ),
            option_values(field, value, label) as (
                select option_value.field, option_value.value, option_value.label
                from filtered_rows
                cross join lateral (
                    values
                    {option_values}
                ) as option_value(field, value, label)
            )
            select field, value, max(label) as label, count(*)::integer as option_count
            from option_values
            where value is not null
            group by field, value
            order by field, value
            """,
            tuple(params),
        )
        options: dict[str, list[dict[str, Any]]] = {field: [] for field in option_fields}
        for row in rows:
            field = text(row.get("field")) or ""
            value = text(row.get("value")) or ""
            if field not in options or not value:
                continue
            label = text(row.get("label")) or value
            if field == "bank_direction":
                label = "支出" if value == "outflow" else "收入" if value == "inflow" else value
            count = int_value(row.get("option_count"), 0)
            options[field].append({"value": value, "label": label, "count": count})
        return {
            "options": options,
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
        statistics_metadata: dict[str, Any] | None = None,
    ) -> None:
        normalized_scope_key = _invoice_relation_scope_key(scope_key)
        rows_to_save = list(rows or [])
        normalized_source_versions = source_versions if isinstance(source_versions, dict) else {}

        def write(connection: Any) -> None:
            if normalized_scope_key == "all":
                connection.execute(f"delete from {table_name}")
            else:
                connection.execute(f"delete from {table_name} where scope_key = %s", (normalized_scope_key,))
            insert_rows: list[dict[str, Any]] = []
            for row in rows_to_save:
                row_payload = dict(row) if isinstance(row, dict) else {}
                row_payload["sourceVersions"] = normalized_source_versions
                insert_rows.append(row_builder(row_payload, normalized_scope_key))
            _execute_many(
                connection,
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
                insert_rows,
            )
            self._upsert_invoice_relation_scope(
                connection,
                scope_table_name=scope_table_name,
                scope_key=normalized_scope_key,
                row_count=len(rows_to_save),
                scope_type=scope_type,
                source_versions=normalized_source_versions,
                scope_payload={"statistics_metadata": dict(statistics_metadata or {})},
            )

        run_in_transaction(self._connection, write)

    def _mark_invoice_relation_scope(
        self,
        *,
        scope_table_name: str,
        scope_key: str,
        row_count: int,
        source_versions: dict[str, Any] | None,
        statistics_metadata: dict[str, Any] | None = None,
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
                scope_payload={"statistics_metadata": dict(statistics_metadata or {})},
            )

        run_in_transaction(self._connection, write)

    def _prune_invoice_relation_scope_shards(
        self,
        *,
        table_name: str,
        scope_table_name: str,
        current_scope_keys: list[str],
    ) -> None:
        normalized_scope_keys: list[str] = []
        for scope_key in list(current_scope_keys or []):
            normalized_scope_key = str(scope_key or "").strip()
            if MONTH_SCOPE_RE.match(normalized_scope_key) and normalized_scope_key not in normalized_scope_keys:
                normalized_scope_keys.append(normalized_scope_key)

        def write(connection: Any) -> None:
            if normalized_scope_keys:
                placeholders = ", ".join(["%s"] * len(normalized_scope_keys))
                params = tuple(normalized_scope_keys)
                connection.execute(
                    f"delete from {table_name} where scope_key <> 'all' and scope_key not in ({placeholders})",
                    params,
                )
                connection.execute(
                    f"delete from {scope_table_name} where scope_key <> 'all' and scope_key not in ({placeholders})",
                    params,
                )
                return
            connection.execute(f"delete from {table_name} where scope_key <> 'all'")
            connection.execute(f"delete from {scope_table_name} where scope_key <> 'all'")

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
        scope_payload: dict[str, Any] | None = None,
    ) -> None:
        raw_payload = {
            "scope_type": scope_type,
            "scope_key": scope_key,
            "row_count": row_count,
            "source_versions": source_versions,
            **dict(scope_payload or {}),
        }
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
                jsonb(raw_payload),
            ),
        )

    def _invoice_relation_scope_row(self, *, scope_table_name: str, scope_key: str) -> dict[str, Any] | None:
        if scope_key == "all":
            rows = self._connection.fetch_all(
                f"""
                select scope_key, row_count, source_versions, cache_status, raw_payload
                from {scope_table_name}
                where scope_key <> 'all'
                order by generated_at desc, scope_key desc
                """
            )
            if not rows:
                row = self._connection.fetch_one(
                    f"select scope_key, row_count, source_versions, cache_status, raw_payload "
                    f"from {scope_table_name} where scope_key = 'all' limit 1"
                )
                if not isinstance(row, dict):
                    return None
                raw_payload = row.get("raw_payload") if isinstance(row.get("raw_payload"), dict) else {}
                return {
                    **dict(row),
                    "statistics_source_versions": (
                        dict(row.get("source_versions")) if isinstance(row.get("source_versions"), dict) else {}
                    ),
                    "statistics_metadata_rows": [raw_payload.get("statistics_metadata")],
                }
            rows_for_all_status = self._invoice_relation_all_scope_effective_rows(rows)
            for row in rows_for_all_status:
                if not isinstance(row, dict):
                    continue
                if text(row.get("cache_status")) not in {"", "fresh"}:
                    return {"scope_key": "all", "source_versions": {}}
            return {
                "scope_key": "all",
                "source_versions": self._common_source_versions(rows_for_all_status),
                "statistics_source_versions": self._common_source_versions(rows_for_all_status),
                "statistics_metadata_rows": [
                    row.get("raw_payload", {}).get("statistics_metadata")
                    if isinstance(row.get("raw_payload"), dict)
                    else None
                    for row in rows_for_all_status
                ],
            }
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



class PostgresBankReadModelRepository:
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

    def bank_detail_category_source_signatures(
        self,
        *,
        scope_keys: list[str],
        tenant_id: str = "default",
        connection: Any | None = None,
    ) -> dict[str, str]:
        normalized_scope_keys = _dedupe_preserve_order(
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if MONTH_SCOPE_RE.match(str(scope_key).strip())
        )
        if not normalized_scope_keys:
            return {}
        executor = connection or self._connection
        rows = executor.fetch_all(
            """
            /* bank_detail_category_source_signatures */
            with requested_scopes as (
                select distinct requested.scope_key
                from unnest(%s::text[]) as requested(scope_key)
            ),
            latest_categories as (
                select distinct on (requested.scope_key, bank.id)
                       requested.scope_key,
                       bank.id::text as transaction_id,
                       jsonb_build_object(
                           'category', category.category,
                           'source', category.source,
                           'version', category.version,
                           'raw_payload', category.raw_payload
                       ) as value
                from app.bank_transaction_categories category
                join app.bank_transactions bank
                  on category.bank_transaction_id = bank.id
                  or (
                      category.bank_transaction_id is null
                      and category.legacy_transaction_id is not null
                      and category.legacy_transaction_id in (bank.legacy_mongo_id, bank.id::text)
                  )
                join requested_scopes requested
                  on to_char(coalesce(bank.txn_month, date_trunc('month', bank.txn_date)), 'YYYY-MM')
                     = requested.scope_key
                where category.status = 'active'
                  and bank.status <> 'deleted'
                order by requested.scope_key, bank.id, category.updated_at desc, category.id desc
            ),
            latest_confirmations as (
                select distinct on (requested.scope_key, bank.id)
                       requested.scope_key,
                       bank.id::text as transaction_id,
                       jsonb_build_object(
                           'category_code', confirmation.category_code,
                           'candidate_category_codes', confirmation.candidate_category_codes,
                           'rule_version', confirmation.rule_version,
                           'version', confirmation.version,
                           'raw_payload', confirmation.raw_payload
                       ) as value
                from app.bank_transaction_category_confirmations confirmation
                join app.bank_transactions bank
                  on confirmation.bank_transaction_id = bank.id
                  or (
                      confirmation.bank_transaction_id is null
                      and confirmation.legacy_transaction_id is not null
                      and confirmation.legacy_transaction_id in (bank.legacy_mongo_id, bank.id::text)
                  )
                join requested_scopes requested
                  on to_char(coalesce(bank.txn_month, date_trunc('month', bank.txn_date)), 'YYYY-MM')
                     = requested.scope_key
                where confirmation.tenant_id = %s
                  and confirmation.status = 'active'
                  and bank.status <> 'deleted'
                order by requested.scope_key, bank.id, confirmation.confirmed_at desc, confirmation.id desc
            ),
            facts as (
                select scope_key, 'category'::text as kind, transaction_id, value
                from latest_categories
                union all
                select scope_key, 'confirmation'::text as kind, transaction_id, value
                from latest_confirmations
            )
            select requested.scope_key,
                   encode(
                       digest(
                           convert_to(
                               coalesce(
                                   jsonb_agg(
                                       jsonb_build_object(
                                           'kind', facts.kind,
                                           'transaction_id', facts.transaction_id,
                                           'value', facts.value
                                       )
                                       order by facts.kind, facts.transaction_id
                                   ) filter (where facts.transaction_id is not null),
                                   '[]'::jsonb
                               )::text,
                               'UTF8'
                           ),
                           'sha256'
                       ),
                       'hex'
                   ) as source_signature
            from requested_scopes requested
            left join facts on facts.scope_key = requested.scope_key
            group by requested.scope_key
            order by requested.scope_key
            """,
            (normalized_scope_keys, tenant_id),
        )
        signatures = {
            scope_key: BANK_DETAIL_EMPTY_CATEGORY_SOURCE_SIGNATURE
            for scope_key in normalized_scope_keys
        }
        for row in rows:
            scope_key = text(row.get("scope_key"))
            source_signature = text(row.get("source_signature"))
            if scope_key in signatures and source_signature:
                signatures[scope_key] = source_signature
        return signatures

    def _bank_detail_relation_source_summaries(
        self,
        *,
        scope_keys: list[str],
        connection: Any | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_scope_keys = _dedupe_preserve_order(
            str(scope_key).strip()
            for scope_key in list(scope_keys or [])
            if MONTH_SCOPE_RE.match(str(scope_key).strip())
        )
        if not normalized_scope_keys:
            return {}
        executor = connection or self._connection
        scope_months = [month_start(scope_key) for scope_key in normalized_scope_keys]
        rows = executor.fetch_all(
            """
            /* bank_detail_relation_source_summaries */
            with requested_scopes as (
                select unnest(%s::date[]) as scope_month
            ),
            bank_scope_ids as (
                select
                    requested.scope_month,
                    coalesce(
                        array_agg(distinct coalesce(bank.legacy_mongo_id, bank.id::text))
                            filter (where bank.id is not null),
                        array[]::text[]
                    ) as row_ids
                from requested_scopes requested
                left join app.bank_transactions bank
                  on bank.txn_month = requested.scope_month
                 and bank.status <> 'deleted'
                group by requested.scope_month
            )
            select
                to_char(scope.scope_month, 'YYYY-MM') as scope_key,
                count(relation.*)::integer as relation_count,
                coalesce(max(relation.updated_at)::text, '') as relation_updated_at
            from bank_scope_ids scope
            left join app.workbench_pair_relations relation
              on relation.status = 'active'
             and (
                    relation.month_scope = scope.scope_month
                    or relation.row_ids && scope.row_ids
                 )
            group by scope.scope_month
            order by scope.scope_month
            """,
            (scope_months,),
        )
        summaries = {
            scope_key: {
                "source": "workbench_pair_relations",
                "scope_key": scope_key,
                "relation_count": 0,
                "relation_updated_at": "",
            }
            for scope_key in normalized_scope_keys
        }
        for row in rows:
            scope_key = text(row.get("scope_key"))
            if scope_key not in summaries:
                continue
            summaries[scope_key] = {
                "source": "workbench_pair_relations",
                "scope_key": scope_key,
                "relation_count": int_value(row.get("relation_count"), 0),
                "relation_updated_at": text(row.get("relation_updated_at")) or "",
            }
        return summaries


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
                   source_versions, generated_at, last_error, raw_payload
            from read_model.bank_detail_scopes
            where tenant_id = %s
              and scope_type = 'bank_detail'
            """,
            (tenant_id,),
        )
        dirty_rows = executor.fetch_all(
            """
            select scope_key, status, updated_at::text as updated_at, last_error, source_version
            from job.read_model_dirty_scopes
            where tenant_id = %s
              and scope_type = 'bank_detail'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            """,
            (tenant_id,),
        )
        by_scope = {text(row.get("scope_key")): row for row in rows if text(row.get("scope_key"))}
        dirty_by_scope: dict[str, dict[str, Any]] = {}
        for row in dirty_rows:
            scope_key = text(row.get("scope_key"))
            if scope_key and scope_key not in dirty_by_scope:
                dirty_by_scope[scope_key] = row
        statistics_scope_keys = sorted(
            {
                scope_key
                for scope_key in [*by_scope, *dirty_by_scope]
                if MONTH_SCOPE_RE.match(scope_key)
            }
        )
        current_category_signatures = self.bank_detail_category_source_signatures(
            scope_keys=_dedupe_preserve_order([*normalized_scope_keys, *statistics_scope_keys]),
            tenant_id=tenant_id,
            connection=executor,
        )
        current_relation_source_summaries = self._bank_detail_relation_source_summaries(
            scope_keys=_dedupe_preserve_order([*normalized_scope_keys, *statistics_scope_keys]),
            connection=executor,
        )

        def status_for(scope_key_values: list[str], *, require_statistics: bool = False) -> str:
            statuses = {
                text(dirty_by_scope.get(scope_key, {}).get("status"))
                for scope_key in scope_key_values
                if scope_key in dirty_by_scope
            }
            if statuses.intersection({"pending", "processing"}):
                return "refreshing"
            if "failed" in statuses:
                return "stale"
            if not scope_key_values or any(scope_key not in by_scope for scope_key in scope_key_values):
                return "missing"
            if any(
                int_value(by_scope[scope_key].get("schema_version"), 0)
                != BANK_DETAIL_READ_MODEL_SCHEMA_VERSION
                for scope_key in scope_key_values
            ):
                return "schema_mismatch"
            if any(text(by_scope[scope_key].get("status")) != "fresh" for scope_key in scope_key_values):
                return "stale"
            if any(
                text(
                    (
                        by_scope[scope_key].get("source_versions")
                        if isinstance(by_scope[scope_key].get("source_versions"), dict)
                        else {}
                    ).get("bank_transaction_category_source_signature")
                )
                != current_category_signatures.get(scope_key, "")
                for scope_key in scope_key_values
            ):
                return "stale"
            if any(
                _normalized_workbench_relation_source_summary(
                    (
                        by_scope[scope_key].get("source_versions")
                        if isinstance(by_scope[scope_key].get("source_versions"), dict)
                        else {}
                    ).get("workbench_relation_source_versions"),
                    scope_key=scope_key,
                )
                != current_relation_source_summaries.get(scope_key)
                for scope_key in scope_key_values
            ):
                return "stale"
            if require_statistics and any(
                _bank_detail_scope_statistics(by_scope[scope_key].get("raw_payload")) is None
                for scope_key in scope_key_values
            ):
                return "stale"
            return "fresh"

        status = status_for(normalized_scope_keys)
        statistics_status = status_for(statistics_scope_keys, require_statistics=True)
        statistics_refresh_scope_keys = [
            scope_key
            for scope_key in statistics_scope_keys
            if status_for([scope_key], require_statistics=True)
            not in {"fresh", "refreshing"}
        ]
        generated_values = [
            text(by_scope[scope_key].get("generated_at"))
            for scope_key in normalized_scope_keys
            if scope_key in by_scope and text(by_scope[scope_key].get("generated_at"))
        ]
        all_signatures = {
            scope_key: {
                "schema_version": int_value(by_scope[scope_key].get("schema_version"), 0),
                "status": text(by_scope[scope_key].get("status")) or "",
                "row_count": int_value(by_scope[scope_key].get("row_count"), 0),
                "source_version": int_value(by_scope[scope_key].get("source_version"), 0),
                "source_versions": by_scope[scope_key].get("source_versions") if isinstance(by_scope[scope_key].get("source_versions"), dict) else {},
                "statistics": _bank_detail_scope_statistics(by_scope[scope_key].get("raw_payload")),
                "generated_at": text(by_scope[scope_key].get("generated_at")),
                "last_error": text(by_scope[scope_key].get("last_error")),
                "dirty_status": text(dirty_by_scope.get(scope_key, {}).get("status")),
                "dirty_source_version": int_value(dirty_by_scope.get(scope_key, {}).get("source_version"), 0),
                "dirty_last_error": text(dirty_by_scope.get(scope_key, {}).get("last_error")),
            }
            for scope_key in statistics_scope_keys
            if scope_key in by_scope
        }
        signatures = {
            scope_key: all_signatures[scope_key]
            for scope_key in normalized_scope_keys
            if scope_key in all_signatures
        }
        statistics = None
        if statistics_status == "fresh":
            statistics = _bank_detail_empty_statistics()
            for scope_key in statistics_scope_keys:
                scope_statistics = _bank_detail_scope_statistics(by_scope[scope_key].get("raw_payload"))
                if scope_statistics is None:
                    statistics = None
                    statistics_status = "stale"
                    break
                for key in statistics:
                    statistics[key] += scope_statistics[key]
        statistics_signature_payload = {
            "status": statistics_status,
            "scopes": {
                scope_key: {
                    **all_signatures.get(scope_key, {}),
                    "statistics": _bank_detail_scope_statistics(by_scope.get(scope_key, {}).get("raw_payload")),
                }
                for scope_key in statistics_scope_keys
            },
        }
        statistics_signature = hashlib.sha256(
            json.dumps(
                statistics_signature_payload,
                ensure_ascii=False,
                sort_keys=True,
                default=str,
                separators=(",", ":"),
            ).encode("utf-8")
        ).hexdigest()
        return {
            "read_model_status": status,
            "read_model_scope_keys": normalized_scope_keys,
            "read_model_generated_at": max(generated_values) if generated_values else None,
            "read_model_scope_signatures": signatures,
            "statistics": statistics,
            "statistics_status": statistics_status,
            "statistics_scope_keys": statistics_scope_keys,
            "statistics_refresh_scope_keys": statistics_refresh_scope_keys,
            "statistics_scope_signatures": all_signatures,
            "statistics_signature": statistics_signature,
            "dirty_scopes": [
                {
                    "scope_key": scope_key,
                    "status": text(row.get("status")),
                    "updated_at": text(row.get("updated_at")),
                    "last_error": text(row.get("last_error")),
                    "source_version": int_value(row.get("source_version"), 0),
                }
                for scope_key, row in dirty_by_scope.items()
                if scope_key in normalized_scope_keys
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


    def get_bank_detail_tagged_snapshot(
        self,
        month: str,
        *,
        include_transaction_ids: list[str] | None = None,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_month = text(month)
        if not normalized_month or not MONTH_SCOPE_RE.match(normalized_month):
            raise ValueError("bank detail tagged snapshot month must be YYYY-MM.")
        normalized_ids = _dedupe_preserve_order(
            text(transaction_id)
            for transaction_id in list(include_transaction_ids or [])
            if text(transaction_id)
        )
        with self._connection.transaction() as connection:
            connection.execute("set transaction isolation level repeatable read read only")
            rows = connection.fetch_all(
                """
                select payload, raw_payload, summary, purpose, scope_key, source_versions
                from read_model.bank_detail_rows
                where tenant_id = %s
                  and (
                    scope_month = %s::date
                    or transaction_id = any(%s)
                    or payload->>'id' = any(%s)
                    or payload->>'transaction_id' = any(%s)
                  )
                order by trade_time_sort desc, transaction_id desc
                """,
                (tenant_id, month_start(normalized_month), normalized_ids, normalized_ids, normalized_ids),
            )
            payload_rows = [_bank_detail_row_payload(row) for row in rows]
            payload_by_id: dict[str, dict[str, Any]] = {}
            for source_row, payload_row in zip(rows, payload_rows, strict=True):
                for row_identity in (payload_row.get("transaction_id"), payload_row.get("id")):
                    if transaction_id := text(row_identity):
                        payload_by_id.setdefault(transaction_id, payload_row)
            target_scope_transaction_ids = _dedupe_preserve_order(
                text(payload_row.get("transaction_id") or payload_row.get("id"))
                for source_row, payload_row in zip(rows, payload_rows, strict=True)
                if text(source_row.get("scope_key")) == normalized_month
            )
            missing_ids = [transaction_id for transaction_id in normalized_ids if transaction_id not in payload_by_id]
            scope_keys = _dedupe_preserve_order(
                [normalized_month, *[text(row.get("scope_key")) for row in rows if text(row.get("scope_key"))]]
            )
            scope_summary = self.bank_detail_scope_summary(
                scope_keys=scope_keys,
                tenant_id=tenant_id,
                connection=connection,
            )
        return {
            "rows": payload_rows,
            "target_scope_transaction_ids": target_scope_transaction_ids,
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
            params_seq = [
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
                )
                for row in list(rows or [])
            ]
            _execute_many(
                connection,
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
                params_seq,
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
        statistics = _bank_detail_statistics_from_rows(rows)

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.bank_detail_rows where tenant_id = %s and scope_key = %s",
                (tenant_id, normalized_scope_key),
            )
            params_seq: list[tuple[Any, ...]] = []
            for row in list(rows or []):
                record = _bank_detail_row_record(row, scope_key=normalized_scope_key, scope_month=scope_month, tenant_id=tenant_id)
                params_seq.append(record)
            _execute_many(
                connection,
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
                params_seq,
            )
            self._upsert_bank_detail_scope(
                connection,
                tenant_id=tenant_id,
                scope_key=normalized_scope_key,
                scope_month=scope_month,
                row_count=len(list(rows or [])),
                source_versions=(rows[0].get("source_versions") if rows and isinstance(rows[0].get("source_versions"), dict) else {}),
                generated_at=generated_at,
                statistics=statistics,
            )

        run_in_transaction(self._connection, write)


    def mark_bank_detail_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        tenant_id: str = "default",
        source_versions: dict[str, Any] | None = None,
        statistics: dict[str, int] | None = None,
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
                statistics=statistics if statistics is not None else (_bank_detail_empty_statistics() if row_count == 0 else None),
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
        statistics: dict[str, int] | None = None,
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
                raw_payload = excluded.raw_payload || case
                    when excluded.raw_payload ? 'statistics' then '{}'::jsonb
                    when bank_detail_scopes.raw_payload ? 'statistics'
                        then jsonb_build_object('statistics', bank_detail_scopes.raw_payload->'statistics')
                    else '{}'::jsonb
                end,
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
                jsonb(
                    {
                        "source_versions": source_versions,
                        **({"statistics": statistics} if statistics is not None else {}),
                    }
                ),
            ),
        )


class PostgresPendingInvoiceLifecycleReadModelRepository:
    def __init__(
        self,
        connection: Any,
        *,
        bank_detail_scope_summary: Any,
        workbench_relation_source_summary_from_source: Any,
    ) -> None:
        self._connection = connection
        self._bank_detail_scope_summary = bank_detail_scope_summary
        self._workbench_relation_source_summary_from_source = workbench_relation_source_summary_from_source

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
        include_statistics: bool = True,
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
                scope_row = _merge_pending_invoice_direction_scope_rows(
                    scope_key=scope_key,
                    rows=[row for row in direction_scope_rows if isinstance(row, dict)],
                )
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
            statistics_state = (
                self._pending_invoice_statistics_state(connection=connection)
                if include_statistics
                else {"status": "not_requested"}
            )
            statistics_status = str(statistics_state.get("status") or "stale")
            statistics = (
                statistics_state.get("statistics")
                if isinstance(statistics_state.get("statistics"), dict)
                else None
            )
            statistics_source_versions_by_scope = (
                statistics_state.get("source_versions_by_scope")
                if isinstance(statistics_state.get("source_versions_by_scope"), dict)
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
                    "statistics": statistics,
                    "statistics_status": statistics_status,
                    "statistics_source_versions_by_scope": statistics_source_versions_by_scope,
                    "bank_transaction_tags": {},
                    "bank_transaction_tags_version": 1,
                    "refresh_status": refresh_status,
                    "source_versions": source_versions,
                }
            rows = connection.fetch_all(
                f"""
                select
                    payload,
                    case when payload = '{{}}'::jsonb then raw_payload else null::jsonb end as raw_payload,
                    missing_invoice,
                    can_create_invoice
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
                "statistics": statistics,
                "statistics_status": statistics_status,
                "statistics_source_versions_by_scope": statistics_source_versions_by_scope,
                "bank_transaction_tags": {},
                "bank_transaction_tags_version": 1,
                "refresh_status": refresh_status,
                "source_versions": source_versions,
            }

    def list_pending_invoice_lifecycle_source_rows(
        self,
        *,
        month: str,
        direction: str,
    ) -> dict[str, Any] | None:
        normalized_month = str(month or "").strip()
        normalized_direction = str(direction or "").strip()
        if not MONTH_SCOPE_RE.match(normalized_month):
            raise ValueError("pending invoice lifecycle source month must be YYYY-MM.")
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice lifecycle source direction must be expense or income.")
        scope_key = f"{normalized_direction}:all:{normalized_month}"
        with self._connection.transaction() as connection:
            refresh_status = self._refresh_status(
                scope_type="pending_invoice",
                scope_key=scope_key,
                connection=connection,
            )
            scope_row = self._pending_invoice_scope_row(scope_key, connection=connection)
            if scope_row is None:
                if refresh_status != "fresh":
                    return {
                        "scope_key": scope_key,
                        "refresh_status": refresh_status,
                        "source_versions": {},
                        "rows": [],
                    }
                bank_detail_source_versions = self._empty_pending_invoice_month_source_versions(
                    month=normalized_month,
                    direction=normalized_direction,
                    connection=connection,
                )
                if bank_detail_source_versions is None:
                    return None
                return {
                    "scope_key": scope_key,
                    "refresh_status": "fresh",
                    "source_versions": {
                        "pending_invoice_empty_month_direction": {
                            "month": normalized_month,
                            "direction": normalized_direction,
                            "bank_detail_source_versions": bank_detail_source_versions,
                        }
                    },
                    "rows": [],
                }
            source_versions = scope_row.get("source_versions")
            if refresh_status != "fresh":
                return {
                    "scope_key": scope_key,
                    "refresh_status": refresh_status,
                    "source_versions": dict(source_versions) if isinstance(source_versions, dict) else {},
                    "rows": [],
                }
            rows = connection.fetch_all(
                """
                select payload, case when payload = '{}'::jsonb then raw_payload else null::jsonb end as raw_payload
                from read_model.pending_invoice_rows
                where direction = %s
                  and scope_month = %s::date
                order by trade_date desc nulls last, row_id
                """,
                (normalized_direction, month_start(normalized_month)),
            )
            return {
                "scope_key": scope_key,
                "refresh_status": refresh_status,
                "source_versions": dict(source_versions) if isinstance(source_versions, dict) else {},
                "rows": [payload for row in rows if isinstance(payload := _read_model_payload(row), dict)],
            }

    def _empty_pending_invoice_month_source_versions(
        self,
        *,
        month: str,
        direction: str,
        connection: Any,
    ) -> dict[str, Any] | None:
        scope_summary = self._bank_detail_scope_summary(
            scope_keys=[month],
            tenant_id="default",
            connection=connection,
        )
        if not isinstance(scope_summary, dict) or str(scope_summary.get("read_model_status") or "") != "fresh":
            return None
        bank_row = connection.fetch_one(
            """
            select transaction_id
            from read_model.bank_detail_rows
            where tenant_id = 'default'
              and scope_month = %s::date
              and direction = %s
            limit 1
            """,
            (month_start(month), direction),
        )
        if bank_row is not None:
            return None
        return _source_versions_from_scope_summary(scope_summary)


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
        statistics_metadata: dict[str, Any] | None = None,
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
                        jsonb({}),
                    ),
                )
            if normalized_filter == "all":
                self._upsert_pending_invoice_scope(
                    connection,
                    scope_key=scope_key,
                    direction=normalized_direction,
                    filter_group=normalized_filter,
                    row_count=len(rows_to_save),
                    source_versions=normalized_source_versions,
                    statistics_metadata=statistics_metadata,
                )
                filter_counts = _pending_invoice_filter_group_counts_for_rows(
                    rows_to_save,
                    direction=normalized_direction,
                )
                for filter_group, row_count in filter_counts.items():
                    if filter_group == "all":
                        continue
                    self._upsert_pending_invoice_scope(
                        connection,
                        scope_key=_pending_invoice_row_scope_key(
                            direction=normalized_direction,
                            filter_group=filter_group,
                            scope_month=scope_month,
                        ),
                        direction=normalized_direction,
                        filter_group=filter_group,
                        row_count=row_count,
                        source_versions=normalized_source_versions,
                        statistics_metadata=statistics_metadata,
                    )
            else:
                self._upsert_pending_invoice_scope(
                    connection,
                    scope_key=scope_key,
                    direction=normalized_direction,
                    filter_group=normalized_filter,
                    row_count=len(rows_to_save),
                    source_versions=normalized_source_versions,
                    statistics_metadata=statistics_metadata,
                )

        run_in_transaction(self._connection, write)


    def mark_pending_invoice_scope(
        self,
        *,
        scope_key: str,
        row_count: int = 0,
        source_versions: dict[str, Any] | None = None,
        statistics_metadata: dict[str, Any] | None = None,
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
                statistics_metadata=statistics_metadata,
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

    def invoice_lifecycle_scope_summary(
        self,
        *,
        month: str,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_month = text(month) or ""
        if not normalized_month:
            return None
        scope_row = self._invoice_lifecycle_scope_row(scope_key=normalized_month, tenant_id=tenant_id)
        if scope_row is None:
            return None
        refresh_status = self._refresh_status(scope_type="invoice_lifecycle", scope_key=normalized_month)
        read_model_status = "fresh"
        stale_reasons: list[str] = []
        if refresh_status != "fresh":
            read_model_status = "refreshing" if refresh_status == "refreshing" else "stale"
            stale_reasons.append(f"{refresh_status}:{normalized_month}")
        source_versions = scope_row.get("source_versions") if isinstance(scope_row.get("source_versions"), dict) else {}
        return {
            "read_model_status": read_model_status,
            "scope_key": normalized_month,
            "row_count": max(int_value(scope_row.get("row_count"), 0), 0),
            "source_versions": dict(source_versions),
            "read_model_scope_keys": [normalized_month],
            "stale_reasons": stale_reasons,
        }


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


    def _upsert_invoice_lifecycle_scope(
        self,
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
        direction, filter_group, scope_month = _parse_pending_invoice_scope_key(scope_key)
        rows = executor.fetch_all(
            """
            select scope_key, row_count, source_versions
            from read_model.pending_invoice_scopes
            where scope_key = %s
               or scope_key like %s
            order by scope_key
            """,
            (scope_key, f"{scope_key}:%"),
        )
        if filter_group != "all" and scope_month is None:
            month_rows = executor.fetch_all(
                """
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from read_model.pending_invoice_rows
                where direction = %s
                  and scope_month is not null
                order by scope_key
                """,
                (direction,),
            )
            active_months = {
                text(row.get("scope_key"))
                for row in month_rows
                if isinstance(row, dict) and text(row.get("scope_key"))
            }
            rows = [
                row
                for row in rows
                if text(row.get("scope_key")) == scope_key
                or text(
                    _parse_pending_invoice_scope_key(text(row.get("scope_key")))[2]
                )[:7]
                in active_months
            ]
        return _pending_invoice_scope_source_versions_row(
            scope_key=scope_key,
            rows=rows,
            include_empty=filter_group != "all",
        )


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
            scope_summary = self._bank_detail_scope_summary(
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
        _ = tenant_id
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
            scope_rows = connection.fetch_all(
                f"""
                /* pending_invoice_relation_source_versions_bulk */
                with pending_scopes as (
                    select
                        to_char(scope_month, 'YYYY-MM') as scope_key,
                        scope_month,
                        array_agg(distinct row_id order by row_id)
                            filter (where row_id is not null) as row_ids
                    from read_model.pending_invoice_rows
                    where {where_sql}
                      and scope_month is not null
                    group by scope_month
                )
                select
                    pending_scopes.scope_key,
                    count(relations.*)::integer as relation_count,
                    coalesce(max(relations.updated_at)::text, '') as relation_updated_at
                from pending_scopes
                left join app.workbench_pair_relations relations
                  on relations.status = 'active'
                 and (
                    relations.month_scope = pending_scopes.scope_month
                    or relations.row_ids && pending_scopes.row_ids
                 )
                group by pending_scopes.scope_key
                order by pending_scopes.scope_key
                """,
                tuple(params),
            )
        result: dict[str, Any] = {}
        for row in scope_rows:
            if not isinstance(row, dict):
                continue
            scope_key = text(row.get("scope_key"))
            if not scope_key:
                continue
            result[scope_key] = {
                "source": "workbench_pair_relations",
                "scope_key": scope_key,
                "relation_count": int_value(row.get("relation_count"), 0),
                "relation_updated_at": text(row.get("relation_updated_at")) or "",
            }
        return result


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

    def _pending_invoice_statistics_state(self, *, connection: Any) -> dict[str, Any]:
        dirty_row = connection.fetch_one(
            """
            select status
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'pending_invoice'
              and scope_key ~ '^(expense|income):all(?::[0-9]{4}-[0-9]{2})?$'
              and status in ('pending', 'processing', 'failed')
            order by updated_at desc
            limit 1
            """
        )
        runtime_status: str | None = None
        if isinstance(dirty_row, dict):
            runtime_status = (
                "refreshing"
                if text(dirty_row.get("status")) in {"pending", "processing"}
                else "stale"
            )
        outbox_row = connection.fetch_one(
            """
            select
                coalesce(bool_or(status in ('failed', 'dead_lettered')), false) as has_failed,
                coalesce(bool_or(status in ('pending', 'processing')), false) as has_active
            from job.outbox_events
            where tenant_id = 'default'
              and event_type = 'pending_invoice.read_model.refresh'
              and coalesce(scope_key, payload->>'scope_key', '')
                  ~ '^(expense|income):all(?::[0-9]{4}-[0-9]{2})?$'
              and status in ('pending', 'processing', 'failed', 'dead_lettered')
            """
        )
        if isinstance(outbox_row, dict) and bool(outbox_row.get("has_failed")):
            runtime_status = "stale"
        elif isinstance(outbox_row, dict) and bool(outbox_row.get("has_active")) and runtime_status != "stale":
            runtime_status = "refreshing"
        rows = connection.fetch_all(
            """
            select scope_key, direction, row_count, cache_status, source_versions, raw_payload
            from read_model.pending_invoice_scopes
            where filter_group = 'all'
              and direction in ('expense', 'income')
            order by scope_key
            """
        )
        by_direction: dict[str, list[dict[str, Any]]] = {}
        metadata_rows: list[Any] = []
        source_versions_by_scope: dict[str, Any] = {}
        for direction in ("expense", "income"):
            direction_rows = [
                row for row in rows if isinstance(row, dict) and text(row.get("direction")) == direction
            ]
            child_rows = [row for row in direction_rows if text(row.get("scope_key") or "").count(":") >= 2]
            nonempty_child_rows = [row for row in child_rows if int_value(row.get("row_count"), 0) > 0]
            parent_rows = [row for row in direction_rows if text(row.get("scope_key") or "").count(":") < 2]
            effective_rows = nonempty_child_rows or parent_rows[-1:] or child_rows[-1:]
            if not effective_rows or any(text(row.get("cache_status")) not in {"", "fresh"} for row in effective_rows):
                return {
                    "status": runtime_status or "stale",
                    "source_versions_by_scope": source_versions_by_scope,
                }
            by_direction[direction] = effective_rows
            source_row = _pending_invoice_scope_source_versions_row(
                f"{direction}:all",
                effective_rows,
            )
            source_versions_by_scope[f"{direction}:all"] = (
                source_row.get("source_versions")
                if isinstance(source_row, dict) and isinstance(source_row.get("source_versions"), dict)
                else {}
            )
            metadata_rows.extend(
                row.get("raw_payload", {}).get("statistics_metadata")
                if isinstance(row.get("raw_payload"), dict)
                else None
                for row in effective_rows
            )
        statistics = _pending_invoice_statistics_from_scope_metadata(metadata_rows)
        if statistics is None:
            return {
                "status": runtime_status or "stale",
                "source_versions_by_scope": source_versions_by_scope,
            }
        if runtime_status is not None:
            return {
                "status": runtime_status,
                "source_versions_by_scope": source_versions_by_scope,
            }
        return {
            "status": "fresh",
            "statistics": statistics,
            "source_versions_by_scope": source_versions_by_scope,
        }


    def _upsert_pending_invoice_scope(
        self,
        connection: Any,
        *,
        scope_key: str,
        direction: str,
        filter_group: str,
        row_count: int,
        source_versions: dict[str, Any],
        statistics_metadata: dict[str, Any] | None = None,
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
                jsonb(
                    {
                        "scope_key": scope_key,
                        "row_count": row_count,
                        "source_versions": source_versions,
                        "statistics_metadata": dict(statistics_metadata or {}),
                    }
                ),
            ),
        )


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

    def get_batch_accounting_relation_rows_by_ids(
        self,
        row_ids: list[str],
        *,
        tenant_id: str = "default",
        scope_keys_hint: list[str] | None = None,
        submitted_year: str | None = None,
    ) -> dict[str, Any] | None:
        """Read the unsubmitted relation distribution and annual count in one snapshot."""
        normalized_ids = _dedupe_preserve_order(text(row_id) for row_id in list(row_ids or []))
        normalized_submitted_year = text(submitted_year)
        if normalized_submitted_year and not re.fullmatch(r"\d{4}", normalized_submitted_year):
            return None
        submitted_scope_keys = (
            [f"{normalized_submitted_year}-{month:02d}" for month in range(1, 13)]
            if normalized_submitted_year
            else []
        )
        if not normalized_ids and not normalized_submitted_year:
            return {
                "read_model_status": "fresh",
                "rows": [],
                "groups": [],
                "submitted_count": 0,
                "source_versions": {},
                "read_model_scope_keys": [],
                "stale_reasons": [],
            }
        normalized_scope_keys_hint = _dedupe_preserve_order(
            text(scope_key) for scope_key in list(scope_keys_hint or [])
        )
        bundle = self._connection.fetch_one(
            """
            /* batch_accounting_relation_rows_scope_groups */
            with requested_rows as (
                select requested.row_id, requested.position
                from unnest(%s::text[]) with ordinality as requested(row_id, position)
            ),
            matched_rows as materialized (
                select requested.position as row_position,
                       relation_row.row_id,
                       relation_row.row_type,
                       relation_row.scope_key,
                       relation_row.scope_month,
                       relation_row.relation_status,
                       relation_row.group_ids,
                       relation_row.linked_oa,
                       relation_row.linked_bank_transactions,
                       relation_row.linked_input_invoices,
                       relation_row.linked_output_invoices,
                       relation_row.source_versions
                from requested_rows requested
                join read_model.workbench_relation_rows relation_row
                  on relation_row.tenant_id = %s
                 and relation_row.row_id = requested.row_id
            ),
            candidate_scopes as materialized (
                select matched.scope_key, min(matched.row_position) as position
                from matched_rows matched
                group by matched.scope_key
                union all
                select hinted.scope_key, hinted.position
                from unnest(%s::text[]) with ordinality as hinted(scope_key, position)
                where not exists (select 1 from matched_rows)
            ),
            resolved_scopes as materialized (
                select combined.scope_key, min(combined.position) as position
                from (
                    select scope_key, position from candidate_scopes
                    union all
                    select annual.scope_key, annual.position + 100000
                    from unnest(%s::text[]) with ordinality as annual(scope_key, position)
                ) combined
                group by combined.scope_key
            ),
            scope_proof as (
                select requested.position,
                       requested.scope_key,
                       (scope.scope_key is not null) as scope_exists,
                       scope.source_versions,
                       dirty.status as dirty_status
                from resolved_scopes requested
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
            ),
            requested_groups as (
                select distinct item.group_id
                from matched_rows matched
                cross join lateral unnest(
                    coalesce(matched.group_ids, array[]::text[])
                ) as item(group_id)
            ),
            group_rows as (
                select group_row.group_id,
                       group_row.scope_key,
                       group_row.scope_month,
                       group_row.relation_source,
                       group_row.relation_kind,
                       group_row.relation_status,
                       group_row.oa_row_ids,
                       group_row.bank_transaction_ids,
                       group_row.input_invoice_ids,
                       group_row.output_invoice_ids,
                       group_row.source_versions,
                       group_row.payload
                from read_model.workbench_relation_groups group_row
                join requested_groups requested_group
                  on requested_group.group_id = group_row.group_id
                where group_row.tenant_id = %s
                  and group_row.scope_key in (select scope_key from resolved_scopes)
            ),
            submitted_count as (
                select count(distinct group_id)::integer as submitted_count
                from read_model.workbench_relation_groups
                where %s::boolean
                  and tenant_id = %s
                  and scope_key = any(%s)
                  and relation_status = 'linked'
                  and payload->'special_metadata'->>'source' = 'batch_accounting'
                  and coalesce(
                        nullif(payload->'special_metadata'->>'bank_year', ''),
                        nullif(payload->'special_metadata'->>'year', '')
                      ) = %s
            )
            select
                coalesce(
                    (
                        select jsonb_agg(
                            to_jsonb(matched_rows) - 'row_position'
                            order by row_position, scope_key
                        )
                        from matched_rows
                    ),
                    '[]'::jsonb
                ) as rows,
                coalesce(
                    (
                        select jsonb_agg(
                            jsonb_build_object(
                                'scope_key', scope_key,
                                'scope_exists', scope_exists,
                                'source_versions', source_versions,
                                'dirty_status', dirty_status
                            )
                            order by position
                        )
                        from scope_proof
                    ),
                    '[]'::jsonb
                ) as scope_proof,
                coalesce(
                    (select jsonb_agg(to_jsonb(group_rows) order by scope_key, group_id) from group_rows),
                    '[]'::jsonb
                ) as groups,
                submitted_count.submitted_count
            from submitted_count
            """,
            (
                normalized_ids,
                tenant_id,
                normalized_scope_keys_hint,
                submitted_scope_keys,
                tenant_id,
                tenant_id,
                tenant_id,
                bool(normalized_submitted_year),
                tenant_id,
                submitted_scope_keys,
                normalized_submitted_year,
            ),
        ) or {}
        rows = [dict(row) for row in list(bundle.get("rows") or []) if isinstance(row, dict)]
        scope_proof = [
            dict(proof)
            for proof in list(bundle.get("scope_proof") or [])
            if isinstance(proof, dict)
        ]
        proof_scope_keys = _dedupe_preserve_order(
            text(proof.get("scope_key")) for proof in scope_proof
        )
        groups = [dict(group) for group in list(bundle.get("groups") or []) if isinstance(group, dict)]
        if not rows:
            scope_keys = proof_scope_keys or normalized_scope_keys_hint
            if not scope_keys:
                return None
            return self._batch_accounting_relation_payload_from_rows(
                rows=[],
                groups=[],
                scope_keys=scope_keys,
                tenant_id=tenant_id,
                fallback_source_versions={},
                scope_proof=scope_proof,
                submitted_count=int_value(bundle.get("submitted_count"), 0),
            )

        row_scope_keys = _dedupe_preserve_order(text(row.get("scope_key")) for row in rows)
        scope_keys = proof_scope_keys if normalized_submitted_year else row_scope_keys
        returned_ids = {text(row.get("row_id")) for row in rows if text(row.get("row_id"))}
        if len(returned_ids) < len(normalized_ids):
            proof_payload = self._batch_accounting_relation_payload_from_rows(
                rows=rows,
                groups=[],
                scope_keys=scope_keys,
                tenant_id=tenant_id,
                scope_proof=scope_proof,
            )
            if proof_payload.get("read_model_status") != "fresh":
                return {
                    "read_model_status": "missing",
                    "rows": [],
                    "groups": [],
                    "source_versions": _source_versions_from_relation_records(rows),
                    "read_model_scope_keys": scope_keys,
                    "stale_reasons": ["missing_relation_rows"],
                }

        return self._batch_accounting_relation_payload_from_rows(
            rows=rows,
            groups=groups,
            scope_keys=scope_keys,
            tenant_id=tenant_id,
            scope_proof=scope_proof,
            submitted_count=int_value(bundle.get("submitted_count"), 0),
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


    def list_batch_accounting_relation_groups_by_year(
        self,
        *,
        year: str,
        tenant_id: str = "default",
    ) -> dict[str, Any] | None:
        normalized_year = text(year)
        if not re.fullmatch(r"\d{4}", normalized_year):
            return None
        scope_keys = [f"{normalized_year}-{month:02d}" for month in range(1, 13)]
        scope_proof = self._batch_accounting_relation_scope_proof(
            scope_keys=scope_keys,
            tenant_id=tenant_id,
        )
        payload = self._batch_accounting_relation_payload_from_rows(
            rows=[],
            groups=[],
            scope_keys=scope_keys,
            tenant_id=tenant_id,
            scope_proof=scope_proof,
        )
        if payload.get("read_model_status") != "fresh":
            return payload
        groups = self._connection.fetch_all(
            """
            select group_id, scope_key, scope_month, relation_source, relation_kind, relation_status,
                   oa_row_ids, bank_transaction_ids, input_invoice_ids, output_invoice_ids,
                   source_versions, payload, raw_payload
            from read_model.workbench_relation_groups
            where tenant_id = %s
              and scope_key = any(%s)
              and relation_status = 'linked'
              and payload->'special_metadata'->>'source' = 'batch_accounting'
              and coalesce(
                    nullif(payload->'special_metadata'->>'bank_year', ''),
                    nullif(payload->'special_metadata'->>'year', '')
                  ) = %s
            order by scope_month desc nulls last, group_id
            """,
            (tenant_id, scope_keys, normalized_year),
        )
        return self._batch_accounting_relation_payload_from_rows(
            rows=[],
            groups=groups,
            scope_keys=scope_keys,
            tenant_id=tenant_id,
            fallback_source_versions=payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
            scope_proof=scope_proof,
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
        proof_rows = self._batch_accounting_relation_scope_proof(
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
                where month_scope is not null and status = 'active'
                union
                select scope_month
                from read_model.workbench_relation_scopes
                where tenant_id = %s and scope_month is not null
            ) scopes
            where scope_month is not null
            order by scope_key
            """,
            (tenant_id,),
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
        tenant_id: str = "default",
    ) -> list[dict[str, Any]]:
        _ = tenant_id
        normalized_row_ids = text_list(row_ids)
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select case_id, status, relation_mode, row_ids, row_types, amount_check, raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and row_ids && %s::text[]
            order by updated_at desc, case_id
            """,
            (normalized_row_ids,),
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
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        _ = tenant_id
        normalized_scope_key = text(scope_key) or ""
        normalized_row_ids = text_list(row_ids)
        normalized_relation_modes = text_list(relation_modes)
        where = ["status = 'active'"]
        params: list[Any] = []
        if relation_modes is not None:
            if not normalized_relation_modes:
                raise ValueError("relation_modes must contain at least one mode when supplied.")
            where.append("relation_mode = any(%s)")
            params.append(normalized_relation_modes)
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
        return dict(scope_row) if isinstance(scope_row, dict) else None


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

    def workbench_relation_delta_source_versions(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
        tenant_id: str = "default",
    ) -> dict[str, Any]:
        normalized_scope_key = text(scope_key) or ""
        normalized_row_ids = text_list(row_ids)
        scope_month = month_start(normalized_scope_key)
        if not scope_month or not normalized_row_ids:
            return {}
        row = self._connection.fetch_one(
            """
            select
              scope.source_versions,
              greatest(
                nullif(scope.source_versions ->> 'workbench_pair_relations_updated_at', '')::timestamptz,
                (
                  select max(relation.updated_at)
                  from app.workbench_pair_relations relation
                  where relation.row_ids && %s::text[]
                )
              )::text as pair_relations_updated_at
            from read_model.workbench_relation_scopes scope
            where scope.tenant_id = %s
              and scope.scope_key = %s
            """,
            (normalized_row_ids, tenant_id, normalized_scope_key),
        )
        payload = row if isinstance(row, dict) else {}
        source_versions = payload.get("source_versions")
        if not isinstance(source_versions, dict):
            return {}
        result = dict(source_versions)
        result["workbench_pair_relations_updated_at"] = text(payload.get("pair_relations_updated_at"))
        return result

    def _batch_accounting_relation_scope_proof(
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
                   dirty.status as dirty_status
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
            (normalized_scope_keys, tenant_id, tenant_id),
        )

    def _batch_accounting_relation_payload_from_rows(
        self,
        *,
        rows: list[dict[str, Any]],
        groups: list[dict[str, Any]],
        scope_keys: list[str],
        tenant_id: str,
        fallback_source_versions: dict[str, Any] | None = None,
        scope_proof: list[dict[str, Any]] | None = None,
        submitted_count: int | None = None,
    ) -> dict[str, Any]:
        normalized_scope_keys = _dedupe_preserve_order(text(scope_key) for scope_key in list(scope_keys or []))
        proof_rows = scope_proof if scope_proof is not None else self._batch_accounting_relation_scope_proof(
            scope_keys=normalized_scope_keys,
            tenant_id=tenant_id,
        )
        proof_by_scope = {
            text(proof.get("scope_key")): proof
            for proof in list(proof_rows or [])
            if isinstance(proof, dict) and text(proof.get("scope_key"))
        }
        status = "fresh"
        stale_reasons: list[str] = []
        source_versions: dict[str, Any] = {}
        scope_source_versions: dict[str, dict[str, Any]] = {}
        for scope_key in normalized_scope_keys:
            proof = proof_by_scope.get(scope_key)
            if not isinstance(proof, dict) or not bool(proof.get("scope_exists")):
                status = "missing"
                stale_reasons.append(f"missing_scope:{scope_key}")
                continue
            dirty_status = text(proof.get("dirty_status"))
            if dirty_status:
                scope_status = "refreshing" if dirty_status in {"pending", "processing"} else "stale"
                status = scope_status
                stale_reasons.append(f"{scope_status}:{scope_key}")
            proof_source_versions = proof.get("source_versions")
            if isinstance(proof_source_versions, dict):
                scope_source_versions[scope_key] = dict(proof_source_versions)
                if not source_versions:
                    source_versions = dict(proof_source_versions)
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
            **({"submitted_count": int_value(submitted_count, 0) if status == "fresh" else 0} if submitted_count is not None else {}),
            "source_versions": source_versions,
            "read_model_scope_source_versions": scope_source_versions,
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

    def get_cost_statistics_scope_metadata(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key:
            return None
        row = self._connection.fetch_one(
            """
            select scope_key,
                   entry_count,
                   source_versions,
                   payload #> '{payload,statistics}' is not null as statistics_ready
            from read_model.cost_statistics_read_models
            where scope_key = %s
            limit 1
            """,
            (normalized_scope_key,),
        )
        if not isinstance(row, dict):
            return None
        return {
            "scope_key": normalized_scope_key,
            "entry_count": max(int_value(row.get("entry_count"), 0), 0),
            "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
            "statistics_ready": row.get("statistics_ready") is True,
        }

    def cost_statistics_aggregate_payload(
        self,
        *,
        project_scope: str,
        scope_keys: list[str],
        bank_accounts: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return _cost_statistics_aggregate_payload(
            self._connection,
            project_scope=project_scope,
            scope_keys=scope_keys,
            bank_accounts=bank_accounts,
        )

    def get_cost_statistics_freshness_gate(self, *, scope_key: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key:
            return None
        row = self._connection.fetch_one(
            """
            select
                model.scope_key,
                model.generated_at,
                model.source_versions,
                model.published_source_version,
                coalesce(
                    model.payload #> '{payload,bank_accounts}',
                    model.payload->'bank_accounts',
                    '[]'::jsonb
                ) as bank_accounts,
                coalesce(
                    nullif(model.payload->>'schema_version', ''),
                    nullif(model.raw_payload #>> '{normalized_payload,schema_version}', '')
                ) as schema_version,
                dirty.source_version as dirty_source_version,
                dirty.status as dirty_status,
                dirty.updated_at as dirty_updated_at,
                dirty.last_error as dirty_last_error,
                settings.source_settings,
                workbench.source_versions as workbench_source_versions,
                workbench_dirty.source_version as workbench_dirty_source_version,
                workbench_dirty.status as workbench_dirty_status,
                bank_detail.schema_version as bank_detail_schema_version,
                bank_detail.status as bank_detail_status,
                bank_detail.source_version as bank_detail_source_version,
                bank_detail.source_versions as bank_detail_source_versions,
                bank_detail_dirty.source_version as bank_detail_dirty_source_version,
                bank_detail_dirty.status as bank_detail_dirty_status,
                statistics_parent.scope_key as statistics_scope_key,
                statistics_parent.payload #> '{payload,statistics}' as statistics,
                statistics_parent.published_source_version as statistics_published_source_version,
                coalesce(
                    nullif(statistics_parent.payload->>'schema_version', ''),
                    nullif(statistics_parent.raw_payload #>> '{normalized_payload,schema_version}', '')
                ) as statistics_schema_version,
                statistics_parent_dirty.source_version as statistics_dirty_source_version,
                statistics_parent_dirty.status as statistics_dirty_status,
                statistics_children.has_failed as statistics_child_has_failed,
                statistics_children.has_active as statistics_child_has_active
            from read_model.cost_statistics_read_models model
            left join lateral (
                select source_version, status, updated_at, last_error
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'cost_statistics'
                  and scope_key = model.scope_key
                order by source_version desc, updated_at desc, id desc
                limit 1
            ) dirty on true
            left join lateral (
                select jsonb_build_object(
                    'bank_transaction_tags', coalesce(settings_payload->'bank_transaction_tags', '{}'::jsonb),
                    'bank_account_mappings', coalesce(settings_payload->'bank_account_mappings', '[]'::jsonb),
                    'cost_statistics_tag_selection',
                        coalesce(settings_payload->'cost_statistics_tag_selection', '{}'::jsonb)
                ) as source_settings
                from app.app_settings
                where settings_key = 'app_settings'
                limit 1
            ) settings on true
            left join lateral (
                select source_versions
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and scope_key = split_part(model.scope_key, ':', 2)
                  and status = 'active'
                  and split_part(model.scope_key, ':', 2) <> 'all'
                order by activated_at desc nulls last,
                         completed_at desc nulls last,
                         updated_at desc
                limit 1
            ) workbench on true
            left join lateral (
                select source_version, status
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'workbench'
                  and scope_key = split_part(model.scope_key, ':', 2)
                  and split_part(model.scope_key, ':', 2) <> 'all'
                order by source_version desc, updated_at desc, id desc
                limit 1
            ) workbench_dirty on true
            left join lateral (
                select schema_version, status, source_version, source_versions
                from read_model.bank_detail_scopes
                where tenant_id = 'default'
                  and scope_type = 'bank_detail'
                  and scope_key = split_part(model.scope_key, ':', 2)
                  and split_part(model.scope_key, ':', 2) <> 'all'
                limit 1
            ) bank_detail on true
            left join lateral (
                select source_version, status
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'bank_detail'
                  and scope_key = split_part(model.scope_key, ':', 2)
                  and split_part(model.scope_key, ':', 2) <> 'all'
                order by source_version desc, updated_at desc, id desc
                limit 1
            ) bank_detail_dirty on true
            left join lateral (
                select scope_key, payload, raw_payload, published_source_version
                from read_model.cost_statistics_read_models
                where scope_key = split_part(model.scope_key, ':', 1) || ':all'
                limit 1
            ) statistics_parent on true
            left join lateral (
                select source_version, status
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'cost_statistics'
                  and scope_key = statistics_parent.scope_key
                order by source_version desc, updated_at desc, id desc
                limit 1
            ) statistics_parent_dirty on true
            left join lateral (
                select
                    coalesce(bool_or(status = 'failed'), false) as has_failed,
                    coalesce(bool_or(status in ('pending', 'processing')), false) as has_active
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'cost_statistics'
                  and scope_key like split_part(model.scope_key, ':', 1) || ':%%'
                  and scope_key <> split_part(model.scope_key, ':', 1) || ':all'
                  and status in ('pending', 'processing', 'failed')
            ) statistics_children on true
            where model.scope_key = %s
            limit 1
            """,
            (normalized_scope_key,),
        )
        if row is None:
            return None
        published_source_version = (
            int_value(row.get("published_source_version"), -1)
            if row.get("published_source_version") is not None
            else None
        )
        dirty_source_version = (
            int_value(row.get("dirty_source_version"), -1)
            if row.get("dirty_source_version") is not None
            else None
        )
        dirty_status = text(row.get("dirty_status"))
        refresh_status = "fresh" if published_source_version is not None else "stale"
        stale_reasons: list[str] = []
        if published_source_version is None:
            stale_reasons.append("published_source_version_missing")
        if dirty_status in {"pending", "processing"}:
            refresh_status = "refreshing"
        elif dirty_status == "failed":
            refresh_status = "failed"
            stale_reasons.append("dirty_scope_failed")
        elif published_source_version is not None and dirty_status is not None and (
            dirty_status != "done" or dirty_source_version != published_source_version
        ):
            refresh_status = "stale"
            stale_reasons.append("published_source_version_mismatch")
        source_settings = row.get("source_settings") if isinstance(row.get("source_settings"), dict) else None
        if source_settings is not None and not (
            isinstance(source_settings.get("bank_transaction_tags"), dict)
            and isinstance(source_settings.get("bank_account_mappings"), list)
            and isinstance(source_settings.get("cost_statistics_tag_selection"), dict)
        ):
            source_settings = None
        if source_settings is None:
            refresh_status = "stale" if refresh_status == "fresh" else refresh_status
            stale_reasons.append("cost_statistics_source_settings_missing")

        scope_month = normalized_scope_key.split(":", 1)[1] if ":" in normalized_scope_key else ""
        workbench_source_versions = (
            row.get("workbench_source_versions")
            if isinstance(row.get("workbench_source_versions"), dict)
            else {}
        )
        bank_detail_source_versions = (
            row.get("bank_detail_source_versions")
            if isinstance(row.get("bank_detail_source_versions"), dict)
            else {}
        )
        if scope_month != "all":
            dependency_statuses = {
                text(row.get("workbench_dirty_status")),
                text(row.get("bank_detail_dirty_status")),
            }
            if "failed" in dependency_statuses:
                refresh_status = "failed"
                stale_reasons.append("cost_statistics_dependency_dirty_scope_failed")
            elif dependency_statuses.intersection({"pending", "processing"}) and refresh_status != "failed":
                refresh_status = "refreshing"
                stale_reasons.append("cost_statistics_dependency_refreshing")
            if not workbench_source_versions:
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("workbench_source_versions_missing")
            elif (
                row.get("workbench_dirty_source_version") is not None
                and int_value(workbench_source_versions.get("source_version"), -1)
                != int_value(row.get("workbench_dirty_source_version"), -1)
            ):
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("workbench_published_source_version_mismatch")
            bank_detail_schema_version = int_value(row.get("bank_detail_schema_version"), 0)
            bank_detail_status = text(row.get("bank_detail_status"))
            if bank_detail_schema_version == 0:
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("bank_detail_scope_missing")
            elif bank_detail_schema_version != BANK_DETAIL_READ_MODEL_SCHEMA_VERSION:
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("bank_detail_schema_version_mismatch")
            if not bank_detail_source_versions:
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("bank_detail_source_versions_missing")
            if (
                row.get("bank_detail_dirty_source_version") is not None
                and int_value(row.get("bank_detail_source_version"), -1)
                != int_value(row.get("bank_detail_dirty_source_version"), -1)
            ):
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("bank_detail_published_source_version_mismatch")
            if bank_detail_status != "fresh":
                refresh_status = "stale" if refresh_status == "fresh" else refresh_status
                stale_reasons.append("bank_detail_scope_not_fresh")
        statistics = _cost_statistics_page_statistics(row.get("statistics"))
        statistics_published_source_version = (
            int_value(row.get("statistics_published_source_version"), -1)
            if row.get("statistics_published_source_version") is not None
            else None
        )
        statistics_dirty_source_version = (
            int_value(row.get("statistics_dirty_source_version"), -1)
            if row.get("statistics_dirty_source_version") is not None
            else None
        )
        statistics_dirty_status = text(row.get("statistics_dirty_status"))
        statistics_status = "fresh"
        if statistics_published_source_version is None or statistics is None:
            statistics_status = "stale"
        if text(row.get("statistics_schema_version")) != COST_STATISTICS_READ_MODEL_SCHEMA_VERSION:
            statistics_status = "stale"
        if bool(row.get("statistics_child_has_failed")) or statistics_dirty_status == "failed":
            statistics_status = "failed"
        elif bool(row.get("statistics_child_has_active")) or statistics_dirty_status in {"pending", "processing"}:
            statistics_status = "refreshing"
        elif statistics_dirty_status is not None and (
            statistics_dirty_status != "done"
            or statistics_dirty_source_version != statistics_published_source_version
        ):
            statistics_status = "stale"
        if statistics_status != "fresh":
            statistics = None
        return {
            "scope_key": normalized_scope_key,
            "schema_version": text(row.get("schema_version")),
            "generated_at": text(row.get("generated_at")),
            "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
            "source_settings": source_settings or {},
            "workbench_source_versions": workbench_source_versions,
            "bank_detail_source_versions": bank_detail_source_versions,
            "bank_accounts": row.get("bank_accounts") if isinstance(row.get("bank_accounts"), list) else [],
            "published_source_version": published_source_version,
            "dirty_source_version": dirty_source_version,
            "refresh_status": refresh_status,
            "stale_reasons": stale_reasons,
            "statistics": statistics,
            "statistics_status": statistics_status,
            "statistics_scope_key": text(row.get("statistics_scope_key"))
            or f"{normalized_scope_key.split(':', 1)[0]}:all",
            "statistics_published_source_version": statistics_published_source_version,
            "dirty_scope": (
                {
                    "source_version": dirty_source_version,
                    "status": dirty_status,
                    "updated_at": row.get("dirty_updated_at"),
                    "last_error": row.get("dirty_last_error"),
                }
                if dirty_status is not None
                else None
            ),
        }

    def get_cost_statistics_page(
        self,
        *,
        project_scope: str,
        scope_kind: str,
        scope_value: str | None,
        view: str,
        filters: dict[str, str],
        selected_tag_codes: list[str] | None,
        cursor_values: tuple[str, str, str, str] | None,
        page_size: int,
    ) -> dict[str, Any] | None:
        normalized_project_scope = text(project_scope)
        if normalized_project_scope not in {"active", "all"}:
            return None
        if view not in {"time", "project", "bank", "expense_type", "bank_tag"}:
            return None

        table_name = (
            "read_model.cost_statistics_bank_flow_rows"
            if view in {"time", "bank_tag"}
            else "read_model.cost_statistics_rows"
        )
        if table_name.endswith("bank_flow_rows"):
            tag_columns = """
                bank_tag_code,
                bank_tag_label,
                bank_tag_primary_label,
                bank_tag_sub_label,
                bank_tag_label_path
            """
        else:
            tag_columns = """
                nullif(payload->>'bank_tag_code', '') as bank_tag_code,
                nullif(payload->>'bank_tag_label', '') as bank_tag_label,
                nullif(payload->>'bank_tag_primary_label', '') as bank_tag_primary_label,
                nullif(payload->>'bank_tag_sub_label', '') as bank_tag_sub_label,
                coalesce(payload->'bank_tag_label_path', '[]'::jsonb) as bank_tag_label_path
            """

        base_params: list[Any] = [normalized_project_scope]
        scope_sql = ""
        if scope_kind == "month":
            scope_sql = "and scope_month = %s::date"
            base_params.append(f"{scope_value}-01")
        elif scope_kind == "year":
            year = int(scope_value or 0)
            scope_sql = "and scope_month >= %s::date and scope_month < %s::date"
            base_params.extend((f"{year:04d}-01-01", f"{year + 1:04d}-01-01"))
        elif scope_kind != "all":
            return None

        tag_filter_sql = ""
        cost_tag_filter_sql = ""
        if selected_tag_codes is not None:
            tag_filter_sql = (
                "and coalesce(nullif(bank_tag_code, ''), %s) = any(%s)"
            )
            base_params.extend(("__uncategorized__", selected_tag_codes))
            cost_tag_filter_sql = (
                "and coalesce(nullif(payload->>'bank_tag_code', ''), %s) = any(%s)"
            )

        cost_count_params: list[Any] = [normalized_project_scope]
        if selected_tag_codes is not None:
            cost_count_params.extend(("__uncategorized__", selected_tag_codes))

        primary_facet_sql = "'[]'::jsonb"
        secondary_facet_sql = "'[]'::jsonb"
        row_filter_sql = "false"
        row_filter_params: list[Any] = []
        facet_params: list[Any] = []
        project_name = text(filters.get("project_name"))
        expense_type = text(filters.get("expense_type"))
        payment_account_label = text(filters.get("payment_account_label"))
        tag_primary = text(filters.get("bank_tag_primary_label"))
        tag_sub = text(filters.get("bank_tag_sub_label"))

        if view == "time":
            row_filter_sql = "true"
        elif view == "project":
            primary_facet_sql = _cost_statistics_project_facets_sql()
            if project_name:
                secondary_facet_sql = _cost_statistics_expense_facets_sql("project_name = %s")
                facet_params.append(project_name)
            if project_name and expense_type:
                row_filter_sql = "project_name = %s and expense_type = %s"
                row_filter_params.extend((project_name, expense_type))
        elif view == "bank":
            primary_facet_sql = _cost_statistics_bank_facets_sql()
            if payment_account_label:
                secondary_facet_sql = _cost_statistics_project_facets_sql("payment_account_label = %s")
                facet_params.append(payment_account_label)
            if payment_account_label and project_name:
                row_filter_sql = "payment_account_label = %s and project_name = %s"
                row_filter_params.extend((payment_account_label, project_name))
        elif view == "expense_type":
            primary_facet_sql = _cost_statistics_expense_facets_sql()
            if expense_type:
                row_filter_sql = "expense_type = %s"
                row_filter_params.append(expense_type)
        elif view == "bank_tag":
            primary_facet_sql = _cost_statistics_bank_tag_primary_facets_sql()
            if tag_primary:
                secondary_facet_sql = _cost_statistics_bank_tag_sub_facets_sql()
                facet_params.append(tag_primary)
            if tag_primary and tag_sub:
                row_filter_sql = "tag_primary_label = %s and tag_sub_label = %s"
                row_filter_params.extend((tag_primary, tag_sub))

        cursor_sql = ""
        cursor_params: list[Any] = []
        if cursor_values is not None:
            cursor_sql = """
                where
                    sort_date < %s::date
                    or (sort_date = %s::date and sort_time < %s)
                    or (sort_date = %s::date and sort_time = %s and (transaction_id, row_key) > (%s, %s))
            """
            cursor_date, cursor_time, cursor_transaction_id, cursor_row_key = cursor_values
            cursor_params.extend(
                (
                    cursor_date,
                    cursor_date,
                    cursor_time,
                    cursor_date,
                    cursor_time,
                    cursor_transaction_id,
                    cursor_row_key,
                )
            )
        query_params = [
            normalized_project_scope,
            *cost_count_params,
            *base_params,
            *row_filter_params,
            *cursor_params,
            page_size + 1,
            *facet_params,
        ]

        row = self._connection.fetch_one(
            f"""
            with available_years as materialized (
                select distinct to_char(scope_month, 'YYYY') as scope_year
                from {table_name}
                where project_scope = %s
                  and scope_month is not null
            ), selected_cost_transactions as materialized (
                select transaction_id
                from read_model.cost_statistics_rows
                where project_scope = %s
                  {cost_tag_filter_sql}
            ), raw_base as materialized (
                select
                    scope_key,
                    project_scope,
                    scope_month,
                    row_key,
                    transaction_id,
                    group_id,
                    trade_time_text,
                    trade_date,
                    coalesce(trade_date, date '0001-01-01') as sort_date,
                    coalesce(trade_time_text, '') as sort_time,
                    counterparty_name,
                    payment_account_label,
                    direction,
                    remark,
                    project_id,
                    project_name,
                    expense_type,
                    expense_content,
                    amount,
                    oa_applicant,
                    {tag_columns}
                from {table_name}
                where project_scope = %s
                  {scope_sql}
            ), base as materialized (
                select
                    raw_base.*,
                    coalesce(nullif(bank_tag_primary_label, ''), nullif(bank_tag_label, ''), '未标记')
                        as tag_primary_label,
                    coalesce(nullif(bank_tag_sub_label, ''), nullif(bank_tag_label, ''), '未标记')
                        as tag_sub_label
                from raw_base
                where true {tag_filter_sql}
            ), row_matches as materialized (
                select * from base where {row_filter_sql}
            ), paged as (
                select *
                from row_matches
                {cursor_sql}
                order by sort_date desc, sort_time desc, transaction_id, row_key
                limit %s
            )
            select jsonb_build_object(
                'summary', (
                    select jsonb_build_object(
                        'row_count', count(*),
                        'transaction_count', count(distinct transaction_id),
                        'total_amount', coalesce(sum(amount), 0)::text,
                        'expense_amount', coalesce(sum(amount) filter (where direction = '支出'), 0)::text,
                        'income_amount', coalesce(sum(amount) filter (where direction = '收入'), 0)::text,
                        'expense_transaction_count', count(distinct transaction_id) filter (where direction = '支出'),
                        'income_transaction_count', count(distinct transaction_id) filter (where direction = '收入')
                    ) from base
                ),
                'cost_transaction_count', (
                    select count(distinct transaction_id) from selected_cost_transactions
                ),
                'available_years', (
                    select coalesce(jsonb_agg(scope_year order by scope_year desc), '[]'::jsonb)
                    from available_years
                ),
                'primary_facets', {primary_facet_sql},
                'secondary_facets', {secondary_facet_sql},
                'row_count', (select count(*) from row_matches),
                'rows', (
                    select coalesce(
                        jsonb_agg(
                            jsonb_build_object(
                                'transaction_id', transaction_id,
                                'group_id', group_id,
                                'month', to_char(scope_month, 'YYYY-MM'),
                                'trade_time', trade_time_text,
                                'direction', direction,
                                'project_name', project_name,
                                'project_id', project_id,
                                'expense_type', expense_type,
                                'expense_content', expense_content,
                                'amount', amount::text,
                                'counterparty_name', counterparty_name,
                                'payment_account_label', payment_account_label,
                                'remark', remark,
                                'oa_applicant', oa_applicant,
                                'bank_tag_code', bank_tag_code,
                                'bank_tag_label', bank_tag_label,
                                'bank_tag_primary_label', bank_tag_primary_label,
                                'bank_tag_sub_label', bank_tag_sub_label,
                                'bank_tag_label_path', bank_tag_label_path,
                                '_cursor_date', sort_date::text,
                                '_cursor_time', sort_time,
                                '_cursor_transaction_id', transaction_id,
                                '_cursor_row_key', row_key
                            ) order by sort_date desc, sort_time desc, transaction_id, row_key
                        ),
                        '[]'::jsonb
                    ) from paged
                )
            ) as payload
            """,
            tuple(query_params),
        )
        payload = row.get("payload") if isinstance(row, dict) else None
        if not isinstance(payload, dict):
            return None
        raw_rows = [dict(item) for item in list(payload.get("rows") or []) if isinstance(item, dict)]
        has_more = len(raw_rows) > page_size
        page_rows = raw_rows[:page_size]
        next_cursor_values: tuple[str, str, str, str] | None = None
        if has_more and page_rows:
            last_row = page_rows[-1]
            next_cursor_values = (
                str(last_row.get("_cursor_date") or "0001-01-01"),
                str(last_row.get("_cursor_time") or ""),
                str(last_row.get("_cursor_transaction_id") or ""),
                str(last_row.get("_cursor_row_key") or ""),
            )
        for item in page_rows:
            for key in ("_cursor_date", "_cursor_time", "_cursor_transaction_id", "_cursor_row_key"):
                item.pop(key, None)
        payload["rows"] = page_rows
        payload["next_cursor_values"] = next_cursor_values
        return payload

    def get_cost_statistics_export_page(
        self,
        *,
        project_scope: str,
        month: str,
        start_month: str | None,
        end_month: str | None,
        start_date: str | None,
        end_date: str | None,
        project_names: list[str],
        expense_types: list[str],
        selected_tag_codes: list[str] | None,
        row_shape: str,
        offset: int,
        page_size: int,
        include_summary: bool,
    ) -> dict[str, Any] | None:
        normalized_project_scope = text(project_scope)
        normalized_month = text(month) or "all"
        normalized_row_shape = text(row_shape)
        if normalized_project_scope not in {"active", "all"}:
            return None
        if normalized_row_shape not in {"raw_bank", "raw_cost", "project_month", "project_year", "month_summary"}:
            return None
        normalized_offset = max(int_value(offset, 0), 0)
        normalized_page_size = int_value(page_size, 0)
        if normalized_page_size < 1 or normalized_page_size > 1000:
            return None

        if start_month and end_month and start_month > end_month:
            start_month, end_month = end_month, start_month
        if start_date and end_date and start_date > end_date:
            start_date, end_date = end_date, start_date

        table_name = (
            "read_model.cost_statistics_bank_flow_rows"
            if normalized_row_shape == "raw_bank"
            else "read_model.cost_statistics_rows"
        )
        bank_tag_code_sql = (
            "bank_tag_code"
            if normalized_row_shape == "raw_bank"
            else "nullif(payload->>'bank_tag_code', '')"
        )
        bank_tag_label_sql = (
            "bank_tag_label"
            if normalized_row_shape == "raw_bank"
            else "nullif(payload->>'bank_tag_label', '')"
        )
        bank_tag_primary_sql = (
            "bank_tag_primary_label"
            if normalized_row_shape == "raw_bank"
            else "nullif(payload->>'bank_tag_primary_label', '')"
        )
        bank_tag_sub_sql = (
            "bank_tag_sub_label"
            if normalized_row_shape == "raw_bank"
            else "nullif(payload->>'bank_tag_sub_label', '')"
        )
        bank_tag_path_sql = (
            "bank_tag_label_path"
            if normalized_row_shape == "raw_bank"
            else "coalesce(payload->'bank_tag_label_path', '[]'::jsonb)"
        )

        where_parts = ["project_scope = %s"]
        params: list[Any] = [normalized_project_scope]
        if normalized_month.lower() != "all":
            if not MONTH_SCOPE_RE.fullmatch(normalized_month):
                return None
            where_parts.append("scope_month = %s::date")
            params.append(f"{normalized_month}-01")
        if start_month:
            if not MONTH_SCOPE_RE.fullmatch(start_month):
                return None
            where_parts.append("scope_month >= %s::date")
            params.append(f"{start_month}-01")
        if end_month:
            if not MONTH_SCOPE_RE.fullmatch(end_month):
                return None
            where_parts.append("scope_month < (%s::date + interval '1 month')")
            params.append(f"{end_month}-01")
        if start_date:
            where_parts.append("trade_date >= %s::date")
            params.append(start_date)
        if end_date:
            where_parts.append("trade_date <= %s::date")
            params.append(end_date)
        normalized_project_names = sorted({text(item) for item in project_names if text(item)})
        if normalized_project_names:
            where_parts.append("project_name = any(%s)")
            params.append(normalized_project_names)
        normalized_expense_types = sorted({text(item) for item in expense_types if text(item)})
        if normalized_expense_types:
            where_parts.append("expense_type = any(%s)")
            params.append(normalized_expense_types)
        if selected_tag_codes is not None:
            where_parts.append(f"coalesce({bank_tag_code_sql}, %s) = any(%s)")
            params.extend(("__uncategorized__", list(selected_tag_codes)))

        where_sql = " and ".join(where_parts)
        base_sql = f"""
            select
                scope_month,
                row_key,
                transaction_id,
                group_id,
                trade_time_text,
                trade_date,
                counterparty_name,
                payment_account_label,
                direction,
                remark,
                project_id,
                project_name,
                expense_type,
                expense_content,
                amount,
                oa_applicant,
                {bank_tag_code_sql} as bank_tag_code,
                {bank_tag_label_sql} as bank_tag_label,
                {bank_tag_primary_sql} as bank_tag_primary_label,
                {bank_tag_sub_sql} as bank_tag_sub_label,
                {bank_tag_path_sql} as bank_tag_label_path
            from {table_name}
            where {where_sql}
        """
        if normalized_row_shape == "project_month":
            result_sql = """
                select
                    to_char(trade_date, 'YYYY-MM') as period_label,
                    project_name,
                    expense_type,
                    expense_content,
                    sum(amount)::text as amount,
                    count(distinct transaction_id)::bigint as transaction_count
                from base
                group by to_char(trade_date, 'YYYY-MM'), project_name, expense_type, expense_content
            """
            order_sql = "period_label, project_name, expense_type, expense_content"
        elif normalized_row_shape == "project_year":
            result_sql = """
                select
                    to_char(trade_date, 'YYYY') as period_label,
                    project_name,
                    expense_type,
                    expense_content,
                    sum(amount)::text as amount,
                    count(distinct transaction_id)::bigint as transaction_count
                from base
                group by to_char(trade_date, 'YYYY'), project_name, expense_type, expense_content
            """
            order_sql = "period_label, project_name, expense_type, expense_content"
        elif normalized_row_shape == "month_summary":
            result_sql = """
                select
                    project_name,
                    expense_type,
                    expense_content,
                    sum(amount)::text as amount,
                    count(distinct transaction_id)::bigint as transaction_count
                from base
                group by project_name, expense_type, expense_content
            """
            order_sql = "project_name, expense_type, expense_content"
        else:
            result_sql = "select * from base"
            order_sql = (
                "coalesce(trade_date, date '0001-01-01') desc, "
                "coalesce(trade_time_text, '') desc, transaction_id, row_key"
            )

        summary: dict[str, Any] | None = None
        if include_summary:
            summary_row = self._connection.fetch_one(
                f"""
                with base as materialized ({base_sql}), result_rows as materialized ({result_sql})
                select
                    (select count(*) from base)::bigint as source_row_count,
                    (select count(*) from result_rows)::bigint as row_count,
                    (select count(distinct transaction_id) from base)::bigint as transaction_count,
                    (select coalesce(sum(amount), 0)::text from base) as total_amount,
                    (select coalesce(sum(amount) filter (where direction = '支出'), 0)::text from base)
                        as expense_amount,
                    (select coalesce(sum(amount) filter (where direction = '收入'), 0)::text from base)
                        as income_amount,
                    (select count(distinct transaction_id) filter (where direction = '支出') from base)::bigint
                        as expense_transaction_count,
                    (select count(distinct transaction_id) filter (where direction = '收入') from base)::bigint
                        as income_transaction_count,
                    (select count(distinct expense_type) from base)::bigint as expense_type_count
                """,
                tuple(params),
            )
            if not isinstance(summary_row, dict):
                return None
            summary = dict(summary_row)

        rows = self._connection.fetch_all(
            f"""
            with base as materialized ({base_sql}), result_rows as ({result_sql})
            select *
            from result_rows
            order by {order_sql}
            offset %s
            limit %s
            """,
            (*params, normalized_offset, normalized_page_size),
        )
        page_rows = [dict(row) for row in rows if isinstance(row, dict)]
        return {
            "summary": summary,
            "rows": page_rows,
            "next_offset": (
                normalized_offset + len(page_rows)
                if len(page_rows) == normalized_page_size
                else None
            ),
        }

    def get_cost_statistics_transaction(
        self,
        *,
        project_scope: str,
        transaction_id: str,
    ) -> dict[str, Any] | None:
        normalized_project_scope = text(project_scope)
        normalized_transaction_id = text(transaction_id)
        if normalized_project_scope not in {"active", "all"} or normalized_transaction_id is None:
            return None
        row = self._connection.fetch_one(
            """
            with candidate as (
                select
                    0 as row_priority, 'cost' as row_kind,
                    scope_key, project_scope, scope_month::text as scope_month, row_key, transaction_id,
                    group_id, trade_time_text, trade_date::text as trade_date, counterparty_name,
                    payment_account_label, direction, remark, project_id, project_name, expense_type,
                    expense_content, amount::text as amount, oa_applicant,
                    null::text as bank_tag_code, null::text as bank_tag_label,
                    null::text as bank_tag_primary_label, null::text as bank_tag_sub_label,
                    '[]'::jsonb as bank_tag_label_path, payload, raw_payload
                from read_model.cost_statistics_rows
                where project_scope = %s and transaction_id = %s
                union all
                select
                    1 as row_priority, 'bank_flow' as row_kind,
                    scope_key, project_scope, scope_month::text as scope_month, row_key, transaction_id,
                    group_id, trade_time_text, trade_date::text as trade_date, counterparty_name,
                    payment_account_label, direction, remark, project_id, project_name, expense_type,
                    expense_content, amount::text as amount, oa_applicant,
                    bank_tag_code, bank_tag_label, bank_tag_primary_label, bank_tag_sub_label,
                    bank_tag_label_path, payload, raw_payload
                from read_model.cost_statistics_bank_flow_rows
                where project_scope = %s and transaction_id = %s
            ), selected as (
                select *
                from candidate
                order by row_priority, scope_month desc, row_key
                limit 1
            ), allocations as (
                select coalesce(
                    jsonb_agg(
                        jsonb_build_object(
                            'row_key', row_key,
                            'project_name', project_name,
                            'project_id', coalesce(project_id, ''),
                            'expense_type', expense_type,
                            'expense_content', coalesce(expense_content, ''),
                            'oa_applicant', coalesce(nullif(oa_applicant, ''), '—'),
                            'amount', amount::text
                        ) order by row_key
                    ),
                    '[]'::jsonb
                ) as cost_allocations
                from read_model.cost_statistics_rows
                where project_scope = %s and transaction_id = %s
            )
            select selected.*, allocations.cost_allocations
            from selected
            cross join allocations
            """,
            (
                normalized_project_scope,
                normalized_transaction_id,
                normalized_project_scope,
                normalized_transaction_id,
                normalized_project_scope,
                normalized_transaction_id,
            ),
        )
        if row is None:
            return None
        return _cost_statistics_row_payload(row, fallback_index=0)

    def publish_cost_statistics_read_models(
        self,
        snapshot: dict[str, Any],
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        changed_scope_keys: set[str] | None = None,
    ) -> bool:
        normalized_tenant_id = text(tenant_id)
        normalized_scope_key = text(scope_key)
        if normalized_tenant_id is None or normalized_scope_key is None:
            raise ValueError("tenant_id and scope_key are required for cost statistics publish.")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            raise ValueError("source_version must be a non-negative integer for cost statistics publish.")

        def publish(connection: Any) -> bool:
            current = connection.fetch_one(
                """
                select source_version
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = 'cost_statistics'
                  and scope_key = %s
                  and status in ('pending', 'processing')
                for update
                """,
                (normalized_tenant_id, normalized_scope_key),
            )
            if current is None or int_value(current.get("source_version"), -1) != source_version:
                return False
            self._write_cost_statistics_read_models(
                connection,
                snapshot,
                changed_scope_keys=changed_scope_keys,
                published_source_version=source_version,
            )
            return True

        return run_in_transaction(self._connection, publish)

    def publish_cost_statistics_relation_delta(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        model: dict[str, Any],
        replacement_rows: list[dict[str, Any]],
        affected_transaction_ids: list[str],
        affected_group_ids: list[str],
    ) -> bool:
        normalized_tenant_id = text(tenant_id)
        normalized_scope_key = text(scope_key)
        if normalized_tenant_id is None or normalized_scope_key is None:
            raise ValueError("tenant_id and scope_key are required for cost statistics relation delta publish.")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            raise ValueError("source_version must be a non-negative integer for cost statistics relation delta publish.")
        if _is_cost_statistics_parent_scope(normalized_scope_key, payload=model):
            raise ValueError("cost statistics relation delta requires a concrete month scope.")

        transaction_ids = sorted({value for item in affected_transaction_ids if (value := text(item))})
        group_ids = sorted({value for item in affected_group_ids if (value := text(item))})

        def publish(connection: Any) -> bool:
            current = connection.fetch_one(
                """
                select source_version
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = 'cost_statistics'
                  and scope_key = %s
                  and status in ('pending', 'processing')
                for update
                """,
                (normalized_tenant_id, normalized_scope_key),
            )
            if current is None or int_value(current.get("source_version"), -1) != source_version:
                return False
            connection.execute(
                """
                delete from read_model.cost_statistics_rows
                where scope_key = %s
                  and (
                    transaction_id = any(%s::text[])
                    or group_id = any(%s::text[])
                  )
                """,
                (normalized_scope_key, transaction_ids, group_ids),
            )
            source_versions = model.get("source_versions") if isinstance(model.get("source_versions"), dict) else {}
            connection.execute(
                """
                update read_model.cost_statistics_rows
                set source_versions = %s::jsonb,
                    generated_at = coalesce(%s::timestamptz, generated_at),
                    cache_status = %s,
                    updated_at = now()
                where scope_key = %s
                """,
                (
                    jsonb(source_versions),
                    text(model.get("generated_at")),
                    text(model.get("cache_status") or "ready") or "ready",
                    normalized_scope_key,
                ),
            )
            delta_model = dict(model)
            delta_payload = dict(delta_model.get("payload") or {})
            delta_payload["time_rows"] = list(replacement_rows)
            delta_model["payload"] = delta_payload
            self._insert_cost_statistics_rows(
                connection,
                scope_key=normalized_scope_key,
                payload=delta_model,
            )
            count_row = connection.fetch_one(
                "select count(*)::integer as row_count from read_model.cost_statistics_rows where scope_key = %s",
                (normalized_scope_key,),
            )
            entry_count = int_value((count_row or {}).get("row_count"), 0)
            metadata_model = dict(model)
            metadata_model["payload"] = _cost_statistics_aggregate_payload(
                connection,
                project_scope=text(model.get("project_scope")) or normalized_scope_key.split(":", 1)[0],
                scope_keys=[normalized_scope_key],
                bank_accounts=list((model.get("payload") or {}).get("bank_accounts") or [])
                if isinstance(model.get("payload"), dict)
                else [],
            )
            metadata_model["entry_count"] = entry_count
            self._save_generic_read_model_snapshots(
                connection,
                {"read_models": {normalized_scope_key: metadata_model}},
                table="read_model.cost_statistics_read_models",
                changed_scope_keys={normalized_scope_key},
                default_project_scope="all",
            )
            connection.execute(
                """
                update read_model.cost_statistics_read_models
                set published_source_version = %s,
                    entry_count = %s,
                    updated_at = now()
                where scope_key = %s
                """,
                (source_version, entry_count, normalized_scope_key),
            )
            return True

        return run_in_transaction(self._connection, publish)

    def acknowledge_unchanged_cost_statistics_scope(
        self,
        *,
        tenant_id: str,
        scope_key: str,
        source_version: int,
        source_versions: dict[str, Any],
    ) -> bool:
        normalized_tenant_id = text(tenant_id)
        normalized_scope_key = text(scope_key)
        if normalized_tenant_id is None or normalized_scope_key is None:
            raise ValueError("tenant_id and scope_key are required for cost statistics unchanged acknowledgement.")
        if isinstance(source_version, bool) or not isinstance(source_version, int) or source_version < 0:
            raise ValueError("source_version must be a non-negative integer for cost statistics unchanged acknowledgement.")
        if not isinstance(source_versions, dict):
            raise ValueError("source_versions must be an object for cost statistics unchanged acknowledgement.")

        def acknowledge(connection: Any) -> bool:
            current = connection.fetch_one(
                """
                select source_version
                from job.read_model_dirty_scopes
                where tenant_id = %s
                  and scope_type = 'cost_statistics'
                  and scope_key = %s
                  and status in ('pending', 'processing')
                for update
                """,
                (normalized_tenant_id, normalized_scope_key),
            )
            if current is None or int_value(current.get("source_version"), -1) != source_version:
                return False
            acknowledged = connection.fetch_one(
                """
                update read_model.cost_statistics_read_models
                set published_source_version = %s,
                    updated_at = now()
                where scope_key = %s
                  and source_versions = %s::jsonb
                  and (published_source_version is null or published_source_version <= %s)
                returning scope_key
                """,
                (source_version, normalized_scope_key, jsonb(source_versions), source_version),
            )
            return acknowledged is not None

        return run_in_transaction(self._connection, acknowledge)

    def _write_cost_statistics_read_models(
        self,
        connection: Any,
        snapshot: dict[str, Any],
        *,
        changed_scope_keys: set[str] | None,
        published_source_version: int | None = None,
    ) -> None:
        self._save_generic_read_model_snapshots(
            connection,
            _cost_statistics_metadata_snapshot(snapshot),
            table="read_model.cost_statistics_read_models",
            changed_scope_keys=changed_scope_keys,
            default_project_scope="all",
        )
        read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
        if published_source_version is not None:
            for published_scope_key, _payload in iter_mapping(read_models):
                if changed_scope_keys is not None and published_scope_key not in changed_scope_keys:
                    continue
                connection.execute(
                    """
                    update read_model.cost_statistics_read_models
                    set published_source_version = %s
                    where scope_key = %s
                    """,
                    (published_source_version, published_scope_key),
                )
        if changed_scope_keys is not None:
            present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
            for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
                connection.execute(
                    "delete from read_model.cost_statistics_bank_flow_rows where scope_key = %s",
                    (scope_key,),
                )
        for scope_key, payload in iter_mapping(read_models):
            if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                continue
            model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
            if _is_cost_statistics_parent_scope(scope_key, payload=model_payload):
                connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
                connection.execute(
                    "delete from read_model.cost_statistics_bank_flow_rows where scope_key = %s",
                    (scope_key,),
                )
                continue
            self._replace_cost_statistics_rows(connection, scope_key=scope_key, payload=payload)
            self._replace_cost_statistics_bank_flow_rows(connection, scope_key=scope_key, payload=payload)

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.tax_offset_read_models order by scope_key",
            "read_models",
        )

    def list_no_oa_bank_batch_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        return self._list_bank_batch_rows(
            filters,
            readiness_scope_type="no_oa_bank_batch",
            table_name="read_model.no_oa_bank_batch_rows",
            relation_mode_filter_enabled=True,
        )

    def list_bank_flow_rule_batch_rows(self, filters: dict[str, Any] | None = None) -> list[dict[str, Any]] | None:
        return self._list_bank_batch_rows(
            filters,
            readiness_scope_type="bank_flow_rule_batch",
            table_name="read_model.bank_flow_rule_batch_rows",
            relation_mode_filter_enabled=False,
        )

    def bank_flow_rule_batch_affected_scope_keys_for_tag_codes(self, tag_codes: list[str]) -> list[str]:
        normalized_codes = _dedupe_preserve_order(
            text(tag_code)
            for tag_code in list(tag_codes or [])
            if text(tag_code)
        )
        if not normalized_codes:
            return []
        presented_status_sql = self._bank_flow_rule_batch_presented_status_sql()
        rows = self._connection.fetch_all(
            f"""
            with affected_scopes as (
                select scope_month
                from read_model.bank_detail_rows
                where tenant_id = 'default'
                  and effective_category_code = any(%s)
                union
                select scope_month
                from read_model.bank_flow_rule_batch_rows
                where batch_type = any(%s)
                  and ({presented_status_sql}) = 'draft'
            )
            select to_char(scope_month, 'YYYY-MM') as scope_key
            from affected_scopes
            where scope_month is not null
            order by scope_key
            """,
            (normalized_codes, normalized_codes),
        )
        return [
            scope_key
            for row in rows
            for scope_key in [text(row.get("scope_key"))]
            if scope_key
        ]

    def read_bank_flow_rule_batch_page(
        self,
        filters: dict[str, Any] | None = None,
        *,
        summary_filters: dict[str, Any] | None = None,
        page: int = 1,
        page_size: int | None = 50,
    ) -> dict[str, Any] | None:
        normalized_page = max(int_value(page, 1), 1)
        normalized_page_size = None if page_size is None else min(max(int_value(page_size, 50), 1), 200)
        where_sql, params = self._bank_flow_rule_batch_filter_sql(filters)
        summary_where_sql, summary_params = self._bank_flow_rule_batch_filter_sql(summary_filters)
        presented_status_sql = self._bank_flow_rule_batch_presented_status_sql()
        visible_where_sql = f"({where_sql}) and ({presented_status_sql}) in ('draft', 'submitted', 'withdrawn')"
        visible_summary_where_sql = (
            f"({summary_where_sql}) and ({presented_status_sql}) in ('draft', 'submitted', 'withdrawn')"
        )
        total_row = self._connection.fetch_one(
            f"""
            select count(*)::bigint as total
            from read_model.bank_flow_rule_batch_rows
            where {visible_where_sql}
            """,
            tuple(params),
        ) or {}
        page_sql = f"""
            select batch_id, source_versions, payload, raw_payload
            from read_model.bank_flow_rule_batch_rows
            where {visible_where_sql}
            order by scope_month desc nulls last, generated_at desc, batch_id
            """
        page_params: tuple[Any, ...] = tuple(params)
        if normalized_page_size is not None:
            page_sql = f"{page_sql} limit %s offset %s"
            page_params = (*params, normalized_page_size, (normalized_page - 1) * normalized_page_size)
        rows = self._connection.fetch_all(page_sql, page_params)
        aggregates = self._connection.fetch_all(
            f"""
            select
              batch_type,
              {presented_status_sql} as presented_status,
              count(*)::bigint as batch_count,
              coalesce(sum(row_count), 0)::bigint as row_count,
              (array_agg(nullif(payload->>'batch_label', '') order by generated_at desc)
                filter (where nullif(payload->>'batch_label', '') is not null))[1] as batch_label,
              (array_agg(nullif(payload->>'category_primary_label', '') order by generated_at desc)
                filter (where nullif(payload->>'category_primary_label', '') is not null))[1] as category_primary_label,
              (array_agg(nullif(payload->>'category_sub_label', '') order by generated_at desc)
                filter (where nullif(payload->>'category_sub_label', '') is not null))[1] as category_sub_label,
              coalesce(sum(total_amount), 0)::text as total_amount
            from read_model.bank_flow_rule_batch_rows
            where {visible_summary_where_sql}
            group by batch_type, presented_status
            order by batch_type, presented_status
            """,
            tuple(summary_params),
        )
        normalized_items: list[dict[str, Any]] = []
        for row in rows:
            payload = _read_model_payload(row)
            if not isinstance(payload, dict):
                continue
            if isinstance(row.get("source_versions"), dict):
                payload = {**payload, "source_versions": row.get("source_versions")}
            normalized_items.append(payload)
        source_versions_summary = self.bank_flow_rule_batch_source_versions_summary(summary_filters)
        if source_versions_summary is None:
            return None
        return {
            "items": normalized_items,
            "total": int_value(total_row.get("total"), 0),
            "aggregates": [dict(row) for row in aggregates if isinstance(row, dict)],
            "source_versions_summary": source_versions_summary,
        }

    @staticmethod
    def _bank_flow_rule_batch_presented_status_sql() -> str:
        return """
        case
          when status = 'unsubmitted' and status_bucket = 'unsubmitted' then 'draft'
          when status = 'stale'
           and (
             status_bucket = 'submitted'
             or lower(coalesce(payload->>'can_withdraw', 'false')) = 'true'
           ) then 'submitted'
          else status
        end
        """.strip()

    @staticmethod
    def _bank_flow_rule_batch_filter_sql(filters: dict[str, Any] | None) -> tuple[str, list[Any]]:
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
        return " and ".join(where), params

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

    def bank_flow_rule_batch_source_versions_summary(self, filters: dict[str, Any] | None = None) -> dict[str, Any] | None:
        return self._bank_batch_source_versions_summary(
            filters,
            readiness_scope_type="bank_flow_rule_batch",
            table_name="read_model.bank_flow_rule_batch_rows",
            relation_mode_filter_enabled=False,
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
        base_clauses: list[str] = ["status <> 'withdrawn'"]
        base_params: list[Any] = []
        if normalized_scope_key != "all":
            base_clauses.append("scope_month = %s::date")
            base_params.append(month_start(normalized_scope_key))
        scoped_clauses: list[str] = ["true"]
        scoped_params: list[Any] = []
        if normalized_family != "all":
            scoped_clauses.append("family = %s")
            scoped_params.append(normalized_family)
        if normalized_status:
            scoped_clauses.append("status = %s")
            scoped_params.append(normalized_status)

        def decimal_sql(field_name: str) -> str:
            normalized = f"replace(btrim(coalesce(payload ->> '{field_name}', '')), ',', '')"
            return (
                f"case when {normalized} ~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)$' "
                f"then ({normalized})::numeric else 0::numeric end"
            )

        explicit_amount_sql = " or ".join(
            f"(payload ? '{field_name}' and payload -> '{field_name}' <> 'null'::jsonb)"
            for field_name in (
                "pending_repayment_amount",
                "repaid_amount",
                "pending_collection_amount",
                "collected_amount",
                "closed_amount",
            )
        )
        direction_sql = "true"
        if normalized_direction == "borrow_in":
            direction_sql = "business_type = 'borrow_in' or pending_repayment_input > 0 or repaid_input > 0"
        elif normalized_direction == "borrow_out":
            direction_sql = (
                "business_type in ('borrow_out', 'business_receivable') "
                "or pending_collection_input > 0 or collected_input > 0"
            )
        cte_sql = f"""
            with base as materialized (
                select relation_id, family, status, scope_month, generated_at, source_versions, payload
                from read_model.turnover_ledger_rows
                where {' and '.join(base_clauses)}
            ), scoped as (
                select * from base where {' and '.join(scoped_clauses)}
            ), amount_inputs as (
                select
                    *,
                    ({explicit_amount_sql}) as has_explicit_amounts,
                    coalesce(payload ->> 'business_type', '') as business_type,
                    {decimal_sql('pending_repayment_amount')} as pending_repayment_input,
                    {decimal_sql('repaid_amount')} as repaid_input,
                    {decimal_sql('pending_collection_amount')} as pending_collection_input,
                    {decimal_sql('collected_amount')} as collected_input,
                    {decimal_sql('closed_amount')} as closed_input,
                    {decimal_sql('principal_amount')} as principal_input,
                    {decimal_sql('settled_amount')} as settled_input,
                    {decimal_sql('balance_amount')} as balance_input
                from scoped
            ), filtered as (
                select * from amount_inputs where {direction_sql}
            ), normalized as (
                select
                    *,
                    case
                        when has_explicit_amounts then pending_repayment_input
                        when business_type = 'borrow_in' then greatest(balance_input, 0::numeric)
                        else 0::numeric
                    end as pending_repayment_amount,
                    case
                        when has_explicit_amounts then repaid_input
                        when business_type = 'borrow_in' then settled_input
                        else 0::numeric
                    end as repaid_amount,
                    case
                        when has_explicit_amounts then pending_collection_input
                        when business_type in ('borrow_out', 'business_receivable')
                            then greatest(balance_input, 0::numeric)
                        else 0::numeric
                    end as pending_collection_amount,
                    case
                        when has_explicit_amounts then collected_input
                        when business_type in ('borrow_out', 'business_receivable') then settled_input
                        else 0::numeric
                    end as collected_amount,
                    case
                        when has_explicit_amounts then closed_input
                        when balance_input = 0 and status in ('deterministic', 'confirmed') then principal_input
                        else 0::numeric
                    end as closed_amount
                from filtered
            )
        """
        query_params = tuple([*base_params, *scoped_params])
        aggregate_rows = self._connection.fetch_all(
            f"""
            {cte_sql}, scope_summary as materialized (
                select scope.row_count, scope.source_versions, scope.statistics,
                       coalesce(parent.generation, 0) as global_generation
                from read_model.turnover_ledger_scopes scope
                left join read_model.turnover_ledger_scopes parent on parent.scope_key = 'all'
                where scope.scope_key = %s
                limit 1
            ), version_proof as (
                select
                    exists (select 1 from scope_summary) as scope_exists,
                    coalesce((select global_generation from scope_summary), 0) as generation,
                    case
                        when count(*) > 0
                         and bool_and(jsonb_typeof(source_versions) = 'object')
                         and count(distinct source_versions) = 1
                            then min(source_versions::text)::jsonb
                        when count(*) = 0
                            then coalesce((select source_versions from scope_summary), '{{}}'::jsonb)
                        else '{{}}'::jsonb
                    end as source_versions,
                    coalesce(
                        bool_and(jsonb_typeof(source_versions) = 'object' and source_versions <> '{{}}'::jsonb)
                        and count(distinct source_versions) > 1,
                        false
                    ) as source_versions_mixed
                from base
            ), statistics as (
                select
                    coalesce(
                        jsonb_typeof((select statistics from scope_summary)) = 'object'
                        and (select row_count from scope_summary) = (select count(*) from base),
                        false
                    ) as statistics_ready,
                    coalesce((select (statistics->>'transaction_count')::integer
                        from scope_summary), 0) as statistics_transaction_count,
                    coalesce((select (statistics->>'expense_transaction_count')::integer
                        from scope_summary), 0) as statistics_expense_transaction_count,
                    coalesce((select (statistics->>'income_transaction_count')::integer
                        from scope_summary), 0) as statistics_income_transaction_count,
                    coalesce((select (statistics->>'ledger_group_count')::integer
                        from scope_summary), 0) as statistics_ledger_group_count,
                    coalesce((select (statistics->>'closed_group_count')::integer
                        from scope_summary), 0) as statistics_closed_group_count,
                    coalesce((select (statistics->>'linked_oa_transaction_count')::integer
                        from scope_summary), 0) as statistics_linked_oa_transaction_count,
                    coalesce((select (statistics->>'linked_invoice_transaction_count')::integer
                        from scope_summary), 0) as statistics_linked_invoice_transaction_count
            ), summary_rows as (
                select
                    grouping(family) = 1 as is_total,
                    family,
                    coalesce(sum(pending_repayment_amount), 0)::text as pending_repayment_amount,
                    coalesce(sum(repaid_amount), 0)::text as repaid_amount,
                    coalesce(sum(pending_collection_amount), 0)::text as pending_collection_amount,
                    coalesce(sum(collected_amount), 0)::text as collected_amount,
                    coalesce(sum(closed_amount), 0)::text as closed_amount,
                    count(*) filter (where status = 'suggested')::integer as suggested_count,
                    count(*) filter (where status = 'conflict')::integer as conflict_count,
                    count(*)::integer as row_count
                from normalized
                group by grouping sets ((), (family))
            )
            select summary_rows.*, version_proof.scope_exists,
                   version_proof.generation, version_proof.source_versions,
                   version_proof.source_versions_mixed,
                   statistics.*
            from summary_rows
            cross join version_proof
            cross join statistics
            order by summary_rows.is_total desc, summary_rows.family
            """,
            (*query_params, normalized_scope_key),
        )
        aggregate = next((row for row in aggregate_rows if bool(row.get("is_total"))), None)
        if not isinstance(aggregate, dict) or not bool(aggregate.get("scope_exists")):
            return None
        total = max(int_value(aggregate.get("row_count"), 0), 0)
        visible_rows: list[dict[str, Any]] = []
        if total:
            rows = self._connection.fetch_all(
                f"""
                {cte_sql}
                select payload
                from filtered
                order by scope_month desc nulls last, generated_at desc, relation_id
                limit %s offset %s
                """,
                (*query_params, normalized_page_size, (normalized_page - 1) * normalized_page_size),
            )
            visible_rows = [dict(row["payload"]) for row in rows if isinstance(row.get("payload"), dict)]
        family_rows = {
            text(row.get("family")): row
            for row in aggregate_rows
            if not bool(row.get("is_total")) and text(row.get("family"))
        }
        refresh_status = self._turnover_ledger_refresh_status(scope_key=normalized_scope_key)
        statistics_ready = bool(aggregate.get("statistics_ready"))
        if refresh_status == "fresh" and not statistics_ready:
            refresh_status = "stale"
        statistics_status = refresh_status if statistics_ready else "stale"
        payload = {
            "summary": _turnover_ledger_aggregate_summary(aggregate),
            "family_summaries": [
                _turnover_ledger_family_aggregate_summary(family_key, family_rows.get(family_key))
                for family_key in ("personal", "company", "bank", "business")
            ],
            "rows": visible_rows,
            "pagination": {
                "page": normalized_page,
                "page_size": normalized_page_size,
                "total": total,
            },
            "filters": {
                "family": normalized_family,
                "direction": normalized_direction,
                "status": normalized_status,
            },
            "read_model_status": "fresh",
            "refresh_status": refresh_status,
            "statistics": _turnover_ledger_page_statistics(aggregate) if refresh_status == "fresh" else None,
            "statistics_status": statistics_status,
            "generation": max(int_value(aggregate.get("generation"), 0), 0),
            "source_versions": aggregate.get("source_versions") if isinstance(aggregate.get("source_versions"), dict) else {},
        }
        if bool(aggregate.get("source_versions_mixed")):
            payload["source_versions_mixed"] = True
        return payload

    def _turnover_ledger_refresh_status(self, *, scope_key: str) -> str:
        if scope_key != "all":
            return self._refresh_status(scope_type="turnover_ledger", scope_key=scope_key)
        row = self._connection.fetch_one(
            """
            select
                coalesce(bool_or(status = 'failed'), false) as has_failed,
                coalesce(bool_or(status in ('pending', 'processing')), false) as has_active
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'turnover_ledger'
              and status in ('pending', 'processing', 'failed')
            """
        )
        if isinstance(row, dict) and bool(row.get("has_failed")):
            return "stale"
        if isinstance(row, dict) and bool(row.get("has_active")):
            return "refreshing"
        return "fresh"

    def load_turnover_ledger_relation_delta(
        self,
        *,
        scope_key: str,
        row_ids: list[str],
    ) -> dict[str, Any]:
        normalized_scope_key = text(scope_key)
        normalized_row_ids = text_list(row_ids)
        if not normalized_scope_key or normalized_scope_key == "all" or not normalized_row_ids:
            raise ValueError("Turnover relation delta requires one month scope and affected row ids.")
        row = self._connection.fetch_one(
            """
            with scoped as materialized (
                select bank_row_ids, source_versions, payload
                from read_model.turnover_ledger_rows
                where scope_month = %s::date
            )
            select
                count(*) > 0 as scope_exists,
                coalesce((
                    select generation
                    from read_model.turnover_ledger_scopes
                    where scope_key = 'all'
                ), 0) as generation,
                case
                    when count(*) > 0
                     and bool_and(jsonb_typeof(source_versions) = 'object')
                     and count(distinct source_versions) = 1
                        then min(source_versions::text)::jsonb
                    else '{}'::jsonb
                end as source_versions,
                coalesce(
                    bool_and(jsonb_typeof(source_versions) = 'object' and source_versions <> '{}'::jsonb)
                    and count(distinct source_versions) > 1,
                    false
                ) as source_versions_mixed,
                coalesce(
                    jsonb_agg(payload order by payload->>'relation_id')
                        filter (where bank_row_ids && %s::text[]),
                    '[]'::jsonb
                ) as rows
            from scoped
            """,
            (month_start(normalized_scope_key), normalized_row_ids),
        )
        payload = row if isinstance(row, dict) else {}
        return {
            "scope_exists": bool(payload.get("scope_exists")),
            "generation": max(int_value(payload.get("generation"), 0), 0),
            "source_versions": (
                dict(payload.get("source_versions"))
                if isinstance(payload.get("source_versions"), dict)
                else {}
            ),
            "source_versions_mixed": bool(payload.get("source_versions_mixed")),
            "rows": [dict(item) for item in list(payload.get("rows") or []) if isinstance(item, dict)],
        }

    def turnover_ledger_generation(self) -> int:
        row = self._connection.fetch_one(
            "select generation from read_model.turnover_ledger_scopes where scope_key = 'all'"
        )
        return max(int_value(row.get("generation") if isinstance(row, dict) else 0, 0), 0)

    def acknowledge_unchanged_turnover_ledger_scope(
        self,
        *,
        scope_key: str,
        source_version: Any,
        expected_generation: int,
    ) -> int:
        normalized_scope_key = text(scope_key) or "all"
        event_source_version = self._turnover_ledger_event_source_version(source_version)

        def write(connection: Any) -> int:
            generation = self._lock_turnover_ledger_generation(
                connection,
                scope_key=normalized_scope_key,
                expected_generation=expected_generation,
                event_source_version=event_source_version,
            )
            connection.execute(
                """
                update read_model.turnover_ledger_scopes
                set generation = %s,
                    published_source_version = case
                        when scope_key = %s and %s is not null then %s
                        else published_source_version
                    end,
                    updated_at = now()
                where scope_key = 'all' or scope_key = %s
                """,
                (
                    generation,
                    normalized_scope_key,
                    event_source_version,
                    event_source_version,
                    normalized_scope_key,
                ),
            )
            return generation

        return int(run_in_transaction(self._connection, write))

    def save_turnover_ledger_relation_delta(
        self,
        payload: dict[str, Any],
        *,
        scope_key: str,
    ) -> None:
        normalized_scope_key = text(scope_key)
        rows = payload.get("rows") if isinstance(payload, dict) else None
        source_versions = payload.get("source_versions") if isinstance(payload, dict) else None
        expected_generation = int_value(payload.get("expected_generation"), 0)
        event_source_version = self._turnover_ledger_event_source_version(payload.get("source_version"))
        if not normalized_scope_key or normalized_scope_key == "all" or not isinstance(rows, list):
            raise ValueError("Turnover relation delta requires one month scope and rows.")
        if not isinstance(source_versions, dict):
            raise ValueError("Turnover relation delta requires source_versions.")

        def write(connection: Any) -> None:
            generation = self._lock_turnover_ledger_generation(
                connection,
                scope_key=normalized_scope_key,
                expected_generation=expected_generation,
                event_source_version=event_source_version,
            )
            connection.execute(
                """
                update read_model.turnover_ledger_rows
                set source_versions = %s,
                    payload = jsonb_set(payload, '{source_versions}', %s, true),
                    generated_at = now(),
                    updated_at = now()
                where scope_month = %s::date
                """,
                (jsonb(source_versions), jsonb(source_versions), month_start(normalized_scope_key)),
            )
            params_seq = [
                self._turnover_ledger_row_params(item, index)
                for index, item in enumerate(rows)
                if isinstance(item, dict)
            ]
            self._upsert_turnover_ledger_rows(connection, params_seq)
            self._refresh_turnover_ledger_scope_summaries(
                connection,
                scope_keys=["all", normalized_scope_key],
                source_versions=source_versions,
                generation=generation,
                published_scope_key=normalized_scope_key,
                published_source_version=event_source_version,
            )

        run_in_transaction(self._connection, write)

    def save_turnover_ledger_rows(self, payload: dict[str, Any], *, scope_key: str | None = None) -> None:
        rows = payload.get("rows") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            return
        normalized_scope_key = text(scope_key) or text(payload.get("scope_key")) or "all"
        expected_generation = int_value(payload.get("expected_generation"), 0)
        event_source_version = self._turnover_ledger_event_source_version(payload.get("source_version"))
        source_versions = payload.get("source_versions") if isinstance(payload, dict) else None
        if not isinstance(source_versions, dict):
            source_versions = next(
                (
                    dict(row["source_versions"])
                    for row in rows
                    if isinstance(row, dict) and isinstance(row.get("source_versions"), dict)
                ),
                {},
            )

        def write(connection: Any) -> None:
            generation = self._lock_turnover_ledger_generation(
                connection,
                scope_key=normalized_scope_key,
                expected_generation=expected_generation,
                event_source_version=event_source_version,
            )
            if normalized_scope_key == "all":
                connection.execute("delete from read_model.turnover_ledger_rows", ())
            else:
                connection.execute(
                    "delete from read_model.turnover_ledger_rows where scope_month = %s::date",
                    (month_start(normalized_scope_key),),
                )
            params_seq = [
                self._turnover_ledger_row_params(item, index)
                for index, item in enumerate(rows)
                if isinstance(item, dict)
            ]
            self._upsert_turnover_ledger_rows(connection, params_seq)
            self._refresh_turnover_ledger_scope_summaries(
                connection,
                scope_keys=None if normalized_scope_key == "all" else ["all", normalized_scope_key],
                source_versions=source_versions,
                generation=generation,
                published_scope_key=normalized_scope_key,
                published_source_version=event_source_version,
            )
            if normalized_scope_key == "all":
                connection.execute(
                    """
                    delete from read_model.turnover_ledger_scopes scope
                    where scope.scope_key <> 'all'
                      and not exists (
                          select 1
                          from read_model.turnover_ledger_rows row
                          where row.scope_month = scope.scope_month
                            and row.status <> 'withdrawn'
                      )
                    """,
                    (),
                )

        run_in_transaction(self._connection, write)

    @staticmethod
    def _turnover_ledger_row_params(item: dict[str, Any], index: int) -> tuple[Any, ...]:
        row = serialize_value(item)
        relation_id = text(row.get("relation_id")) or f"turnover-row-{index}"
        return (
            relation_id,
            month_start(row.get("first_transaction_at") or row.get("borrow_date") or row.get("scope_month")),
            text(row.get("family")),
            text(row.get("status") or "suggested"),
            text(row.get("relation_type") or row.get("business_type")),
            text(row.get("source")),
            text(row.get("counterparty_name")),
            decimal_text(row.get("balance_amount") or row.get("principal_amount") or row.get("amount")),
            text_list(row.get("bank_row_ids")),
            jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
            jsonb(row),
            jsonb({}),
        )

    @staticmethod
    def _upsert_turnover_ledger_rows(connection: Any, params_seq: list[tuple[Any, ...]]) -> None:
        _execute_many(
            connection,
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
            params_seq,
        )

    @staticmethod
    def _refresh_turnover_ledger_scope_summaries(
        connection: Any,
        *,
        scope_keys: list[str] | None,
        source_versions: dict[str, Any],
        generation: int,
        published_scope_key: str,
        published_source_version: int | None,
    ) -> None:
        requested_scopes_sql = (
            """
                select 'all'::text as scope_key, null::date as scope_month
                union all
                select distinct to_char(scope_month, 'YYYY-MM'), scope_month
                from read_model.turnover_ledger_rows
                where scope_month is not null and status <> 'withdrawn'
            """
            if scope_keys is None
            else """
                select requested.scope_key,
                       case when requested.scope_key = 'all'
                            then null::date
                            else to_date(requested.scope_key || '-01', 'YYYY-MM-DD')
                       end as scope_month
                from unnest(%s::text[]) requested(scope_key)
            """
        )
        requested_scope_params: tuple[Any, ...] = (
            () if scope_keys is None else (scope_keys,)
        )
        connection.execute(
            f"""
            with requested_scopes as materialized (
                {requested_scopes_sql}
            ), scoped_rows as materialized (
                select requested.scope_key, row.payload
                from requested_scopes requested
                join read_model.turnover_ledger_rows row
                  on requested.scope_key = 'all' or row.scope_month = requested.scope_month
                where row.status <> 'withdrawn'
            ), statistics_flows as materialized (
                select
                    scoped.scope_key,
                    nullif(btrim(flow.value->>'source_bank_row_id'), '') as transaction_id,
                    flow.value->>'flow_direction' as direction,
                    coalesce(flow.value->>'linked_oa', 'false') = 'true' as linked_oa,
                    coalesce(flow.value->>'linked_invoice', 'false') = 'true' as linked_invoice
                from scoped_rows scoped
                join lateral jsonb_array_elements(
                    case
                        when jsonb_typeof(scoped.payload->'flow_rows') = 'array'
                        then scoped.payload->'flow_rows'
                        else '[]'::jsonb
                    end
                ) flow(value) on true
            ), row_statistics as (
                select
                    scope_key,
                    count(*)::integer as ledger_group_count,
                    count(*) filter (
                        where coalesce(payload->>'cash_closure_linked', 'false') = 'true'
                    )::integer as closed_group_count
                from scoped_rows
                group by scope_key
            ), flow_statistics as (
                select
                    scope_key,
                    count(distinct transaction_id) filter (where transaction_id is not null)::integer
                        as transaction_count,
                    count(distinct transaction_id) filter (
                        where transaction_id is not null and direction = 'expense'
                    )::integer as expense_transaction_count,
                    count(distinct transaction_id) filter (
                        where transaction_id is not null and direction = 'income'
                    )::integer as income_transaction_count,
                    count(distinct transaction_id) filter (
                        where transaction_id is not null and linked_oa
                    )::integer as linked_oa_transaction_count,
                    count(distinct transaction_id) filter (
                        where transaction_id is not null and linked_invoice
                    )::integer as linked_invoice_transaction_count
                from statistics_flows
                group by scope_key
            ), summaries as (
                select
                    requested.scope_key,
                    requested.scope_month,
                    coalesce(rows.ledger_group_count, 0) as row_count,
                    jsonb_build_object(
                        'transaction_count', coalesce(flows.transaction_count, 0),
                        'expense_transaction_count', coalesce(flows.expense_transaction_count, 0),
                        'income_transaction_count', coalesce(flows.income_transaction_count, 0),
                        'ledger_group_count', coalesce(rows.ledger_group_count, 0),
                        'closed_group_count', coalesce(rows.closed_group_count, 0),
                        'linked_oa_transaction_count', coalesce(flows.linked_oa_transaction_count, 0),
                        'linked_invoice_transaction_count', coalesce(flows.linked_invoice_transaction_count, 0)
                    ) as statistics
                from requested_scopes requested
                left join row_statistics rows on rows.scope_key = requested.scope_key
                left join flow_statistics flows on flows.scope_key = requested.scope_key
            )
            insert into read_model.turnover_ledger_scopes(
                scope_key, scope_month, row_count, source_versions, statistics,
                generation, published_source_version, generated_at, cache_status
            )
            select scope_key, scope_month, row_count, %s, statistics, %s,
                   case when scope_key = %s then %s else null end,
                   now(), 'fresh'
            from summaries
            on conflict (scope_key) do update set
                scope_month = excluded.scope_month,
                row_count = excluded.row_count,
                source_versions = excluded.source_versions,
                statistics = excluded.statistics,
                generation = excluded.generation,
                published_source_version = coalesce(
                    excluded.published_source_version,
                    turnover_ledger_scopes.published_source_version
                ),
                generated_at = excluded.generated_at,
                cache_status = excluded.cache_status,
                updated_at = now()
            """,
            (
                *requested_scope_params,
                jsonb(source_versions),
                generation,
                published_scope_key,
                published_source_version,
            ),
        )

    @staticmethod
    def _turnover_ledger_event_source_version(value: Any) -> int | None:
        if value in (None, ""):
            return None
        try:
            normalized = int(value)
        except (TypeError, ValueError) as exc:
            raise ValueError("Turnover ledger source_version must be a non-negative integer.") from exc
        if normalized < 0:
            raise ValueError("Turnover ledger source_version must be a non-negative integer.")
        return normalized

    @staticmethod
    def _lock_turnover_ledger_generation(
        connection: Any,
        *,
        scope_key: str,
        expected_generation: int,
        event_source_version: int | None,
    ) -> int:
        connection.execute(
            "select pg_advisory_xact_lock(hashtext(%s))",
            ("turnover_ledger_projection",),
        )
        row = connection.fetch_one(
            """
            select
                coalesce((
                    select generation from read_model.turnover_ledger_scopes where scope_key = 'all'
                ), 0) as generation,
                (
                    select published_source_version
                    from read_model.turnover_ledger_scopes
                    where scope_key = %s
                ) as published_source_version
            """,
            (scope_key,),
        )
        current_generation = max(int_value(row.get("generation") if isinstance(row, dict) else 0, 0), 0)
        published_source_version = (
            int_value(row.get("published_source_version"), -1) if isinstance(row, dict) else -1
        )
        if current_generation != max(int_value(expected_generation, 0), 0):
            raise TurnoverLedgerGenerationConflictError(
                f"Turnover ledger generation advanced from {expected_generation} to {current_generation}."
            )
        if event_source_version is not None and published_source_version > event_source_version:
            raise TurnoverLedgerGenerationConflictError(
                "Turnover ledger event source_version is older than the published scope version."
            )
        return current_generation + 1

    def tax_offset_statistics_generation_token(self) -> str | None:
        row = self._connection.fetch_one(
            """
            with scope_material as (
                select coalesce(string_agg(
                    scope_key || ':' || generated_at::text || ':' || source_versions::text || ':'
                    || coalesce((coalesce(payload->'payload', payload)->'statistics')::text, ''),
                    ',' order by scope_key
                ), '') as value
                from read_model.tax_offset_read_models
                where scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            ), dirty_material as (
                select coalesce(string_agg(scope_key || ':' || status || ':' || source_version::text, ',' order by scope_key), '') as value
                from job.read_model_dirty_scopes
                where tenant_id = 'default'
                  and scope_type = 'tax_offset'
                  and status in ('pending', 'processing', 'failed')
            ), outbox_material as (
                select coalesce(string_agg(coalesce(scope_key, '') || ':' || status, ',' order by scope_key), '') as value
                from job.outbox_events
                where tenant_id = 'default'
                  and event_type = 'tax_offset.read_model.refresh'
                  and status in ('pending', 'processing', 'failed', 'dead_lettered')
            )
            select md5(scope_material.value || '|dirty:' || dirty_material.value || '|outbox:' || outbox_material.value) as token
            from scope_material
            cross join dirty_material
            cross join outbox_material
            """
        )
        return text(row.get("token")) if isinstance(row, dict) else None

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
        statistics_row = self._connection.fetch_one(
            """
            /* check: tax_offset_page_statistics */
            with scopes as (
                select
                    scope_key,
                    generated_at,
                    schema_version,
                    cache_status,
                    source_versions,
                    coalesce(payload->'payload', payload) as page_payload
                from read_model.tax_offset_read_models
                where scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            ), scope_counts as (
                select
                    coalesce(sum((page_payload->'statistics'->>'input_invoice_count')::integer), 0)::integer as input_invoice_count,
                    coalesce(sum((page_payload->'statistics'->>'output_invoice_count')::integer), 0)::integer as output_invoice_count,
                    coalesce(sum((page_payload->'statistics'->>'certification_record_count')::integer), 0)::integer as certification_record_count,
                    coalesce(sum((page_payload->'statistics'->>'matched_certification_count')::integer), 0)::integer as matched_certification_count,
                    coalesce(sum((page_payload->'statistics'->>'out_of_scope_certification_count')::integer), 0)::integer as out_of_scope_certification_count,
                    coalesce(sum((page_payload->'statistics'->>'selected_invoice_count')::integer), 0)::integer as selected_invoice_count,
                    bool_and(
                        schema_version = %s
                        and cache_status in ('fresh', 'ready')
                        and source_versions = %s::jsonb
                        and jsonb_typeof(page_payload->'statistics') = 'object'
                    ) as scopes_fresh,
                    md5(coalesce(string_agg(
                        scope_key || ':' || generated_at::text || ':' || source_versions::text || ':'
                        || coalesce((page_payload->'statistics')::text, ''),
                        ',' order by scope_key
                    ), '')) as statistics_generation_token
                from scopes
            )
            select scope_counts.*,
                   not exists (
                       select 1
                       from job.read_model_dirty_scopes dirty
                       where dirty.tenant_id = 'default'
                         and dirty.scope_type = 'tax_offset'
                         and dirty.status in ('pending', 'processing', 'failed')
                   ) and not exists (
                       select 1
                       from job.outbox_events outbox
                       where outbox.tenant_id = 'default'
                         and outbox.event_type = 'tax_offset.read_model.refresh'
                         and outbox.status in ('pending', 'processing', 'failed', 'dead_lettered')
                   ) and coalesce(scope_counts.scopes_fresh, false) as statistics_fresh
            from scope_counts
            """,
            (
                text(row.get("schema_version") or stored_payload.get("schema_version") or payload.get("schema_version")),
                jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
            ),
        )
        statistics: dict[str, int] | None = None
        if isinstance(statistics_row, dict) and bool(statistics_row.get("statistics_fresh")):
            input_count = int_value(statistics_row.get("input_invoice_count"), 0)
            output_count = int_value(statistics_row.get("output_invoice_count"), 0)
            certification_count = int_value(statistics_row.get("certification_record_count"), 0)
            matched_count = int_value(statistics_row.get("matched_certification_count"), 0)
            selected_count = int_value(statistics_row.get("selected_invoice_count"), 0)
            invoice_count = input_count + output_count
            statistics = {
                "input_invoice_count": input_count,
                "output_invoice_count": output_count,
                "certification_record_count": certification_count,
                "matched_certification_count": matched_count,
                "unmatched_certification_count": max(certification_count - matched_count, 0),
                "out_of_scope_certification_count": int_value(
                    statistics_row.get("out_of_scope_certification_count"), 0
                ),
                "deductible_invoice_count": input_count,
                "selected_invoice_count": selected_count,
                "unselected_invoice_count": max(invoice_count - selected_count, 0),
            }
        payload = dict(payload)
        payload["statistics"] = statistics
        payload["statistics_status"] = (
            "fresh"
            if statistics is not None
            else "refreshing"
            if isinstance(statistics_row, dict) and not bool(statistics_row.get("statistics_fresh"))
            else "stale"
        )
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
            "statistics_generation_token": (
                text(statistics_row.get("statistics_generation_token"))
                if isinstance(statistics_row, dict)
                else None
            ),
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
                model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                row_count = self._read_model_row_count(model_payload)
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
                if isinstance(model_payload, dict) and any(key in model_payload for key in _TAX_OFFSET_ITEM_TYPES):
                    self._replace_tax_offset_items(connection, scope_key=scope_key, payload=payload)

        run_in_transaction(self._connection, write)

    def _replace_cost_statistics_rows(self, connection: Any, *, scope_key: str, payload: dict[str, Any]) -> None:
        connection.execute("delete from read_model.cost_statistics_rows where scope_key = %s", (scope_key,))
        self._insert_cost_statistics_rows(connection, scope_key=scope_key, payload=payload)

    def _insert_cost_statistics_rows(self, connection: Any, *, scope_key: str, payload: dict[str, Any]) -> None:
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
                    decimal_text(str(row.get("amount") or "").replace(",", "")) or "0",
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

    def _replace_cost_statistics_bank_flow_rows(
        self,
        connection: Any,
        *,
        scope_key: str,
        payload: dict[str, Any],
    ) -> None:
        connection.execute(
            "delete from read_model.cost_statistics_bank_flow_rows where scope_key = %s",
            (scope_key,),
        )
        model_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
        bank_flow_rows = model_payload.get("bank_flow_time_rows") if isinstance(model_payload, dict) else None
        if not isinstance(bank_flow_rows, list):
            return
        source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
        project_scope, scope_month_text = _parse_cost_statistics_scope_parts(scope_key, payload=model_payload)
        if scope_month_text == "all":
            raise ValueError("cost_statistics_bank_flow_rows only supports concrete month scopes.")
        scope_month = month_start(model_payload.get("scope_month") or model_payload.get("month") or scope_month_text)
        if scope_month is None:
            raise ValueError("cost_statistics_bank_flow_rows requires a concrete scope_month.")
        generated_at = text(payload.get("generated_at") or model_payload.get("generated_at"))
        cache_status = text(payload.get("cache_status") or model_payload.get("cache_status") or "fresh") or "fresh"
        row_params: list[tuple[Any, ...]] = []
        for index, item in enumerate(bank_flow_rows):
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
                    text(row.get("project_name")) or "未配对OA",
                    text(row.get("expense_type")) or "未分类",
                    text(row.get("expense_content")),
                    decimal_text(str(row.get("amount") or "").replace(",", "")) or "0",
                    text(row.get("oa_applicant")),
                    text(row.get("bank_tag_code")),
                    text(row.get("bank_tag_label")),
                    text(row.get("bank_tag_primary_label")),
                    text(row.get("bank_tag_sub_label")),
                    jsonb(row.get("bank_tag_label_path") if isinstance(row.get("bank_tag_label_path"), list) else []),
                    jsonb(source_versions),
                    generated_at,
                    cache_status,
                    jsonb(row),
                    jsonb({"normalized_payload": row}),
                )
            )
        _execute_many(
            connection,
            """
            insert into read_model.cost_statistics_bank_flow_rows(
                scope_key, project_scope, scope_month, row_key, transaction_id, group_id,
                trade_time_text, trade_date, counterparty_name, payment_account_label, direction,
                remark, project_id, project_name, expense_type, expense_content, amount,
                oa_applicant, bank_tag_code, bank_tag_label, bank_tag_primary_label,
                bank_tag_sub_label, bank_tag_label_path, source_versions, generated_at,
                cache_status, payload, raw_payload
            )
            values (
                %s, %s, %s::date, %s, %s, %s, %s, %s::date, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()),
                %s, %s, %s
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
                bank_tag_code = excluded.bank_tag_code,
                bank_tag_label = excluded.bank_tag_label,
                bank_tag_primary_label = excluded.bank_tag_primary_label,
                bank_tag_sub_label = excluded.bank_tag_sub_label,
                bank_tag_label_path = excluded.bank_tag_label_path,
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
                        decimal_text(str(row.get("tax_amount") or "").replace(",", "")),
                        decimal_text(str(row.get("total_with_tax") or row.get("amount") or "").replace(",", "")),
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



class PostgresReadModelRepository:
    def __init__(self, connection: Any) -> None:
        self._connection = connection
        self._workbench_generation_consistency_cache: dict[tuple[str, str], list[dict[str, Any]]] = {}
        self._summary_read_model_repository = PostgresSummaryReadModelRepository(connection)
        self._search_workbench_relation_repository = PostgresSearchWorkbenchRelationReadModelRepository(connection)
        self._bank_read_model_repository = PostgresBankReadModelRepository(connection)
        self._invoice_usage_collection_repository = PostgresInvoiceUsageCollectionReadModelRepository(connection)
        self._pending_invoice_lifecycle_repository = PostgresPendingInvoiceLifecycleReadModelRepository(
            connection,
            bank_detail_scope_summary=self.bank_detail_scope_summary,
            workbench_relation_source_summary_from_source=self.workbench_relation_source_summary_from_source,
        )

    def get_cost_statistics_scope_metadata(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_cost_statistics_scope_metadata(*args, **kwargs)

    def cost_statistics_aggregate_payload(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._summary_read_model_repository.cost_statistics_aggregate_payload(*args, **kwargs)

    def get_cost_statistics_freshness_gate(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_cost_statistics_freshness_gate(*args, **kwargs)

    def get_cost_statistics_page(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_cost_statistics_page(*args, **kwargs)

    def get_cost_statistics_export_page(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_cost_statistics_export_page(*args, **kwargs)

    def get_cost_statistics_transaction(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_cost_statistics_transaction(*args, **kwargs)

    def active_workbench_source_versions(self, *, scope_key: str) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip()
        if not normalized_scope_key:
            return {}
        return self._active_workbench_generation_source_versions(
            self._connection,
            scope_key=normalized_scope_key,
        )

    def publish_cost_statistics_read_models(self, *args: Any, **kwargs: Any) -> bool:
        return self._summary_read_model_repository.publish_cost_statistics_read_models(*args, **kwargs)

    def publish_cost_statistics_relation_delta(self, *args: Any, **kwargs: Any) -> bool:
        return self._summary_read_model_repository.publish_cost_statistics_relation_delta(*args, **kwargs)

    def acknowledge_unchanged_cost_statistics_scope(self, *args: Any, **kwargs: Any) -> bool:
        return self._summary_read_model_repository.acknowledge_unchanged_cost_statistics_scope(*args, **kwargs)

    def load_tax_offset_read_models(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._summary_read_model_repository.load_tax_offset_read_models(*args, **kwargs)

    def get_tax_offset_view(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.get_tax_offset_view(*args, **kwargs)

    def save_tax_offset_read_models(self, *args: Any, **kwargs: Any) -> None:
        self._summary_read_model_repository.save_tax_offset_read_models(*args, **kwargs)

    def list_no_oa_bank_batch_rows(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]] | None:
        return self._summary_read_model_repository.list_no_oa_bank_batch_rows(*args, **kwargs)

    def no_oa_bank_batch_source_versions_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.no_oa_bank_batch_source_versions_summary(*args, **kwargs)

    def list_bank_flow_rule_batch_rows(self, *args: Any, **kwargs: Any) -> list[dict[str, Any]] | None:
        return self._summary_read_model_repository.list_bank_flow_rule_batch_rows(*args, **kwargs)

    def bank_flow_rule_batch_affected_scope_keys_for_tag_codes(self, *args: Any, **kwargs: Any) -> list[str]:
        return self._summary_read_model_repository.bank_flow_rule_batch_affected_scope_keys_for_tag_codes(
            *args,
            **kwargs,
        )

    def read_bank_flow_rule_batch_page(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.read_bank_flow_rule_batch_page(*args, **kwargs)

    def bank_flow_rule_batch_source_versions_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.bank_flow_rule_batch_source_versions_summary(*args, **kwargs)

    def list_turnover_ledger_view(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._summary_read_model_repository.list_turnover_ledger_view(*args, **kwargs)

    def save_turnover_ledger_rows(self, *args: Any, **kwargs: Any) -> None:
        self._summary_read_model_repository.save_turnover_ledger_rows(*args, **kwargs)

    def turnover_ledger_generation(self, *args: Any, **kwargs: Any) -> int:
        return self._summary_read_model_repository.turnover_ledger_generation(*args, **kwargs)

    def acknowledge_unchanged_turnover_ledger_scope(self, *args: Any, **kwargs: Any) -> int:
        return self._summary_read_model_repository.acknowledge_unchanged_turnover_ledger_scope(*args, **kwargs)

    def load_turnover_ledger_relation_delta(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._summary_read_model_repository.load_turnover_ledger_relation_delta(*args, **kwargs)

    def save_turnover_ledger_relation_delta(self, *args: Any, **kwargs: Any) -> None:
        self._summary_read_model_repository.save_turnover_ledger_relation_delta(*args, **kwargs)

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

    def get_batch_accounting_relation_rows_by_ids(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.get_batch_accounting_relation_rows_by_ids(*args, **kwargs)

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

    def workbench_relation_delta_source_versions(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._search_workbench_relation_repository.workbench_relation_delta_source_versions(*args, **kwargs)

    def list_batch_accounting_relation_groups_by_year(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._search_workbench_relation_repository.list_batch_accounting_relation_groups_by_year(*args, **kwargs)

    def bank_detail_scope_keys_for_range(self, *args: Any, **kwargs: Any) -> list[str]:
        return self._bank_read_model_repository.bank_detail_scope_keys_for_range(*args, **kwargs)

    def _bank_detail_scope_keys_for_range(self, *args: Any, **kwargs: Any) -> list[str]:
        return self._bank_read_model_repository._bank_detail_scope_keys_for_range(*args, **kwargs)

    def _bank_detail_available_month_scope_keys(self, *args: Any, **kwargs: Any) -> list[str]:
        return self._bank_read_model_repository._bank_detail_available_month_scope_keys(*args, **kwargs)

    def bank_detail_scope_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._bank_read_model_repository.bank_detail_scope_summary(*args, **kwargs)

    def bank_detail_category_source_signatures(self, *args: Any, **kwargs: Any) -> dict[str, str]:
        return self._bank_read_model_repository.bank_detail_category_source_signatures(*args, **kwargs)

    def bank_account_balance_scope_summary(self, *args: Any, **kwargs: Any) -> dict[str, Any]:
        return self._bank_read_model_repository.bank_account_balance_scope_summary(*args, **kwargs)

    def list_bank_detail_transactions(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.list_bank_detail_transactions(*args, **kwargs)

    def list_bank_detail_accounts(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.list_bank_detail_accounts(*args, **kwargs)

    def get_bank_detail_tagged_rows_by_transaction_ids(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.get_bank_detail_tagged_rows_by_transaction_ids(*args, **kwargs)

    def get_bank_detail_tagged_snapshot(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.get_bank_detail_tagged_snapshot(*args, **kwargs)

    def list_bank_detail_tagged_rows_by_month(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.list_bank_detail_tagged_rows_by_month(*args, **kwargs)

    def list_bank_account_balances(self, *args: Any, **kwargs: Any) -> dict[str, Any] | None:
        return self._bank_read_model_repository.list_bank_account_balances(*args, **kwargs)

    def save_bank_account_balances(self, *args: Any, **kwargs: Any) -> None:
        self._bank_read_model_repository.save_bank_account_balances(*args, **kwargs)

    def save_bank_detail_rows(self, *args: Any, **kwargs: Any) -> None:
        self._bank_read_model_repository.save_bank_detail_rows(*args, **kwargs)

    def mark_bank_detail_scope(self, *args: Any, **kwargs: Any) -> None:
        self._bank_read_model_repository.mark_bank_detail_scope(*args, **kwargs)

    def list_input_invoice_usage_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_input_invoice_usage_rows(**kwargs)

    def list_input_invoice_usage_filter_options(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_input_invoice_usage_filter_options(**kwargs)

    def input_invoice_usage_scope_source_versions(self, **kwargs: Any) -> dict[str, Any]:
        return self._invoice_usage_collection_repository.input_invoice_usage_scope_source_versions(**kwargs)

    def save_input_invoice_usage_rows(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.save_input_invoice_usage_rows(**kwargs)

    def mark_input_invoice_usage_scope(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.mark_input_invoice_usage_scope(**kwargs)

    def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._invoice_usage_collection_repository.prune_input_invoice_usage_scope_shards(current_scope_keys)

    def get_input_invoice_usage_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_input_invoice_usage_row_by_row_id(row_id)

    def list_input_invoice_usage_rows_by_invoice_ids(self, invoice_ids: list[str]) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_input_invoice_usage_rows_by_invoice_ids(invoice_ids)

    def list_output_invoice_collection_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_output_invoice_collection_rows(**kwargs)

    def output_invoice_collection_scope_source_versions(self, **kwargs: Any) -> dict[str, Any]:
        return self._invoice_usage_collection_repository.output_invoice_collection_scope_source_versions(**kwargs)

    def get_output_invoice_collection_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_output_invoice_collection_row_by_row_id(row_id)

    def save_output_invoice_collection_rows(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.save_output_invoice_collection_rows(**kwargs)

    def mark_output_invoice_collection_scope(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.mark_output_invoice_collection_scope(**kwargs)

    def prune_output_invoice_collection_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._invoice_usage_collection_repository.prune_output_invoice_collection_scope_shards(current_scope_keys)

    def list_oa_pending_payment_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_oa_pending_payment_rows(**kwargs)

    def list_oa_pending_payment_lifecycle_source_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.list_oa_pending_payment_lifecycle_source_rows(**kwargs)

    def oa_pending_payment_read_snapshot(self):
        return self._invoice_usage_collection_repository.oa_pending_payment_read_snapshot()

    def oa_pending_payment_query_state(self, **kwargs: Any) -> dict[str, Any]:
        return self._invoice_usage_collection_repository.oa_pending_payment_query_state(**kwargs)

    def save_oa_pending_payment_rows(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.save_oa_pending_payment_rows(**kwargs)

    def publish_oa_pending_payment_rows(self, **kwargs: Any) -> bool:
        return self._invoice_usage_collection_repository.publish_oa_pending_payment_rows(**kwargs)

    def mark_oa_pending_payment_scope(self, **kwargs: Any) -> None:
        self._invoice_usage_collection_repository.mark_oa_pending_payment_scope(**kwargs)

    def prune_oa_pending_payment_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._invoice_usage_collection_repository.prune_oa_pending_payment_scope_shards(current_scope_keys)

    def get_oa_pending_payment_row_by_row_id(self, row_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_oa_pending_payment_row_by_row_id(row_id)

    def get_oa_pending_payment_row_by_oa_id(self, oa_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_oa_pending_payment_row_by_oa_id(oa_id)

    def get_oa_pending_payment_row_by_bank_transaction_id(self, bank_transaction_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_oa_pending_payment_row_by_bank_transaction_id(bank_transaction_id)

    def get_oa_pending_payment_row_by_invoice_id(self, invoice_id: str) -> dict[str, Any] | None:
        return self._invoice_usage_collection_repository.get_oa_pending_payment_row_by_invoice_id(invoice_id)


    def list_pending_invoice_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.list_pending_invoice_rows(**kwargs)

    def list_pending_invoice_lifecycle_source_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.list_pending_invoice_lifecycle_source_rows(**kwargs)

    def list_pending_invoice_filter_options(self, **kwargs: Any) -> dict[str, Any]:
        return self._pending_invoice_lifecycle_repository.list_pending_invoice_filter_options(**kwargs)

    def save_pending_invoice_rows(self, **kwargs: Any) -> None:
        self._pending_invoice_lifecycle_repository.save_pending_invoice_rows(**kwargs)

    def mark_pending_invoice_scope(self, **kwargs: Any) -> None:
        self._pending_invoice_lifecycle_repository.mark_pending_invoice_scope(**kwargs)

    def pending_invoice_source_summary(self, **kwargs: Any) -> dict[str, int]:
        return self._pending_invoice_lifecycle_repository.pending_invoice_source_summary(**kwargs)

    def pending_invoice_bank_detail_source_versions(self, **kwargs: Any) -> dict[str, Any]:
        return self._pending_invoice_lifecycle_repository.pending_invoice_bank_detail_source_versions(**kwargs)

    def pending_invoice_workbench_relation_source_versions(self, **kwargs: Any) -> dict[str, Any]:
        return self._pending_invoice_lifecycle_repository.pending_invoice_workbench_relation_source_versions(**kwargs)

    def _pending_invoice_scope_row(self, scope_key: str, *, connection: Any | None = None) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository._pending_invoice_scope_row(scope_key, connection=connection)

    def _pending_invoice_source_summary(self, **kwargs: Any) -> dict[str, int]:
        return self._pending_invoice_lifecycle_repository._pending_invoice_source_summary(**kwargs)

    def save_invoice_lifecycle_rows(self, **kwargs: Any) -> None:
        self._pending_invoice_lifecycle_repository.save_invoice_lifecycle_rows(**kwargs)

    def mark_invoice_lifecycle_scope(self, **kwargs: Any) -> None:
        self._pending_invoice_lifecycle_repository.mark_invoice_lifecycle_scope(**kwargs)

    def get_invoice_lifecycle_rows_by_subject_ids(self, subject_ids: list[str], **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.get_invoice_lifecycle_rows_by_subject_ids(subject_ids, **kwargs)

    def get_invoice_lifecycle_rows_by_identity_keys(self, invoice_identity_keys: list[str], **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.get_invoice_lifecycle_rows_by_identity_keys(invoice_identity_keys, **kwargs)

    def list_invoice_lifecycle_rows(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.list_invoice_lifecycle_rows(**kwargs)

    def invoice_lifecycle_scope_summary(self, **kwargs: Any) -> dict[str, Any] | None:
        return self._pending_invoice_lifecycle_repository.invoice_lifecycle_scope_summary(**kwargs)











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
                else:
                    statistics = self._workbench_published_all_page_statistics()
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

    def _publish_workbench_all_generation_stats(self, connection: Any) -> None:
        active_month_version = self._workbench_active_month_generation_version(connection)
        generation_id = text(active_month_version.get("version"))
        if not generation_id:
            raise RuntimeError("Workbench all-scope generation stats require active month generations.")
        transaction_repository = PostgresReadModelRepository(connection)
        summary = transaction_repository._get_workbench_all_canonical_summary_counts()
        self._upsert_workbench_generation_stats(
            connection,
            generation_id=generation_id,
            scope_key="all",
            summary_payload={"summary": summary},
        )
        connection.execute(
            """
            delete from read_model.workbench_generation_stats
            where scope_key = 'all'
              and generation_id <> %s
            """,
            (generation_id,),
        )

    def _workbench_published_all_page_statistics(self) -> dict[str, int] | None:
        if self._workbench_summary_read_model_status(scope_key="all") != "fresh":
            return None
        active_version = self._workbench_active_month_generation_version(self._connection)
        generation_id = text(active_version.get("version"))
        if not generation_id:
            return None
        rows = self._connection.fetch_all(
            """
            select zone, payload
            from read_model.workbench_generation_stats
            where generation_id = %s
              and scope_key = 'all'
              and zone in ('paired', 'unpaired')
              and status_bucket = 'all'
            order by zone
            """,
            (generation_id,),
        )
        if len(rows) != 2:
            return None
        page_statistics: list[dict[str, int]] = []
        for row in rows:
            payload = row.get("payload") if isinstance(row, dict) else None
            statistics = payload.get("page_statistics") if isinstance(payload, dict) else None
            if not isinstance(statistics, dict):
                return None
            page_statistics.append(
                {str(key): int_value(value, 0) for key, value in statistics.items()}
            )
        if page_statistics[0] != page_statistics[1]:
            return None
        return page_statistics[0]

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

    def list_workbench_search_rows(self, *, scope_key: str) -> list[dict[str, Any]]:
        normalized_scope_key = str(scope_key or "").strip()
        if not MONTH_SCOPE_RE.match(normalized_scope_key):
            raise ValueError("Workbench search rows require a month scope key YYYY-MM.")
        rows = self._connection.fetch_all(
            """
            with active_generation as (
                select generation_id, scope_key
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and scope_key = %s
                  and status = 'active'
                limit 1
            ), active_rows as (
                select rows.*
                from read_model.workbench_rows rows
                join active_generation generation
                  on generation.generation_id = rows.generation_id
                 and generation.scope_key = rows.scope_key
            ), ranked_memberships as (
                select
                    members.row_id,
                    members.zone,
                    members.group_id,
                    members.row_role,
                    members.row_index,
                    groups.updated_at as group_updated_at,
                    row_number() over (
                        partition by members.row_id
                        order by
                            case when members.zone = 'paired' then 0 else 1 end,
                            groups.updated_at desc nulls last,
                            members.group_id,
                            members.row_role,
                            members.row_index
                    ) as membership_rank
                from read_model.workbench_group_rows members
                join active_generation generation
                  on generation.generation_id = members.generation_id
                 and generation.scope_key = members.scope_key
                left join read_model.workbench_groups groups
                  on groups.generation_id = members.generation_id
                 and groups.scope_key = members.scope_key
                 and groups.zone = members.zone
                 and groups.group_id = members.group_id
            ), group_project_names as (
                select
                    members.zone,
                    members.group_id,
                    array_agg(
                        distinct coalesce(
                            nullif(btrim(oa_rows.project_name), ''),
                            nullif(btrim(oa_rows.payload->>'project_name'), '')
                        )
                    ) filter (
                        where coalesce(
                            nullif(btrim(oa_rows.project_name), ''),
                            nullif(btrim(oa_rows.payload->>'project_name'), '')
                        ) is not null
                    ) as project_names
                from read_model.workbench_group_rows members
                join active_generation generation
                  on generation.generation_id = members.generation_id
                 and generation.scope_key = members.scope_key
                join active_rows oa_rows
                  on oa_rows.row_id = members.row_id
                 and members.pane = 'oa'
                group by members.zone, members.group_id
            )
            select
                rows.row_id,
                rows.source_kind,
                rows.status,
                rows.payload,
                rows.raw_payload,
                membership.zone as group_zone,
                membership.group_id,
                membership.group_updated_at,
                membership.row_role,
                membership.row_index,
                projects.project_names
            from active_rows rows
            left join ranked_memberships membership
              on membership.row_id = rows.row_id
             and membership.membership_rank = 1
            left join group_project_names projects
              on projects.zone = membership.zone
             and projects.group_id = membership.group_id
            order by
                case
                    when rows.status = 'ignored' then 2
                    when membership.zone = 'paired' then 0
                    else 1
                end,
                membership.group_updated_at desc nulls last,
                membership.group_id,
                membership.row_role,
                membership.row_index,
                rows.row_id
            """,
            (normalized_scope_key,),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = _read_model_payload(row)
            if not isinstance(payload, dict):
                continue
            row_type = text(payload.get("type")) or text(row.get("source_kind"))
            if row_type not in WORKBENCH_PANES:
                continue
            payload["id"] = text(payload.get("id")) or text(row.get("row_id")) or ""
            payload["type"] = row_type
            status = text(row.get("status"))
            if status == "ignored" or bool(payload.get("ignored")):
                zone_hint = "ignored"
            elif status == "processed_exception" or bool(payload.get("handled_exception")):
                zone_hint = "processed_exception"
            else:
                zone_hint = text(row.get("group_zone")) or status or "unpaired"
            result.append(
                {
                    "row": payload,
                    "zone_hint": zone_hint,
                    "group_id": text(row.get("group_id")) or "",
                    "project_names": sorted(text_list(row.get("project_names"))),
                }
            )
        return result

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
        generation_stats_eligible = bool(active_generation_id) and not any(
            (
                text(status),
                text(source_kind),
                normalized_search,
                normalized_column_filters,
                normalized_time_filters,
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
        if composed_all_scope and generation_stats_eligible and materialized_counts is None:
            return None
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
                                  'no_oa_bank_batch_summary',
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
                                  'no_oa_bank_batch_summary',
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
        scope_clause = "" if normalized_scope_key == "all" else "and scope_key = %s"
        params = () if normalized_scope_key == "all" else (normalized_scope_key,)
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
        schema_status = self._workbench_groups_schema_status(scope_key=normalized_scope_key)
        read_model_status = "fresh"
        stale_reasons: list[str] = []
        if not active_generation_id:
            read_model_status = "unavailable"
            stale_reasons.append("active_generation_missing")
        elif pending_scopes:
            read_model_status = "refreshing"
        elif failed_scopes:
            read_model_status = "stale"
            stale_reasons.append("refresh_failed")
        elif schema_status != "fresh":
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
        published_scope_keys: set[str] = set()

        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                if set(changed_scope_keys) - present_scope_keys:
                    raise ValueError("changed_scope_keys must reference payloads written in this call.")
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                self._lock_workbench_generation_scope(connection, scope_key=scope_key)
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
            if published_scope_keys:
                self._publish_workbench_all_generation_stats(connection)
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

    def load_batch_accounting_workbench_payload(self, *, bank_year: str) -> dict[str, Any] | None:
        return self._load_batch_accounting_workbench_payload(
            bank_year=bank_year,
            include_oa=True,
            include_invoices=True,
        )

    def load_batch_accounting_submitted_bank_workbench_payload(self, *, bank_year: str) -> dict[str, Any] | None:
        return self._load_batch_accounting_workbench_payload(
            bank_year=bank_year,
            include_oa=False,
            include_invoices=False,
        )

    def load_batch_accounting_submit_workbench_payload(
        self,
        *,
        bank_year: str,
        bank_row_id: str,
        oa_row_ids: list[str],
    ) -> dict[str, Any] | None:
        resolved_bank_year = text(bank_year)
        normalized_bank_row_id = text(bank_row_id)
        normalized_oa_row_ids = _dedupe_preserve_order(text(row_id) for row_id in list(oa_row_ids or []))
        if not resolved_bank_year or not normalized_bank_row_id or not normalized_oa_row_ids:
            return None
        bank_start = f"{resolved_bank_year}-01-01"
        bank_rows = self._connection.fetch_all(
            """
            with active_rows as (
                select distinct on (r.row_id)
                    r.row_id, r.source_kind, r.status, r.payload, r.raw_payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.row_id = %s
                  and r.source_kind = 'bank'
                  and r.scope_month >= %s::date
                  and r.scope_month < (%s::date + interval '1 year')
                order by r.row_id, r.updated_at desc nulls last
            )
            select row_id, source_kind, status, payload, raw_payload
            from active_rows
            order by updated_at desc nulls last, row_id
            """,
            (normalized_bank_row_id, bank_start, bank_start),
        )
        oa_rows = self._connection.fetch_all(
            """
            with active_rows as (
                select distinct on (r.row_id)
                    r.row_id, r.source_kind, r.status, r.payload, r.raw_payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.row_id = any(%s)
                  and r.source_kind = 'oa'
                order by r.row_id,
                  case when r.scope_key = 'all' then 1 else 0 end,
                  r.updated_at desc nulls last
            )
            select row_id, source_kind, status, payload, raw_payload
            from active_rows
            order by array_position(%s::text[], row_id), updated_at desc nulls last
            """,
            (normalized_oa_row_ids, normalized_oa_row_ids),
        )
        invoice_rows = self._load_batch_accounting_invoice_rows(
            oa_row_ids=normalized_oa_row_ids,
            allow_all_scope=True,
        )
        return self._batch_accounting_payload_from_rows(
            bank_year=resolved_bank_year,
            bank_rows=bank_rows,
            oa_rows=oa_rows,
            invoice_rows=invoice_rows,
        )

    def _load_batch_accounting_workbench_payload(
        self,
        *,
        bank_year: str,
        include_oa: bool,
        include_invoices: bool,
    ) -> dict[str, Any] | None:
        resolved_bank_year = text(bank_year)
        if not resolved_bank_year:
            return None
        bank_start = f"{resolved_bank_year}-01-01"
        candidate_rows = self._connection.fetch_all(
            f"""
            with active_bank_rows as (
                select distinct on (r.row_id)
                    1 as batch_row_order,
                    'bank'::text as batch_row_kind,
                    coalesce(
                        r.payload->>'trade_time',
                        r.payload->>'pay_receive_time',
                        r.payload->>'txn_date',
                        ''
                    ) as batch_sort_value,
                    r.row_id, r.source_kind, r.status, r.payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.scope_key <> 'all'
                  and r.source_kind = 'bank'
                  and r.counterparty_name = %s
                  and (
                        r.scope_month >= %s::date
                        and r.scope_month < (%s::date + interval '1 year')
                      )
                order by r.row_id, r.updated_at desc nulls last
            ),
            active_oa_rows as (
                select distinct on (r.row_id)
                    2 as batch_row_order,
                    'oa'::text as batch_row_kind,
                    coalesce(
                        r.payload->>'apply_time',
                        r.payload->>'application_time',
                        r.payload->>'application_date',
                        r.payload->>'created_at',
                        ''
                    ) as batch_sort_value,
                    r.row_id, r.source_kind, r.status, r.payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.scope_key <> 'all'
                  and r.source_kind = 'oa'
                  and %s::boolean
                  and (
                        coalesce(r.payload->>'apply_type', '')
                        || ' '
                        || coalesce(r.payload->>'expense_type', '')
                      ) like %s
                order by r.row_id, r.updated_at desc nulls last
            ),
            oa_candidate_ids as materialized (
                select coalesce(nullif(payload->>'id', ''), row_id) as oa_row_id
                from active_oa_rows
            ),
            active_invoice_rows as (
                select distinct on (r.row_id)
                    3 as batch_row_order,
                    'invoice'::text as batch_row_kind,
                    r.row_id as batch_sort_value,
                    r.row_id, r.source_kind, r.status, r.payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.source_kind = 'oa_attachment_invoice'
                  and r.scope_key <> 'all'
                  and %s::boolean
                  and (
                    {_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL}
                  )
                order by r.row_id, r.updated_at desc nulls last
            ),
            candidate_rows as (
                select * from active_bank_rows
                union all
                select * from active_oa_rows
                union all
                select * from active_invoice_rows
            )
            select batch_row_kind, row_id, source_kind, status, payload
            from candidate_rows
            order by
                batch_row_order,
                case when batch_row_order in (1, 2) then batch_sort_value end desc,
                case when batch_row_order = 3 then row_id end,
                row_id
            """,
            (
                "批量账务集中处理",
                bank_start,
                bank_start,
                include_oa,
                "%日常报销%",
                include_invoices,
            ),
        )
        bank_rows = [row for row in candidate_rows if text(row.get("batch_row_kind")) == "bank"]
        oa_rows = [row for row in candidate_rows if text(row.get("batch_row_kind")) == "oa"]
        invoice_rows = [row for row in candidate_rows if text(row.get("batch_row_kind")) == "invoice"]
        return self._batch_accounting_payload_from_rows(
            bank_year=resolved_bank_year,
            bank_rows=bank_rows,
            oa_rows=oa_rows,
            invoice_rows=invoice_rows,
        )

    def _load_batch_accounting_invoice_rows(
        self,
        *,
        oa_row_ids: list[str],
        allow_all_scope: bool,
    ) -> list[dict[str, Any]]:
        normalized_oa_row_ids = _dedupe_preserve_order(text(row_id) for row_id in list(oa_row_ids or []))
        if not normalized_oa_row_ids:
            return []
        return self._connection.fetch_all(
            f"""
            with oa_candidate_ids as materialized (
                select unnest(%s::text[]) as oa_row_id
            ),
            active_rows as (
                select distinct on (r.row_id)
                    r.row_id, r.source_kind, r.status, r.payload, r.raw_payload,
                    r.updated_at
                from read_model.workbench_rows r
                join read_model.workbench_generations gen
                  on gen.generation_id = r.generation_id
                 and gen.scope_key = r.scope_key
                 and gen.status = 'active'
                where r.source_kind = 'oa_attachment_invoice'
                  and (%s or r.scope_key <> 'all')
                  and (
                    {_BATCH_ACCOUNTING_INVOICE_CANDIDATE_MATCH_SQL}
                  )
                order by r.row_id,
                  case when r.scope_key = 'all' then 1 else 0 end,
                  r.updated_at desc nulls last
            )
            select row_id, source_kind, status, payload, raw_payload
            from active_rows
            order by row_id
            """,
            (normalized_oa_row_ids, allow_all_scope),
        )

    def _batch_accounting_payload_from_rows(
        self,
        *,
        bank_year: str,
        bank_rows: list[dict[str, Any]],
        oa_rows: list[dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        return {
            "month": "all",
            "summary": {},
            "paired": {"groups": []},
            "unpaired": {
                "groups": [
                    {
                        "group_id": f"batch-accounting:{bank_year}:unpaired-oa",
                        "group_type": "batch_accounting_sql_read_model",
                        "bank_rows": self._batch_accounting_payload_rows(bank_rows),
                        "oa_rows": self._batch_accounting_payload_rows(oa_rows),
                        "invoice_rows": self._batch_accounting_payload_rows(invoice_rows),
                    }
                ]
            },
        }

    @staticmethod
    def _batch_accounting_payload_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
        payload_rows: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "payload")
            if isinstance(payload, dict):
                payload_rows.append(
                    {key: value for key, value in payload.items() if str(key) != "rebuildable"}
                    if "rebuildable" in payload
                    else payload
                )
                continue
            row_id = text(row.get("row_id"))
            if row_id:
                payload_rows.append({"id": row_id, "type": text(row.get("source_kind")) or "unknown"})
        return payload_rows

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


def _pending_invoice_filter_groups_for_direction(direction: str) -> tuple[str, ...]:
    if str(direction or "").strip() == "income":
        return ("all", "requires_invoice", "no_invoice_required", "cash_income")
    return ("all", "requires_invoice", "bank_statement_as_invoice", "no_invoice_required")


def _pending_invoice_filter_group_counts_for_rows(rows: list[dict[str, Any]], *, direction: str) -> dict[str, int]:
    normalized_direction = text(direction) or "expense"
    filter_counts = {filter_group: 0 for filter_group in _pending_invoice_filter_groups_for_direction(normalized_direction)}
    for row in rows:
        row_payload = dict(row) if isinstance(row, dict) else {}
        payload = row_payload.get("payload") if isinstance(row_payload.get("payload"), dict) else row_payload
        status = payload.get("invoice_acquisition_status") if isinstance(payload.get("invoice_acquisition_status"), dict) else {}
        status_code = text(row_payload.get("status_code") or status.get("code"))
        counted = False
        if status_code:
            for filter_group in filter_counts:
                if filter_group == "all":
                    continue
                if status_code in pending_invoice_filter_status_codes(
                    direction=normalized_direction,
                    filter_name=filter_group,
                ):
                    filter_counts[filter_group] += 1
                    counted = True
                    break
        if not counted and not status_code:
            row_filter_group = text(row_payload.get("filter_group") or payload.get("filter_group")) or "all"
            if row_filter_group in filter_counts:
                filter_counts[row_filter_group] += 1
    return filter_counts


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


def _invoice_relation_option_label_expression(field: str, expression: str) -> str:
    if field == "payment_status":
        return "payment_status_label"
    if field == "receipt_status":
        return "receipt_status_label"
    if field == "collection_status":
        return "collection_status_label"
    return expression


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
        with base_rows as (
            select *
            from {table_name}
            where {where_sql}
        ),
        invoice_count_ids as (
            select nullif(btrim(coalesce(
                invoice_summary.value->>'invoiceId',
                invoice_summary.value->>'id',
                invoice_summary.value->>'primaryInvoiceId',
                payload->'invoice'->>'id',
                invoice_id
            )), '') as invoice_id
            from base_rows
            left join lateral jsonb_array_elements(
                case
                    when jsonb_typeof(payload->'invoiceRelations'->'summaries') = 'array'
                    then coalesce(
                        nullif(payload->'invoiceRelations'->'summaries', '[]'::jsonb),
                        jsonb_build_array(jsonb_build_object('invoiceId', coalesce(payload->'invoice'->>'id', invoice_id)))
                    )
                    else jsonb_build_array(jsonb_build_object('invoiceId', coalesce(payload->'invoice'->>'id', invoice_id)))
                end
            ) as invoice_summary(value) on true
        )
        select
            count(*) as count,
            (select count(distinct invoice_id) from invoice_count_ids) as invoice_count,
            coalesce(sum(total_with_tax), 0) as total_with_tax,
            coalesce(sum(case when oa_relation_count > 0 then 1 else 0 end), 0) as matched_oa_count,
            coalesce(sum(case when bank_relation_count > 0 then 1 else 0 end), 0) as matched_bank_transaction_count,
            coalesce(sum(case when payment_status = 'pending' then 1 else 0 end), 0) as pending_count
        from base_rows
        """
    return f"""
    with base_rows as (
        select *
        from {table_name}
        where {where_sql}
    ),
    invoice_count_ids as (
        select nullif(btrim(coalesce(
            invoice_summary.value->>'invoiceId',
            invoice_summary.value->>'id',
            invoice_summary.value->>'primaryInvoiceId',
            invoice_summary.value->>'relatedInvoiceId',
            payload->'invoice'->>'id',
            invoice_id
        )), '') as invoice_id
        from base_rows
        left join lateral jsonb_array_elements(
            case
                when jsonb_typeof(payload->'invoiceRelations'->'summaries') = 'array'
                then coalesce(
                    nullif(payload->'invoiceRelations'->'summaries', '[]'::jsonb),
                    jsonb_build_array(jsonb_build_object('invoiceId', coalesce(payload->'invoice'->>'id', invoice_id)))
                )
                else jsonb_build_array(jsonb_build_object('invoiceId', coalesce(payload->'invoice'->>'id', invoice_id)))
            end
        ) as invoice_summary(value) on true
    )
    select
        count(*) as count,
        (select count(distinct invoice_id) from invoice_count_ids) as invoice_count,
        coalesce(sum(total_with_tax), 0) as total_with_tax,
        coalesce(sum(collected_amount), 0) as collected_amount,
        coalesce(sum(pending_amount), 0) as pending_amount,
        coalesce(sum(case when collection_status = 'pending_collection' then 1 else 0 end), 0) as pending_collection_count,
        coalesce(sum(case when collection_status = 'partial_collected' then 1 else 0 end), 0) as partial_collection_count,
        coalesce(sum(case when receipt_status = 'pending' then 1 else 0 end), 0) as receipt_pending_count
    from base_rows
    """


def _invoice_relation_summary_payload(row: dict[str, Any], *, summary_kind: str, total: int) -> dict[str, Any]:
    if summary_kind == "input":
        return {
            "invoiceCount": int_value(row.get("invoice_count"), total),
            "totalWithTax": decimal_text(row.get("total_with_tax")) or "0.00",
            "matchedOaCount": int_value(row.get("matched_oa_count"), 0),
            "matchedBankTransactionCount": int_value(row.get("matched_bank_transaction_count"), 0),
            "pendingCount": int_value(row.get("pending_count"), 0),
        }
    return {
        "invoiceCount": int_value(row.get("invoice_count"), total),
        "totalWithTax": decimal_text(row.get("total_with_tax")) or "0.00",
        "collectedAmount": decimal_text(row.get("collected_amount")) or "0.00",
        "pendingAmount": decimal_text(row.get("pending_amount")) or "0.00",
        "pendingCollectionCount": int_value(row.get("pending_collection_count"), 0),
        "partialCollectionCount": int_value(row.get("partial_collection_count"), 0),
        "receiptPendingCount": int_value(row.get("receipt_pending_count"), 0),
    }


def _invoice_relation_statistics_from_scope_metadata(
    values: Any,
    *,
    summary_kind: str,
) -> dict[str, int] | None:
    metadata_rows = list(values) if isinstance(values, list) else []
    if not metadata_rows:
        return None
    keys = (
        (
            "invoice_count",
            "linked_oa_invoice_count",
            "linked_bank_invoice_count",
            "paid_invoice_count",
            "unlinked_oa_invoice_count",
            "unlinked_bank_invoice_count",
            "unpaid_invoice_count",
            "formal_relation_group_count",
        )
        if summary_kind == "input"
        else (
            "invoice_count",
            "linked_oa_invoice_count",
            "linked_income_bank_invoice_count",
            "collected_invoice_count",
            "unlinked_oa_invoice_count",
            "unlinked_bank_invoice_count",
            "uncollected_invoice_count",
            "red_invoice_count",
            "issued_receipt_count",
        )
    )
    totals = {key: 0 for key in keys}
    for metadata in metadata_rows:
        if not isinstance(metadata, dict) or not isinstance(metadata.get("statistics"), dict):
            return None
        statistics = metadata["statistics"]
        if any(
            isinstance(statistics.get(key), bool)
            or not isinstance(statistics.get(key), int)
            or int(statistics[key]) < 0
            for key in keys
        ):
            return None
        for key in keys:
            value = int(statistics[key])
            totals[key] += value
    invoice_count = totals["invoice_count"]
    linked_oa_count = totals["linked_oa_invoice_count"]
    if totals["unlinked_oa_invoice_count"] != invoice_count - linked_oa_count:
        return None
    if summary_kind == "input":
        if (
            totals["unlinked_bank_invoice_count"]
            != invoice_count - totals["linked_bank_invoice_count"]
            or totals["unpaid_invoice_count"] != invoice_count - totals["paid_invoice_count"]
        ):
            return None
        totals["oa_reverse_batch_count"] = 0
    elif (
        totals["unlinked_bank_invoice_count"]
        != invoice_count - totals["linked_income_bank_invoice_count"]
        or totals["uncollected_invoice_count"] != invoice_count - totals["collected_invoice_count"]
    ):
        return None
    return totals


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
    oa = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
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
            "oa_applicant": text(oa.get("applicantName")),
            "oa_application_type": text(oa.get("applicationType")),
            "oa_project_name": text(oa.get("projectName")),
            "bank_counterparty_name": text(bank.get("counterpartyName")),
            "bank_trade_time": text(bank.get("tradeTime")),
            "bank_amount": decimal_text(bank.get("amount")),
            "bank_name": text(bank.get("bankName")),
            "bank_summary": text(bank.get("summary")),
            "receipt_status": text(receipt.get("status")),
            "receipt_status_label": text(receipt.get("label")),
            "oa_relation_count": int_value(oa.get("relationCount"), 0),
            "bank_relation_count": int_value(bank.get("relationCount"), 0),
            "red_invoice_relation_count": int_value(red_invoice.get("relationCount"), 0),
        }
    )
    return record


def _oa_pending_payment_read_model_record(row: dict[str, Any], scope_key: str) -> dict[str, Any]:
    payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
    oa = payload.get("oa") if isinstance(payload.get("oa"), dict) else {}
    oa_ids = _dedupe_preserve_order(
        [
            text(summary.get("oaId") or summary.get("id"))
            for summary in list(oa.get("summaries") or [])
            if isinstance(summary, dict)
        ]
        + [text(oa.get("id"))]
    )
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
        "oa_ids": oa_ids,
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


def _cost_statistics_aggregate_payload(
    connection: Any,
    *,
    project_scope: str,
    scope_keys: list[str],
    bank_accounts: list[dict[str, Any]],
) -> dict[str, Any]:
    normalized_scope_keys = sorted({value for item in scope_keys if (value := text(item))})
    if normalized_scope_keys:
        cost_row = connection.fetch_one(
            """
            with base as materialized (
                select transaction_id, group_id, project_name, expense_type, amount
                from read_model.cost_statistics_rows
                where project_scope = %s
                  and scope_key = any(%s::text[])
                  and scope_month is not null
            ), projects as (
                select project_name, sum(amount) as total_amount,
                       count(distinct transaction_id)::integer as transaction_count,
                       count(distinct expense_type)::integer as expense_type_count
                from base
                group by project_name
            ), expenses as (
                select expense_type, sum(amount) as total_amount,
                       count(distinct transaction_id)::integer as transaction_count,
                       count(distinct project_name)::integer as project_count
                from base
                group by expense_type
            )
            select
                (select count(*)::integer from base) as row_count,
                (select count(distinct transaction_id)::integer from base) as transaction_count,
                (select count(distinct group_id)::integer from base
                    where nullif(btrim(group_id), '') is not null) as group_count,
                (select count(distinct project_name)::integer from base
                    where nullif(btrim(project_name), '') is not null) as project_count,
                (select count(distinct expense_type)::integer from base
                    where nullif(btrim(expense_type), '') is not null) as expense_type_count,
                (select coalesce(sum(amount), 0)::text from base) as total_amount,
                coalesce(
                    (
                        select jsonb_agg(
                            jsonb_build_object(
                                'project_name', project_name,
                                'total_amount', total_amount::text,
                                'transaction_count', transaction_count,
                                'expense_type_count', expense_type_count
                            ) order by total_amount desc, project_name
                        )
                        from projects
                    ),
                    '[]'::jsonb
                ) as project_rows,
                coalesce(
                    (
                        select jsonb_agg(
                            jsonb_build_object(
                                'expense_type', expense_type,
                                'total_amount', total_amount::text,
                                'transaction_count', transaction_count,
                                'project_count', project_count
                            ) order by total_amount desc, expense_type
                        )
                        from expenses
                    ),
                    '[]'::jsonb
                ) as expense_type_rows
            """,
            (project_scope, normalized_scope_keys),
        ) or {}
        bank_row = connection.fetch_one(
            """
            select
                count(*)::integer as row_count,
                count(distinct transaction_id)::integer as transaction_count,
                coalesce(sum(abs(amount)), 0)::text as total_amount,
                coalesce(sum(abs(amount)) filter (where direction = '支出'), 0)::text as expense_amount,
                coalesce(sum(abs(amount)) filter (where direction = '收入'), 0)::text as income_amount,
                count(distinct transaction_id) filter (where direction = '支出')::integer
                    as expense_transaction_count,
                count(distinct transaction_id) filter (where direction = '收入')::integer
                    as income_transaction_count,
                count(distinct transaction_id) filter (
                    where nullif(btrim(bank_tag_code), '') is not null
                )::integer as tagged_transaction_count,
                count(distinct bank_tag_code) filter (
                    where nullif(btrim(bank_tag_code), '') is not null
                )::integer as bank_tag_count
            from read_model.cost_statistics_bank_flow_rows
            where project_scope = %s
              and scope_key = any(%s::text[])
              and scope_month is not null
            """,
            (project_scope, normalized_scope_keys),
        ) or {}
    else:
        cost_row = {}
        bank_row = {}

    project_rows = [dict(row) for row in list(cost_row.get("project_rows") or []) if isinstance(row, dict)]
    expense_type_rows = [dict(row) for row in list(cost_row.get("expense_type_rows") or []) if isinstance(row, dict)]
    for row in [*project_rows, *expense_type_rows]:
        row["total_amount"] = _format_decimal(_decimal_or_zero(row.get("total_amount")))
    cost_count = int_value(cost_row.get("row_count"), 0)
    cost_transaction_count = int_value(cost_row.get("transaction_count"), 0)
    bank_count = int_value(bank_row.get("row_count"), 0)
    bank_transaction_count = int_value(bank_row.get("transaction_count"), 0)
    tagged_transaction_count = int_value(bank_row.get("tagged_transaction_count"), 0)
    return {
        "month": "all" if len(normalized_scope_keys) != 1 else normalized_scope_keys[0].split(":", 1)[-1],
        "project_scope": project_scope,
        "summary": {
            "row_count": cost_count,
            "transaction_count": cost_transaction_count,
            "total_amount": _format_decimal(_decimal_or_zero(cost_row.get("total_amount"))),
        },
        "bank_flow_summary": {
            "row_count": bank_count,
            "transaction_count": bank_transaction_count,
            "total_amount": _format_decimal(_decimal_or_zero(bank_row.get("total_amount"))),
            "expense_amount": _format_decimal(_decimal_or_zero(bank_row.get("expense_amount"))),
            "income_amount": _format_decimal(_decimal_or_zero(bank_row.get("income_amount"))),
            "expense_transaction_count": int_value(bank_row.get("expense_transaction_count"), 0),
            "income_transaction_count": int_value(bank_row.get("income_transaction_count"), 0),
        },
        "statistics": {
            "transaction_count": bank_transaction_count,
            "expense_transaction_count": int_value(bank_row.get("expense_transaction_count"), 0),
            "income_transaction_count": int_value(bank_row.get("income_transaction_count"), 0),
            "cost_group_count": int_value(cost_row.get("group_count"), 0),
            "tagged_transaction_count": tagged_transaction_count,
            "untagged_transaction_count": max(bank_transaction_count - tagged_transaction_count, 0),
            "project_count": int_value(cost_row.get("project_count"), 0),
            "expense_type_count": int_value(cost_row.get("expense_type_count"), 0),
            "bank_tag_count": int_value(bank_row.get("bank_tag_count"), 0),
            "cost_transaction_count": cost_transaction_count,
        },
        "bank_accounts": [dict(row) for row in bank_accounts if isinstance(row, dict)],
        "project_rows": project_rows,
        "expense_type_rows": expense_type_rows,
    }


def _cost_statistics_page_statistics(value: Any) -> dict[str, int] | None:
    if not isinstance(value, dict):
        return None
    expected_keys = (
        "transaction_count",
        "expense_transaction_count",
        "income_transaction_count",
        "cost_group_count",
        "tagged_transaction_count",
        "untagged_transaction_count",
        "project_count",
        "expense_type_count",
        "bank_tag_count",
        "cost_transaction_count",
    )
    if any(
        isinstance(value.get(key), bool)
        or not isinstance(value.get(key), int)
        or value.get(key, -1) < 0
        for key in expected_keys
    ):
        return None
    statistics = {key: int(value[key]) for key in expected_keys}
    if (
        statistics["transaction_count"]
        != statistics["expense_transaction_count"] + statistics["income_transaction_count"]
        or statistics["transaction_count"]
        != statistics["tagged_transaction_count"] + statistics["untagged_transaction_count"]
    ):
        return None
    return statistics


def _cost_statistics_percentage_sql() -> str:
    return """
        case
            when coalesce(sum(sum(amount)) over (), 0) = 0 then '0.0%%'
            else round(sum(amount) * 100 / sum(sum(amount)) over (), 1)::text || '%%'
        end
    """


def _cost_statistics_project_facets_sql(where_sql: str = "true") -> str:
    return f"""(
        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'project_name', facet.project_name,
                    'total_amount', facet.total_amount::text,
                    'transaction_count', facet.transaction_count,
                    'expense_type_count', facet.expense_type_count,
                    'percentage_label', facet.percentage_label
                ) order by facet.total_amount desc, facet.project_name
            ),
            '[]'::jsonb
        )
        from (
            select
                project_name,
                sum(amount) as total_amount,
                count(distinct transaction_id) as transaction_count,
                count(distinct expense_type) as expense_type_count,
                {_cost_statistics_percentage_sql()} as percentage_label
            from base
            where {where_sql}
            group by project_name
        ) facet
    )"""


def _cost_statistics_expense_facets_sql(where_sql: str = "true") -> str:
    return f"""(
        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'expense_type', facet.expense_type,
                    'total_amount', facet.total_amount::text,
                    'transaction_count', facet.transaction_count,
                    'project_count', facet.project_count,
                    'percentage_label', facet.percentage_label
                ) order by facet.total_amount desc, facet.expense_type
            ),
            '[]'::jsonb
        )
        from (
            select
                expense_type,
                sum(amount) as total_amount,
                count(distinct transaction_id) as transaction_count,
                count(distinct project_name) as project_count,
                {_cost_statistics_percentage_sql()} as percentage_label
            from base
            where {where_sql}
            group by expense_type
        ) facet
    )"""


def _cost_statistics_bank_facets_sql() -> str:
    return f"""(
        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'payment_account_label', facet.payment_account_label,
                    'total_amount', facet.total_amount::text,
                    'transaction_count', facet.transaction_count,
                    'project_count', facet.project_count,
                    'percentage_label', facet.percentage_label
                ) order by facet.total_amount desc, facet.payment_account_label
            ),
            '[]'::jsonb
        )
        from (
            select
                coalesce(nullif(payment_account_label, ''), '未识别账户') as payment_account_label,
                sum(amount) as total_amount,
                count(distinct transaction_id) as transaction_count,
                count(distinct project_name) as project_count,
                {_cost_statistics_percentage_sql()} as percentage_label
            from base
            group by coalesce(nullif(payment_account_label, ''), '未识别账户')
        ) facet
    )"""


def _cost_statistics_bank_tag_primary_facets_sql() -> str:
    return """(
        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'primary_label', facet.primary_label,
                    'expense_amount', facet.expense_amount::text,
                    'income_amount', facet.income_amount::text,
                    'expense_transaction_count', facet.expense_transaction_count,
                    'income_transaction_count', facet.income_transaction_count,
                    'sub_tag_count', facet.sub_tag_count
                ) order by (facet.expense_amount + facet.income_amount) desc, facet.primary_label
            ),
            '[]'::jsonb
        )
        from (
            select
                tag_primary_label as primary_label,
                coalesce(sum(amount) filter (where direction = '支出'), 0) as expense_amount,
                coalesce(sum(amount) filter (where direction = '收入'), 0) as income_amount,
                count(distinct transaction_id) filter (where direction = '支出') as expense_transaction_count,
                count(distinct transaction_id) filter (where direction = '收入') as income_transaction_count,
                count(distinct tag_sub_label) as sub_tag_count
            from base
            group by tag_primary_label
        ) facet
    )"""


def _cost_statistics_bank_tag_sub_facets_sql() -> str:
    return """(
        select coalesce(
            jsonb_agg(
                jsonb_build_object(
                    'primary_label', facet.primary_label,
                    'sub_label', facet.sub_label,
                    'expense_amount', facet.expense_amount::text,
                    'income_amount', facet.income_amount::text,
                    'expense_transaction_count', facet.expense_transaction_count,
                    'income_transaction_count', facet.income_transaction_count
                ) order by (facet.expense_amount + facet.income_amount) desc, facet.sub_label
            ),
            '[]'::jsonb
        )
        from (
            select
                tag_primary_label as primary_label,
                tag_sub_label as sub_label,
                coalesce(sum(amount) filter (where direction = '支出'), 0) as expense_amount,
                coalesce(sum(amount) filter (where direction = '收入'), 0) as income_amount,
                count(distinct transaction_id) filter (where direction = '支出') as expense_transaction_count,
                count(distinct transaction_id) filter (where direction = '收入') as income_transaction_count
            from base
            where tag_primary_label = %s
            group by tag_primary_label, tag_sub_label
        ) facet
    )"""


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


def _cost_statistics_metadata_snapshot(snapshot: dict[str, Any]) -> dict[str, Any]:
    storage_snapshot = deepcopy(snapshot if isinstance(snapshot, dict) else {})
    read_models = storage_snapshot.get("read_models")
    if not isinstance(read_models, dict):
        return storage_snapshot
    for read_model in read_models.values():
        if not isinstance(read_model, dict):
            continue
        model_payload = read_model.get("payload")
        if isinstance(model_payload, dict):
            model_payload.pop("time_rows", None)
            model_payload.pop("bank_flow_time_rows", None)
    return storage_snapshot


def _cost_statistics_row_payload(db_row: dict[str, Any], *, fallback_index: int) -> dict[str, Any]:
    payload = _read_model_payload(db_row)
    row_payload_value = deepcopy(payload) if isinstance(payload, dict) else {}
    transaction_id = text(db_row.get("transaction_id") or row_payload_value.get("transaction_id")) or f"row-{fallback_index}"
    amount = _decimal_or_zero(db_row.get("amount") or row_payload_value.get("amount"))
    label_path = db_row.get("bank_tag_label_path")
    if not isinstance(label_path, list):
        label_path = row_payload_value.get("bank_tag_label_path")
    cost_allocations = db_row.get("cost_allocations")
    return {
        **row_payload_value,
        "transaction_id": transaction_id,
        "group_id": text(db_row.get("group_id") or row_payload_value.get("group_id")),
        "month": text(db_row.get("scope_month") or row_payload_value.get("month")),
        "trade_time": text(
            db_row.get("trade_time_text")
            or row_payload_value.get("trade_time")
            or db_row.get("trade_date")
        ),
        "direction": text(db_row.get("direction") or row_payload_value.get("direction")),
        "project_name": text(db_row.get("project_name") or row_payload_value.get("project_name")) or "未归集项目",
        "project_id": text(db_row.get("project_id") or row_payload_value.get("project_id")),
        "expense_type": text(db_row.get("expense_type") or row_payload_value.get("expense_type")) or "未分类",
        "expense_content": text(db_row.get("expense_content") or row_payload_value.get("expense_content")),
        "amount": _format_decimal(amount),
        "counterparty_name": text(db_row.get("counterparty_name") or row_payload_value.get("counterparty_name")),
        "payment_account_label": text(
            db_row.get("payment_account_label") or row_payload_value.get("payment_account_label")
        ),
        "remark": text(db_row.get("remark") or row_payload_value.get("remark")),
        "oa_applicant": text(db_row.get("oa_applicant") or row_payload_value.get("oa_applicant")),
        "bank_tag_code": text(db_row.get("bank_tag_code") or row_payload_value.get("bank_tag_code")),
        "bank_tag_label": text(db_row.get("bank_tag_label") or row_payload_value.get("bank_tag_label")),
        "bank_tag_primary_label": text(
            db_row.get("bank_tag_primary_label") or row_payload_value.get("bank_tag_primary_label")
        ),
        "bank_tag_sub_label": text(
            db_row.get("bank_tag_sub_label") or row_payload_value.get("bank_tag_sub_label")
        ),
        "bank_tag_label_path": deepcopy(label_path) if isinstance(label_path, list) else [],
        "cost_allocations": [
            deepcopy(item)
            for item in list(cost_allocations or [])
            if isinstance(item, dict)
        ],
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


def _turnover_ledger_aggregate_summary(row: dict[str, Any] | None) -> dict[str, Any]:
    aggregate = row if isinstance(row, dict) else {}
    return {
        "pending_repayment_amount": _format_decimal(_decimal_or_zero(aggregate.get("pending_repayment_amount"))),
        "repaid_amount": _format_decimal(_decimal_or_zero(aggregate.get("repaid_amount"))),
        "pending_collection_amount": _format_decimal(_decimal_or_zero(aggregate.get("pending_collection_amount"))),
        "collected_amount": _format_decimal(_decimal_or_zero(aggregate.get("collected_amount"))),
        "closed_amount": _format_decimal(_decimal_or_zero(aggregate.get("closed_amount"))),
        "suggested_count": max(int_value(aggregate.get("suggested_count"), 0), 0),
        "conflict_count": max(int_value(aggregate.get("conflict_count"), 0), 0),
        "row_count": max(int_value(aggregate.get("row_count"), 0), 0),
    }


def _turnover_ledger_page_statistics(row: dict[str, Any]) -> dict[str, int]:
    group_count = max(int_value(row.get("statistics_ledger_group_count"), 0), 0)
    closed_group_count = max(int_value(row.get("statistics_closed_group_count"), 0), 0)
    return {
        "transaction_count": max(int_value(row.get("statistics_transaction_count"), 0), 0),
        "expense_transaction_count": max(
            int_value(row.get("statistics_expense_transaction_count"), 0),
            0,
        ),
        "income_transaction_count": max(
            int_value(row.get("statistics_income_transaction_count"), 0),
            0,
        ),
        "ledger_group_count": group_count,
        "closed_group_count": closed_group_count,
        "unclosed_group_count": max(group_count - closed_group_count, 0),
        "linked_oa_transaction_count": max(
            int_value(row.get("statistics_linked_oa_transaction_count"), 0),
            0,
        ),
        "linked_invoice_transaction_count": max(
            int_value(row.get("statistics_linked_invoice_transaction_count"), 0),
            0,
        ),
    }


def _turnover_ledger_family_aggregate_summary(family: str, row: dict[str, Any] | None) -> dict[str, Any]:
    summary = _turnover_ledger_aggregate_summary(row)
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
    return {"oa": oa_count, "bank": bank_count, "invoice": invoice_count, "rows": oa_count + bank_count + invoice_count}


def _sum_workbench_group_fact_row_counts(groups: list[dict[str, Any]]) -> dict[str, int]:
    result = _empty_workbench_row_counts()
    for group in groups:
        counts = _workbench_group_fact_row_counts(group)
        for key in ("oa", "bank", "invoice", "rows"):
            result[key] += counts[key]
    return result


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


def _sanitize_workbench_row_for_read_model(row: dict[str, Any]) -> dict[str, Any]:
    payload = dict(row)
    payload.pop("workbench_reconciliation_decision", None)
    return payload


def _workbench_group_payload_for_rows(group: dict[str, Any], *, payload: dict[str, Any] | None = None) -> dict[str, Any]:
    source_payload = payload if isinstance(payload, dict) else group.get("payload")
    payload = dict(source_payload if isinstance(source_payload, dict) else group)
    payload.setdefault("group_id", text(group.get("group_id") or group.get("id")))
    payload.setdefault("zone", text(group.get("zone") or group.get("status")) or "unpaired")
    payload.setdefault("status", text(group.get("status") or group.get("zone")) or "unpaired")
    payload.setdefault("scope_month", group.get("scope_month"))
    payload.setdefault("month", group.get("month"))
    return payload


WORKBENCH_GROUP_MEMBER_PAYLOAD_KEYS = {
    "rows",
    "oa_rows",
    "bank_rows",
    "invoice_rows",
    "collapsed_rows",
}


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


def _pending_invoice_scope_source_versions_row(
    scope_key: str,
    rows: list[dict[str, Any]],
    *,
    include_empty: bool = False,
) -> dict[str, Any] | None:
    normalized_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return None
    child_rows = [
        row
        for row in normalized_rows
        if text(row.get("scope_key")).startswith(f"{scope_key}:")
    ]
    if child_rows:
        normalized_rows = child_rows
    if len(normalized_rows) == 1:
        row = normalized_rows[0]
        return {
            "scope_key": text(row.get("scope_key")) or scope_key,
            "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
        }
    effective_rows = normalized_rows if include_empty else [
        row for row in normalized_rows if int_value(row.get("row_count"), 0) > 0
    ] or normalized_rows
    first_versions = (
        effective_rows[0].get("source_versions")
        if isinstance(effective_rows[0].get("source_versions"), dict)
        else {}
    )
    aggregate = dict(first_versions)
    bank_detail_by_month: dict[str, Any] = {}
    workbench_relation_by_month: dict[str, Any] = {}
    for row in effective_rows:
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


def _pending_invoice_statistics_from_scope_metadata(values: Any) -> dict[str, int] | None:
    metadata_rows = list(values) if isinstance(values, list) else []
    if not metadata_rows:
        return None
    keys = (
        "bank_transaction_count",
        "expense_transaction_count",
        "income_transaction_count",
        "found_invoice_transaction_count",
        "pending_invoice_transaction_count",
        "no_invoice_required_transaction_count",
        "cash_income_transaction_count",
        "linked_oa_transaction_count",
        "linked_input_invoice_transaction_count",
        "linked_output_invoice_transaction_count",
    )
    totals = {key: 0 for key in keys}
    for metadata in metadata_rows:
        if not isinstance(metadata, dict) or not isinstance(metadata.get("statistics"), dict):
            return None
        statistics = metadata["statistics"]
        if any(
            isinstance(statistics.get(key), bool)
            or not isinstance(statistics.get(key), int)
            or int(statistics[key]) < 0
            for key in keys
        ):
            return None
        for key in keys:
            totals[key] += int(statistics[key])
    if (
        totals["bank_transaction_count"]
        != totals["expense_transaction_count"] + totals["income_transaction_count"]
        or totals["found_invoice_transaction_count"]
        != totals["linked_input_invoice_transaction_count"]
        + totals["linked_output_invoice_transaction_count"]
    ):
        return None
    return totals


def _merge_pending_invoice_direction_scope_rows(scope_key: str, rows: list[dict[str, Any]]) -> dict[str, Any] | None:
    normalized_rows = [row for row in list(rows or []) if isinstance(row, dict)]
    if not normalized_rows:
        return None
    if len(normalized_rows) == 1:
        row = normalized_rows[0]
        return {
            "scope_key": text(row.get("scope_key")) or scope_key,
            "source_versions": row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {},
        }
    effective_rows = [
        row
        for row in normalized_rows
        if int_value(row.get("row_count"), 0) > 0
    ] or normalized_rows
    first_versions = (
        effective_rows[0].get("source_versions")
        if isinstance(effective_rows[0].get("source_versions"), dict)
        else {}
    )
    aggregate = dict(first_versions)
    for dependency_key in ("bank_detail_source_versions", "workbench_relation_source_versions"):
        dependency_versions_by_direction: dict[str, Any] = {}
        for row in effective_rows:
            row_scope_key = text(row.get("scope_key")) or ""
            row_direction, _filter_group, _scope_month = _parse_pending_invoice_scope_key(row_scope_key)
            if row_direction not in {"expense", "income"}:
                continue
            source_versions = row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
            dependency_versions = source_versions.get(dependency_key)
            if isinstance(dependency_versions, dict):
                dependency_versions_by_direction[row_direction] = dict(dependency_versions)
        if dependency_versions_by_direction:
            aggregate[dependency_key] = dependency_versions_by_direction
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


def _bank_detail_empty_statistics() -> dict[str, int]:
    return {
        "transaction_count": 0,
        "expense_transaction_count": 0,
        "income_transaction_count": 0,
        "classified_transaction_count": 0,
        "unclassified_transaction_count": 0,
        "linked_transaction_count": 0,
        "unlinked_transaction_count": 0,
    }


def _normalized_workbench_relation_source_summary(
    value: Any,
    *,
    scope_key: str,
) -> dict[str, Any]:
    payload = value if isinstance(value, dict) else {}
    return {
        "source": text(payload.get("source")),
        "scope_key": text(payload.get("scope_key")) or scope_key,
        "relation_count": int_value(payload.get("relation_count"), 0),
        "relation_updated_at": text(payload.get("relation_updated_at")) or "",
    }


def _bank_detail_statistics_from_rows(rows: list[dict[str, Any]]) -> dict[str, int]:
    statistics = _bank_detail_empty_statistics()
    for row in rows:
        payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
        direction = text(row.get("direction") or payload.get("direction"))
        classified = bool(text(row.get("effective_category_code") or payload.get("effective_category_code")))
        linked = text(row.get("relation_status") or payload.get("relation_status")) == "linked"
        statistics["transaction_count"] += 1
        if direction == "income":
            statistics["income_transaction_count"] += 1
        else:
            statistics["expense_transaction_count"] += 1
        statistics["classified_transaction_count" if classified else "unclassified_transaction_count"] += 1
        statistics["linked_transaction_count" if linked else "unlinked_transaction_count"] += 1
    return statistics


def _bank_detail_scope_statistics(raw_payload: Any) -> dict[str, int] | None:
    if not isinstance(raw_payload, dict) or not isinstance(raw_payload.get("statistics"), dict):
        return None
    raw_statistics = raw_payload["statistics"]
    expected_keys = tuple(_bank_detail_empty_statistics())
    if any(
        isinstance(raw_statistics.get(key), bool)
        or not isinstance(raw_statistics.get(key), int)
        or raw_statistics.get(key, -1) < 0
        for key in expected_keys
    ):
        return None
    statistics = {key: int(raw_statistics[key]) for key in expected_keys}
    if (
        statistics["transaction_count"]
        != statistics["expense_transaction_count"] + statistics["income_transaction_count"]
        or statistics["transaction_count"]
        != statistics["classified_transaction_count"] + statistics["unclassified_transaction_count"]
        or statistics["transaction_count"]
        != statistics["linked_transaction_count"] + statistics["unlinked_transaction_count"]
    ):
        return None
    return statistics


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
