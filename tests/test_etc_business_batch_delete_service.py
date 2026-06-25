from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_business_batch_delete_service import EtcBusinessBatchDeleteService
from fin_ops_platform.services.etc_service import EtcBusinessBatchNotFoundError


class _Cleanup:
    def __init__(self) -> None:
        self.deleted_tasks: list[object | None] = []

    def delete_reconciliation_task_after_business_batch_delete(self, task: object | None) -> None:
        self.deleted_tasks.append(task)


class _TaskService:
    def __init__(self, task: object | None) -> None:
        self._task = task

    def get_task(self, task_id: str) -> object:
        if self._task is None or str(getattr(self._task, "task_id", "")) != task_id:
            raise KeyError(task_id)
        return self._task


class EtcBusinessBatchDeleteServiceTests(unittest.TestCase):
    def test_unsubmitted_business_batch_delete_removes_canonical_invoices_and_returns_refresh_event(self) -> None:
        batch = SimpleNamespace(
            business_batch_id="business-1",
            status="draft",
            invoice_ids=["invoice-1"],
            import_batch_ids=["import-1"],
            task_id="task-1",
        )
        task = SimpleNamespace(task_id="task-1")
        cleanup = _Cleanup()
        removed_import_batches: list[str] = []

        class EtcService:
            def get_business_batch(self, batch_id: str) -> object:
                return batch

            def delete_business_batch(
                self,
                business_batch_id: str,
                *,
                expected_version: int | None = None,
                reason: str | None = None,
            ) -> dict[str, object]:
                return {
                    "deleted": True,
                    "businessBatchId": business_batch_id,
                    "kind": "business_batch",
                    "expectedVersion": expected_version,
                    "reason": reason,
                }

        service = EtcBusinessBatchDeleteService(
            etc_service=EtcService(),
            import_service=SimpleNamespace(
                remove_etc_invoices_by_import_batch_id=lambda batch_id: removed_import_batches.append(batch_id) or 1
            ),
            reconciliation_task_service=_TaskService(task),
            cleanup_service=cleanup,
            existing_etc_invoices_by_ids=lambda invoice_ids: (
                [SimpleNamespace(month="2026-02")] if invoice_ids == ["invoice-1"] else []
            ),
            etc_invoice_changed_months=lambda invoices: ["2026-02"] if invoices else [],
            link_etc_invoices_to_existing_invoices=lambda _invoices: [],
            assert_etc_summary_relation_write_precondition_for_batch=lambda _batch: None,
            cancel_etc_summary_relations_for_batch=lambda _batch: [],
        )

        result = service.delete_business_batch("business-1", expected_version=3, reason="delete")

        self.assertEqual(result.delete_result["kind"], "business_batch")
        self.assertEqual(result.delete_result["expectedVersion"], 3)
        self.assertEqual(result.delete_result["reason"], "delete")
        self.assertEqual(removed_import_batches, ["import-1"])
        self.assertEqual(cleanup.deleted_tasks, [task])
        self.assertEqual(len(result.refresh_events), 1)
        self.assertEqual(result.refresh_events[0].changed_months, ["2026-02"])
        self.assertEqual(result.refresh_events[0].reason, "etc_business_batch_deleted")
        self.assertTrue(result.refresh_events[0].persist_required)

    def test_submitted_business_batch_delete_runs_relation_preflight_cancel_and_cleanup(self) -> None:
        batch = SimpleNamespace(
            business_batch_id="business-2",
            status="oa_submitted",
            invoice_ids=["invoice-1"],
            import_batch_ids=["import-1"],
            task_id="task-2",
        )
        task = SimpleNamespace(task_id="task-2")
        cleanup = _Cleanup()
        preflight_batches: list[object] = []
        cancelled_batches: list[object] = []
        linked_invoice_calls: list[list[object]] = []
        invoice = SimpleNamespace(month="2026-02")

        class EtcService:
            def get_business_batch(self, batch_id: str) -> object:
                return batch

            def delete_business_batch(
                self,
                business_batch_id: str,
                *,
                expected_version: int | None = None,
                reason: str | None = None,
            ) -> dict[str, object]:
                return {
                    "deleted": True,
                    "businessBatchId": business_batch_id,
                    "kind": "submitted_business_batch_reset",
                    "releasedInvoiceCount": 1,
                    "submissionBatchId": "submission-1",
                }

        service = EtcBusinessBatchDeleteService(
            etc_service=EtcService(),
            import_service=SimpleNamespace(remove_etc_invoices_by_import_batch_id=lambda _batch_id: 0),
            reconciliation_task_service=_TaskService(task),
            cleanup_service=cleanup,
            existing_etc_invoices_by_ids=lambda invoice_ids: [invoice] if invoice_ids == ["invoice-1"] else [],
            etc_invoice_changed_months=lambda invoices: ["2026-02"] if invoices else [],
            link_etc_invoices_to_existing_invoices=lambda invoices: (
                linked_invoice_calls.append(list(invoices)) or ["2026-03"]
            ),
            assert_etc_summary_relation_write_precondition_for_batch=lambda checked_batch: (
                preflight_batches.append(checked_batch)
            ),
            cancel_etc_summary_relations_for_batch=lambda checked_batch: (
                cancelled_batches.append(checked_batch) or ["2026-04"]
            ),
        )

        result = service.delete_business_batch("business-2", expected_version=7, reason="reset")

        self.assertEqual(result.delete_result["kind"], "submitted_business_batch_reset")
        self.assertEqual(preflight_batches, [batch])
        self.assertEqual(cancelled_batches, [batch])
        self.assertEqual(linked_invoice_calls, [[invoice]])
        self.assertEqual(cleanup.deleted_tasks, [task])
        self.assertEqual(len(result.refresh_events), 1)
        self.assertEqual(result.refresh_events[0].changed_months, ["2026-02", "2026-03", "2026-04"])
        self.assertEqual(result.refresh_events[0].reason, "etc_submitted_business_batch_reset")
        self.assertTrue(result.refresh_events[0].persist_required)

    def test_missing_business_batch_delete_preserves_idempotent_fallback(self) -> None:
        class EtcService:
            def get_business_batch(self, _batch_id: str) -> object:
                raise EtcBusinessBatchNotFoundError("missing")

            def delete_business_batch(
                self,
                business_batch_id: str,
                *,
                expected_version: int | None = None,
                reason: str | None = None,
            ) -> dict[str, object]:
                return {"deleted": True, "businessBatchId": business_batch_id, "kind": "business_batch"}

        cleanup = _Cleanup()
        service = EtcBusinessBatchDeleteService(
            etc_service=EtcService(),
            import_service=SimpleNamespace(remove_etc_invoices_by_import_batch_id=lambda _batch_id: 0),
            reconciliation_task_service=_TaskService(None),
            cleanup_service=cleanup,
            existing_etc_invoices_by_ids=lambda _invoice_ids: [],
            etc_invoice_changed_months=lambda _invoices: [],
            link_etc_invoices_to_existing_invoices=lambda _invoices: [],
            assert_etc_summary_relation_write_precondition_for_batch=lambda _batch: None,
            cancel_etc_summary_relations_for_batch=lambda _batch: [],
        )

        result = service.delete_business_batch("etc_business_batch_missing", expected_version=1, reason="retry")

        self.assertEqual(
            result.delete_result,
            {"deleted": True, "businessBatchId": "etc_business_batch_missing", "kind": "business_batch"},
        )
        self.assertEqual(result.refresh_events, [])
        self.assertEqual(cleanup.deleted_tasks, [])


if __name__ == "__main__":
    unittest.main()
