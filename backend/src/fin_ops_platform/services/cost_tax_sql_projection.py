from __future__ import annotations

from collections import defaultdict
from datetime import datetime
from decimal import Decimal, InvalidOperation
import re
from typing import Any

from fin_ops_platform.services.cost_statistics_read_model_service import CostStatisticsReadModelService
from fin_ops_platform.services.live_workbench_service import format_decimal
from fin_ops_platform.services.postgres_repositories.common import month_start, row_payload
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.tax_offset_read_model_service import TaxOffsetReadModelService
from fin_ops_platform.services.tax_offset_service import TaxOffsetService


MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
PROJECT_SCOPES = {"active", "all"}
ZERO = Decimal("0.00")


class CostStatisticsSqlProjectionBuilder:
    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        redis_helper: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._redis_helper = redis_helper

    def list_cost_statistics_scope_shards(self, scope_key: str) -> list[str]:
        project_scope, month = _parse_cost_scope_key(scope_key)
        if month != "all":
            return [f"{project_scope}:{month}"] if MONTH_RE.match(month) else []
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from read_model.workbench_snapshots
            where scope_month is not null
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
            raise ValueError("cost statistics all-scope must be expanded into month shards before rebuild.")
        payload = self._build_explorer_payload(month, project_scope=project_scope)
        service = CostStatisticsReadModelService()
        read_model = service.upsert_read_model(
            month,
            project_scope,
            payload,
            generated_at=datetime.now().isoformat(),
            source_scope_keys=[month],
            cache_status="ready",
        )
        warmed_scope_key = str(read_model["scope_key"])
        self._read_model_repository.save_cost_statistics_read_models(
            service.snapshot_scope_keys([warmed_scope_key]),
            changed_scope_keys={warmed_scope_key},
        )
        self._set_redis_json(
            f"cost_statistics:explorer:{warmed_scope_key}",
            {"payload": {**payload, "read_model_status": "fresh", "read_model_scope_key": warmed_scope_key}},
        )
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "project_scope": project_scope,
            "entry_count": len(payload.get("time_rows") or []),
        }

    def _build_explorer_payload(self, month: str, *, project_scope: str) -> dict[str, Any]:
        entries = self._cost_entries_from_workbench(month, project_scope=project_scope)
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
        payload = self._workbench_payload(month)
        groups = [
            *list(((payload.get("paired") or {}).get("groups") or [])),
            *list(((payload.get("open") or {}).get("groups") or [])),
        ]
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
                    }
                )
        return entries

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
        row = self._connection.fetch_one(
            "select settings_payload from app.app_settings where settings_key = %s limit 1",
            ("app_settings",),
        )
        payload = row.get("settings_payload") if isinstance(row, dict) else {}
        if not isinstance(payload, dict):
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
        redis_helper: Any | None = None,
    ) -> None:
        self._connection = connection
        self._read_model_repository = read_model_repository or PostgresReadModelRepository(connection)
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
        service = TaxOffsetReadModelService()
        read_model = service.upsert_read_model(
            month,
            payload,
            generated_at=datetime.now().isoformat(),
            source_scope_keys=[month],
            cache_status="ready",
        )
        warmed_scope_key = str(read_model["scope_key"])
        self._read_model_repository.save_tax_offset_read_models(
            service.snapshot_scope_keys([warmed_scope_key]),
            changed_scope_keys={warmed_scope_key},
        )
        self._set_redis_json(
            f"tax_offset:month:{warmed_scope_key}",
            {"payload": {**payload, "read_model_status": "fresh", "read_model_scope_key": warmed_scope_key}},
        )
        return {
            "scope_key": warmed_scope_key,
            "month": month,
            "entry_count": sum(len(payload.get(key) or []) for key in ("output_items", "input_plan_items", "certified_items")),
        }

    def _build_tax_payload(self, month: str) -> dict[str, Any]:
        month_data = {
            month: {
                "output_items": self._invoice_items(month, output=True),
                "input_plan_items": [*self._invoice_items(month, output=False), *self._oa_attachment_invoice_items(month)],
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

    def _oa_attachment_invoice_items(self, month: str) -> list[dict[str, Any]]:
        rows = self._connection.fetch_all(
            """
            select cache.source_attachment_key, cache.invoices, attachment.oa_source_id, attachment.form_id
            from app.oa_attachment_invoice_cache cache
            left join app.oa_attachments attachment on attachment.source_attachment_key = cache.source_attachment_key
            where cache.invoices is not null
            order by cache.source_attachment_key
            """
        )
        items: list[dict[str, Any]] = []
        for row in rows:
            invoices = row.get("invoices")
            if not isinstance(invoices, list):
                continue
            for index, invoice in enumerate(invoices):
                if not isinstance(invoice, dict):
                    continue
                issue_date = str(invoice.get("issue_date") or invoice.get("invoice_date") or invoice.get("开票日期") or "")
                if not issue_date.startswith(month):
                    continue
                invoice_type = str(invoice.get("invoice_type") or invoice.get("发票类型") or "进项发票")
                if "销" in invoice_type:
                    continue
                items.append(
                    {
                        "id": f"oa-attachment-invoice:{row.get('source_attachment_key')}:{index}",
                        "seller_name": str(invoice.get("seller_name") or invoice.get("销售方名称") or ""),
                        "seller_tax_no": invoice.get("seller_tax_no") or invoice.get("销售方识别号"),
                        "issue_date": issue_date,
                        "invoice_no": invoice.get("invoice_no") or invoice.get("发票号码"),
                        "invoice_code": invoice.get("invoice_code") or invoice.get("发票代码"),
                        "digital_invoice_no": invoice.get("digital_invoice_no") or invoice.get("数电发票号码"),
                        "tax_amount": _money(invoice.get("tax_amount") or invoice.get("税额")),
                        "total_with_tax": _money(invoice.get("total_with_tax") or invoice.get("价税合计") or invoice.get("amount")),
                        "risk_level": str(invoice.get("risk_level") or "待评估"),
                        "invoice_type": invoice_type,
                        "tax_rate": str(invoice.get("tax_rate") or "—"),
                        "source_kind": "oa_attachment_invoice",
                        "derived_from_oa_id": row.get("form_id") or row.get("oa_source_id"),
                    }
                )
        return items

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
