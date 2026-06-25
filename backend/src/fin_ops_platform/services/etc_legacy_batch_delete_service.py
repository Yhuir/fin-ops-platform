from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.etc_reconciliation_import_cleanup_service import (
    EtcReconciliationImportCleanupService,
)
from fin_ops_platform.services.etc_service import EtcBatchNotFoundError


@dataclass(frozen=True)
class EtcLegacyBatchRefreshEvent:
    changed_months: list[str]
    reason: str
    persist_required: bool = False


@dataclass(frozen=True)
class EtcLegacyBatchDeleteResult:
    delete_result: dict[str, object]
    refresh_events: list[EtcLegacyBatchRefreshEvent]


class EtcLegacyBatchDeleteService:
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
        etc_import_batch_by_id: Callable[[str], object | None],
    ) -> None:
        self._etc_service = etc_service
        self._import_service = import_service
        self._reconciliation_task_service = reconciliation_task_service
        self._cleanup_service = cleanup_service
        self._existing_etc_invoices_by_ids = existing_etc_invoices_by_ids
        self._etc_invoice_changed_months = etc_invoice_changed_months
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices
        self._etc_import_batch_by_id = etc_import_batch_by_id

    def delete_non_business_batch(self, batch_id: str) -> EtcLegacyBatchDeleteResult:
        task = None
        resolved_submission_batch_id = batch_id
        submission_invoice_ids: list[str] = []
        submission_import_batch_ids: list[str] = []
        import_batch_changed_months: list[str] = []
        existing_batch = None
        try:
            existing_batch = self._etc_service.get_batch(batch_id)
            resolved_submission_batch_id = str(getattr(existing_batch, "id", "") or batch_id)
            submission_invoice_ids = [
                str(invoice_id)
                for invoice_id in list(getattr(existing_batch, "invoice_ids", []) or [])
            ]
            submission_invoices = self._existing_etc_invoices_by_ids(submission_invoice_ids)
            submission_import_batch_ids = sorted(
                {
                    str(getattr(invoice, "import_batch_id", "") or "").strip()
                    for invoice in submission_invoices
                    if str(getattr(invoice, "import_batch_id", "") or "").strip()
                }
            )
            task = self._reconciliation_task_service.find_task_for_oa_batch_id(
                str(getattr(existing_batch, "id", ""))
            )
        except EtcBatchNotFoundError:
            import_batch = self._etc_import_batch_by_id(batch_id)
            if import_batch is not None:
                import_batch_invoices = self._existing_etc_invoices_by_ids(
                    [
                        str(invoice_id)
                        for invoice_id in list(getattr(import_batch, "invoice_ids", []) or [])
                    ]
                )
                import_batch_changed_months = self._etc_invoice_changed_months(import_batch_invoices)
            task = self._reconciliation_task_service.find_task_for_submission_batch_id(batch_id)
            if task is None and import_batch is not None:
                task = self._reconciliation_task_service.find_task_for_import_batch_ids([batch_id])

        try:
            delete_result = self._etc_service.delete_batch(batch_id)
        except EtcBatchNotFoundError as error:
            repaired = self._repair_missing_submission_batch_link(task=task, error=error)
            if repaired is not None:
                return repaired
            raise

        refresh_events: list[EtcLegacyBatchRefreshEvent] = []
        if delete_result.get("kind") == "submission_batch" and task is not None:
            task = self._reconciliation_task_service.record_oa_draft_deleted(
                task_id=str(getattr(task, "task_id")),
                oa_draft_batch_id=resolved_submission_batch_id,
                etc_batch_id=str(getattr(existing_batch, "etc_batch_id", "") or ""),
                actor="system",
            )
        if delete_result.get("kind") == "submission_batch" and submission_import_batch_ids:
            changed_months: list[str] = []
            for import_batch_id in submission_import_batch_ids:
                import_cleanup = self._cleanup_service.delete_etc_import_batch_sources(import_batch_id)
                changed_months.extend(import_cleanup.changed_months)
                task = self._cleanup_service.clear_task_import_after_batch_delete(task, import_batch_id)
            refresh_events.append(
                EtcLegacyBatchRefreshEvent(
                    changed_months=changed_months,
                    reason="etc_submission_batch_contents_deleted",
                    persist_required=True,
                )
            )
        if (
            delete_result.get("kind") == "submission_batch"
            and submission_invoice_ids
            and not submission_import_batch_ids
        ):
            existing_invoices = self._existing_etc_invoices_by_ids(submission_invoice_ids)
            if existing_invoices:
                changed_months = self._link_etc_invoices_to_existing_invoices(existing_invoices)
                refresh_events.append(
                    EtcLegacyBatchRefreshEvent(
                        changed_months=changed_months,
                        reason="etc_oa_draft_deleted",
                    )
                )
        if delete_result.get("kind") == "import_batch":
            delete_batch_id = str(delete_result.get("batchId") or batch_id)
            canonical_deleted = self._import_service.remove_etc_invoices_by_import_batch_id(
                delete_batch_id
            )
            self._cleanup_service.clear_task_import_after_batch_delete(task, delete_batch_id)
            if canonical_deleted or import_batch_changed_months:
                refresh_events.append(
                    EtcLegacyBatchRefreshEvent(
                        changed_months=import_batch_changed_months,
                        reason="etc_import_batch_deleted",
                        persist_required=True,
                    )
                )
        return EtcLegacyBatchDeleteResult(delete_result=delete_result, refresh_events=refresh_events)

    def _repair_missing_submission_batch_link(
        self,
        *,
        task: object | None,
        error: EtcBatchNotFoundError,
    ) -> EtcLegacyBatchDeleteResult | None:
        if task is None:
            return None
        try:
            submission_cleanup = self._cleanup_service.delete_unsubmitted_submission_batch(
                task=task,
                actor="system",
            )
        except EtcBatchNotFoundError as cleanup_error:
            raise error from cleanup_error
        delete_result = submission_cleanup.delete_result
        if delete_result is None:
            return None
        task = submission_cleanup.task
        changed_months = list(submission_cleanup.changed_months)
        import_batch_id = str(getattr(task, "import_batch_id", "") or "").strip()
        if import_batch_id:
            import_cleanup = self._cleanup_service.delete_etc_import_batch_sources(import_batch_id)
            changed_months.extend(import_cleanup.changed_months)
            self._cleanup_service.clear_task_import_after_batch_delete(task, import_batch_id)
        return EtcLegacyBatchDeleteResult(
            delete_result=delete_result,
            refresh_events=[
                EtcLegacyBatchRefreshEvent(
                    changed_months=changed_months,
                    reason="etc_missing_oa_draft_link_repaired",
                    persist_required=True,
                )
            ],
        )
