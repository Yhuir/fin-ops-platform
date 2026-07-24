from __future__ import annotations

from typing import Any

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
    output_invoice_collection_source_versions,
)
from fin_ops_platform.services.output_invoice_collection_read_model_repository import OutputInvoiceCollectionReadModelRepositoryPort
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

    def __init__(
        self,
        *,
        connection: Any,
        workbench_relation_read_facade: WorkbenchRelationReadFacade | None = None,
        input_invoice_usage_read_model_repository: Any | None = None,
        output_invoice_collection_read_model_repository: Any | None = None,
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
        self._oa_projection_repository = PostgresOAProjectionRepository(connection)
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

    def rebuild_input_invoice_usage_read_model_scope(
        self,
        scope_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        self._require_fresh_workbench_relation_scope(normalized_scope_key)
        source_versions = input_invoice_usage_source_versions(
            payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
            oa_reverse_batch_source_version=None,
        )
        relation_source_versions = self._invoice_relation_source_versions_for_scope(
            normalized_scope_key,
            invoice_type=InvoiceType.INPUT,
        )
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        unchanged = None
        if not force_refresh:
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
            statistics_metadata=_invoice_relation_statistics_metadata(
                rows,
                summary_kind="input",
                scope_key=normalized_scope_key,
            ),
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def rebuild_output_invoice_collection_read_model_scope(
        self,
        scope_key: str,
        *,
        force_refresh: bool = False,
    ) -> dict[str, object]:
        normalized_scope_key = self._month_scope(scope_key)
        self._require_fresh_workbench_relation_scope(normalized_scope_key)
        source_versions = output_invoice_collection_source_versions()
        relation_source_versions = self._invoice_relation_source_versions_for_scope(
            normalized_scope_key,
            invoice_type=InvoiceType.OUTPUT,
        )
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        unchanged = None
        if not force_refresh:
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
            statistics_metadata=_invoice_relation_statistics_metadata(
                rows,
                summary_kind="output",
                scope_key=normalized_scope_key,
            ),
        )
        return {"scope_key": normalized_scope_key, "row_count": len(rows), "source_versions": source_versions}

    def mark_input_invoice_usage_scope_empty(self, scope_key: str) -> None:
        source_versions = input_invoice_usage_source_versions(
            payment_status_rules_version=self._payment_rules_provider.rules_source_version(),
            oa_reverse_batch_source_version=None,
        )
        relation_source_versions = self._invoice_relation_source_versions_for_scope(
            scope_key,
            invoice_type=InvoiceType.INPUT,
        )
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        self._input_invoice_usage_read_model_repository.mark_input_invoice_usage_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=source_versions,
            statistics_metadata=_invoice_relation_statistics_metadata(
                [],
                summary_kind="input",
                scope_key=scope_key,
            ),
        )

    def mark_output_invoice_collection_scope_empty(self, scope_key: str) -> None:
        source_versions = output_invoice_collection_source_versions()
        relation_source_versions = self._invoice_relation_source_versions_for_scope(
            scope_key,
            invoice_type=InvoiceType.OUTPUT,
        )
        if relation_source_versions:
            source_versions["workbench_relation_source_versions"] = relation_source_versions
        self._output_invoice_collection_read_model_repository.mark_output_invoice_collection_scope(
            scope_key=scope_key,
            row_count=0,
            source_versions=source_versions,
            statistics_metadata=_invoice_relation_statistics_metadata(
                [],
                summary_kind="output",
                scope_key=scope_key,
            ),
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
        if not isinstance(payload.get("statistics"), dict):
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

    def _invoice_relation_source_versions_for_scope(
        self,
        scope_key: str,
        *,
        invoice_type: InvoiceType,
    ) -> dict[str, object]:
        method_name = (
            "input_invoice_usage_relation_source_versions"
            if invoice_type == InvoiceType.INPUT
            else "output_invoice_collection_relation_source_versions"
        )
        source_versions_loader = getattr(self._read_repository, method_name, None)
        if callable(source_versions_loader):
            source_versions_by_scope = source_versions_loader(
                scope_keys=[scope_key],
                tenant_id="default",
            )
            source_versions = (
                source_versions_by_scope.get(scope_key)
                if isinstance(source_versions_by_scope, dict)
                else None
            )
            if isinstance(source_versions, dict):
                return dict(source_versions)
        return {}

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


def _invoice_relation_statistics_metadata(
    rows: list[dict[str, object]],
    *,
    summary_kind: str,
    scope_key: str,
) -> dict[str, object]:
    members: dict[str, dict[str, object]] = {}
    formal_group_ids: set[str] = set()
    for index, raw_row in enumerate(rows):
        row = raw_row.get("payload") if isinstance(raw_row.get("payload"), dict) else raw_row
        if not isinstance(row, dict):
            continue
        invoice = row.get("invoice") if isinstance(row.get("invoice"), dict) else {}
        oa = row.get("oa") if isinstance(row.get("oa"), dict) else {}
        bank = row.get("bankTransactions") if isinstance(row.get("bankTransactions"), dict) else {}
        payment = row.get("paymentStatus") if isinstance(row.get("paymentStatus"), dict) else {}
        collection = row.get("collectionStatus") if isinstance(row.get("collectionStatus"), dict) else {}
        receipt = row.get("receipt") if isinstance(row.get("receipt"), dict) else {}
        relation = row.get("invoiceRelations") if isinstance(row.get("invoiceRelations"), dict) else {}
        summaries = relation.get("summaries") if isinstance(relation.get("summaries"), list) else []
        if not summaries:
            summaries = [invoice]
        linked_oa = int(oa.get("relationCount") or 0) > 0
        linked_bank = int(bank.get("relationCount") or 0) > 0
        row_id = str(row.get("id") or raw_row.get("id") or f"row:{index}").strip()
        primary_month = str(invoice.get("invoiceDate") or invoice.get("invoice_date") or "")[:7]
        if row_id and primary_month == scope_key and (linked_oa or linked_bank):
            formal_group_ids.add(row_id)
        for summary in summaries:
            member = summary if isinstance(summary, dict) else {}
            invoice_id = str(
                member.get("invoiceId")
                or member.get("relatedInvoiceId")
                or member.get("primaryInvoiceId")
                or member.get("id")
                or invoice.get("id")
                or row.get("invoiceId")
                or ""
            ).strip()
            if not invoice_id:
                continue
            member_month = str(member.get("invoiceDate") or member.get("invoice_date") or "")[:7]
            primary_invoice_id = str(invoice.get("id") or row.get("invoiceId") or "").strip()
            if not member_month and invoice_id == primary_invoice_id:
                member_month = primary_month
            if member_month != scope_key:
                continue
            flags = members.setdefault(
                invoice_id,
                {
                    "invoice_id": invoice_id,
                    "linked_oa": False,
                    "linked_bank": False,
                    "linked_income_bank": False,
                    "paid": False,
                    "collected": False,
                    "red_invoice": False,
                    "receipt_issued": False,
                },
            )
            flags["linked_oa"] = bool(flags["linked_oa"] or linked_oa)
            flags["linked_bank"] = bool(flags["linked_bank"] or linked_bank)
            flags["linked_income_bank"] = bool(
                flags["linked_income_bank"] or (linked_bank and str(bank.get("direction") or "") == "inflow")
            )
            flags["paid"] = bool(flags["paid"] or str(payment.get("code") or "") == "paid")
            flags["collected"] = bool(
                flags["collected"]
                or str(collection.get("code") or "") in {"collected", "collected_red_refunded"}
            )
            flags["receipt_issued"] = bool(
                flags["receipt_issued"] or str(receipt.get("status") or receipt.get("code") or "") == "issued"
            )
            total_with_tax = str(
                member.get("totalWithTax")
                or member.get("total_with_tax")
                or invoice.get("totalWithTax")
                or ""
            ).strip()
            positive = str(
                member.get("isPositiveInvoice")
                or member.get("is_positive_invoice")
                or invoice.get("isPositiveInvoice")
                or ""
            ).strip()
            flags["red_invoice"] = bool(
                flags["red_invoice"]
                or positive in {"否", "false", "False", "0"}
                or total_with_tax.startswith("-")
            )
    statistics = _invoice_relation_statistics_from_members(
        members,
        summary_kind=summary_kind,
        formal_group_count=len(formal_group_ids),
    )
    return {"statistics": statistics}


def _invoice_relation_statistics_from_members(
    members: dict[str, dict[str, object]],
    *,
    summary_kind: str,
    formal_group_count: int = 0,
) -> dict[str, int]:
    values = list(members.values())
    invoice_count = len(values)
    linked_oa_count = sum(bool(item.get("linked_oa")) for item in values)
    if summary_kind == "input":
        linked_bank_count = sum(bool(item.get("linked_bank")) for item in values)
        paid_count = sum(bool(item.get("paid")) for item in values)
        return {
            "invoice_count": invoice_count,
            "linked_oa_invoice_count": linked_oa_count,
            "linked_bank_invoice_count": linked_bank_count,
            "paid_invoice_count": paid_count,
            "unlinked_oa_invoice_count": invoice_count - linked_oa_count,
            "unlinked_bank_invoice_count": invoice_count - linked_bank_count,
            "unpaid_invoice_count": invoice_count - paid_count,
            "formal_relation_group_count": formal_group_count,
        }
    linked_bank_count = sum(bool(item.get("linked_income_bank")) for item in values)
    collected_count = sum(bool(item.get("collected")) for item in values)
    return {
        "invoice_count": invoice_count,
        "linked_oa_invoice_count": linked_oa_count,
        "linked_income_bank_invoice_count": linked_bank_count,
        "collected_invoice_count": collected_count,
        "unlinked_oa_invoice_count": invoice_count - linked_oa_count,
        "unlinked_bank_invoice_count": invoice_count - linked_bank_count,
        "uncollected_invoice_count": invoice_count - collected_count,
        "red_invoice_count": sum(bool(item.get("red_invoice")) for item in values),
        "issued_receipt_count": sum(bool(item.get("receipt_issued")) for item in values),
    }
