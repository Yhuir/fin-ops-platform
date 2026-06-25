from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_legacy_batch_delete_service import EtcLegacyBatchDeleteService
from fin_ops_platform.services.etc_service import EtcBatchNotFoundError


class _ImportCleanup:
    def __init__(self) -> None:
        self.deleted_import_batches: list[str] = []
        self.cleared_import_batches: list[str] = []

    def delete_unsubmitted_submission_batch(self, *, task: object, actor: str):
        return SimpleNamespace(
            task=task,
            delete_result={
                "deleted": True,
                "batchId": "missing-submission-1",
                "kind": "missing_submission_batch",
            },
            changed_months=["2026-01"],
        )

    def delete_etc_import_batch_sources(self, import_batch_id: str):
        self.deleted_import_batches.append(import_batch_id)
        return SimpleNamespace(
            delete_result={"deleted": True, "batchId": import_batch_id, "kind": "import_batch"},
            canonical_deleted=1,
            changed_months=["2026-02"],
        )

    def clear_task_import_after_batch_delete(self, task: object | None, import_batch_id: str):
        self.cleared_import_batches.append(import_batch_id)
        return task


class _TaskService:
    def __init__(self, task: object | None) -> None:
        self._task = task

    def find_task_for_oa_batch_id(self, _batch_id: str):
        return None

    def find_task_for_submission_batch_id(self, _batch_id: str):
        return self._task

    def find_task_for_import_batch_ids(self, _batch_ids: list[str]):
        return self._task


class EtcLegacyBatchDeleteServiceTests(unittest.TestCase):
    def test_missing_submission_batch_repair_returns_refresh_event_and_import_cleanup(self) -> None:
        task = SimpleNamespace(task_id="task-1", import_batch_id="import-1")
        cleanup = _ImportCleanup()

        class EtcService:
            def get_batch(self, _batch_id: str):
                raise EtcBatchNotFoundError("missing")

            def delete_batch(self, _batch_id: str):
                raise EtcBatchNotFoundError("missing")

        service = EtcLegacyBatchDeleteService(
            etc_service=EtcService(),
            import_service=SimpleNamespace(remove_etc_invoices_by_import_batch_id=lambda _batch_id: 0),
            reconciliation_task_service=_TaskService(task),
            cleanup_service=cleanup,
            existing_etc_invoices_by_ids=lambda _invoice_ids: [],
            etc_invoice_changed_months=lambda _invoices: [],
            link_etc_invoices_to_existing_invoices=lambda _invoices: [],
            etc_import_batch_by_id=lambda _batch_id: None,
        )

        result = service.delete_non_business_batch("missing-submission-1")

        self.assertEqual(result.delete_result["kind"], "missing_submission_batch")
        self.assertEqual(cleanup.deleted_import_batches, ["import-1"])
        self.assertEqual(cleanup.cleared_import_batches, ["import-1"])
        self.assertEqual(len(result.refresh_events), 1)
        self.assertEqual(result.refresh_events[0].reason, "etc_missing_oa_draft_link_repaired")
        self.assertTrue(result.refresh_events[0].persist_required)
        self.assertEqual(result.refresh_events[0].changed_months, ["2026-01", "2026-02"])

    def test_import_batch_delete_returns_refresh_event_without_http_or_application_dependency(self) -> None:
        cleanup = _ImportCleanup()
        removed_import_batches: list[str] = []
        import_batch = SimpleNamespace(invoice_ids=["invoice-1"])
        invoice = SimpleNamespace(month="2026-03")

        class EtcService:
            def get_batch(self, _batch_id: str):
                raise EtcBatchNotFoundError("missing")

            def delete_batch(self, batch_id: str):
                return {"deleted": True, "batchId": batch_id, "kind": "import_batch"}

        service = EtcLegacyBatchDeleteService(
            etc_service=EtcService(),
            import_service=SimpleNamespace(
                remove_etc_invoices_by_import_batch_id=lambda batch_id: removed_import_batches.append(batch_id) or 1
            ),
            reconciliation_task_service=_TaskService(None),
            cleanup_service=cleanup,
            existing_etc_invoices_by_ids=lambda invoice_ids: [invoice] if invoice_ids == ["invoice-1"] else [],
            etc_invoice_changed_months=lambda invoices: ["2026-03"] if invoices else [],
            link_etc_invoices_to_existing_invoices=lambda _invoices: [],
            etc_import_batch_by_id=lambda _batch_id: import_batch,
        )

        result = service.delete_non_business_batch("import-1")

        self.assertEqual(result.delete_result, {"deleted": True, "batchId": "import-1", "kind": "import_batch"})
        self.assertEqual(removed_import_batches, ["import-1"])
        self.assertEqual(cleanup.cleared_import_batches, ["import-1"])
        self.assertEqual(len(result.refresh_events), 1)
        self.assertEqual(result.refresh_events[0].reason, "etc_import_batch_deleted")
        self.assertEqual(result.refresh_events[0].changed_months, ["2026-03"])
        self.assertTrue(result.refresh_events[0].persist_required)


if __name__ == "__main__":
    unittest.main()
