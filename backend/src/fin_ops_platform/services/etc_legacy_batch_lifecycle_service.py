from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EtcLegacyBatchLifecycleRefreshEvent:
    changed_months: list[str]
    reason: str


@dataclass(frozen=True)
class EtcLegacyBatchDraftResult:
    payload: dict[str, object]
    refresh_events: list[EtcLegacyBatchLifecycleRefreshEvent]


@dataclass(frozen=True)
class EtcLegacyBatchTransitionResult:
    payload: dict[str, object]
    refresh_events: list[EtcLegacyBatchLifecycleRefreshEvent]


class EtcLegacyBatchLifecycleService:
    def __init__(
        self,
        *,
        etc_service: Any,
        reconciliation_task_service: Any,
        link_etc_invoices_to_existing_invoices: Any,
    ) -> None:
        self._etc_service = etc_service
        self._reconciliation_task_service = reconciliation_task_service
        self._link_etc_invoices_to_existing_invoices = link_etc_invoices_to_existing_invoices

    def create_draft_from_invoice_ids(
        self,
        invoice_ids: list[str],
        *,
        oa_client: object | None,
    ) -> EtcLegacyBatchDraftResult:
        invoices = self._etc_service.list_invoices_by_ids(invoice_ids)
        import_batch_ids = [
            str(getattr(invoice, "import_batch_id", "") or "")
            for invoice in invoices
            if str(getattr(invoice, "import_batch_id", "") or "").strip()
        ]
        reconciliation_task = self._reconciliation_task_service.find_task_for_import_batch_ids(
            import_batch_ids
        )
        draft = self._etc_service.create_oa_draft(
            invoice_ids,
            oa_client=oa_client,
            reconciliation_task=reconciliation_task,
        )
        if reconciliation_task is not None:
            self._reconciliation_task_service.record_oa_draft_created(
                task_id=str(getattr(reconciliation_task, "task_id")),
                oa_draft_batch_id=draft.batch_id,
                etc_batch_id=draft.etc_batch_id,
                actor="system",
            )
        changed_months = self._link_etc_invoices_to_existing_invoices(
            self._etc_service.list_invoices_by_ids(invoice_ids),
        )
        return EtcLegacyBatchDraftResult(
            payload={
                "batchId": draft.batch_id,
                "etcBatchId": draft.etc_batch_id,
                "oaDraftId": draft.oa_draft_id,
                "oaDraftUrl": draft.oa_draft_url,
            },
            refresh_events=[
                EtcLegacyBatchLifecycleRefreshEvent(
                    changed_months=changed_months,
                    reason="etc_oa_draft_created",
                )
            ],
        )

    def confirm_submitted(self, batch_id: str) -> EtcLegacyBatchTransitionResult:
        batch = self._etc_service.confirm_submitted(batch_id)
        task = self._reconciliation_task_service.find_task_for_oa_batch_id(
            str(getattr(batch, "id", ""))
        )
        if task is not None:
            self._reconciliation_task_service.record_oa_submitted_confirmed(
                task_id=str(getattr(task, "task_id")),
                oa_draft_batch_id=str(getattr(batch, "id", "")),
                actor="system",
            )
        changed_months = self._link_etc_invoices_to_existing_invoices(
            self._etc_service.list_invoices_by_ids(list(batch.invoice_ids)),
        )
        return EtcLegacyBatchTransitionResult(
            payload={"batch": batch},
            refresh_events=[
                EtcLegacyBatchLifecycleRefreshEvent(
                    changed_months=changed_months,
                    reason="etc_oa_submission_confirmed",
                )
            ],
        )

    def mark_not_submitted(self, batch_id: str) -> EtcLegacyBatchTransitionResult:
        batch = self._etc_service.mark_not_submitted(batch_id)
        changed_months = self._link_etc_invoices_to_existing_invoices(
            self._etc_service.list_invoices_by_ids(list(batch.invoice_ids)),
        )
        return EtcLegacyBatchTransitionResult(
            payload={"batch": batch},
            refresh_events=[
                EtcLegacyBatchLifecycleRefreshEvent(
                    changed_months=changed_months,
                    reason="etc_oa_submission_reopened",
                )
            ],
        )
