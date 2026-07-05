from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

from fin_ops_platform.services.etc_service import ETC_BUSINESS_BATCH_SUBMITTED_STATUSES, EtcBatchNotFoundError


@dataclass(frozen=True)
class EtcImportedInvoicesRemovalResult:
    updated_task: object
    delete_result: dict[str, object]
    changed_months: list[str]


@dataclass(frozen=True)
class EtcTaskImportCleanupResult:
    task: object
    removed_import_batch: dict[str, object] | None
    removed_submission_batch: dict[str, object] | None
    changed_months: list[str]


@dataclass(frozen=True)
class EtcImportBatchCleanupResult:
    delete_result: dict[str, object]
    changed_months: list[str]


@dataclass(frozen=True)
class EtcSubmissionBatchCleanupResult:
    task: object
    delete_result: dict[str, object] | None
    changed_months: list[str]


class EtcReconciliationImportCleanupService:
    def __init__(
        self,
        *,
        etc_service: Any,
        reconciliation_task_service: Any,
        existing_etc_invoices_by_ids: Callable[[list[str]], list[object]],
        etc_invoice_changed_months: Callable[[list[object]], list[str]],
        link_etc_invoices_to_existing_invoices: Callable[[list[object]], list[str]],
        etc_import_batch_by_id: Callable[[str], object | None],
        assert_etc_summary_relation_write_precondition_for_batch: Callable[[object], None],
        cancel_etc_summary_relations_for_batch: Callable[[object], list[str]],
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._existing_etc_invoices_by_ids = existing_etc_invoices_by_ids
        self._etc_invoice_changed_months = etc_invoice_changed_months
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices
        self._etc_import_batch_by_id = etc_import_batch_by_id
        self._assert_etc_summary_relation_write_precondition_for_batch = (
            assert_etc_summary_relation_write_precondition_for_batch
        )
        self._cancel_etc_summary_relations_for_batch = cancel_etc_summary_relations_for_batch

    def remove_imported_invoices(
        self,
        *,
        task: object,
        expected_version: int,
        actor: str,
    ) -> EtcImportedInvoicesRemovalResult:
        if int(getattr(task, "version", 0) or 0) != expected_version:
            raise ValueError("task_version_conflict")
        import_batch_id = str(getattr(task, "import_batch_id", "") or "").strip()
        if not import_batch_id:
            raise ValueError("reconciliation_task_import_batch_required")
        submission_cleanup = self.delete_unsubmitted_submission_batch(task=task, actor=actor)
        task = submission_cleanup.task
        if (
            str(getattr(task, "oa_draft_batch_id", "") or "").strip()
            or str(getattr(task, "etc_batch_id", "") or "").strip()
            or getattr(task, "submitted_confirmed_at", None) is not None
        ):
            raise ValueError("reconciliation_task_has_submission_link")
        import_cleanup = self.delete_task_import_batch_sources(task)
        changed_months = [*submission_cleanup.changed_months, *import_cleanup.changed_months]
        updated_task = self._reconciliation_task_service.remove_imported_invoices(
            task_id=str(getattr(task, "task_id", "")),
            expected_version=int(getattr(task, "version", expected_version) or expected_version),
            import_batch_id=import_batch_id,
            actor=actor,
        )
        return EtcImportedInvoicesRemovalResult(
            updated_task=updated_task,
            delete_result=import_cleanup.delete_result,
            changed_months=changed_months,
        )

    def cleanup_task_import_sources(self, *, task: object, actor: str) -> EtcTaskImportCleanupResult:
        removed_submission_batch: dict[str, object] | None = None
        changed_months: list[str] = []
        if str(getattr(task, "import_batch_id", "") or "").strip():
            if self.reconciliation_task_business_batch_for_import(task) is None:
                submission_cleanup = self.delete_unsubmitted_submission_batch(task=task, actor=actor)
                task = submission_cleanup.task
                removed_submission_batch = submission_cleanup.delete_result
                changed_months.extend(submission_cleanup.changed_months)
            import_cleanup = self.delete_task_import_batch_sources(task)
            changed_months.extend(import_cleanup.changed_months)
            return EtcTaskImportCleanupResult(
                task=task,
                removed_import_batch=import_cleanup.delete_result,
                removed_submission_batch=removed_submission_batch,
                changed_months=sorted(set(changed_months)),
            )
        return EtcTaskImportCleanupResult(
            task=task,
            removed_import_batch=None,
            removed_submission_batch=None,
            changed_months=[],
        )

    def delete_unsubmitted_submission_batch(
        self,
        *,
        task: object,
        actor: str,
    ) -> EtcSubmissionBatchCleanupResult:
        oa_draft_batch_id = str(getattr(task, "oa_draft_batch_id", "") or "").strip()
        etc_batch_id = str(getattr(task, "etc_batch_id", "") or "").strip()
        if not oa_draft_batch_id and not etc_batch_id:
            return EtcSubmissionBatchCleanupResult(task=task, delete_result=None, changed_months=[])

        delete_batch_id = oa_draft_batch_id or etc_batch_id
        try:
            batch = self._etc_service.get_batch(delete_batch_id)
        except EtcBatchNotFoundError:
            refreshed_invoices = self._etc_service.release_missing_submission_batch_link(delete_batch_id)
            changed_months = self._etc_invoice_changed_months(refreshed_invoices)
            if refreshed_invoices:
                changed_months.extend(self._link_etc_invoices_to_existing_invoices(refreshed_invoices))
            task = self._reconciliation_task_service.record_oa_draft_deleted(
                task_id=str(getattr(task, "task_id", "")),
                oa_draft_batch_id=oa_draft_batch_id or delete_batch_id,
                etc_batch_id=etc_batch_id,
                actor=actor,
            )
            return EtcSubmissionBatchCleanupResult(
                task=task,
                delete_result={"deleted": True, "batchId": delete_batch_id, "kind": "missing_submission_batch"},
                changed_months=sorted(set(changed_months)),
            )
        invoice_ids = [str(invoice_id) for invoice_id in list(getattr(batch, "invoice_ids", []) or [])]
        changed_months = self._etc_invoice_changed_months(self._existing_etc_invoices_by_ids(invoice_ids))
        delete_result = self._etc_service.delete_batch(delete_batch_id)
        refreshed_invoices = self._existing_etc_invoices_by_ids(invoice_ids)
        changed_months.extend(self._etc_invoice_changed_months(refreshed_invoices))
        if refreshed_invoices:
            changed_months.extend(self._link_etc_invoices_to_existing_invoices(refreshed_invoices))
        if delete_result.get("kind") == "submission_batch":
            task = self._reconciliation_task_service.record_oa_draft_deleted(
                task_id=str(getattr(task, "task_id", "")),
                oa_draft_batch_id=str(getattr(batch, "id", "") or delete_batch_id),
                etc_batch_id=str(getattr(batch, "etc_batch_id", "") or etc_batch_id),
                actor=actor,
            )
        return EtcSubmissionBatchCleanupResult(
            task=task,
            delete_result=delete_result,
            changed_months=sorted(set(changed_months)),
        )

    def delete_task_import_batch_sources(self, task: object) -> EtcImportBatchCleanupResult:
        import_batch_id = str(getattr(task, "import_batch_id", "") or "").strip()
        if not import_batch_id:
            raise ValueError("reconciliation_task_import_batch_required")
        business_delete_result = self.delete_reconciliation_task_business_batch_sources(task)
        if business_delete_result is not None:
            return business_delete_result
        return self.delete_etc_import_batch_sources(import_batch_id)

    def reconciliation_task_business_batch_for_import(self, task: object):
        task_id = str(getattr(task, "task_id", "") or "").strip()
        import_batch_id = str(getattr(task, "import_batch_id", "") or "").strip()
        candidate_batches = self._etc_service.list_business_batches(task_id=task_id) if task_id else []
        if candidate_batches:
            if not import_batch_id:
                return candidate_batches[0]
            matched_batch = next(
                (
                    batch
                    for batch in candidate_batches
                    if import_batch_id in {str(value) for value in list(getattr(batch, "import_batch_ids", []) or [])}
                ),
                None,
            )
            if matched_batch is not None:
                return matched_batch
        linked_ids = [
            import_batch_id,
            str(getattr(task, "oa_draft_batch_id", "") or "").strip(),
            str(getattr(task, "etc_batch_id", "") or "").strip(),
        ]
        for linked_id in linked_ids:
            linked_batch = self._etc_service.find_business_batch_by_linked_batch_id(linked_id)
            if linked_batch is not None:
                return linked_batch
        return None

    def delete_reconciliation_task_business_batch_sources(
        self,
        task: object,
    ) -> EtcImportBatchCleanupResult | None:
        business_batch = self.reconciliation_task_business_batch_for_import(task)
        if business_batch is None:
            return None
        import_batch_ids = [
            str(value).strip()
            for value in list(getattr(business_batch, "import_batch_ids", []) or [])
            if str(value).strip()
        ]
        invoice_ids = [str(value) for value in list(getattr(business_batch, "invoice_ids", []) or [])]
        changed_months = self._etc_invoice_changed_months(self._existing_etc_invoices_by_ids(invoice_ids))
        if str(getattr(business_batch, "status", "") or "") in ETC_BUSINESS_BATCH_SUBMITTED_STATUSES:
            self._assert_etc_summary_relation_write_precondition_for_batch(business_batch)
        delete_result = self._etc_service.delete_business_batch(
            str(getattr(business_batch, "business_batch_id", "")),
            expected_version=int(getattr(business_batch, "version", 0) or 0),
            reason="reconciliation_task_import_removed",
        )
        if delete_result.get("kind") == "submitted_business_batch_reset":
            changed_months.extend(self._cancel_etc_summary_relations_for_batch(business_batch))
            refreshed_invoices = self._existing_etc_invoices_by_ids(invoice_ids)
            changed_months.extend(self._etc_invoice_changed_months(refreshed_invoices))
            if refreshed_invoices:
                changed_months.extend(self._link_etc_invoices_to_existing_invoices(refreshed_invoices))
        if delete_result.get("kind") != "submitted_business_batch_reset":
            for linked_import_batch_id in import_batch_ids:
                if self._etc_service.list_invoices_by_import_batch_id(linked_import_batch_id):
                    self._etc_service.delete_import_batch_sources(linked_import_batch_id)
        return EtcImportBatchCleanupResult(
            delete_result=delete_result,
            changed_months=sorted(set(changed_months)),
        )

    def delete_etc_import_batch_sources(self, import_batch_id: str) -> EtcImportBatchCleanupResult:
        import_batch = self._etc_import_batch_by_id(import_batch_id)
        if import_batch is not None:
            etc_invoices = self._existing_etc_invoices_by_ids(
                [str(invoice_id) for invoice_id in list(getattr(import_batch, "invoice_ids", []) or [])]
            )
        else:
            etc_invoices = self._etc_service.list_invoices_by_import_batch_id(import_batch_id)
        changed_months = self._etc_invoice_changed_months(etc_invoices)
        delete_result = self._etc_service.delete_import_batch_sources(import_batch_id)
        return EtcImportBatchCleanupResult(
            delete_result=delete_result,
            changed_months=changed_months,
        )

    def clear_task_import_after_batch_delete(self, task: object | None, import_batch_id: str) -> object | None:
        if task is None:
            return None
        normalized_import_batch_id = str(import_batch_id or "").strip()
        if not normalized_import_batch_id or str(getattr(task, "import_batch_id", "") or "").strip() != normalized_import_batch_id:
            return task
        if (
            str(getattr(task, "oa_draft_batch_id", "") or "").strip()
            or str(getattr(task, "etc_batch_id", "") or "").strip()
            or getattr(task, "submitted_confirmed_at", None) is not None
        ):
            return task
        return self._reconciliation_task_service.remove_imported_invoices(
            task_id=str(getattr(task, "task_id", "")),
            expected_version=int(getattr(task, "version", 0) or 0),
            import_batch_id=normalized_import_batch_id,
            actor="system",
        )

    def delete_reconciliation_task_after_business_batch_delete(self, task: object | None) -> dict[str, object] | None:
        if task is None:
            return None
        task_id = str(getattr(task, "task_id", "") or "").strip()
        if not task_id:
            return None
        try:
            return self._reconciliation_task_service.delete_task(
                task_id=task_id,
                expected_version=int(getattr(task, "version", 0) or 0),
                actor="system",
                import_cleanup_confirmed=True,
            )
        except KeyError:
            return None
