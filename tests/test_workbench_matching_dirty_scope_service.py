import unittest

from fin_ops_platform.services.workbench_matching_dirty_scope_service import WorkbenchMatchingDirtyScopeService


class WorkbenchMatchingDirtyScopeServiceTests(unittest.TestCase):
    def test_mark_dirty_dedupes_months_and_reasons(self) -> None:
        service = WorkbenchMatchingDirtyScopeService()

        marked = service.mark_dirty(["2026-05", "2026-05", "all"], reason="import_confirm", error="boom")
        service.mark_dirty(["2026-05"], reason="import_confirm")
        service.mark_dirty(["2026-05"], reason="oa_sync")

        self.assertEqual(marked, ["2026-05"])
        entries = service.list_dirty_scopes()
        self.assertEqual(len(entries), 1)
        self.assertEqual(entries[0]["scope_month"], "2026-05")
        self.assertEqual(entries[0]["reasons"], ["import_confirm", "oa_sync"])
        self.assertEqual(entries[0]["last_error"], "boom")

    def test_take_dirty_scopes_removes_scopes_in_order(self) -> None:
        service = WorkbenchMatchingDirtyScopeService()
        service.mark_dirty(["2026-05", "2026-03"], reason="unit")

        self.assertEqual(service.take_dirty_scopes(limit=1), ["2026-03"])
        self.assertEqual([entry["scope_month"] for entry in service.list_dirty_scopes()], ["2026-05"])
        self.assertEqual(service.take_dirty_scopes(), ["2026-05"])
        self.assertEqual(service.list_dirty_scopes(), [])

    def test_requeue_dirty_scopes_increments_attempt_count(self) -> None:
        service = WorkbenchMatchingDirtyScopeService()

        service.requeue_dirty_scopes(["2026-05"], reason="worker", error="failed")

        entry = service.list_dirty_scopes()[0]
        self.assertEqual(entry["attempt_count"], 1)
        self.assertEqual(entry["last_error"], "failed")

    def test_snapshot_round_trip(self) -> None:
        service = WorkbenchMatchingDirtyScopeService()
        service.mark_dirty(["2026-05"], reason="import_confirm")

        restored = WorkbenchMatchingDirtyScopeService.from_snapshot(service.snapshot())

        self.assertEqual(restored.snapshot(), service.snapshot())


if __name__ == "__main__":
    unittest.main()
