from __future__ import annotations

import re
from datetime import datetime
from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import attachment_invoice_cache_parser_version
from fin_ops_platform.services.postgres_repositories.oa_projection import OA_PROJECTION_SYNC_VERSION
from fin_ops_platform.services.postgres_repositories.read_models import PostgresReadModelRepository
from fin_ops_platform.services.postgres_repositories.tax_offset import (
    load_tax_offset_month,
    tax_offset_scope_statistics,
)
from fin_ops_platform.services.tax_offset_read_model_repository import TaxOffsetReadModelRepositoryPort
from fin_ops_platform.services.tax_offset_read_model_service import (
    TAX_OFFSET_READ_MODEL_SCHEMA_VERSION,
    TaxOffsetReadModelService,
)

MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


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
        payload = load_tax_offset_month(self._connection, month)
        payload["statistics"] = tax_offset_scope_statistics(payload)
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
