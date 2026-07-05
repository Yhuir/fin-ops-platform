from __future__ import annotations

import re
from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from fin_ops_platform.services.cost_statistics_bank_accounts import (
    bank_account_mappings_fingerprint_from_settings_payload,
    bank_accounts_from_settings_payload,
    bank_auto_tag_rules_version_from_settings_payload,
)
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.cost_statistics_read_model_repository import CostStatisticsReadModelRepositoryPort
from fin_ops_platform.services.cost_statistics_read_model_service import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    CostStatisticsReadModelService,
)
from fin_ops_platform.services.cost_statistics_relation_rules import (
    is_candidate_workbench_group,
    is_cost_eligible_open_group,
)
from fin_ops_platform.services.live_workbench_service import format_decimal
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.read_model_query_gateway import build_fresh_cache_envelope
from fin_ops_platform.services.tax_offset_read_model_repository import TaxOffsetReadModelRepositoryPort
from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetReadModelService,
)
from fin_ops_platform.services.tax_offset_service import TaxOffsetService
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
ZERO = Decimal("0.00")


class CostStatisticsSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        redis_helper: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = CostStatisticsReadModelRepositoryPort(
            read_model_repository or PostgresReadModelRepository(connection)
        )
        self._redis_helper = redis_helper

    def list_cost_statistics_scope_shards(self, scope_key: str) -> list[str]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month != "all":
            return [f"{project_scope}:{month}"] if MONTH_RE.match(month) else []
        rows = self._connection.fetch_all(
            """
            select scope_key
            from read_model.workbench_generations
            where tenant_id = 'default'
              and status = 'active'
              and scope_key <> 'all'
            order by scope_key desc
            """
        )
        return [
            f"{project_scope}:{row['scope_key']}"
            for row in rows
            if MONTH_RE.match(str(row.get("scope_key") or ""))
        ]

    def rebuild_cost_statistics_read_model_scope(self, scope_key: str) -> dict[str, object]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month == "all":
            return self.rebuild_cost_statistics_parent_scope(scope_key)
        return self.rebuild_cost_statistics_month_scope(scope_key)

    def rebuild_cost_statistics_month_scope(self, scope_key: str) -> dict[str, object]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month == "all":
            raise ValueError("month scope rebuild requires a concrete YYYY-MM scope.")
        source_versions = self._source_versions(month)
        unchanged = self._unchanged_cost_statistics_scope_result(
            scope_key=f"{project_scope}:{month}",
            month=month,
            project_scope=project_scope,
            source_versions=source_versions,
            refresh_kind="month",
        )
        if unchanged is not None:
            return unchanged
        payload = self._build_explorer_payload(month, project_scope=project_scope)
        return self._publish_cost_statistics_scope(
            month=month,
            project_scope=project_scope,
            payload=payload,
            source_versions=source_versions,
            refresh_kind="month",
        )

    def rebuild_cost_statistics_parent_scope(self, scope_key: str) -> dict[str, object]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month != "all":
            raise ValueError("parent scope rebuild requires an all scope.")
        entries, shard_versions = self._cost_entries_from_materialized_shards(project_scope=project_scope)
        payload = self._build_explorer_payload_from_entries(entries, month="all", project_scope=project_scope)
        source_versions = {
            **self._source_versions("all"),
            "cost_statistics_parent_source": "materialized_shards",
            "source_shard_count": len(shard_versions),
            "source_shards": shard_versions,
        }
        unchanged = self._unchanged_cost_statistics_scope_result(
            scope_key=f"{project_scope}:all",
            month="all",
            project_scope=project_scope,
            source_versions=source_versions,
            refresh_kind="parent",
        )
        if unchanged is not None:
            return unchanged
        return self._publish_cost_statistics_scope(
            month="all",
            project_scope=project_scope,
            payload=payload,
            source_versions=source_versions,
            refresh_kind="parent",
        )

    def missing_or_stale_cost_statistics_shards(self, parent_scope_key: str) -> list[str]:
        project_scope, month = _parse_cost_scope_key(parent_scope_key)
        if month != "all":
            return []
        shard_keys = self.list_cost_statistics_scope_shards(parent_scope_key)
        if not shard_keys:
            return []
        readiness_rows = self._connection.fetch_all(
            """
            select scope_key, status
            from read_model.app_status_readiness
            where tenant_id = 'default'
              and read_model_key = 'cost_statistics'
              and scope_type = 'cost_statistics'
              and scope_key = any(%s)
            """,
            (shard_keys,),
        )
        fresh_scopes = {
            str(row.get("scope_key") or "").strip()
            for row in readiness_rows
            if str(row.get("status") or "").strip().lower() == "fresh"
        }
        return [scope_key for scope_key in shard_keys if scope_key not in fresh_scopes]

    def _publish_cost_statistics_scope(
        self,
        *,
        month: str,
        project_scope: str,
        payload: dict[str, Any],
        source_versions: dict[str, Any],
        refresh_kind: str,
    ) -> dict[str, object]:
        service = CostStatisticsReadModelService()
        read_model = service.upsert_read_model(
            month,
            project_scope,
            payload,
            generated_at=datetime.now().isoformat(),
            source_scope_keys=[month],
            source_versions=source_versions,
            cache_status="ready",
        )
        warmed_scope_key = str(read_model["scope_key"])
        self._read_model_repository.save_cost_statistics_read_models(
            service.snapshot_scope_keys([warmed_scope_key]),
            changed_scope_keys={warmed_scope_key},
        )
        self._set_redis_json(
            f"cost_statistics:explorer:{warmed_scope_key}",
            build_fresh_cache_envelope(
                {
                    **payload,
                    "read_model_status": "fresh",
                    "read_model_scope_key": warmed_scope_key,
                    "source_versions": source_versions,
                },
                scope_key=warmed_scope_key,
                source_versions=source_versions,
                schema_version=COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            ),
        )
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "project_scope": project_scope,
            "entry_count": len(payload.get("time_rows") or []),
            "row_count": len(payload.get("time_rows") or []),
            "source_shard_count": source_versions.get("source_shard_count"),
            "refresh_kind": refresh_kind,
        }

    def _source_versions(self, month: str) -> dict[str, Any]:
        settings_payload = _app_settings_payload(self._connection)
        source_versions = {
            "cost_statistics_read_model_schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
            "workbench_scope_key": month,
            "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": bank_auto_tag_rules_version_from_settings_payload(settings_payload),
            "bank_account_mappings_fingerprint": bank_account_mappings_fingerprint_from_settings_payload(settings_payload),
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }
        if month != "all":
            workbench_source_versions = self._workbench_source_versions(month)
            if workbench_source_versions:
                source_versions["workbench_source_versions"] = workbench_source_versions
        return source_versions

    def _workbench_source_versions(self, scope_key: str) -> dict[str, Any]:
        try:
            row = self._connection.fetch_one(
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
        except Exception:
            return {}
        source_versions = row.get("source_versions") if isinstance(row, dict) else {}
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def _unchanged_cost_statistics_scope_result(
        self,
        *,
        scope_key: str,
        month: str,
        project_scope: str,
        source_versions: dict[str, Any],
        refresh_kind: str,
    ) -> dict[str, object] | None:
        get_view = getattr(self._read_model_repository, "get_cost_statistics_view", None)
        if not callable(get_view):
            return None
        try:
            view = get_view(scope_key=scope_key)
        except AttributeError:
            return None
        if not isinstance(view, dict):
            return None
        existing_source_versions = view.get("source_versions")
        if not isinstance(existing_source_versions, dict) or existing_source_versions != source_versions:
            return None
        entry_count = int(view.get("entry_count") or 0)
        return {
            "scope_key": scope_key,
            "month": month,
            "project_scope": project_scope,
            "entry_count": entry_count,
            "row_count": entry_count,
            "source_versions": source_versions,
            "refresh_kind": refresh_kind,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

    def _build_explorer_payload(self, month: str, *, project_scope: str) -> dict[str, Any]:
        entries = self._cost_entries_from_workbench(month, project_scope=project_scope)
        return self._build_explorer_payload_from_entries(entries, month=month, project_scope=project_scope)

    def _build_explorer_payload_from_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        month: str,
        project_scope: str,
    ) -> dict[str, Any]:
        sorted_entries = sorted(entries, key=lambda item: (str(item["trade_time"]), str(item["transaction_id"])), reverse=True)
        project_groups: dict[str, dict[str, Any]] = {}
        expense_type_groups: dict[str, dict[str, Any]] = {}
        for entry in sorted_entries:
            project_bucket = project_groups.setdefault(
                entry["project_name"],
                {"project_name": entry["project_name"], "total_amount": ZERO, "transaction_count": 0, "expense_types": set()},
            )
            project_bucket["total_amount"] += entry["amount_decimal"]
            project_bucket["transaction_count"] += 1
            project_bucket["expense_types"].add(entry["expense_type"])
            expense_bucket = expense_type_groups.setdefault(
                entry["expense_type"],
                {"expense_type": entry["expense_type"], "total_amount": ZERO, "transaction_count": 0, "projects": set()},
            )
            expense_bucket["total_amount"] += entry["amount_decimal"]
            expense_bucket["transaction_count"] += 1
            expense_bucket["projects"].add(entry["project_name"])
        return {
            "month": month,
            "project_scope": project_scope,
            "summary": {
                "row_count": len(sorted_entries),
                "transaction_count": len(sorted_entries),
                "total_amount": format_decimal(sum((entry["amount_decimal"] for entry in sorted_entries), start=ZERO)),
            },
            "time_rows": [_serialize_cost_entry(entry) for entry in sorted_entries],
            "bank_accounts": self._bank_accounts_from_settings(),
            "project_rows": [
                {
                    "project_name": bucket["project_name"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": bucket["transaction_count"],
                    "expense_type_count": len(bucket["expense_types"]),
                }
                for bucket in sorted(project_groups.values(), key=lambda item: (-item["total_amount"], item["project_name"]))
            ],
            "expense_type_rows": [
                {
                    "expense_type": bucket["expense_type"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": bucket["transaction_count"],
                    "project_count": len(bucket["projects"]),
                }
                for bucket in sorted(expense_type_groups.values(), key=lambda item: (-item["total_amount"], item["expense_type"]))
            ],
        }

    def _cost_entries_from_workbench(self, month: str, *, project_scope: str) -> list[dict[str, Any]]:
        member_rows = self._connection.fetch_all(
            """
            with active_generation as (
                select generation_id
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and scope_key = %s
                  and status = 'active'
                order by activated_at desc nulls last, completed_at desc nulls last, updated_at desc
                limit 1
            )
            select
                g.group_id,
                g.zone,
                g.payload,
                g.raw_payload,
                gr.pane,
                gr.row_id,
                gr.row_role,
                gr.row_index,
                wr.payload as row_payload,
                wr.raw_payload as row_raw_payload,
                gr.payload as member_payload,
                gr.raw_payload as member_raw_payload
            from active_generation active
            join read_model.workbench_groups g
              on g.generation_id = active.generation_id
            join read_model.workbench_group_rows gr
              on gr.generation_id = g.generation_id
             and gr.scope_key = g.scope_key
             and gr.zone = g.zone
             and gr.group_id = g.group_id
            left join read_model.workbench_rows wr
              on wr.generation_id = gr.generation_id
             and wr.scope_key = gr.scope_key
             and wr.row_id = gr.row_id
            where g.scope_key = %s
              and g.zone in ('paired', 'open')
              and g.source_kinds && array['oa', 'bank']::text[]
              and gr.pane in ('oa', 'bank')
              and coalesce(gr.row_role, '') <> 'collapsed'
            order by g.bank_sort_max desc nulls last, g.group_id, gr.pane, gr.row_index, gr.row_id
            """,
            (month, month),
        )
        groups_by_id: dict[tuple[str, str], dict[str, Any]] = {}
        for row in member_rows:
            group_id = str(row.get("group_id") or "").strip()
            zone = str(row.get("zone") or "paired").strip().lower() or "paired"
            if not group_id:
                continue
            group_key = (zone, group_id)
            group_payload = groups_by_id.get(group_key)
            if group_payload is None:
                source_payload = row_payload(row, "payload", "raw_payload")
                group_payload = dict(source_payload) if isinstance(source_payload, dict) else {"group_id": group_id}
                group_payload["group_id"] = group_id
                group_payload["zone"] = zone
                group_payload.setdefault("oa_rows", [])
                group_payload.setdefault("bank_rows", [])
                groups_by_id[group_key] = group_payload
            pane = str(row.get("pane") or "").strip()
            if pane not in {"oa", "bank"}:
                continue
            payload = row_payload(row, "row_payload", "row_raw_payload", "member_payload", "member_raw_payload")
            member_payload = dict(payload) if isinstance(payload, dict) else {}
            row_id = str(row.get("row_id") or "").strip()
            if row_id:
                member_payload.setdefault("id", row_id)
                member_payload.setdefault("row_id", row_id)
            member_payload.setdefault("type", pane)
            group_payload.setdefault(f"{pane}_rows", []).append(member_payload)
        groups = []
        for group_payload in groups_by_id.values():
            if is_candidate_workbench_group(group_payload):
                continue
            zone = str(group_payload.get("zone") or "paired").strip().lower()
            if zone == "open" and not is_cost_eligible_open_group(group_payload):
                continue
            groups.append(group_payload)
        active_projects = self._active_project_names() if project_scope == "active" else None
        entries: list[dict[str, Any]] = []
        for group in groups:
            oa_rows = [row for row in list(group.get("oa_rows") or []) if isinstance(row, dict)]
            bank_rows = [row for row in list(group.get("bank_rows") or []) if isinstance(row, dict)]
            if not oa_rows or not bank_rows:
                continue
            context = _cost_context_from_oa_rows(oa_rows)
            if context is None:
                continue
            if active_projects is not None and context["project_name"] not in active_projects:
                continue
            for bank_row in bank_rows:
                amount = _outflow_amount(bank_row)
                if amount is None:
                    continue
                entries.append(
                    {
                        "group_id": str(group.get("group_id") or ""),
                        "transaction_id": str(bank_row.get("id") or bank_row.get("row_id") or ""),
                        "trade_time": str(bank_row.get("trade_time") or bank_row.get("date") or ""),
                        "counterparty_name": str(bank_row.get("counterparty_name") or ""),
                        "payment_account_label": str(bank_row.get("payment_account_label") or bank_row.get("bank_name") or ""),
                        "direction": str(bank_row.get("direction") or "支出"),
                        "remark": str(bank_row.get("remark") or ""),
                        "project_name": context["project_name"],
                        "project_id": context["project_id"],
                        "expense_type": context["expense_type"],
                        "expense_content": context["expense_content"],
                        "oa_applicant": context["oa_applicant"],
                        "amount_decimal": amount,
                        **bank_tag_context_from_row(bank_row),
                    }
                )
        return entries

    def _cost_entries_from_materialized_shards(self, *, project_scope: str) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select
                scope_key, project_scope, scope_month::text as scope_month, row_key, transaction_id,
                group_id, trade_time_text, trade_date::text as trade_date, counterparty_name,
                payment_account_label, direction, remark, project_id, project_name, expense_type,
                expense_content, amount::text as amount, oa_applicant, source_versions,
                generated_at::text as generated_at, cache_status, payload, raw_payload
            from read_model.cost_statistics_rows
            where project_scope = %s
              and scope_key <> %s
              and scope_key like %s
              and scope_month is not null
            order by trade_date desc nulls last, trade_time_text desc, transaction_id, row_key
            """,
            (project_scope, f"{project_scope}:all", f"{project_scope}:%"),
        )
        entries: list[dict[str, Any]] = []
        shard_versions: dict[str, Any] = {}
        for index, row in enumerate(rows):
            entry = _cost_entry_from_materialized_row(row, fallback_index=index)
            entries.append(entry)
            scope_key = str(row.get("scope_key") or "").strip()
            if scope_key and scope_key not in shard_versions:
                versions = row.get("source_versions")
                shard_versions[scope_key] = versions if isinstance(versions, dict) else {}
        return entries, shard_versions

    def _workbench_payload(self, month: str) -> dict[str, Any]:
        row = self._connection.fetch_one(
            """
            select payload, raw_payload
            from read_model.workbench_snapshots
            where scope_key = %s
            limit 1
            """,
            (month,),
        )
        payload = row_payload(row or {}, "payload", "raw_payload")
        if isinstance(payload, dict) and isinstance(payload.get("payload"), dict):
            return payload["payload"]
        return payload if isinstance(payload, dict) else {}

    def _active_project_names(self) -> set[str] | None:
        payload = _app_settings_payload(self._connection)
        if not payload:
            return None
        projects = payload.get("projects")
        if not isinstance(projects, list):
            return None
        active: set[str] = set()
        for project in projects:
            if not isinstance(project, dict):
                continue
            name = str(project.get("name") or project.get("project_name") or "").strip()
            enabled = project.get("active", project.get("enabled", True))
            if name and bool(enabled):
                active.add(name)
        return active or None

    def _bank_accounts_from_settings(self) -> list[dict[str, str]]:
        return bank_accounts_from_settings_payload(_app_settings_payload(self._connection))

    def _set_redis_json(self, key: str, value: dict[str, Any]) -> None:
        set_json = getattr(self._redis_helper, "set_json", None)
        if callable(set_json):
            set_json(key, value, ttl_seconds=120)


class TaxOffsetSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        tax_offset_read_model_repository: Any | None = None,
        redis_helper: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._tax_offset_read_model_repository = tax_offset_read_model_repository or TaxOffsetReadModelRepositoryPort(
            self._read_model_repository
        )
        self._redis_helper = redis_helper

    def list_tax_offset_scope_shards(self, scope_key: str) -> list[str]:
        normalized = str(scope_key or "").strip()
        if normalized != "all":
            return [normalized] if MONTH_RE.match(normalized) else []
        rows = self._connection.fetch_all(
            """
            select scope_key
            from (
                select distinct to_char(invoice_month, 'YYYY-MM') as scope_key
                from app.invoices
                where invoice_month is not null
                union
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from app.tax_certified_import_records
                where scope_month is not null
            ) scopes
            where scope_key is not null
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_RE.match(str(row.get("scope_key") or ""))]

    def rebuild_tax_offset_read_model_scope(self, scope_key: str) -> dict[str, object]:
        month = str(scope_key or "").strip()
        if not MONTH_RE.match(month):
            raise ValueError("tax offset SQL projection scope_key must be a month shard YYYY-MM.")
        payload = self._build_tax_payload(month)
        source_versions = self._source_versions()
        service = TaxOffsetReadModelService()
        read_model = service.upsert_read_model(
            month,
            payload,
            generated_at=datetime.now().isoformat(),
            source_scope_keys=[month],
            source_versions=source_versions,
            cache_status="ready",
        )
        warmed_scope_key = str(read_model["scope_key"])
        self._tax_offset_read_model_repository.save_tax_offset_read_models(
            service.snapshot_scope_keys([warmed_scope_key]),
            changed_scope_keys={warmed_scope_key},
        )
        self._set_redis_json(
            f"tax_offset:month:{warmed_scope_key}",
            build_fresh_cache_envelope(
                {
                    **payload,
                    "read_model_status": "fresh",
                    "read_model_scope_key": warmed_scope_key,
                    "source_versions": source_versions,
                },
                scope_key=warmed_scope_key,
                source_versions=source_versions,
                schema_version=TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            ),
        )
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "entry_count": sum(len(payload.get(key) or []) for key in ("output_items", "input_plan_items", "certified_items")),
        }

    def _source_versions(self) -> dict[str, Any]:
        return {
            "tax_offset_read_model_schema_version": TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
            "invoice_fact_source_version": self._table_source_version("app.invoices", "status <> 'deleted'"),
            "tax_certified_import_source_version": self._table_source_version("app.tax_certified_import_records", "status <> 'deleted'"),
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }

    def _table_source_version(self, table_name: str, where_sql: str) -> str:
        try:
            row = self._connection.fetch_one(
                f"select count(*) as row_count, max(updated_at)::text as max_updated_at from {table_name} where {where_sql}"
            )
        except Exception:
            return "unavailable"
        if not isinstance(row, dict):
            return "rows:0|max_updated_at:"
        return f"rows:{row.get('row_count') or 0}|max_updated_at:{row.get('max_updated_at') or ''}"

    def _build_tax_payload(self, month: str) -> dict[str, Any]:
        month_data = {
            month: {
                "output_items": self._invoice_items(month, output=True),
                "input_plan_items": self._invoice_items(month, output=False),
            }
        }
        service = TaxOffsetService(
            month_data=month_data,
            certified_records_loader=lambda requested_month: self._certified_items(requested_month),
        )
        return service.get_month_payload(month)

    def _invoice_items(self, month: str, *, output: bool) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
                   digital_invoice_no, invoice_date, seller_name, seller_tax_no, buyer_name, buyer_tax_no,
                   tax_amount, total_with_tax, amount, tax_rate, raw_payload
            from app.invoices
            where invoice_month = %s::date
              and status <> 'deleted'
              and (
                (%s and (invoice_type ilike '%%output%%' or invoice_type like '%%销%%'))
                or (not %s and not (invoice_type ilike '%%output%%' or invoice_type like '%%销%%'))
              )
            order by invoice_date nulls last, row_id
            """,
            (month_start(month), output, output),
        )
        return [_tax_invoice_item(row, output=output) for row in rows]

    def _certified_items(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select certified_unique_key, invoice_no, invoice_code, digital_invoice_no, seller_name, seller_tax_no,
                   invoice_date, amount, tax_amount, status, raw_payload
            from app.tax_certified_import_records
            where scope_month = %s::date
              and status <> 'deleted'
            order by invoice_date nulls last, certified_unique_key
            """,
            (month_start(month),),
        )
        return [
            {
                **(row_payload(row, "raw_payload") if isinstance(row_payload(row, "raw_payload"), dict) else {}),
                "id": str(row.get("certified_unique_key") or ""),
                "unique_key": row.get("certified_unique_key"),
                "invoice_no": row.get("invoice_no"),
                "invoice_code": row.get("invoice_code"),
                "digital_invoice_no": row.get("digital_invoice_no"),
                "seller_name": row.get("seller_name"),
                "seller_tax_no": row.get("seller_tax_no"),
                "issue_date": str(row.get("invoice_date") or ""),
                "amount": _money(row.get("amount")),
                "tax_amount": _money(row.get("tax_amount")),
                "status": row.get("status") or "已认证",
            }
            for row in rows
        ]

    def _set_redis_json(self, key: str, value: dict[str, Any]) -> None:
        set_json = getattr(self._redis_helper, "set_json", None)
        if callable(set_json):
            set_json(key, value, ttl_seconds=120)


