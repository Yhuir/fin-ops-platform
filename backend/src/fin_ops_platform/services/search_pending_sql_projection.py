from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import json
import re
from typing import Any

from fin_ops_platform.services.mongo_oa_adapter import MongoOAAdapter
from fin_ops_platform.services.pending_invoice_rules import (
    pending_invoice_group_for_category,
    pending_invoice_tag_group_sets,
)
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.workbench_sql_projection import WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PENDING_INVOICE_FILTERS = {"all", "requires_invoice", "bank_statement_as_invoice", "no_invoice_required"}


class SearchPendingSqlProjectionBuilder:
    def __init__(self, *, connection: Any, read_model_repository: PostgresReadModelRepository | None = None) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)

    def list_search_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope = str(scope_key or "").strip()
        if normalized_scope != "all":
            return [normalized_scope] if MONTH_RE.match(normalized_scope) else []
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from read_model.workbench_rows
            where scope_month is not null
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_RE.match(str(row.get("scope_key") or ""))]

    def rebuild_search_index_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope = str(scope_key or "").strip()
        if not MONTH_RE.match(normalized_scope):
            raise ValueError("search SQL projection scope_key must be a month shard YYYY-MM.")
        rows = self._search_rows_for_month(normalized_scope)
        source_versions = self._search_source_versions()
        self._read_model_repository.save_search_index_rows(
            scope_key=normalized_scope,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_direction, normalized_filter, month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice direction must be expense or income.")
        if normalized_filter not in PENDING_INVOICE_FILTERS:
            raise ValueError("pending invoice filter must be all or a supported filter group.")
        if month is None:
            raise ValueError("pending invoice SQL projection scope_key must include a month shard YYYY-MM.")
        rows = self._pending_invoice_rows(direction=normalized_direction, filter_name=normalized_filter, month=month)
        source_versions = self._pending_invoice_source_versions()
        self._read_model_repository.save_pending_invoice_rows(
            scope_key=f"{normalized_direction}:{normalized_filter}:{month}",
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": f"{normalized_direction}:{normalized_filter}:{month}", "row_count": len(rows), "source_versions": source_versions}

    def mark_pending_invoice_scope_empty(self, scope_key: str) -> dict[str, object]:
        normalized_direction, normalized_filter, _month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice direction must be expense or income.")
        if normalized_filter not in PENDING_INVOICE_FILTERS:
            raise ValueError("pending invoice filter must be all or a supported filter group.")
        mark_scope = getattr(self._read_model_repository, "mark_pending_invoice_scope", None)
        if not callable(mark_scope):
            return {"scope_key": f"{normalized_direction}:{normalized_filter}", "row_count": 0}
        normalized_scope_key = str(scope_key or "").strip() or f"{normalized_direction}:{normalized_filter}"
        mark_scope(
            scope_key=normalized_scope_key,
            row_count=0,
            source_versions=self._pending_invoice_source_versions(),
        )
        return {"scope_key": normalized_scope_key, "row_count": 0}

    def list_pending_invoice_scope_shards(self, scope_key: str) -> list[str]:
        normalized_direction, normalized_filter, month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            return []
        if normalized_filter not in PENDING_INVOICE_FILTERS:
            return []
        if month is not None:
            return [f"{normalized_direction}:{normalized_filter}:{month}"]
        txn_direction = "outflow" if normalized_direction == "expense" else "inflow"
        rows = self._connection.fetch_all(
            """
            select distinct to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where txn_month is not null
              and txn_direction = %s
              and status <> 'deleted'
            order by scope_key desc
            """,
            (txn_direction,),
        )
        return [
            f"{normalized_direction}:{normalized_filter}:{row['scope_key']}"
            for row in rows
            if MONTH_RE.match(str(row.get("scope_key") or ""))
        ]

    def _search_rows_for_month(self, month: str) -> list[dict[str, object]]:
        rows = self._connection.fetch_all(
            """
            select row_id, source_kind, status, scope_month, project_name, counterparty_name,
                   amount, generated_at, payload, raw_payload
            from read_model.workbench_rows
            where scope_month = %s::date
              and (scope_key = %s or scope_key is null)
            order by source_kind, row_id
            """,
            (month_start(month), month),
        )
        result: list[dict[str, object]] = []
        for row in rows:
            payload = _payload_from_row(row)
            row_id = str(row.get("row_id") or payload.get("id") or payload.get("row_id") or "").strip()
            source_kind = str(row.get("source_kind") or payload.get("type") or payload.get("record_type") or "").strip()
            if not row_id or source_kind not in {"oa", "bank", "invoice"}:
                continue
            zone_hint = str(row.get("status") or payload.get("zone_hint") or "open").strip() or "open"
            title = _search_title(source_kind, payload, row)
            primary_meta = _primary_meta(payload, row)
            secondary_meta = _secondary_meta(payload, row)
            searchable_text = _join_text(
                row_id,
                title,
                primary_meta,
                secondary_meta,
                row.get("project_name"),
                row.get("counterparty_name"),
                payload.get("invoice_no"),
                payload.get("digital_invoice_no"),
                payload.get("applicant"),
                payload.get("reason"),
                payload.get("remark"),
                payload.get("summary"),
            )
            result_payload = {
                "row_id": row_id,
                "record_type": source_kind,
                "month": month,
                "zone_hint": zone_hint,
                "matched_field": "全文",
                "title": title,
                "primary_meta": primary_meta,
                "secondary_meta": secondary_meta,
                "status_label": _status_label(zone_hint),
                "jump_target": {"month": month, "row_id": row_id, "record_type": source_kind, "zone_hint": zone_hint},
            }
            result.append(
                {
                    "row_id": row_id,
                    "source_kind": source_kind,
                    "status": zone_hint,
                    "title": title,
                    "subtitle": secondary_meta,
                    "searchable_text": searchable_text,
                    "project_name": row.get("project_name") or payload.get("project_name"),
                    "counterparty_name": row.get("counterparty_name") or payload.get("counterparty_name"),
                    "amount": row.get("amount") or payload.get("amount"),
                    "generated_at": row.get("generated_at"),
                    "payload": result_payload,
                }
            )
        return result

    def _pending_invoice_rows(self, *, direction: str, filter_name: str, month: str) -> list[dict[str, object]]:
        txn_direction = "outflow" if direction == "expense" else "inflow"
        target_invoice_type = "input" if direction == "expense" else "output"
        tag_groups = self._pending_invoice_tag_groups(direction=direction)
        rows = self._connection.fetch_all(
            """
            select
                coalesce(t.legacy_mongo_id, t.id::text) as transaction_id,
                t.counterparty_name_raw,
                t.trade_time,
                t.txn_date,
                t.amount,
                t.balance,
                t.currency,
                t.summary,
                t.remark,
                t.bank_serial_no,
                t.account_name,
                t.account_no,
                t.txn_direction,
                t.txn_month,
                c.raw_payload as category_payload,
                coalesce(inv.invoices, '[]'::jsonb) as invoices,
                coalesce(pay.paid_total, 0)::text as paid_total,
                coalesce(rel.oa_applicant, '') as oa_applicant,
                coalesce(rel.oa_project_name, '') as oa_project_name,
                iso.income_status_override,
                coalesce(rel.case_ids, array[]::text[]) as relation_case_ids
            from app.bank_transactions t
            left join lateral (
                select raw_payload
                from app.bank_transaction_categories c
                where c.status = 'active'
                  and (c.legacy_transaction_id = coalesce(t.legacy_mongo_id, t.id::text) or c.bank_transaction_id = t.id)
                order by c.updated_at desc
                limit 1
            ) c on true
            left join lateral (
                select
                    jsonb_agg(
                        jsonb_build_object(
                            'id', coalesce(i.legacy_mongo_id, i.id::text),
                            'invoice_no', i.invoice_no,
                            'digital_invoice_no', i.digital_invoice_no,
                            'issue_date', i.invoice_date,
                            'total_with_tax', coalesce(i.total_with_tax, i.amount)::text,
                            'seller_name', i.seller_name,
                            'buyer_name', i.buyer_name,
                            'invoice_type', i.invoice_type,
                            'counterparty_display_name', case when %s = 'expense' then i.seller_name else i.buyer_name end
                        )
                        order by i.invoice_date nulls last, i.invoice_no
                    ) as invoices
                from app.workbench_pair_relations pr
                join app.invoices i
                  on coalesce(i.legacy_mongo_id, i.id::text) = any(pr.row_ids)
                 and i.invoice_type = %s
                where pr.status = 'active'
                  and coalesce(t.legacy_mongo_id, t.id::text) = any(pr.row_ids)
            ) inv on true
            left join lateral (
                select coalesce(sum(paid.amount), 0) as paid_total
                from (
                    select distinct coalesce(tb.legacy_mongo_id, tb.id::text) as bank_row_id, tb.amount
                    from app.workbench_pair_relations pr
                    join app.bank_transactions tb
                      on coalesce(tb.legacy_mongo_id, tb.id::text) = any(pr.row_ids)
                    where pr.status = 'active'
                      and exists (
                          select 1
                          from jsonb_array_elements(coalesce(inv.invoices, '[]'::jsonb)) invoice_item
                          where invoice_item->>'id' = any(pr.row_ids)
                      )
                ) paid
            ) pay on true
            left join lateral (
                select
                    array_agg(distinct pr.case_id) as case_ids,
                    max(coalesce(
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'oa_applicant',
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'applicant',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'oa_applicant',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'applicant'
                    )) as oa_applicant,
                    max(coalesce(
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'oa_project_name',
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'project_name',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'oa_project_name',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'project_name'
                    )) as oa_project_name
                from app.workbench_pair_relations pr
                where pr.status = 'active'
                  and coalesce(t.legacy_mongo_id, t.id::text) = any(pr.row_ids)
            ) rel on true
            left join lateral (
                select command_payload->'income_status_override' as income_status_override
                from app.pending_invoice_manual_invoice_commands command
                where command.status = 'completed'
                  and command.command_payload->>'operation' = 'income_status_override'
                  and command.command_payload->'income_status_override'->>'transaction_id' = coalesce(t.legacy_mongo_id, t.id::text)
                order by command.updated_at desc
                limit 1
            ) iso on true
            where t.txn_direction = %s
              and t.status <> 'deleted'
              and t.txn_month = %s::date
            order by coalesce(t.trade_time, t.txn_date::timestamptz) desc, transaction_id
            """,
            (direction, target_invoice_type, txn_direction, month_start(month)),
        )
        result: list[dict[str, object]] = []
        for row in rows:
            category = row_payload(row, "category_payload")
            category = category if isinstance(category, dict) else {}
            category_code = str(category.get("category_code") or category.get("category") or "").strip()
            filter_group = _filter_group_for_category(category_code, tag_groups, direction=direction) or "all"
            if direction == "expense" and filter_name != "all" and filter_group != filter_name:
                continue
            invoices = row.get("invoices") if isinstance(row.get("invoices"), list) else []
            payment_summary = _payment_summary_from_invoices(invoices, paid_total=row.get("paid_total"))
            can_create_invoice = direction == "expense" and not invoices and filter_group != "no_invoice_required"
            transaction_id = str(row.get("transaction_id") or "").strip()
            relation_case_ids = list(row.get("relation_case_ids") or [])
            oa_applicant = str(row.get("oa_applicant") or "").strip()
            oa_project_name = str(row.get("oa_project_name") or "").strip()
            oa_summaries = [
                {
                    "id": relation_case_ids[0] if relation_case_ids else transaction_id,
                    "applicant": oa_applicant,
                    "project_name": oa_project_name,
                }
            ] if oa_applicant or oa_project_name or relation_case_ids else []
            status_payload = _pending_invoice_status_payload(
                direction=direction,
                group=filter_group if filter_group != "all" else None,
                has_invoices=bool(invoices),
                payment_summary=payment_summary,
                matched_rule=_matched_rule_payload(
                    group=filter_group if filter_group != "all" else None,
                    category_code=category_code,
                    category_label=category.get("category_label"),
                    category=category,
                ),
                status_override=row.get("income_status_override") if isinstance(row.get("income_status_override"), dict) else None,
            )
            bank_transaction = {
                "id": transaction_id,
                "counterparty_name": row.get("counterparty_name_raw"),
                "counterparty_account_no": "",
                "counterparty_bank_name": "",
                "trade_time": _date_text(row.get("trade_time") or row.get("txn_date")),
                "booked_date": _date_text(row.get("txn_date")),
                "trade_date": _date_text(row.get("txn_date") or row.get("trade_time"))[:10],
                "amount": str(row.get("amount") or ""),
                "debit_amount": str(row.get("amount") or "") if direction == "expense" else "0.00",
                "credit_amount": str(row.get("amount") or "") if direction == "income" else "0.00",
                "balance": str(row.get("balance") or ""),
                "currency": row.get("currency") or "CNY",
                "bank_name": row.get("account_name") or "",
                "account_name": row.get("account_name") or "",
                "account_last4": str(row.get("account_no") or "")[-4:],
                "summary": row.get("summary") or "",
                "remark": row.get("remark") or "",
                "statement_serial_no": row.get("bank_serial_no") or "",
                "enterprise_serial_no": "",
                "voucher_type": "",
                "voucher_no": "",
                "effective_tag_code": category_code or None,
                "effective_tag_label": category.get("category_label"),
                "effective_tag_primary_label": category.get("category_primary_label"),
                "effective_tag_sub_label": category.get("category_sub_label"),
                "effective_tag_label_path": list(category.get("category_label_path") or []),
            }
            input_invoices = {
                "primary": invoices[0] if invoices else None,
                "relation_count": len(invoices),
                "has_multiple": len(invoices) > 1,
                "summaries": invoices,
                "payment_summary": payment_summary,
            }
            oa_payload = {
                "primary": oa_summaries[0] if oa_summaries else None,
                "relation_count": len(oa_summaries),
                "has_multiple": len(oa_summaries) > 1,
                "summaries": oa_summaries,
            }
            payload = {
                "id": transaction_id,
                "bank_transaction": bank_transaction,
                "invoice_acquisition_status": status_payload,
                "input_invoices": input_invoices,
                "oa": oa_payload,
                "invoices": invoices,
                "oa_applicant": oa_applicant or "—",
                "can_create_invoice": can_create_invoice,
                "relation_case_ids": relation_case_ids,
                "filter_group": filter_group,
            }
            searchable_text = _join_text(
                transaction_id,
                bank_transaction.get("counterparty_name"),
                bank_transaction.get("trade_time"),
                bank_transaction.get("amount"),
                bank_transaction.get("effective_tag_label"),
                payload.get("oa_applicant"),
            )
            result.append({"filter_group": filter_group, "searchable_text": searchable_text, "payload": payload})
        return result

    def _pending_invoice_tag_groups(self, *, direction: str) -> dict[str, set[str]]:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            ("app_settings",),
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else {}
        return pending_invoice_tag_group_sets(payload if isinstance(payload, dict) else {}, direction=direction)

    def _search_source_versions(self) -> dict[str, object]:
        return {
            "search_index_schema_version": "2026-05-search-index-v1",
            "workbench_read_model_schema_version": WORKBENCH_SQL_PROJECTION_SCHEMA_VERSION,
            "bank_auto_tag_rules_version": _current_bank_auto_tag_rules_version(self._connection),
            "oa_attachment_invoice_parser_version": MongoOAAdapter._attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }

    def _pending_invoice_source_versions(self) -> dict[str, object]:
        settings = _settings_payload(self._connection)
        pending_groups = settings.get("pending_invoice_tag_groups")
        pending_output_groups = settings.get("pending_output_invoice_tag_groups")
        bank_tags = settings.get("bank_transaction_tags")
        return {
            "pending_invoice_read_model_schema_version": "2026-05-pending-invoice-v1",
            "pending_invoice_tag_groups_version": pending_groups.get("version") if isinstance(pending_groups, dict) else 1,
            "pending_output_invoice_tag_groups_version": pending_output_groups.get("version") if isinstance(pending_output_groups, dict) else 1,
            "bank_auto_tag_rules_version": bank_tags.get("version") if isinstance(bank_tags, dict) else 1,
            "oa_attachment_invoice_parser_version": MongoOAAdapter._attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }


def _parse_pending_invoice_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = [part.strip() for part in str(scope_key or "").split(":")]
    direction = parts[0] if parts and parts[0] else "expense"
    filter_name = parts[1] if len(parts) > 1 and parts[1] else "all"
    month = parts[2] if len(parts) > 2 and parts[2] else ""
    normalized_month = month[:7] if MONTH_RE.match(month[:7]) else None
    return direction, filter_name, normalized_month


def _settings_payload(connection: Any) -> dict[str, Any]:
    row = connection.fetch_one(
        "select settings_payload from app.app_settings where settings_key = %s",
        ("app_settings",),
    )
    payload = row.get("settings_payload") if isinstance(row, dict) else {}
    return payload if isinstance(payload, dict) else {}


def _current_bank_auto_tag_rules_version(connection: Any) -> int:
    settings = _settings_payload(connection)
    rules_payload = settings.get("bank_transaction_tags")
    if not isinstance(rules_payload, dict):
        return 1
    try:
        return int(rules_payload.get("version") or 1)
    except (TypeError, ValueError):
        return 1


def _payload_from_row(row: dict[str, Any]) -> dict[str, Any]:
    payload = row_payload(row, "payload", "raw_payload")
    return payload if isinstance(payload, dict) else {}


def _search_title(source_kind: str, payload: dict[str, Any], row: dict[str, Any]) -> str:
    if source_kind == "oa":
        return str(payload.get("project_name") or payload.get("reason") or payload.get("applicant") or row.get("row_id") or "")
    if source_kind == "invoice":
        return str(payload.get("seller_name") or payload.get("buyer_name") or row.get("counterparty_name") or row.get("row_id") or "")
    return str(row.get("counterparty_name") or payload.get("counterparty_name") or row.get("row_id") or "")


def _primary_meta(payload: dict[str, Any], row: dict[str, Any]) -> str:
    return _join_text(
        payload.get("date"),
        payload.get("trade_time"),
        payload.get("invoice_date"),
        row.get("amount") or payload.get("amount"),
    )


def _secondary_meta(payload: dict[str, Any], row: dict[str, Any]) -> str:
    return _join_text(row.get("project_name") or payload.get("project_name"), row.get("counterparty_name") or payload.get("counterparty_name"))


def _join_text(*parts: object) -> str:
    return " ".join(str(part).strip() for part in parts if str(part or "").strip())


def _status_label(status: str) -> str:
    return {
        "paired": "已配对",
        "open": "未配对",
        "ignored": "已忽略",
        "processed_exception": "已处理异常",
    }.get(status, status)


def _filter_group_for_category(category_code: str, tag_groups: dict[str, set[str]], *, direction: str) -> str | None:
    return pending_invoice_group_for_category(category_code, tag_groups, direction=direction)


def _matched_rule_payload(
    *,
    group: str | None,
    category_code: str,
    category_label: object,
    category: dict[str, object] | None = None,
) -> dict[str, object] | None:
    if not group:
        return None
    category_payload = category if isinstance(category, dict) else {}
    return {
        "group": group,
        "tag_code": category_code or None,
        "tag_label": category_label,
        "tag_primary_label": category_payload.get("category_primary_label"),
        "tag_sub_label": category_payload.get("category_sub_label"),
        "tag_label_path": list(category_payload.get("category_label_path") or []),
    }


def _pending_invoice_status_payload(
    *,
    direction: str,
    group: str | None,
    has_invoices: bool,
    payment_summary: dict[str, object],
    matched_rule: dict[str, object] | None,
    status_override: dict[str, object] | None = None,
) -> dict[str, object]:
    if direction == "income":
        if has_invoices:
            return {
                "code": "income_invoiced",
                "label": "已开票",
                "reason": "收入流水已关联销项发票。",
                "severity": "success",
                "primary_action": "view_relation",
                "matched_rule": matched_rule,
            }
        if isinstance(status_override, dict):
            status_code = str(status_override.get("status_code") or "").strip()
            if status_code == "income_no_invoice_required":
                return {
                    "code": "income_no_invoice_required",
                    "label": "无需开票",
                    "reason": "收入流水已人工标记为无需开票。",
                    "severity": "default",
                    "primary_action": "none",
                    "matched_rule": matched_rule,
                }
            if status_code == "cash_income":
                return {
                    "code": "cash_income",
                    "label": "现金收入",
                    "reason": "收入流水已人工标记为现金收入。",
                    "severity": "info",
                    "primary_action": "none",
                    "matched_rule": matched_rule,
                }
        if group == "no_invoice_required":
            return {
                "code": "income_no_invoice_required",
                "label": "无需开票",
                "reason": "收入流水分类命中无需开票规则。",
                "severity": "default",
                "primary_action": "view_rules",
                "matched_rule": matched_rule,
            }
        if group == "cash_income":
            return {
                "code": "cash_income",
                "label": "现金收入",
                "reason": "收入流水分类命中现金收入规则。",
                "severity": "info",
                "primary_action": "view_rules",
                "matched_rule": matched_rule,
            }
        return {
            "code": "income_pending_invoice",
            "label": "未开票",
            "reason": "收入流水未关联销项发票，也未命中无需开票或现金收入规则。",
            "severity": "error",
            "primary_action": "mark_income_status",
            "matched_rule": matched_rule,
        }
    invoice_total = _decimal_from_text(payment_summary.get("invoice_total"))
    paid_total = _decimal_from_text(payment_summary.get("paid_total"))
    if has_invoices and invoice_total > paid_total:
        return {
            "code": "invoice_not_fully_paid",
            "label": "未支付完已开票",
            "reason": "已有关联进项发票，但关联支付流水合计小于发票价税合计。",
            "severity": "warning",
            "primary_action": "view_relation",
            "matched_rule": matched_rule,
        }
    if has_invoices:
        return {
            "code": "paid_invoiced",
            "label": "已支付已开票",
            "reason": "支出流水已关联进项发票。",
            "severity": "success",
            "primary_action": "view_relation",
            "matched_rule": matched_rule,
        }
    if group == "no_invoice_required":
        return {
            "code": "no_invoice_required",
            "label": "无需开票",
            "reason": "流水分类命中无需开票规则。",
            "severity": "default",
            "primary_action": "view_rules",
            "matched_rule": matched_rule,
        }
    if group == "bank_statement_as_invoice":
        return {
            "code": "bank_statement_as_invoice",
            "label": "流水代替发票",
            "reason": "流水分类命中流水代替发票规则。",
            "severity": "info",
            "primary_action": "view_rules",
            "matched_rule": matched_rule,
        }
    return {
        "code": "paid_pending_invoice",
        "label": "已支付待开票",
        "reason": "支出流水未关联进项发票，也未命中免票或流水替票规则。",
        "severity": "error",
        "primary_action": "attach_or_create_invoice",
        "matched_rule": matched_rule,
    }


def _payment_summary_from_invoices(invoices: list[object], *, paid_total: object) -> dict[str, object]:
    invoice_total = sum(
        (_invoice_total_from_payload(invoice) for invoice in invoices if isinstance(invoice, dict)),
        start=Decimal("0.00"),
    )
    normalized_paid_total = _decimal_from_text(paid_total)
    remaining = invoice_total - normalized_paid_total
    if remaining < Decimal("0.00"):
        remaining = Decimal("0.00")
    return {
        "invoice_total": _decimal_to_str(invoice_total),
        "paid_total": _decimal_to_str(normalized_paid_total),
        "remaining_amount": _decimal_to_str(remaining),
        "difference_amount": _decimal_to_str(invoice_total - normalized_paid_total),
        "payment_transaction_count": 0,
    }


def _invoice_total_from_payload(invoice: dict[str, object]) -> Decimal:
    return _decimal_from_text(invoice.get("total_with_tax") or invoice.get("amount"))


def _decimal_from_text(value: object) -> Decimal:
    try:
        return Decimal(str(value or "0").strip() or "0")
    except (InvalidOperation, ValueError):
        return Decimal("0.00")


def _decimal_to_str(value: Decimal) -> str:
    return str(value.quantize(Decimal("0.01")))


def _date_text(value: object) -> str:
    if isinstance(value, (date,)):
        return value.isoformat()
    return str(value or "")[:19]
