from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_legacy_batch_lifecycle_service import (
    EtcLegacyBatchLifecycleService,
)


class _EtcService:
    def __init__(self) -> None:
        self.created_drafts: list[tuple[list[str], object | None, object | None]] = []
        self.confirmed_batches: list[str] = []
        self.reopened_batches: list[str] = []
        self.batch = SimpleNamespace(id="submission-1", invoice_ids=["invoice-1"])

    def list_invoices_by_ids(self, invoice_ids: list[str]):
        return [
            SimpleNamespace(invoice_id=invoice_id, import_batch_id="import-1")
            for invoice_id in invoice_ids
        ]

    def create_oa_draft(
        self,
        invoice_ids: list[str],
        *,
        oa_client: object | None,
        reconciliation_task: object | None,
    ):
        self.created_drafts.append((invoice_ids, oa_client, reconciliation_task))
        return SimpleNamespace(
            batch_id="submission-1",
            etc_batch_id="etc-1",
            oa_draft_id="oa-draft-1",
            oa_draft_url="https://oa.example/draft/1",
        )

    def confirm_submitted(self, batch_id: str):
        self.confirmed_batches.append(batch_id)
        return self.batch

    def mark_not_submitted(self, batch_id: str):
        self.reopened_batches.append(batch_id)
        return self.batch


class _TaskService:
    def __init__(self) -> None:
        self.task = SimpleNamespace(task_id="task-1")
        self.draft_created: list[dict[str, object]] = []
        self.submitted_confirmed: list[dict[str, object]] = []

    def find_task_for_import_batch_ids(self, import_batch_ids: list[str]):
        return self.task if import_batch_ids == ["import-1"] else None

    def find_task_for_oa_batch_id(self, batch_id: str):
        return self.task if batch_id == "submission-1" else None

    def record_oa_draft_created(self, **kwargs):
        self.draft_created.append(kwargs)

    def record_oa_submitted_confirmed(self, **kwargs):
        self.submitted_confirmed.append(kwargs)


class EtcLegacyBatchLifecycleServiceTests(unittest.TestCase):
    def test_create_draft_records_task_and_returns_refresh_event(self) -> None:
        etc_service = _EtcService()
        task_service = _TaskService()
        linked_invoice_batches: list[list[object]] = []
        oa_client = object()
        service = EtcLegacyBatchLifecycleService(
            etc_service=etc_service,
            reconciliation_task_service=task_service,
            link_etc_invoices_to_existing_invoices=lambda invoices: linked_invoice_batches.append(invoices) or ["2026-04"],
        )

        result = service.create_draft_from_invoice_ids(["invoice-1"], oa_client=oa_client)

        self.assertEqual(
            result.payload,
            {
                "batchId": "submission-1",
                "etcBatchId": "etc-1",
                "oaDraftId": "oa-draft-1",
                "oaDraftUrl": "https://oa.example/draft/1",
            },
        )
        self.assertEqual(etc_service.created_drafts, [(["invoice-1"], oa_client, task_service.task)])
        self.assertEqual(task_service.draft_created[0]["task_id"], "task-1")
        self.assertEqual(task_service.draft_created[0]["oa_draft_batch_id"], "submission-1")
        self.assertEqual(result.refresh_events[0].reason, "etc_oa_draft_created")
        self.assertEqual(result.refresh_events[0].changed_months, ["2026-04"])
        self.assertEqual(len(linked_invoice_batches), 1)

    def test_confirm_and_reopen_return_distinct_refresh_reasons(self) -> None:
        etc_service = _EtcService()
        task_service = _TaskService()
        service = EtcLegacyBatchLifecycleService(
            etc_service=etc_service,
            reconciliation_task_service=task_service,
            link_etc_invoices_to_existing_invoices=lambda _invoices: ["2026-05"],
        )

        confirmed = service.confirm_submitted("submission-1")
        reopened = service.mark_not_submitted("submission-1")

        self.assertEqual(etc_service.confirmed_batches, ["submission-1"])
        self.assertEqual(etc_service.reopened_batches, ["submission-1"])
        self.assertEqual(task_service.submitted_confirmed[0]["task_id"], "task-1")
        self.assertEqual(confirmed.payload["batch"], etc_service.batch)
        self.assertEqual(reopened.payload["batch"], etc_service.batch)
        self.assertEqual(confirmed.refresh_events[0].reason, "etc_oa_submission_confirmed")
        self.assertEqual(reopened.refresh_events[0].reason, "etc_oa_submission_reopened")
        self.assertEqual(confirmed.refresh_events[0].changed_months, ["2026-05"])


if __name__ == "__main__":
    unittest.main()
