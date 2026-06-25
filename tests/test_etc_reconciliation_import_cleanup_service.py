from __future__ import annotations

from types import SimpleNamespace
import unittest

from fin_ops_platform.services.etc_reconciliation_import_cleanup_service import EtcReconciliationImportCleanupService


class EtcReconciliationImportCleanupServiceTests(unittest.TestCase):
    def test_submitted_business_batch_cleanup_requires_relation_preflight_before_delete(self) -> None:
        calls: list[str] = []
        business_batch = SimpleNamespace(
            business_batch_id="business-1",
            status="oa_submitted",
            version=7,
            import_batch_ids=["import-1"],
            invoice_ids=["invoice-1"],
            task_id="task-1",
        )
        task = SimpleNamespace(task_id="task-1", import_batch_id="import-1", oa_draft_batch_id=None, etc_batch_id=None)

        class FakeEtcService:
            def list_business_batches(self, *, task_id: str):
                assert task_id == "task-1"
                return [business_batch]

            def find_business_batch_by_linked_batch_id(self, _linked_id: str):
                return None

            def delete_business_batch(self, business_batch_id: str, *, expected_version: int, reason: str):
                calls.append("delete_business_batch")
                assert business_batch_id == "business-1"
                assert expected_version == 7
                assert reason == "reconciliation_task_import_removed"
                return {"deleted": True, "kind": "submitted_business_batch_reset"}

        class FakeImportService:
            def remove_etc_invoices_by_import_batch_id(self, import_batch_id: str) -> int:
                calls.append(f"remove_canonical:{import_batch_id}")
                return 2

        def existing_etc_invoices_by_ids(invoice_ids: list[str]) -> list[object]:
            self.assertEqual(invoice_ids, ["invoice-1"])
            return [SimpleNamespace(month="2026-02")]

        def changed_months(_invoices: list[object]) -> list[str]:
            return ["2026-02"]

        def link_existing(_invoices: list[object]) -> list[str]:
            calls.append("link_existing")
            return ["2026-03"]

        def assert_precondition(batch: object) -> None:
            calls.append("preflight")
            self.assertIs(batch, business_batch)

        def cancel_summary(batch: object) -> list[str]:
            calls.append("cancel_summary")
            self.assertIs(batch, business_batch)
            return ["2026-04"]

        service = EtcReconciliationImportCleanupService(
            etc_service=FakeEtcService(),
            import_service=FakeImportService(),
            reconciliation_task_service=SimpleNamespace(),
            existing_etc_invoices_by_ids=existing_etc_invoices_by_ids,
            etc_invoice_changed_months=changed_months,
            link_etc_invoices_to_existing_invoices=link_existing,
            etc_import_batch_by_id=lambda _import_batch_id: None,
            assert_etc_summary_relation_write_precondition_for_batch=assert_precondition,
            cancel_etc_summary_relations_for_batch=cancel_summary,
        )

        result = service.delete_task_import_batch_sources(task)

        self.assertEqual(calls[:3], ["remove_canonical:import-1", "preflight", "delete_business_batch"])
        self.assertIn("cancel_summary", calls)
        self.assertIn("link_existing", calls)
        self.assertEqual(result.delete_result, {"deleted": True, "kind": "submitted_business_batch_reset"})
        self.assertEqual(result.canonical_deleted, 2)
        self.assertEqual(result.changed_months, ["2026-02", "2026-03", "2026-04"])


if __name__ == "__main__":
    unittest.main()