def _parse_cost_scope_key(scope_key: str) -> tuple[str, str]:
    raw = str(scope_key or "").strip()
    if ":" not in raw:
        raise ValueError("cost statistics SQL projection scope_key must use project_scope:month.")
    project_scope, month = raw.split(":", 1)
    project_scope = project_scope.strip().lower()
    month = month.strip()
    if project_scope not in PROJECT_SCOPES:
        raise ValueError("cost statistics project_scope must be active or all.")
    if month != "all" and not MONTH_RE.match(month):
        raise ValueError("cost statistics month must be all or YYYY-MM.")
    return project_scope, month


def _current_bank_auto_tag_rules_version(connection: Any) -> int:
    return bank_auto_tag_rules_version_from_settings_payload(_app_settings_payload(connection))


def _app_settings_payload(connection: Any) -> dict[str, Any]:
    try:
        row = connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s limit 1",
            ("app_settings",),
        )
    except Exception:
        return {}
    payload = row.get("settings_payload") if isinstance(row, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _cost_context_from_oa_rows(oa_rows: list[dict[str, Any]]) -> dict[str, str] | None:
    contexts: set[tuple[str, str, str, str, str]] = set()
    for row in oa_rows:
        detail_fields = row.get("detail_fields") if isinstance(row.get("detail_fields"), dict) else {}
        project_name = _clean_text(row.get("project_name")) or _clean_text(detail_fields.get("项目名称"))
        project_id = _clean_text(row.get("project_id")) or _clean_text(detail_fields.get("项目编号"))
        expense_type = _clean_text(row.get("expense_type")) or _clean_text(detail_fields.get("费用类型"))
        expense_content = _clean_text(row.get("expense_content")) or _clean_text(row.get("reason")) or _clean_text(detail_fields.get("费用内容"))
        applicant = _clean_text(row.get("applicant")) or _clean_text(detail_fields.get("申请人"))
        if expense_type in {"借款", "还款"}:
            continue
        if project_name and expense_type and expense_content:
            contexts.add((project_name, project_id, expense_type, expense_content, applicant))
    if len(contexts) != 1:
        return None
    project_name, project_id, expense_type, expense_content, applicant = next(iter(contexts))
    return {
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": expense_type,
        "expense_content": expense_content,
        "oa_applicant": applicant or "—",
    }


def _outflow_amount(bank_row: dict[str, Any]) -> Decimal | None:
    direction = str(bank_row.get("direction") or bank_row.get("txn_direction") or "").strip().lower()
    if direction and not any(token in direction for token in ("out", "支出", "付款", "debit")):
        return None
    amount = _decimal(bank_row.get("debit_amount") or bank_row.get("amount"))
    if amount in (None, ZERO):
        return None
    return abs(amount)


def _serialize_cost_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bank_tag_context = bank_tag_context_from_row(entry)
    return {
        "transaction_id": entry["transaction_id"],
        "trade_time": entry["trade_time"],
        "direction": entry["direction"],
        "project_name": entry["project_name"],
        "expense_type": entry["expense_type"],
        "expense_content": entry["expense_content"],
        "amount": format_decimal(entry["amount_decimal"]),
        "counterparty_name": entry["counterparty_name"],
        "payment_account_label": entry["payment_account_label"],
        "remark": entry["remark"],
        "oa_applicant": entry["oa_applicant"],
        **bank_tag_context,
    }


def _cost_entry_from_materialized_row(row: dict[str, Any], *, fallback_index: int) -> dict[str, Any]:
    payload = row_payload(row, "payload", "raw_payload")
    if not isinstance(payload, dict):
        payload = {}
    amount = _decimal(row.get("amount") or payload.get("amount")) or ZERO
    transaction_id = str(row.get("transaction_id") or payload.get("transaction_id") or f"row-{fallback_index}")
    return {
        "group_id": str(row.get("group_id") or payload.get("group_id") or ""),
        "transaction_id": transaction_id,
        "trade_time": str(row.get("trade_time_text") or payload.get("trade_time") or row.get("trade_date") or ""),
        "counterparty_name": str(row.get("counterparty_name") or payload.get("counterparty_name") or ""),
        "payment_account_label": str(row.get("payment_account_label") or payload.get("payment_account_label") or ""),
        "direction": str(row.get("direction") or payload.get("direction") or "支出"),
        "remark": str(row.get("remark") or payload.get("remark") or ""),
        "project_name": str(row.get("project_name") or payload.get("project_name") or "未归集项目"),
        "project_id": str(row.get("project_id") or payload.get("project_id") or ""),
        "expense_type": str(row.get("expense_type") or payload.get("expense_type") or "未分类"),
        "expense_content": str(row.get("expense_content") or payload.get("expense_content") or ""),
        "oa_applicant": str(row.get("oa_applicant") or payload.get("oa_applicant") or "—"),
        "amount_decimal": amount,
        **bank_tag_context_from_row(payload),
    }


def _tax_invoice_item(row: dict[str, Any], *, output: bool) -> dict[str, Any]:
    common = {
        "id": str(row.get("row_id") or ""),
        "issue_date": str(row.get("invoice_date") or ""),
        "invoice_no": row.get("invoice_no"),
        "invoice_code": row.get("invoice_code"),
        "digital_invoice_no": row.get("digital_invoice_no"),
        "tax_amount": _money(row.get("tax_amount")),
        "total_with_tax": _money(row.get("total_with_tax") or ((_decimal(row.get("amount")) or ZERO) + (_decimal(row.get("tax_amount")) or ZERO))),
        "invoice_type": "销项发票" if output else "进项发票",
        "tax_rate": row.get("tax_rate") or "—",
    }
    if output:
        return {
            **common,
            "buyer_name": row.get("buyer_name") or "",
            "buyer_tax_no": row.get("buyer_tax_no"),
        }
    return {
        **common,
        "seller_name": row.get("seller_name") or "",
        "seller_tax_no": row.get("seller_tax_no"),
        "risk_level": (row_payload(row, "raw_payload") if isinstance(row_payload(row, "raw_payload"), dict) else {}).get("risk_level") or "待评估",
    }


def _clean_text(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    return "" if text in {"-", "--", "—", "——"} else text


def _decimal(value: Any) -> Decimal | None:
    if value in (None, "", "—", "--"):
        return None
    try:
        return Decimal(str(value).replace(",", "").strip())
    except (InvalidOperation, ValueError):
        return None


def _money(value: Any) -> str:
    amount = _decimal(value)
    return format_decimal(amount or ZERO)
