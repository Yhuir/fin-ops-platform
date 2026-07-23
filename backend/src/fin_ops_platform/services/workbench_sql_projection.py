from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.no_oa_bank_batch_service import (
    BANK_FLOW_RULE_BATCH_RELATION_MODE,
    NO_OA_BANK_BATCH_RELATION_MODE,
)
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.oa_attachment_invoice_linking import (
    oa_attachment_best_source_link,
    oa_attachment_matches_oa,
    oa_attachment_parent_oa_id,
)
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    COMPLETED_WORKFLOW_STATUS_SQL,
    OA_PROJECTION_SYNC_VERSION,
    PostgresOAProjectionAdapter,
    PostgresOAProjectionRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_exception_case_service import ACTIVE_CASE_STATUSES
from fin_ops_platform.services.workbench_etc_batch_link import relation_external_etc_batch_id
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_object_identity_arbitration import WorkbenchObjectIdentityArbitrationService
from fin_ops_platform.services.workbench_query_service import (
    OA_ATTACHMENT_INVOICE_SOURCE_KIND,
    WorkbenchQueryService,
)
from fin_ops_platform.services.workbench_relation_alignment_service import WorkbenchRelationAlignmentService
from fin_ops_platform.services.workbench_relation_grouping import WorkbenchRelationGroupingService
from fin_ops_platform.services.workbench_relation_requirements import (
    evaluate_bank_relation_completion,
)
from fin_ops_platform.services.workbench_read_model_version import (
    WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
    WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION,
)
from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.workbench_free_matching_engine import RULE_VERSION as WORKBENCH_FORMAL_RELATION_RULE_VERSION


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()
WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION = WORKBENCH_MONTH_SCOPE_SCHEMA_VERSION
ETC_BATCH_TAG = "ETC批量提交"


class WorkbenchSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        oa_query_service: WorkbenchQueryService | None = None,
        bank_account_resolver: BankAccountResolver | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._bank_account_mapping_cache: dict[str, str] | None = None
        self._bank_account_resolver = bank_account_resolver or BankAccountResolver(self._bank_account_mapping_dict)
        if oa_query_service is not None:
            self._oa_query_service = oa_query_service
        else:
            oa_repository = PostgresOAProjectionRepository(connection)
            self._oa_query_service = WorkbenchQueryService(
                oa_adapter=PostgresOAProjectionAdapter(oa_repository),
                seed_demo_rows=False,
            )

    def list_workbench_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope = str(scope_key or "").strip()
        if normalized_scope != "all":
            return [normalized_scope] if MONTH_RE.match(normalized_scope) else []
        rows = self._connection.fetch_all(
            """
            select scope_key
            from (
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from app.oa_applications
                where scope_month is not null
                  and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
                union
                select distinct to_char(txn_month, 'YYYY-MM') as scope_key
                from app.bank_transactions
                where txn_month is not null
                union
                select distinct to_char(invoice_month, 'YYYY-MM') as scope_key
                from app.invoices
                where invoice_month is not null
                union
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from app.etc_business_batches
                where scope_month is not null
                union
                select distinct to_char(scope_month, 'YYYY-MM') as scope_key
                from app.etc_invoices
                where scope_month is not null
                union
                select distinct scope_key
                from read_model.workbench_generations
                where tenant_id = 'default'
                  and status = 'active'
                  and scope_key ~ '^[0-9]{4}-[0-9]{2}$'
            ) scopes
            where scope_key is not null
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_RE.match(str(row.get("scope_key") or ""))]

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

    def rebuild_workbench_read_model_scope(
        self,
        scope_key: str,
        *,
        source_version: int | str | None = None,
    ) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip()
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("workbench SQL projection scope_key must be a month shard YYYY-MM.")
        self._bank_account_mapping_cache = None
        resolved_source_version = _int_or_none(source_version)
        if resolved_source_version is None:
            resolved_source_version = self._current_dirty_scope_source_version(normalized_scope)
        pending_claimed_bank_ids = set(self._pending_claimed_bank_transaction_ids_for_month(normalized_scope))
        rows_by_id = self._workbench_rows_for_month(
            normalized_scope,
            excluded_bank_transaction_ids=pending_claimed_bank_ids,
        )
        relations = self._active_pair_relations_for_month(normalized_scope, set(rows_by_id))
        self._supplement_missing_relation_rows(rows_by_id, relations)
        payload = self._group_payload(
            normalized_scope,
            rows_by_id,
            relations,
        )
        source_versions = self.source_versions_for_scope(normalized_scope)
        source_versions["source_version"] = resolved_source_version
        snapshot = {
            "read_models": {
                normalized_scope: {
                    "scope_key": normalized_scope,
                    "scope_month": normalized_scope,
                    "generated_at": datetime.now().isoformat(),
                    "cache_status": "fresh",
                    "payload": payload,
                    "source_versions": source_versions,
                },
            }
        }
        published_scope_keys = self._read_model_repository.save_workbench_read_models(
            snapshot,
            changed_scope_keys={normalized_scope},
        )
        row_count = sum(
            len(group.get(f"{kind}_rows") or [])
            for group in payload["paired"]["groups"] + payload["unpaired"]["groups"]
            for kind in ("oa", "bank", "invoice")
        )
        return {
            "scope_key": normalized_scope,
            "base_scope_key": normalized_scope,
            "row_count": row_count,
            "ignored_row_count": 0,
            "published": normalized_scope in set(published_scope_keys or set()),
        }

    def source_versions_for_scope(self, scope_key: str) -> dict[str, object]:
        """Return the canonical version proof used by both projection and query gates."""
        normalized_scope = str(scope_key or "").strip()
        if normalized_scope != "all":
            if not MONTH_RE.match(normalized_scope):
                raise ValueError(
                    "workbench SQL source-version scope_key must be a month shard YYYY-MM or all."
                )
            return self.source_versions_for_scopes([normalized_scope])[normalized_scope]
        row = self._connection.fetch_one(
            """
            select
              coalesce((select max(updated_at)::text from app.workbench_pair_relations), '') as pair_relations_updated_at,
              coalesce((select max(updated_at)::text from app.workbench_exception_cases), '') as exception_cases_updated_at,
              coalesce((select max(updated_at)::text from app.workbench_row_overrides), '') as row_overrides_updated_at,
              coalesce((
                select max(updated_at)::text
                from app.bank_transaction_relation_claims
                where status = 'active'
              ), '') as oa_pending_payment_bank_claims_updated_at,
              coalesce((
                select max(updated_at)::text
                from app.bank_transactions
                where status <> 'deleted'
              ), '') as bank_transactions_updated_at,
              coalesce((
                select max(updated_at)::text
                from app.invoices
                where status <> 'deleted'
              ), '') as invoices_updated_at,
              coalesce((
                select max(oa.updated_at)::text
                from app.oa_applications oa
                where """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
                   or oa.row_id in (
                     select unnest(relation.row_ids)
                     from app.workbench_pair_relations relation
                     where relation.status = 'active'
                   )
              ), '') as oa_projection_updated_at
            """
        )
        payload = row if isinstance(row, dict) else {}
        return {
            "builder": WORKBENCH_ALL_SCOPE_COMPOSED_SCHEMA_VERSION,
            "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
            "bank_auto_tag_rules_version": self._current_bank_auto_tag_rules_version(),
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
            "workbench_pair_relations_updated_at": str(payload.get("pair_relations_updated_at") or ""),
            "workbench_exception_cases_updated_at": str(payload.get("exception_cases_updated_at") or ""),
            "workbench_row_overrides_updated_at": str(payload.get("row_overrides_updated_at") or ""),
            "oa_pending_payment_bank_claims_updated_at": str(
                payload.get("oa_pending_payment_bank_claims_updated_at") or ""
            ),
            "bank_transactions_updated_at": str(payload.get("bank_transactions_updated_at") or ""),
            "invoices_updated_at": str(payload.get("invoices_updated_at") or ""),
            "oa_projection_updated_at": str(payload.get("oa_projection_updated_at") or ""),
        }

    def source_versions_for_scopes(self, scope_keys: list[str]) -> dict[str, dict[str, object]]:
        """Return canonical Workbench version proofs for month scopes in one query."""
        normalized_scope_keys = list(
            dict.fromkeys(
                normalized
                for scope_key in list(scope_keys or [])
                for normalized in [str(scope_key or "").strip()]
                if normalized
            )
        )
        if any(not MONTH_RE.match(scope_key) for scope_key in normalized_scope_keys):
            raise ValueError("workbench SQL bulk source-version scope_keys must be month shards YYYY-MM.")
        if not normalized_scope_keys:
            return {}
        scope_months = [month_start(scope_key) for scope_key in normalized_scope_keys]
        rows = self._connection.fetch_all(
            """
            with requested_scopes as (
                select unnest(%s::date[]) as scope_month
            ),
            month_objects as (
                select scopes.scope_month, coalesce(bank.legacy_mongo_id, bank.id::text) as row_id
                from requested_scopes scopes
                join app.bank_transactions bank on bank.txn_month = scopes.scope_month
                where bank.status <> 'deleted'
                union
                select scopes.scope_month, oa.row_id
                from requested_scopes scopes
                join app.oa_applications oa
                  on oa.application_date >= scopes.scope_month
                 and oa.application_date < scopes.scope_month + interval '1 month'
                where """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
                union
                select scopes.scope_month, coalesce(invoice.legacy_mongo_id, invoice.id::text) as row_id
                from requested_scopes scopes
                join app.invoices invoice on invoice.invoice_month = scopes.scope_month
                where invoice.status <> 'deleted'
            ),
            month_object_arrays as (
                select
                  scopes.scope_month,
                  coalesce(
                    array_agg(distinct objects.row_id) filter (where objects.row_id is not null),
                    array[]::text[]
                  ) as row_ids
                from requested_scopes scopes
                left join month_objects objects on objects.scope_month = scopes.scope_month
                group by scopes.scope_month
            ),
            scoped_relations as (
                select scopes.scope_month, relation.status, relation.updated_at, relation.row_ids
                from requested_scopes scopes
                join app.workbench_pair_relations relation on relation.month_scope = scopes.scope_month
                union
                select objects.scope_month, relation.status, relation.updated_at, relation.row_ids
                from month_object_arrays objects
                join app.workbench_pair_relations relation on relation.row_ids && objects.row_ids
            ),
            active_relation_row_ids as (
                select distinct relations.scope_month, unnest(relations.row_ids) as row_id
                from scoped_relations relations
                where relations.status = 'active'
            ),
            scope_row_ids as (
                select scope_month, row_id from month_objects
                union
                select scope_month, row_id from active_relation_row_ids
            ),
            scope_row_id_arrays as (
                select
                  scopes.scope_month,
                  coalesce(
                    array_agg(distinct ids.row_id) filter (where ids.row_id is not null),
                    array[]::text[]
                  ) as row_ids
                from requested_scopes scopes
                left join scope_row_ids ids on ids.scope_month = scopes.scope_month
                group by scopes.scope_month
            ),
            relation_versions as (
                select scope_month, max(updated_at)::text as pair_relations_updated_at
                from scoped_relations
                group by scope_month
            ),
            exception_updates as (
                select scopes.scope_month, exception.updated_at
                from requested_scopes scopes
                join app.workbench_exception_cases exception
                  on exception.scope_month = scopes.scope_month
                union all
                select objects.scope_month, exception.updated_at
                from scope_row_id_arrays objects
                join app.workbench_exception_cases exception
                  on exception.row_ids && objects.row_ids
            ),
            exception_versions as (
                select scope_month, max(updated_at)::text as exception_cases_updated_at
                from exception_updates
                group by scope_month
            ),
            override_updates as (
                select scopes.scope_month, override.updated_at
                from requested_scopes scopes
                join app.workbench_row_overrides override
                  on override.scope_month = scopes.scope_month
                union all
                select ids.scope_month, override.updated_at
                from scope_row_ids ids
                join app.workbench_row_overrides override on override.row_id = ids.row_id
            ),
            override_versions as (
                select scope_month, max(updated_at)::text as row_overrides_updated_at
                from override_updates
                group by scope_month
            ),
            claim_versions as (
                select claims.scope_month, max(claims.updated_at)::text as oa_pending_payment_bank_claims_updated_at
                from app.bank_transaction_relation_claims claims
                join requested_scopes scopes on scopes.scope_month = claims.scope_month
                where claims.status = 'active'
                group by claims.scope_month
            ),
            bank_updates as (
                select scopes.scope_month, bank.updated_at
                from requested_scopes scopes
                join app.bank_transactions bank on bank.txn_month = scopes.scope_month
                where bank.status <> 'deleted'
                union all
                select ids.scope_month, bank.updated_at
                from scope_row_ids ids
                join app.bank_transactions bank
                  on coalesce(bank.legacy_mongo_id, bank.id::text) = ids.row_id
                where bank.status <> 'deleted'
            ),
            bank_versions as (
                select scope_month, max(updated_at)::text as bank_transactions_updated_at
                from bank_updates
                group by scope_month
            ),
            invoice_updates as (
                select scopes.scope_month, invoice.updated_at
                from requested_scopes scopes
                join app.invoices invoice on invoice.invoice_month = scopes.scope_month
                where invoice.status <> 'deleted'
                union all
                select ids.scope_month, invoice.updated_at
                from scope_row_ids ids
                join app.invoices invoice
                  on coalesce(invoice.legacy_mongo_id, invoice.id::text) = ids.row_id
                where invoice.status <> 'deleted'
            ),
            invoice_versions as (
                select scope_month, max(updated_at)::text as invoices_updated_at
                from invoice_updates
                group by scope_month
            ),
            oa_updates as (
                select scopes.scope_month, oa.updated_at
                from requested_scopes scopes
                join app.oa_applications oa
                  on oa.application_date >= scopes.scope_month
                 and oa.application_date < scopes.scope_month + interval '1 month'
                where """
            + COMPLETED_WORKFLOW_STATUS_SQL
            + """
                union all
                select ids.scope_month, oa.updated_at
                from scope_row_ids ids
                join app.oa_applications oa on oa.row_id = ids.row_id
            ),
            oa_versions as (
                select scope_month, max(updated_at)::text as oa_projection_updated_at
                from oa_updates
                group by scope_month
            )
            select
              to_char(scopes.scope_month, 'YYYY-MM') as scope_key,
              relations.pair_relations_updated_at,
              exceptions.exception_cases_updated_at,
              overrides.row_overrides_updated_at,
              claims.oa_pending_payment_bank_claims_updated_at,
              bank.bank_transactions_updated_at,
              invoice.invoices_updated_at,
              oa.oa_projection_updated_at,
              coalesce(
                (
                  select case
                           when coalesce(
                             settings_payload->'bank_transaction_tags'->>'version',
                             ''
                           ) ~ '^[0-9]+$'
                           then (
                             settings_payload->'bank_transaction_tags'->>'version'
                           )::integer
                           else 1
                         end
                  from app.app_settings
                  where settings_key = 'app_settings'
                  order by updated_at desc
                  limit 1
                ),
                1
              ) as bank_auto_tag_rules_version
            from requested_scopes scopes
            left join relation_versions relations using (scope_month)
            left join exception_versions exceptions using (scope_month)
            left join override_versions overrides using (scope_month)
            left join claim_versions claims using (scope_month)
            left join bank_versions bank using (scope_month)
            left join invoice_versions invoice using (scope_month)
            left join oa_versions oa using (scope_month)
            order by scopes.scope_month
            """,
            (scope_months,),
        )
        payload_by_scope = {
            str(row.get("scope_key") or "").strip(): {
                "builder": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
                "workbench_formal_relation_rule_version": WORKBENCH_FORMAL_RELATION_RULE_VERSION,
                "bank_auto_tag_rules_version": (
                    _int_or_none(row.get("bank_auto_tag_rules_version")) or 1
                ),
                "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
                "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
                "workbench_pair_relations_updated_at": str(row.get("pair_relations_updated_at") or ""),
                "workbench_exception_cases_updated_at": str(row.get("exception_cases_updated_at") or ""),
                "workbench_row_overrides_updated_at": str(row.get("row_overrides_updated_at") or ""),
                "oa_pending_payment_bank_claims_updated_at": str(
                    row.get("oa_pending_payment_bank_claims_updated_at") or ""
                ),
                "bank_transactions_updated_at": str(row.get("bank_transactions_updated_at") or ""),
                "invoices_updated_at": str(row.get("invoices_updated_at") or ""),
                "oa_projection_updated_at": str(row.get("oa_projection_updated_at") or ""),
            }
            for row in rows
            if isinstance(row, dict) and str(row.get("scope_key") or "").strip()
        }
        return {
            scope_key: payload_by_scope[scope_key]
            for scope_key in normalized_scope_keys
            if scope_key in payload_by_scope
        }

    def _current_bank_auto_tag_rules_version(self) -> int:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            ("app_settings",),
        )
        payload = row_payload(row, "settings_payload")
        if not isinstance(payload, dict):
            return 1
        bank_transaction_tags = payload.get("bank_transaction_tags")
        if isinstance(bank_transaction_tags, dict):
            value = bank_transaction_tags.get("version")
            try:
                return int(value)
            except (TypeError, ValueError):
                return 1
        return 1

    def _workbench_rows_for_month(
        self,
        month: str,
        *,
        excluded_bank_transaction_ids: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for row in self._oa_projection_rows(month):
            rows[str(row["id"])] = row
        for row in self._bank_rows(month, excluded_bank_transaction_ids=excluded_bank_transaction_ids):
            rows[str(row["id"])] = row
        invoice_rows = self._invoice_rows(month)
        self._supplement_source_oa_rows_for_attachment_invoices(rows, invoice_rows)
        for row in invoice_rows:
            rows[str(row["id"])] = row
        for row in self._unpaired_etc_invoice_summary_rows(month):
            rows[str(row["id"])] = row
        return rows

    def _supplement_source_oa_rows_for_attachment_invoices(
        self,
        rows: dict[str, dict[str, Any]],
        invoice_rows: list[dict[str, Any]],
    ) -> None:
        missing_parent_oa_ids = {
            parent_oa_id
            for row in invoice_rows
            if str(row.get("source_kind") or "").strip() == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            if (parent_oa_id := oa_attachment_parent_oa_id(row.get("derived_from_oa_id")))
            if parent_oa_id not in rows
        }
        for row in self._oa_projection_rows_by_ids(missing_parent_oa_ids):
            rows.setdefault(str(row["id"]), row)

    def _oa_projection_rows(self, month: str) -> list[dict[str, Any]]:
        self._oa_query_service.get_workbench(month)
        result: list[dict[str, Any]] = []
        for row in self._oa_query_service.list_record_snapshots():
            row_month = str(row.get("_month") or "").strip()
            row_type = str(row.get("type") or "").strip()
            if row_month != month or row_type != "oa":
                continue
            payload = self._oa_query_service.serialize_row(row)
            payload["status"] = "unpaired"
            payload.setdefault("source_kind", payload.get("type") or row_type)
            result.append(payload)
        return result

    def _oa_projection_rows_by_ids(self, row_ids: set[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        oa_row_ids = {row_id for row_id in row_ids if row_id.startswith("oa-") and not row_id.startswith("oa-att-")}
        wanted = set(row_ids)
        self._oa_query_service.sync_oa_row_ids(sorted(oa_row_ids))
        result: list[dict[str, Any]] = []
        for row in self._oa_query_service.list_record_snapshots():
            row_id = str(row.get("id") or "").strip()
            if row_id not in wanted:
                continue
            if str(row.get("type") or "").strip() != "oa":
                continue
            payload = self._oa_query_service.serialize_row(row)
            payload["status"] = "unpaired"
            payload.setdefault("source_kind", payload.get("type") or row.get("type"))
            result.append(payload)
        missing_row_ids = wanted - {str(row.get("id") or "").strip() for row in result}
        result.extend(self._oa_projection_rows_by_sql_ids(missing_row_ids))
        return result

    def _oa_projection_rows_by_sql_ids(self, row_ids: set[str]) -> list[dict[str, Any]]:
        normalized_row_ids = sorted({row_id for row_id in row_ids if row_id.startswith("oa-") and not row_id.startswith("oa-att-")})
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select row_id, applicant, application_date, approved_at, project_name, amount, status, workflow_status, normalized_payload, raw_payload
            from app.oa_applications
            where row_id = any(%s)
            order by row_id
            """,
            (normalized_row_ids,),
        )
        return [payload for row in rows if (payload := self._oa_row_from_sql(row))]

    def _legacy_oa_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select row_id, applicant, application_date, approved_at, project_name, amount, status, normalized_payload, raw_payload
            from app.oa_applications
            where scope_month = %s::date
              and """ + COMPLETED_WORKFLOW_STATUS_SQL + """
            order by row_id
            """,
            (month_start(month),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            if payload := self._oa_row_from_sql(row):
                result.append(payload)
        return result

    @staticmethod
    def _oa_row_from_sql(row: dict[str, Any]) -> dict[str, Any] | None:
        payload = row_payload(row, "normalized_payload", "raw_payload")
        payload = payload if isinstance(payload, dict) else {}
        row_id = str(row.get("row_id") or payload.get("id") or "").strip()
        if not row_id:
            return None
        detail_fields = payload.get("detail_fields") if isinstance(payload.get("detail_fields"), dict) else {}
        summary_fields = payload.get("summary_fields") if isinstance(payload.get("summary_fields"), dict) else {}
        amount_mismatch = payload.get("amount_mismatch") if isinstance(payload.get("amount_mismatch"), dict) else None
        apply_time = _oa_application_time(row, payload, detail_fields, summary_fields)
        completed_at = _oa_completed_time(row, payload, detail_fields, summary_fields)
        return {
            "id": row_id,
            "type": "oa",
            "source_kind": "oa",
            "status": "unpaired",
            "workflow_status": row.get("workflow_status") or payload.get("workflow_status"),
            "applicant": row.get("applicant") or payload.get("applicant"),
            "apply_time": apply_time,
            "application_time": apply_time,
            "application_date": apply_time,
            "completed_at": completed_at,
            "date": _date_text(row.get("application_date") or payload.get("date")),
            "project_name": row.get("project_name") or payload.get("project_name"),
            "amount": str(row.get("amount") or payload.get("amount") or ""),
            "amount_source": payload.get("amount_source") or detail_fields.get("金额来源"),
            "amount_mismatch": amount_mismatch,
            "reconciliation_amount": _oa_reconciliation_amount(payload, detail_fields),
            "reason": payload.get("reason"),
            "summary_fields": summary_fields,
            "detail_fields": detail_fields,
        }

    def _bank_rows(
        self,
        month: str,
        *,
        excluded_bank_transaction_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        excluded_bank_ids = {
            str(row_id).strip()
            for row_id in (excluded_bank_transaction_ids or set())
            if str(row_id).strip()
        }
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, account_no, account_name,
                   txn_direction, counterparty_name_raw, amount, txn_date, trade_time,
                   summary, remark, project_id, raw_payload
            from app.bank_transactions
            where txn_month = %s::date
              and status <> 'deleted'
              and not (coalesce(legacy_mongo_id, id::text) = any(%s::text[]))
            order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
            """,
            (month_start(month), sorted(excluded_bank_ids)),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            if str(row.get("row_id") or "").strip() in excluded_bank_ids:
                continue
            if row_payload_dict := self._bank_row_from_sql(row):
                result.append(row_payload_dict)
        return result

    def _bank_rows_by_ids(self, row_ids: set[str]) -> list[dict[str, Any]]:
        normalized_row_ids = sorted({row_id for row_id in row_ids if row_id})
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, account_no, account_name,
                   txn_direction, counterparty_name_raw, amount, signed_amount, txn_date, trade_time,
                   pay_receive_time, summary, remark, project_id, raw_payload
            from app.bank_transactions
            where coalesce(legacy_mongo_id, id::text) = any(%s)
              and status <> 'deleted'
            order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
            """,
            (normalized_row_ids,),
        )
        return [payload for row in rows if (payload := self._bank_row_from_sql(row))]

    def _bank_row_from_sql(self, row: dict[str, Any]) -> dict[str, Any] | None:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            return None
        amount = row.get("amount")
        signed_amount = row.get("signed_amount")
        direction = str(row.get("txn_direction") or "")
        debit_amount = amount if _is_outflow(direction, signed_amount) else None
        credit_amount = amount if not _is_outflow(direction, signed_amount) else None
        account_no = str(row.get("account_no") or "")
        account_name = str(row.get("account_name") or "")
        payment_account_label = self._bank_account_resolver.resolve_label(account_no, account_name)
        detail_fields = row_payload(row, "raw_payload")
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        return {
            "id": row_id,
            "type": "bank",
            "source_kind": "bank",
            "status": "unpaired",
            "case_id": None,
            "trade_time": _date_text(row.get("trade_time") or row.get("txn_date")),
            "account_no": account_no,
            "account_name": account_name,
            "debit_amount": str(debit_amount or "") or None,
            "credit_amount": str(credit_amount or "") or None,
            "counterparty_name": row.get("counterparty_name_raw"),
            "payment_account_label": payment_account_label,
            "invoice_relation": {"code": "pending_invoice_match", "label": "待关联发票", "tone": "warn"},
            "pay_receive_time": _date_text(row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date")),
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
                "支付/收款时间": _date_text(row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date")),
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
              {self._submitted_etc_overlap_exclusion_sql("invoices")}
            order by invoice_date desc nulls last, row_id
            """,
            (month_start(month),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            if row_payload_dict := self._invoice_row_from_sql(row):
                result.append(row_payload_dict)
        return result

    def _invoice_rows_by_ids(self, row_ids: set[str]) -> list[dict[str, Any]]:
        normalized_row_ids = sorted({row_id for row_id in row_ids if row_id})
        if not normalized_row_ids:
            return []
        rows = self._connection.fetch_all(
            f"""
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
                   digital_invoice_no, invoice_date, counterparty_name, seller_name, seller_tax_no,
                   buyer_name, buyer_tax_no, amount, tax_rate, tax_amount, total_with_tax, status,
                   workbench_visibility, tags, source_links, raw_payload
            from app.invoices invoices
            where coalesce(invoices.legacy_mongo_id, invoices.id::text) = any(%s)
              and invoices.status <> 'deleted'
              and coalesce(invoices.workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
              and coalesce(invoices.raw_payload->'normalized_payload'->>'workbench_visibility', 'visible') <> 'hidden_after_etc_submission'
              and coalesce(invoices.raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
              {self._submitted_etc_overlap_exclusion_sql("invoices")}
            order by invoice_date desc nulls last, row_id
            """,
            (normalized_row_ids,),
        )
        return [payload for row in rows if (payload := self._invoice_row_from_sql(row))]

    @staticmethod
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

    def _invoice_row_from_sql(self, row: dict[str, Any]) -> dict[str, Any] | None:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            return None
        detail_fields = row_payload(row, "raw_payload")
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        if self._invoice_hidden_after_etc_submission(row, detail_fields):
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
            "status": "unpaired",
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

    def _active_pair_relations_for_month(self, month: str, row_ids: set[str]) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select case_id, relation_mode, month_scope, row_ids, row_types,
                   amount_check, special_metadata, source_versions, raw_payload
            from app.workbench_pair_relations relation
            where relation.status = 'active'
              and (
                    relation.row_ids && %s::text[]
                 or relation.month_scope = %s::date
                 or exists (
                        select 1
                        from unnest(relation.row_ids) member(row_id)
                        join app.bank_transactions bank
                          on coalesce(bank.legacy_mongo_id, bank.id::text) = member.row_id
                         and bank.status <> 'deleted'
                         and bank.txn_month = %s::date
                    )
                 or exists (
                        select 1
                        from unnest(relation.row_ids) member(row_id)
                        join app.invoices invoice
                          on coalesce(invoice.legacy_mongo_id, invoice.id::text) = member.row_id
                         and invoice.status <> 'deleted'
                         and invoice.invoice_month = %s::date
                    )
                 or exists (
                        select 1
                        from unnest(relation.row_ids) member(row_id)
                        join app.oa_applications oa
                          on oa.row_id = member.row_id
                         and oa.status <> 'deleted'
                         and coalesce(oa.scope_month, date_trunc('month', oa.application_date)::date) = %s::date
                    )
              )
            order by case_id
            """,
            (
                sorted(row_ids),
                month_start(month),
                month_start(month),
                month_start(month),
                month_start(month),
            ),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "raw_payload")
            payload = payload if isinstance(payload, dict) else {}
            result.append(
                {
                    **payload,
                    "case_id": str(row.get("case_id") or payload.get("case_id") or ""),
                    "relation_mode": row.get("relation_mode") or payload.get("relation_mode"),
                    "row_ids": [str(item) for item in list(row.get("row_ids") or payload.get("row_ids") or [])],
                    "row_types": [str(item) for item in list(row.get("row_types") or payload.get("row_types") or [])],
                    "amount_check": row_payload(row, "amount_check") or payload.get("amount_check") or {},
                    "special_metadata": row_payload(row, "special_metadata") or payload.get("special_metadata") or {},
                    "source_versions": row_payload(row, "source_versions") or payload.get("source_versions") or {},
                }
            )
        return result

    def _pending_claimed_bank_transaction_ids_for_month(self, month: str) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select bank_transaction_id
            from app.bank_transaction_relation_claims
            where status = 'active'
              and owner_type = 'oa_pending_payment_relation'
              and scope_month = %s::date
            order by bank_transaction_id
            """,
            (month_start(month),),
        )
        return _dedupe_text(row.get("bank_transaction_id") for row in rows)

    def _supplement_missing_relation_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> None:
        relation_row_ids = {
            str(row_id).strip()
            for relation in relations
            for row_id in list(relation.get("row_ids") or [])
            if str(row_id).strip()
        }
        missing_row_ids = relation_row_ids - set(rows_by_id)
        if not missing_row_ids:
            return
        for row in [
            *self._oa_projection_rows_by_ids(missing_row_ids),
            *self._bank_rows_by_ids(missing_row_ids),
            *self._invoice_rows_by_ids(missing_row_ids),
        ]:
            row_id = str(row.get("id") or "").strip()
            if row_id and row_id not in rows_by_id:
                rows_by_id[row_id] = row

    def _group_payload(
        self,
        month: str,
        rows_by_id: dict[str, dict[str, Any]],
        relations: list[dict[str, Any]],
    ) -> dict[str, Any]:
        working_rows_by_id = {row_id: dict(row) for row_id, row in rows_by_id.items()}
        formal_relation_row_ids = {
            normalized_row_id
            for relation in relations
            for row_id in list(relation.get("row_ids") or [])
            if (normalized_row_id := str(row_id).strip())
        }
        self._apply_workbench_overrides_and_exceptions(
            working_rows_by_id,
            formal_relation_row_ids=formal_relation_row_ids,
        )
        etc_summary_rows_by_external_batch_id = self._etc_invoice_summary_rows_for_relations(relations)
        for relation in relations:
            relation_row_ids = [row_id for row_id in list(relation.get("row_ids") or []) if row_id in working_rows_by_id]
            if not relation_row_ids:
                continue
            case_id = str(relation.get("case_id") or "")
            completion = evaluate_bank_relation_completion(
                row_types=list(relation.get("row_types") or []),
                special_metadata=(
                    relation.get("special_metadata")
                    if isinstance(relation.get("special_metadata"), dict)
                    else {}
                ),
                relation_mode=str(relation.get("relation_mode") or ""),
                amount_check=(
                    relation.get("amount_check")
                    if isinstance(relation.get("amount_check"), dict)
                    else None
                ),
            )
            relation_zone = "paired" if completion["is_complete"] else "unpaired"
            external_etc_batch_id = self._relation_external_etc_batch_id(relation)
            relation_amount_check = relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else None
            for row_id in relation_row_ids:
                row = working_rows_by_id[row_id]
                row["status"] = relation_zone
                row["case_id"] = case_id
                row["relation_mode"] = relation.get("relation_mode")
                self._apply_active_relation_metadata(row, relation)
                row[self._relation_field_name(str(row.get("type") or ""))] = self._active_relation_payload(
                    relation,
                    completion=completion,
                )
                if relation_amount_check:
                    row["relation_amount_check"] = deepcopy(relation_amount_check)
                if external_etc_batch_id and str(row.get("type") or "").strip() == "oa":
                    row["etc_batch_id"] = external_etc_batch_id
                    tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
                    if ETC_BATCH_TAG not in tags:
                        tags.append(ETC_BATCH_TAG)
                    row["tags"] = tags
                if str(relation.get("relation_mode") or "").strip() == NO_OA_BANK_BATCH_RELATION_MODE:
                    self._apply_no_oa_relation_metadata(row, relation)
            self._apply_relation_row_alignment(
                working_rows_by_id,
                relation,
                relation_row_ids=relation_row_ids,
            )
            if case_id and external_etc_batch_id:
                summary_row = etc_summary_rows_by_external_batch_id.get(external_etc_batch_id)
                if summary_row:
                    row = deepcopy(summary_row)
                    row["case_id"] = case_id
                    row["status"] = relation_zone
                    row["workbench_display_role"] = "summary"
                    row["relation_mode"] = relation.get("relation_mode")
                    self._apply_active_relation_metadata(row, relation)
                    row["invoice_bank_relation"] = {
                        "code": "fully_linked",
                        "label": "已关联ETC发票",
                        "tone": "success",
                    }
                    tags = list(row.get("tags") or [])
                    if "已关联ETC发票" not in tags:
                        tags.append("已关联ETC发票")
                    row["tags"] = tags
                    if relation_amount_check:
                        row["relation_amount_check"] = deepcopy(relation_amount_check)
                    working_rows_by_id[str(row["id"])] = row

        WorkbenchObjectIdentityArbitrationService(identity_policy=OBJECT_IDENTITY_POLICY).arbitrate_rows(
            working_rows_by_id
        )
        grouped = WorkbenchRelationGroupingService().group_payload(
            month,
            rows_by_id=working_rows_by_id,
            active_relations=relations,
        )
        grouped["oa_status"] = {"code": "ready", "message": "OA projection ready"}
        grouped["workbench_read_model_schema_version"] = WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION
        grouped["oa_attachment_invoice_parser_version"] = attachment_invoice_cache_parser_version()
        grouped["oa_projection_sync_version"] = OA_PROJECTION_SYNC_VERSION
        return grouped

    def _apply_relation_row_alignment(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        relation: dict[str, Any],
        *,
        relation_row_ids: list[str],
    ) -> None:
        if not relation_row_ids:
            return
        relation_for_alignment = {
            **relation,
            "row_ids": relation_row_ids,
        }
        alignment = WorkbenchRelationAlignmentService().align_relation(
            rows_by_id=rows_by_id,
            relation=relation_for_alignment,
        )
        if not alignment.get("links") and not alignment.get("unresolved_row_ids"):
            return
        for row_id in relation_row_ids:
            row = rows_by_id.get(row_id)
            if not isinstance(row, dict):
                continue
            metadata = row.get("special_metadata")
            row["special_metadata"] = dict(metadata) if isinstance(metadata, dict) else {}
            row["special_metadata"]["row_alignment"] = deepcopy(alignment)
        for link in list(alignment.get("links") or []):
            if not isinstance(link, dict):
                continue
            oa_row_id = str(link.get("oa_row_id") or "").strip()
            if not oa_row_id:
                continue
            for row_id in [*list(link.get("bank_row_ids") or []), *list(link.get("invoice_row_ids") or [])]:
                row = rows_by_id.get(str(row_id))
                if not isinstance(row, dict):
                    continue
                row["source_oa_id"] = oa_row_id
                row["source_oa_row_id"] = oa_row_id

    def _current_dirty_scope_source_version(self, scope_key: str) -> int:
        row = self._connection.fetch_one(
            """
            select source_version
            from job.read_model_dirty_scopes
            where tenant_id = 'default'
              and scope_type = 'workbench'
              and scope_key = %s
              and status in ('pending', 'processing')
            order by updated_at desc
            limit 1
            """,
            (scope_key,),
        )
        return _int_value(row.get("source_version") if isinstance(row, dict) else None, 0)

    def _apply_workbench_overrides_and_exceptions(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        *,
        formal_relation_row_ids: set[str] | None = None,
    ) -> None:
        if not rows_by_id:
            return
        row_ids = set(rows_by_id) - set(formal_relation_row_ids or ())
        if not row_ids:
            return
        row_overrides = self._row_overrides_for_rows(row_ids)
        exception_cases = self._active_exception_cases_for_rows(row_ids)
        if not row_overrides and not exception_cases:
            return
        override_service = WorkbenchOverrideService.from_snapshot(
            {"row_overrides": row_overrides}
        )
        override_row_ids = set(row_overrides)
        for row_id in row_overrides:
            row = rows_by_id.get(row_id)
            if row is None:
                continue
            rows_by_id[row_id] = override_service.apply_to_row(row)
        for case_payload in exception_cases:
            case_row_ids = [
                str(row_id).strip()
                for row_id in list(case_payload.get("row_ids") or [])
                if str(row_id).strip() in row_ids
                and str(row_id).strip() not in override_row_ids
            ]
            if not case_row_ids:
                continue
            projected_rows = override_service.apply_exception_projection(
                case_payload,
                [rows_by_id[row_id] for row_id in case_row_ids],
                candidate_evidence=list(case_payload.get("candidate_evidence") or []),
            )
            for projected in projected_rows:
                row_id = str(projected.get("id") or "").strip()
                if row_id:
                    rows_by_id[row_id] = projected

    def _row_overrides_for_rows(self, row_ids: set[str]) -> dict[str, dict[str, Any]]:
        if not row_ids:
            return {}
        rows = self._connection.fetch_all(
            """
            select row_id, override_payload, raw_payload
            from app.workbench_row_overrides
            where row_id = any(%s)
              and status = 'active'
            order by row_id
            """,
            (sorted(row_ids),),
        )
        result: dict[str, dict[str, Any]] = {}
        for row in rows:
            row_id = str(row.get("row_id") or "").strip()
            payload = row_payload(row, "override_payload", "raw_payload")
            if row_id and isinstance(payload, dict):
                result[row_id] = payload
        return result

    def _active_exception_cases_for_rows(self, row_ids: set[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select case_id, raw_payload
            from app.workbench_exception_cases
            where status = any(%s)
              and row_ids && %s::text[]
            order by updated_at, case_id
            """,
            (sorted(ACTIVE_CASE_STATUSES), sorted(row_ids)),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "raw_payload")
            if isinstance(payload, dict):
                payload.setdefault("id", row.get("case_id"))
                payload.setdefault("case_id", row.get("case_id"))
                result.append(payload)
        return result

    @staticmethod
    def _active_relation_payload(
        relation: dict[str, Any],
        *,
        completion: dict[str, object],
    ) -> dict[str, str]:
        missing_row_types = [str(value) for value in list(completion.get("missing_row_types") or [])]
        if missing_row_types:
            labels = {"oa": "OA", "invoice": "发票"}
            missing_label = "、".join(labels.get(row_type, row_type) for row_type in missing_row_types)
            return {
                "code": "relation_incomplete",
                "label": f"待补{missing_label}",
                "tone": "warning",
            }
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            special_metadata = {}
        if str(special_metadata.get("origin") or "").strip() == "oa_pending_payment_in_progress":
            return {"code": "oa_pending_payment_in_progress", "label": "已关联进行中OA", "tone": "success"}
        relation_mode = str(relation.get("relation_mode") or "").strip()
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            return {"code": NO_OA_BANK_BATCH_RELATION_MODE, "label": "免OA批量处理", "tone": "success"}
        if relation_mode == "turnover_manual_closure":
            return {"code": relation_mode, "label": "收支闭环", "tone": "success"}
        if relation_mode and relation_mode != "manual_confirmed":
            return {"code": relation_mode, "label": "已关联", "tone": "success"}
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

    @staticmethod
    def _apply_active_relation_metadata(row: dict[str, Any], relation: dict[str, Any]) -> None:
        special_metadata = relation.get("special_metadata")
        metadata_for_tags = special_metadata if isinstance(special_metadata, dict) else {}
        existing_metadata = row.get("special_metadata")
        merged_metadata = dict(existing_metadata) if isinstance(existing_metadata, dict) else {}
        merged_metadata["active_pair_relation"] = True
        merged_metadata["active_relation_case_id"] = str(relation.get("case_id") or "")
        if isinstance(special_metadata, dict) and special_metadata:
            merged_metadata.update(deepcopy(special_metadata))
        row["special_metadata"] = merged_metadata

        display_tags = [
            str(tag).strip()
            for tag in list(relation.get("display_tags") or metadata_for_tags.get("display_tags") or [])
            if str(tag).strip()
        ]
        if not display_tags:
            return
        existing_tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
        for tag in display_tags:
            if tag not in existing_tags:
                existing_tags.append(tag)
        row["tags"] = existing_tags
        row["display_tags"] = display_tags

    @staticmethod
    def _apply_no_oa_relation_metadata(row: dict[str, Any], relation: dict[str, Any]) -> None:
        special_metadata = relation.get("special_metadata")
        if not isinstance(special_metadata, dict):
            special_metadata = {}
        if special_metadata:
            row["special_metadata"] = deepcopy(special_metadata)

        display_tags = [
            str(tag).strip()
            for tag in list(relation.get("display_tags") or special_metadata.get("display_tags") or [])
            if str(tag).strip()
        ]
        batch_label = str(special_metadata.get("batch_label") or "").strip()
        if not display_tags:
            display_tags = ["免OA"]
            if batch_label:
                display_tags.append(batch_label)

        tags = [str(tag).strip() for tag in list(row.get("tags") or []) if str(tag).strip()]
        for tag in display_tags:
            if tag not in tags:
                tags.append(tag)
        row["tags"] = tags
        row["display_tags"] = display_tags

        source_batch_id = str(special_metadata.get("source_batch_id") or "").strip()
        actions = [str(action).strip() for action in list(row.get("available_actions") or []) if str(action).strip()]
        actions = ["detail"] if not actions else [action for action in actions if action in {"detail", "withdraw_no_oa_batch"}]
        withdrawable = (
            bool(special_metadata.get("withdrawable"))
            if "withdrawable" in special_metadata
            else bool(source_batch_id)
        )
        if source_batch_id and withdrawable and "withdraw_no_oa_batch" not in actions:
            actions.append("withdraw_no_oa_batch")
        row["available_actions"] = actions

    @staticmethod
    def _invoice_hidden_after_etc_submission(row: dict[str, Any], payload: dict[str, Any]) -> bool:
        return (
            str(row.get("workbench_visibility") or payload.get("workbench_visibility") or "").strip()
            == "hidden_after_etc_submission"
            or str(payload.get("etc_submission_status") or "").strip() == "submitted"
        )

    def _etc_invoice_summary_rows_for_relations(self, relations: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
        external_batch_ids = {
            external_batch_id
            for relation in relations
            if (external_batch_id := self._relation_external_etc_batch_id(relation))
        }
        if not external_batch_ids:
            return {}
        return self._etc_invoice_summary_rows(external_batch_ids=external_batch_ids)

    def _unpaired_etc_invoice_summary_rows(self, month: str) -> list[dict[str, Any]]:
        linked_external_batch_ids = self._active_etc_relation_external_batch_ids()
        return list(
            self._etc_invoice_summary_rows(
                month=month,
                excluded_external_batch_ids=linked_external_batch_ids,
            ).values()
        )

    def _etc_invoice_summary_rows(
        self,
        *,
        month: str | None = None,
        external_batch_ids: set[str] | None = None,
        excluded_external_batch_ids: set[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        normalized_external_batch_ids = {
            str(external_batch_id).strip()
            for external_batch_id in set(external_batch_ids or set())
            if str(external_batch_id).strip()
        }
        normalized_excluded_external_batch_ids = {
            str(external_batch_id).strip()
            for external_batch_id in set(excluded_external_batch_ids or set())
            if str(external_batch_id).strip()
        }
        filters = [
            "invoices.status <> 'deleted'",
            """
            (
                invoices.workbench_visibility = 'hidden_after_etc_submission'
             or invoices.raw_payload->'normalized_payload'->>'workbench_visibility' = 'hidden_after_etc_submission'
             or invoices.raw_payload->'normalized_payload'->>'etc_submission_status' = 'submitted'
            )
            """,
        ]
        params: list[Any] = []
        normalized_month = str(month or "").strip()
        if normalized_month:
            filters.append("invoices.invoice_month = %s::date")
            params.append(month_start(normalized_month))
        if normalized_external_batch_ids:
            filters.append("submitted_batches.external_etc_batch_id = any(%s)")
            params.append(sorted(normalized_external_batch_ids))
        if normalized_excluded_external_batch_ids:
            filters.append("submitted_batches.external_etc_batch_id <> all(%s)")
            params.append(sorted(normalized_excluded_external_batch_ids))
        where_clause = "\n              and ".join(filters)
        invoices_by_external_batch_id: dict[str, list[dict[str, Any]]] = defaultdict(list)
        batch_payload_by_external_batch_id: dict[str, dict[str, Any]] = {}

        def append_summary_source_row(row: dict[str, Any], *, batch_payload: dict[str, Any] | None = None) -> None:
            external_batch_id = str(row.get("external_etc_batch_id") or "").strip()
            if not external_batch_id:
                return
            existing_keys = {
                self._etc_invoice_summary_invoice_identity(existing)
                for existing in invoices_by_external_batch_id[external_batch_id]
            }
            invoice_key = self._etc_invoice_summary_invoice_identity(row)
            if invoice_key not in existing_keys:
                invoices_by_external_batch_id[external_batch_id].append(row)
            if batch_payload:
                existing_payload = batch_payload_by_external_batch_id.get(external_batch_id, {})
                batch_payload_by_external_batch_id[external_batch_id] = {**existing_payload, **batch_payload}

        link_rows = self._etc_invoice_summary_link_rows(
            normalized_month,
            normalized_external_batch_ids,
            normalized_excluded_external_batch_ids,
        )
        linked_external_batch_ids = self._etc_invoice_summary_link_source_ids(
            normalized_external_batch_ids,
            normalized_excluded_external_batch_ids,
        )
        business_external_batch_ids = self._etc_invoice_summary_business_source_ids(
            normalized_external_batch_ids,
            normalized_excluded_external_batch_ids,
        )
        for row in link_rows:
            append_summary_source_row(
                row,
                batch_payload=self._etc_business_summary_batch_payload(row),
            )

        rows = self._connection.fetch_all(
            f"""
            with submitted_batches as (
                select
                    submission_batch_id,
                    coalesce(nullif(raw_payload->'normalized_payload'->>'etc_batch_id', ''), submission_batch_id) as external_etc_batch_id,
                    raw_payload->'normalized_payload' as batch_payload
                from app.etc_submission_batches
                where status in ('submitted_confirmed', 'submitted', 'closed')
            )
            select
                submitted_batches.external_etc_batch_id,
                submitted_batches.batch_payload,
                coalesce(invoices.legacy_mongo_id, invoices.id::text) as row_id,
                invoices.invoice_type,
                invoices.invoice_no,
                invoices.invoice_code,
                invoices.digital_invoice_no,
                invoices.invoice_date,
                invoices.counterparty_name,
                invoices.seller_name,
                invoices.seller_tax_no,
                invoices.buyer_name,
                invoices.buyer_tax_no,
                invoices.amount,
                invoices.tax_rate,
                invoices.tax_amount,
                invoices.total_with_tax,
                invoices.status,
                invoices.workbench_visibility,
                invoices.raw_payload
            from app.invoices invoices
            join submitted_batches
              on submitted_batches.submission_batch_id = coalesce(invoices.raw_payload->'normalized_payload'->>'etc_submission_batch_id', '')
              or submitted_batches.external_etc_batch_id = coalesce(invoices.raw_payload->'normalized_payload'->>'etc_submission_batch_id', '')
            where {where_clause}
            order by submitted_batches.external_etc_batch_id, invoices.invoice_date, row_id
            """,
            tuple(params),
        )
        for row in rows:
            if str(row.get("external_etc_batch_id") or "").strip() in (
                linked_external_batch_ids | business_external_batch_ids
            ):
                continue
            batch_payload = row_payload(row, "batch_payload")
            append_summary_source_row(row, batch_payload=batch_payload if isinstance(batch_payload, dict) else None)

        business_rows = self._connection.fetch_all(
            f"""
            with submitted_business_batches as (
                select
                    business_batch_id,
                    task_id,
                    status,
                    scope_month,
                    invoice_count as business_invoice_count,
                    total_amount as business_total_amount,
                    coalesce(raw_payload->'normalized_payload', '{{}}'::jsonb) as business_batch_payload,
                    coalesce(
                        nullif(raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                        nullif(raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                        nullif(raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                        nullif(raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                        business_batch_id
                    ) as external_etc_batch_id,
                    coalesce(
                        nullif(raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                        nullif(raw_payload->'normalized_payload'->>'submissionBatchId', '')
                    ) as submission_batch_id
                from app.etc_business_batches
                where status in ('oa_submitted', 'manually_marked_submitted', 'closed')
            ),
            submitted_batches as (
                select
                    submission_batch_id,
                    raw_payload->'normalized_payload' as submission_batch_payload
                from app.etc_submission_batches
            )
            select
                business_batches.external_etc_batch_id,
                business_batches.business_batch_id,
                business_batches.business_invoice_count,
                business_batches.business_total_amount,
                business_batches.business_batch_payload,
                submitted_batches.submission_batch_payload,
                coalesce(etc_invoices.legacy_mongo_id, etc_invoices.etc_invoice_id, etc_invoices.id::text) as row_id,
                '进项发票' as invoice_type,
                etc_invoices.invoice_no,
                etc_invoices.invoice_code,
                etc_invoices.invoice_no as digital_invoice_no,
                etc_invoices.invoice_date,
                etc_invoices.seller_name as counterparty_name,
                etc_invoices.seller_name,
                etc_invoices.buyer_name,
                etc_invoices.amount,
                null as tax_rate,
                etc_invoices.tax_amount,
                etc_invoices.total_with_tax,
                etc_invoices.status,
                'hidden_after_etc_submission' as workbench_visibility,
                etc_invoices.raw_payload
            from submitted_business_batches business_batches
            left join submitted_batches
              on submitted_batches.submission_batch_id = business_batches.submission_batch_id
            join app.etc_invoices etc_invoices
              on exists (
                  select 1
                  from jsonb_array_elements_text(coalesce(business_batches.business_batch_payload->'invoice_ids', '[]'::jsonb)) invoice_ids(invoice_id)
                  where invoice_ids.invoice_id = etc_invoices.etc_invoice_id
                     or invoice_ids.invoice_id = coalesce(etc_invoices.legacy_mongo_id, '')
              )
            where {" and ".join(self._etc_business_summary_filters(
                normalized_month,
                normalized_external_batch_ids,
                normalized_excluded_external_batch_ids,
            ))}
            order by business_batches.external_etc_batch_id, etc_invoices.invoice_date, row_id
            """,
            tuple(
                self._etc_business_summary_params(
                    normalized_month,
                    normalized_external_batch_ids,
                    normalized_excluded_external_batch_ids,
                )
            ),
        )
        for row in business_rows:
            if str(row.get("external_etc_batch_id") or "").strip() in linked_external_batch_ids:
                continue
            append_summary_source_row(
                row,
                batch_payload=self._etc_business_summary_batch_payload(row),
            )
        return {
            external_batch_id: self._build_etc_invoice_summary_row(
                external_batch_id,
                invoices,
                batch_payload=batch_payload_by_external_batch_id.get(external_batch_id),
            )
            for external_batch_id, invoices in invoices_by_external_batch_id.items()
            if invoices
        }

    def _etc_invoice_summary_business_source_ids(
        self,
        external_batch_ids: set[str],
        excluded_external_batch_ids: set[str] | None = None,
    ) -> set[str]:
        batch_id_expr = """
            coalesce(
                nullif(batch.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                nullif(batch.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                batch.business_batch_id
            )
        """
        filters = [
            "batch.status in ('oa_submitted', 'manually_marked_submitted', 'closed')",
            "invoice.status <> 'deleted'",
        ]
        params: list[Any] = []
        if external_batch_ids:
            filters.append(f"{batch_id_expr} = any(%s)")
            params.append(sorted(external_batch_ids))
        if excluded_external_batch_ids:
            filters.append(f"{batch_id_expr} <> all(%s)")
            params.append(sorted(excluded_external_batch_ids))
        rows = self._connection.fetch_all(
            f"""
            select distinct {batch_id_expr} as external_etc_batch_id
            from app.etc_business_batches batch
            join lateral jsonb_array_elements_text(
                case when jsonb_typeof(batch.raw_payload->'normalized_payload'->'invoice_ids') = 'array'
                     then batch.raw_payload->'normalized_payload'->'invoice_ids' else '[]'::jsonb end
            ) member(invoice_id) on true
            join app.etc_invoices invoice
              on invoice.etc_invoice_id = member.invoice_id
              or coalesce(invoice.legacy_mongo_id, '') = member.invoice_id
            where {" and ".join(filters)}
            """,
            tuple(params),
        )
        return {
            str(row.get("external_etc_batch_id") or "").strip()
            for row in rows
            if str(row.get("external_etc_batch_id") or "").strip()
        }

    def _etc_invoice_summary_link_rows(
        self,
        month: str,
        external_batch_ids: set[str],
        excluded_external_batch_ids: set[str] | None = None,
    ) -> list[dict[str, Any]]:
        batch_id_expr = """
            coalesce(
                nullif(business_batches.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                links.business_batch_id
            )
        """
        filters = ["links.link_status = 'active'", "invoices.status <> 'deleted'"]
        params: list[Any] = []
        if month:
            filters.append(
                "coalesce(business_batches.scope_month, invoices.invoice_month) = %s::date"
            )
            params.append(month_start(month))
        if external_batch_ids:
            filters.append(f"{batch_id_expr} = any(%s)")
            params.append(sorted(external_batch_ids))
        if excluded_external_batch_ids:
            filters.append(f"{batch_id_expr} <> all(%s)")
            params.append(sorted(excluded_external_batch_ids))
        rows = self._connection.fetch_all(
            f"""
            select
                {batch_id_expr} as external_etc_batch_id,
                links.business_batch_id,
                business_batches.invoice_count as business_invoice_count,
                business_batches.total_amount as business_total_amount,
                coalesce(business_batches.raw_payload->'normalized_payload', '{{}}'::jsonb) as business_batch_payload,
                coalesce(invoices.legacy_mongo_id, invoices.id::text) as row_id,
                invoices.invoice_type,
                invoices.invoice_no,
                invoices.invoice_code,
                invoices.digital_invoice_no,
                invoices.invoice_date,
                invoices.counterparty_name,
                invoices.seller_name,
                invoices.seller_tax_no,
                invoices.buyer_name,
                invoices.buyer_tax_no,
                invoices.amount,
                invoices.tax_rate,
                invoices.tax_amount,
                invoices.total_with_tax,
                invoices.status,
                invoices.workbench_visibility,
                invoices.raw_payload
            from app.etc_batch_invoice_links links
            join app.invoices invoices
              on invoices.id = links.invoice_id
            left join app.etc_business_batches business_batches
              on business_batches.business_batch_id = links.business_batch_id
            where {" and ".join(filters)}
            order by external_etc_batch_id, invoices.invoice_date, row_id
            """,
            tuple(params),
        )
        return list(rows)

    def _etc_invoice_summary_link_source_ids(
        self,
        external_batch_ids: set[str],
        excluded_external_batch_ids: set[str] | None = None,
    ) -> set[str]:
        batch_id_expr = """
            coalesce(
                nullif(business_batches.raw_payload->'normalized_payload'->>'external_etc_batch_id', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'externalEtcBatchId', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'submission_batch_id', ''),
                nullif(business_batches.raw_payload->'normalized_payload'->>'submissionBatchId', ''),
                links.business_batch_id
            )
        """
        filters = ["links.link_status = 'active'", "invoices.status <> 'deleted'"]
        params: list[Any] = []
        if external_batch_ids:
            filters.append(f"{batch_id_expr} = any(%s)")
            params.append(sorted(external_batch_ids))
        if excluded_external_batch_ids:
            filters.append(f"{batch_id_expr} <> all(%s)")
            params.append(sorted(excluded_external_batch_ids))
        rows = self._connection.fetch_all(
            f"""
            select distinct {batch_id_expr} as external_etc_batch_id
            from app.etc_batch_invoice_links links
            join app.invoices invoices on invoices.id = links.invoice_id
            left join app.etc_business_batches business_batches
              on business_batches.business_batch_id = links.business_batch_id
            where {" and ".join(filters)}
            """,
            tuple(params),
        )
        return {
            str(row.get("external_etc_batch_id") or "").strip()
            for row in rows
            if str(row.get("external_etc_batch_id") or "").strip()
        }

    @staticmethod
    def _etc_business_summary_filters(
        month: str,
        external_batch_ids: set[str],
        excluded_external_batch_ids: set[str] | None = None,
    ) -> list[str]:
        filters = ["etc_invoices.status <> 'deleted'"]
        if month:
            filters.append("business_batches.scope_month = %s::date")
        if external_batch_ids:
            filters.append("business_batches.external_etc_batch_id = any(%s)")
        if excluded_external_batch_ids:
            filters.append("business_batches.external_etc_batch_id <> all(%s)")
        return filters

    @staticmethod
    def _etc_business_summary_params(
        month: str,
        external_batch_ids: set[str],
        excluded_external_batch_ids: set[str] | None = None,
    ) -> list[Any]:
        params: list[Any] = []
        if month:
            params.append(month_start(month))
        if external_batch_ids:
            params.append(sorted(external_batch_ids))
        if excluded_external_batch_ids:
            params.append(sorted(excluded_external_batch_ids))
        return params

    def _active_etc_relation_external_batch_ids(self) -> set[str]:
        rows = self._connection.fetch_all(
            """
            select amount_check, special_metadata
            from app.workbench_pair_relations
            where status = 'active'
              and (
                    nullif(amount_check->>'external_etc_batch_id', '') is not null
                 or nullif(amount_check->>'etc_batch_id', '') is not null
                 or nullif(special_metadata->>'external_etc_batch_id', '') is not null
                 or nullif(special_metadata->>'etc_batch_id', '') is not null
                 or nullif(special_metadata->'etc_batch_link'->>'external_etc_batch_id', '') is not null
                 or nullif(special_metadata->'etc_batch_link'->>'etc_batch_id', '') is not null
                 or nullif(special_metadata->'historical_etc_business_batch_migration'->>'external_etc_batch_id', '') is not null
                 or nullif(special_metadata->'historical_etc_business_batch_migration'->>'etc_batch_id', '') is not null
              )
            """,
            (),
        )
        return {
            external_batch_id
            for row in rows
            if (external_batch_id := relation_external_etc_batch_id(row))
        }

    @staticmethod
    def _etc_invoice_summary_invoice_identity(row: dict[str, Any]) -> str:
        for key in ("digital_invoice_no", "invoice_no", "row_id"):
            value = str(row.get(key) or "").strip()
            if value:
                return f"{key}:{value}"
        return f"row:{id(row)}"

    @staticmethod
    def _etc_business_summary_batch_payload(row: dict[str, Any]) -> dict[str, Any]:
        business_payload = row_payload(row, "business_batch_payload")
        submission_payload = row_payload(row, "submission_batch_payload")
        payload: dict[str, Any] = {}
        if isinstance(submission_payload, dict):
            payload.update(submission_payload)
        if isinstance(business_payload, dict):
            payload.update(business_payload)
        amount = (
            _nonzero_decimal_or_none(payload.get("oa_total_amount"))
            or _nonzero_decimal_or_none(payload.get("total_amount"))
            or _nonzero_decimal_or_none(row.get("business_total_amount"))
            or _nonzero_decimal_or_none(payload.get("etc_invoice_amount"))
            or _nonzero_decimal_or_none(
                (submission_payload or {}).get("oa_total_amount") if isinstance(submission_payload, dict) else None
            )
            or _nonzero_decimal_or_none(
                (submission_payload or {}).get("total_amount") if isinstance(submission_payload, dict) else None
            )
        )
        if amount is not None:
            payload["oa_total_amount"] = str(amount)
            payload["total_amount"] = str(amount)
        count = (
            _int_or_none(payload.get("etc_invoice_count"))
            or _int_or_none(row.get("business_invoice_count"))
            or _int_or_none(payload.get("invoice_count"))
        )
        if count is not None:
            payload["etc_invoice_count"] = count
        return payload

    def _build_etc_invoice_summary_row(
        self,
        external_batch_id: str,
        invoices: list[dict[str, Any]],
        *,
        batch_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        invoice_total_amount = sum((_decimal_value(row.get("total_with_tax") or row.get("amount")) for row in invoices), Decimal("0.00"))
        batch_payload = batch_payload if isinstance(batch_payload, dict) else {}
        total_amount = invoice_total_amount
        issue_dates = [_date_text(row.get("invoice_date")) for row in invoices if _date_text(row.get("invoice_date"))]
        seller_names = [
            str(row.get("seller_name") or row.get("counterparty_name") or "").strip()
            for row in invoices
            if str(row.get("seller_name") or row.get("counterparty_name") or "").strip()
        ]
        first_seller_name = seller_names[0] if seller_names else "ETC发票"
        count = len(invoices)
        title = f"ETC发票 {count} 张"
        issue_range = _date_range_label(issue_dates)
        total_amount_text = _money_text(total_amount)
        invoice_lines = [self._etc_invoice_summary_line(row) for row in invoices]
        detail_rows = [self._etc_invoice_detail_row(row, external_batch_id=external_batch_id) for row in invoices]
        return {
            "id": _etc_invoice_summary_row_id(external_batch_id),
            "type": "invoice",
            "case_id": None,
            "source_kind": "etc_invoice_summary",
            "seller_tax_no": "ETC批次",
            "seller_name": title,
            "buyer_tax_no": external_batch_id,
            "buyer_name": first_seller_name,
            "invoice_code": external_batch_id,
            "invoice_no": title,
            "digital_invoice_no": title,
            "issue_date": issue_range or "—",
            "amount": total_amount_text,
            "amount_value": str(total_amount),
            "tax_rate": "—",
            "tax_amount": "—",
            "total_with_tax": total_amount_text,
            "invoice_type": "进项发票",
            "invoice_bank_relation": {"code": "pending_oa_bank_match", "label": "待匹配OA/流水", "tone": "warn"},
            "tags": ["ETC", "ETC批量提交"],
            "etc_batch_id": external_batch_id,
            "etc_invoice_count": count,
            "etc_invoice_detail_count": len(detail_rows),
            "etc_invoice_detail_rows": detail_rows,
            "available_actions": ["detail"],
            "summary_fields": {
                "ETC批次": external_batch_id,
                "ETC发票数量": f"{count} 张",
                "ETC发票合计": total_amount_text,
                "开票日期范围": issue_range or "—",
                "代表销方": first_seller_name,
            },
            "detail_fields": {
                "ETC批次": external_batch_id,
                "ETC发票数量": f"{count} 张",
                "ETC发票合计": total_amount_text,
                "开票日期范围": issue_range or "—",
                "发票清单": "\n".join(invoice_lines) if invoice_lines else "—",
            },
        }

    @staticmethod
    def _relation_external_etc_batch_id(relation: dict[str, Any]) -> str:
        return relation_external_etc_batch_id(relation)

    @staticmethod
    def _etc_invoice_summary_line(row: dict[str, Any]) -> str:
        invoice_no = str(row.get("digital_invoice_no") or row.get("invoice_no") or "—")
        issue_date = _date_text(row.get("invoice_date")) or "—"
        seller_name = str(row.get("seller_name") or row.get("counterparty_name") or "—")
        amount = _money_text(_decimal_value(row.get("total_with_tax") or row.get("amount")))
        return f"{issue_date} ｜ {invoice_no} ｜ {seller_name} ｜ {amount}"

    @staticmethod
    def _etc_invoice_detail_row(row: dict[str, Any], *, external_batch_id: str) -> dict[str, Any]:
        row_id = str(row.get("row_id") or row.get("digital_invoice_no") or row.get("invoice_no") or "").strip()
        invoice_no = str(row.get("digital_invoice_no") or row.get("invoice_no") or row_id or "—").strip()
        issue_date = _date_text(row.get("invoice_date")) or "—"
        seller_name = str(row.get("seller_name") or row.get("counterparty_name") or "—").strip() or "—"
        amount = _money_text(_decimal_value(row.get("total_with_tax") or row.get("amount")))
        return {
            "id": row_id or f"{_etc_invoice_summary_row_id(external_batch_id)}:detail:{invoice_no}",
            "type": "invoice",
            "source_kind": "etc_invoice",
            "status": "paired",
            "seller_tax_no": "ETC发票",
            "seller_name": seller_name,
            "buyer_tax_no": external_batch_id,
            "buyer_name": str(row.get("buyer_name") or "—").strip() or "—",
            "invoice_code": str(row.get("invoice_code") or external_batch_id).strip() or external_batch_id,
            "invoice_no": invoice_no,
            "digital_invoice_no": invoice_no,
            "issue_date": issue_date,
            "amount": amount,
            "amount_value": str(_decimal_value(row.get("total_with_tax") or row.get("amount"))),
            "tax_rate": str(row.get("tax_rate") or "—"),
            "tax_amount": _money_text(_decimal_value(row.get("tax_amount"))) if row.get("tax_amount") not in (None, "") else "—",
            "total_with_tax": amount,
            "invoice_type": str(row.get("invoice_type") or "进项发票"),
            "tags": ["ETC", "ETC发票明细"],
            "etc_batch_id": external_batch_id,
            "invoice_bank_relation": {"code": "etc_batch_detail", "label": "ETC批次明细", "tone": "neutral"},
            "available_actions": ["detail"],
            "summary_fields": {
                "ETC批次": external_batch_id,
                "发票号码": invoice_no,
                "销方": seller_name,
                "金额": amount,
                "开票日期": issue_date,
            },
            "detail_fields": {
                "ETC批次": external_batch_id,
                "发票号码": invoice_no,
                "销方": seller_name,
                "金额": amount,
                "开票日期": issue_date,
            },
        }

    @staticmethod
    def _relation_field_name(row_type: str) -> str:
        if row_type == "oa":
            return "oa_bank_relation"
        if row_type == "bank":
            return "invoice_relation"
        return "invoice_bank_relation"

    @staticmethod
    def _empty_group(month: str, *, case_id: str, relation_mode: str) -> dict[str, Any]:
        return {
            "group_id": case_id,
            "case_id": case_id,
            "month": month,
            "relation_mode": relation_mode,
            "oa_rows": [],
            "bank_rows": [],
            "invoice_rows": [],
        }


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


def _oa_application_time(
    row: dict[str, Any],
    payload: dict[str, Any],
    detail_fields: dict[str, Any],
    summary_fields: dict[str, Any],
) -> str | None:
    return _first_text_or_none(
        payload.get("apply_time"),
        payload.get("application_time"),
        detail_fields.get("申请时间"),
        summary_fields.get("申请时间"),
        payload.get("application_date"),
        payload.get("apply_date"),
        detail_fields.get("申请日期"),
        summary_fields.get("申请日期"),
        row.get("application_date"),
        payload.get("date"),
        payload.get("created_at"),
        payload.get("updated_at"),
    )


def _oa_completed_time(
    row: dict[str, Any],
    payload: dict[str, Any],
    detail_fields: dict[str, Any],
    summary_fields: dict[str, Any],
) -> str | None:
    return _first_text_or_none(
        payload.get("completed_at"),
        detail_fields.get("审批完成时间"),
        summary_fields.get("审批完成时间"),
        payload.get("submitted_at"),
        payload.get("modified_time"),
        payload.get("modifiedTime"),
        row.get("approved_at"),
    )


def _first_text_or_none(*values: object) -> str | None:
    for value in values:
        normalized = _text_or_none(value)
        if normalized:
            return normalized
    return None


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


def _dedupe_text(values: Any) -> list[str]:
    result: list[str] = []
    for value in list(values or []):
        normalized = _text_or_none(value)
        if normalized is not None and normalized not in result:
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


def _decimal_value(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0").replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _decimal_or_none(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value).replace(",", "")).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        return None


def _oa_reconciliation_amount(payload: dict[str, Any], detail_fields: dict[str, Any]) -> str | None:
    explicit_amount = payload.get("reconciliation_amount")
    if explicit_amount not in (None, "", "--", "—"):
        parsed = _decimal_or_none(explicit_amount)
        return f"{parsed:.2f}" if parsed is not None else str(explicit_amount)
    amount_source = str(payload.get("amount_source") or detail_fields.get("金额来源") or "").strip()
    if amount_source not in {"header", "主表总金额"}:
        return None
    amount_mismatch = payload.get("amount_mismatch")
    if not isinstance(amount_mismatch, dict) and "金额差异" not in detail_fields:
        return None
    detail_sum = amount_mismatch.get("detail_sum") if isinstance(amount_mismatch, dict) else None
    detail_sum = detail_sum or detail_fields.get("明细金额合计")
    parsed = _decimal_or_none(detail_sum)
    return f"{parsed:.2f}" if parsed is not None else (str(detail_sum).strip() or None)


def _nonzero_decimal_or_none(value: object) -> Decimal | None:
    parsed = _decimal_or_none(value)
    if parsed is None or parsed == Decimal("0.00"):
        return None
    return parsed


def _money_text(value: Decimal) -> str:
    return f"{value.quantize(Decimal('0.01')):,.2f}"


def _date_range_label(values: list[str]) -> str:
    normalized = sorted(value[:10] for value in values if len(value) >= 10)
    if not normalized:
        return ""
    if normalized[0] == normalized[-1]:
        return normalized[0]
    return f"{normalized[0]} 至 {normalized[-1]}"


def _etc_invoice_summary_row_id(external_batch_id: str) -> str:
    safe_batch_id = re.sub(r"[^A-Za-z0-9_-]+", "-", external_batch_id).strip("-") or "unknown"
    return f"etc-summary-{safe_batch_id}"


def _is_outflow(direction: str, signed_amount: object) -> bool:
    normalized_direction = str(direction or "").strip().lower()
    if any(token in normalized_direction for token in ("支出", "付款", "out", "debit")):
        return True
    if any(token in normalized_direction for token in ("收入", "收款", "in", "credit")):
        return False
    try:
        return float(str(signed_amount or "0").replace(",", "")) < 0
    except ValueError:
        return True


def _int_value(value: object, default: int) -> int:
    if value in (None, ""):
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _int_or_none(value: object) -> int | None:
    if value in (None, ""):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
