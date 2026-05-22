from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime
import re
from types import SimpleNamespace
from typing import Any

from fin_ops_platform.services.no_oa_bank_batch_service import NO_OA_BANK_BATCH_RELATION_MODE
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.oa_projection import (
    PostgresOAProjectionAdapter,
    PostgresOAProjectionRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_candidate_grouping import WorkbenchCandidateGroupingService
from fin_ops_platform.services.workbench_candidate_match_service import WorkbenchCandidateMatchService
from fin_ops_platform.services.workbench_exception_case_service import ACTIVE_CASE_STATUSES
from fin_ops_platform.services.workbench_matching_rules import (
    WORKBENCH_MATCHING_RULES_VERSION,
    WorkbenchMatchingRules,
)
from fin_ops_platform.services.workbench_override_service import WorkbenchOverrideService
from fin_ops_platform.services.workbench_query_service import WorkbenchQueryService
from fin_ops_platform.services.workbench_special_pair_rule_service import (
    OA_INVOICE_OFFSET_AUTO_MATCH,
    WORKBENCH_SPECIAL_RULES_VERSION,
)


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


class WorkbenchSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        oa_query_service: WorkbenchQueryService | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
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
            ) scopes
            where scope_key is not null
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_RE.match(str(row.get("scope_key") or ""))]

    def rebuild_workbench_read_model_scope(
        self,
        scope_key: str,
        *,
        source_version: int | str | None = None,
    ) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip()
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("workbench SQL projection scope_key must be a month shard YYYY-MM.")
        resolved_source_version = _int_value(source_version, self._current_dirty_scope_source_version(normalized_scope))
        rows_by_id = self._workbench_rows_for_month(normalized_scope)
        relations = self._active_pair_relations_for_month(normalized_scope, set(rows_by_id))
        self._supplement_missing_relation_rows(rows_by_id, relations)
        payload = self._group_payload(
            normalized_scope,
            rows_by_id,
            relations,
            source_version=resolved_source_version,
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
                        "builder": "workbench_sql_projection.v1",
                        "source_version": resolved_source_version,
                    },
                }
            }
        }
        self._read_model_repository.save_workbench_read_models(snapshot, changed_scope_keys={normalized_scope})
        row_count = sum(len(group.get(f"{kind}_rows") or []) for group in payload["paired"]["groups"] + payload["open"]["groups"] for kind in ("oa", "bank", "invoice"))
        return {
            "scope_key": normalized_scope,
            "base_scope_key": normalized_scope,
            "row_count": row_count,
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
            if row_type == "invoice" and not str(row.get("source_kind") or "").startswith("oa_attachment_"):
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
                select cache.invoices, cache.evidences, cache.artifacts
                from app.oa_attachment_invoice_cache_sources source
                join app.oa_attachment_invoice_cache cache
                  on cache.source_attachment_key = source.cache_source_attachment_key
                where source.source_attachment_key = attachment.source_attachment_key
                order by cache.parsed_at desc nulls last
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
            cache_artifacts = row.get("cache_artifacts") if isinstance(row.get("cache_artifacts"), list) else []
            for evidence in [
                *list(row.get("cache_invoices") or []),
                *list(row.get("cache_evidences") or []),
                *list(cache_artifacts),
            ]:
                if not isinstance(evidence, dict):
                    continue
                evidence_attachment_key = str(evidence.get("source_attachment_key") or "").strip()
                if source_attachment_key_text and evidence_attachment_key and evidence_attachment_key != source_attachment_key_text:
                    continue
                normalized = dict(evidence)
                normalized.setdefault("source_expense_item_id", source_expense_item_id)
                normalized.setdefault("source_expense_row_index", source_expense_row_index)
                normalized.setdefault("source_attachment_key", source_attachment_key)
                normalized.setdefault("source_attachment_name", source_attachment_name)
                evidence_by_oa_id.setdefault(oa_row_id, []).append(normalized)
        result: list[dict[str, Any]] = []
        seen: set[str] = set()
        for oa_row_id, attachment_evidences in evidence_by_oa_id.items():
            oa_row = oa_rows_by_id.get(oa_row_id)
            if not isinstance(oa_row, dict) or not attachment_evidences:
                continue
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

    @staticmethod
    def _attachment_evidences_from_expense_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
        evidences: list[dict[str, Any]] = []
        for item in list(payload.get("expense_items") or []):
            if not isinstance(item, dict):
                continue
            source_expense_item_id = item.get("expense_item_id")
            source_expense_row_index = item.get("row_index")
            for source_key in ("attachment_invoices", "attachment_evidences", "attachment_artifacts"):
                for evidence in list(item.get(source_key) or []):
                    if not isinstance(evidence, dict):
                        continue
                    normalized = dict(evidence)
                    normalized.setdefault("source_expense_item_id", source_expense_item_id)
                    normalized.setdefault("source_expense_row_index", source_expense_row_index)
                    if source_key == "attachment_artifacts" and not _looks_like_invoice_artifact(normalized):
                        continue
                    evidences.append(normalized)
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
            "payment_account_label": account_name or account_no[-4:],
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
                "支付账户": account_name or account_no[-4:] or "—",
                "和发票关联情况": "待关联发票",
                "支付/收款时间": _date_text(row.get("pay_receive_time") or row.get("trade_time") or row.get("txn_date")),
                "备注": row.get("remark") or "—",
            },
            "detail_fields": detail_fields,
        }

    def _invoice_rows(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select coalesce(legacy_mongo_id, id::text) as row_id, invoice_type, invoice_no,
                   digital_invoice_no, invoice_date, counterparty_name, seller_name, buyer_name,
                   amount, total_with_tax, status, raw_payload
            from app.invoices
            where invoice_month = %s::date
              and status <> 'deleted'
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
                   buyer_name, buyer_tax_no, amount, tax_rate, tax_amount, total_with_tax, status, raw_payload
            from app.invoices
            where coalesce(legacy_mongo_id, id::text) = any(%s)
              and status <> 'deleted'
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
        return {
            "id": row_id,
            "type": "invoice",
            "source_kind": "invoice",
            "status": "open",
            "case_id": None,
            "invoice_type": row.get("invoice_type"),
            "invoice_no": row.get("invoice_no"),
            "invoice_code": row.get("invoice_code"),
            "digital_invoice_no": row.get("digital_invoice_no"),
            "issue_date": _date_text(row.get("invoice_date")),
            "counterparty_name": row.get("counterparty_name") or row.get("seller_name") or row.get("buyer_name"),
            "seller_name": row.get("seller_name"),
            "seller_tax_no": row.get("seller_tax_no"),
            "buyer_name": row.get("buyer_name"),
            "buyer_tax_no": row.get("buyer_tax_no"),
            "amount": str(row.get("amount") or ""),
            "tax_rate": row.get("tax_rate") or "—",
            "tax_amount": str(row.get("tax_amount") or "—"),
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
                "税率": row.get("tax_rate") or "—",
                "税额": str(row.get("tax_amount") or "—"),
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
        *,
        source_version: int | str | None = None,
    ) -> dict[str, Any]:
        working_rows_by_id = {row_id: dict(row) for row_id, row in rows_by_id.items()}
        self._apply_workbench_overrides_and_exceptions(working_rows_by_id)
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
            for row_id in relation_row_ids:
                paired_row_ids.add(row_id)
                row = working_rows_by_id[row_id]
                row["status"] = "paired"
                row["case_id"] = case_id
                row["relation_mode"] = relation.get("relation_mode")
                row[self._relation_field_name(str(row.get("type") or ""))] = self._active_relation_payload(relation)

        candidates = self._rebuild_candidate_matches(
            month,
            working_rows_by_id,
            paired_row_ids,
            source_version=source_version,
        )
        self._apply_candidate_matches_to_rows(working_rows_by_id, candidates, paired_row_ids)

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
        grouped["workbench_read_model_schema_version"] = "workbench_sql_projection.v2"
        return grouped

    def _rebuild_candidate_matches(
        self,
        month: str,
        rows_by_id: dict[str, dict[str, Any]],
        paired_row_ids: set[str],
        *,
        source_version: int | str | None = None,
    ) -> list[dict[str, Any]]:
        source_versions = self._matching_source_versions(source_version=source_version)
        settings = self._matching_settings()
        candidate_service = WorkbenchCandidateMatchService()
        candidate_service.delete_month(month)
        rules = WorkbenchMatchingRules(include_special_rules=True)
        candidates = rules.generate_candidates(
            month,
            [
                deepcopy(row)
                for row_id, row in rows_by_id.items()
                if row_id not in paired_row_ids
                and not self._row_is_held_for_matching(row)
                and str(row.get("type") or "") == "oa"
            ],
            [
                deepcopy(row)
                for row_id, row in rows_by_id.items()
                if row_id not in paired_row_ids
                and not self._row_is_held_for_matching(row)
                and str(row.get("type") or "") == "bank"
            ],
            [
                deepcopy(row)
                for row_id, row in rows_by_id.items()
                if row_id not in paired_row_ids
                and not self._row_is_held_for_matching(row)
                and str(row.get("type") or "") == "invoice"
            ],
            settings=settings,
            source_versions=source_versions,
        )
        upserted = [candidate_service.upsert_candidate(candidate) for candidate in candidates]
        candidate_service.mark_scope_processed(
            month,
            source_versions=source_versions,
            candidate_count=len(upserted),
            request_id=f"workbench-sql-projection:{month}",
            reason="workbench_sql_projection",
        )
        self._read_model_repository.save_workbench_candidate_matches(
            candidate_service.snapshot(),
            changed_scope_months={month},
        )
        return upserted

    def _apply_candidate_matches_to_rows(
        self,
        rows_by_id: dict[str, dict[str, Any]],
        candidates: list[dict[str, Any]],
        paired_row_ids: set[str],
    ) -> None:
        claimed_row_ids: set[str] = set()
        for candidate in sorted(candidates, key=self._candidate_display_sort_key):
            row_ids = [
                str(row_id).strip()
                for row_id in list(candidate.get("row_ids") or [])
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
            if not self._candidate_can_apply_to_rows(candidate, row_ids):
                continue
            case_id = str(candidate.get("candidate_key") or candidate.get("candidate_id") or "").strip()
            if not case_id:
                continue
            relation = self._candidate_relation_payload(candidate)
            for row_id in row_ids:
                row = rows_by_id[row_id]
                row["case_id"] = case_id
                row[self._relation_field_name(str(row.get("type") or ""))] = deepcopy(relation)
                if str(candidate.get("rule_code") or "") == OA_INVOICE_OFFSET_AUTO_MATCH:
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

    def _matching_source_versions(self, *, source_version: int | str | None = None) -> dict[str, Any]:
        versions: dict[str, Any] = {
            "builder": "workbench_sql_projection.v2",
            "matching_rules": WORKBENCH_MATCHING_RULES_VERSION,
            "special_rules": WORKBENCH_SPECIAL_RULES_VERSION,
        }
        if source_version is not None:
            versions["source_version"] = _int_value(source_version, 0)
        return versions

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

    def _matching_settings(self) -> dict[str, Any]:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = 'app_settings'"
        )
        payload = row_payload(row, "settings_payload")
        settings = payload if isinstance(payload, dict) else {}
        offset = settings.get("oa_invoice_offset") if isinstance(settings.get("oa_invoice_offset"), dict) else {}
        return {
            "offset_applicant_names": [
                str(name).strip()
                for name in list(offset.get("applicant_names") or [])
                if str(name).strip()
            ],
        }

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
    def _candidate_can_apply_to_rows(candidate: dict[str, Any], row_ids: list[str]) -> bool:
        unique_row_ids = {str(row_id).strip() for row_id in row_ids if str(row_id).strip()}
        if len(unique_row_ids) <= 1:
            return True
        return str(candidate.get("status") or "").strip() in {"auto_closed", "incomplete"}

    @staticmethod
    def _candidate_display_sort_key(candidate: dict[str, Any]) -> tuple[int, int, str, str]:
        status_priority = {
            "auto_closed": 0,
            "conflict": 1,
            "incomplete": 2,
            "needs_review": 3,
        }
        row_count = len({str(row_id).strip() for row_id in list(candidate.get("row_ids") or []) if str(row_id).strip()})
        return (
            status_priority.get(str(candidate.get("status") or ""), 9),
            -row_count,
            str(candidate.get("rule_code") or ""),
            str(candidate.get("candidate_key") or candidate.get("candidate_id") or ""),
        )

    @staticmethod
    def _candidate_relation_payload(candidate: dict[str, Any]) -> dict[str, str]:
        status = str(candidate.get("status") or "").strip()
        rule_code = str(candidate.get("rule_code") or "").strip()
        if status == "auto_closed":
            if rule_code == OA_INVOICE_OFFSET_AUTO_MATCH:
                return {"code": rule_code, "label": "冲", "tone": "success"}
            return {"code": "automatic_match", "label": "自动匹配", "tone": "success"}
        if status == "conflict":
            return {"code": "candidate_conflict", "label": "候选冲突", "tone": "danger"}
        if status == "incomplete":
            return {"code": "candidate_incomplete", "label": "候选未闭环", "tone": "warn"}
        return {"code": "suggested_match", "label": "待人工确认", "tone": "warn"}

    @staticmethod
    def _active_relation_payload(relation: dict[str, Any]) -> dict[str, str]:
        relation_mode = str(relation.get("relation_mode") or "").strip()
        if relation_mode == NO_OA_BANK_BATCH_RELATION_MODE:
            return {"code": NO_OA_BANK_BATCH_RELATION_MODE, "label": "免OA批量处理", "tone": "success"}
        if relation_mode and relation_mode != "manual_confirmed":
            return {"code": relation_mode, "label": "已关联", "tone": "success"}
        return {"code": "fully_linked", "label": "完全关联", "tone": "success"}

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
            if str(row.get("source_kind") or "").startswith("oa_attachment_")
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


def _looks_like_invoice_artifact(evidence: dict[str, Any]) -> bool:
    evidence_type = str(evidence.get("evidence_type") or "").strip()
    if evidence_type in {"tax_invoice", "machine_invoice", "non_tax_receipt"}:
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
    return "发票" in file_name or suffix == "pdf"
