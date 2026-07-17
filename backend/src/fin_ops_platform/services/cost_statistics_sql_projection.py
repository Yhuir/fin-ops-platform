from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
ZERO = Decimal("0.00")
OA_INVOICE_OFFSET_AUTO_MATCH_CODE = "oa_invoice_offset_auto_match"
OA_INVOICE_OFFSET_TAG = "冲"
CASH_TICKET_PURCHASE_MODE = "cash_ticket_purchase"


class CostStatisticsSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: Any | None = None,
        bank_transaction_tag_read_facade: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = CostStatisticsReadModelRepositoryPort(
            read_model_repository or PostgresReadModelRepository(connection)
        )
        self._bank_transaction_tag_read_facade = bank_transaction_tag_read_facade
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
    ) -> dict[str, object]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month == "all":
            return self.rebuild_cost_statistics_parent_scope(
                scope_key,
                tenant_id=tenant_id,
                source_version=source_version,
            )
        return self.rebuild_cost_statistics_month_scope(
            scope_key,
            tenant_id=tenant_id,
            source_version=source_version,
        )

    def rebuild_cost_statistics_month_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
    ) -> dict[str, object]:
        self._settings_payload_cache = None
        try:
            project_scope, month = _parse_cost_scope_key(scope_key)
            if month == "all":
                raise ValueError("month scope rebuild requires a concrete YYYY-MM scope.")
            workbench_groups = self._cost_groups_from_workbench(month)
            bank_detail_payload = self._bank_detail_snapshot_payload(
                month,
                include_transaction_ids=_bank_transaction_ids_from_groups(workbench_groups),
            )
            source_versions = self._source_versions(month, bank_detail_payload=bank_detail_payload)
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

    def rebuild_cost_statistics_relation_delta(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
        relation_deltas: list[dict[str, object]],
    ) -> dict[str, object]:
        self._settings_payload_cache = None
        try:
            project_scope, month = _parse_cost_scope_key(scope_key)
            if month == "all":
                raise ValueError("relation delta requires a concrete YYYY-MM scope.")
            normalized_deltas = _normalize_relation_deltas(relation_deltas)
            if not normalized_deltas:
                raise ValueError("relation delta requires at least one valid relation delta.")
            affected_case_ids = [str(delta["case_id"]) for delta in normalized_deltas]
            affected_group_ids = [_workbench_relation_group_id(case_id) for case_id in affected_case_ids]
            all_relation_row_ids = _dedupe_text(
                [row_id for delta in normalized_deltas for row_id in list(delta["row_ids"])]
            )
            rows_by_id = self._active_workbench_rows_by_ids(
                tenant_id=tenant_id,
                month=month,
                row_ids=all_relation_row_ids,
            )
            groups: list[dict[str, Any]] = []
            affected_bank_ids: list[str] = []
            for delta in normalized_deltas:
                case_id = str(delta["case_id"])
                delta_row_ids = [str(row_id) for row_id in list(delta["row_ids"])]
                relation_status = str(delta["status"])
                if relation_status == "active":
                    missing_row_ids = [row_id for row_id in delta_row_ids if row_id not in rows_by_id]
                    if missing_row_ids:
                        return {
                            "scope_key": scope_key,
                            "month": month,
                            "project_scope": project_scope,
                            "published": False,
                            "skip_reason": "workbench_rows_not_published",
                            "missing_row_ids": missing_row_ids,
                            "source_version": source_version,
                            "refresh_kind": "relation_delta",
                        }
                bank_rows: list[dict[str, Any]] = []
                oa_rows: list[dict[str, Any]] = []
                for row_id in delta_row_ids:
                    row = rows_by_id.get(row_id)
                    row_type = _relation_delta_row_type("", row)
                    if row_type == "bank":
                        if row_id not in affected_bank_ids:
                            affected_bank_ids.append(row_id)
                        if row is not None:
                            bank_rows.append(row)
                    elif row_type == "oa" and row is not None:
                        oa_rows.append(row)
                if relation_status == "active" and oa_rows and bank_rows:
                    groups.append(
                        {
                            "group_id": _workbench_relation_group_id(case_id),
                            "oa_rows": oa_rows,
                            "bank_rows": bank_rows,
                            "special_metadata": {},
                        }
                    )

            replacement_entries = self._cost_entries_from_workbench(
                groups,
                project_scope=project_scope,
                bank_detail_rows=self._cost_bank_tag_rows(
                    scope_key=scope_key,
                    transaction_ids=affected_bank_ids,
                ),
            )
            existing_metadata = self._read_model_repository.get_cost_statistics_scope_metadata(scope_key=scope_key) or {}
            existing_source_versions = existing_metadata.get("source_versions")
            existing_source_versions = existing_source_versions if isinstance(existing_source_versions, dict) else {}
            source_versions = cost_statistics_source_versions(
                month=month,
                settings_payload=self._settings_payload(),
                workbench_source_versions=self._workbench_source_versions(month),
                bank_detail_source_versions=existing_source_versions.get("bank_detail_source_versions")
                if isinstance(existing_source_versions.get("bank_detail_source_versions"), dict)
                else {},
            )
            source_versions["cost_statistics_relation_delta"] = {
                "source_version": source_version,
                "row_ids": sorted(all_relation_row_ids),
                "case_ids": sorted(affected_case_ids),
                "relations": normalized_deltas,
            }
            generated_at = datetime.now(UTC).isoformat()
            model = {
                "scope_key": scope_key,
                "scope_type": "month",
                "schema_version": COST_STATISTICS_READ_MODEL_SCHEMA_VERSION,
                "month": month,
                "project_scope": project_scope,
                "generated_at": generated_at,
                "cache_status": "ready",
                "payload": {
                    "month": month,
                    "project_scope": project_scope,
                    "bank_accounts": self._bank_accounts_from_settings(),
                },
                "source_scope_keys": [month],
                "source_versions": source_versions,
            }
            published = self._read_model_repository.publish_cost_statistics_relation_delta(
                tenant_id=tenant_id,
                scope_key=scope_key,
                source_version=source_version,
                model=model,
                replacement_rows=[_serialize_cost_entry(entry) for entry in replacement_entries],
                affected_transaction_ids=affected_bank_ids,
                affected_group_ids=affected_group_ids,
            )
            return {
                "scope_key": scope_key,
                "month": month,
                "project_scope": project_scope,
                "entry_count": len(replacement_entries),
                "row_count": len(replacement_entries),
                "affected_row_count": len(all_relation_row_ids),
                "source_version": source_version,
                "refresh_kind": "relation_delta",
                "published": published,
                **({"skip_reason": "stale_source_version_at_publish"} if not published else {}),
            }
        finally:
            self._settings_payload_cache = None

    def _active_workbench_rows_by_ids(
        self,
        *,
        tenant_id: str,
        month: str,
        row_ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        if not row_ids:
            return {}
        rows = self._connection.fetch_all(
            """
            with active_generation as (
                select distinct on (scope_key)
                       generation_id, scope_key, activated_at, completed_at, updated_at
                from read_model.workbench_generations
                where tenant_id = %s
                  and status = 'active'
                  and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
                order by scope_key, activated_at desc nulls last, completed_at desc nulls last, updated_at desc
            )
            select distinct on (row.row_id)
                   row.row_id, row.source_kind, row.payload, row.raw_payload
            from active_generation active
            join read_model.workbench_rows row on row.generation_id = active.generation_id
            where row.row_id = any(%s::text[])
            order by row.row_id,
                     (row.scope_key = %s) desc,
                     active.activated_at desc nulls last,
                     active.completed_at desc nulls last,
                     active.updated_at desc
            """,
            (str(tenant_id or "default"), row_ids, month),
        )
        result: dict[str, dict[str, Any]] = {}
        for item in rows:
            row_id = str(item.get("row_id") or "").strip()
            payload = row_payload(item, "payload", "raw_payload")
            if not row_id or not isinstance(payload, dict):
                continue
            normalized = dict(payload)
            normalized.setdefault("id", row_id)
            normalized.setdefault("row_id", row_id)
            normalized.setdefault("source_kind", item.get("source_kind"))
            normalized.setdefault("type", item.get("source_kind"))
            result[row_id] = normalized
        return result

    def _cost_bank_tag_rows(self, *, scope_key: str, transaction_ids: list[str]) -> list[dict[str, Any]]:
        if not transaction_ids:
            return []
        return self._connection.fetch_all(
            """
            select transaction_id, bank_tag_code, bank_tag_label,
                   bank_tag_primary_label, bank_tag_sub_label, bank_tag_label_path,
                   payload, raw_payload
            from read_model.cost_statistics_bank_flow_rows
            where scope_key = %s
              and transaction_id = any(%s::text[])
            order by transaction_id, row_key
            """,
            (scope_key, transaction_ids),
        )

    def rebuild_cost_statistics_parent_scope(
        self,
        scope_key: str,
        *,
        tenant_id: str,
        source_version: int,
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
            project_scope=project_scope,
            bank_detail_rows=bank_detail_rows,
        )
        bank_flow_entries = self._bank_flow_entries_from_bank_detail_rows(
            [
                row
                for row in list((bank_detail_payload or {}).get("month_rows") or [])
                if isinstance(row, dict)
            ]
        )
        return self._build_explorer_payload_from_entries(
            entries,
            month=month,
            project_scope=project_scope,
            bank_flow_entries=bank_flow_entries,
        )

    def _build_explorer_payload_from_entries(
        self,
        entries: list[dict[str, Any]],
        *,
        month: str,
        project_scope: str,
        bank_flow_entries: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        sorted_entries = sorted(entries, key=lambda item: (str(item["trade_time"]), str(item["transaction_id"])), reverse=True)
        sorted_bank_flow_entries = sorted(
            bank_flow_entries or [],
            key=lambda item: (str(item["trade_time"]), str(item["transaction_id"])),
            reverse=True,
        )
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
            "bank_flow_summary": _bank_flow_summary(sorted_bank_flow_entries),
            "bank_flow_time_rows": [_serialize_cost_entry(entry) for entry in sorted_bank_flow_entries],
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
        return [group for group in groups_by_id.values() if group.get("zone") == "paired"]

    def _cost_entries_from_workbench(
        self,
        groups: list[dict[str, Any]],
        *,
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
        for group in groups:
            oa_rows = [row for row in list(group.get("oa_rows") or []) if isinstance(row, dict)]
            bank_rows = [row for row in list(group.get("bank_rows") or []) if isinstance(row, dict)]
            if not oa_rows or not bank_rows:
                continue
            special_metadata = _group_special_metadata(group)
            special_policy = _clean_text(special_metadata.get("cost_policy"))
            if special_policy == "exclude_all":
                continue
            if special_policy == "include_ticket_cost_only":
                ticket_entry = _cash_ticket_cost_entry(
                    group,
                    oa_rows=oa_rows,
                    bank_rows=bank_rows,
                    special_metadata=special_metadata,
                    bank_tag_contexts=bank_tag_contexts,
                )
                if ticket_entry is not None and not _is_completed_project(
                    ticket_entry,
                    completed_project_ids=completed_project_ids,
                    completed_project_names=completed_project_names,
                ):
                    entries.append(ticket_entry)
                continue
            context = _cost_context_from_oa_rows(oa_rows)
            if context is None:
                continue
            if _is_completed_project(
                context,
                completed_project_ids=completed_project_ids,
                completed_project_names=completed_project_names,
            ):
                continue
            for bank_row in bank_rows:
                amount = _outflow_amount(bank_row)
                if amount is None:
                    continue
                transaction_id = str(bank_row.get("id") or bank_row.get("row_id") or "")
                entries.append(
                    {
                        "group_id": str(group.get("group_id") or ""),
                        "transaction_id": transaction_id,
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
                        **(bank_tag_contexts.get(transaction_id) or bank_tag_context_from_row({})),
                    }
                )
        return entries

    def _bank_flow_entries_from_bank_detail_rows(
        self,
        bank_detail_rows: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for index, row in enumerate(bank_detail_rows):
            if not isinstance(row, dict):
                continue
            direction = _bank_flow_direction(row)
            if direction is None:
                continue
            transaction_id = str(row.get("transaction_id") or row.get("id") or row.get("row_id") or f"bank-flow-{index}").strip()
            amount = _decimal(row.get("amount") or row.get("signed_amount") or row.get("debit_amount"))
            if amount in (None, ZERO):
                continue
            bank_tag_context = bank_tag_context_from_row(row)
            label = str(
                bank_tag_context.get("bank_tag_sub_label")
                or bank_tag_context.get("bank_tag_label")
                or bank_tag_context.get("bank_tag_primary_label")
                or "未分类"
            )
            summary = _clean_text(row.get("summary")) or _clean_text(row.get("purpose")) or _clean_text(row.get("remark"))
            entries.append(
                {
                    "group_id": "",
                    "transaction_id": transaction_id,
                    "trade_time": str(row.get("trade_time") or row.get("trade_date") or ""),
                    "counterparty_name": str(row.get("counterparty_name") or ""),
                    "payment_account_label": _bank_detail_payment_account_label(row),
                    "direction": direction,
                    "remark": str(row.get("purpose") or row.get("remark") or row.get("summary") or ""),
                    "project_name": "未配对OA",
                    "project_id": "",
                    "expense_type": label,
                    "expense_content": summary or label,
                    "oa_applicant": "—",
                    "amount_decimal": abs(amount),
                    **bank_tag_context,
                }
            )
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


def _dedupe_text(values: list[object]) -> list[str]:
    result: list[str] = []
    for value in values:
        normalized = str(value or "").strip()
        if normalized and normalized not in result:
            result.append(normalized)
    return result


def _normalize_relation_deltas(values: list[dict[str, object]]) -> list[dict[str, object]]:
    result_by_case_id: dict[str, dict[str, object]] = {}
    for value in list(values or []):
        if not isinstance(value, dict):
            continue
        case_id = str(value.get("case_id") or "").strip()
        status = str(value.get("status") or "").strip().lower()
        raw_row_ids = value.get("row_ids")
        row_ids = _dedupe_text(list(raw_row_ids) if isinstance(raw_row_ids, (list, tuple, set)) else [])
        if case_id and status in {"active", "cancelled"} and row_ids:
            result_by_case_id[case_id] = {"case_id": case_id, "status": status, "row_ids": row_ids}
    return list(result_by_case_id.values())


def _workbench_relation_group_id(case_id: object) -> str:
    normalized_case_id = str(case_id or "").strip()
    if not normalized_case_id:
        raise ValueError("Workbench relation group identity requires case_id.")
    return f"case:{normalized_case_id}"


def _relation_delta_row_type(raw_type: object, row: dict[str, Any] | None) -> str:
    normalized = str(raw_type or "").strip().lower()
    if normalized in {"bank", "bank_transaction"}:
        return "bank"
    if normalized == "oa":
        return "oa"
    source_kind = str((row or {}).get("source_kind") or (row or {}).get("type") or "").strip().lower()
    if source_kind in {"bank", "bank_transaction"}:
        return "bank"
    if source_kind == "oa":
        return "oa"
    return ""


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
        if _is_cost_excluded_oa_row(row):
            continue
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
    credit_amount = _decimal(bank_row.get("credit_amount"))
    if credit_amount not in (None, ZERO):
        return None
    amount = _decimal(bank_row.get("debit_amount") or bank_row.get("amount"))
    if amount in (None, ZERO):
        return None
    return abs(amount)


def _group_special_metadata(group: dict[str, Any]) -> dict[str, Any]:
    metadata = group.get("special_metadata")
    if isinstance(metadata, dict) and metadata:
        return dict(metadata)
    for row in [
        *list(group.get("oa_rows") or []),
        *list(group.get("bank_rows") or []),
        *list(group.get("invoice_rows") or []),
    ]:
        if not isinstance(row, dict):
            continue
        row_metadata = row.get("special_metadata")
        if isinstance(row_metadata, dict) and row_metadata:
            return dict(row_metadata)
    return {}


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
    context = _cost_context_from_oa_rows(oa_rows) or {}
    project_name = _clean_text(special_metadata.get("project_name")) or str(context.get("project_name") or "")
    if not project_name:
        return None
    transaction_id = str(bank_row.get("id") or bank_row.get("row_id") or "")
    return {
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
        "oa_applicant": str(context.get("oa_applicant") or _cash_special_applicant(oa_rows) or "—"),
        "amount_decimal": amount,
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


def _is_cost_excluded_oa_row(row: dict[str, Any]) -> bool:
    if bool(row.get("cost_excluded")):
        return True
    tags = {_clean_text(tag) for tag in list(row.get("tags") or []) if _clean_text(tag)}
    if OA_INVOICE_OFFSET_TAG in tags:
        return True
    relation = row.get("oa_bank_relation")
    return isinstance(relation, dict) and _clean_text(relation.get("code")) == OA_INVOICE_OFFSET_AUTO_MATCH_CODE


def _is_completed_project(
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


def _bank_flow_direction(row: dict[str, Any]) -> str | None:
    direction = str(row.get("direction") or row.get("txn_direction") or "").strip().lower()
    if direction in {"income", "inflow", "收入", "收", "收款", "credit"}:
        return "收入"
    if direction in {"expense", "outflow", "支出", "支", "付款", "debit"}:
        return "支出"
    return None


def _bank_flow_summary(entries: list[dict[str, Any]]) -> dict[str, Any]:
    expense_entries = [entry for entry in entries if entry.get("direction") == "支出"]
    income_entries = [entry for entry in entries if entry.get("direction") == "收入"]
    return {
        "row_count": len(entries),
        "transaction_count": len(entries),
        "total_amount": format_decimal(sum((entry["amount_decimal"] for entry in entries), start=ZERO)),
        "expense_amount": format_decimal(sum((entry["amount_decimal"] for entry in expense_entries), start=ZERO)),
        "income_amount": format_decimal(sum((entry["amount_decimal"] for entry in income_entries), start=ZERO)),
        "expense_transaction_count": len(expense_entries),
        "income_transaction_count": len(income_entries),
    }


def _serialize_cost_entry(entry: dict[str, Any]) -> dict[str, Any]:
    bank_tag_context = bank_tag_context_from_row(entry)
    return {
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


def _bank_detail_payment_account_label(row: dict[str, Any]) -> str:
    explicit_label = _clean_text(row.get("payment_account_label"))
    if explicit_label:
        return explicit_label
    bank_name = _clean_text(row.get("bank_name"))
    account_last4 = _clean_text(row.get("account_last4"))
    if bank_name and account_last4:
        return f"{bank_name} 账户 {account_last4}"
    return bank_name or account_last4


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
