from __future__ import annotations

from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.postgres_repositories import (
    PostgresCoreRepository,
    PostgresOAProjectionRepository,
    PostgresReadModelRepository,
    PostgresWorkbenchRepository,
)
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.workbench_pair_relation_service import WorkbenchPairRelationService


class InvoiceUsageCollectionSqlProjectionBuilder:
    """Build SQL read models for invoice relation pages outside the API hot path."""

    def __init__(self, *, connection: Any) -> None:
        self._connection = connection
        self._core_repository = PostgresCoreRepository(connection)
        self._read_repository = PostgresReadModelRepository(connection)
        self._workbench_repository = PostgresWorkbenchRepository(connection)
        self._oa_projection_repository = PostgresOAProjectionRepository(connection)

    def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.INPUT)

    def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.OUTPUT)

    def rebuild_input_invoice_usage_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        service = self._input_service()
        context = service._query_context()
        rows = service._filtered_sorted_rows(
            context=context,
            month=normalized_scope_key,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
        )
        self._read_repository.save_input_invoice_usage_rows(scope_key=normalized_scope_key, rows=rows)
        return {"scope_key": normalized_scope_key, "row_count": len(rows)}

    def rebuild_output_invoice_collection_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        service = self._output_service()
        context = service._query_context()
        rows = service._filtered_sorted_rows(
            context=context,
            month=normalized_scope_key,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
        )
        self._read_repository.save_output_invoice_collection_rows(scope_key=normalized_scope_key, rows=rows)
        return {"scope_key": normalized_scope_key, "row_count": len(rows)}

    def mark_input_invoice_usage_scope_empty(self, scope_key: str) -> None:
        self._read_repository.mark_input_invoice_usage_scope(scope_key=scope_key, row_count=0)

    def mark_output_invoice_collection_scope_empty(self, scope_key: str) -> None:
        self._read_repository.mark_output_invoice_collection_scope(scope_key=scope_key, row_count=0)

    def _input_service(self) -> InputInvoiceUsageQueryService:
        return InputInvoiceUsageQueryService(
            import_service=self._import_service(),
            pair_relation_service=self._pair_relation_service(),
            oa_projection=self._oa_projection_repository,
        )

    def _output_service(self) -> OutputInvoiceCollectionQueryService:
        return OutputInvoiceCollectionQueryService(
            import_service=self._import_service(),
            pair_relation_service=self._pair_relation_service(),
        )

    def _import_service(self) -> ImportNormalizationService:
        return ImportNormalizationService.from_snapshot(None, fact_repository=self._core_repository)

    def _pair_relation_service(self) -> WorkbenchPairRelationService:
        return WorkbenchPairRelationService.from_snapshot(self._workbench_repository.load_workbench_pair_relations())

    def _list_invoice_month_shards(self, *, scope_key: str, invoice_type: InvoiceType) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
        rows = self._connection.fetch_all(
            """
            select distinct to_char(coalesce(invoice_month, date_trunc('month', invoice_date)), 'YYYY-MM') as scope_key
            from app.invoices
            where invoice_type = %s
              and coalesce(invoice_month, invoice_date) is not null
            order by scope_key desc
            """,
            (invoice_type.value,),
        )
        return [
            str(row.get("scope_key"))
            for row in rows
            if isinstance(row, dict) and MONTH_SCOPE_RE.match(str(row.get("scope_key") or ""))
        ]

    @staticmethod
    def _month_scope(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        if not MONTH_SCOPE_RE.match(normalized_scope_key):
            raise ValueError(f"invoice read model scope must be a YYYY-MM shard: {scope_key}")
        return normalized_scope_key
