from __future__ import annotations

from typing import Any, Callable

from fin_ops_platform.domain.enums import InvoiceType
from fin_ops_platform.services.imports import ImportNormalizationService
from fin_ops_platform.services.input_invoice_usage_read_model_repository import InputInvoiceUsageReadModelRepositoryPort
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
from fin_ops_platform.services.oa_payment_status_service import OAPaymentStatusRepository
from fin_ops_platform.services.oa_payment_admitted_projection import PaymentAdmittedOAProjectionAdapter
from fin_ops_platform.services.oa_pending_payment_read_model_repository import OaPendingPaymentReadModelRepositoryPort
from fin_ops_platform.services.oa_pending_payment_service import OaPendingPaymentQueryService
from fin_ops_platform.services.output_invoice_collection_read_model_repository import OutputInvoiceCollectionReadModelRepositoryPort
from fin_ops_platform.services.output_invoice_collection_service import OutputInvoiceCollectionQueryService
from fin_ops_platform.services.postgres_repositories import (
    PostgresCoreRepository,
    PostgresOaPendingPaymentRelationRepository,
    PostgresOAProjectionRepository,
    PostgresReadModelRepository,
)
from fin_ops_platform.services.postgres_repositories.output_invoice_collection import (
    build_output_invoice_collection_lifecycle_repository,
)
from fin_ops_platform.services.postgres_repositories.oa_pending_payment_admission import (
    PostgresOaPendingPaymentAdmissionRepository,
    oa_pending_payment_records_signature,
)
from fin_ops_platform.services.postgres_repositories.read_models import MONTH_SCOPE_RE
from fin_ops_platform.services.workbench_relation_read_facade import WorkbenchRelationReadFacade


