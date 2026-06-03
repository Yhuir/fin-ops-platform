from __future__ import annotations

from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    PostgresInputInvoiceUsagePaymentRulesStateStore,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    input_invoice_usage_source_versions,
    oa_pending_payment_source_versions,
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.postgres_repositories import (
    PostgresCoreRepository,
    PostgresOAProjectionRepository,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.output_invoice_collection import (
    build_output_invoice_collection_lifecycle_repository,
)
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class InvoiceUsageCollectionSqlProjectionBuilder:
    """Build SQL read models for invoice relation pages outside the API hot path."""

    def __init__(self, *, connection: Any, workbench_relation_read_facade: WorkbenchRelationReadFacade | None = None) -> None:
        self._connection = connection
        self._core_repository = PostgresCoreRepository(connection)
        self._read_repository = PostgresReadModelRepository(connection)
        self._oa_projection_repository = PostgresOAProjectionRepository(connection)
        self._workbench_relation_read_facade = workbench_relation_read_facade or WorkbenchRelationReadFacade(
            read_model_repository=self._read_repository,
        )
        self._payment_rules_provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(
            state_store=PostgresInputInvoiceUsagePaymentRulesStateStore(connection),
        )

    def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.INPUT)

    def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.OUTPUT)

    def list_oa_pending_payment_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
        rows = self._connection.fetch_all(
            """
            select distinct to_char(scope_month, 'YYYY-MM') as scope_key
            from app.oa_applications
            where scope_month is not null
            order by scope_key desc
            """
        )
        return [
            str(row.get("scope_key"))
            for row in rows
            if isinstance(row, dict) and MONTH_SCOPE_RE.match(str(row.get("scope_key") or ""))
        ]

    def rebuild_input_invoice_usage_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        service = self._input_service()
        context = service._query_context(month_hint=normalized_scope_key)
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
        source_versions = input_invoice_usage_source_versions(
            payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
        )
        if self._workbench_relation_read_facade.last_source_versions:
            source_versions["workbench_relation_source_versions"] = self._workbench_relation_read_facade.last_source_versions
        self._read_repository.save_input_invoice_usage_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_output_invoice_collection_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        service = self._output_service()
        context = service._query_context(month_hint=normalized_scope_key)
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
        source_versions = output_invoice_collection_source_versions()
        if self._workbench_relation_read_facade.last_source_versions:
            source_versions["workbench_relation_source_versions"] = self._workbench_relation_read_facade.last_source_versions
        self._read_repository.save_output_invoice_collection_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_oa_pending_payment_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        service = self._oa_pending_payment_service()
        context = service._query_context(month_hint=normalized_scope_key)
        rows = service._filtered_sorted_rows(
            context=context,
            month=normalized_scope_key,
            keyword=None,
            trade_date_from=None,
            trade_date_to=None,
            filters=[],
            sort_field="bank_trade_time",
            sort_direction="desc",
        )
        source_versions = oa_pending_payment_source_versions()
        if self._workbench_relation_read_facade.last_source_versions:
            source_versions["workbench_relation_source_versions"] = self._workbench_relation_read_facade.last_source_versions
        self._read_repository.save_oa_pending_payment_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def mark_input_invoice_usage_scope_empty(self, scope_key: str) -> None:
        self._read_repository.mark_input_invoice_usage_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=input_invoice_usage_source_versions(
                payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
            ),
        )

    def mark_output_invoice_collection_scope_empty(self, scope_key: str) -> None:
        self._read_repository.mark_output_invoice_collection_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=output_invoice_collection_source_versions(),
        )

    def mark_oa_pending_payment_scope_empty(self, scope_key: str) -> None:
        self._read_repository.mark_oa_pending_payment_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=oa_pending_payment_source_versions(),
        )

    def _input_service(self) -> InputInvoiceUsageQueryService:
        return InputInvoiceUsageQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            oa_projection=self._oa_projection_repository,
            payment_rules_provider=self._payment_rules_provider,
            require_fresh_relations=True,
        )

    def _output_service(self) -> OutputInvoiceCollectionQueryService:
        return OutputInvoiceCollectionQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            lifecycle_repository=build_output_invoice_collection_lifecycle_repository(self._connection),
            require_fresh_relations=True,
        )

    def _oa_pending_payment_service(self) -> OaPendingPaymentQueryService:
        return OaPendingPaymentQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            oa_projection=self._oa_projection_repository,
            require_fresh_relations=True,
        )

    def _import_service(self) -> ImportNormalizationService:
        return ImportNormalizationService.from_snapshot(None, fact_repository=self._core_repository)

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
