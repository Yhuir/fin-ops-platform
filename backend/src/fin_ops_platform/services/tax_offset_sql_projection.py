from __future__ import annotations

import re
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

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

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")
ZERO = Decimal("0.00")


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
                union
                select distinct scope_key
                from read_model.tax_offset_read_models
                where scope_key ~ '^[0-9]{4}-[0-9]{2}$'
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
            "tax_certified_import_source_version": self._table_source_version(
                "app.tax_certified_import_records",
                "status <> 'deleted'",
                timestamp_column="created_at",
            ),
            "oa_attachment_invoice_parser_version": attachment_invoice_cache_parser_version(),
            "oa_projection_sync_version": OA_PROJECTION_SYNC_VERSION,
        }

    def _table_source_version(self, table_name: str, where_sql: str, *, timestamp_column: str = "updated_at") -> str:
        try:
            row = self._connection.fetch_one(
                f"select count(*) as row_count, max({timestamp_column})::text as max_updated_at "
                f"from {table_name} where {where_sql}"
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