class InvoiceUsageCollectionSqlProjectionBuilder:
    """Build SQL read models for invoice relation pages outside the API hot path."""

    def __init__(
        self,
        *,
        connection: Any,
        workbench_relation_read_facade: WorkbenchRelationReadFacade | None = None,
        payment_status_repository: OAPaymentStatusRepository | None = None,
        oa_source_adapter: Any | None = None,
        input_invoice_usage_read_model_repository: Any | None = None,
        output_invoice_collection_read_model_repository: Any | None = None,
        oa_pending_payment_read_model_repository: Any | None = None,
        oa_pending_payment_admission_repository: Any | None = None,
    ) -> None:
        self._connection = connection
        self._core_repository = PostgresCoreRepository(connection)
        self._read_repository = PostgresReadModelRepository(connection)
        self._input_invoice_usage_read_model_repository = (
            input_invoice_usage_read_model_repository
            or InputInvoiceUsageReadModelRepositoryPort(self._read_repository)
        )
        self._output_invoice_collection_read_model_repository = (
            output_invoice_collection_read_model_repository
            or OutputInvoiceCollectionReadModelRepositoryPort(self._read_repository)
        )
        self._oa_pending_payment_read_model_repository = (
            oa_pending_payment_read_model_repository
            or OaPendingPaymentReadModelRepositoryPort(self._read_repository)
        )
        self._oa_pending_payment_admission_repository = (
            oa_pending_payment_admission_repository
            or PostgresOaPendingPaymentAdmissionRepository(connection)
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

    def list_input_invoice_usage_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.INPUT)

    def prune_input_invoice_usage_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._input_invoice_usage_read_model_repository.prune_input_invoice_usage_scope_shards(current_scope_keys)

    def list_output_invoice_collection_scope_shards(self, scope_key: str) -> list[str]:
        return self._list_invoice_month_shards(scope_key=scope_key, invoice_type=InvoiceType.OUTPUT)

    def prune_output_invoice_collection_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._output_invoice_collection_read_model_repository.prune_output_invoice_collection_scope_shards(current_scope_keys)

    def list_oa_pending_payment_scope_shards(self, scope_key: str) -> list[str]:
        normalized_scope_key = str(scope_key or "").strip()
        if MONTH_SCOPE_RE.match(normalized_scope_key):
            return [normalized_scope_key]
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

    def prune_oa_pending_payment_scope_shards(self, current_scope_keys: list[str]) -> None:
        self._oa_pending_payment_admission_repository.prune_scopes(current_scope_keys)
        self._oa_pending_payment_read_model_repository.prune_oa_pending_payment_scope_shards(current_scope_keys)

    def rebuild_input_invoice_usage_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        self._require_fresh_workbench_relation_scope(normalized_scope_key)
        source_versions = input_invoice_usage_source_versions(
            payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
        )
        relation_source_versions = self._workbench_relation_source_versions_for_scope(normalized_scope_key)
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        unchanged = self._unchanged_scope_result(
            self._input_invoice_usage_read_model_repository,
            "list_input_invoice_usage_rows",
            scope_key=normalized_scope_key,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return unchanged
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
        self._input_invoice_usage_read_model_repository.save_input_invoice_usage_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_output_invoice_collection_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        self._require_fresh_workbench_relation_scope(normalized_scope_key)
        source_versions = output_invoice_collection_source_versions()
        relation_source_versions = self._workbench_relation_source_versions_for_scope(normalized_scope_key)
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        unchanged = self._unchanged_scope_result(
            self._output_invoice_collection_read_model_repository,
            "list_output_invoice_collection_rows",
            scope_key=normalized_scope_key,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return unchanged
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
        self._output_invoice_collection_read_model_repository.save_output_invoice_collection_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_oa_pending_payment_read_model_scope(self, scope_key: str) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        payment_statuses_by_flow_id: dict[str, Any] | None = None
        in_progress_projection = self._oa_pending_payment_projection(
            payment_statuses_provider=lambda: payment_statuses_by_flow_id,
        )
        service = self._oa_pending_payment_service(
            payment_statuses_provider=lambda: payment_statuses_by_flow_id,
            in_progress_oa_projection=in_progress_projection,
        )
        context = service._query_context(month_hint=normalized_scope_key)
        payment_statuses_by_flow_id = service._payment_statuses_by_flow_id()
        completed_records = service._oa_records(
            month=normalized_scope_key,
            view_mode="completed",
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        in_progress_records = service._oa_records(
            month=normalized_scope_key,
            view_mode="in_progress",
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
        )
        self._oa_pending_payment_admission_repository.replace_scope(
            scope_key=normalized_scope_key,
            records=in_progress_records,
        )
        source_versions = {
            **oa_pending_payment_source_versions(),
            "completed_oa_signature": oa_pending_payment_records_signature(completed_records),
            "in_progress_admission_signature": oa_pending_payment_records_signature(in_progress_records),
            "in_progress_admission_count": len(in_progress_records),
        }
        relation_source_versions = self._workbench_relation_source_versions_for_scope(normalized_scope_key)
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        unchanged = self._unchanged_scope_result(
            self._oa_pending_payment_read_model_repository,
            "list_oa_pending_payment_rows",
            scope_key=normalized_scope_key,
            source_versions=source_versions,
        )
        if unchanged is not None:
            return unchanged
        completed_rows = service._build_rows(
            month=normalized_scope_key,
            context=context,
            view_mode="completed",
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            records=completed_records,
        )
        in_progress_rows = service._build_rows(
            month=normalized_scope_key,
            context=context,
            view_mode="in_progress",
            payment_statuses_by_flow_id=payment_statuses_by_flow_id,
            records=in_progress_records,
        )
        cleanup_result = self._cancel_oa_pending_relations_missing_admission(
            month_scope=normalized_scope_key,
            admitted_oa_row_ids=_oa_pending_payment_row_oa_ids(in_progress_rows),
        )
        rows = [*completed_rows, *in_progress_rows]
        self._oa_pending_payment_read_model_repository.save_oa_pending_payment_rows(
            scope_key=normalized_scope_key,
            rows=rows,
            source_versions=source_versions,
        )
        return {
            "scope_key": normalized_scope_key,
            "row_count": len(rows),
            "source_versions": source_versions,
            "pending_relation_cleanup": cleanup_result,
        }

    def mark_input_invoice_usage_scope_empty(self, scope_key: str) -> None:
        self._input_invoice_usage_read_model_repository.mark_input_invoice_usage_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=input_invoice_usage_source_versions(
                payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
            ),
        )

    def mark_output_invoice_collection_scope_empty(self, scope_key: str) -> None:
        self._output_invoice_collection_read_model_repository.mark_output_invoice_collection_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=output_invoice_collection_source_versions(),
        )

    def mark_oa_pending_payment_scope_empty(self, scope_key: str) -> None:
        self._oa_pending_payment_admission_repository.replace_scope(scope_key=scope_key, records=[])
        self._oa_pending_payment_read_model_repository.mark_oa_pending_payment_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=oa_pending_payment_source_versions(),
        )

    @staticmethod
    def _unchanged_scope_result(
        repository: Any,
        list_method_name: str,
        *,
        scope_key: str,
        source_versions: dict[str, object],
    ) -> dict[str, object] | None:
        list_rows = getattr(repository, list_method_name, None)
        if not callable(list_rows):
            return None
        payload = list_rows(month=scope_key, page=1, page_size=1)
        if not isinstance(payload, dict):
            return None
        existing_source_versions = payload.get("source_versions")
        if not isinstance(existing_source_versions, dict) or existing_source_versions != source_versions:
            return None
        pagination = payload.get("pagination") if isinstance(payload.get("pagination"), dict) else {}
        return {
            "scope_key": scope_key,
            "row_count": int(pagination.get("total") or len(list(payload.get("rows") or []))),
            "source_versions": source_versions,
            "skipped": True,
            "skip_reason": "source_versions_unchanged",
        }

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
            oa_projection=self._oa_projection_repository,
            lifecycle_repository=build_output_invoice_collection_lifecycle_repository(self._connection),
            require_fresh_relations=True,
        )

    def _oa_pending_payment_service(
        self,
        *,
        payment_statuses_provider: Callable[[], dict[str, Any] | None] | None = None,
        in_progress_oa_projection: PaymentAdmittedOAProjectionAdapter | None = None,
    ) -> OaPendingPaymentQueryService:
        return OaPendingPaymentQueryService(
            import_service=self._import_service(),
            relation_facade=self._workbench_relation_read_facade,
            pending_relation_service=PostgresOaPendingPaymentRelationRepository(self._connection),
            oa_projection=self._oa_projection_repository,
            in_progress_oa_projection=in_progress_oa_projection
            or self._oa_pending_payment_projection(payment_statuses_provider=payment_statuses_provider),
            payment_status_repository=self._payment_status_repository,
            require_fresh_relations=True,
        )

    def _oa_pending_payment_projection(
        self,
        *,
        payment_statuses_provider: Callable[[], dict[str, Any] | None] | None = None,
    ) -> PaymentAdmittedOAProjectionAdapter:
        return PaymentAdmittedOAProjectionAdapter(
            source_adapter=self._oa_source_adapter,
            payment_status_repository=self._payment_status_repository,
            payment_statuses_provider=payment_statuses_provider,
        )

    def _cancel_oa_pending_relations_missing_admission(
        self,
        *,
        month_scope: str,
        admitted_oa_row_ids: list[str],
    ) -> dict[str, object]:
        if self._payment_status_repository is None:
            return {"changed_relation_ids": [], "affected_months": [], "skipped": "payment_status_repository_unavailable"}
        read_status = self._oa_pending_payment_projection().get_read_status()
        if str(getattr(read_status, "code", "") or "").strip() not in {"ready", "fresh"}:
            return {
                "changed_relation_ids": [],
                "affected_months": [],
                "skipped": "oa_admission_projection_not_ready",
                "read_status": str(getattr(read_status, "code", "") or "").strip(),
            }
        repository = PostgresOaPendingPaymentRelationRepository(self._connection)
        return repository.cancel_active_relations_missing_oa_admission(
            month_scope=month_scope,
            admitted_oa_row_ids=admitted_oa_row_ids,
            actor_id="system:oa_pending_payment_read_model_refresh",
        )

    def _workbench_relation_source_versions_for_scope(self, scope_key: str) -> dict[str, object]:
        source_versions_loader = getattr(self._read_repository, "workbench_relation_source_versions", None)
        if callable(source_versions_loader):
            source_versions = source_versions_loader(scope_key=scope_key)
            if isinstance(source_versions, dict) and source_versions:
                return dict(source_versions)
        return dict(self._workbench_relation_read_facade.last_source_versions)

    def _require_fresh_workbench_relation_scope(self, scope_key: str) -> None:
        payload = self._workbench_relation_read_facade.list_by_month(
            scope_key,
            require_fresh=True,
            reason="invoice_usage_collection_sql_projection",
        )
        if not isinstance(payload, dict) or str(payload.get("status") or "") != "fresh":
            raise RuntimeError("workbench_relation_read_model_not_fresh")

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


def _oa_pending_payment_row_oa_ids(rows: list[dict[str, Any]]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for row in rows:
        oa_payload = row.get("oa") if isinstance(row, dict) else None
        if not isinstance(oa_payload, dict):
            continue
        candidates: list[Any] = [oa_payload.get("id"), oa_payload.get("oaId")]
        summaries = oa_payload.get("summaries")
        if isinstance(summaries, list):
            for summary in summaries:
                if isinstance(summary, dict):
                    candidates.extend([summary.get("oaId"), summary.get("id")])
        for candidate in candidates:
            normalized = str(candidate).strip() if candidate is not None else ""
            if normalized and normalized not in seen:
                seen.add(normalized)
                result.append(normalized)
    return result
