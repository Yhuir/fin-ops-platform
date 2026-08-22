from __future__ import annotations

from typing import Any

from fin_ops_platform.services.oa_attachment_invoice_cache import (
    ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
    attachment_invoice_cache_parser_version,
)
from fin_ops_platform.services.oa_attachment_invoice_promotion_service import (
    OAAttachmentInvoicePromotionService,
)
from fin_ops_platform.services.postgres_repositories.core import PostgresCoreRepository
from fin_ops_platform.services.postgres_repositories.oa_attachment_invoice import (
    PostgresOAAttachmentInvoiceRepository,
)
from fin_ops_platform.services.postgres_repositories.workbench_matching_queue import (
    PostgresWorkbenchMatchingQueueRepository,
)
from fin_ops_platform.services.workbench_reconciliation_dirty_queue import (
    expand_scope_month_window,
)


class ConfirmedInvoiceImportUnitOfWork:
    """One transaction for confirmed facts, reverse OA links, and matching dirtiness."""

    def __init__(self, connection: Any) -> None:
        self._connection = connection

    def execute(
        self,
        *,
        normalized_payload: dict[str, Any],
        scope_months: list[str],
        promotion_mode: str,
        source_versions: dict[str, object],
    ) -> dict[str, Any]:
        imports_snapshot = normalized_payload.get("imports") or {}
        file_imports_snapshot = normalized_payload.get("file_imports") or {}
        expanded_months = sorted(
            {
                expanded
                for month in scope_months
                for expanded in expand_scope_month_window(str(month))
            }
        )
        with self._connection.transaction() as transaction:
            core = PostgresCoreRepository(transaction)
            # This must precede the generic UPSERT: it merges every current
            # provenance edge, including edges absent from today's OA cache.
            core.prepare_confirmed_invoice_upserts_in_transaction(
                transaction,
                imports_snapshot=imports_snapshot,
            )
            core.save_import_delta_in_transaction(
                transaction,
                imports_snapshot=imports_snapshot,
                file_imports_snapshot=file_imports_snapshot,
            )
            strong_keys = self._strong_invoice_keys(imports_snapshot)
            promoter = OAAttachmentInvoicePromotionService(
                invoice_repository=PostgresOAAttachmentInvoiceRepository(
                    transaction,
                    identity_locks_held=True,
                )
            )
            promotion = promoter.promote_confirmed_invoice_identity_keys(
                strong_keys,
                configured_mode=promotion_mode,
                parser_version=attachment_invoice_cache_parser_version(),
                cache_schema_version=ATTACHMENT_INVOICE_CACHE_SCHEMA_VERSION,
                apply=True,
            )
            queued_matching_months = (
                PostgresWorkbenchMatchingQueueRepository.mark_workbench_matching_dirty_scopes_in_transaction(
                    transaction=transaction,
                    tenant_id="default",
                    scope_months=expanded_months,
                    reason="import_file_confirm",
                    source_versions=dict(source_versions or {}),
                    debounce_seconds=60,
                )
                if expanded_months
                else []
            )
        return {
            "queued_matching_months": list(queued_matching_months),
            "oa_attachment_invoice_promotion": promotion,
        }

    @staticmethod
    def _strong_invoice_keys(imports_snapshot: dict[str, Any]) -> set[str]:
        raw_invoices = imports_snapshot.get("invoices")
        invoices = (
            list(raw_invoices.values())
            if isinstance(raw_invoices, dict)
            else list(raw_invoices or [])
            if isinstance(raw_invoices, list)
            else []
        )
        return {
            identity_key
            for invoice in invoices
            if isinstance(invoice, dict)
            if (
                identity_key
                := OAAttachmentInvoicePromotionService.strong_identity_key(invoice)
            )
        }
