from __future__ import annotations

from collections import defaultdict
from copy import deepcopy
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
import re
from types import SimpleNamespace
from typing import Any

from fin_ops_platform.services.bank_account_resolver import BankAccountResolver
from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_RELATION_MODE
from fin_ops_platform.services.object_identity_policy import FinancialObjectIdentityPolicy
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    OA_PROJECTION_SYNC_VERSION,
    PostgresOAProjectionAdapter,
    PostgresOAProjectionRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService
from fin_ops_platform.services.workbench_exception_case_service import ACTIVE_CASE_STATUSES
from fin_ops_platform.services.workbench_reconciliation_models import (
    DECISION_STATUS_OPEN,
    DECISION_STATUS_PAIRED,
    DISPLAY_STATE_OPEN,
    DISPLAY_STATE_PAIRED,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_object_identity_arbitration import WorkbenchObjectIdentityArbitrationService
from fin_ops_platform.services.workbench_query_service import (
    OA_ATTACHMENT_INVOICE_SOURCE_KIND,
    WorkbenchQueryService,
)
from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.workbench_special_pair_rule_service import (
    OA_INVOICE_OFFSET_AUTO_MATCH,
)


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
OBJECT_IDENTITY_POLICY = FinancialObjectIdentityPolicy()
WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION = "2026-06-turnover-bank-only-open-v1"
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
        resolved_source_version = _int_value(source_version, self._current_dirty_scope_source_version(normalized_scope))
        rows_by_id = self._workbench_rows_for_month(normalized_scope)
        relations = self._active_pair_relations_for_month(normalized_scope, set(rows_by_id))
        decisions = self._active_reconciliation_decisions_for_month(normalized_scope)
        self._supplement_missing_relation_rows(rows_by_id, relations)
        self._supplement_missing_decision_rows(rows_by_id, decisions)
        payload = self._group_payload(
            normalized_scope,
            rows_by_id,
            relations,
            decisions=decisions,
        )
        snapshot = {
            "read_models": {
                normalized_scope: {
                    "scope_key": normalized_scope,
                    "scope_month": normalized_scope,
                    "generated_at": datetime.now().isoformat(),
                    "cache_status": "fresh",
                    "payload": payload,
                    "source_versions": {
                        "builder": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
                        "source_version": resolved_source_version,
                        "bank_auto_tag_rules_version": self._current_bank_auto_tag_rules_version(),
                        "oa_attachment_invoice_parser_version": MongoOAAdapter._attachment_invoice_cache_parser_version(),
                        "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
                    },
                }
            }
        }
        self._read_model_repository.save_workbench_read_models(
            snapshot,
            changed_scope_keys={normalized_scope},
            refresh_all_scope_from_month_shards=False,
        )
        row_count = sum(len(group.get(f"{kind}_rows") or []) for group in payload["paired"]["groups"] + payload["open"]["groups"] for kind in ("oa", "bank", "invoice"))
        return {
            "scope_key": normalized_scope,
            "base_scope_key": normalized_scope,
            "row_count": row_count,
            "ignored_row_count": 0,
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

    def refresh_workbench_all_scope_from_active_shards(
        self,
        scope_key: str = "all",
        *,
        source_version: int | str | None = None,
    ) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip() or "all"
        if normalized_scope != "all":
            raise ValueError("workbench all-scope aggregation requires scope_key='all'.")
        self._read_model_repository.save_workbench_read_models({"read_models": {}}, changed_scope_keys={"all"})
        status = self._read_model_repository.get_workbench_refresh_status(scope_key="all")
        if str(status.get("read_model_status") or "").strip() == "failed":
            raise RuntimeError(str(status.get("last_error") or "Workbench all-scope aggregation failed."))
        return {
            "scope_key": "all",
            "base_scope_key": "all",
            "projection": "sql",
            "aggregate_only": True,
            "source_version": source_version,
            "read_model_status": status.get("read_model_status") or "fresh",
            "active_generation_id": status.get("active_generation_id"),
            "row_count": 0,
            "ignored_row_count": 0,
        }

    def _workbench_rows_for_month(self, month: str) -> dict[str, dict[str, Any]]:
        rows: dict[str, dict[str, Any]] = {}
        for row in self._oa_projection_rows(month):
            rows[str(row["id"])] = row
        for row in self._bank_rows(month):
            rows[str(row["id"])] = row
        for row in self._invoice_rows(month):
            rows[str(row["id"])] = row
        for row in self._open_etc_invoice_summary_rows(month):
            rows[str(row["id"])] = row
        return rows

    def _oa_projection_rows(self, month: str) -> list[dict[str, Any]]:
        self._oa_query_service.get_workbench(month)
        result: list[dict[str, Any]] = []
        oa_rows_by_id: dict[str, dict[str, Any]] = {}
        for row in self._oa_query_service.list_record_snapshots():
            row_month = str(row.get("_month") or "").strip()
            row_type = str(row.get("type") or "").strip()
            if row_month != month or row_type not in {"oa", "invoice"}:
                continue
            if row_type == "invoice" and str(row.get("source_kind") or "").strip() != OA_ATTACHMENT_INVOICE_SOURCE_KIND:
                continue
            payload = self._oa_query_service.serialize_row(row)
            payload["status"] = "open"
            payload.setdefault("source_kind", payload.get("type") or row_type)
            result.append(payload)
            if row_type == "oa":
                oa_rows_by_id[str(payload.get("id") or "")] = payload
        result.extend(self._attachment_invoice_rows_from_expense_items(month, oa_rows_by_id))
        return result

    def _oa_projection_rows_by_ids(self, row_ids: set[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        oa_row_ids = {row_id for row_id in row_ids if row_id.startswith("oa-") and not row_id.startswith("oa-att-")}
        attachment_parent_ids = {
            match.group("oa_id")
            for row_id in row_ids
            if (match := re.match(r"^oa-att-(?:inv|pay|unk)-(?P<oa_id>oa-[^-]+-\d+)-", row_id))
        }
        wanted = set(row_ids)
        self._oa_query_service.sync_oa_row_ids(sorted(oa_row_ids | attachment_parent_ids))
        result: list[dict[str, Any]] = []
        for row in self._oa_query_service.list_record_snapshots():
            row_id = str(row.get("id") or "").strip()
            if row_id not in wanted:
                continue
            payload = self._oa_query_service.serialize_row(row)
            payload["status"] = "open"
            payload.setdefault("source_kind", payload.get("type") or row.get("type"))
            result.append(payload)
        if attachment_parent_ids:
            oa_rows_by_id = {
                str(row.get("id") or ""): self._oa_query_service.serialize_row(row)
                for row in self._oa_query_service.list_record_snapshots()
                if str(row.get("id") or "") in attachment_parent_ids and str(row.get("type") or "") == "oa"
            }
            result.extend(
                row
                for row in self._attachment_invoice_rows_from_expense_items("all", oa_rows_by_id)
                if str(row.get("id") or "") in wanted
            )
        return result

    def _attachment_invoice_rows_from_expense_items(
        self,
        month: str,
        oa_rows_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        if not oa_rows_by_id:
            return []
        structured = self._attachment_invoice_rows_from_structured_oa_tables(month, oa_rows_by_id)
        structured_ids = {str(row.get("id") or "") for row in structured}
        structured_attachment_keys = {
            str(row.get("source_attachment_key") or "").strip()
            for row in structured
            if str(row.get("source_attachment_key") or "").strip()
        }
        structured_attachment_identities = {
            identity
            for row in structured
            if (identity := self._attachment_source_identity(row)) is not None
        }
        rows = self._connection.fetch_all(
            """
            select row_id, scope_month, normalized_payload, raw_payload
            from app.oa_applications
            where row_id = any(%s)
              and (%s = 'all' or scope_month = %s::date)
            order by row_id
            """,
            (sorted(oa_rows_by_id), month, month_start(month) if month != "all" else None),
        )
        result: list[dict[str, Any]] = []
        seen: set[str] = set(structured_ids)
        for row in rows:
            payload = row_payload(row, "normalized_payload", "raw_payload")
            if not isinstance(payload, dict):
                continue
            oa_row_id = str(row.get("row_id") or payload.get("id") or "").strip()
            oa_row = oa_rows_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict):
                continue
            attachment_evidences = self._attachment_evidences_from_expense_items(payload)
            if structured_attachment_keys:
                attachment_evidences = [
                    evidence
                    for evidence in attachment_evidences
                    if str(evidence.get("source_attachment_key") or "").strip() not in structured_attachment_keys
                    and self._attachment_source_identity(evidence) not in structured_attachment_identities
                ]
            if not attachment_evidences:
                continue
            record = SimpleNamespace(attachment_evidences=attachment_evidences, attachment_invoices=[])
            internal_oa_row = {
                **dict(oa_row),
                "_month": str(row.get("scope_month") or "")[:7] or str(oa_row.get("month") or month),
                "_section": "paired" if str(oa_row.get("status") or "") == "paired" else "open",
                "_detail_fields": dict(oa_row.get("detail_fields") if isinstance(oa_row.get("detail_fields"), dict) else {}),
            }
            for attachment_row in self._oa_query_service._build_attachment_invoice_rows(record, oa_row=internal_oa_row):
                serialized = self._oa_query_service.serialize_row(attachment_row)
                row_id = str(serialized.get("id") or "").strip()
                if not row_id or row_id in seen:
                    continue
                seen.add(row_id)
                serialized["status"] = "open"
                serialized.setdefault("source_kind", serialized.get("source_kind") or "oa_attachment_invoice")
                result.append(serialized)
        return [*structured, *result]

    def _attachment_invoice_rows_from_structured_oa_tables(
        self,
        month: str,
        oa_rows_by_id: dict[str, dict[str, Any]],
    ) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select
                oa.row_id as oa_row_id,
                oa.scope_month,
                item.normalized_payload as item_payload,
                attachment.normalized_payload as attachment_payload,
                cache.cache_source_attachment_key,
                coalesce(cache.invoices, '[]'::jsonb) as cache_invoices,
                coalesce(cache.evidences, '[]'::jsonb) as cache_evidences,
                coalesce(
                    case
                        when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                        else '[]'::jsonb
                    end,
                    '[]'::jsonb
                ) as cache_artifacts
            from app.oa_application_items item
            join app.oa_applications oa on oa.id = item.oa_application_id
            left join app.oa_attachments attachment
              on attachment.oa_application_id = oa.id
             and (
                    attachment.row_id = item.row_id
                    or attachment.normalized_payload->>'source_expense_item_id' = item.row_id
                 )
            left join lateral (
                select matched.cache_source_attachment_key, matched.invoices, matched.evidences, matched.artifacts
                from (
                    select
                        0 as match_rank,
                        source.cache_source_attachment_key,
                        cache.parsed_at,
                        cache.invoices,
                        cache.evidences,
                        cache.artifacts
                    from app.oa_attachment_invoice_cache_sources source
                    join app.oa_attachment_invoice_cache cache
                      on cache.source_attachment_key = source.cache_source_attachment_key
                    where source.source_attachment_key = attachment.source_attachment_key
                    union all
                    select
                        1 as match_rank,
                        cache.source_attachment_key as cache_source_attachment_key,
                        cache.parsed_at,
                        cache.invoices,
                        cache.evidences,
                        cache.artifacts
                    from app.oa_attachment_invoice_cache cache
                    where nullif(
                            coalesce(
                                item.normalized_payload->>'expense_item_id',
                                item.normalized_payload->>'row_id'
                            ),
                            ''
                          ) is not null
                      and nullif(
                            coalesce(
                                attachment.normalized_payload->>'source_attachment_name',
                                attachment.normalized_payload->>'attachment_name',
                                attachment.normalized_payload->>'fileName',
                                attachment.normalized_payload->>'filename'
                            ),
                            ''
                          ) is not null
                      and exists (
                            select 1
                            from jsonb_array_elements(
                                coalesce(cache.invoices, '[]'::jsonb)
                                || coalesce(cache.evidences, '[]'::jsonb)
                                || coalesce(
                                    case
                                        when jsonb_typeof(cache.artifacts) = 'array' then cache.artifacts
                                        else '[]'::jsonb
                                    end,
                                    '[]'::jsonb
                                )
                            ) as evidence(value)
                            where nullif(evidence.value->>'source_expense_item_id', '') = nullif(
                                    coalesce(
                                        item.normalized_payload->>'expense_item_id',
                                        item.normalized_payload->>'row_id'
                                    ),
                                    ''
                                  )
                              and nullif(
                                    coalesce(
                                        evidence.value->>'source_attachment_name',
                                        evidence.value->>'attachment_name',
                                        evidence.value->>'fileName',
                                        evidence.value->>'filename'
                                    ),
                                    ''
                                  ) = nullif(
                                    coalesce(
                                        attachment.normalized_payload->>'source_attachment_name',
                                        attachment.normalized_payload->>'attachment_name',
                                        attachment.normalized_payload->>'fileName',
                                        attachment.normalized_payload->>'filename'
                                    ),
                                    ''
                                  )
                        )
                ) matched
                order by matched.match_rank, matched.parsed_at desc nulls last, matched.cache_source_attachment_key
                limit 1
            ) cache on true
            where oa.row_id = any(%s)
              and (%s = 'all' or oa.scope_month = %s::date)
            order by oa.row_id, item.row_id, attachment.source_attachment_key
            """,
            (sorted(oa_rows_by_id), month, month_start(month) if month != "all" else None),
        )
        evidence_by_oa_id: dict[str, list[dict[str, Any]]] = {}
        scope_month_by_oa_id: dict[str, str] = {}
        for row in rows:
            oa_row_id = str(row.get("oa_row_id") or "").strip()
            if not oa_row_id or oa_row_id not in oa_rows_by_id:
                continue
            scope_month_by_oa_id[oa_row_id] = str(row.get("scope_month") or "")[:7]
            item_payload = row.get("item_payload") if isinstance(row.get("item_payload"), dict) else {}
            attachment_payload = row.get("attachment_payload") if isinstance(row.get("attachment_payload"), dict) else {}
            source_expense_item_id = item_payload.get("expense_item_id") or item_payload.get("row_id")
            source_expense_row_index = item_payload.get("row_index") or item_payload.get("item_no")
            source_attachment_key = attachment_payload.get("source_attachment_key")
            source_attachment_name = (
                attachment_payload.get("source_attachment_name")
                or attachment_payload.get("attachment_name")
                or attachment_payload.get("filename")
            )
            source_attachment_key_text = str(source_attachment_key or "").strip()
            cache_source_attachment_key = str(row.get("cache_source_attachment_key") or "").strip()
            cache_artifacts = row.get("cache_artifacts") if isinstance(row.get("cache_artifacts"), list) else []
            for evidence in self._select_structured_attachment_evidences(
                invoices=row.get("cache_invoices") if isinstance(row.get("cache_invoices"), list) else [],
                evidences=row.get("cache_evidences") if isinstance(row.get("cache_evidences"), list) else [],
                artifacts=cache_artifacts,
            ):
                if not isinstance(evidence, dict):
                    continue
                evidence_attachment_key = str(evidence.get("source_attachment_key") or "").strip()
                allowed_attachment_keys = {
                    key for key in (source_attachment_key_text, cache_source_attachment_key) if key
                }
                evidence_source_identity_matches_attachment = (
                    str(evidence.get("source_expense_item_id") or "").strip() == str(source_expense_item_id or "").strip()
                    and str(
                        evidence.get("source_attachment_name")
                        or evidence.get("attachment_name")
                        or evidence.get("fileName")
                        or evidence.get("filename")
                        or ""
                    ).strip() == str(source_attachment_name or "").strip()
                )
                if (
                    allowed_attachment_keys
                    and evidence_attachment_key
                    and evidence_attachment_key not in allowed_attachment_keys
                    and not evidence_source_identity_matches_attachment
                ):
                    continue
                normalized = dict(evidence)
                normalized.setdefault("source_expense_item_id", source_expense_item_id)
                normalized.setdefault("source_expense_row_index", source_expense_row_index)
                if cache_source_attachment_key:
                    normalized.setdefault("cache_source_attachment_key", cache_source_attachment_key)
                normalized["source_attachment_key"] = source_attachment_key_text or evidence_attachment_key
                normalized.setdefault("source_attachment_name", source_attachment_name)
                evidence_by_oa_id.setdefault(oa_row_id, []).append(normalized)
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for oa_row_id, attachment_evidences in evidence_by_oa_id.items():
            oa_row = oa_rows_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict) or not attachment_evidences:
                continue
            attachment_evidences = self._dedupe_attachment_evidences_by_source_identity(attachment_evidences)
            record = SimpleNamespace(attachment_evidences=attachment_evidences, attachment_invoices=[])
            internal_oa_row = {
                **dict(oa_row),
                "_month": scope_month_by_oa_id.get(oa_row_id) or str(oa_row.get("month") or month),
                "_section": "paired" if str(oa_row.get("status") or "") == "paired" else "open",
                "_detail_fields": dict(oa_row.get("detail_fields") if isinstance(oa_row.get("detail_fields"), dict) else {}),
            }
            for attachment_row in self._oa_query_service._build_attachment_invoice_rows(record, oa_row=internal_oa_row):
                serialized = self._oa_query_service.serialize_row(attachment_row)
                row_id = str(serialized.get("id") or "").strip()
                if not row_id or row_id in seen:
                    continue
                seen.add(row_id)
                serialized["status"] = "open"
                serialized.setdefault("source_kind", serialized.get("source_kind") or "oa_attachment_invoice")
                result.append(serialized)
        return result

    @classmethod
    def _select_structured_attachment_evidences(
        cls,
        *,
        invoices: list[Any],
        evidences: list[Any],
        artifacts: list[Any],
    ) -> list[dict[str, Any]]:
        parsed_payloads = [
            dict(payload)
            for payload in [*invoices, *evidences]
            if isinstance(payload, dict) and _is_formal_attachment_invoice_evidence(payload)
        ]
        if parsed_payloads:
            return cls._dedupe_structured_attachment_evidences(parsed_payloads)

        artifact_payloads = [
            dict(payload)
            for payload in artifacts
            if (
                isinstance(payload, dict)
                and _looks_like_invoice_artifact(payload)
                and _is_formal_attachment_invoice_evidence(payload)
            )
        ]
        return cls._dedupe_structured_attachment_evidences(artifact_payloads)

    @classmethod
    def _dedupe_structured_attachment_evidences(cls, evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        result: list[dict[str, Any]] = []
        seen: set[tuple[str, ...]] = set()
        for evidence in evidences:
            identity = cls._structured_attachment_evidence_identity(evidence)
            if identity in seen:
                continue
            seen.add(identity)
            result.append(evidence)
        return result

    @staticmethod
    def _structured_attachment_evidence_identity(evidence: dict[str, Any]) -> tuple[str, ...]:
        def clean(value: Any) -> str:
            text = str(value or "").strip()
            return "" if text in {"—", "--"} else text

        return (
            clean(evidence.get("source_attachment_key")),
            clean(evidence.get("invoice_no")),
            clean(evidence.get("digital_invoice_no")),
            clean(evidence.get("issue_date")),
            clean(evidence.get("seller_tax_no")),
            clean(evidence.get("seller_name")),
            clean(evidence.get("buyer_tax_no")),
            clean(evidence.get("buyer_name")),
            clean(evidence.get("total_with_tax") or evidence.get("amount")),
            clean(evidence.get("tax_amount")),
            clean(evidence.get("evidence_type")),
            clean(evidence.get("transaction_no") or evidence.get("merchant_order_no")),
        )

    @classmethod
    def _dedupe_attachment_evidences_by_source_identity(cls, evidences: list[dict[str, Any]]) -> list[dict[str, Any]]:
        by_identity: dict[tuple[str, str], dict[str, Any]] = {}
        passthrough: list[dict[str, Any]] = []
        for evidence in evidences:
            identity = cls._attachment_source_identity(evidence)
            if identity is None:
                passthrough.append(evidence)
                continue
            current = by_identity.get(identity)
            if current is None or cls._attachment_evidence_quality_score(evidence) > cls._attachment_evidence_quality_score(current):
                by_identity[identity] = evidence
        return [*by_identity.values(), *passthrough]

    @staticmethod
    def _attachment_evidence_quality_score(evidence: dict[str, Any]) -> int:
        score = 0
        for key in (
            "digital_invoice_no",
            "invoice_no",
            "invoice_code",
            "seller_tax_no",
            "seller_name",
            "buyer_tax_no",
            "buyer_name",
            "total_with_tax",
            "tax_amount",
            "transaction_no",
            "merchant_order_no",
        ):
            value = str(evidence.get(key) or "").strip()
            if value and value not in {"—", "--"}:
                score += 1
        return score

    @staticmethod
    def _attachment_source_identity(evidence: dict[str, Any]) -> tuple[str, str] | None:
        source_expense_item_id = str(evidence.get("source_expense_item_id") or "").strip()
        source_attachment_name = str(
            evidence.get("source_attachment_name")
            or evidence.get("attachment_name")
            or evidence.get("fileName")
            or evidence.get("filename")
            or ""
        ).strip()
        if not source_expense_item_id or not source_attachment_name:
            return None
        return (source_expense_item_id, source_attachment_name)

    @staticmethod
    def _attachment_evidences_from_expense_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        evidences: list[dict[str, Any]] = []
        for item in list(payload.get("expense_items") or []):
            if not isinstance(item, dict):
                continue
            source_expense_item_id = item.get("expense_item_id")
            source_expense_row_index = item.get("row_index")
            parsed_evidences = [
                evidence
                for source_key in ("attachment_invoices", "attachment_evidences")
                for evidence in list(item.get(source_key) or [])
                if isinstance(evidence, dict)
            ]
            parsed_attachment_keys = {
                str(evidence.get("source_attachment_key") or "").strip()
                for evidence in parsed_evidences
                if str(evidence.get("source_attachment_key") or "").strip()
            }
            item_evidences = [*parsed_evidences]
            for artifact in list(item.get("attachment_artifacts") or []):
                if not isinstance(artifact, dict):
                    continue
                normalized_artifact = dict(artifact)
                artifact_attachment_key = str(normalized_artifact.get("source_attachment_key") or "").strip()
                if artifact_attachment_key and artifact_attachment_key in parsed_attachment_keys:
                    continue
                if not _looks_like_invoice_artifact(normalized_artifact):
                    continue
                item_evidences.append(normalized_artifact)
            file_offset = len(item_evidences)
            for file_index, attachment_file in enumerate(list(item.get("attachment_files") or [])):
                if not isinstance(attachment_file, dict):
                    continue
                normalized_file = dict(attachment_file)
                if not _looks_like_invoice_artifact(normalized_file):
                    continue
                file_attachment_key = str(normalized_file.get("source_attachment_key") or "").strip()
                if file_attachment_key and file_attachment_key in parsed_attachment_keys:
                    continue
                normalized_file.setdefault("source_attachment_name", normalized_file.get("fileName") or normalized_file.get("filename"))
                normalized_file.setdefault("attachment_name", normalized_file.get("source_attachment_name"))
                normalized_file.setdefault(
                    "source_attachment_key",
                    _fallback_attachment_source_key(
                        payload,
                        source_expense_item_id=source_expense_item_id,
                        fallback_index=file_offset + file_index,
                        attachment=normalized_file,
                    ),
                )
                item_evidences.append(normalized_file)

            normalized_item_evidences: list[dict[str, Any]] = []
            for item_evidence in item_evidences:
                normalized_item_evidence = dict(item_evidence)
                normalized_item_evidence.setdefault("source_expense_item_id", source_expense_item_id)
                normalized_item_evidence.setdefault("source_expense_row_index", source_expense_row_index)
                normalized_item_evidences.append(normalized_item_evidence)
            deduped_item_evidences = WorkbenchSqlProjectionBuilder._dedupe_attachment_evidences_by_source_identity(
                normalized_item_evidences
            )
            for evidence in WorkbenchSqlProjectionBuilder._dedupe_structured_attachment_evidences(deduped_item_evidences):
                evidences.append(evidence)
        return evidences

    def _legacy_oa_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select row_id, applicant, application_date, project_name, amount, status, normalized_payload, raw_payload
            from app.oa_applications
            where scope_month = %s::date
            order by row_id
            """,
            (month_start(month),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
            payload = row_payload(row, "normalized_payload", "raw_payload")
            payload = payload if isinstance(payload, dict) else {}
            row_id = str(row.get("row_id") or payload.get("id") or "").strip()
            if not row_id:
                continue
            result.append(
                {
                    "id": row_id,
                    "type": "oa",
                    "source_kind": "oa",
                    "status": "open",
                    "applicant": row.get("applicant") or payload.get("applicant"),
                    "date": _date_text(row.get("application_date") or payload.get("date")),
                    "project_name": row.get("project_name") or payload.get("project_name"),
                    "amount": str(row.get("amount") or payload.get("amount") or ""),
                    "reason": payload.get("reason"),
                    "summary_fields": payload.get("summary_fields") if isinstance(payload.get("summary_fields"), dict) else {},
                    "detail_fields": payload.get("detail_fields") if isinstance(payload.get("detail_fields"), dict) else {},
                }
            )
        return result

    def _bank_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, account_no, account_name,
                   txn_direction, counterparty_name_raw, amount, txn_date, trade_time,
                   summary, remark, project_id, raw_payload
            from app.bank_transactions
            where txn_month = %s::date
              and status <> 'deleted'
            order by coalesce(trade_time, txn_date::timestamptz) desc, row_id
            """,
            (month_start(month),),
        )
        result: list[dict[str, Any]] = []
        for row in rows:
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
            "status": "open",
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
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
                   digital_invoice_no, invoice_date, counterparty_name, seller_name, seller_tax_no,
                   buyer_name, buyer_tax_no, amount, tax_rate, tax_amount, total_with_tax, status,
                   workbench_visibility, raw_payload
            from app.invoices
            where invoice_month = %s::date
              and status <> 'deleted'
              and coalesce(workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'workbench_visibility', 'visible') <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
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
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no, invoice_code,
                   digital_invoice_no, invoice_date, counterparty_name, seller_name, seller_tax_no,
                   buyer_name, buyer_tax_no, amount, tax_rate, tax_amount, total_with_tax, status,
                   workbench_visibility, raw_payload
            from app.invoices
            where coalesce(legacy_mongo_id, id::text) = any(%s)
              and status <> 'deleted'
              and coalesce(workbench_visibility, 'visible') <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'workbench_visibility', 'visible') <> 'hidden_after_etc_submission'
              and coalesce(raw_payload->'normalized_payload'->>'etc_submission_status', '') <> 'submitted'
            order by invoice_date desc nulls last, row_id
            """,
            (normalized_row_ids,),
        )
        return [payload for row in rows if (payload := self._invoice_row_from_sql(row))]

    def _invoice_row_from_sql(self, row: dict[str, Any]) -> dict[str, Any] | None:
        row_id = str(row.get("row_id") or "").strip()
        if not row_id:
            return None
        detail_fields = row_payload(row, "raw_payload")
        detail_fields = detail_fields if isinstance(detail_fields, dict) else {}
        if self._invoice_hidden_after_etc_submission(row, detail_fields):
            return None
        invoice_code = _first_display_value(row.get("invoice_code"), detail_fields.get("发票代码"))
        invoice_no = _first_display_value(row.get("invoice_no"), detail_fields.get("发票号码"))
        digital_invoice_no = _first_display_value(row.get("digital_invoice_no"), detail_fields.get("数电发票号码"))
        tax_rate = _first_display_value(row.get("tax_rate"), detail_fields.get("税率"), detail_fields.get("tax_rate"))
        tax_amount = _first_display_value(row.get("tax_amount"), detail_fields.get("税额"), detail_fields.get("tax_amount"))
        return {
            "id": row_id,
            "type": "invoice",
            "source_kind": "invoice",
            "status": "open",
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
            },
            "detail_fields": detail_fields,
        }

    def _active_pair_relations_for_month(self, month: str, row_ids: set[str]) -> list[dict[str, Any]]:
        if not row_ids:
            return []
        rows = self._connection.fetch_all(
            """
            select case_id, relation_mode, month_scope, row_ids, row_types, raw_payload
            from app.workbench_pair_relations
            where status = 'active'
              and (month_scope is null or month_scope = %s::date)
              and row_ids && %s::text[]
            order by case_id
            """,
            (month_start(month), sorted(row_ids)),
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
                }
            )
        return result

    def _active_reconciliation_decisions_for_month(self, month: str) -> list[dict[str, Any]]:
        list_decisions = getattr(self._read_model_repository, "list_workbench_reconciliation_decisions", None)
        if not callable(list_decisions):
            return []
        return [
            decision
            for decision in list_decisions(
                tenant_id="default",
                scope_month=month,
                statuses={DECISION_STATUS_PAIRED, DECISION_STATUS_OPEN},
            )
            if self._decision_is_projectable(decision)
        ]

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

    def _supplement_missing_decision_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        decisions: list[dict[str, Any]],
    ) -> None:
        decision_row_ids = {
            str(row_id).strip()
            for decision in decisions
            for row_id in list(decision.get("row_ids") or [])
            if str(row_id).strip()
        }
        missing_row_ids = decision_row_ids - set(rows_by_id)
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
        *,
        decisions: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        working_rows_by_id = {row_id: dict(row) for row_id, row in rows_by_id.items()}
        self._apply_workbench_overrides_and_exceptions(working_rows_by_id)
        etc_summary_rows_by_external_batch_id = self._etc_invoice_summary_rows_for_relations(relations)
        paired_row_ids: set[str] = set()
        for relation in relations:
            relation_row_ids = [row_id for row_id in list(relation.get("row_ids") or []) if row_id in working_rows_by_id]
            relation_row_ids.extend(
                row_id
                for row_id in self._attachment_row_ids_for_relation(relation, working_rows_by_id)
                if row_id not in relation_row_ids
            )
            if not relation_row_ids:
                continue
            case_id = str(relation.get("case_id") or "")
            external_etc_batch_id = self._relation_external_etc_batch_id(relation)
            relation_amount_check = relation.get("amount_check") if isinstance(relation.get("amount_check"), dict) else None
            for row_id in relation_row_ids:
                paired_row_ids.add(row_id)
                row = working_rows_by_id[row_id]
                row["status"] = "paired"
                row["case_id"] = case_id
                row["relation_mode"] = relation.get("relation_mode")
                row[self._relation_field_name(str(row.get("type") or ""))] = self._active_relation_payload(relation)
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
            if case_id and external_etc_batch_id:
                summary_row = etc_summary_rows_by_external_batch_id.get(external_etc_batch_id)
                if summary_row:
                    row = deepcopy(summary_row)
                    row["case_id"] = case_id
                    row["status"] = "paired"
                    row["relation_mode"] = relation.get("relation_mode")
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

        self._apply_reconciliation_decisions_to_rows(
            working_rows_by_id,
            decisions or [],
            paired_row_ids,
        )
        WorkbenchObjectIdentityArbitrationService(identity_policy=OBJECT_IDENTITY_POLICY).arbitrate_rows(
            working_rows_by_id
        )

        grouped = WorkbenchCandidateGroupingService().group_payload(
            month,
            oa_rows=[
                deepcopy(row)
                for row in working_rows_by_id.values()
                if str(row.get("type") or "") == "oa"
            ],
            bank_rows=[
                deepcopy(row)
                for row in working_rows_by_id.values()
                if str(row.get("type") or "") == "bank"
            ],
            invoice_rows=[
                deepcopy(row)
                for row in working_rows_by_id.values()
                if str(row.get("type") or "") == "invoice"
            ],
        )
        grouped["oa_status"] = {"code": "ready", "message": "OA projection ready"}
        grouped["workbench_read_model_schema_version"] = WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION
        grouped["oa_attachment_invoice_parser_version"] = MongoOAAdapter._attachment_invoice_cache_parser_version()
        grouped["oa_projection_sync_version"] = OA_PROJECTION_SYNC_VERSION
        return grouped

    def _apply_reconciliation_decisions_to_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        decisions: list[dict[str, Any]],
        paired_row_ids: set[str],
    ) -> None:
        claimed_row_ids: set[str] = set()
        for decision in sorted(decisions, key=self._decision_display_sort_key):
            if not self._decision_is_projectable(decision):
                continue
            row_ids = [
                str(row_id).strip()
                for row_id in list(decision.get("row_ids") or [])
                if str(row_id).strip()
            ]
            if not row_ids or any(row_id in paired_row_ids for row_id in row_ids):
                continue
            if any(row_id in claimed_row_ids for row_id in row_ids):
                continue
            applicable_rows = [rows_by_id.get(row_id) for row_id in row_ids]
            if any(not isinstance(row, dict) for row in applicable_rows):
                continue
            if any(self._row_is_held_for_matching(row) for row in applicable_rows if isinstance(row, dict)):
                continue
            decision_key = str(decision.get("decision_key") or decision.get("decision_id") or "").strip()
            if not decision_key:
                continue
            display_state = str(decision.get("display_state") or "").strip()
            metadata = self._decision_metadata(decision)
            for row_id in row_ids:
                row = rows_by_id[row_id]
                row["workbench_reconciliation_decision"] = deepcopy(metadata)
                if metadata.get("warnings"):
                    row["workbench_reconciliation_warnings"] = deepcopy(metadata["warnings"])
                if display_state != DISPLAY_STATE_PAIRED:
                    continue
                row["status"] = "paired"
                row["case_id"] = decision_key
                row["relation_mode"] = "automatic_decision"
                row[self._relation_field_name(str(row.get("type") or ""))] = self._decision_relation_payload(decision)
                if str(decision.get("rule_code") or "") == OA_INVOICE_OFFSET_AUTO_MATCH:
                    tags = [
                        str(tag).strip()
                        for tag in list(row.get("tags") or [])
                        if str(tag).strip()
                    ]
                    if "冲" not in tags:
                        tags.append("冲")
                    row["tags"] = tags
                    row["cost_excluded"] = True
            claimed_row_ids.update(row_ids)

    @staticmethod
    def _decision_is_projectable(decision: dict[str, Any]) -> bool:
        decision_status = str(decision.get("decision_status") or "").strip()
        display_state = str(decision.get("display_state") or "").strip()
        return (
            (decision_status == DECISION_STATUS_PAIRED and display_state == DISPLAY_STATE_PAIRED)
            or (decision_status == DECISION_STATUS_OPEN and display_state == DISPLAY_STATE_OPEN)
        )

    @staticmethod
    def _decision_display_sort_key(decision: dict[str, Any]) -> tuple[int, int, str, str]:
        state_priority = {
            DISPLAY_STATE_PAIRED: 0,
            DISPLAY_STATE_OPEN: 1,
        }
        row_count = len({str(row_id).strip() for row_id in list(decision.get("row_ids") or []) if str(row_id).strip()})
        return (
            state_priority.get(str(decision.get("display_state") or ""), 9),
            -row_count,
            str(decision.get("rule_code") or ""),
            str(decision.get("decision_key") or decision.get("decision_id") or ""),
        )

    @staticmethod
    def _decision_metadata(decision: dict[str, Any]) -> dict[str, Any]:
        keys = (
            "decision_id",
            "decision_key",
            "display_state",
            "decision_status",
            "match_domain",
            "match_shape",
            "rule_code",
            "rule_version",
            "row_ids",
            "oa_row_ids",
            "bank_row_ids",
            "invoice_row_ids",
            "amount",
            "direction",
            "payment_amount_closed",
            "invoice_amount_closed",
            "warnings",
            "evidence",
            "blockers",
            "explanation",
            "source_versions",
        )
        return {key: deepcopy(decision.get(key)) for key in keys if key in decision}

    @staticmethod
    def _decision_relation_payload(decision: dict[str, Any]) -> dict[str, str]:
        rule_code = str(decision.get("rule_code") or "").strip()
        warnings = list(decision.get("warnings") or [])
        if rule_code == OA_INVOICE_OFFSET_AUTO_MATCH:
            return {"code": rule_code, "label": "冲", "tone": "warn" if warnings else "success"}
        return {"code": "automatic_match", "label": "自动匹配", "tone": "warn" if warnings else "success"}

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

    def _apply_workbench_overrides_and_exceptions(self, rows_by_id: dict[str, dict[str, Any]]) -> None:
        if not rows_by_id:
            return
        override_service = WorkbenchOverrideService.from_snapshot(
            {"row_overrides": self._row_overrides_for_rows(set(rows_by_id))}
        )
        for row_id, row in list(rows_by_id.items()):
            rows_by_id[row_id] = override_service.apply_to_row(row)
        for case_payload in self._active_exception_cases_for_rows(set(rows_by_id)):
            case_row_ids = [
                str(row_id).strip()
                for row_id in list(case_payload.get("row_ids") or [])
                if str(row_id).strip() in rows_by_id
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
    def _active_relation_payload(relation: dict[str, Any]) -> dict[str, str]:
        relation_mode = str(relation.get("relation_mode") or "").strip()
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            return {"code": NO_OA_BANK_BATCH_RELATION_MODE, "label": "免OA批量处理", "tone": "success"}
        if relation_mode and relation_mode != "manual_confirmed":
            return {"code": relation_mode, "label": "已关联", "tone": "success"}
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

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

    def _open_etc_invoice_summary_rows(self, month: str) -> list[dict[str, Any]]:
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

        for row in rows:
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
            select distinct amount_check->>'external_etc_batch_id' as external_etc_batch_id
            from app.workbench_pair_relations
            where status = 'active'
              and amount_check ? 'external_etc_batch_id'
              and nullif(amount_check->>'external_etc_batch_id', '') is not null
            """,
            (),
        )
        return {
            str(row.get("external_etc_batch_id") or "").strip()
            for row in rows
            if str(row.get("external_etc_batch_id") or "").strip()
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
        total_amount = (
            _decimal_or_none(batch_payload.get("oa_total_amount"))
            or _decimal_or_none(batch_payload.get("total_amount"))
            or _decimal_or_none(batch_payload.get("etc_invoice_amount"))
            or invoice_total_amount
        )
        issue_dates = [_date_text(row.get("invoice_date")) for row in invoices if _date_text(row.get("invoice_date"))]
        seller_names = [
            str(row.get("seller_name") or row.get("counterparty_name") or "").strip()
            for row in invoices
            if str(row.get("seller_name") or row.get("counterparty_name") or "").strip()
        ]
        first_seller_name = seller_names[0] if seller_names else "ETC发票"
        count = _int_or_none(batch_payload.get("etc_invoice_count")) or len(invoices)
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
        amount_check = relation.get("amount_check")
        if not isinstance(amount_check, dict):
            return ""
        return str(amount_check.get("external_etc_batch_id") or amount_check.get("etc_batch_id") or "").strip()

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
    def _row_is_held_for_matching(row: dict[str, Any]) -> bool:
        if bool(row.get("ignored")) or bool(row.get("handled_exception")):
            return True
        case_id = str(row.get("case_id") or "").strip()
        if case_id and not case_id.startswith("candidate:"):
            return True
        exception_case_id = str(row.get("exception_case_id") or "").strip()
        if exception_case_id:
            return True
        return False

    @staticmethod
    def _relation_field_name(row_type: str) -> str:
        if row_type == "oa":
            return "oa_bank_relation"
        if row_type == "bank":
            return "invoice_relation"
        return "invoice_bank_relation"

    @staticmethod
    def _attachment_row_ids_for_relation(
        relation: dict[str, Any],
        rows_by_id: dict[str, dict[str, Any]],
    ) -> list[str]:
        row_ids = [str(row_id).strip() for row_id in list(relation.get("row_ids") or []) if str(row_id).strip()]
        row_types = [str(row_type).strip() for row_type in list(relation.get("row_types") or [])]
        oa_row_ids = {
            row_id
            for index, row_id in enumerate(row_ids)
            if (row_types[index] if index < len(row_types) else "") == "oa" or row_id.startswith("oa-")
        }
        if not oa_row_ids:
            return []
        return [
            row_id
            for row_id, row in rows_by_id.items()
            if str(row.get("source_kind") or "").strip() == OA_ATTACHMENT_INVOICE_SOURCE_KIND
            and str(row.get("derived_from_oa_id") or "").strip() in oa_row_ids
        ]

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


def _is_formal_attachment_invoice_evidence(evidence: dict[str, Any]) -> bool:
    source_kind = str(evidence.get("source_kind") or "").strip()
    if source_kind:
        return source_kind == OA_ATTACHMENT_INVOICE_SOURCE_KIND
    return OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence)


def _looks_like_invoice_artifact(evidence: dict[str, Any]) -> bool:
    evidence_type = str(evidence.get("evidence_type") or "").strip()
    if OBJECT_IDENTITY_POLICY.is_oa_attachment_invoice_evidence(evidence):
        return True
    document_kind = str(evidence.get("document_kind") or "").strip()
    if "发票" in document_kind:
        return True
    file_name = str(
        evidence.get("source_attachment_name")
        or evidence.get("attachment_name")
        or evidence.get("fileName")
        or evidence.get("filename")
        or ""
    )
    suffix = str(evidence.get("suffix") or "").strip().lower()
    return "发票" in file_name


def _fallback_attachment_source_key(
    payload: dict[str, Any],
    *,
    source_expense_item_id: Any,
    fallback_index: int,
    attachment: dict[str, Any],
) -> str:
    oa_row_id = str(payload.get("id") or payload.get("row_id") or "").strip()
    source_item = str(source_expense_item_id or "root").strip() or "root"
    name = str(
        attachment.get("source_attachment_name")
        or attachment.get("attachment_name")
        or attachment.get("fileName")
        or attachment.get("filename")
        or attachment.get("filePath")
        or "unnamed"
    ).strip() or "unnamed"
    return f"{oa_row_id}:attachment:{source_item}:{fallback_index}:{name}"
