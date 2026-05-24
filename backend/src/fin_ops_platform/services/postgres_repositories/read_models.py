from __future__ import annotations

from copy import deepcopy
import re
from typing import Any

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

MONTH_SCOPE_RE = re.compile(r"^\d{4}-\d{2}$")


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
            select source_kind, payload, raw_payload
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
        for row in rows:
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
        }
        return result

    def save_search_index_rows(self, *, scope_key: str, rows: list[dict[str, Any]]) -> None:
        scope_month = month_start(scope_key)

        def write(connection: Any) -> None:
            if scope_month is not None:
                connection.execute("delete from read_model.search_index_rows where scope_month = %s::date", (scope_month,))
            for row in list(rows or []):
                payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
                connection.execute(
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
                    (
                        text(row.get("row_id") or payload.get("row_id")),
                        text(row.get("source_kind") or payload.get("record_type")),
                        scope_month or month_start(payload.get("month")),
                        text(row.get("status") or payload.get("zone_hint")),
                        text(row.get("title") or payload.get("title")),
                        text(row.get("subtitle") or payload.get("secondary_meta")),
                        text(row.get("searchable_text")),
                        text(row.get("project_name")),
                        text(row.get("counterparty_name")),
                        decimal_text(row.get("amount")),
                        jsonb(row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}),
                        text(row.get("generated_at")),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def list_pending_invoice_rows(
        self,
        *,
        direction: str,
        filter: str = "all",
        date_from: str | None = None,
        date_to: str | None = None,
        keyword: str | None = None,
        page: int | str | None = 1,
        page_size: int | str | None = 50,
    ) -> dict[str, Any] | None:
        normalized_direction = str(direction or "").strip()
        normalized_filter = str(filter or "all").strip() or "all"
        page_number = max(int_value(page, 1), 1)
        page_limit = min(max(int_value(page_size, 50), 1), 200)
        where = ["direction = %s"]
        params: list[Any] = [normalized_direction]
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
        where_sql = " and ".join(where)
        total_row = self._connection.fetch_one(
            f"select count(*) as count from read_model.pending_invoice_rows where {where_sql}",
            tuple(params),
        )
        total = int_value(total_row.get("count") if isinstance(total_row, dict) else 0, 0)
        if total == 0:
            return None
        rows = self._connection.fetch_all(
            f"""
            select payload, raw_payload, missing_invoice, can_create_invoice
            from read_model.pending_invoice_rows
            where {where_sql}
            order by trade_date desc, row_id
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
            },
            "bank_transaction_tags": {},
            "bank_transaction_tags_version": 1,
            "refresh_status": self._refresh_status(scope_type="pending_invoice", scope_key=f"{normalized_direction}:{normalized_filter}"),
        }

    def save_pending_invoice_rows(self, *, scope_key: str, rows: list[dict[str, Any]]) -> None:
        direction, _, filter_group = str(scope_key or "").partition(":")
        normalized_direction = direction or "expense"
        normalized_filter = filter_group or "all"

        def write(connection: Any) -> None:
            connection.execute(
                "delete from read_model.pending_invoice_rows where direction = %s and (%s = 'all' or filter_group = %s)",
                (normalized_direction, normalized_filter, normalized_filter),
            )
            for row in list(rows or []):
                payload = serialize_value(row.get("payload") if isinstance(row.get("payload"), dict) else row)
                bank_transaction = payload.get("bank_transaction") if isinstance(payload.get("bank_transaction"), dict) else {}
                connection.execute(
                    """
                    insert into read_model.pending_invoice_rows(
                        row_id, direction, filter_group, scope_month, trade_date, counterparty_name,
                        amount, missing_invoice, can_create_invoice, searchable_text, generated_at, payload, raw_payload
                    )
                    values (%s, %s, %s, %s::date, %s::date, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s)
                    on conflict (row_id, direction) do update set
                        filter_group = excluded.filter_group,
                        scope_month = excluded.scope_month,
                        trade_date = excluded.trade_date,
                        counterparty_name = excluded.counterparty_name,
                        amount = excluded.amount,
                        missing_invoice = excluded.missing_invoice,
                        can_create_invoice = excluded.can_create_invoice,
                        searchable_text = excluded.searchable_text,
                        generated_at = excluded.generated_at,
                        payload = excluded.payload,
                        raw_payload = excluded.raw_payload,
                        updated_at = now()
                    """,
                    (
                        text(payload.get("id")),
                        normalized_direction,
                        text(row.get("filter_group") or payload.get("filter_group") or "all"),
                        month_start(bank_transaction.get("trade_time")),
                        text(bank_transaction.get("trade_time"))[:10] if text(bank_transaction.get("trade_time")) else None,
                        text(bank_transaction.get("counterparty_name")),
                        decimal_text(bank_transaction.get("amount")),
                        not bool(payload.get("invoices")),
                        bool(payload.get("can_create_invoice")),
                        text(row.get("searchable_text") or payload),
                        text(row.get("generated_at")),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )

        run_in_transaction(self._connection, write)

    def _refresh_status(self, *, scope_type: str, scope_key: str) -> str:
        dirty_row = self._connection.fetch_one(
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
        result = {
            "scope_key": normalized_scope_key,
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else payload,
            "cache_status": text(row.get("cache_status") or payload.get("cache_status")) or "fresh",
            "generated_at": text(row.get("generated_at") or payload.get("generated_at")),
            "source_versions": payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
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
        materialized_row = self._connection.fetch_one(
            """
            select scope_key, generated_at::text as generated_at, source_versions, payload, raw_payload
            from read_model.workbench_summary
            where scope_key = %s
            """,
            (normalized_scope_key,),
        )
        if isinstance(materialized_row, dict):
            payload = _read_model_payload(materialized_row)
            if isinstance(payload, dict):
                result = dict(payload)
                result.setdefault("month", normalized_scope_key)
                result.setdefault("scope_key", normalized_scope_key)
                result.setdefault("generated_at", text(materialized_row.get("generated_at")))
                result["read_model_status"] = self._workbench_summary_read_model_status(
                    scope_key=normalized_scope_key
                )
                return result

        group_where, group_params = self._workbench_scope_filter(normalized_scope_key)
        row_where, row_params = self._workbench_scope_filter(normalized_scope_key)
        group_rows = self._connection.fetch_all(
            f"""
            select zone, count(*)::bigint as count
            from read_model.workbench_groups
            where {group_where}
            group by zone
            """,
            tuple(group_params),
        )
        row_count_rows = self._connection.fetch_all(
            f"""
            select coalesce(nullif(payload->>'type', ''), source_kind) as row_type, count(*)::bigint as count
            from read_model.workbench_rows
            where {row_where}
            group by row_type
            """,
            tuple(row_params),
        )
        generated_row = self._connection.fetch_one(
            f"""
            select max(generated_at)::text as generated_at
            from read_model.workbench_groups
            where {group_where}
            """,
            tuple(group_params),
        )
        summary = {
            "oa_count": 0,
            "bank_count": 0,
            "invoice_count": 0,
            "paired_count": 0,
            "open_count": 0,
            "exception_count": 0,
        }
        for row in row_count_rows:
            row_type = text(row.get("row_type")) or ""
            count = int_value(row.get("count"), 0)
            if row_type == "oa":
                summary["oa_count"] += count
            elif row_type == "bank":
                summary["bank_count"] += count
            elif row_type == "invoice":
                summary["invoice_count"] += count
        for row in group_rows:
            zone = text(row.get("zone")) or ""
            count = int_value(row.get("count"), 0)
            if zone == "paired":
                summary["paired_count"] += count
            elif zone == "open":
                summary["open_count"] += count
        generated_at = text((generated_row or {}).get("generated_at"))
        if generated_at is None and not any(summary.values()):
            return None
        refresh_status = self.get_workbench_refresh_status(scope_key=normalized_scope_key)
        return {
            "month": normalized_scope_key,
            "scope_key": normalized_scope_key,
            "summary": summary,
            "invoice_inventory": self._workbench_invoice_inventory(scope_key=normalized_scope_key),
            "read_model_status": refresh_status["read_model_status"],
            "generated_at": generated_at,
        }

    def _workbench_invoice_inventory(self, *, scope_key: str) -> dict[str, int]:
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
        attachment_row = self._connection.fetch_one(
            f"""
            select count(distinct row_id)::bigint as oa_attachment_total
            from read_model.workbench_rows
            where {row_where} and source_kind = 'oa_attachment_invoice'
            """,
            tuple(row_params),
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
        all_groups = [*paired_groups, *open_groups]
        summary = {
            "oa_count": sum(len(group.get("oa_rows") or []) for group in all_groups),
            "bank_count": sum(len(group.get("bank_rows") or []) for group in all_groups),
            "invoice_count": sum(len(group.get("invoice_rows") or []) for group in all_groups),
            "paired_count": len(paired_groups),
            "open_count": len(open_groups),
            "exception_count": sum(1 for group in open_groups if text(group.get("status")) == "exception"),
        }
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
        sort: str | None = None,
        detail_level: str | None = None,
    ) -> dict[str, Any]:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_detail_level = _normalize_workbench_group_detail_level(detail_level)
        normalized_page = max(1, int_value(page, 1))
        normalized_page_size = min(200, max(1, int_value(page_size, 50)))
        offset = (normalized_page - 1) * normalized_page_size
        scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
        clauses = [scope_where, "zone = %s"]
        params = [*scope_params, normalized_zone]
        if normalized := text(status):
            clauses.append("status = %s")
            params.append(normalized)
        if normalized := text(source_kind):
            clauses.append("%s = any(source_kinds)")
            params.append(normalized)
        if normalized := text(search):
            clauses.append("(searchable_text ilike %s or group_id ilike %s)")
            pattern = f"%{normalized}%"
            params.extend([pattern, pattern])
        where_sql = " and ".join(clauses)
        order_by_sql = _workbench_groups_order_by(sort)
        count_row = self._connection.fetch_one(
            f"""
            select count(*) as total_count
            from read_model.workbench_groups
            where {where_sql}
            """,
            tuple(params),
        )
        page_params = [*params, normalized_page_size + 1, offset]
        rows = self._connection.fetch_all(
            f"""
            select group_id, zone, payload, raw_payload
            from read_model.workbench_groups
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
            if normalized_detail_level == "summary":
                group = _compact_workbench_group_for_summary_page(group)
            groups.append(group)
        refresh_status = self.get_workbench_refresh_status(scope_key=normalized_scope_key)
        return {
            "month": normalized_scope_key,
            "scope_key": normalized_scope_key,
            "zone": normalized_zone,
            "page": normalized_page,
            "page_size": normalized_page_size,
            "detail_level": normalized_detail_level,
            "total": int_value((count_row or {}).get("total_count"), 0),
            "has_more": len(rows) > normalized_page_size,
            "groups": groups,
            "read_model_status": refresh_status["read_model_status"],
        }

    def get_workbench_group_detail(self, *, scope_key: str, zone: str, group_id: str) -> dict[str, Any] | None:
        normalized_scope_key = str(scope_key or "").strip() or "all"
        normalized_zone = str(zone or "").strip()
        normalized_group_id = str(group_id or "").strip()
        if not normalized_zone or not normalized_group_id:
            return None
        scope_where, scope_params = self._workbench_scope_filter(normalized_scope_key)
        row = self._connection.fetch_one(
            f"""
            select group_id, zone, payload, raw_payload
            from read_model.workbench_groups
            where {scope_where}
              and zone = %s
              and group_id = %s
            order by scope_month desc nulls last, updated_at desc
            limit 1
            """,
            (*scope_params, normalized_zone, normalized_group_id),
        )
        if not isinstance(row, dict):
            return None
        group = _read_model_payload(row)
        if not isinstance(group, dict):
            return {"group_id": text(row.get("group_id"))}
        return group

    def get_workbench_refresh_status(self, *, scope_key: str | None = None) -> dict[str, Any]:
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
        read_model_status = "fresh"
        if dirty_statuses.intersection({"pending", "processing"}):
            read_model_status = "refreshing"
        elif "failed" in dirty_statuses:
            read_model_status = "stale"
        last_error = next((scope["last_error"] for scope in dirty_scopes if scope.get("last_error")), None)
        worker_lag_values = [
            row.get("lag_seconds")
            for row in worker_rows
            if isinstance(row.get("lag_seconds"), (int, float))
        ]
        return {
            "scope_key": normalized_scope_key,
            "read_model_status": read_model_status,
            "dirty_scopes": dirty_scopes,
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

    def save_workbench_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            refresh_all_scope = False
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    if scope_key == "all" or MONTH_SCOPE_RE.match(str(scope_key or "")):
                        refresh_all_scope = True
                    connection.execute(
                        "delete from read_model.workbench_rows where scope_key = %s",
                        (scope_key,),
                    )
                    connection.execute(
                        "delete from read_model.workbench_groups where scope_key = %s",
                        (scope_key,),
                    )
                    connection.execute(
                        "delete from read_model.workbench_summary where scope_key = %s",
                        (scope_key,),
                    )
                    connection.execute(
                        "delete from read_model.workbench_snapshots where scope_key = %s",
                        (scope_key,),
                    )
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                if scope_key == "all" or MONTH_SCOPE_RE.match(str(scope_key or "")):
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
                existing_row = connection.fetch_one(
                    "select source_versions from read_model.workbench_snapshots where scope_key = %s",
                    (scope_key,),
                )
                existing_source_versions = existing_row.get("source_versions") if isinstance(existing_row, dict) else {}
                if (
                    incoming_source_version is not None
                    and _source_version_value(existing_source_versions) is not None
                    and incoming_source_version < _source_version_value(existing_source_versions)
                ):
                    continue
                connection.execute(
                    """
                    insert into read_model.workbench_snapshots(scope_key, scope_month, source_versions, generated_at, cache_status, row_count, payload, raw_payload)
                    values (%s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s)
                    on conflict (scope_key) do update set
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
                        scope_key,
                        scope_month,
                        jsonb(source_versions),
                        generated_at,
                        cache_status,
                        len(workbench_rows) or int_value(payload.get("row_count"), 0),
                        jsonb(payload),
                        jsonb({"normalized_payload": payload}),
                    ),
                )
                connection.execute("delete from read_model.workbench_rows where scope_key = %s", (scope_key,))
                connection.execute("delete from read_model.workbench_groups where scope_key = %s", (scope_key,))
                connection.execute(
                    """
                    insert into read_model.workbench_summary(
                        scope_key, scope_month, source_versions, generated_at, cache_status,
                        summary, invoice_inventory, payload, raw_payload
                    )
                    values (%s, %s::date, %s, coalesce(%s::timestamptz, now()), %s, %s, %s, %s, %s)
                    on conflict (scope_key) do update set
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
                for row in workbench_rows:
                    row_id = text(row.get("id") or row.get("row_id"))
                    if row_id is None:
                        continue
                    connection.execute(
                        """
                        insert into read_model.workbench_rows(
                            row_id, scope_month, scope_key, source_kind, status, project_id, project_name,
                            counterparty_name, amount, source_versions, generated_at, cache_status, payload, raw_payload
                        )
                        values (%s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), %s, %s, %s)
                        on conflict (scope_key, row_id) do update set
                            scope_month = excluded.scope_month,
                            scope_key = excluded.scope_key,
                            source_kind = excluded.source_kind,
                            status = excluded.status,
                            project_id = excluded.project_id,
                            project_name = excluded.project_name,
                            counterparty_name = excluded.counterparty_name,
                            amount = excluded.amount,
                            source_versions = excluded.source_versions,
                            generated_at = excluded.generated_at,
                            cache_status = excluded.cache_status,
                            payload = excluded.payload,
                            raw_payload = excluded.raw_payload,
                            updated_at = now()
                        """,
                        (
                            row_id,
                            month_start(row.get("scope_month") or row.get("month") or scope_month),
                            scope_key,
                            text(row.get("source_kind") or row.get("type") or "workbench_row") or "workbench_row",
                            text(row.get("status") or payload.get("status") or "open") or "open",
                            text(row.get("project_id")),
                            text(row.get("project_name") or row.get("project")),
                            text(row.get("counterparty_name") or row.get("counterparty") or row.get("supplier_name")),
                            decimal_text(row.get("amount") or row.get("amount_with_tax") or row.get("invoice_amount")),
                            jsonb(source_versions),
                            generated_at,
                            cache_status,
                            jsonb(row),
                            jsonb({"normalized_payload": row}),
                        ),
                    )
                for group in workbench_groups:
                    group_id = text(group.get("group_id"))
                    if group_id is None:
                        continue
                    connection.execute(
                        """
                        insert into read_model.workbench_groups(
                            group_id, scope_key, scope_month, zone, status, group_type, source_kinds,
                            row_count, searchable_text, oa_sort_min, oa_sort_max, bank_sort_min, bank_sort_max,
                            invoice_sort_min, invoice_sort_max, source_versions, generated_at, cache_status,
                            payload, raw_payload
                        )
                        values (
                            %s, %s, %s::date, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                            %s, coalesce(%s::timestamptz, now()), %s, %s, %s
                        )
                        on conflict (scope_key, zone, group_id) do update set
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
                        (
                            group_id,
                            scope_key,
                            month_start(group.get("scope_month") or group.get("month") or scope_month),
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
            if refresh_all_scope:
                self._refresh_workbench_all_scope_from_month_shards(connection)

        run_in_transaction(self._connection, write)

    def _refresh_workbench_all_scope_from_month_shards(self, connection: Any) -> None:
        group_rows = connection.fetch_all(
            """
            select scope_key, scope_month, zone, group_id, payload, source_versions, generated_at::text as generated_at
            from read_model.workbench_groups
            where scope_key <> 'all'
            order by scope_month desc nulls last, zone, group_id, updated_at desc
            """
        )
        groups = []
        max_generated_at = ""
        max_source_version: int | None = None
        for row in group_rows:
            group = _read_model_payload(row)
            if not isinstance(group, dict):
                continue
            normalized_group = deepcopy(group)
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
            return

        aggregate_payload = _aggregate_workbench_all_scope_payload(groups)
        aggregate_source_versions = {
            "builder": "workbench_sql_projection.aggregate.v1",
            "source_version": max_source_version or 0,
        }
        generated_at = max_generated_at or None
        workbench_rows = list(self._iter_workbench_rows(aggregate_payload))
        workbench_groups = list(self._iter_workbench_groups(aggregate_payload))
        summary_payload = self._workbench_summary_from_payload(
            scope_key="all",
            grouped_payload=aggregate_payload,
            source_versions=aggregate_source_versions,
            generated_at=generated_at,
        )

        connection.execute("delete from read_model.workbench_rows where scope_key = 'all'")
        connection.execute("delete from read_model.workbench_groups where scope_key = 'all'")
        connection.execute("delete from read_model.workbench_summary where scope_key = 'all'")
        connection.execute("delete from read_model.workbench_snapshots where scope_key = 'all'")
        connection.execute(
            """
            insert into read_model.workbench_snapshots(
                scope_key, scope_month, source_versions, generated_at, cache_status, row_count, payload, raw_payload
            )
            values ('all', null, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s, %s)
            """,
            (
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
        connection.execute(
            """
            insert into read_model.workbench_summary(
                scope_key, scope_month, source_versions, generated_at, cache_status,
                summary, invoice_inventory, payload, raw_payload
            )
            values ('all', null, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s, %s, %s)
            """,
            (
                jsonb(aggregate_source_versions),
                generated_at,
                jsonb(summary_payload.get("summary") if isinstance(summary_payload.get("summary"), dict) else {}),
                jsonb(summary_payload.get("invoice_inventory") if isinstance(summary_payload.get("invoice_inventory"), dict) else {}),
                jsonb(summary_payload),
                jsonb({"normalized_payload": summary_payload}),
            ),
        )
        for row in workbench_rows:
            row_id = text(row.get("id") or row.get("row_id"))
            if row_id is None:
                continue
            connection.execute(
                """
                insert into read_model.workbench_rows(
                    row_id, scope_month, scope_key, source_kind, status, project_id, project_name,
                    counterparty_name, amount, source_versions, generated_at, cache_status, payload, raw_payload
                )
                values (%s, %s::date, 'all', %s, %s, %s, %s, %s, %s, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s)
                on conflict (scope_key, row_id) do update set
                    scope_month = excluded.scope_month,
                    source_kind = excluded.source_kind,
                    status = excluded.status,
                    project_id = excluded.project_id,
                    project_name = excluded.project_name,
                    counterparty_name = excluded.counterparty_name,
                    amount = excluded.amount,
                    source_versions = excluded.source_versions,
                    generated_at = excluded.generated_at,
                    cache_status = excluded.cache_status,
                    payload = excluded.payload,
                    raw_payload = excluded.raw_payload,
                    updated_at = now()
                """,
                (
                    row_id,
                    month_start(row.get("scope_month") or row.get("month")),
                    text(row.get("source_kind") or row.get("type") or "workbench_row") or "workbench_row",
                    text(row.get("status") or "open") or "open",
                    text(row.get("project_id")),
                    text(row.get("project_name") or row.get("project")),
                    text(row.get("counterparty_name") or row.get("counterparty") or row.get("supplier_name")),
                    decimal_text(row.get("amount") or row.get("amount_with_tax") or row.get("invoice_amount")),
                    jsonb(aggregate_source_versions),
                    generated_at,
                    jsonb(row),
                    jsonb({"normalized_payload": row}),
                ),
            )
        for group in workbench_groups:
            group_id = text(group.get("group_id"))
            if group_id is None:
                continue
            sort_keys = _workbench_group_sort_keys(group)
            connection.execute(
                """
                insert into read_model.workbench_groups(
                    group_id, scope_key, scope_month, zone, status, group_type, source_kinds,
                    row_count, searchable_text, oa_sort_min, oa_sort_max, bank_sort_min, bank_sort_max,
                    invoice_sort_min, invoice_sort_max, source_versions, generated_at, cache_status,
                    payload, raw_payload
                )
                values (
                    %s, 'all', null, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                    %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s
                )
                on conflict (scope_key, zone, group_id) do update set
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
                (
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
        final_summary_payload = self._workbench_summary_from_payload(
            scope_key="all",
            grouped_payload=aggregate_payload,
            source_versions=aggregate_source_versions,
            generated_at=generated_at,
        )
        final_summary_payload["invoice_inventory"] = self._workbench_invoice_inventory(scope_key="all")
        connection.execute(
            """
            insert into read_model.workbench_summary(
                scope_key, scope_month, source_versions, generated_at, cache_status,
                summary, invoice_inventory, payload, raw_payload
            )
            values ('all', null, %s, coalesce(%s::timestamptz, now()), 'fresh', %s, %s, %s, %s)
            on conflict (scope_key) do update set
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
        if scope_key == "all":
            clauses = ["scope_key <> 'all'"]
            params: list[Any] = []
        else:
            clauses = ["scope_key = %s"]
            params = [scope_key]
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
            select row_id, source_kind, status, payload, raw_payload
            from read_model.workbench_rows
            where scope_key <> 'all'
              and source_kind = 'bank'
              and (
                    counterparty_name = %s
                    or payload->>'counterparty_name' = %s
                    or payload->>'counterparty_name_raw' = %s
                  )
              and (
                    scope_month >= %s::date
                    and scope_month < (%s::date + interval '1 year')
                  )
            order by coalesce(payload->>'trade_time', payload->>'pay_receive_time', payload->>'txn_date', '') desc, row_id
            """,
            ("批量账务集中处理", "批量账务集中处理", "批量账务集中处理", bank_start, bank_start),
        )
        oa_rows = self._connection.fetch_all(
            """
            select row_id, source_kind, status, payload, raw_payload
            from read_model.workbench_rows
            where scope_key <> 'all'
              and source_kind = 'oa'
              and (
                    scope_month >= %s::date
                    and scope_month < (%s::date + interval '1 year')
                  )
            order by coalesce(payload->>'apply_time', payload->>'application_time', payload->>'application_date', payload->>'created_at', '') desc, row_id
            """,
            (oa_start, oa_start),
        )
        invoice_rows = self._connection.fetch_all(
            """
            select row_id, source_kind, status, payload, raw_payload
            from read_model.workbench_rows
            where scope_key <> 'all'
              and source_kind = 'oa_attachment_invoice'
              and (
                    scope_month >= %s::date
                    and scope_month < (%s::date + interval '1 year')
                  )
            order by row_id
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
        return {"candidates": values} if values else {}

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
        payload = _read_model_payload(row)
        if not isinstance(payload, dict):
            payload = {}
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
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else payload,
            "generated_at": text(row.get("generated_at") or payload.get("generated_at")),
            "source_versions": payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
            "entry_count": int_value(row.get("entry_count") or payload.get("entry_count"), 0),
            "refresh_status": refresh_status,
            "dirty_scope": dict(dirty_row) if isinstance(dirty_row, dict) else None,
        }

    def save_cost_statistics_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        run_in_transaction(
            self._connection,
            lambda connection: self._save_generic_read_model_snapshots(
                connection,
                snapshot,
                table="read_model.cost_statistics_read_models",
                changed_scope_keys=changed_scope_keys,
                default_project_scope="all",
            ),
        )

    def load_tax_offset_read_models(self) -> dict[str, Any]:
        return self._load_table_map(
            "select scope_key as key, payload, raw_payload from read_model.tax_offset_read_models order by scope_key",
            "read_models",
        )

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
        payload = _read_model_payload(row)
        if not isinstance(payload, dict):
            payload = {}
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
            "payload": payload.get("payload") if isinstance(payload.get("payload"), dict) else payload,
            "schema_version": text(row.get("schema_version") or payload.get("schema_version")),
            "generated_at": text(row.get("generated_at") or payload.get("generated_at")),
            "source_versions": payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {},
            "entry_count": int_value(row.get("entry_count") or payload.get("entry_count"), 0),
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

        run_in_transaction(self._connection, write)

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

        def add_row(value: Any) -> None:
            if not isinstance(value, dict):
                return
            row_id = text(value.get("id") or value.get("row_id"))
            if row_id is None or row_id in seen:
                return
            seen.add(row_id)
            rows.append(serialize_value(value))

        def scan_group(group: Any) -> None:
            if not isinstance(group, dict):
                return
            for key, value in group.items():
                if not str(key).endswith("_rows") or not isinstance(value, list):
                    continue
                for row in value:
                    add_row(row)

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
                    scan_group(group)
            else:
                scan_group(section)
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
                group_id = text(group.get("group_id") or group.get("id")) or f"{zone}:{index}"
                key = (zone, group_id)
                if key in seen:
                    continue
                seen.add(key)
                group_rows = list(_iter_group_rows(group))
                row_ids = {
                    row_id
                    for row in group_rows
                    if (row_id := text(row.get("id") or row.get("row_id"))) is not None
                }
                row_identity = _workbench_group_row_identity(group)
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
                sort_keys = _workbench_group_sort_keys(group)
                groups.append(
                    {
                        "group_id": group_id,
                        "scope_month": group.get("scope_month") or group.get("month") or payload.get("month"),
                        "month": group.get("month") or payload.get("month"),
                        "zone": zone,
                        "status": zone,
                        "group_type": text(group.get("group_type")) or "candidate",
                        "source_kinds": source_kinds,
                        "row_count": len(row_ids),
                        "searchable_text": _searchable_group_text(group),
                        **sort_keys,
                        "payload": serialize_value(group),
                    }
                )
        return groups


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


def _aggregate_workbench_all_scope_payload(groups: list[dict[str, Any]]) -> dict[str, Any]:
    aggregate = {
        "month": "all",
        "scope_key": "all",
        "read_model_scope_key": "all",
        "paired": {"groups": []},
        "open": {"groups": []},
        "workbench_read_model_schema_version": "workbench_sql_projection.aggregate.v1",
    }
    grouped: dict[tuple[str, str], dict[str, Any]] = {}
    for group in groups:
        zone = text(group.get("zone") or group.get("status")) or "open"
        if zone not in {"paired", "open"}:
            zone = "open"
        group_id = text(group.get("group_id") or group.get("id"))
        if group_id is None:
            continue
        key = (zone, group_id)
        if key not in grouped:
            grouped[key] = _normalize_all_scope_group(group, zone=zone, group_id=group_id)
            continue
        _merge_all_scope_group(grouped[key], group)

    for (zone, _group_id), group in grouped.items():
        _finalize_all_scope_group(group, zone=zone)
        aggregate[zone]["groups"].append(group)
    for zone in ("paired", "open"):
        aggregate[zone]["groups"].sort(key=lambda item: text(item.get("group_id")) or "")
    aggregate["summary"] = _summarize_workbench_payload_groups(aggregate)
    return aggregate


def _normalize_all_scope_group(group: dict[str, Any], *, zone: str, group_id: str) -> dict[str, Any]:
    normalized = deepcopy(group)
    normalized["group_id"] = group_id
    normalized["id"] = group_id
    normalized["zone"] = zone
    normalized["status"] = zone
    normalized["scope_key"] = "all"
    normalized["month"] = "all"
    normalized["scope_month"] = None
    normalized.pop("row_counts", None)
    normalized.pop("collapsed_row_counts", None)
    for key in ("oa_rows", "bank_rows", "invoice_rows"):
        normalized[key] = _dedupe_workbench_rows(normalized.get(key))
    collapsed_rows = normalized.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        normalized["collapsed_rows"] = {
            str(row_type): _dedupe_workbench_rows(rows)
            for row_type, rows in collapsed_rows.items()
            if isinstance(rows, list)
        }
    return normalized


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
    group.pop("row_counts", None)
    group.pop("collapsed_row_counts", None)
    group["zone"] = zone
    group["status"] = zone
    group["scope_key"] = "all"
    group["month"] = "all"
    group["scope_month"] = None
    group["row_count"] = len(_workbench_group_row_identity(group))
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


def _summarize_workbench_payload_groups(payload: dict[str, Any]) -> dict[str, int]:
    summary = {
        "oa_count": 0,
        "bank_count": 0,
        "invoice_count": 0,
        "paired_count": 0,
        "open_count": 0,
        "exception_count": 0,
    }
    seen_rows: set[tuple[str, str]] = set()
    for zone in ("paired", "open"):
        section = payload.get(zone)
        groups = section.get("groups") if isinstance(section, dict) else []
        if not isinstance(groups, list):
            continue
        summary[f"{zone}_count"] = sum(1 for group in groups if isinstance(group, dict))
        for group in groups:
            if not isinstance(group, dict):
                continue
            if zone == "open" and _workbench_group_has_danger(group):
                summary["exception_count"] += 1
            for row_type, row in _iter_typed_group_rows(group):
                row_type = text(row.get("type") or row.get("record_type")) or row_type
                row_id = text(row.get("id") or row.get("row_id"))
                if row_type is None or row_id is None:
                    continue
                row_key = (row_type, row_id)
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


def _compact_workbench_group_for_summary_page(group: dict[str, Any]) -> dict[str, Any]:
    compact = without_keys(dict(group), {"raw_payload", "payload"})
    compact["row_counts"] = {
        "oa": len(group.get("oa_rows") if isinstance(group.get("oa_rows"), list) else []),
        "bank": len(group.get("bank_rows") if isinstance(group.get("bank_rows"), list) else []),
        "invoice": len(group.get("invoice_rows") if isinstance(group.get("invoice_rows"), list) else []),
    }
    for row_key in ("oa_rows", "bank_rows", "invoice_rows"):
        rows = group.get(row_key)
        compact[row_key] = [
            _compact_workbench_row_for_summary_page(row)
            for row in rows[:WORKBENCH_GROUP_SUMMARY_PREVIEW_ROW_LIMIT]
            if isinstance(row, dict)
        ] if isinstance(rows, list) else []
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        compact["collapsed_row_counts"] = {
            str(row_type): len(rows)
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
    return without_keys(
        dict(row),
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


def _workbench_group_row_identity(group: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    identities = []
    for fallback_row_type, row in _iter_typed_group_rows(group):
        row_id = text(row.get("id") or row.get("row_id"))
        if row_id is None:
            continue
        row_type = text(row.get("type") or row.get("record_type")) or fallback_row_type
        identities.append((row_type, row_id))
    return tuple(sorted(set(identities)))


def _iter_typed_group_rows(group: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    rows: list[tuple[str, dict[str, Any]]] = []
    for row_type, key in (("oa", "oa_rows"), ("bank", "bank_rows"), ("invoice", "invoice_rows")):
        value = group.get(key)
        if isinstance(value, list):
            rows.extend((row_type, row) for row in value if isinstance(row, dict))
    collapsed_rows = group.get("collapsed_rows")
    if isinstance(collapsed_rows, dict):
        for row_type, value in collapsed_rows.items():
            if isinstance(value, list):
                rows.extend((str(row_type), row) for row in value if isinstance(row, dict))
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
