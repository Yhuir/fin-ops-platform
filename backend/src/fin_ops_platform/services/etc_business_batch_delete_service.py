from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.etc_reconciliation_import_cleanup_service import (
    EtcReconciliationImportCleanupService,
)
from fin_ops_platform.services.etc_service import (
    ETC_BUSINESS_BATCH_SUBMITTED_STATUSES,
    EtcBusinessBatchNotFoundError,
)


@dataclass(frozen=True)
class EtcBusinessBatchDeleteRefreshEvent:
    changed_months: list[str]
    reason: str
    persist_required: bool = False


@dataclass(frozen=True)
class EtcBusinessBatchDeleteResult:
    delete_result: dict[str, object]
    refresh_events: list[EtcBusinessBatchDeleteRefreshEvent]


class EtcBusinessBatchDeleteService:
    def __init__(
        self,
        *,
        etc_service: Any,
        import_service: Any,
        reconciliation_task_service: Any,
        cleanup_service: EtcReconciliationImportCleanupService,
        existing_etc_invoices_by_ids: Callable[[list[str]], list[object]],
        etc_invoice_changed_months: Callable[[list[object]], list[str]],
        link_etc_invoices_to_existing_invoices: Callable[[list[object]], list[str]],
        assert_etc_summary_relation_write_precondition_for_batch: Callable[[object], None],
        cancel_etc_summary_relations_for_batch: Callable[[object], list[str]],
    ) -> None:
        self._etc_service = etc_service
        self._import_service = import_service
        self._reconciliation_task_service = reconciliation_task_service
        self._cleanup_service = cleanup_service
        self._existing_etc_invoices_by_ids = existing_etc_invoices_by_ids
        self._etc_invoice_changed_months = etc_invoice_changed_months
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices
        self._assert_etc_summary_relation_write_precondition_for_batch = (
            assert_etc_summary_relation_write_precondition_for_batch
        )
        self._cancel_etc_summary_relations_for_batch = cancel_etc_summary_relations_for_batch

    def delete_business_batch(
        self,
        business_batch_id: str,
        *,
        expected_version: int | None = None,
        reason: str | None = None,
    ) -> EtcBusinessBatchDeleteResult:
        try:
            batch = self._etc_service.get_business_batch(business_batch_id)
        except EtcBusinessBatchNotFoundError:
            delete_result = self._etc_service.delete_business_batch(
                business_batch_id,
                expected_version=expected_version,
                reason=reason,
            )
            return EtcBusinessBatchDeleteResult(delete_result=delete_result, refresh_events=[])

        invoice_ids = [str(invoice_id) for invoice_id in list(getattr(batch, "invoice_ids", []) or [])]
        import_batch_ids = [
            str(import_batch_id).strip()
            for import_batch_id in list(getattr(batch, "import_batch_ids", []) or [])
            if str(import_batch_id).strip()
        ]
        task = self._task_for_batch(batch)
        changed_months = self._etc_invoice_changed_months(self._existing_etc_invoices_by_ids(invoice_ids))
        if str(getattr(batch, "status", "") or "") in ETC_BUSINESS_BATCH_SUBMITTED_STATUSES:
            self._assert_etc_summary_relation_write_precondition_for_batch(batch)

        delete_result = self._etc_service.delete_business_batch(
            business_batch_id,
            expected_version=expected_version,
            reason=reason,
        )

        if delete_result.get("kind") == "submitted_business_batch_reset":
            changed_months.extend(self._cancel_etc_summary_relations_for_batch(batch))
            refreshed_invoices = self._existing_etc_invoices_by_ids(invoice_ids)
            changed_months.extend(self._etc_invoice_changed_months(refreshed_invoices))
            changed_months.extend(self._link_etc_invoices_to_existing_invoices(refreshed_invoices))
            self._cleanup_service.delete_reconciliation_task_after_business_batch_delete(task)
            return EtcBusinessBatchDeleteResult(
                delete_result=delete_result,
                refresh_events=(
                    [
                        EtcBusinessBatchDeleteRefreshEvent(
                            changed_months=sorted(set(changed_months)),
                            reason="etc_submitted_business_batch_reset",
                            persist_required=True,
                        )
                    ]
                    if changed_months
                    else []
                ),
            )

        canonical_deleted = 0
        for import_batch_id in import_batch_ids:
            canonical_deleted += self._import_service.remove_etc_invoices_by_import_batch_id(import_batch_id)
        self._cleanup_service.delete_reconciliation_task_after_business_batch_delete(task)
        return EtcBusinessBatchDeleteResult(
            delete_result=delete_result,
            refresh_events=(
                [
                    EtcBusinessBatchDeleteRefreshEvent(
                        changed_months=changed_months,
                        reason="etc_business_batch_deleted",
                        persist_required=True,
                    )
                ]
                if canonical_deleted or changed_months
                else []
            ),
        )

    def _task_for_batch(self, batch: object) -> object | None:
        task_id = str(getattr(batch, "task_id", "") or "").strip()
        if not task_id:
            return None
        try:
            return self._reconciliation_task_service.get_task(task_id)
        except KeyError:
            return None
