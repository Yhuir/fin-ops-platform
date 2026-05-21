from __future__ import annotations

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

    def load_workbench_read_models(self) -> dict[str, Any]:
        rows = self._connection.fetch_all("select scope_key as key, payload, raw_payload from read_model.workbench_snapshots order by scope_key")
        if rows:
            return {"read_models": {str(row.get("key")): _read_model_payload(row) for row in rows}}
        return {}

    def save_workbench_read_models(self, snapshot: dict[str, Any], *, changed_scope_keys: set[str] | None = None) -> None:
        def write(connection: Any) -> None:
            read_models = snapshot.get("read_models") if isinstance(snapshot, dict) else None
            if changed_scope_keys is not None:
                present_scope_keys = {scope_key for scope_key, _ in iter_mapping(read_models)}
                for scope_key in sorted(set(changed_scope_keys) - present_scope_keys):
                    connection.execute(
                        "delete from read_model.workbench_rows where scope_key = %s",
                        (scope_key,),
                    )
                    connection.execute(
                        "delete from read_model.workbench_snapshots where scope_key = %s",
                        (scope_key,),
                    )
            for scope_key, payload in iter_mapping(read_models):
                if changed_scope_keys is not None and scope_key not in changed_scope_keys:
                    continue
                grouped_payload = payload.get("payload") if isinstance(payload.get("payload"), dict) else payload
                source_versions = payload.get("source_versions") if isinstance(payload.get("source_versions"), dict) else {}
                generated_at = text(payload.get("generated_at"))
                cache_status = text(payload.get("cache_status") or "fresh") or "fresh"
                scope_month = month_start(payload.get("scope_month") or payload.get("month") or grouped_payload.get("month") or scope_key)
                workbench_rows = list(self._iter_workbench_rows(grouped_payload))
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
                        on conflict (row_id) do update set
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

        run_in_transaction(self._connection, write)

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
        clauses = ["scope_key = %s"]
        params: list[Any] = [scope_key]
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
        params.extend([normalized_page_size + 1, offset])
        rows = self._connection.fetch_all(
            f"""
            select row_id, source_kind, status, payload, raw_payload
            from read_model.workbench_rows
            where {' and '.join(clauses)}
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
            "has_more": len(rows) > normalized_page_size,
            "rows": payload_rows,
        }

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
            for scope_month in sorted(normalized_months):
                connection.execute(
                    "delete from read_model.workbench_candidate_matches where to_char(scope_month, 'YYYY-MM') = %s",
                    (scope_month,),
                )
            for candidate_key, payload in iter_mapping(candidates):
                scope_month = month_start(payload.get("scope_month") or payload.get("month"))
                if normalized_months and str(scope_month or "")[:7] not in normalized_months:
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


def _read_model_payload(row: dict[str, Any], *, drop_rebuildable_rows: bool = False) -> Any:
    payload = row_payload(row, "payload", "extra_payload", "raw_payload")
    if drop_rebuildable_rows and isinstance(payload, dict) and payload.get("rebuildable") is True:
        return None
    return without_keys(payload, {"rebuildable"})


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
