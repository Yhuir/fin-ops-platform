from __future__ import annotations

from datetime import date
import json
import re
from typing import Any

from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository


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
        self._read_model_repository.save_search_index_rows(scope_key=normalized_scope, rows=rows)
        return {"scope_key": normalized_scope, "row_count": len(rows)}

    def rebuild_pending_invoice_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_direction, normalized_filter, month = _parse_pending_invoice_scope_key(scope_key)
        if normalized_direction not in {"expense", "income"}:
            raise ValueError("pending invoice direction must be expense or income.")
        if normalized_filter not in PENDING_INVOICE_FILTERS:
            raise ValueError("pending invoice filter must be all or a supported filter group.")
        if month is None:
            raise ValueError("pending invoice SQL projection scope_key must include a month shard YYYY-MM.")
        rows = self._pending_invoice_rows(direction=normalized_direction, filter_name=normalized_filter, month=month)
        self._read_model_repository.save_pending_invoice_rows(
            scope_key=f"{normalized_direction}:{normalized_filter}:{month}",
            rows=rows,
        )
        return {"scope_key": f"{normalized_direction}:{normalized_filter}:{month}", "row_count": len(rows)}

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
        tag_groups = self._pending_invoice_tag_groups()
        rows = self._connection.fetch_all(
            """
            select
                coalesce(t.legacy_mongo_id, t.id::text) as transaction_id,
                t.counterparty_name_raw,
                t.trade_time,
                t.txn_date,
                t.amount,
                t.account_name,
                t.account_no,
                t.txn_direction,
                t.txn_month,
                c.raw_payload as category_payload,
                coalesce(inv.invoices, '[]'::jsonb) as invoices,
                coalesce(rel.oa_applicant, '') as oa_applicant,
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
                select
                    array_agg(distinct pr.case_id) as case_ids,
                    max(coalesce(
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'oa_applicant',
                        pr.raw_payload->'normalized_payload'->'special_metadata'->>'applicant',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'oa_applicant',
                        pr.raw_payload->'normalized_payload'->'evidence'->>'applicant'
                    )) as oa_applicant
                from app.workbench_pair_relations pr
                where pr.status = 'active'
                  and coalesce(t.legacy_mongo_id, t.id::text) = any(pr.row_ids)
            ) rel on true
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
            filter_group = _filter_group_for_category(category_code, tag_groups) or "all"
            if direction == "expense" and filter_name != "all" and filter_group != filter_name:
                continue
            invoices = row.get("invoices") if isinstance(row.get("invoices"), list) else []
            can_create_invoice = not invoices and not (direction == "expense" and filter_group == "no_invoice_required")
            transaction_id = str(row.get("transaction_id") or "").strip()
            bank_transaction = {
                "id": transaction_id,
                "counterparty_name": row.get("counterparty_name_raw"),
                "trade_time": _date_text(row.get("trade_time") or row.get("txn_date")),
                "amount": str(row.get("amount") or ""),
                "bank_name": row.get("account_name") or "",
                "account_last4": str(row.get("account_no") or "")[-4:],
                "effective_tag_code": category_code or None,
                "effective_tag_label": category.get("category_label"),
            }
            payload = {
                "id": transaction_id,
                "bank_transaction": bank_transaction,
                "invoices": invoices,
                "oa_applicant": str(row.get("oa_applicant") or "").strip() or "—",
                "can_create_invoice": can_create_invoice,
                "relation_case_ids": list(row.get("relation_case_ids") or []),
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

    def _pending_invoice_tag_groups(self) -> dict[str, set[str]]:
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s",
            ("app_settings",),
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else {}
        groups = (((payload or {}).get("pending_invoice_tag_groups") or {}).get("groups") or {}) if isinstance(payload, dict) else {}
        return {
            group_name: {
                str(code).strip()
                for code in list((groups.get(group_name) or {}).get("tag_codes") or [])
                if str(code).strip()
            }
            for group_name in ("requires_invoice", "bank_statement_as_invoice", "no_invoice_required")
        }


def _parse_pending_invoice_scope_key(scope_key: str) -> tuple[str, str, str | None]:
    parts = [part.strip() for part in str(scope_key or "").split(":")]
    direction = parts[0] if parts and parts[0] else "expense"
    filter_name = parts[1] if len(parts) > 1 and parts[1] else "all"
    month = parts[2] if len(parts) > 2 and parts[2] else ""
    normalized_month = month[:7] if MONTH_RE.match(month[:7]) else None
    return direction, filter_name, normalized_month


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


def _filter_group_for_category(category_code: str, tag_groups: dict[str, set[str]]) -> str | None:
    for group_name in ("requires_invoice", "bank_statement_as_invoice", "no_invoice_required"):
        if category_code in tag_groups.get(group_name, set()):
            return group_name
    return None


def _date_text(value: object) -> str:
    if isinstance(value, (date,)):
        return value.isoformat()
    return str(value or "")[:19]
