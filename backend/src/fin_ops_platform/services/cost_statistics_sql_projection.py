from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any, Callable

from fin_ops_platform.services.cost_statistics_bank_accounts import (
    bank_accounts_from_settings_payload,
    bank_auto_tag_rules_version_from_settings_payload,
)
from fin_ops_platform.services.cost_statistics_bank_tags import bank_tag_context_from_row
from fin_ops_platform.services.cost_statistics_read_model_repository import CostStatisticsReadModelRepositoryPort
from fin_ops_platform.services.cost_statistics_source_versions import (
    COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
    cost_statistics_source_versions,
)
from fin_ops_platform.services.live_workbench_service import format_decimal
from fin_ops_platform.services.postgres_repositories.common import row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    is_completed_workflow_status,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.read_model_freshness import (
    require_expected_source_versions,
    source_version_mismatch_reasons,
)
from fin_ops_platform.services.workbench_sql_projection import WorkbenchSqlProjectionBuilder

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
ZERO = Decimal("0.00")
MONEY_QUANTUM = Decimal("0.01")
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"
UNATTRIBUTED_PROJECT_NAME = "未归集项目"
UNCATEGORIZED_EXPENSE_TYPE = "未分类"
MULTI_PROJECT_NAME = "多项目"
MULTI_EXPENSE_TYPE = "多费用类型"


class CostStatisticsSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        bank_transaction_tag_read_facade: Any | None = None,
        workbench_dependency_versions_provider: Callable[
            [str], tuple[dict[str, object], dict[str, object]]
        ]
        | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = CostStatisticsReadModelRepositoryPort(
            read_model_repository or PostgresReadModelRepository(connection)
        )
        self._bank_transaction_tag_read_facade = bank_transaction_tag_read_facade
        self._workbench_dependency_versions_provider = (
            workbench_dependency_versions_provider
            or self._current_workbench_dependency_versions
        )
        self._settings_payload_cache: dict[str, Any] | None = None

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

    def rebuild_cost_statistics_read_model_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month == "all":
            return self.rebuild_cost_statistics_parent_scope(
                scope_key,
                tenant_id=tenant_id,
                source_version=source_version,
                force_refresh=force_refresh,
            )
        return self.rebuild_cost_statistics_month_scope(
            scope_key,
            tenant_id=tenant_id,
            source_version=source_version,
            force_refresh=force_refresh,
        )

    def rebuild_cost_statistics_month_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        self._settings_payload_cache = None
        try:
            project_scope, month = _parse_cost_scope_key(scope_key)
            if month == "all":
                raise ValueError("month scope rebuild requires a concrete YYYY-MM scope.")
            self._require_fresh_workbench_dependency(month)
            workbench_groups = self._cost_groups_from_workbench(month)
            bank_detail_payload = self._bank_detail_snapshot_payload(
                month,
                include_transaction_ids=_bank_transaction_ids_from_groups(workbench_groups),
            )
            source_versions = self._source_versions(month, bank_detail_payload=bank_detail_payload)
            if not force_refresh:
                unchanged = self._unchanged_cost_statistics_scope_result(
                    scope_key=f"{project_scope}:{month}",
                    month=month,
                    project_scope=project_scope,
                    source_versions=source_versions,
                    refresh_kind="month",
                    tenant_id=tenant_id,
                    source_version=source_version,
                )
                if unchanged is not None:
                    return unchanged
            payload = self._build_explorer_payload(
                month,
                project_scope=project_scope,
                workbench_groups=workbench_groups,
                bank_detail_payload=bank_detail_payload,
            )
            return self._publish_cost_statistics_scope(
                month=month,
                project_scope=project_scope,
                payload=payload,
                source_versions=source_versions,
                refresh_kind="month",
                tenant_id=tenant_id,
                source_version=source_version,
            )
        finally:
            self._settings_payload_cache = None

    def _current_workbench_dependency_versions(
        self,
        scope_key: str,
    ) -> tuple[dict[str, object], dict[str, object]]:
        expected = WorkbenchSqlProjectionBuilder(
            connection=self._connection
        ).source_versions_for_scope(scope_key)
        actual = self._read_model_repository.active_workbench_source_versions(
            scope_key=scope_key
        )
        return expected, actual

    def _require_fresh_workbench_dependency(self, scope_key: str) -> None:
        expected, actual = self._workbench_dependency_versions_provider(scope_key)
        expected = require_expected_source_versions(
            expected,
            context=f"cost_statistics_workbench_dependency:{scope_key}",
        )
        if source_version_mismatch_reasons(expected=expected, actual=actual):
            raise RuntimeError(
                "workbench_read_model_not_fresh: "
                f"operation=cost_statistics_month_projection status=stale scope_keys={scope_key}"
            )

    def rebuild_cost_statistics_parent_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        self._settings_payload_cache = None
        try:
            project_scope, month = _parse_cost_scope_key(scope_key)
            if month != "all":
                raise ValueError("parent scope rebuild requires an all scope.")
            obsolete_scope_keys = self._obsolete_cost_statistics_month_scopes(project_scope=project_scope)
            shard_versions = self._cost_statistics_shard_versions(project_scope=project_scope)
            payload = self._cost_statistics_parent_metadata_payload(
                project_scope=project_scope,
                scope_keys=list(shard_versions),
            )
            source_versions = {
                **self._source_versions("all"),
                "cost_statistics_parent_source": "materialized_shards",
                "source_shard_count": len(shard_versions),
                "source_shards": shard_versions,
            }
            if not force_refresh:
                unchanged = self._unchanged_cost_statistics_scope_result(
                    scope_key=f"{project_scope}:all",
                    month="all",
                    project_scope=project_scope,
                    source_versions=source_versions,
                    refresh_kind="parent",
                    tenant_id=tenant_id,
                    source_version=source_version,
                )
                if unchanged is not None and not obsolete_scope_keys:
                    return unchanged
            return self._publish_cost_statistics_scope(
                month="all",
                project_scope=project_scope,
                payload=payload,
                source_versions=source_versions,
                refresh_kind="parent",
                tenant_id=tenant_id,
                source_version=source_version,
                obsolete_scope_keys=obsolete_scope_keys,
            )
        finally:
            self._settings_payload_cache = None

    def _obsolete_cost_statistics_month_scopes(self, *, project_scope: str) -> set[str]:
        current_scope_keys = set(self.list_cost_statistics_scope_shards(f"{project_scope}:all"))
        rows = self._connection.fetch_all(
            """
            select scope_key
            from read_model.cost_statistics_read_models
            where project_scope = %s
              and scope_key ~ '^(active|all):[0-9]{4}-[0-9]{2}$'
            order by scope_key
            """,
            (project_scope,),
        )
        return {
            str(row.get("scope_key") or "").strip()
            for row in rows
            if str(row.get("scope_key") or "").strip()
            and str(row.get("scope_key") or "").strip() not in current_scope_keys
        }

    def _publish_cost_statistics_scope(
        self,
        *,
        month: str,
        project_scope: str,
        payload: dict[str, Any],
        source_versions: dict[str, Any],
        refresh_kind: str,
        tenant_id: str,
        source_version: int,
        obsolete_scope_keys: set[str] | None = None,
    ) -> dict[str, object]:
        warmed_scope_key = f"{project_scope}:{month}"
        entry_count = int(
            (payload.get("summary") or {}).get("row_count")
            if month == "all" and isinstance(payload.get("summary"), dict)
            else len(payload.get("time_rows") or [])
        )
        snapshot = {
            "read_models": {
                warmed_scope_key: {
                    "scope_key": warmed_scope_key,
                    "scope_type": "all_time" if month == "all" else "month",
                    "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                    "month": month,
                    "project_scope": project_scope,
                    "generated_at": datetime.now(UTC).isoformat(),
                    "cache_status": "ready",
                    "entry_count": entry_count,
                    "payload": payload,
                    "source_scope_keys": [month],
                    "source_versions": source_versions,
                }
            }
        }
        published = self._read_model_repository.publish_cost_statistics_read_models(
            snapshot,
            tenant_id=tenant_id,
            scope_key=warmed_scope_key,
            source_version=source_version,
            changed_scope_keys={warmed_scope_key, *(obsolete_scope_keys or set())},
        )
        if not published:
            return {
                "scope_key": warmed_scope_key,
                "month": month,
                "project_scope": project_scope,
                "published": False,
                "skipped": True,
                "skip_reason": "stale_source_version_at_publish",
                "source_version": source_version,
                "refresh_kind": refresh_kind,
            }
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "project_scope": project_scope,
            "entry_count": entry_count,
            "row_count": entry_count,
            "source_shard_count": source_versions.get("source_shard_count"),
            "refresh_kind": refresh_kind,
            "source_version": source_version,
            "published": True,
        }

    def _source_versions(
        self,
        month: str,
        *,
        bank_detail_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        settings_payload = self._settings_payload()
        workbench_source_versions = self._workbench_source_versions(month) if month != "all" else None
        bank_detail_source_versions = (
            self._bank_detail_source_versions(bank_detail_payload, scope_key=month)
            if month != "all"
            else None
        )
        return cost_statistics_source_versions(
            month=month,
            settings_payload=settings_payload,
            workbench_source_versions=workbench_source_versions,
            bank_detail_source_versions=bank_detail_source_versions,
        )

    def _bank_detail_snapshot_payload(
        self,
        month: str,
        *,
        include_transaction_ids: list[str],
    ) -> dict[str, Any] | None:
        facade = self._bank_transaction_tag_read_facade
        snapshot_for_month = getattr(facade, "snapshot_for_month", None)
        if not callable(snapshot_for_month) or month == "all":
            return None
        payload = snapshot_for_month(
            month,
            include_transaction_ids=include_transaction_ids,
            require_fresh=False,
            reason="downstream_bank_tag_read",
        )
        if not isinstance(payload, dict) or str(payload.get("status") or "").strip().lower() != "fresh":
            raise RuntimeError(_bank_detail_not_fresh_error(payload, operation="month_snapshot", month=month))
        return payload

    @staticmethod
    def _bank_detail_source_versions(
        payload: dict[str, Any] | None,
        *,
        scope_key: str,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None
        scope_signatures = payload.get("read_model_scope_signatures")
        if isinstance(scope_signatures, dict):
            scope_signature = scope_signatures.get(scope_key)
            if isinstance(scope_signature, dict):
                scope_source_versions = scope_signature.get("source_versions")
                if isinstance(scope_source_versions, dict):
                    return dict(scope_source_versions)
        source_versions = payload.get("source_versions")
        return dict(source_versions) if isinstance(source_versions, dict) else {}

    def _workbench_source_versions(self, scope_key: str) -> dict[str, Any]:
        return self._read_model_repository.active_workbench_source_versions(scope_key=scope_key)

    def _unchanged_cost_statistics_scope_result(
        self,
        *,
        scope_key: str,
        month: str,
        project_scope: str,
        source_versions: dict[str, Any],
        refresh_kind: str,
        tenant_id: str,
        source_version: int,
    ) -> dict[str, object] | None:
        try:
            metadata = self._read_model_repository.get_cost_statistics_scope_metadata(scope_key=scope_key)
        except AttributeError:
            return None
        if not isinstance(metadata, dict):
            return None
        if month == "all" and metadata.get("statistics_ready") is not True:
            return None
        existing_source_versions = metadata.get("source_versions")
        if not isinstance(existing_source_versions, dict) or existing_source_versions != source_versions:
            return None
        entry_count = int(metadata.get("entry_count") or 0)
        acknowledged = self._read_model_repository.acknowledge_unchanged_cost_statistics_scope(
            tenant_id=tenant_id,
            scope_key=scope_key,
            source_version=source_version,
            source_versions=source_versions,
        )
        if not acknowledged:
            return {
                "scope_key": scope_key,
                "month": month,
                "project_scope": project_scope,
                "entry_count": entry_count,
                "row_count": entry_count,
                "source_versions": source_versions,
                "source_version": source_version,
                "refresh_kind": refresh_kind,
                "published": False,
                "skipped": True,
                "skip_reason": "stale_source_version_at_unchanged_ack",
            }
        return {
            "scope_key": scope_key,
            "month": month,
            "project_scope": project_scope,
            "entry_count": entry_count,
            "row_count": entry_count,
            "source_versions": source_versions,
            "source_version": source_version,
            "refresh_kind": refresh_kind,
            "published": True,
            "skipped_rebuild": True,
            "skip_reason": "source_versions_unchanged",
        }

    def _build_explorer_payload(
        self,
        month: str,
        *,
        project_scope: str,
        workbench_groups: list[dict[str, Any]],
        bank_detail_payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        bank_detail_rows = [
            row
            for row in list((bank_detail_payload or {}).get("rows") or [])
            if isinstance(row, dict)
        ]
        entries = self._cost_entries_from_workbench(
            workbench_groups,
            month=month,
            project_scope=project_scope,
            bank_detail_rows=bank_detail_rows,
        )
        return self._build_explorer_payload_from_entries(
            entries,
            month=month,
            project_scope=project_scope,
        )

    def _build_explorer_payload_from_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        month: str,
        project_scope: str,
    ) -> dict[str, Any]:
        sorted_entries = sorted(
            entries,
            key=lambda item: (
                str(item["trade_time"]),
                str(item["transaction_id"]),
                str(item.get("row_key") or ""),
            ),
            reverse=True,
        )
        project_groups: dict[str, dict[str, Any]] = {}
        expense_type_groups: dict[str, dict[str, Any]] = {}
        for entry in sorted_entries:
            project_bucket = project_groups.setdefault(
                entry["project_name"],
                {
                    "project_name": entry["project_name"],
                    "total_amount": ZERO,
                    "transaction_ids": set(),
                    "expense_types": set(),
                },
            )
            project_bucket["total_amount"] += entry["amount_decimal"]
            project_bucket["transaction_ids"].add(entry["transaction_id"])
            project_bucket["expense_types"].add(entry["expense_type"])
            expense_bucket = expense_type_groups.setdefault(
                entry["expense_type"],
                {
                    "expense_type": entry["expense_type"],
                    "total_amount": ZERO,
                    "transaction_ids": set(),
                    "projects": set(),
                },
            )
            expense_bucket["total_amount"] += entry["amount_decimal"]
            expense_bucket["transaction_ids"].add(entry["transaction_id"])
            expense_bucket["projects"].add(entry["project_name"])
        transaction_ids = {str(entry["transaction_id"]) for entry in sorted_entries}
        return {
            "month": month,
            "project_scope": project_scope,
            "summary": {
                "row_count": len(sorted_entries),
                "transaction_count": len(transaction_ids),
                "total_amount": format_decimal(sum((entry["amount_decimal"] for entry in sorted_entries), start=ZERO)),
            },
            "time_rows": [_serialize_cost_entry(entry) for entry in sorted_entries],
            "bank_accounts": self._bank_accounts_from_settings(),
            "project_rows": [
                {
                    "project_name": bucket["project_name"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": len(bucket["transaction_ids"]),
                    "expense_type_count": len(bucket["expense_types"]),
                }
                for bucket in sorted(project_groups.values(), key=lambda item: (-item["total_amount"], item["project_name"]))
            ],
            "expense_type_rows": [
                {
                    "expense_type": bucket["expense_type"],
                    "total_amount": format_decimal(bucket["total_amount"]),
                    "transaction_count": len(bucket["transaction_ids"]),
                    "project_count": len(bucket["projects"]),
                }
                for bucket in sorted(expense_type_groups.values(), key=lambda item: (-item["total_amount"], item["expense_type"]))
            ],
        }

    def _cost_groups_from_workbench(
        self,
        month: str,
    ) -> list[dict[str, Any]]:
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
                g.group_type,
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
              and g.zone in ('paired', 'unpaired')
              and g.group_type = 'relation'
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
        return list(groups_by_id.values())

    def _cost_entries_from_workbench(
        self,
        groups: list[dict[str, Any]],
        *,
        month: str,
        project_scope: str,
        bank_detail_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        bank_tag_contexts = self._bank_tag_contexts_for_rows(
            [
                row
                for group in groups
                if list(group.get("oa_rows") or []) and list(group.get("bank_rows") or [])
                for row in list(group.get("bank_rows") or [])
                if isinstance(row, dict)
            ],
            bank_detail_rows=bank_detail_rows,
        )
        completed_project_ids, completed_project_names = (
            self._completed_project_identities() if project_scope == "active" else (set(), set())
        )
        entries: list[dict[str, Any]] = []
        bank_detail_rows_by_id = {
            transaction_id: row
            for row in bank_detail_rows
            for transaction_id in [
                str(row.get("transaction_id") or row.get("id") or row.get("row_id") or "").strip()
            ]
            if transaction_id
        }
        for group in groups:
            oa_rows = [row for row in list(group.get("oa_rows") or []) if isinstance(row, dict)]
            bank_rows = [
                row
                for row in list(group.get("bank_rows") or [])
                if isinstance(row, dict)
                and (
                    month == "all"
                    or _bank_row_native_month(row, bank_detail_rows_by_id=bank_detail_rows_by_id) == month
                )
            ]
            if not oa_rows or not bank_rows:
                continue
            special_metadata = _group_special_metadata(group)
            special_policy = _clean_text(special_metadata.get("cost_policy"))
            if special_policy == "include_ticket_cost_only":
                ticket_entry = _cash_ticket_cost_entry(
                    group,
                    oa_rows=oa_rows,
                    bank_rows=bank_rows,
                    special_metadata=special_metadata,
                    bank_tag_contexts=bank_tag_contexts,
                )
                if ticket_entry is not None and not _is_completed_project_allocation(
                    ticket_entry,
                    completed_project_ids=completed_project_ids,
                    completed_project_names=completed_project_names,
                ):
                    entries.append(ticket_entry)
                continue
            for entry in _oa_cost_entries_for_group(
                group,
                oa_rows=oa_rows,
                bank_rows=bank_rows,
                bank_tag_contexts=bank_tag_contexts,
            ):
                if not _is_completed_project_allocation(
                    entry,
                    completed_project_ids=completed_project_ids,
                    completed_project_names=completed_project_names,
                ):
                    entries.append(entry)
        return entries

    def _bank_tag_contexts_for_rows(
        self,
        bank_rows: list[dict[str, Any]],
        *,
        bank_detail_rows: list[dict[str, Any]],
    ) -> dict[str, dict[str, Any]]:
        requested_ids = {
            transaction_id
            for row in bank_rows
            for transaction_id in [str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()]
            if transaction_id
        }
        return {
            transaction_id: bank_tag_context_from_row(row)
            for row in bank_detail_rows
            for transaction_id in [str(row.get("transaction_id") or row.get("id") or "").strip()]
            if transaction_id in requested_ids
        }

    def _cost_statistics_shard_versions(self, *, project_scope: str) -> dict[str, Any]:
        rows = self._connection.fetch_all(
            """
            select scope_key, source_versions
            from read_model.cost_statistics_read_models
            where project_scope = %s
              and scope_key <> %s
              and scope_key like %s
              and scope_month is not null
            order by scope_key
            """,
            (project_scope, f"{project_scope}:all", f"{project_scope}:%"),
        )
        return {
            scope_key: row.get("source_versions") if isinstance(row.get("source_versions"), dict) else {}
            for row in rows
            for scope_key in [str(row.get("scope_key") or "").strip()]
            if scope_key
        }

    def _cost_statistics_parent_metadata_payload(
        self,
        *,
        project_scope: str,
        scope_keys: list[str],
    ) -> dict[str, Any]:
        payload = self._read_model_repository.cost_statistics_aggregate_payload(
            project_scope=project_scope,
            scope_keys=scope_keys,
            bank_accounts=self._bank_accounts_from_settings(),
        )
        payload["month"] = "all"
        return payload

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

    def _completed_project_identities(self) -> tuple[set[str], set[str]]:
        payload = self._settings_payload()
        projects = payload.get("projects")
        if not isinstance(projects, dict):
            return set(), set()
        completed_ids = {
            _clean_text(project_id)
            for project_id in list(projects.get("completed_project_ids") or [])
            if _clean_text(project_id)
        }
        completed_names: set[str] = set()
        for project in list(projects.get("completed") or []):
            if not isinstance(project, dict):
                continue
            project_id = _clean_text(project.get("id"))
            project_name = _clean_text(project.get("project_name") or project.get("name"))
            if project_id:
                completed_ids.add(project_id)
            if project_name:
                completed_names.add(project_name)
        return completed_ids, completed_names

    def _bank_accounts_from_settings(self) -> list[dict[str, str]]:
        return bank_accounts_from_settings_payload(self._settings_payload())

    def _settings_payload(self) -> dict[str, Any]:
        if self._settings_payload_cache is None:
            self._settings_payload_cache = _app_settings_payload(self._connection)
        return dict(self._settings_payload_cache)

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


def _oa_cost_entries_for_group(
    group: dict[str, Any],
    *,
    oa_rows: list[dict[str, Any]],
    bank_rows: list[dict[str, Any]],
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> list[dict[str, Any]]:
    eligible_oa_rows = [row for row in oa_rows if _is_completed_oa_cost_row(row)]
    contexts = [
        _oa_cost_context(row, fallback_index=index)
        for index, row in enumerate(eligible_oa_rows)
    ]
    outflows = [
        (bank_row, amount)
        for bank_row in bank_rows
        if (amount := _outflow_amount(bank_row)) is not None
    ]
    if not contexts or not outflows:
        return []

    project_names = {str(context["project_name"]) for context in contexts}
    expense_types = {str(context["expense_type"]) for context in contexts}
    dimensions_differ = len(project_names) > 1 or len(expense_types) > 1
    exact_split = (
        len(outflows) == 1
        and len(contexts) > 1
        and dimensions_differ
        and all(context["allocation_amount"] is not None for context in contexts)
        and sum(
            (context["allocation_amount"] for context in contexts),
            start=ZERO,
        ).quantize(MONEY_QUANTUM)
        == outflows[0][1].quantize(MONEY_QUANTUM)
    )
    if exact_split:
        bank_row, _bank_amount = outflows[0]
        return [
            _cost_entry(
                group,
                bank_row=bank_row,
                context=context,
                amount=context["allocation_amount"],
                row_key_suffix=f"oa:{context['oa_id']}",
                bank_tag_contexts=bank_tag_contexts,
            )
            for context in contexts
        ]

    context = _fallback_cost_context(contexts)
    return [
        _cost_entry(
            group,
            bank_row=bank_row,
            context=context,
            amount=amount,
            row_key_suffix="full",
            bank_tag_contexts=bank_tag_contexts,
        )
        for bank_row, amount in outflows
    ]


def _oa_cost_context(row: dict[str, Any], *, fallback_index: int) -> dict[str, Any]:
    detail_fields = row.get("detail_fields") if isinstance(row.get("detail_fields"), dict) else {}
    project_name = (
        _clean_text(row.get("project_name"))
        or _clean_text(detail_fields.get("项目名称"))
        or UNATTRIBUTED_PROJECT_NAME
    )
    project_id = _clean_text(row.get("project_id")) or _clean_text(detail_fields.get("项目编号"))
    expense_type = (
        _clean_text(row.get("expense_type"))
        or _clean_text(detail_fields.get("费用类型"))
        or UNCATEGORIZED_EXPENSE_TYPE
    )
    expense_content = (
        _clean_text(row.get("expense_content"))
        or _clean_text(row.get("reason"))
        or _clean_text(detail_fields.get("费用内容"))
        or expense_type
    )
    applicant = _clean_text(row.get("applicant")) or _clean_text(detail_fields.get("申请人"))
    allocation_amount = _decimal(row.get("reconciliation_amount"))
    if allocation_amount is None or allocation_amount <= ZERO:
        allocation_amount = _decimal(row.get("amount"))
    if allocation_amount is not None and allocation_amount <= ZERO:
        allocation_amount = None
    oa_id = _clean_text(row.get("id") or row.get("row_id")) or f"index-{fallback_index}"
    return {
        "oa_id": oa_id,
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": expense_type,
        "expense_content": expense_content,
        "oa_applicant": applicant or "—",
        "allocation_amount": allocation_amount.quantize(MONEY_QUANTUM)
        if allocation_amount is not None
        else None,
    }


def _fallback_cost_context(contexts: list[dict[str, Any]]) -> dict[str, Any]:
    project_names = {str(context["project_name"]) for context in contexts}
    project_ids = {
        str(context["project_id"])
        for context in contexts
        if str(context["project_id"])
    }
    expense_types = {str(context["expense_type"]) for context in contexts}
    if len(project_names) == 1:
        project_name = next(iter(project_names))
        project_id = next(iter(project_ids)) if len(project_ids) == 1 else ""
    else:
        project_id, project_name = "", MULTI_PROJECT_NAME
    return {
        "project_name": project_name,
        "project_id": project_id,
        "expense_type": next(iter(expense_types)) if len(expense_types) == 1 else MULTI_EXPENSE_TYPE,
        "expense_content": _join_unique_text(context["expense_content"] for context in contexts)
        or UNCATEGORIZED_EXPENSE_TYPE,
        "oa_applicant": _join_unique_text(context["oa_applicant"] for context in contexts) or "—",
        "source_project_contexts": [
            {"project_id": context["project_id"], "project_name": context["project_name"]}
            for context in contexts
        ],
    }


def _cost_entry(
    group: dict[str, Any],
    *,
    bank_row: dict[str, Any],
    context: dict[str, Any],
    amount: Decimal,
    row_key_suffix: str,
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    transaction_id = str(
        bank_row.get("id") or bank_row.get("transaction_id") or bank_row.get("row_id") or ""
    ).strip()
    return {
        "row_key": f"{transaction_id}:{row_key_suffix}",
        "group_id": str(group.get("group_id") or ""),
        "transaction_id": transaction_id,
        "trade_time": str(
            bank_row.get("trade_time")
            or bank_row.get("pay_receive_time")
            or bank_row.get("date")
            or ""
        ),
        "counterparty_name": str(bank_row.get("counterparty_name") or ""),
        "payment_account_label": str(
            bank_row.get("payment_account_label") or bank_row.get("bank_name") or ""
        ),
        "direction": str(bank_row.get("direction") or "支出"),
        "remark": str(bank_row.get("remark") or ""),
        "project_name": str(context["project_name"]),
        "project_id": str(context["project_id"]),
        "expense_type": str(context["expense_type"]),
        "expense_content": str(context["expense_content"]),
        "oa_applicant": str(context["oa_applicant"]),
        "amount_decimal": amount.quantize(MONEY_QUANTUM),
        **(
            {"source_project_contexts": list(context["source_project_contexts"])}
            if isinstance(context.get("source_project_contexts"), list)
            else {}
        ),
        **(bank_tag_contexts.get(transaction_id) or bank_tag_context_from_row({})),
    }


def _join_unique_text(values: Any) -> str:
    return "、".join(sorted({_clean_text(value) for value in values if _clean_text(value)}))


def _outflow_amount(bank_row: dict[str, Any]) -> Decimal | None:
    direction = str(bank_row.get("direction") or bank_row.get("txn_direction") or "").strip().lower()
    if direction and not any(token in direction for token in ("out", "支出", "付款", "debit")):
        return None
    credit_amount = _decimal(bank_row.get("credit_amount"))
    if credit_amount not in (None, ZERO):
        return None
    amount = _decimal(bank_row.get("debit_amount") or bank_row.get("amount"))
    if amount in (None, ZERO):
        return None
    return abs(amount)


def _bank_row_native_month(
    bank_row: dict[str, Any],
    *,
    bank_detail_rows_by_id: dict[str, dict[str, Any]],
) -> str:
    transaction_id = str(
        bank_row.get("id") or bank_row.get("transaction_id") or bank_row.get("row_id") or ""
    ).strip()
    detail_row = bank_detail_rows_by_id.get(transaction_id) or {}
    for value in (
        detail_row.get("scope_key"),
        detail_row.get("month"),
        detail_row.get("trade_date"),
        detail_row.get("trade_time"),
        bank_row.get("trade_time"),
        bank_row.get("pay_receive_time"),
        bank_row.get("date"),
    ):
        normalized = str(value or "").strip()
        if MONTH_RE.match(normalized[:7]):
            return normalized[:7]
    return ""


def _group_special_metadata(group: dict[str, Any]) -> dict[str, Any]:
    metadata = group.get("special_metadata")
    return dict(metadata) if isinstance(metadata, dict) else {}


def _cash_ticket_cost_entry(
    group: dict[str, Any],
    *,
    oa_rows: list[dict[str, Any]],
    bank_rows: list[dict[str, Any]],
    special_metadata: dict[str, Any],
    bank_tag_contexts: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if _clean_text(special_metadata.get("special_type")) != CASH_TICKET_PURCHASE_MODE:
        return None
    amount = _decimal(special_metadata.get("ticket_cost_amount"))
    if amount in (None, ZERO):
        return None
    bank_row = next((row for row in bank_rows if _outflow_amount(row) is not None), None)
    if bank_row is None:
        return None
    eligible_oa_rows = [row for row in oa_rows if _is_completed_oa_cost_row(row)]
    if not eligible_oa_rows:
        return None
    contexts = [
        _oa_cost_context(row, fallback_index=index)
        for index, row in enumerate(eligible_oa_rows)
    ]
    context = _fallback_cost_context(contexts)
    project_name = _clean_text(special_metadata.get("project_name")) or str(context["project_name"])
    transaction_id = str(bank_row.get("id") or bank_row.get("row_id") or "")
    return {
        "row_key": f"{transaction_id}:ticket",
        "group_id": str(group.get("group_id") or ""),
        "transaction_id": transaction_id,
        "trade_time": str(bank_row.get("trade_time") or bank_row.get("pay_receive_time") or ""),
        "counterparty_name": str(bank_row.get("counterparty_name") or ""),
        "payment_account_label": str(bank_row.get("payment_account_label") or ""),
        "direction": str(bank_row.get("direction") or "支出"),
        "remark": str(bank_row.get("remark") or ""),
        "project_name": project_name,
        "project_id": _clean_text(special_metadata.get("project_id")) or str(context.get("project_id") or ""),
        "expense_type": _clean_text(special_metadata.get("expense_type"))
        or str(context.get("expense_type") or "现金往来"),
        "expense_content": _clean_text(special_metadata.get("expense_content")) or "买票成本",
        "oa_applicant": str(
            context.get("oa_applicant") or _cash_special_applicant(eligible_oa_rows) or "—"
        ),
        "amount_decimal": amount,
        **(
            {"source_project_contexts": list(context["source_project_contexts"])}
            if isinstance(context.get("source_project_contexts"), list)
            else {}
        ),
        **(bank_tag_contexts.get(transaction_id) or bank_tag_context_from_row(bank_row)),
    }


def _cash_special_applicant(oa_rows: list[dict[str, Any]]) -> str:
    for row in oa_rows:
        applicant = _clean_text(row.get("applicant"))
        if applicant:
            return applicant
        detail_fields = row.get("detail_fields")
        if isinstance(detail_fields, dict):
            applicant = _clean_text(detail_fields.get("申请人"))
            if applicant:
                return applicant
    return ""


def _is_completed_oa_cost_row(row: dict[str, Any]) -> bool:
    return is_completed_workflow_status(row.get("workflow_status"))


def _is_completed_project_allocation(
    context: dict[str, Any],
    *,
    completed_project_ids: set[str],
    completed_project_names: set[str],
) -> bool:
    source_contexts = context.get("source_project_contexts")
    if isinstance(source_contexts, list) and source_contexts:
        return all(
            _is_completed_project_identity(
                item,
                completed_project_ids=completed_project_ids,
                completed_project_names=completed_project_names,
            )
            for item in source_contexts
            if isinstance(item, dict)
        )
    return _is_completed_project_identity(
        context,
        completed_project_ids=completed_project_ids,
        completed_project_names=completed_project_names,
    )


def _is_completed_project_identity(
    context: dict[str, Any],
    *,
    completed_project_ids: set[str],
    completed_project_names: set[str],
) -> bool:
    project_id = _clean_text(context.get("project_id"))
    project_name = _clean_text(context.get("project_name"))
    return bool(
        (project_id and project_id in completed_project_ids)
        or (project_name and project_name in completed_project_names)
    )


def _serialize_cost_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bank_tag_context = bank_tag_context_from_row(entry)
    return {
        "row_key": entry.get("row_key") or f"{entry['transaction_id']}:full",
        "group_id": entry.get("group_id") or "",
        "transaction_id": entry["transaction_id"],
        "trade_time": entry["trade_time"],
        "direction": entry["direction"],
        "project_name": entry["project_name"],
        "project_id": entry.get("project_id") or "",
        "expense_type": entry["expense_type"],
        "expense_content": entry["expense_content"],
        "amount": format_decimal(entry["amount_decimal"]),
        "counterparty_name": entry["counterparty_name"],
        "payment_account_label": entry["payment_account_label"],
        "remark": entry["remark"],
        "oa_applicant": entry["oa_applicant"],
        **bank_tag_context,
    }


def _cost_entry_from_payload_row(row: dict[str, Any], *, fallback_index: int) -> dict[str, Any]:
    amount = _decimal(row.get("amount")) or ZERO
    transaction_id = str(row.get("transaction_id") or row.get("id") or f"payload-row-{fallback_index}")
    return {
        "row_key": str(row.get("row_key") or f"{transaction_id}:full"),
        "group_id": str(row.get("group_id") or ""),
        "transaction_id": transaction_id,
        "trade_time": str(row.get("trade_time") or ""),
        "counterparty_name": str(row.get("counterparty_name") or ""),
        "payment_account_label": str(row.get("payment_account_label") or ""),
        "direction": str(row.get("direction") or "支出"),
        "remark": str(row.get("remark") or ""),
        "project_name": str(row.get("project_name") or "未配对OA"),
        "project_id": str(row.get("project_id") or ""),
        "expense_type": str(row.get("expense_type") or "未分类"),
        "expense_content": str(row.get("expense_content") or ""),
        "oa_applicant": str(row.get("oa_applicant") or "—"),
        "amount_decimal": amount,
        **bank_tag_context_from_row(row),
    }


def _bank_transaction_ids_from_groups(groups: list[dict[str, Any]]) -> list[str]:
    transaction_ids: list[str] = []
    seen: set[str] = set()
    for group in groups:
        if not list(group.get("oa_rows") or []) or not list(group.get("bank_rows") or []):
            continue
        for row in list(group.get("bank_rows") or []):
            if not isinstance(row, dict):
                continue
            transaction_id = str(row.get("id") or row.get("transaction_id") or row.get("row_id") or "").strip()
            if transaction_id and transaction_id not in seen:
                transaction_ids.append(transaction_id)
                seen.add(transaction_id)
    return transaction_ids


def _bank_detail_not_fresh_error(
    payload: dict[str, Any] | None,
    *,
    operation: str,
    month: str,
) -> str:
    if not isinstance(payload, dict):
        return f"bank_detail_read_model_not_fresh: operation={operation} status=invalid_payload scope_keys={month}"
    status = str(payload.get("status") or "missing").strip().lower() or "missing"
    scope_keys = [str(value).strip() for value in list(payload.get("scope_keys") or []) if str(value).strip()]
    stale_reasons = [
        str(value).strip()
        for value in list(payload.get("stale_reasons") or [])
        if str(value).strip()
    ]
    return " ".join(
        [
            "bank_detail_read_model_not_fresh:",
            f"operation={operation}",
            f"status={status}",
            f"scope_keys={','.join(scope_keys or [month])}",
            f"stale_reasons={','.join(stale_reasons) or 'unknown'}",
        ]
    )


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
