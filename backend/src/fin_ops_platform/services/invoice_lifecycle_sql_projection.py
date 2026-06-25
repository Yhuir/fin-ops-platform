from __future__ import annotations

from typing import Any

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_payment_rules import (
    AppSettingsInputInvoiceUsagePaymentRulesProvider,
    PostgresInputInvoiceUsagePaymentRulesStateStore,
)
from fin_ops_platform.services.input_invoice_usage_service import InputInvoiceUsageQueryService
from fin_ops_platform.services.invoice_lifecycle_policy import InvoiceLifecyclePolicy
from fin_ops_platform.services.invoice_lifecycle_read_model_repository import InvoiceLifecycleReadModelRepositoryPort
from fin_ops_platform.services.invoice_usage_collection_source_versions import (
    input_invoice_usage_source_versions,
    oa_pending_payment_source_versions,
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRepository
from fin_ops_platform.services.oa_payment_admitted_projection import PaymentAdmittedOAProjectionAdapter
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
from fin_ops_platform.services.search_pending_sql_projection import SearchPendingSqlProjectionBuilder
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class InvoiceLifecycleSqlProjectionBuilder:
    """Build the invoice lifecycle distribution read model outside API hot paths."""

    def __init__(
        self,
        *,
        connection: Any,
        read_model_repository: PostgresReadModelRepository | None = None,
        workbench_relation_read_facade: WorkbenchRelationReadFacade | None = None,
        payment_status_repository: OAPaymentStatusRepository | None = None,
        oa_source_adapter: Any | None = None,
        invoice_lifecycle_read_model_repository: Any | None = None,
    ) -> None:
        self._connection = connection
        self._core_repository = PostgresCoreRepository(connection)
        self._read_repository = read_model_repository or PostgresReadModelRepository(connection)
        self._invoice_lifecycle_read_model_repository = (
            invoice_lifecycle_read_model_repository
            or InvoiceLifecycleReadModelRepositoryPort(self._read_repository)
        )
        self._oa_projection_repository = PostgresOAProjectionRepository(connection)
        self._payment_status_repository = payment_status_repository
        self._oa_source_adapter = oa_source_adapter
        self._workbench_relation_read_facade = workbench_relation_read_facade or WorkbenchRelationReadFacade(
            read_model_repository=self._read_repository,
        )
        self._payment_rules_provider = AppSettingsInputInvoiceUsagePaymentRulesProvider(
            state_store=PostgresInputInvoiceUsagePaymentRulesStateStore(connection),
        )
        self._policy = InvoiceLifecyclePolicy(input_payment_rules_provider=self._payment_rules_provider)
        self._read_model_dependency_source_versions: dict[str, object] = {}

    def list_invoice_lifecycle_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
        months: set[str] = set()
        months.update(self._invoice_month_shards(invoice_type=InvoiceType.INPUT))
        months.update(self._invoice_month_shards(invoice_type=InvoiceType.OUTPUT))
        months.update(self._oa_month_shards())
        months.update(self._bank_transaction_month_shards())
        return sorted(months, reverse=True)

    def rebuild_invoice_lifecycle_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        self._read_model_dependency_source_versions = {}
        rows = []
        rows.extend(self._pending_invoice_lifecycle_rows(normalized_scope_key))
        rows.extend(self._input_invoice_lifecycle_rows(normalized_scope_key))
        rows.extend(self._output_invoice_lifecycle_rows(normalized_scope_key))
        rows.extend(self._oa_pending_payment_lifecycle_rows(normalized_scope_key))
        source_versions = self._source_versions()
        self._invoice_lifecycle_read_model_repository.save_invoice_lifecycle_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def mark_invoice_lifecycle_scope_empty(self, scope_key: str) -> None:
        self._invoice_lifecycle_read_model_repository.mark_invoice_lifecycle_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=self._source_versions(),
        )

    def _pending_invoice_lifecycle_rows(self, month: str) -> list[dict[str, Any]]:
        builder = SearchPendingSqlProjectionBuilder(
            connection=self._connection,
            read_model_repository=self._read_repository,
            workbench_relation_read_facade=self._workbench_relation_read_facade,
        )
        rows: list[dict[str, Any]] = []
        for direction in ("expense", "income"):
            for row in builder._pending_invoice_rows(direction=direction, filter_name="all", month=month):
                bank = row.get("bank_transaction") if isinstance(row.get("bank_transaction"), dict) else {}
                status = row.get("invoice_acquisition_status") if isinstance(row.get("invoice_acquisition_status"), dict) else {}
                subject_id = str(row.get("id") or bank.get("id") or "").strip()
                if not subject_id:
                    continue
                rows.append(
                    {
                        "subject_id": subject_id,
                        "subject_type": "bank_transaction",
                        "scope_key": month,
                        "scope_month": month,
                        "lifecycle_status": _status_code(status),
                        "acquisition_status": status,
                        "payment_status": {},
                        "collection_status": {},
                        "certification_status": {},
                    }
                )
        return rows

    def _input_invoice_lifecycle_rows(self, month: str) -> list[dict[str, Any]]:
        page_rows = self._fresh_read_model_rows(
            "list_input_invoice_usage_rows",
            month=month,
            sort_field="invoice_date",
            sort_direction="desc",
            source_versions_key="input_invoice_usage_read_model_source_versions",
        )
        if page_rows is not None:
            return [
                row
                for page_row in page_rows
                if (row := self._input_invoice_lifecycle_row(page_row, month)) is not None
            ]
        service = InputInvoiceUsageQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            oa_projection=self._oa_projection_repository,
            payment_rules_provider=self._payment_rules_provider,
            lifecycle_policy=self._policy,
            require_fresh_relations=True,
        )
        context = service._query_context(month_hint=month)
        page_rows = service._filtered_sorted_rows(
            context=context,
            month=month,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
        )
        return [
            row
            for page_row in page_rows
            if (row := self._input_invoice_lifecycle_row(page_row, month)) is not None
        ]

    def _output_invoice_lifecycle_rows(self, month: str) -> list[dict[str, Any]]:
        page_rows = self._fresh_read_model_rows(
            "list_output_invoice_collection_rows",
            month=month,
            sort_field="invoice_date",
            sort_direction="desc",
            source_versions_key="output_invoice_collection_read_model_source_versions",
        )
        if page_rows is not None:
            return [
                row
                for page_row in page_rows
                if (row := self._output_invoice_lifecycle_row(page_row, month)) is not None
            ]
        service = OutputInvoiceCollectionQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            lifecycle_repository=build_output_invoice_collection_lifecycle_repository(self._connection),
            lifecycle_policy=self._policy,
            require_fresh_relations=True,
        )
        context = service._query_context(month_hint=month)
        page_rows = service._filtered_sorted_rows(
            context=context,
            month=month,
            keyword=None,
            invoice_date_from=None,
            invoice_date_to=None,
            filters=[],
            sort_field="invoice_date",
            sort_direction="desc",
        )
        return [
            row
            for page_row in page_rows
            if (row := self._output_invoice_lifecycle_row(page_row, month)) is not None
        ]

    def _oa_pending_payment_lifecycle_rows(self, month: str) -> list[dict[str, Any]]:
        page_rows = self._fresh_read_model_rows(
            "list_oa_pending_payment_rows",
            month=month,
            sort_field="bank_trade_time",
            sort_direction="desc",
            source_versions_key="oa_pending_payment_read_model_source_versions",
            view_mode="completed",
        )
        if page_rows is not None:
            return [
                row
                for page_row in page_rows
                if (row := self._oa_pending_payment_lifecycle_row(page_row, month)) is not None
            ]
        service = OaPendingPaymentQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            oa_projection=self._oa_projection_repository,
            in_progress_oa_projection=self._oa_pending_payment_projection(),
            payment_status_repository=self._payment_status_repository,
            lifecycle_policy=self._policy,
            require_fresh_relations=True,
        )
        context = service._query_context(month_hint=month)
        page_rows = service._filtered_sorted_rows(
            context=context,
            month=month,
            keyword=None,
            trade_date_from=None,
            trade_date_to=None,
            filters=[],
            sort_field="bank_trade_time",
            sort_direction="desc",
        )
        return [
            row
            for page_row in page_rows
            if (row := self._oa_pending_payment_lifecycle_row(page_row, month)) is not None
        ]

    def _fresh_read_model_rows(
        self,
        list_method_name: str,
        *,
        month: str,
        sort_field: str,
        sort_direction: str,
        source_versions_key: str,
        view_mode: str | None = None,
    ) -> list[dict[str, Any]] | None:
        list_rows = getattr(self._read_repository, list_method_name, None)
        if not callable(list_rows):
            return None
        rows: list[dict[str, Any]] = []
        page = 1
        page_size = 200
        while True:
            kwargs: dict[str, Any] = {
                "month": month,
                "page": page,
                "page_size": page_size,
                "sort_field": sort_field,
                "sort_direction": sort_direction,
            }
            if view_mode is not None:
                kwargs["view_mode"] = view_mode
            payload = list_rows(**kwargs)
            if not isinstance(payload, dict) or payload.get("refresh_status") != "fresh":
                return None
            if page == 1:
                source_versions = payload.get("source_versions")
                if isinstance(source_versions, dict) and source_versions:
                    self._read_model_dependency_source_versions[source_versions_key] = dict(source_versions)
            page_rows = [row for row in list(payload.get("rows") or []) if isinstance(row, dict)]
            rows.extend(page_rows)
            pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
            total = int(pagination.get("total") or len(rows))
            if len(rows) >= total or not page_rows:
                return rows
            page += 1

    @staticmethod
    def _input_invoice_lifecycle_row(row: dict[str, Any], month: str) -> dict[str, Any] | None:
        status = row.get("paymentStatus") if isinstance(row.get("paymentStatus"), dict) else {}
        subject_id = str(row.get("invoiceId") or "").strip()
        if not subject_id:
            return None
        return {
            "subject_id": subject_id,
            "subject_type": "input_invoice",
            "scope_key": month,
            "scope_month": month,
            "invoice_identity_key": row.get("invoiceIdentityKey"),
            "lifecycle_status": _status_code(status),
            "acquisition_status": {},
            "payment_status": status,
            "collection_status": {},
            "certification_status": {},
        }

    @staticmethod
    def _output_invoice_lifecycle_row(row: dict[str, Any], month: str) -> dict[str, Any] | None:
        status = row.get("collectionStatus") if isinstance(row.get("collectionStatus"), dict) else {}
        subject_id = str(row.get("invoiceId") or "").strip()
        if not subject_id:
            return None
        return {
            "subject_id": subject_id,
            "subject_type": "output_invoice",
            "scope_key": month,
            "scope_month": month,
            "invoice_identity_key": row.get("invoiceIdentityKey"),
            "lifecycle_status": _status_code(status),
            "acquisition_status": {},
            "payment_status": {},
            "collection_status": status,
            "certification_status": {},
        }

    @staticmethod
    def _oa_pending_payment_lifecycle_row(row: dict[str, Any], month: str) -> dict[str, Any] | None:
        oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        status = row.get("paymentStatus") if isinstance(row.get("paymentStatus"), dict) else {}
        subject_id = str(oa.get("id") or row.get("id") or "").strip()
        if not subject_id:
            return None
        return {
            "subject_id": subject_id,
            "subject_type": "oa_application",
            "scope_key": month,
            "scope_month": month,
            "lifecycle_status": _status_code(status),
            "acquisition_status": {},
            "payment_status": status,
            "collection_status": {},
            "certification_status": {},
        }

    def _source_versions(self) -> dict[str, object]:
        source_versions: dict[str, object] = {
            **self._policy.source_versions(),
            "invoice_lifecycle_read_model_schema_version": 1,
            "input_invoice_usage_source_versions": input_invoice_usage_source_versions(
                payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
            ),
            "output_invoice_collection_source_versions": output_invoice_collection_source_versions(),
            "oa_pending_payment_source_versions": oa_pending_payment_source_versions(),
        }
        if self._workbench_relation_read_facade.last_source_versions:
            source_versions["workbench_relation_source_versions"] = self._workbench_relation_read_facade.last_source_versions
        source_versions.update(self._read_model_dependency_source_versions)
        return source_versions

    def _import_service(self) -> ImportNormalizationService:
        return ImportNormalizationService.from_snapshot(None, fact_repository=self._core_repository)

    def _invoice_month_shards(self, *, invoice_type: InvoiceType) -> list[str]:
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
        return [str(row.get("scope_key")) for row in rows if MONTH_SCOPE_RE.match(str(row.get("scope_key") or ""))]

    def _oa_month_shards(self) -> list[str]:
        months: set[str] = set()
        list_completed_months = getattr(self._oa_projection_repository, "list_available_months", None)
        if callable(list_completed_months):
            months.update(str(month).strip() for month in list_completed_months() if MONTH_SCOPE_RE.match(str(month or "")))
        months.update(
            str(month).strip()
            for month in self._oa_pending_payment_projection().list_available_months()
            if MONTH_SCOPE_RE.match(str(month or ""))
        )
        return sorted(months, reverse=True)

    def _oa_pending_payment_projection(self) -> PaymentAdmittedOAProjectionAdapter:
        return PaymentAdmittedOAProjectionAdapter(
            source_adapter=self._oa_source_adapter,
            payment_status_repository=self._payment_status_repository,
        )

    def _bank_transaction_month_shards(self) -> list[str]:
        rows = self._connection.fetch_all(
            """
            select distinct to_char(txn_month, 'YYYY-MM') as scope_key
            from app.bank_transactions
            where txn_month is not null
              and status <> 'deleted'
            order by scope_key desc
            """
        )
        return [str(row.get("scope_key")) for row in rows if MONTH_SCOPE_RE.match(str(row.get("scope_key") or ""))]

    @staticmethod
    def _month_scope(scope_key: str) -> str:
        normalized_scope_key = str(scope_key or "").strip()
        if not MONTH_SCOPE_RE.match(normalized_scope_key):
            raise ValueError(f"invoice lifecycle scope must be a YYYY-MM shard: {scope_key}")
        return normalized_scope_key


def _status_code(status: dict[str, Any]) -> str:
    return str(status.get("code") or "unknown").strip() or "unknown"
